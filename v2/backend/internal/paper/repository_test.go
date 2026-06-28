// Package paper 的 Repository 测试。
//
// 文件概述：repository_test.go 验证论文/主题 CRUD 的核心契约：
//   - Upsert 幂等（重复同步不产生重复行）；
//   - 重开数据库后数据仍在（痛点②"重启读取为 0"的最小验证闭环）；
//   - 重复 Upsert 不覆盖用户阅读进度（read_status）；
//   - Slugify 生成稳定 id。
//
// 测试库由 store.Open + store.Migrate 创建，保证 schema 与生产一致。
package paper

import (
	"database/sql"
	"path/filepath"
	"testing"

	"nuclear-ox-v2/backend/internal/store"
)

// openTestRepo 建一个临时库并迁移 schema。
// 返回 Repository、底层 db（调用方负责 Close）与库路径（供重开测试）。
func openTestRepo(t *testing.T) (*Repository, *sql.DB, string) {
	t.Helper()
	dbPath := filepath.Join(t.TempDir(), "test.db")
	db, err := store.Open(dbPath)
	if err != nil {
		t.Fatalf("store.Open 失败: %v", err)
	}
	if err := store.Migrate(db); err != nil {
		db.Close()
		t.Fatalf("store.Migrate 失败: %v", err)
	}
	return NewRepository(db), db, dbPath
}

// TestSlugify 验证 id 派生的稳定性与规范化。
func TestSlugify(t *testing.T) {
	cases := []struct{ in, want string }{
		{"Distributed Systems", "distributed_systems"},
		{"OSDI '23!", "osdi_23"},
		{"  Multi   Space  ", "multi___space"}, // 空格逐个转下划线
		{"中文目录", ""},                          // 非ASCII全部丢弃 → 空
		{"already_lower", "already_lower"},
		{"Mixed-Case-Name", "mixed-case-name"},
	}
	for _, c := range cases {
		got := Slugify(c.in)
		if got != c.want {
			t.Errorf("Slugify(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

// TestUpsertTopicIdempotent 验证主题 Upsert 幂等：同 id 写两次只留一条。
func TestUpsertTopicIdempotent(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()
	t1 := Topic{ID: "distributed_systems", Name: "distributed_systems", NameCN: "分布式系统"}
	if err := repo.UpsertTopic(t1); err != nil {
		t.Fatal(err)
	}
	// 第二次 Upsert（模拟重复同步），应更新而非新增
	t1.NameCN = "分布式系统（更新）"
	if err := repo.UpsertTopic(t1); err != nil {
		t.Fatal(err)
	}
	topics, err := repo.ListTopics()
	if err != nil {
		t.Fatal(err)
	}
	if len(topics) != 1 {
		t.Fatalf("幂等后应只 1 条主题，实际 %d", len(topics))
	}
	if topics[0].NameCN != "分布式系统（更新）" {
		t.Errorf("NameCN 未更新: %q", topics[0].NameCN)
	}
}

// TestUpsertPaperAndList 验证论文写入、列出、重开后持久。
// 重开后持久是痛点②修复的核心验证：只要库路径稳定，重启即得旧数据。
func TestUpsertPaperAndList(t *testing.T) {
	repo, db, dbPath := openTestRepo(t)
	// 注意：store.Open 启用了外键约束，必须先建主题再建论文（papers.topic_id → topics.id）
	if err := repo.UpsertTopic(Topic{ID: "distributed_systems", Name: "distributed_systems"}); err != nil {
		t.Fatal(err)
	}
	p := Paper{
		ID: "distributed_systems_mapreduce", Title: "MapReduce",
		TopicID: "distributed_systems", PDFURL: "http://x/mr.pdf", ReadStatus: "unread",
	}
	if err := repo.UpsertPaper(p); err != nil {
		t.Fatal(err)
	}
	_ = repo.UpdatePaperCount("distributed_systems")

	// 列出验证
	papers, err := repo.ListPapersByTopic("distributed_systems")
	if err != nil {
		t.Fatal(err)
	}
	if len(papers) != 1 || papers[0].Title != "MapReduce" {
		t.Fatalf("ListPapersByTopic 错误: %+v", papers)
	}

	// 关闭后重开同一文件，验证数据持久（模拟重启）
	if err := db.Close(); err != nil {
		t.Fatal(err)
	}
	db2, err := store.Open(dbPath)
	if err != nil {
		t.Fatalf("重开数据库失败: %v", err)
	}
	defer db2.Close()
	repo2 := NewRepository(db2)

	// 重开后论文仍在——这正是"重启不丢论文"的保证
	n, err := repo2.CountPapers()
	if err != nil {
		t.Fatal(err)
	}
	if n != 1 {
		t.Fatalf("重开后论文数应为 1，实际 %d（数据未持久？）", n)
	}
	papers2, err := repo2.ListPapersByTopic("distributed_systems")
	if err != nil {
		t.Fatal(err)
	}
	if len(papers2) != 1 || papers2[0].Title != "MapReduce" {
		t.Fatalf("重开后 ListPapersByTopic 错误: %+v", papers2)
	}
}

// TestUpsertPaperPreservesReadStatus 验证重复同步不覆盖用户阅读进度。
// 用户标记为 done 后，再次同步该论文（Upsert）应保留 done。
func TestUpsertPaperPreservesReadStatus(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()
	// 先建主题以满足外键约束
	if err := repo.UpsertTopic(Topic{ID: "t", Name: "t"}); err != nil {
		t.Fatal(err)
	}
	p := Paper{ID: "t_p1", Title: "Paper1", TopicID: "t", ReadStatus: "unread"}
	if err := repo.UpsertPaper(p); err != nil {
		t.Fatal(err)
	}
	// 用户标记已读
	if err := repo.UpdateReadStatus("t_p1", "done"); err != nil {
		t.Fatal(err)
	}
	// 再次同步（Upsert 同 id，ReadStatus 字段为 unread 但不应覆盖）
	p.ReadStatus = "unread" // 同步写入的默认值
	if err := repo.UpsertPaper(p); err != nil {
		t.Fatal(err)
	}
	got, err := repo.GetPaper("t_p1")
	if err != nil {
		t.Fatal(err)
	}
	if got.ReadStatus != "done" {
		t.Errorf("重复同步不应覆盖阅读进度，实际 read_status=%q", got.ReadStatus)
	}
}

// TestUpdatePaperCount 验证论文计数刷新。
func TestUpdatePaperCount(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()
	_ = repo.UpsertTopic(Topic{ID: "t", Name: "t"})
	_ = repo.UpsertPaper(Paper{ID: "t_p1", Title: "P1", TopicID: "t"})
	_ = repo.UpsertPaper(Paper{ID: "t/p2", Title: "P2", TopicID: "t"})
	if err := repo.UpdatePaperCount("t"); err != nil {
		t.Fatal(err)
	}
	tp, err := repo.GetTopic("t")
	if err != nil {
		t.Fatal(err)
	}
	if tp.PaperCount != 2 {
		t.Errorf("PaperCount: got %d want 2", tp.PaperCount)
	}
}
