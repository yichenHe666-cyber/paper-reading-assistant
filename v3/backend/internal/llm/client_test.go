// Package llm 的契约测试。
//
// 文件概述：client_test.go 用 httptest mock server 验证 LLM 适配层的关键契约，
// 重点覆盖痛点①（agent 失败首要根因）的修复：
//   - DeepSeek-chat 请求体绝不含 reasoning_effort/thinking（旧版硬塞 → 400 的根因）；
//   - provider 能力矩阵正确区分各模型能力；
//   - 正常响应解析、成本记录、缓存命中、4xx/5xx 错误分类。
//
// 这些测试是"agent loop 能跑通"的最底层保证：只要请求体构造正确 + 响应可解析，
// M2 的 agent loop 就有可靠的地基。
package llm

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// TestLookupCapabilities 验证能力矩阵对各 provider/model 的判定。
// 这是痛点①修复的核心：能力判定错误会直接导致 400。
func TestLookupCapabilities(t *testing.T) {
	cases := []struct {
		name           string
		provider       string
		model          string
		wantReasoning  bool // SupportsReasoningEffort
		wantThinking   bool // SupportsThinkingParam
		wantRRC        bool // ReturnsReasoningContent
	}{
		// DeepSeek-chat：全 false（旧版误注入 reasoning_effort 就是 bug 根源）
		{"deepseek-chat", "deepseek", "deepseek-chat", false, false, false},
		{"deepseek-v4-flash", "deepseek", "deepseek-v4-flash", false, false, false},
		// DeepSeek-reasoner：返回 reasoning_content，但不接受 reasoning_effort/thinking
		{"deepseek-reasoner", "deepseek", "deepseek-reasoner", false, false, true},
		{"deepseek-v4-pro", "deepseek", "deepseek-v4-pro", false, false, true},
		// OpenAI o1：支持 reasoning_effort
		{"openai-o1", "openai", "o1", true, false, false},
		// 未知模型：全 false（安全兜底）
		{"unknown", "somevendor", "weird-model", false, false, false},
		// 大小写不敏感
		{"case-insensitive", "DeepSeek", "DeepSeek-Chat", false, false, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			caps := Lookup(tc.provider, tc.model)
			if caps.SupportsReasoningEffort != tc.wantReasoning {
				t.Errorf("SupportsReasoningEffort: got %v want %v", caps.SupportsReasoningEffort, tc.wantReasoning)
			}
			if caps.SupportsThinkingParam != tc.wantThinking {
				t.Errorf("SupportsThinkingParam: got %v want %v", caps.SupportsThinkingParam, tc.wantThinking)
			}
			if caps.ReturnsReasoningContent != tc.wantRRC {
				t.Errorf("ReturnsReasoningContent: got %v want %v", caps.ReturnsReasoningContent, tc.wantRRC)
			}
		})
	}
}

// TestBuildRequestNoReasoningForDeepSeekChat 是痛点①修复的直接验证：
// DeepSeek-chat 的请求体序列化后绝不能出现 "reasoning_effort" 或 "thinking" 字段。
// 旧版 app/services/llm_utils.py:18-25 正是因为硬塞这两个字段导致 400。
func TestBuildRequestNoReasoningForDeepSeekChat(t *testing.T) {
	c := New("deepseek", "deepseek-chat", "http://x", "k", 10)
	req := c.buildRequest([]Message{{Role: RoleUser, Content: "hi"}}, nil)

	body, err := json.Marshal(req)
	if err != nil {
		t.Fatalf("序列化请求失败: %v", err)
	}
	s := string(body)
	if strings.Contains(s, "reasoning_effort") {
		t.Errorf("DeepSeek-chat 请求体不应含 reasoning_effort，实际: %s", s)
	}
	if strings.Contains(s, "thinking") {
		t.Errorf("DeepSeek-chat 请求体不应含 thinking，实际: %s", s)
	}
}

// TestBuildRequestReasoningForOpenAI 验证 OpenAI o1 请求体包含 reasoning_effort。
func TestBuildRequestReasoningForOpenAI(t *testing.T) {
	c := New("openai", "o1", "http://x", "k", 10)
	req := c.buildRequest([]Message{{Role: RoleUser, Content: "hi"}}, nil)

	body, _ := json.Marshal(req)
	s := string(body)
	if !strings.Contains(s, "reasoning_effort") {
		t.Errorf("OpenAI o1 请求体应含 reasoning_effort，实际: %s", s)
	}
}

// fakeRecorder 是 CostRecorder 的测试 mock，记录每次调用。
type fakeRecorder struct {
	calls []recordedCall
}
type recordedCall struct {
	provider, model string
	usage           Usage
}

func (f *fakeRecorder) Record(p, m string, u Usage) error {
	f.calls = append(f.calls, recordedCall{p, m, u})
	return nil
}

// mockResp 构造一个合法的 OpenAI 风格响应体。
func mockResp(content string, usage Usage) string {
	return `{
		"id": "resp-1",
		"model": "deepseek-chat",
		"choices": [{"index":0,"message":{"role":"assistant","content":` + jsonString(content) + `},"finish_reason":"stop"}],
		"usage": {"prompt_tokens":` + itoa(usage.PromptTokens) + `,"completion_tokens":` + itoa(usage.CompletionTokens) + `,"total_tokens":` + itoa(usage.TotalTokens) + `}
	}`
}

// TestChatNormal 验证正常调用：响应解析 + 成本记录被触发。
func TestChatNormal(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, mockResp("hello", Usage{PromptTokens: 5, CompletionTokens: 3, TotalTokens: 8}))
	}))
	defer srv.Close()

	rec := &fakeRecorder{}
	c := New("deepseek", "deepseek-chat", srv.URL, "k", 10)
	c.SetRecorder(rec)

	resp, err := c.Chat(context.Background(), []Message{{Role: RoleUser, Content: "hi"}})
	if err != nil {
		t.Fatalf("Chat 失败: %v", err)
	}
	if len(resp.Choices) != 1 || resp.Choices[0].Message.Content != "hello" {
		t.Fatalf("响应解析错误: %+v", resp)
	}
	if len(rec.calls) != 1 {
		t.Fatalf("成本记录应被调用 1 次，实际 %d", len(rec.calls))
	}
	if rec.calls[0].usage.TotalTokens != 8 {
		t.Errorf("用量记录错误: %+v", rec.calls[0].usage)
	}
}

// TestChat400NotRetryable 验证 4xx 返回 ClientError 且不可重试。
// 这正是旧版 agent 失败的场景（DeepSeek 返回 400）；新版应清晰上抛而非吞掉。
func TestChat400NotRetryable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadRequest)
		io.WriteString(w, `{"error":{"message":"reasoning_effort not supported"}}`)
	}))
	defer srv.Close()

	c := New("deepseek", "deepseek-chat", srv.URL, "k", 10)
	_, err := c.Chat(context.Background(), []Message{{Role: RoleUser, Content: "hi"}})
	if err == nil {
		t.Fatal("应返回错误，实际 nil")
	}
	var ce *ClientError
	if !errors.As(err, &ce) {
		t.Fatalf("应返回 *ClientError，实际 %T: %v", err, err)
	}
	if ce.StatusCode != 400 {
		t.Errorf("StatusCode: got %d want 400", ce.StatusCode)
	}
	if ce.IsRetryable() {
		t.Error("400 不应可重试")
	}
}

// TestChat500Retryable 验证 5xx 可重试。
func TestChat500Retryable(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusBadGateway)
		io.WriteString(w, `upstream error`)
	}))
	defer srv.Close()

	c := New("deepseek", "deepseek-chat", srv.URL, "k", 10)
	_, err := c.Chat(context.Background(), []Message{{Role: RoleUser, Content: "hi"}})
	var ce *ClientError
	if !errors.As(err, &ce) {
		t.Fatalf("应返回 *ClientError，实际 %T", err)
	}
	if ce.StatusCode != 502 {
		t.Errorf("StatusCode: got %d want 502", ce.StatusCode)
	}
	if !ce.IsRetryable() {
		t.Error("502 应可重试")
	}
}

// fakeCache 是 CacheStore 的测试 mock。
type fakeCache struct {
	store map[string]string
	gets  int
	sets  int
}

func newFakeCache() *fakeCache { return &fakeCache{store: map[string]string{}} }
func (f *fakeCache) Get(key string) (string, bool) {
	f.gets++
	v, ok := f.store[key]
	return v, ok
}
func (f *fakeCache) Set(key, val string) error {
	f.sets++
	f.store[key] = val
	return nil
}

// TestChatCacheHit 验证缓存命中时跳过网络请求（mock server 不应被第二次调用）。
func TestChatCacheHit(t *testing.T) {
	hits := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, mockResp("cached-answer", Usage{PromptTokens: 2, CompletionTokens: 2, TotalTokens: 4}))
	}))
	defer srv.Close()

	cache := newFakeCache()
	rec := &fakeRecorder{}
	c := New("deepseek", "deepseek-chat", srv.URL, "k", 10)
	c.SetCache(cache)
	c.SetRecorder(rec)

	msgs := []Message{{Role: RoleUser, Content: "same question"}}
	// 第一次：未命中，走网络，写缓存
	resp1, err := c.Chat(context.Background(), msgs)
	if err != nil {
		t.Fatalf("首次 Chat 失败: %v", err)
	}
	if resp1.Choices[0].Message.Content != "cached-answer" {
		t.Fatalf("首次响应错误: %+v", resp1)
	}
	if hits != 1 {
		t.Fatalf("首次应命中 server 1 次，实际 %d", hits)
	}
	if cache.sets != 1 {
		t.Fatalf("首次应写缓存 1 次，实际 %d", cache.sets)
	}

	// 第二次：相同请求，应命中缓存，不再访问 server
	resp2, err := c.Chat(context.Background(), msgs)
	if err != nil {
		t.Fatalf("二次 Chat 失败: %v", err)
	}
	if resp2.Choices[0].Message.Content != "cached-answer" {
		t.Fatalf("缓存响应错误: %+v", resp2)
	}
	if hits != 1 {
		t.Errorf("二次应命中缓存不再访问 server，但 server 命中 %d 次", hits)
	}
	// 缓存命中不应记录成本（未实际调用 provider）
	if len(rec.calls) != 1 {
		t.Errorf("成本记录应为 1 次（仅首次），实际 %d", len(rec.calls))
	}
}

// TestChatWithNoCacheOption 验证 WithNoCache 跳过缓存读写。
func TestChatWithNoCacheOption(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		io.WriteString(w, mockResp("fresh", Usage{}))
	}))
	defer srv.Close()

	cache := newFakeCache()
	c := New("deepseek", "deepseek-chat", srv.URL, "k", 10)
	c.SetCache(cache)

	_, err := c.Chat(context.Background(),
		[]Message{{Role: RoleUser, Content: "q"}}, WithNoCache())
	if err != nil {
		t.Fatalf("Chat 失败: %v", err)
	}
	if cache.gets != 0 || cache.sets != 0 {
		t.Errorf("WithNoCache 应跳过缓存，gets=%d sets=%d", cache.gets, cache.sets)
	}
}

// --- 测试辅助函数 ---

// jsonString 将字符串转为 JSON 字符串字面量（含引号）。
func jsonString(s string) string {
	b, _ := json.Marshal(s)
	return string(b)
}

// itoa 是测试用的整数转字符串（避免 import strconv 占行）。
func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var b [20]byte
	i := len(b)
	for n > 0 {
		i--
		b[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		b[i] = '-'
	}
	return string(b[i:])
}
