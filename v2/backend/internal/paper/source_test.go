// Package paper 的 SourceManager 测试。
//
// 文件概述：source_test.go 用 mock PaperSource 验证 SourceManager 的并发同步行为：
//   - SyncAll 返回每个源的结果，单源失败不影响其他源；
//   - 成功源的论文正确幂等落库；
//   - sources 表的 last_synced_at / sync_count 正确更新；
//   - SyncOne 可单独同步指定源，未注册源返回错误；
//   - 重复同步不产生重复行（幂等）。
package paper

import (
	"context"
	"errors"
	"testing"
)

// mockSource 是 PaperSource 的测试替身：成功源返回 metas，失败源返回 err。
type mockSource struct {
	id    string
	name  string
	metas []PaperMeta
	err   error
}

func (m *mockSource) ID() string   { return m.id }
func (m *mockSource) Name() string { return m.name }
func (m *mockSource) Sync(ctx context.Context) ([]PaperMeta, error) {
	if m.err != nil {
		return nil, m.err
	}
	return m.metas, nil
}
func (m *mockSource) TestConnection() error { return m.err }

// TestSourceManagerSyncAll 验证并发同步：成功与失败源共存，互不影响。
func TestSourceManagerSyncAll(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	ok := &mockSource{
		id:   "arxiv",
		name: "arXiv",
		metas: []PaperMeta{
			{
				Title:   "Attention Is All You Need",
				Authors: "Vaswani et al.",
				Year:    2017,
				ArxivID: "1706.03762",
				Source:  "arxiv",
				PDFURL:  "https://arxiv.org/pdf/1706.03762",
			},
		},
	}
	bad := &mockSource{
		id:   "broken",
		name: "故障源",
		err:  errors.New("connection refused"),
	}

	mgr := NewSourceManager(repo)
	mgr.Register(ok)
	mgr.Register(bad)

	results := mgr.SyncAll(context.Background())
	if len(results) != 2 {
		t.Fatalf("SyncAll 结果数: got %d want 2", len(results))
	}

	// 定位各源结果
	var okRes, badRes *SyncResult
	for i := range results {
		switch results[i].SourceID {
		case "arxiv":
			okRes = &results[i]
		case "broken":
			badRes = &results[i]
		}
	}
	if okRes == nil || !okRes.Success || okRes.Count != 1 {
		t.Errorf("arxiv 源应成功且 Count=1: %+v", okRes)
	}
	if badRes == nil || badRes.Success || badRes.Error == "" {
		t.Errorf("broken 源应失败且带错误信息: %+v", badRes)
	}

	// 验证成功的源数据正确写入数据库
	p, err := repo.GetPaper("arxiv_1706.03762")
	if err != nil {
		t.Fatalf("GetPaper 失败: %v", err)
	}
	if p == nil {
		t.Fatal("成功源的论文未写入数据库")
	}
	if p.Title != "Attention Is All You Need" {
		t.Errorf("Title: got %q want %q", p.Title, "Attention Is All You Need")
	}
	if p.PDFURL != "https://arxiv.org/pdf/1706.03762" {
		t.Errorf("PDFURL: got %q want https://arxiv.org/pdf/1706.03762", p.PDFURL)
	}

	// 验证 sources 表更新（成功源）
	src, err := repo.GetSource("arxiv")
	if err != nil {
		t.Fatalf("GetSource(arxiv) 失败: %v", err)
	}
	if src == nil {
		t.Fatal("sources 表未记录 arxiv 源")
	}
	if src.SyncCount != 1 {
		t.Errorf("arxiv SyncCount: got %d want 1", src.SyncCount)
	}
	if src.LastSyncedAt == "" {
		t.Error("arxiv LastSyncedAt 不应为空")
	}

	// 验证失败的源不影响成功的源：失败源未写入 sources 表（SyncAll 中失败分支不调用 UpdateSourceSync）
	badSrc, err := repo.GetSource("broken")
	if err != nil {
		t.Fatalf("GetSource(broken) 失败: %v", err)
	}
	if badSrc != nil {
		t.Error("失败源不应写入 sources 表")
	}

	// ListSources 返回注册的全部源
	if got := len(mgr.ListSources()); got != 2 {
		t.Errorf("ListSources 长度: got %d want 2", got)
	}
}

// TestSourceManagerSyncOne 验证单源同步与未注册源的错误返回。
func TestSourceManagerSyncOne(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	ok := &mockSource{
		id:   "openalex",
		name: "OpenAlex",
		metas: []PaperMeta{
			{Title: "BERT", Authors: "Devlin et al.", Year: 2019,
				DOI: "10.18653/v1/N19-1423", Source: "openalex"},
		},
	}
	mgr := NewSourceManager(repo)
	mgr.Register(ok)

	// 同步已注册源
	res, err := mgr.SyncOne(context.Background(), "openalex")
	if err != nil {
		t.Fatalf("SyncOne 失败: %v", err)
	}
	if !res.Success || res.Count != 1 {
		t.Errorf("openalex 应成功且 Count=1: %+v", res)
	}
	// doi 优先级生成 id：doi_{doi}
	p, _ := repo.GetPaper("doi_10.18653/v1/N19-1423")
	if p == nil || p.Title != "BERT" {
		t.Errorf("BERT 论文未正确落库: %+v", p)
	}

	// 同步未注册源应返回错误
	if _, err := mgr.SyncOne(context.Background(), "ghost"); err == nil {
		t.Error("未注册源应返回错误")
	}
}

// TestSourceManagerIdempotent 验证重复同步不产生重复行。
func TestSourceManagerIdempotent(t *testing.T) {
	repo, db, _ := openTestRepo(t)
	defer db.Close()

	ok := &mockSource{
		id:   "arxiv",
		name: "arXiv",
		metas: []PaperMeta{
			{Title: "GPT-4 Technical Report", ArxivID: "2303.08774", Source: "arxiv"},
		},
	}
	mgr := NewSourceManager(repo)
	mgr.Register(ok)

	mgr.SyncAll(context.Background())
	mgr.SyncAll(context.Background())

	n, _ := repo.CountPapers()
	if n != 1 {
		t.Errorf("重复同步后论文数应为 1（幂等），实际 %d", n)
	}
}
