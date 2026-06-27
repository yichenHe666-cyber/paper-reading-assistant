// Package agent 实现 agent loop、技能系统、工具调用与自进化能力。
//
// 本包是"多 agent 模块从未测试成功"痛点（spec §4.1）的运行时修复层。
// M1 已在协议层（llm 包的能力矩阵）根治"硬塞 reasoning_effort → 400"；
// 本包在运行时层补齐：真 agent loop、统一流式抽象、技能 upsert、自进化雏形。
//
// 子文件分工：
//   - stream.go : StreamEvent 统一事件类型与 channel 抽象（本文件）
//   - tools.go  : Tool 接口、工具注册表、内置工具（list_topics/search_papers/get_paper）
//   - skill.go  : 技能注册表 + 渐进式披露（Level 0 摘要注入 system prompt）
//   - loop.go   : agent loop（maxTurns + 每轮超时 + token 预算）
//   - chat.go   : ChatService，会话/消息管理 + 流式异常落库
//   - evolve.go : 自进化雏形（任务后提炼技能 + 复用 + 用量统计）
package agent

// StreamEventType 枚举 agent loop 对外吐出的事件类型。
//
// 设计动机（spec §4.1 修复方案"流式统一抽象"）：
// 旧 Python 版 send_message 在 auto 模式返回 dict、stream 模式返回生成器，
// 调用方 `for chunk in dict` 把 dict 的 key 当 token 吐给前端，是 agent 崩溃的次要根因。
// 本包所有流式路径统一返回 <-chan StreamEvent，事件类型显式枚举，杜绝类型歧义。
type StreamEventType string

const (
	// EventToken 表示一段模型生成的文本（assistant 内容）。
	// 一次 agent 回合可能产生多个 EventToken（按句/行分块吐出，模拟流式体验）。
	EventToken StreamEventType = "token"

	// EventToolCall 表示模型决定调用某工具。携带工具名与参数。
	// 前端据此展示"正在调用工具 X"。
	EventToolCall StreamEventType = "tool_call"

	// EventToolResult 表示工具执行完成。携带工具名与结果（JSON 字符串）。
	EventToolResult StreamEventType = "tool_result"

	// EventUsage 表示本轮 LLM 调用的 token 用量。每轮至少一个。
	EventUsage StreamEventType = "usage"

	// EventError 表示流程中发生的错误。channel 收到 error 后即结束，不再有后续事件。
	// 流式异常落库（spec §4.1）：即便中途失败，已积累的 assistant 内容也会落库。
	EventError StreamEventType = "error"

	// EventDone 表示 agent loop 正常结束。channel 关闭前的最后一个事件。
	EventDone StreamEventType = "done"
)

// StreamEvent 是 agent loop 通过 channel 吐出的统一事件。
//
// 字段使用值类型 + omitempty 序列化，便于直接 JSON 编码后通过 SSE 推送给前端。
// Type 字段决定其余字段哪些有效：
//   - token       : Content 有效
//   - tool_call   : ToolName + ToolArgs 有效
//   - tool_result : ToolName + ToolResult 有效
//   - usage       : Usage 字段有效
//   - error       : Content 为可读错误信息
//   - done        : Turn 表示实际执行了多少轮（供调试与配额分析）
type StreamEvent struct {
	Type       StreamEventType `json:"type"`                  // 事件类型
	Content    string          `json:"content,omitempty"`     // token 文本 / error 描述
	ToolName   string          `json:"tool_name,omitempty"`   // 工具名（tool_call/tool_result）
	ToolCallID string          `json:"tool_call_id,omitempty"`// 工具调用 id（匹配模型回传）
	ToolArgs   string          `json:"tool_args,omitempty"`   // 工具入参 JSON（tool_call）
	ToolResult string          `json:"tool_result,omitempty"` // 工具结果 JSON（tool_result）
	Usage      *Usage          `json:"usage,omitempty"`       // token 用量（usage 事件）
	Turn       int             `json:"turn,omitempty"`        // 当前轮次（done/error 携带）
}

// Usage 是 token 用量统计。与 llm.Usage 对应但独立定义，避免 agent 包反向依赖 llm 包的内部类型
// （agent 已正向依赖 llm.Client，此处仅做值拷贝隔离）。
type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`     // 输入 token
	CompletionTokens int `json:"completion_tokens"` // 输出 token
	TotalTokens      int `json:"total_tokens"`      // 合计
}

// --- 事件构造辅助函数 ---
// 集中构造避免散落各处手写 StreamEvent{Type:...}，降低拼写错误风险。

// newTokenEvent 构造一个 token 事件。
func newTokenEvent(content string) StreamEvent {
	return StreamEvent{Type: EventToken, Content: content}
}

// newToolCallEvent 构造一个 tool_call 事件。
func newToolCallEvent(callID, name, args string) StreamEvent {
	return StreamEvent{Type: EventToolCall, ToolCallID: callID, ToolName: name, ToolArgs: args}
}

// newToolResultEvent 构造一个 tool_result 事件。
func newToolResultEvent(callID, name, result string) StreamEvent {
	return StreamEvent{Type: EventToolResult, ToolCallID: callID, ToolName: name, ToolResult: result}
}

// newUsageEvent 构造一个 usage 事件。
func newUsageEvent(u Usage) StreamEvent {
	return StreamEvent{Type: EventUsage, Usage: &u}
}

// newErrorEvent 构造一个 error 事件。turn 标记出错时已执行到第几轮。
func newErrorEvent(turn int, msg string) StreamEvent {
	return StreamEvent{Type: EventError, Turn: turn, Content: msg}
}

// newDoneEvent 构造一个 done 事件。turn 标记总共执行了多少轮。
func newDoneEvent(turn int) StreamEvent {
	return StreamEvent{Type: EventDone, Turn: turn}
}
