// Package server 的 HTTP 契约测试。
//
// 文件概述：server_test.go 用 httptest 验证各 /api 路由的契约：
//   - GET /api/health 返回 200 且 data_dir 为绝对路径（M1 验收点）；
//   - GET /api/papers 空库返回 papers=[]；
//   - GET /api/papers/:id 不存在返回 404；
//   - PATCH /api/papers/:id/status 更新生效且校验非法值；
//   - GET /api/sources 空库返回 []；
//   - POST /api/sources/sync 全量同步空源管理器返回 results=[]。
//
// 测试用临时 SQLite 库（store.Open + Migrate），不依赖真实网络。
package server

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"nuclear-ox-v2/backend/internal/config"
	"nuclear-ox-v2/backend/internal/paper"
	"nuclear-ox-v2/backend/internal/store"
)

// newTestServer 构造一个指向临时库的测试 Server，返回 Server 与 httptest 实例。
// t.Cleanup 负责关闭 httptest 与 db。
func newTestServer(t *testing.T) (*Server, *httptest.Server) {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")
	db, err := store.Open(dbPath)
	if err != nil {
		t.Fatalf("store.Open 失败: %v", err)
	}
	if err := store.Migrate(db); err != nil {
		db.Close()
		t.Fatalf("store.Migrate 失败: %v", err)
	}
	cfg := &config.Config{
		DataDir: dir,
		DBPath:  dbPath,
		LogDir:  filepath.Join(dir, "logs"),
		Server:  config.ServerConfig{Host: "127.0.0.1", Port: 0},
		LLM: config.LLMConfig{
			Provider: "deepseek", Model: "deepseek-chat",
			APIBase: "http://x", APIKey: "k", Timeout: 10,
		},
		PaperSource: config.PaperSourceConfig{},
	}
	s := New(cfg, db)
	ts := httptest.NewServer(s.Handler())
	t.Cleanup(func() { ts.Close(); db.Close() })
	return s, ts
}

// readBody 读取并返回完整响应体。
func readBody(t *testing.T, r io.Reader) []byte {
	t.Helper()
	b, err := io.ReadAll(r)
	if err != nil {
		t.Fatalf("读取响应体失败: %v", err)
	}
	return b
}

// doGet 发起 GET 请求，返回状态码与响应体。
func doGet(t *testing.T, ts *httptest.Server, path string) (int, []byte) {
	t.Helper()
	resp, err := http.Get(ts.URL + path)
	if err != nil {
		t.Fatalf("GET %s 失败: %v", path, err)
	}
	defer resp.Body.Close()
	return resp.StatusCode, readBody(t, resp.Body)
}

// doJSON 发起带 JSON body 的请求，返回状态码与响应体。body 为 nil 时发送空 body。
func doJSON(t *testing.T, ts *httptest.Server, method, path string, body []byte) (int, []byte) {
	t.Helper()
	var reader io.Reader
	if body != nil {
		reader = bytes.NewReader(body)
	}
	req, err := http.NewRequest(method, ts.URL+path, reader)
	if err != nil {
		t.Fatalf("构造请求失败: %v", err)
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("%s %s 失败: %v", method, path, err)
	}
	defer resp.Body.Close()
	return resp.StatusCode, readBody(t, resp.Body)
}

// TestHealthReturnsAbsDataDir 是 M1 验收测试：健康检查必须返回绝对路径 data_dir。
func TestHealthReturnsAbsDataDir(t *testing.T) {
	_, ts := newTestServer(t)

	code, body := doGet(t, ts, "/api/health")
	if code != 200 {
		t.Fatalf("health 状态码: %d, body: %s", code, body)
	}
	var h healthResponse
	if err := json.Unmarshal(body, &h); err != nil {
		t.Fatalf("解析 health 响应失败: %v, body: %s", err, body)
	}
	if h.Status != "ok" {
		t.Errorf("status: got %q want ok", h.Status)
	}
	// 核心验收点：data_dir 必须是绝对路径（痛点②修复可视验证）
	if !filepath.IsAbs(h.DataDir) {
		t.Errorf("data_dir 应为绝对路径，实际: %q", h.DataDir)
	}
	if !filepath.IsAbs(h.DBPath) {
		t.Errorf("db_path 应为绝对路径，实际: %q", h.DBPath)
	}
	if h.PaperCount != 0 {
		t.Errorf("空库 paper_count 应为 0，实际 %d", h.PaperCount)
	}
}

// TestListPapersEmpty 验证空库返回 papers=[] 而非 null。
func TestListPapersEmpty(t *testing.T) {
	_, ts := newTestServer(t)
	code, body := doGet(t, ts, "/api/papers")
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	var resp listPapersResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if resp.Papers == nil {
		t.Errorf("空库 papers 应为 [] 而非 null")
	}
	if resp.Total != 0 {
		t.Errorf("空库 total 应为 0，实际 %d", resp.Total)
	}
}

// TestListPapersWithFilter 验证写入论文后可按 source 过滤列出。
func TestListPapersWithFilter(t *testing.T) {
	s, ts := newTestServer(t)
	// 用 UpsertPaperMeta 写两篇不同 source 的论文
	if err := s.repo.UpsertPaperMeta(paper.PaperMeta{
		Title: "Paper A", ArxivID: "0001.00001", Source: "arxiv",
	}); err != nil {
		t.Fatal(err)
	}
	if err := s.repo.UpsertPaperMeta(paper.PaperMeta{
		Title: "Paper B", DOI: "10.1/b", Source: "openalex",
	}); err != nil {
		t.Fatal(err)
	}

	// 全量
	code, body := doGet(t, ts, "/api/papers")
	if code != 200 {
		t.Fatalf("全量状态码: %d, body: %s", code, body)
	}
	var resp listPapersResponse
	json.Unmarshal(body, &resp)
	if resp.Total != 2 {
		t.Errorf("全量 total: got %d want 2", resp.Total)
	}

	// 按 source 过滤
	code, body = doGet(t, ts, "/api/papers?source=arxiv")
	if code != 200 {
		t.Fatalf("过滤状态码: %d", code)
	}
	json.Unmarshal(body, &resp)
	if resp.Total != 1 {
		t.Errorf("arxiv 过滤 total: got %d want 1", resp.Total)
	}
	if len(resp.Papers) != 1 || resp.Papers[0].Title != "Paper A" {
		t.Errorf("arxiv 过滤结果: %+v", resp.Papers)
	}
}

// TestGetPaperNotFound 验证不存在论文返回 404。
func TestGetPaperNotFound(t *testing.T) {
	_, ts := newTestServer(t)
	code, _ := doGet(t, ts, "/api/papers/nope")
	if code != 404 {
		t.Errorf("不存在论文应 404，实际 %d", code)
	}
}

// TestGetPaperDetail 验证论文详情含阅读统计。
func TestGetPaperDetail(t *testing.T) {
	s, ts := newTestServer(t)
	if err := s.repo.UpsertPaperMeta(paper.PaperMeta{
		Title: "Detail Paper", ArxivID: "0002.00001", Source: "arxiv",
	}); err != nil {
		t.Fatal(err)
	}
	code, body := doGet(t, ts, "/api/papers/arxiv_0002.00001")
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	var detail paper.PaperDetail
	if err := json.Unmarshal(body, &detail); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if detail.Title != "Detail Paper" {
		t.Errorf("Title: got %q want Detail Paper", detail.Title)
	}
	if detail.ReadingStats.Count != 0 {
		t.Errorf("空库阅读次数应为 0，实际 %d", detail.ReadingStats.Count)
	}
}

// TestUpdatePaperStatus 验证阅读状态更新生效。
func TestUpdatePaperStatus(t *testing.T) {
	s, ts := newTestServer(t)
	if err := s.repo.UpsertTopic(paper.Topic{ID: "t", Name: "t"}); err != nil {
		t.Fatal(err)
	}
	if err := s.repo.UpsertPaper(paper.Paper{ID: "t_p1", Title: "P1", TopicID: "t"}); err != nil {
		t.Fatal(err)
	}
	code, _ := doJSON(t, ts, http.MethodPatch, "/api/papers/t_p1/status",
		[]byte(`{"status":"done"}`))
	if code != 200 {
		t.Fatalf("PATCH 状态码: %d", code)
	}
	p, err := s.repo.GetPaper("t_p1")
	if err != nil {
		t.Fatal(err)
	}
	if p.ReadStatus != "done" {
		t.Errorf("read_status: got %q want done", p.ReadStatus)
	}
}

// TestUpdatePaperStatusRejectsInvalid 验证非法状态值被拒（400）。
func TestUpdatePaperStatusRejectsInvalid(t *testing.T) {
	s, ts := newTestServer(t)
	_ = s.repo.UpsertTopic(paper.Topic{ID: "t", Name: "t"})
	_ = s.repo.UpsertPaper(paper.Paper{ID: "t_p1", Title: "P1", TopicID: "t"})
	code, _ := doJSON(t, ts, http.MethodPatch, "/api/papers/t_p1/status",
		[]byte(`{"status":"bogus"}`))
	if code != 400 {
		t.Errorf("非法状态应 400，实际 %d", code)
	}
}

// TestReadingStartEnd 验证开始/结束阅读流程。
func TestReadingStartEnd(t *testing.T) {
	s, ts := newTestServer(t)
	if err := s.repo.UpsertPaperMeta(paper.PaperMeta{
		Title: "Reading Paper", ArxivID: "0003.00001", Source: "arxiv",
	}); err != nil {
		t.Fatal(err)
	}

	// 开始阅读
	code, body := doJSON(t, ts, http.MethodPost, "/api/papers/arxiv_0003.00001/reading-start", nil)
	if code != 200 {
		t.Fatalf("reading-start 状态码: %d, body: %s", code, body)
	}
	var start struct{ HistoryID string `json:"history_id"` }
	if err := json.Unmarshal(body, &start); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if start.HistoryID == "" {
		t.Fatal("history_id 不应为空")
	}

	// 验证状态已置为 reading
	p, _ := s.repo.GetPaper("arxiv_0003.00001")
	if p.ReadStatus != "reading" {
		t.Errorf("read_status: got %q want reading", p.ReadStatus)
	}

	// 结束阅读
	code, body = doJSON(t, ts, http.MethodPost, "/api/papers/arxiv_0003.00001/reading-end",
		[]byte(`{"history_id":"`+start.HistoryID+`"}`))
	if code != 200 {
		t.Fatalf("reading-end 状态码: %d, body: %s", code, body)
	}

	// 验证阅读统计已更新
	detail, _ := s.repo.GetPaperWithHistory("arxiv_0003.00001")
	if detail.ReadingStats.Count != 1 {
		t.Errorf("阅读次数: got %d want 1", detail.ReadingStats.Count)
	}
	if detail.LastReadAt == "" {
		t.Errorf("last_read_at 不应为空")
	}
}

// TestListSourcesEmpty 验证空库返回 []。
func TestListSourcesEmpty(t *testing.T) {
	_, ts := newTestServer(t)
	code, body := doGet(t, ts, "/api/sources")
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	if string(body) != "[]" {
		t.Errorf("空库 sources 应返回 []，实际: %s", body)
	}
}

// TestSyncSourcesAll 验证全量同步返回 results 数组。
func TestSyncSourcesAll(t *testing.T) {
	s, ts := newTestServer(t)
	// 替换为空源管理器，SyncAll 返回空数组
	s.setSourceManager(paper.NewSourceManager(s.repo))

	code, body := doJSON(t, ts, http.MethodPost, "/api/sources/sync", nil)
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	var resp struct {
		Results []paper.SyncResult `json:"results"`
	}
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if resp.Results == nil {
		t.Error("results 不应为 nil")
	}
}

// TestRelatedPapers 验证相关论文按 sub_domain 返回。
func TestRelatedPapers(t *testing.T) {
	s, ts := newTestServer(t)
	// 写两篇同 sub_domain 的论文 + 一篇不同 sub_domain
	_ = s.repo.UpsertPaperMeta(paper.PaperMeta{Title: "A", ArxivID: "0004.00001", Source: "arxiv"})
	// 设置 sub_domain
	_, _ = s.db.Exec(`UPDATE papers SET sub_domain='llm' WHERE id='arxiv_0004.00001'`)
	_ = s.repo.UpsertPaperMeta(paper.PaperMeta{Title: "B", ArxivID: "0004.00002", Source: "arxiv"})
	_, _ = s.db.Exec(`UPDATE papers SET sub_domain='llm' WHERE id='arxiv_0004.00002'`)
	_ = s.repo.UpsertPaperMeta(paper.PaperMeta{Title: "C", ArxivID: "0004.00003", Source: "arxiv"})
	_, _ = s.db.Exec(`UPDATE papers SET sub_domain='ml' WHERE id='arxiv_0004.00003'`)

	code, body := doGet(t, ts, "/api/papers/arxiv_0004.00001/related")
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	var papers []paper.Paper
	if err := json.Unmarshal(body, &papers); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if len(papers) != 1 || papers[0].Title != "B" {
		t.Errorf("相关论文应为 1 篇 (B)，实际: %+v", papers)
	}
}
