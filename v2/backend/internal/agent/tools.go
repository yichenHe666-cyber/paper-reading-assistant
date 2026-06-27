// agent 包的工具系统。
//
// 文件概述：tools.go 定义 Tool 接口、ToolRegistry 注册表，以及三个内置工具
// （list_topics / search_papers / get_paper），让 agent 能查询本地论文库。
//
// 设计动机（spec §4.1 根因 #6"无 agent loop"的配套）：
// 旧版 _send_with_tools 仅"一次工具调用 + 一次最终回答"，工具为空时技能路由形同虚设。
// 本包提供真实可执行的工具，配合 loop.go 的 maxTurns 循环实现多步推理：
//   模型 → 决定调用 list_topics → 拿到主题 → 决定调用 search_papers → 拿到论文
//   → 决定调用 get_paper → 拿到摘要 → 综合回答用户。
//
// 工具协议：Execute 接收 JSON 字符串参数，返回 JSON 字符串结果。
// 这样 agent loop 无需关心每个工具的参数 schema，统一以 string 透传给 LLM 回传。
package agent

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"nuclear-ox-v2/backend/internal/llm"
	"nuclear-ox-v2/backend/internal/paper"
)

// Tool 是 agent 可调用的工具抽象。每个工具负责：声明 schema + 执行。
type Tool interface {
	// Name 返回工具名（与 Definition().Function.Name 一致，模型据此调用）。
	Name() string
	// Definition 返回该工具的 JSON Schema 声明，注入 LLM 请求的 tools 字段。
	Definition() llm.ToolDefinition
	// Execute 执行工具。argsJSON 为模型回传的参数 JSON 字符串，返回结果 JSON 字符串。
	// 错误以 error 返回，agent loop 会把错误信息作为 tool_result 回传给模型让其自行处理。
	Execute(ctx context.Context, argsJSON string) (string, error)
}

// ToolRegistry 是工具注册表。agent loop 持有它，把 Definitions() 下发给 LLM，
// 收到 tool_calls 后按名称路由到对应 Tool.Execute。
type ToolRegistry struct {
	tools map[string]Tool
}

// NewToolRegistry 创建空注册表。
func NewToolRegistry() *ToolRegistry {
	return &ToolRegistry{tools: make(map[string]Tool)}
}

// Register 注册一个工具。重名覆盖（后注册胜出，便于测试替换）。
func (r *ToolRegistry) Register(t Tool) {
	r.tools[t.Name()] = t
}

// Definitions 返回全部已注册工具的 schema 列表，供 LLM 请求 tools 字段使用。
// 空注册表返回 nil（llm.WithTools 会 omit）。
func (r *ToolRegistry) Definitions() []llm.ToolDefinition {
	if len(r.tools) == 0 {
		return nil
	}
	out := make([]llm.ToolDefinition, 0, len(r.tools))
	for _, t := range r.tools {
		out = append(out, t.Definition())
	}
	return out
}

// Execute 按名称执行工具。未注册返回错误。
func (r *ToolRegistry) Execute(ctx context.Context, name, argsJSON string) (string, error) {
	t, ok := r.tools[name]
	if !ok {
		return "", fmt.Errorf("未知工具: %s", name)
	}
	return t.Execute(ctx, argsJSON)
}

// HasReports 工具是否注册了某名称（供测试断言）。
func (r *ToolRegistry) Has(name string) bool {
	_, ok := r.tools[name]
	return ok
}

// --- 内置工具实现 ---
// 三个工具均依赖 paper.Repository 查询本地论文库。
// agent → paper 单向依赖，paper 不反向依赖 agent，无循环。

// listTopicsTool 列出全部论文主题。
type listTopicsTool struct {
	repo *paper.Repository
}

func (t *listTopicsTool) Name() string { return "list_topics" }
func (t *listTopicsTool) Definition() llm.ToolDefinition {
	return llm.ToolDefinition{
		Type: "function",
		Function: llm.FunctionDefinition{
			Name:        "list_topics",
			Description: "列出本地论文库的全部主题分类。无参数。返回主题数组，每项含 id/name/name_cn/paper_count。",
			Parameters:  map[string]any{"type": "object", "properties": map[string]any{}},
		},
	}
}
func (t *listTopicsTool) Execute(ctx context.Context, argsJSON string) (string, error) {
	topics, err := t.repo.ListTopics()
	if err != nil {
		return "", fmt.Errorf("查询主题失败: %w", err)
	}
	// 空切片序列化为 [] 而非 null（前端/模型友好）
	if topics == nil {
		topics = []paper.Topic{}
	}
	b, err := json.Marshal(topics)
	if err != nil {
		return "", fmt.Errorf("序列化主题失败: %w", err)
	}
	return string(b), nil
}

// searchPapersTool 按主题或关键词搜索论文。
type searchPapersTool struct {
	repo *paper.Repository
}

// searchPapersArgs 是 search_papers 的参数 schema 对应 Go 结构。
type searchPapersArgs struct {
	TopicID string `json:"topic_id,omitempty"` // 可选：限定主题
	Query   string `json:"query,omitempty"`    // 可选：标题/作者关键词（大小写不敏感包含匹配）
	Limit   int    `json:"limit,omitempty"`    // 可选：返回上限，缺省 20
}

func (t *searchPapersTool) Name() string { return "search_papers" }
func (t *searchPapersTool) Definition() llm.ToolDefinition {
	return llm.ToolDefinition{
		Type: "function",
		Function: llm.FunctionDefinition{
			Name:        "search_papers",
			Description: "搜索本地论文库。可按 topic_id 限定主题，按 query 关键词匹配标题/作者。返回论文数组。",
			Parameters: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"topic_id": map[string]any{"type": "string", "description": "可选，限定主题 id"},
					"query":    map[string]any{"type": "string", "description": "可选，标题/作者关键词"},
					"limit":    map[string]any{"type": "integer", "description": "可选，返回上限，缺省 20"},
				},
			},
		},
	}
}
func (t *searchPapersTool) Execute(ctx context.Context, argsJSON string) (string, error) {
	var args searchPapersArgs
	// 空参数容错：模型可能传 "{}" 或空串
	if strings.TrimSpace(argsJSON) != "" {
		if err := json.Unmarshal([]byte(argsJSON), &args); err != nil {
			return "", fmt.Errorf("参数解析失败: %w", err)
		}
	}
	if args.Limit <= 0 {
		args.Limit = 20
	}

	var papers []paper.Paper
	var err error
	if args.TopicID != "" {
		// 按主题取，再内存过滤关键词
		papers, err = t.repo.ListPapers(args.TopicID)
		if err != nil {
			return "", fmt.Errorf("查询主题论文失败: %w", err)
		}
	} else {
		// 无主题限定：目前 repo 未提供全量接口，返回空并提示用 list_topics 先取主题
		// （避免全表扫描；M4 引入向量检索后可改为语义搜索）
		return `[]`, nil
	}

	// 关键词过滤（大小写不敏感包含）
	if args.Query != "" {
		q := strings.ToLower(args.Query)
		filtered := make([]paper.Paper, 0, len(papers))
		for _, p := range papers {
			if strings.Contains(strings.ToLower(p.Title), q) ||
				strings.Contains(strings.ToLower(p.Authors), q) ||
				strings.Contains(strings.ToLower(p.Abstract), q) {
				filtered = append(filtered, p)
			}
		}
		papers = filtered
	}
	// 截断到 limit
	if len(papers) > args.Limit {
		papers = papers[:args.Limit]
	}
	if papers == nil {
		papers = []paper.Paper{}
	}
	b, err := json.Marshal(papers)
	if err != nil {
		return "", fmt.Errorf("序列化论文失败: %w", err)
	}
	return string(b), nil
}

// getPaperTool 查询单篇论文详情。
type getPaperTool struct {
	repo *paper.Repository
}

type getPaperArgs struct {
	ID string `json:"id"`
}

func (t *getPaperTool) Name() string { return "get_paper" }
func (t *getPaperTool) Definition() llm.ToolDefinition {
	return llm.ToolDefinition{
		Type: "function",
		Function: llm.FunctionDefinition{
			Name:        "get_paper",
			Description: "按 id 查询单篇论文详情，含标题/作者/年份/摘要/阅读状态等。",
			Parameters: map[string]any{
				"type": "object",
				"properties": map[string]any{
					"id": map[string]any{"type": "string", "description": "论文 id"},
				},
				"required": []string{"id"},
			},
		},
	}
}
func (t *getPaperTool) Execute(ctx context.Context, argsJSON string) (string, error) {
	var args getPaperArgs
	if err := json.Unmarshal([]byte(argsJSON), &args); err != nil {
		return "", fmt.Errorf("参数解析失败: %w", err)
	}
	if args.ID == "" {
		return "", fmt.Errorf("缺少参数 id")
	}
	p, err := t.repo.GetPaper(args.ID)
	if err != nil {
		return "", fmt.Errorf("查询论文失败: %w", err)
	}
	if p == nil {
		return `{"error":"论文不存在"}`, nil
	}
	b, err := json.Marshal(p)
	if err != nil {
		return "", fmt.Errorf("序列化论文失败: %w", err)
	}
	return string(b), nil
}

// RegisterBuiltinTools 把三个内置工具注册到 registry。
// repo 为论文数据访问层；agent loop 构造时调用此函数装配工具。
func RegisterBuiltinTools(r *ToolRegistry, repo *paper.Repository) {
	r.Register(&listTopicsTool{repo: repo})
	r.Register(&searchPapersTool{repo: repo})
	r.Register(&getPaperTool{repo: repo})
}
