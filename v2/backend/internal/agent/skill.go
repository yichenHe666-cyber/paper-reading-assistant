// agent 包的技能注册表与渐进式披露。
//
// 文件概述：skill.go 负责从 store 加载启用技能，构造"Level 0 概要"注入 system prompt，
// 并记录哪些技能被注入（供自进化统计用量）。
//
// 渐进式披露（spec §6.4）：
//   - Level 0：技能概要（name + description）始终注入 system prompt，约数千 tokens 预算内；
//   - Level 1：技能完整 content 按需加载（M2 阶段通过摘要提示模型"如需详细步骤可追问"）；
//   - Level 2：深入参考材料（M4+ 配合向量检索实现）。
//
// M2 实现 Level 0：把启用技能的 name+description 汇编成一段提示，告诉模型可用技能。
// 这让自进化（evolve.go）产出的技能能被模型感知并在合适场景复用。
package agent

import (
	"database/sql"
	"fmt"
	"strings"

	"nuclear-ox-v2/backend/internal/store"
)

// SkillRegistry 管理技能加载与 system prompt 注入。
type SkillRegistry struct {
	db           *sql.DB   // 数据库连接（查 skills 表）
	enabledSlugs []string  // 显式启用的 slug 列表；nil 表示使用全部 enabled=1 的技能
}

// NewSkillRegistry 构造技能注册表。
// enabledSlugs 为 nil 时使用会话默认（全部启用技能）；非空时仅加载指定 slug（manual 模式）。
func NewSkillRegistry(db *sql.DB, enabledSlugs []string) *SkillRegistry {
	return &SkillRegistry{db: db, enabledSlugs: enabledSlugs}
}

// LoadEnabled 加载应注入的技能列表。
// 过滤逻辑：取 enabled=1 的技能；若 enabledSlugs 非空，再限定到这些 slug。
func (r *SkillRegistry) LoadEnabled() ([]store.Skill, error) {
	all, err := store.ListSkills(r.db, true) // true: 仅 enabled
	if err != nil {
		return nil, fmt.Errorf("加载技能失败: %w", err)
	}
	if len(r.enabledSlugs) == 0 {
		return all, nil
	}
	// manual 模式：仅保留指定 slug
	wanted := make(map[string]bool, len(r.enabledSlugs))
	for _, s := range r.enabledSlugs {
		wanted[s] = true
	}
	out := make([]store.Skill, 0, len(all))
	for _, s := range all {
		if wanted[s.Slug] {
			out = append(out, s)
		}
	}
	return out, nil
}

// SystemPromptBlock 构造注入 system prompt 的技能概要块（Level 0）。
//
// 返回值：
//   - prompt：汇编后的提示文本（无技能时返回空串，调用方可选择不追加）；
//   - slugs：本次实际注入的技能 slug 列表（供自进化 IncrSkillUsage 统计用量）；
//   - err：加载错误。
//
// 文本格式示例：
//   【可用技能】以下技能可在合适场景复用，按需调用对应工具或遵循其指引：
//   - summarize（使用 12 次，成功率 0.85）: 生成论文结构化摘要
//   - qa（使用 5 次，成功率 0.90）: 针对论文内容问答
//
// 把 usage_count/success_rate 一并展示，让模型优先复用验证过的高成功率技能——
// 这是 Hermes 风格"复用降低 token 与成本"的最小落地。
func (r *SkillRegistry) SystemPromptBlock() (prompt string, slugs []string, err error) {
	skills, err := r.LoadEnabled()
	if err != nil {
		return "", nil, err
	}
	if len(skills) == 0 {
		return "", nil, nil
	}
	var b strings.Builder
	b.WriteString("【可用技能】以下技能可在合适场景复用，按需遵循其指引或调用对应工具：\n")
	for _, s := range skills {
		// 概要行：slug（用量与成功率）: 描述
		fmt.Fprintf(&b, "- %s（使用 %d 次，成功率 %.2f）: %s\n",
			s.Slug, s.UsageCount, s.SuccessRate, s.Description)
		// Level 0 概要：若技能 content 较短（<500 字），直接附上；过长则仅展示描述
		// （完整 content 走 Level 1 按需加载，M2 阶段不自动注入避免 prompt 膨胀）
		if s.Content != "" && len([]rune(s.Content)) <= 500 {
			b.WriteString("  指引: ")
			b.WriteString(s.Content)
			b.WriteString("\n")
		}
		slugs = append(slugs, s.Slug)
	}
	return b.String(), slugs, nil
}

// BuildSystemPrompt 组装完整 system prompt：基础角色描述 + 技能概要块。
// skillBlock 为空时仅返回基础描述。
func BuildSystemPrompt(base, skillBlock string) string {
	if skillBlock == "" {
		return base
	}
	return base + "\n\n" + skillBlock
}
