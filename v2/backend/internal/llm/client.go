// Package llm 的 HTTP 客户端。
//
// 文件概述：client.go 实现 Client.Chat——向 OpenAI 兼容 chat completions 端点发起非流式请求。
// 核心修复点（痛点①）：buildRequest 严格依据 provider 能力矩阵决定是否下发
// reasoning_effort / thinking 参数，不支持则完全不放入请求体，根治旧版 400。
//
// 错误处理策略（为 M2 agent loop 的重试决策提供依据）：
//   - 网络错误 / 超时：可重试；
//   - 4xx（含 400 参数错误）：配置/参数问题，不重试，直接上抛并带 body 片段供排查；
//   - 5xx：服务端瞬时错误，可重试。
// 通过 ClientError.StatusCode 区分，agent loop 据此决定是否进入下一轮。
package llm

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

// CostRecorder 由 cost.go 实现，client 在每次成功调用后回调记录用量与成本。
// 设为接口便于测试时注入 mock，且解耦 client 与 store 包（避免循环依赖）。
type CostRecorder interface {
	// Record 记录一次 LLM 调用的成本信息。
	Record(provider, model string, usage Usage) error
}

// Client 是 LLM 调用客户端。构造后可并发安全使用（http.Client 自身并发安全）。
type Client struct {
	provider string        // provider 标识（用于能力查表与成本记录）
	model    string        // 默认模型名
	baseURL  string        // API 基址（如 https://api.deepseek.com/v1）
	apiKey   string        // API 密钥
	timeout  time.Duration // 单次请求超时
	caps     Capabilities  // 构造时查表的能力，后续不变
	http     *http.Client  // 底层 HTTP 客户端
	recorder CostRecorder  // 成本记录器（可 nil，nil 时不记录）
	cache    CacheStore    // 响应缓存（可 nil，nil 时不缓存）
}

// CacheStore 是响应缓存的抽象接口。*Cache（cache.go）实现该接口。
// 设为接口便于测试注入 mock，同时解耦 client 与具体存储实现。
type CacheStore interface {
	Get(key string) (string, bool)
	Set(key, respJSON string) error
}

// New 依据 config 层的 LLMConfig 构造 Client。
// 同时查能力矩阵，固化 caps，避免每次请求重复查表。
func New(provider, model, baseURL, apiKey string, timeoutSec float64) *Client {
	return &Client{
		provider: provider,
		model:    model,
		baseURL:  baseURL,
		apiKey:   apiKey,
		timeout:  time.Duration(timeoutSec * float64(time.Second)),
		// 能力矩阵查表：未知模型返回全 false（安全兜底），见 provider.go
		caps: Lookup(provider, model),
		http: &http.Client{Timeout: time.Duration(timeoutSec * float64(time.Second))},
	}
}

// SetRecorder 注入成本记录器。通常在 main 启动时注入 store 实现后调用。
func (c *Client) SetRecorder(r CostRecorder) { c.recorder = r }

// SetCache 注入响应缓存。通常在 main 启动时注入 store 实现后调用。
func (c *Client) SetCache(cache CacheStore) { c.cache = cache }

// Capabilities 返回当前 client 的能力（主要供测试与调试查看）。
func (c *Client) Capabilities() Capabilities { return c.caps }

// Option 是 Chat 的可选参数（函数选项模式）。
type Option func(*Request)

// WithTemperature 覆盖默认温度。
func WithTemperature(t float64) Option { return func(r *Request) { r.Temperature = t } }

// WithMaxTokens 覆盖默认最大 token。
func WithMaxTokens(n int) Option { return func(r *Request) { r.MaxTokens = n } }

// WithTools 附加可用工具声明（M2 agent loop 使用）。
func WithTools(tools []ToolDefinition) Option { return func(r *Request) { r.Tools = tools } }

// WithModel 临时覆盖本次调用的模型（仍按该模型查能力矩阵决定参数下发）。
// 若覆盖后的模型能力与默认不同，会重新查表。
func WithModel(model string) Option {
	return func(r *Request) {
		r.Model = model
	}
}

// WithNoCache 标记本次调用跳过响应缓存（强制刷新）。
func WithNoCache() Option { return func(r *Request) { r.NoCache = true } }

// Chat 发起一次非流式 chat completions 请求。
//
// 流程：
//   1. buildRequest 按能力矩阵构造请求体（推理参数条件下发）；
//   2. POST 到 {baseURL}/chat/completions；
//   3. 检查 HTTP 状态码，非 2xx 返回携带状态码与 body 的 ClientError；
//   4. 解析响应；
//   5. 成功后异步记录成本（不阻塞返回，失败仅记录不影响主流程）。
func (c *Client) Chat(ctx context.Context, messages []Message, opts ...Option) (*Response, error) {
	req := c.buildRequest(messages, opts)

	// 缓存查询：仅当注入了 cache、本次未禁用缓存时尝试。
	// 带工具的请求 CacheKey 返回空串，自动跳过缓存（见 cache.go）。
	var cacheKey string
	if c.cache != nil && !req.NoCache {
		cacheKey = CacheKey(req)
		if cacheKey != "" {
			if cached, ok := c.cache.Get(cacheKey); ok {
				// 命中缓存：反序列化直接返回，跳过网络请求与成本记录（未实际调用 provider）
				var resp Response
				if err := json.Unmarshal([]byte(cached), &resp); err == nil {
					return &resp, nil
				}
				// 反序列化失败则忽略缓存，继续走正常请求
			}
		}
	}

	body, err := json.Marshal(req)
	if err != nil {
		return nil, fmt.Errorf("序列化请求失败: %w", err)
	}

	// 拼装 URL：baseURL 末尾可能带或不带 /，统一处理
	url := c.baseURL + "/chat/completions"
	httpReq, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, fmt.Errorf("构造 HTTP 请求失败: %w", err)
	}
	httpReq.Header.Set("Content-Type", "application/json")
	// Authorization Bearer 头；ollama 本地模式 key 为空时仍设置（多数实现容忍空 token）
	httpReq.Header.Set("Authorization", "Bearer "+c.apiKey)

	httpResp, err := c.http.Do(httpReq)
	if err != nil {
		// 网络层错误（含超时）：可重试
		return nil, fmt.Errorf("LLM 请求失败（网络/超时，可重试）: %w", err)
	}
	defer httpResp.Body.Close()

	respBody, err := io.ReadAll(httpResp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取响应体失败: %w", err)
	}

	// 非 2xx：构造带状态码的错误，便于上层决策重试
	if httpResp.StatusCode < 200 || httpResp.StatusCode >= 300 {
		// 截取 body 片段（最多 500 字节）放入错误信息，便于排查 400 等参数错误
		snippet := string(respBody)
		if len(snippet) > 500 {
			snippet = snippet[:500]
		}
		return nil, &ClientError{
			StatusCode: httpResp.StatusCode,
			Body:       string(respBody),
			Err: fmt.Errorf("LLM 返回非 2xx: status=%d body=%s",
				httpResp.StatusCode, snippet),
		}
	}

	var resp Response
	if err := json.Unmarshal(respBody, &resp); err != nil {
		return nil, fmt.Errorf("解析响应 JSON 失败: %w", err)
	}

	// 成功：记录成本（失败不影响主流程，仅记日志）
	if c.recorder != nil && len(resp.Choices) > 0 {
		_ = c.recorder.Record(c.provider, req.Model, resp.Usage)
	}

	// 写入缓存（失败忽略，不阻断主流程）
	if cacheKey != "" && c.cache != nil {
		if respBytes, err := json.Marshal(&resp); err == nil {
			_ = c.cache.Set(cacheKey, string(respBytes))
		}
	}

	return &resp, nil
}

// buildRequest 构造请求体——痛点①修复的核心落地点。
//
// 关键逻辑：reasoning_effort 与 thinking 仅在能力矩阵声明支持时才赋值。
// 不支持的模型这两个字段保持零值/nil，json.Marshal 配合 omitempty 直接丢弃，
// 请求体里完全不出现 → 服务端不会因"未知参数"返回 400。
func (c *Client) buildRequest(messages []Message, opts []Option) *Request {
	req := &Request{
		Model:    c.model,      // 默认模型，可被 WithModel 覆盖
		Messages: messages,
	}
	// 应用调用方选项（可能覆盖 Model）
	for _, opt := range opts {
		opt(req)
	}

	// 确定本次实际使用模型的能力：若模型被 WithModel 覆盖，需重新查表。
	caps := c.caps
	if req.Model != c.model {
		caps = Lookup(c.provider, req.Model)
	}

	// 条件下发推理参数——这是与旧版 llm_utils.py:18-25 的根本区别。
	// 旧版无条件注入；此处仅按能力注入。
	if caps.SupportsReasoningEffort && req.ReasoningEffort == "" {
		// 默认中等强度；调用方也可通过后续 WithReasoningEffort 显式指定
		req.ReasoningEffort = "medium"
	}
	if caps.SupportsThinkingParam && req.Thinking == nil {
		req.Thinking = &ThinkingConfig{Type: "enabled"}
	}
	// 不支持的模型：req.ReasoningEffort 为 ""、req.Thinking 为 nil
	// → omitempty 序列化时丢弃 → 请求体干净。

	return req
}

// ClientError 是 LLM 调用的业务错误，携带 HTTP 状态码供上层重试决策。
type ClientError struct {
	StatusCode int    // HTTP 状态码
	Body       string // 原始响应体（完整，便于排查）
	Err        error  // 格式化后的错误描述
}

// Error 实现 error 接口。
func (e *ClientError) Error() string { return e.Err.Error() }

// Unwrap 支持 errors.Is/As。
func (e *ClientError) Unwrap() error { return e.Err }

// IsRetryable 判断该错误是否值得重试。
// 4xx 为配置/参数错误，重试无意义；5xx 与网络错误可重试。
func (e *ClientError) IsRetryable() bool {
	return e.StatusCode >= 500
}
