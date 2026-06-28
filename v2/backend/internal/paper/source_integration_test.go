// Package paper 的 SourceManager 端到端集成测试。
//
// 文件概述：source_integration_test.go 用 :memory: SQLite + 真 Repository + mock PaperSource
// 验证论文同步流程的稳定性与隔离性：
//   - 重复同步幂等不重复落库（B1）；
//   - 单源失败/panic 不影响其他源（B2）；
//   - 未注册源 SyncOne 返回 nil + error（B3）；
//   - 已注册源 SyncOne 成功（B4）；
//   - sources 表的 sync_count / last_synced_at 正确追踪（B5）；
//   - UpsertPaperMeta 不覆盖用户阅读状态（B6）。
//
// 与 source_test.go 互补：本文件聚焦端到端落库与隔离场景，使用独立的 extMockSource
// 支持成功/失败/panic 三种模式。
package paper

import (
	"context"
	"errors"
	"strings"
	"testing"
)

// extMockSource 是 SourceManager 集成测试用的 mock PaperSource。
// 与 source_test.go 的 mockSource 互补：本类型额外支持 panic 模式，用于测试 recover 隔离。
//
// 字段：
//   - metas 非 nil 且无 syncErr/panic 时，Sync 返回 metas；
//   - syncErr 非 nil 时，Sync 返回此 error；
//   - panic 为 true 时，Sync 触发 panic（由 SourceManager 的 recover 捕获）。
type extMockSource struct {
	id      string
	name    string
	metas   []PaperMeta
	syncErr error
	panic   bool
}

func (m *extMockSource) ID() string   { return m.id }
func (m *extMockSource) Name() string { return m.name }
func (m *extMockSource) TestConnection() error { return nil }
func (m *extMockSource) Sync(ctx context.Context) ([]PaperMeta, error) {
	if m.panic {
		panic("mock panic")
	}
	if m.syncErr != nil {
		return nil, m.syncErr
	}
	return m.metas, nil
}

// B1. TestSyncAllIdempotent 验证重复同步幂等不重复落库。
func TestSyncAllIdempotent(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	src := &extMockSource{
		id:   "arxiv",
		name: "arXiv",
		metas: []PaperMeta{
			{Title: "Paper 1", ArxivID: "1001.00001", Source: "arxiv"},
			{Title: "Paper 2", ArxivID: "1001.00002", Source: "arxiv"},
			{Title: "Paper 3", ArxivID: "1001.00003", Source: "arxiv"},
		},
	}
	mgr := NewSourceManager(repo)
	mgr.Register(src)

	// 第一次同步
	results1 := mgr.SyncAll(context.Background())
	if len(results1) != 1 {
		t.Fatalf("第一次 SyncAll 结果数: got %d want 1", len(results1))
	}
	if !results1[0].Success || results1[0].Count != 3 {
		t.Errorf("第一次 SyncAll: success=%v count=%d, want success=true count=3",
			results1[0].Success, results1[0].Count)
	}
	n1, _ := repo.CountPapers()
	if n1 != 3 {
		t.Errorf("第一次同步后论文数: got %d want 3", n1)
	}

	// 第二次同步（幂等，不应产生重复行）
	results2 := mgr.SyncAll(context.Background())
	if len(results2) != 1 {
		t.Fatalf("第二次 SyncAll 结果数: got %d want 1", len(results2))
	}
	if !results2[0].Success || results2[0].Count != 3 {
		t.Errorf("第二次 SyncAll: success=%v count=%d, want success=true count=3",
			results2[0].Success, results2[0].Count)
	}
	n2, _ := repo.CountPapers()
	if n2 != 3 {
		t.Errorf("第二次同步后论文数: got %d want 3（幂等不重复）", n2)
	}
}

// B2. TestSyncAllSingleSourceFailureIsolation 验证单源失败/panic 不影响其他源。
func TestSyncAllSingleSourceFailureIsolation(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	srcA := &extMockSource{
		id:   "sourceA",
		name: "Source A",
		metas: []PaperMeta{
			{Title: "A1", ArxivID: "2001.00001", Source: "arxiv"},
			{Title: "A2", ArxivID: "2001.00002", Source: "arxiv"},
		},
	}
	srcB := &extMockSource{
		id:      "sourceB",
		name:    "Source B",
		syncErr: errors.New("sync failed: connection refused"),
	}
	srcC := &extMockSource{
		id:    "sourceC",
		name:  "Source C",
		panic: true,
	}
	srcD := &extMockSource{
		id:   "sourceD",
		name: "Source D",
		metas: []PaperMeta{
			{Title: "D1", ArxivID: "2001.00003", Source: "arxiv"},
			{Title: "D2", ArxivID: "2001.00004", Source: "arxiv"},
			{Title: "D3", ArxivID: "2001.00005", Source: "arxiv"},
		},
	}
	mgr := NewSourceManager(repo)
	mgr.Register(srcA)
	mgr.Register(srcB)
	mgr.Register(srcC)
	mgr.Register(srcD)

	results := mgr.SyncAll(context.Background())
	if len(results) != 4 {
		t.Fatalf("SyncAll 结果数: got %d want 4", len(results))
	}

	// 按 source ID 索引结果
	resMap := make(map[string]SyncResult, len(results))
	for _, r := range results {
		resMap[r.SourceID] = r
	}

	// A 和 D 成功
	if !resMap["sourceA"].Success || resMap["sourceA"].Count != 2 {
		t.Errorf("sourceA 应成功且 count=2: %+v", resMap["sourceA"])
	}
	if !resMap["sourceD"].Success || resMap["sourceD"].Count != 3 {
		t.Errorf("sourceD 应成功且 count=3: %+v", resMap["sourceD"])
	}

	// B 失败且 error 含 "sync failed"
	if resMap["sourceB"].Success {
		t.Errorf("sourceB 应失败")
	}
	if !strings.Contains(resMap["sourceB"].Error, "sync failed") {
		t.Errorf("sourceB error 应含 'sync failed': %q", resMap["sourceB"].Error)
	}

	// C 失败且 error 含 "panic"（被 recover 捕获）
	if resMap["sourceC"].Success {
		t.Errorf("sourceC 应失败")
	}
	if !strings.Contains(resMap["sourceC"].Error, "panic") {
		t.Errorf("sourceC error 应含 'panic': %q", resMap["sourceC"].Error)
	}

	// A 和 D 的论文都已入库（共 5 篇），B 和 C 的失败不影响它们
	n, _ := repo.CountPapers()
	if n != 5 {
		t.Errorf("入库论文数: got %d want 5（A=2 + D=3）", n)
	}
	for _, id := range []string{
		"arxiv_2001.00001", "arxiv_2001.00002", // A
		"arxiv_2001.00003", "arxiv_2001.00004", "arxiv_2001.00005", // D
	} {
		p, err := repo.GetPaper(id)
		if err != nil || p == nil {
			t.Errorf("论文 %s 应已入库: err=%v p=%v", id, err, p)
		}
	}
}

// B3. TestSyncOneNotFound 验证未注册源 SyncOne 返回 nil + error。
func TestSyncOneNotFound(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	mgr := NewSourceManager(repo)
	res, err := mgr.SyncOne(context.Background(), "不存在")
	if res != nil {
		t.Errorf("未注册源应返回 nil result, got %+v", res)
	}
	if err == nil {
		t.Error("未注册源应返回 error")
	}
}

// B4. TestSyncOneSuccess 验证已注册源 SyncOne 成功。
func TestSyncOneSuccess(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	src := &extMockSource{
		id:   "openalex",
		name: "OpenAlex",
		metas: []PaperMeta{
			{Title: "BERT", DOI: "10.18653/v1/N19-1423", Source: "openalex"},
			{Title: "GPT", DOI: "10.18653/v1/N19-1424", Source: "openalex"},
		},
	}
	mgr := NewSourceManager(repo)
	mgr.Register(src)

	res, err := mgr.SyncOne(context.Background(), "openalex")
	if err != nil {
		t.Fatalf("SyncOne 失败: %v", err)
	}
	if res == nil {
		t.Fatal("res 不应为 nil")
	}
	if !res.Success {
		t.Errorf("应成功: %+v", res)
	}
	if res.Count != 2 {
		t.Errorf("count: got %d want 2", res.Count)
	}
}

// B5. TestUpdateSourceSyncTracking 验证 sources 表的 sync_count / last_synced_at 正确追踪。
func TestUpdateSourceSyncTracking(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	src := &extMockSource{
		id:   "arxiv",
		name: "arXiv",
		metas: []PaperMeta{
			{Title: "Paper 1", ArxivID: "3001.00001", Source: "arxiv"},
			{Title: "Paper 2", ArxivID: "3001.00002", Source: "arxiv"},
			{Title: "Paper 3", ArxivID: "3001.00003", Source: "arxiv"},
		},
	}
	mgr := NewSourceManager(repo)
	mgr.Register(src)

	// 第一次同步
	mgr.SyncAll(context.Background())

	sources, err := repo.ListSources()
	if err != nil {
		t.Fatalf("ListSources 失败: %v", err)
	}
	if len(sources) != 1 {
		t.Fatalf("sources 数: got %d want 1", len(sources))
	}
	if sources[0].SyncCount != 3 {
		t.Errorf("第一次同步后 sync_count: got %d want 3", sources[0].SyncCount)
	}
	if sources[0].LastSyncedAt == "" {
		t.Error("last_synced_at 不应为空")
	}

	// 第二次同步（mock 仍返回 3 篇）
	mgr.SyncAll(context.Background())
	sources, _ = repo.ListSources()
	if len(sources) != 1 {
		t.Fatalf("第二次同步后 sources 数: got %d want 1", len(sources))
	}
	// UpdateSourceSync 用 excluded.sync_count，第二次传入也是 3，故仍为 3
	if sources[0].SyncCount != 3 {
		t.Errorf("第二次同步后 sync_count: got %d want 3（excluded.sync_count）", sources[0].SyncCount)
	}
	if sources[0].LastSyncedAt == "" {
		t.Error("第二次同步后 last_synced_at 不应为空")
	}
}

// B6. TestUpsertPaperMetaPreservesUserState 验证重复 UpsertPaperMeta 不覆盖用户阅读状态。
func TestUpsertPaperMetaPreservesUserState(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	meta := PaperMeta{
		Title:   "User State Paper",
		ArxivID: "4001.00001",
		Source:  "arxiv",
	}
	paperID := "arxiv_4001.00001"

	// 第一次入库
	if err := repo.UpsertPaperMeta(meta); err != nil {
		t.Fatal(err)
	}

	// 手动设置用户阅读状态
	if err := repo.UpdateReadStatus(paperID, "done"); err != nil {
		t.Fatal(err)
	}
	if err := repo.UpdatePaperReadStats(paperID, 100); err != nil {
		t.Fatal(err)
	}

	// 第二次 UpsertPaperMeta（同 meta，模拟重复同步）
	if err := repo.UpsertPaperMeta(meta); err != nil {
		t.Fatal(err)
	}

	// 验证用户状态保留
	p, err := repo.GetPaper(paperID)
	if err != nil {
		t.Fatal(err)
	}
	if p == nil {
		t.Fatal("论文应存在")
	}
	if p.ReadStatus != "done" {
		t.Errorf("read_status: got %q want done（不应被同步覆盖）", p.ReadStatus)
	}
	if p.TotalReadSeconds != 100 {
		t.Errorf("total_read_seconds: got %d want 100（不应被同步覆盖）", p.TotalReadSeconds)
	}
}
