// Package store 的技能数据访问层。
//
// 文件概述：skills.go 实现 skills 表的 CRUD 与 upsert，修复旧 Python 版的
// "技能注册幂等性陷阱"（spec §4.1 根因 #5）：
//   旧 init_db.py:134-144 仅当 skills 表完全为空才注册内置技能，表里有一条非内置记录
//   就永不注册 → tools 为空 → 技能路由形同虚设。
//
// 修复方案（spec §6.1 / §7.1）：以 slug 维度 upsert。
//   - RegisterBuiltin：内置技能按 slug upsert，仅更新 name/description/content/level，
//     保留已有技能的 usage_count/success_rate/version（用户/自进化积累的统计不丢）。
//   - UpsertSkill：用户/自进化写入技能，全字段替换（除统计字段由 UpdateSkillStats 专门维护）。
//   - UpdateSkillStats / IncrSkillUsage：自进化闭环更新用量与成功率。
package store

import (
	"database/sql"
	"errors"
	"fmt"
	"time"
)

// Skill 对应 skills 表一行。字段与 store.go Migrate 中的建表语句一一对应。
//
// 自进化字段（spec §6.1）：
//   - UsageCount  : 累计使用次数，每次该技能被注入 prompt 并参与任务后 +1
//   - SuccessRate : 成功率（0~1），由 UpdateSkillStats 根据任务结果增量更新
//   - Level       : 渐进式披露层级（spec §6.4）：0 概要 / 1 完整 / 2 深入参考
//   - Version     : 技能版本，每次自进化改进 +1
//   - LastImprovedAt : 最近一次自进化改进时间
type Skill struct {
	ID             string  `json:"id"`               // 主键（通常等于 slug）
	Slug           string  `json:"slug"`             // 唯一标识，upsert 维度
	Name           string  `json:"name"`             // 展示名
	Description    string  `json:"description"`      // 一句话描述
	Content        string  `json:"content"`          // 技能 prompt/指令正文
	Enabled        bool    `json:"enabled"`          // 是否启用
	Level          int     `json:"level"`            // 渐进披露层级 0/1/2
	UsageCount     int     `json:"usage_count"`      // 使用次数
	SuccessRate    float64 `json:"success_rate"`     // 成功率 0~1
	Version        int     `json:"version"`          // 版本号
	LastImprovedAt string  `json:"last_improved_at"` // 最近自进化时间
	CreatedAt      string  `json:"created_at"`       // 创建时间
}

// ErrSkillNotFound 表示按 slug 未找到技能。供上层区分"空结果"与"查询错误"。
var ErrSkillNotFound = errors.New("技能不存在")

// RegisterBuiltin 按 slug upsert 一个内置技能。
//
// 关键差异（与旧版"整表为空才注册"的根本区别）：
//   - 若 slug 已存在：只更新 name/description/content/level，绝不覆盖
//     usage_count/success_rate/version/last_improved_at（保护用户与自进化的积累）；
//   - 若 slug 不存在：插入新行，统计字段用默认值。
//
// 这保证内置技能永远会被注册/刷新，且不会清掉已有的使用统计。
func RegisterBuiltin(db *sql.DB, s Skill) error {
	if s.Slug == "" {
		return fmt.Errorf("技能 slug 不能为空")
	}
	if s.ID == "" {
		s.ID = s.Slug
	}
	// upsert：命中 slug 时只更新内容字段，统计字段保持原值（COALESCE 保留旧值）
	const q = `
INSERT INTO skills (id, slug, name, description, content, enabled, level, usage_count, success_rate, version, last_improved_at)
VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 1, '')
ON CONFLICT(slug) DO UPDATE SET
	name           = excluded.name,
	description    = excluded.description,
	content        = excluded.content,
	level          = excluded.level,
	enabled        = COALESCE(skills.enabled, 1)`
	enabled := 1
	if !s.Enabled {
		enabled = 0
	}
	_, err := db.Exec(q, s.ID, s.Slug, s.Name, s.Description, s.Content, enabled, s.Level)
	if err != nil {
		return fmt.Errorf("注册内置技能 %s 失败: %w", s.Slug, err)
	}
	return nil
}

// UpsertSkill 写入/更新一个技能（用户创建或自进化产出）。
// 与 RegisterBuiltin 不同：此函数全字段写入（含 level/enabled），适合用户主动编辑或
// 自进化产出新版本。统计字段（usage_count/success_rate/version）仍由专门接口维护，
// 这里写入时保留旧值（COALESCE），避免编辑内容时清零统计。
func UpsertSkill(db *sql.DB, s Skill) error {
	if s.Slug == "" {
		return fmt.Errorf("技能 slug 不能为空")
	}
	if s.ID == "" {
		s.ID = s.Slug
	}
	const q = `
INSERT INTO skills (id, slug, name, description, content, enabled, level, usage_count, success_rate, version, last_improved_at)
VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 1, '')
ON CONFLICT(slug) DO UPDATE SET
	name           = excluded.name,
	description    = excluded.description,
	content        = excluded.content,
	level          = excluded.level,
	enabled        = excluded.enabled`
	enabled := 1
	if !s.Enabled {
		enabled = 0
	}
	_, err := db.Exec(q, s.ID, s.Slug, s.Name, s.Description, s.Content, enabled, s.Level)
	if err != nil {
		return fmt.Errorf("upsert 技能 %s 失败: %w", s.Slug, err)
	}
	return nil
}

// GetSkillBySlug 按 slug 查询单个技能。未找到返回 ErrSkillNotFound。
func GetSkillBySlug(db *sql.DB, slug string) (*Skill, error) {
	const q = `SELECT id, slug, name, description, content, enabled, level, usage_count, success_rate, version, last_improved_at, created_at FROM skills WHERE slug = ?`
	row := db.QueryRow(q, slug)
	var s Skill
	var enabled int
	if err := row.Scan(&s.ID, &s.Slug, &s.Name, &s.Description, &s.Content, &enabled, &s.Level, &s.UsageCount, &s.SuccessRate, &s.Version, &s.LastImprovedAt, &s.CreatedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrSkillNotFound
		}
		return nil, fmt.Errorf("查询技能 %s 失败: %w", slug, err)
	}
	s.Enabled = enabled != 0
	return &s, nil
}

// ListSkills 列出全部技能。enabledOnly=true 时只返回启用技能。
// 按 usage_count 降序排列：高频使用的技能靠前，便于自进化优先改进。
func ListSkills(db *sql.DB, enabledOnly bool) ([]Skill, error) {
	q := `SELECT id, slug, name, description, content, enabled, level, usage_count, success_rate, version, last_improved_at, created_at FROM skills`
	if enabledOnly {
		q += ` WHERE enabled = 1`
	}
	q += ` ORDER BY usage_count DESC, slug ASC`
	rows, err := db.Query(q)
	if err != nil {
		return nil, fmt.Errorf("查询技能列表失败: %w", err)
	}
	defer rows.Close()

	var out []Skill
	for rows.Next() {
		var s Skill
		var enabled int
		if err := rows.Scan(&s.ID, &s.Slug, &s.Name, &s.Description, &s.Content, &enabled, &s.Level, &s.UsageCount, &s.SuccessRate, &s.Version, &s.LastImprovedAt, &s.CreatedAt); err != nil {
			return nil, fmt.Errorf("扫描技能行失败: %w", err)
		}
		s.Enabled = enabled != 0
		out = append(out, s)
	}
	return out, rows.Err()
}

// DeleteSkill 按 slug 删除技能。不存在不算错误（幂等）。
func DeleteSkill(db *sql.DB, slug string) error {
	_, err := db.Exec(`DELETE FROM skills WHERE slug = ?`, slug)
	if err != nil {
		return fmt.Errorf("删除技能 %s 失败: %w", slug, err)
	}
	return nil
}

// IncrSkillUsage 原子地将某技能 usage_count +1。
// 自进化闭环（spec §6.1 Observe→Plan→Act→Learn）的 Observe 阶段调用：
// 每当某技能被注入 prompt 并参与一次任务，调用此函数记录使用。
func IncrSkillUsage(db *sql.DB, slug string) error {
	res, err := db.Exec(`UPDATE skills SET usage_count = usage_count + 1 WHERE slug = ?`, slug)
	if err != nil {
		return fmt.Errorf("更新技能 %s 使用次数失败: %w", slug, err)
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return ErrSkillNotFound
	}
	return nil
}

// UpdateSkillStats 更新技能的成功率与版本，并刷新 last_improved_at。
//
// 成功率采用增量平滑（exponential moving average）而非全量替换，避免单次失败
// 把长期积累的好成绩清零：
//   newRate = alpha * recentSuccess + (1-alpha) * oldRate
// 其中 recentSuccess 为本次任务结果（1.0 成功 / 0.0 失败），alpha 默认 0.3。
//
// succeeded=true 时 version+1（持续改进），失败不增版本（避免噪声驱动版本膨胀）。
// 注意：本函数前置要求是 IncrSkillUsage 已先把 usage_count +1，这里只动成功率/版本/时间。
func UpdateSkillStats(db *sql.DB, slug string, succeeded bool) error {
	const alpha = 0.3 // EMA 平滑系数：新结果权重 0.3，历史权重 0.7
	recent := 0.0
	if succeeded {
		recent = 1.0
	}
	// 一条 SQL 完成：读取旧成功率 → EMA → 写回；成功时 version+1
	const q = `
UPDATE skills SET
	success_rate = ? * ? + (1 - ?) * success_rate,
	version = version + ?,
	last_improved_at = ?
WHERE slug = ?`
	verIncr := 0
	if succeeded {
		verIncr = 1
	}
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := db.Exec(q, alpha, recent, alpha, verIncr, now, slug)
	if err != nil {
		return fmt.Errorf("更新技能 %s 统计失败: %w", slug, err)
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return ErrSkillNotFound
	}
	return nil
}
