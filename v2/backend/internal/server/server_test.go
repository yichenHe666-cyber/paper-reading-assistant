// Package server 的 HTTP 契约测试。
//
// 文件概述：server_test.go 用 httptest 验证各 /api 路由的契约：
//   - GET /api/health 返回 200 且 data_dir 为绝对路径（M1 验收点）；
//   - GET /api/topics 空库返回 []；
//   - 主题写入后可列出；
//   - GET /api/papers/:id 不存在返回 404；
//   - PATCH /api/papers/:id/status 更新生效且校验非法值；
//   - POST /api/sync 走 mock GitHub，同步结果正确；
//   - POST /api/migrate-legacy 返回结构正确。
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
		GitHub: config.GitHubConfig{DefaultRepo: "pwl/papers"},
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

// TestListTopicsEmpty 验证空库返回 [] 而非 null（前端友好）。
func TestListTopicsEmpty(t *testing.T) {
	_, ts := newTestServer(t)
	code, body := doGet(t, ts, "/api/topics")
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	if string(body) != "[]" {
		t.Errorf("空库 topics 应返回 []，实际: %s", body)
	}
}

// TestCreateTopicAndList 验证写入主题后可列出。
func TestCreateTopicAndList(t *testing.T) {
	s, ts := newTestServer(t)
	if err := s.repo.UpsertTopic(paper.Topic{ID: "ds", Name: "distributed_systems"}); err != nil {
		t.Fatal(err)
	}
	code, body := doGet(t, ts, "/api/topics")
	if code != 200 {
		t.Fatalf("状态码: %d", code)
	}
	var topics []paper.Topic
	if err := json.Unmarshal(body, &topics); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if len(topics) != 1 || topics[0].ID != "ds" {
		t.Errorf("topics: %+v", topics)
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

// TestSyncEndpoint 验证同步端点走 mock GitHub 并返回正确结果。
func TestSyncEndpoint(t *testing.T) {
	s, ts := newTestServer(t)
	// 起 mock GitHub API
	ghSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		switch r.URL.Path {
		case "/repos/pwl/papers/contents":
			w.Write([]byte(`[{"name":"distributed_systems","path":"distributed_systems","type":"dir"}]`))
		case "/repos/pwl/papers/contents/distributed_systems":
			w.Write([]byte(`[{"name":"mapreduce.pdf","path":"distributed_systems/mapreduce.pdf","type":"file","download_url":"http://raw/mr.pdf"}]`))
		default:
			w.WriteHeader(404)
		}
	}))
	defer ghSrv.Close()
	// 注入指向 mock 的 GitHub 客户端
	s.setGitHubClient(paper.NewGitHubClientWithBaseURL("", ghSrv.URL))

	// 触发同步（空 body 用默认仓库 pwl/papers）
	code, body := doJSON(t, ts, http.MethodPost, "/api/sync", nil)
	if code != 200 {
		t.Fatalf("sync 状态码: %d, body: %s", code, body)
	}
	var resp syncResultResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if resp.TopicsAdded != 1 || resp.PapersAdded != 1 {
		t.Errorf("sync 结果: topics=%d papers=%d", resp.TopicsAdded, resp.PapersAdded)
	}
	// 验证论文确实落库
	n, _ := s.repo.CountPapers()
	if n != 1 {
		t.Errorf("同步后论文数应为 1，实际 %d", n)
	}
}

// TestMigrateLegacyEndpoint 验证迁移端点返回结构正确（无旧库时 found=0, results=[]）。
func TestMigrateLegacyEndpoint(t *testing.T) {
	_, ts := newTestServer(t)
	code, body := doJSON(t, ts, http.MethodPost, "/api/migrate-legacy", nil)
	if code != 200 {
		t.Fatalf("migrate 状态码: %d, body: %s", code, body)
	}
	var resp migrateLegacyResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if resp.Results == nil {
		t.Error("results 不应为 nil（应为空数组）")
	}
}
