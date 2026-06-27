// store 包 skills 表的测试。
//
// 覆盖痛点①根因 #5（技能注册幂等性陷阱）的修复：
//   - 内置技能可重复注册（不再"表非空就跳过"）
//   - 重复注册保留已有统计（usage_count/success_rate/version 不被清零）
//   - upsert/get/list/delete/incr/stats 全链路
package store

import (
	"database/sql"
	"path/filepath"
	"testing"
)

// newSkillsTestDB 建一个内存级临时库并迁移。每个测试独立，互不污染。
func newSkillsTestDB(t *testing.T) *sql.DB {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open 失败: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	if err := Migrate(db); err != nil {
		t.Fatalf("Migrate 失败: %v", err)
	}
	return db
}

// TestRegisterBuiltinIdempotent 验证内置技能可重复注册且不破坏统计。
// 这是修复"表非空就永不注册"陷阱的核心断言。
func TestRegisterBuiltinIdempotent(t *testing.T) {
	db := newSkillsTestDB(t)

	// 第一次注册
	if err := RegisterBuiltin(db, Skill{
		Slug: "summarize", Name: "摘要", Description: "生成论文摘要",
		Content: "v1 内容", Level: 0, Enabled: true,
	}); err != nil {
		t.Fatalf("首次注册失败: %v", err)
	}

	// 模拟使用：incr + 多次成功统计，使成功率积累到明显非零值
	if err := IncrSkillUsage(db, "summarize"); err != nil {
		t.Fatalf("IncrSkillUsage 失败: %v", err)
	}
	for i := 0; i < 3; i++ {
		if err := UpdateSkillStats(db, "summarize", true); err != nil {
			t.Fatalf("UpdateSkillStats 失败: %v", err)
		}
	}

	// 校验统计已积累
	got, err := GetSkillBySlug(db, "summarize")
	if err != nil {
		t.Fatalf("GetSkillBySlug 失败: %v", err)
	}
	if got.UsageCount != 1 {
		t.Fatalf("usage_count 异常: %d", got.UsageCount)
	}
	if got.Version != 4 { // version 初始 1，3 次成功各 +1 → 4
		t.Fatalf("version 异常: %d", got.Version)
	}
	if got.SuccessRate == 0 { // EMA 多次成功后应明显 > 0
		t.Fatalf("成功率不应为 0: %v", got.SuccessRate)
	}
	// 捕获注册前的统计基准，用于二次注册后比对（不依赖 EMA 具体公式）
	beforeUsage, beforeVersion, beforeRate := got.UsageCount, got.Version, got.SuccessRate

	// 第二次注册（更新内容）——不应清零统计
	if err := RegisterBuiltin(db, Skill{
		Slug: "summarize", Name: "摘要v2", Description: "改进版",
		Content: "v2 内容", Level: 1, Enabled: true,
	}); err != nil {
		t.Fatalf("二次注册失败: %v", err)
	}
	got2, _ := GetSkillBySlug(db, "summarize")
	if got2.Content != "v2 内容" || got2.Name != "摘要v2" {
		t.Fatalf("内容未更新: %+v", got2)
	}
	// 关键断言：统计字段与注册前完全一致（保留用户/自进化积累）
	if got2.UsageCount != beforeUsage || got2.Version != beforeVersion || got2.SuccessRate != beforeRate {
		t.Fatalf("重复注册改变了统计! before(usage=%d ver=%d rate=%v) after(usage=%d ver=%d rate=%v)",
			beforeUsage, beforeVersion, beforeRate, got2.UsageCount, got2.Version, got2.SuccessRate)
	}
}

// TestRegisterBuiltinAlongsideUserSkill 验证"表里有用户技能时内置技能仍能注册"。
// 这正是旧版 init_db.py 的崩溃场景：表非空 → 跳过内置注册 → tools 为空。
func TestRegisterBuiltinAlongsideUserSkill(t *testing.T) {
	db := newSkillsTestDB(t)
	// 先写一条用户技能
	if err := UpsertSkill(db, Skill{Slug: "my-skill", Name: "我的", Content: "x"}); err != nil {
		t.Fatalf("UpsertSkill 失败: %v", err)
	}
	// 此时表非空，旧版会跳过；新版应正常注册内置技能
	if err := RegisterBuiltin(db, Skill{Slug: "builtin-1", Name: "内置", Content: "y"}); err != nil {
		t.Fatalf("表非空时注册内置失败: %v", err)
	}
	got, err := GetSkillBySlug(db, "builtin-1")
	if err != nil || got == nil {
		t.Fatalf("内置技能未注册成功: %v %v", got, err)
	}
}

// TestListSkillsOrderByUsage 验证按 usage_count 降序排列（高频在前）。
func TestListSkillsOrderByUsage(t *testing.T) {
	db := newSkillsTestDB(t)
	_ = RegisterBuiltin(db, Skill{Slug: "a", Name: "A", Content: "1"})
	_ = RegisterBuiltin(db, Skill{Slug: "b", Name: "B", Content: "2"})
	_ = RegisterBuiltin(db, Skill{Slug: "c", Name: "C", Content: "3"})
	// b 用 3 次，a 用 1 次，c 用 0 次
	for i := 0; i < 3; i++ {
		_ = IncrSkillUsage(db, "b")
	}
	_ = IncrSkillUsage(db, "a")

	list, err := ListSkills(db, false)
	if err != nil {
		t.Fatalf("ListSkills 失败: %v", err)
	}
	if len(list) != 3 {
		t.Fatalf("期望 3 条技能，得到 %d", len(list))
	}
	if list[0].Slug != "b" || list[1].Slug != "a" || list[2].Slug != "c" {
		t.Fatalf("排序异常，期望 b a c，得到 %s %s %s", list[0].Slug, list[1].Slug, list[2].Slug)
	}
}

// TestUpdateSkillStatsEMA 验证成功率 EMA 平滑：连续成功→渐近 1.0，再失败→回落但不清零。
// EMA 公式（alpha=0.3，从 0 起）：rate_n = 1 - 0.7^n。
func TestUpdateSkillStatsEMA(t *testing.T) {
	db := newSkillsTestDB(t)
	_ = RegisterBuiltin(db, Skill{Slug: "s", Name: "S", Content: "x"})

	// 连续 5 次成功 → rate = 1 - 0.7^5 ≈ 0.832
	for i := 0; i < 5; i++ {
		_ = UpdateSkillStats(db, "s", true)
	}
	got, _ := GetSkillBySlug(db, "s")
	// 0.82~0.84 容差
	if got.SuccessRate < 0.82 || got.SuccessRate > 0.84 {
		t.Fatalf("5 次成功后成功率应约 0.832，实际 %v", got.SuccessRate)
	}
	if got.Version != 6 { // 初始 1 + 5 次成功
		t.Fatalf("version 期望 6，得到 %d", got.Version)
	}
	// 一次失败 → newRate = 0.3*0 + 0.7*0.832 ≈ 0.582（回落但不清零）
	_ = UpdateSkillStats(db, "s", false)
	got2, _ := GetSkillBySlug(db, "s")
	if got2.SuccessRate < 0.55 || got2.SuccessRate > 0.61 {
		t.Fatalf("一次失败后成功率应约 0.582，实际 %v", got2.SuccessRate)
	}
	// 失败不应增加版本
	if got2.Version != 6 {
		t.Fatalf("失败不应增版本，期望 6，得到 %d", got2.Version)
	}
}

// TestDeleteSkill 验证删除幂等。
func TestDeleteSkill(t *testing.T) {
	db := newSkillsTestDB(t)
	_ = RegisterBuiltin(db, Skill{Slug: "tmp", Name: "T", Content: "x"})
	if err := DeleteSkill(db, "tmp"); err != nil {
		t.Fatalf("删除失败: %v", err)
	}
	if _, err := GetSkillBySlug(db, "tmp"); err != ErrSkillNotFound {
		t.Fatalf("删除后应返回 ErrSkillNotFound，得到 %v", err)
	}
	// 再删一次不报错（幂等）
	if err := DeleteSkill(db, "tmp"); err != nil {
		t.Fatalf("重复删除应幂等，得到 %v", err)
	}
}

// TestGetSkillNotFound 验证未找到返回明确错误。
func TestGetSkillNotFound(t *testing.T) {
	db := newSkillsTestDB(t)
	_, err := GetSkillBySlug(db, "nope")
	if err != ErrSkillNotFound {
		t.Fatalf("期望 ErrSkillNotFound，得到 %v", err)
	}
}
