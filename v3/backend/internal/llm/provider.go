// Package llm 提供 LLM 调用适配层。
//
// 本包是"多 agent 模块从未测试成功"痛点（spec §4.1）的核心修复层。
//
// 根因回顾（旧 Python 版 app/services/llm_utils.py:18-25）：
//   _build_reasoning_kwargs 对所有模型无条件注入：
//     reasoning_effort="max" + extra_body.thinking.type="enabled"
//   而 DeepSeek-chat / 多数 OpenAI 兼容模型并不接受这两个参数，
//   导致每次 agent 调用都返回 HTTP 400，agent loop 永远跑不通。
//
// 修复方案：引入"provider 能力矩阵"——按 (provider, model) 显式声明该模型支持哪些
// 推理类参数，请求构造时只下发被声明支持的参数，从根本上杜绝"对不支持的模型硬塞参数"。
//
// 本包子文件分工：
//   - provider.go : 能力矩阵 Capabilities + Lookup（本文件）
//   - types.go    : OpenAI 兼容 chat completions 的请求/响应类型
//   - client.go   : HTTP 客户端，非流式 Chat（M2 扩展流式）
//   - cost.go     : 成本估算 + 持久化到 llm_calls 表
//   - cache.go    : 响应缓存（llm_cache 表，替代 Redis）
package llm

// Capabilities 描述某 (provider, model) 组合支持的推理类能力。
//
// 设计原则（保守优先）：
// 所有字段默认 false。只有显式确认某 provider/model 支持某参数时才置 true。
// 这样未知模型/新增模型默认不会下发任何可能引发 400 的参数，保证 agent 不会因
// "参数不被接受"而整体失败——这是旧版的核心 bug。
type Capabilities struct {
	// SupportsReasoningEffort 为 true 时，才在请求体顶层放入 "reasoning_effort" 字段。
	// 典型支持者：OpenAI o1/o3 系列（通过 OpenAI 官方 API）。
	// DeepSeek（含 v4 flash/pro）不支持，必须为 false。
	SupportsReasoningEffort bool

	// SupportsThinkingParam 为 true 时，才在请求体放入 "thinking" 对象。
	// 典型支持者：部分 Anthropic 兼容代理 / 通义千问 reasoning 模型。
	// DeepSeek / Ollama / 通用 OpenAI 兼容接口不支持，必须为 false。
	SupportsThinkingParam bool

	// ReturnsReasoningContent 为 true 时，解析响应中 choices[].message.reasoning_content
	// 字段（DeepSeek-reasoner / QwQ 等推理模型会返回该字段，需单独存储与展示）。
	// 注意：返回 reasoning_content ≠ 接受 reasoning_effort 参数，二者独立。
	ReturnsReasoningContent bool
}

// 能力矩阵表。key 为 "provider/model" 全小写。
//
// 维护约定：
//   - 新增 provider/model 时，若不确定其能力，一律按默认（全 false）处理，
//     即"不下发任何推理参数，不解析 reasoning_content"——安全兜底。
//   - 仅在官方文档明确支持时才置 true，并在注释中标注依据来源。
var capabilityMatrix = map[string]Capabilities{
	// DeepSeek-chat（含 v4 flash 对话模型）：
	// 不支持 reasoning_effort / thinking 参数；不返回 reasoning_content。
	"deepseek/deepseek-chat":     {},
	"deepseek/deepseek-v4-flash": {},

	// DeepSeek-reasoner（含 v4 pro 推理模型）：
	// 官方说明：reasoner 自动进行推理，不接受 reasoning_effort/thinking 参数；
	// 但响应中会返回 reasoning_content 字段，需单独提取存储。
	// 依据：DeepSeek API 文档 "Reasoner Model" 章节。
	"deepseek/deepseek-reasoner": {ReturnsReasoningContent: true},
	"deepseek/deepseek-v4-pro":   {ReturnsReasoningContent: true},

	// OpenAI o1/o3 系列（通过官方 OpenAI API，非 DeepSeek 转发）：
	// 支持 reasoning_effort；不返回 reasoning_content（其推理过程不通过该字段暴露）。
	"openai/o1":  {SupportsReasoningEffort: true},
	"openai/o3":  {SupportsReasoningEffort: true},
	"openai/o1-mini": {SupportsReasoningEffort: true},
	"openai/o3-mini": {SupportsReasoningEffort: true},
}

// Lookup 返回指定 (provider, model) 的能力。provider 与 model 大小写不敏感。
//
// 查找策略（逐级降级，保证总有返回值，绝不 panic）：
//   1. 精确匹配 "provider/model"；
//   2. provider 下任意 model 都未命中时，返回该 provider 的零能力默认（全 false）；
//   3. provider 也未知时，返回全零 Capabilities（最安全：不下发任何推理参数）。
//
// 这意味着：对任何未在矩阵中登记的模型，行为都是"只发标准 chat completions 字段"，
// 不会再重蹈旧版"硬塞 reasoning_effort 导致 400"的覆辙。
func Lookup(provider, model string) Capabilities {
	key := normalizeKey(provider, model)
	if caps, ok := capabilityMatrix[key]; ok {
		return caps
	}
	// 未命中：返回零值 Capabilities（全 false），即安全兜底。
	// 不返回 error——调用方无需为"未知模型"做特殊处理，能力矩阵天然降级。
	return Capabilities{}
}

// normalizeKey 将 provider/model 转为小写并拼接为 "provider/model" 形式作为查表 key。
// 去除首尾空白以容忍配置中的多余空格。
func normalizeKey(provider, model string) string {
	p := toLowerTrim(provider)
	m := toLowerTrim(model)
	if p == "" || m == "" {
		return ""
	}
	return p + "/" + m
}

// toLowerTrim 是 strings.ToLower + strings.TrimSpace 的简写，避免在本文件再 import strings。
// （保持 provider.go 依赖最小化，便于阅读。）
func toLowerTrim(s string) string {
	// 手写小写转换仅处理 ASCII，模型名均为 ASCII，足够。
	b := make([]byte, 0, len(s))
	for i := 0; i < len(s); i++ {
		c := s[i]
		// 去除首尾空白：这里简化为逐字符处理，遇到非空白才追加
		if c == ' ' || c == '\t' || c == '\n' || c == '\r' {
			continue
		}
		if c >= 'A' && c <= 'Z' {
			c += 'a' - 'A'
		}
		b = append(b, c)
	}
	return string(b)
}
