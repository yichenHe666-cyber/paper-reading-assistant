// agent 包的核心：agent loop。
//
// 文件概述：loop.go 实现 Agent.Run——真正的多轮工具调用循环，修复 spec §4.1 根因 #6
// "无 agent loop"（旧版 _send_with_tools 仅一次工具调用 + 一次最终回答，无法多步推理）。
//
// 循环结构（spec §4.1 修复方案"真正 agent loop"）：
//   for turn < maxTurns {
//       callWithTools(messages)              // 调 LLM，带工具声明
//       if noToolCalls { emit tokens; break } // 模型给出最终回答，结束
//       for each toolCall {                  // 模型要调工具
//           execute; emit tool_result; append tool message
//       }
//       // 带着工具结果进入下一轮，让模型基于结果继续推理
//   }
//
// 每轮保护：
//   - perTurnTimeout：单轮 LLM 调用超时（context.WithTimeout），超时 emit error；
//   - tokenBudget：累计 token 超预算时 emit error 终止，防失控烧钱；
//   - 重试：可重试错误（5xx/网络）单轮内重试 1 次，4xx 直接失败（参数错重试无意义）。
//
// 流式契约：Run 返回 <-chan StreamEvent，所有路径（正常/工具/错误）统一 channel，
// 杜绝旧版"dict 当生成器"。channel 在 done/error 后关闭。
package agent

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"nuclear-ox-v2/backend/internal/llm"
)

// DefaultMaxTurns 是 agent loop 默认最大轮数（spec §4.1：默认 8）。
// 8 轮足以覆盖"列主题→搜论文→取详情→综合回答"这类多步任务，又不会无限烧 token。
const DefaultMaxTurns = 8

// DefaultPerTurnTimeout 是单轮 LLM 调用默认超时。
// 长 enough 让推理模型（DeepSeek-reasoner）有时间思考，又能在卡死时及时放弃。
const DefaultPerTurnTimeout = 90 * time.Second

// DefaultTokenBudget 是整个 agent loop 的默认 token 预算（0 表示不限）。
// 设非零上限防失控；按 deepseek-chat 价格约 $0.27/1M input，4 万 token 约 $0.01，可控。
const DefaultTokenBudget = 40000

// Agent 是 agent loop 执行器。构造后可重复调用 Run。
//
// 不持有技能/数据库依赖——技能注入由调用方（ChatService）组装进 system prompt，
// 用量统计由调用方在 Run 结束后处理。Agent 只负责"循环调 LLM + 执行工具"。
type Agent struct {
	llm             *llm.Client      // LLM 客户端
	tools           *ToolRegistry    // 工具注册表（可为空表示无工具）
	maxTurns        int              // 最大轮数
	perTurnTimeout  time.Duration    // 单轮超时
	tokenBudget     int              // 总 token 预算（0 不限）
	retryOn5xx      bool             // 5xx 是否单轮内重试一次
	baseSystemPrompt string          // 基础 system prompt（技能块由调用方拼接后传入 messages）
}

// Option 是 NewAgent 的可选参数。
type Option func(*Agent)

// WithMaxTurns 覆盖默认最大轮数。
func WithMaxTurns(n int) Option { return func(a *Agent) { if n > 0 { a.maxTurns = n } } }

// WithPerTurnTimeout 覆盖单轮超时。
func WithPerTurnTimeout(d time.Duration) Option { return func(a *Agent) { a.perTurnTimeout = d } }

// WithTokenBudget 覆盖总 token 预算。
func WithTokenBudget(n int) Option { return func(a *Agent) { a.tokenBudget = n } }

// WithBaseSystemPrompt 设置基础 system prompt。
func WithBaseSystemPrompt(s string) Option { return func(a *Agent) { a.baseSystemPrompt = s } }

// WithRetryOn5xx 启用 5xx 单轮内重试一次（默认启用）。
func WithRetryOn5xx(enable bool) Option { return func(a *Agent) { a.retryOn5xx = enable } }

// NewAgent 构造 Agent。tools 可为 nil（纯对话无工具场景）。
func NewAgent(llmClient *llm.Client, tools *ToolRegistry, opts ...Option) *Agent {
	a := &Agent{
		llm:             llmClient,
		tools:           tools,
		maxTurns:        DefaultMaxTurns,
		perTurnTimeout:  DefaultPerTurnTimeout,
		tokenBudget:     DefaultTokenBudget,
		retryOn5xx:      true,
		baseSystemPrompt: defaultSystemPrompt(),
	}
	for _, opt := range opts {
		opt(a)
	}
	return a
}

// defaultSystemPrompt 返回默认基础 system prompt。
// 强调工具使用规范与"无把握时先查后答"，降低幻觉。
func defaultSystemPrompt() string {
	return `你是"核动力科研牛马"的科研助手，帮助用户管理与分析本地论文库。

行为准则：
1. 涉及论文/主题数据时，优先调用工具查询本地库，不要凭空编造论文信息。
2. 多步任务可连续调用工具：先 list_topics 了解分类，再 search_papers 检索，必要时 get_paper 取详情。
3. 工具结果若为空数组，如实告知用户"未找到"，不要臆测。
4. 回答用中文，专业术语保留英文原文。`
}

// Run 执行 agent loop，返回 StreamEvent channel。
//
// 调用方负责组装 messages（含 system prompt 与技能块）；Run 不修改入参切片（内部 copy）。
// channel 关闭时机：emit done/error 后。调用方应 range channel 直到关闭。
//
// 取消：ctx.Done() 时尽快结束（当前轮 LLM 调用会因 ctx 取消而返回 error）。
func (a *Agent) Run(ctx context.Context, messages []llm.Message) <-chan StreamEvent {
	ch := make(chan StreamEvent, 32) // 缓冲 32：避免单事件阻塞循环；溢出时 Send 阻塞可接受

	go func() {
		defer close(ch)
		// 内部工作副本，避免修改调用方切片
		history := make([]llm.Message, len(messages))
		copy(history, messages)

		// sendCtx 向 ch 发送事件，消费方停止读取（SSE 客户端断开）时通过 ctx 取消，
		// 避免 Run goroutine 永久阻塞在发送上导致 goroutine 泄漏。
		// 返回 false 表示 ctx 已取消，调用方应 return。
		sendCtx := func(ev StreamEvent) bool {
			select {
			case ch <- ev:
				return true
			case <-ctx.Done():
				return false
			}
		}

		totalTokens := 0
		turn := 0
		for turn < a.maxTurns {
			// 检查上层取消
			if err := ctx.Err(); err != nil {
				sendCtx(newErrorEvent(turn, "agent 被取消: "+err.Error()))
				return
			}
			// 检查 token 预算
			if a.tokenBudget > 0 && totalTokens >= a.tokenBudget {
				sendCtx(newErrorEvent(turn, fmt.Sprintf("token 预算耗尽（已用 %d/%d）", totalTokens, a.tokenBudget)))
				return
			}

			turn++
			resp, err := a.callOnce(ctx, history)
			if err != nil {
				// 错误事件携带当前轮次，便于排查"第几轮崩的"
				sendCtx(newErrorEvent(turn, err.Error()))
				return
			}

			// 累计 token 用量并 emit
			totalTokens += resp.Usage.TotalTokens
			if !sendCtx(newUsageEvent(Usage{
				PromptTokens: resp.Usage.PromptTokens,
				CompletionTokens: resp.Usage.CompletionTokens,
				TotalTokens: resp.Usage.TotalTokens,
			})) {
				return
			}

			// 防御空 choices：LLM 返回 200 但 choices 为空（内容过滤/异常响应）时
			// 不能越界 panic——该 goroutine 无 recover，panic 会崩溃整个进程。
			if len(resp.Choices) == 0 {
				sendCtx(newErrorEvent(turn, "LLM 返回空 choices（可能触发内容过滤）"))
				return
			}
			choice := resp.Choices[0]
			assistantMsg := choice.Message
			// 追加 assistant 消息到历史（含 tool_calls，模型下一轮会看到自己的调用记录）
			history = append(history, assistantMsg)

			// 无工具调用 → 最终回答：分块 emit token + done
			if len(assistantMsg.ToolCalls) == 0 {
				a.emitTokensCtx(ctx, ch, sendCtx, assistantMsg.Content)
				sendCtx(newDoneEvent(turn))
				return
			}

			// 有工具调用：逐个执行，emit tool_call/tool_result，append tool 消息
			for _, tc := range assistantMsg.ToolCalls {
				if !sendCtx(newToolCallEvent(tc.ID, tc.Function.Name, tc.Function.Arguments)) {
					return
				}

				result, execErr := a.execTool(ctx, tc.Function.Name, tc.Function.Arguments)
				// 执行失败也回传给模型（JSON 错误体），让模型自行决定重试或换方案
				if execErr != nil {
					result = fmt.Sprintf(`{"error":"%s"}`, escapeJSONString(execErr.Error()))
				}
				if !sendCtx(newToolResultEvent(tc.ID, tc.Function.Name, result)) {
					return
				}

				// append tool 角色消息：role=tool，content=结果，tool_call_id 匹配
				history = append(history, llm.Message{
					Role:       llm.RoleTool,
					Content:    result,
					ToolCallID: tc.ID,
				})
			}
			// 进入下一轮：模型基于工具结果继续推理
		}

		// 达到 maxTurns 仍未给出最终回答
		sendCtx(newErrorEvent(turn, fmt.Sprintf("达到最大轮数 %d 仍未完成", a.maxTurns)))
	}()

	return ch
}

// callOnce 执行单轮 LLM 调用（带工具），含 5xx 重试逻辑。
// 超时由 perTurnTimeout 通过 context 控制。
func (a *Agent) callOnce(ctx context.Context, messages []llm.Message) (*llm.Response, error) {
	// 单轮超时 context：嵌套于上层 ctx，二者任一到期都中止
	turnCtx, cancel := context.WithTimeout(ctx, a.perTurnTimeout)
	defer cancel()

	opts := []llm.Option{}
	if a.tools != nil && len(a.tools.Definitions()) > 0 {
		opts = append(opts, llm.WithTools(a.tools.Definitions()))
	}

	resp, err := a.llm.Chat(turnCtx, messages, opts...)
	if err == nil {
		return resp, nil
	}

	// 错误处理：区分可重试（5xx/网络）与不可重试（4xx 参数错）
	if !a.retryOn5xx {
		return nil, fmt.Errorf("LLM 调用失败: %w", err)
	}
	var ce *llm.ClientError
	if !errors.As(err, &ce) || !ce.IsRetryable() {
		// 4xx 或非 ClientError：不可重试，直接上抛
		// 注意：4xx 通常是参数/配置问题（如 reasoning_effort 不被支持），
		// M1 能力矩阵已根治主要原因；此处仍可能因 provider 特异 4xx 失败。
		return nil, fmt.Errorf("LLM 调用失败（不可重试）: %w", err)
	}

	// 可重试：短暂退避后重试一次
	select {
	case <-time.After(2 * time.Second):
	case <-turnCtx.Done():
		return nil, fmt.Errorf("LLM 调用超时: %w", turnCtx.Err())
	}
	resp2, err2 := a.llm.Chat(turnCtx, messages, opts...)
	if err2 != nil {
		return nil, fmt.Errorf("LLM 调用重试后仍失败: %w (首次错误: %v)", err2, err)
	}
	return resp2, nil
}

// execTool 执行单个工具调用。无工具注册表时返回错误。
func (a *Agent) execTool(ctx context.Context, name, argsJSON string) (string, error) {
	if a.tools == nil {
		return "", fmt.Errorf("未注册任何工具")
	}
	return a.tools.Execute(ctx, name, argsJSON)
}

// emitTokens 将最终回答内容分块 emit 为多个 token 事件，模拟流式体验。
// 按换行符分块；无换行则整段一次 emit。
func (a *Agent) emitTokens(ch chan<- StreamEvent, content string) {
	a.emitTokensCtx(context.Background(), ch, func(ev StreamEvent) bool {
		ch <- ev
		return true
	}, content)
}

// emitTokensCtx 是 ctx 感知版本：消费方停止读取时通过 sendCtx 返回 false 提前终止，
// 避免 Run goroutine 阻塞在 token 发送上导致泄漏。
func (a *Agent) emitTokensCtx(ctx context.Context, ch chan<- StreamEvent, send func(StreamEvent) bool, content string) {
	if content == "" {
		return
	}
	// 按行分块，保留换行符，让前端按行渲染
	parts := splitLinesKeepNL(content)
	for _, p := range parts {
		if p == "" {
			continue
		}
		if !send(newTokenEvent(p)) {
			return
		}
	}
}

// splitLinesKeepNL 按换行切分但保留换行符在每段末尾。
func splitLinesKeepNL(s string) []string {
	if !strings.Contains(s, "\n") {
		return []string{s}
	}
	lines := strings.SplitAfter(s, "\n")
	return lines
}

// escapeJSONString 转义字符串以便安全嵌入 JSON 字符串值。
// 用于构造 tool_result 的错误体，避免引号/反斜杠破坏 JSON。
func escapeJSONString(s string) string {
	s = strings.ReplaceAll(s, `\`, `\\`)
	s = strings.ReplaceAll(s, `"`, `\"`)
	s = strings.ReplaceAll(s, "\n", `\n`)
	return s
}
