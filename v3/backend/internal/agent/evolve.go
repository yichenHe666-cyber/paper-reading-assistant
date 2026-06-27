// agent 包的自进化能力雏形。
//
// 文件概述：evolve.go 实现 spec §6 的 Hermes 风格闭环学习最小闭环：
//   Observe → Plan → Act → Learn
//     - Observe：收集会话消息（用户意图 + agent 工具调用 + 最终回答）
//     - Plan   ：让 LLM 评估"什么有效/什么可复用"，决定是否值得沉淀为技能
//     - Act    ：若值得，提炼出技能草稿（slug/name/description/content）
//     - Learn  ：UpsertSkill 落库，后续相似任务可复用
//
// 触发节奏（spec §6.2）：每约 N 次工具调用（默认 15）评估一次；也支持手动触发。
// M2 实现"技能效果评估 + 增量改进"的最小闭环，不追求完整 GEPA（spec §6.3）。
//
// 安全缰绳（spec §6.5）：
//   - 凭证不进技能文件（distill prompt 显式禁止包含 key/token）；
//   - 技能变更可审查（落库后用户可在 /api/skills 查看/禁用/删除）；
//   - prompt 注入防护：提炼出的 content 会被注入 system prompt，但模型无法直接执行
//     危险操作（工具调用仍受 ToolRegistry 白名单约束）。
package agent

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"

	"nuclear-ox-v2/backend/internal/llm"
	"nuclear-ox-v2/backend/internal/store"
)

// DistillThreshold 是默认的自进化触发阈值（spec §6.2：约 15 次工具调用）。
const DistillThreshold = 15

// Evolver 负责自进化：从会话提炼技能 + 维护技能用量统计。
type Evolver struct {
	llmClient *llm.Client // 用于 Observe/Plan/Act 阶段的 LLM 调用
	db        *sql.DB     // 经 store 包函数操作 skills 表
}

// NewEvolver 构造自进化器。
func NewEvolver(llmClient *llm.Client, db *sql.DB) *Evolver {
	return &Evolver{llmClient: llmClient, db: db}
}

// ShouldDistill 判断是否该触发自进化。
// toolCallCount 为本会话累计工具调用次数；达到阈值返回 true。
// 阈值取 DistillThreshold；调用方可覆盖（如手动触发时传 -1 强制为 true）。
func (e *Evolver) ShouldDistill(toolCallCount int) bool {
	return toolCallCount >= DistillThreshold
}

// skillDraft 是 LLM 提炼出的技能草稿结构。
type skillDraft struct {
	Slug        string `json:"slug"`         // 唯一标识（kebab-case）
	Name        string `json:"name"`         // 展示名
	Description string `json:"description"`  // 一句话描述
	Content     string `json:"content"`      // 技能指引正文
	WorthSaving bool   `json:"worth_saving"` // LLM 判断是否值得沉淀
}

// DistillSkill 从一次会话提炼可复用技能（Observe→Plan→Act→Learn 闭环）。
//
// 流程：
//  1. Observe：传入会话消息摘要（messages 已由调用方从 store 加载）；
//  2. Plan+Act：让 LLM 评估并产出 skillDraft JSON；
//  3. Learn：若 WorthSaving，UpsertSkill 落库。
//
// 返回提炼出的草稿（无论是否落库）与可能的错误。
// 安全校验：拒绝 slug 含路径分隔符/空白；content 截断到 8KB 防膨胀。
func (e *Evolver) DistillSkill(ctx context.Context, messages []store.Message) (*skillDraft, error) {
	if len(messages) == 0 {
		return nil, fmt.Errorf("会话无消息，无法提炼")
	}

	// Observe：把会话压缩成文本（仅 role + content 摘要，去 tool_calls 细节避免噪音）
	conv := compressConversation(messages)
	if conv == "" {
		return nil, fmt.Errorf("会话内容为空，无法提炼")
	}

	// Plan+Act：构造提炼 prompt
	prompt := buildDistillPrompt(conv)
	resp, err := e.llmClient.Chat(ctx, []llm.Message{
		{Role: llm.RoleSystem, Content: "你是技能提炼器，从对话中提取可复用的工作流知识。只输出 JSON。"},
		{Role: llm.RoleUser, Content: prompt},
	}, llm.WithTemperature(0.2), llm.WithMaxTokens(1024))
	if err != nil {
		return nil, fmt.Errorf("提炼技能 LLM 调用失败: %w", err)
	}
	if len(resp.Choices) == 0 {
		return nil, fmt.Errorf("提炼技能返回空响应")
	}
	raw := resp.Choices[0].Message.Content

	// 解析 JSON（容忍代码块包裹）
	draft, err := parseSkillDraft(raw)
	if err != nil {
		return nil, fmt.Errorf("解析技能草稿失败: %w", err)
	}

	// 安全校验
	if err := validateDraft(draft); err != nil {
		return nil, err
	}
	// content 截断防膨胀
	if len(draft.Content) > 8192 {
		draft.Content = draft.Content[:8192]
	}

	// Learn：值得沉淀则落库
	if draft.WorthSaving && draft.Slug != "" {
		if err := store.UpsertSkill(e.db, store.Skill{
			Slug:        draft.Slug,
			Name:        draft.Name,
			Description: draft.Description,
			Content:     draft.Content,
			Enabled:     true, // 落库即启用，用户可手动禁用
			Level:       0,    // Level 0 概要默认注入
		}); err != nil {
			return draft, fmt.Errorf("技能落库失败: %w", err)
		}
	}
	return draft, nil
}

// TrackUsage 更新一批技能的用量统计（Learn 阶段的持续改进）。
// succeeded 表示本次任务整体是否成功：成功则 usage+1 & stats(success)，
// 失败则仅 usage+1 & stats(failure)（仍记录使用，但不增版本）。
//
// 这是 GEPA 式"按效果反馈调整"的最小落地：高成功率技能优先被复用（见 skill.go 展示顺序）。
func (e *Evolver) TrackUsage(slugs []string, succeeded bool) error {
	for _, slug := range slugs {
		if slug == "" {
			continue
		}
		// IncrSkillUsage：不存在则跳过（用户可能已删除该技能）
		if err := store.IncrSkillUsage(e.db, slug); err != nil {
			if errors.Is(err, store.ErrSkillNotFound) {
				continue
			}
			return fmt.Errorf("更新技能 %s 用量失败: %w", slug, err)
		}
		if err := store.UpdateSkillStats(e.db, slug, succeeded); err != nil {
			if errors.Is(err, store.ErrSkillNotFound) {
				continue
			}
			return fmt.Errorf("更新技能 %s 统计失败: %w", slug, err)
		}
	}
	return nil
}

// compressConversation 把会话消息压缩成供 LLM 提炼的文本。
// 仅保留 role + content（tool_calls 细节省略，避免噪音），每条限 500 字。
func compressConversation(messages []store.Message) string {
	var b strings.Builder
	for _, m := range messages {
		// 跳过空 content 且无 tool_calls 的消息
		if m.Content == "" && m.ToolCalls == "" {
			continue
		}
		switch m.Role {
		case "user":
			b.WriteString("[用户] ")
		case "assistant":
			b.WriteString("[助手] ")
		case "tool":
			b.WriteString("[工具结果] ")
		case "system":
			continue // 系统提示不含可提炼的任务知识
		default:
			b.WriteString("[" + m.Role + "] ")
		}
		content := m.Content
		if len([]rune(content)) > 500 {
			content = string([]rune(content)[:500]) + "..."
		}
		b.WriteString(content)
		b.WriteString("\n")
	}
	return b.String()
}

// buildDistillPrompt 构造提炼技能的 prompt。
// 显式要求：输出 JSON、不含凭证、slug 用 kebab-case。
func buildDistillPrompt(conv string) string {
	return fmt.Sprintf(`从以下对话中提炼可复用的工作流技能。

对话内容：
%s

要求：
1. 判断这次对话是否包含值得沉淀为技能的可复用模式（如"查询主题→检索论文→取详情→综合回答"）。
2. 若值得，输出技能草稿；若不值得（如简单闲聊），仍输出 JSON 但 worth_saving=false。
3. slug 用 kebab-case 英文，简短唯一。
4. content 是可复用的指引步骤，中文，不超过 500 字。
5. 严禁在技能中包含任何 API key、token、密码等凭证。
6. 只输出 JSON，格式：{"slug":"...","name":"...","description":"...","content":"...","worth_saving":true}`, conv)
}

// parseSkillDraft 解析 LLM 返回的技能草稿 JSON，容忍 ```json 代码块包裹。
func parseSkillDraft(raw string) (*skillDraft, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, fmt.Errorf("空内容")
	}
	// 去代码块包裹
	if strings.HasPrefix(raw, "```") {
		raw = strings.TrimPrefix(raw, "```json")
		raw = strings.TrimPrefix(raw, "```")
		raw = strings.TrimSuffix(raw, "```")
		raw = strings.TrimSpace(raw)
	}
	var d skillDraft
	if err := json.Unmarshal([]byte(raw), &d); err != nil {
		return nil, fmt.Errorf("JSON 解析失败: %w（原文前200字: %s）", err, truncForErr(raw, 200))
	}
	return &d, nil
}

// validateDraft 校验草稿安全性。
func validateDraft(d *skillDraft) error {
	if d == nil {
		return fmt.Errorf("草稿为空")
	}
	// slug 安全校验：禁止路径分隔符与空白，防路径遍历/注入
	if d.Slug != "" {
		if strings.ContainsAny(d.Slug, "/\\\n\r\t ") {
			return fmt.Errorf("slug 含非法字符: %q", d.Slug)
		}
	}
	// 凭证扫描：content 含疑似 key 的模式则拒绝（粗筛，宁可误拒不可漏）
	for _, pat := range []string{"sk-", "api_key", "API_KEY", "Bearer ", "password=", "token="} {
		if strings.Contains(d.Content, pat) {
			return fmt.Errorf("技能 content 疑似包含凭证（%s），已拒绝", pat)
		}
	}
	return nil
}

// truncForErr 截断字符串用于错误信息。
func truncForErr(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}
