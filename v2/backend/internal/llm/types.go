// Package llm 类型定义。
//
// 文件概述：types.go 定义 OpenAI 兼容 chat completions 接口的请求/响应 Go 类型。
// 所有推理类参数（reasoning_effort / thinking）均使用指针或 omitempty，
// 以便 client.go 依据 provider 能力矩阵（provider.go）决定是否真正下发——
// 不支持的模型这些字段为 nil/零值，序列化时被 omitempty 丢弃，绝不进入请求体。
// 这是"不再硬塞不支持的参数"在序列化层面的落地点。
package llm

// Role 是消息角色枚举。OpenAI 兼容接口标准四值。
type Role string

const (
	RoleSystem    Role = "system"    // 系统指令
	RoleUser      Role = "user"      // 用户消息
	RoleAssistant Role = "assistant" // 助手回复
	RoleTool      Role = "tool"      // 工具调用结果回传
)

// Message 表示一条对话消息。请求与响应共用此类型。
//
// 字段说明（按 OpenAI chat completions 规范）：
//   - Role / Content：必有字段；
//   - ReasoningContent：仅推理模型（DeepSeek-reasoner 等）在响应中返回，请求侧留空；
//   - ToolCalls：助手发起函数调用时携带（M2 agent loop 使用）；
//   - ToolCallID：role=tool 时必填，指明回传的是哪次调用结果。
type Message struct {
	Role             Role     `json:"role"`                       // 消息角色
	Content          string   `json:"content"`                    // 文本内容
	ReasoningContent string   `json:"reasoning_content,omitempty"` // 推理过程（仅响应，仅推理模型）
	ToolCalls        []ToolCall `json:"tool_calls,omitempty"`      // 助手发起的工具调用
	ToolCallID       string   `json:"tool_call_id,omitempty"`     // tool 角色消息的回传 id
}

// ToolCall 描述助手发起的一次函数调用。
type ToolCall struct {
	ID       string       `json:"id"`                 // 调用 id（回传时匹配用）
	Type     string       `json:"type"`               // 固定 "function"
	Function FunctionCall `json:"function"`           // 函数名与参数
}

// FunctionCall 是 ToolCall 的函数描述。
type FunctionCall struct {
	Name      string `json:"name"`               // 函数名
	Arguments string `json:"arguments"`           // JSON 字符串形式的参数（保持原样，不预解析）
}

// ThinkingConfig 对应部分 provider（通义/Anthropic 代理等）的 thinking 参数。
// 用指针类型，nil 时 omitempty 不序列化——即"不下发该参数"。
type ThinkingConfig struct {
	Type string `json:"type"` // "enabled" | "disabled"
}

// Request 是 chat completions 请求体。
//
// 关键：ReasoningEffort（string+omitempty）与 Thinking（指针+omitempty）。
// client.go 在构造请求时，仅当 provider 能力矩阵声明支持时才赋值；
// 否则保持零值/nil，序列化时被 omitempty 丢弃，请求体里完全不出现这两个字段。
// 这从协议层杜绝了旧版"对 DeepSeek-chat 硬塞 reasoning_effort → 400"的 bug。
type Request struct {
	Model            string           `json:"model"`                       // 模型名
	Messages         []Message        `json:"messages"`                    // 对话历史
	Temperature      float64          `json:"temperature,omitempty"`       // 采样温度（0 表示用默认，omitempty 丢弃）
	MaxTokens        int              `json:"max_tokens,omitempty"`        // 单次最大 token
	Stream           bool             `json:"stream,omitempty"`            // 是否流式（M2 使用）
	Tools            []ToolDefinition `json:"tools,omitempty"`             // 可用工具声明（M2 agent loop）
	ReasoningEffort  string           `json:"reasoning_effort,omitempty"`  // 仅 SupportsReasoningEffort 时下发
	Thinking         *ThinkingConfig  `json:"thinking,omitempty"`          // 仅 SupportsThinkingParam 时下发

	// NoCache 控制本次调用是否跳过响应缓存。不参与 JSON 序列化。
	// 用于 agent loop 中需要强制刷新的场景，或带温度采样的探索性调用。
	NoCache bool `json:"-"`
}

// ToolDefinition 声明一个可被模型调用的工具（函数）。
type ToolDefinition struct {
	Type     string             `json:"type"`     // 固定 "function"
	Function FunctionDefinition `json:"function"` // 函数 schema
}

// FunctionDefinition 是工具的 JSON Schema 描述。
type FunctionDefinition struct {
	Name        string         `json:"name"`                 // 函数名
	Description string         `json:"description,omitempty"` // 用途说明（帮助模型决策）
	Parameters  map[string]any `json:"parameters"`            // JSON Schema 参数定义
}

// Response 是 chat completions 非流式响应。
type Response struct {
	ID      string   `json:"id"`       // 响应 id
	Model   string   `json:"model"`    // 实际使用的模型
	Choices []Choice `json:"choices"`  // 候选项（非流式通常 length=1）
	Usage   Usage    `json:"usage"`    // token 用量（成本计算依据）
}

// Choice 是一个候选回复。
type Choice struct {
	Index        int     `json:"index"`         // 候选序号
	Message      Message `json:"message"`       // 回复内容
	FinishReason string  `json:"finish_reason"` // 结束原因：stop/length/tool_calls
}

// Usage 是 token 用量统计。成本追踪（cost.go）据此计算。
type Usage struct {
	PromptTokens     int `json:"prompt_tokens"`     // 输入 token
	CompletionTokens int `json:"completion_tokens"` // 输出 token
	TotalTokens      int `json:"total_tokens"`      // 合计
}
