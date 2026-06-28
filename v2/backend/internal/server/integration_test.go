// Package server 的 HTTP 端到端集成测试。
//
// 文件概述：integration_test.go 用 httptest 验证论文同步/检索/阅读全流程：
//   - 健康检查返回完整状态字段（A1）；
//   - 空库列表返回标准分页结构（A2）；
//   - 分页参数正确生效（A3）；
//   - source/level/q 组合过滤（A4）；
//   - 论文详情含阅读统计、不存在返回 404（A5）；
//   - 阅读历史 start→end→统计闭环（A6）；
//   - 状态更新合法/非法校验（A7）；
//   - PDF 代理 404 路径不触发真实下载（A8）；
//   - 空源同步返回零汇总（A9）；
//   - classifier 为 nil 时分类端点返回 500（A10）。
//
// 每个测试用 newTestServer 起独立 :memory: SQLite，互不干扰。
package server

import (
	"encoding/json"
	"fmt"
	"net/http"
	"testing"

	"nuclear-ox-v2/backend/internal/paper"
)

// mustUpsertPaperMeta 插入一篇 PaperMeta，失败即终止测试。
func mustUpsertPaperMeta(t *testing.T, s *Server, meta paper.PaperMeta) {
	t.Helper()
	if err := s.repo.UpsertPaperMeta(meta); err != nil {
		t.Fatalf("UpsertPaperMeta 失败: %v", err)
	}
}

// mustSetPaperField 用 SQL 更新单篇论文的某列，失败即终止测试。
// 供 level/sub_domain 等不由 UpsertPaperMeta 维护的字段使用。
func mustSetPaperField(t *testing.T, s *Server, id, column, value string) {
	t.Helper()
	// column 为内部硬编码常量（level/sub_domain），无注入风险
	stmt := fmt.Sprintf("UPDATE papers SET %s=? WHERE id=?", column)
	if _, err := s.db.Exec(stmt, value, id); err != nil {
		t.Fatalf("设置 papers.%s 失败 (id=%s): %v", column, id, err)
	}
}

// A1. TestHealthEndpoint 验证健康检查返回完整状态字段。
func TestHealthEndpoint(t *testing.T) {
	_, ts := newTestServer(t)

	code, body := doGet(t, ts, "/api/health")
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	var h healthResponse
	if err := json.Unmarshal(body, &h); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if h.Status != "ok" {
		t.Errorf("status: got %q want ok", h.Status)
	}
	if h.DataDir == "" {
		t.Errorf("data_dir 不应为空")
	}
	if h.DBPath == "" {
		t.Errorf("db_path 不应为空")
	}
	if h.PaperCount != 0 {
		t.Errorf("paper_count: got %d want 0", h.PaperCount)
	}
	if h.TopicCount != 0 {
		t.Errorf("topic_count: got %d want 0", h.TopicCount)
	}
	if h.LLMProvider == "" {
		t.Errorf("llm_provider 不应为空")
	}
	if h.LLMModel == "" {
		t.Errorf("llm_model 不应为空")
	}
}

// A2. TestListPapersEmptyResponse 验证空库返回标准分页结构。
// 注意：与 server_test.go 的 TestListPapersEmpty 互补，本测试额外校验 page/page_size 默认值。
func TestListPapersEmptyResponse(t *testing.T) {
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
		t.Errorf("papers 应为 [] 而非 null")
	}
	if len(resp.Papers) != 0 {
		t.Errorf("papers 长度: got %d want 0", len(resp.Papers))
	}
	if resp.Total != 0 {
		t.Errorf("total: got %d want 0", resp.Total)
	}
	if resp.Page != 1 {
		t.Errorf("page: got %d want 1", resp.Page)
	}
	if resp.PageSize != 20 {
		t.Errorf("page_size: got %d want 20", resp.PageSize)
	}
}

// A3. TestListPapersPagination 验证分页参数生效。
func TestListPapersPagination(t *testing.T) {
	s, ts := newTestServer(t)
	// 插入 25 篇论文
	for i := 0; i < 25; i++ {
		mustUpsertPaperMeta(t, s, paper.PaperMeta{
			Title:   fmt.Sprintf("Paper %02d", i),
			ArxivID: fmt.Sprintf("0001.%05d", i+1),
			Source:  "arxiv",
		})
	}

	code, body := doGet(t, ts, "/api/papers?page=2&page_size=10")
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	var resp listPapersResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if len(resp.Papers) != 10 {
		t.Errorf("papers 长度: got %d want 10", len(resp.Papers))
	}
	if resp.Total != 25 {
		t.Errorf("total: got %d want 25", resp.Total)
	}
	if resp.Page != 2 {
		t.Errorf("page: got %d want 2", resp.Page)
	}
	if resp.PageSize != 10 {
		t.Errorf("page_size: got %d want 10", resp.PageSize)
	}
}

// A4. TestListPapersFiltering 验证 source/level/q 及组合过滤。
func TestListPapersFiltering(t *testing.T) {
	s, ts := newTestServer(t)
	// arxiv: 3 篇
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "Transformer Architecture", ArxivID: "0002.00001", Source: "arxiv", Abstract: "transformer model"})
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "Attention Networks", ArxivID: "0002.00002", Source: "arxiv", Abstract: "attention transformer"})
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "Graph Neural Networks", ArxivID: "0002.00003", Source: "arxiv"})
	// openalex: 2 篇
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "Deep Learning Survey", DOI: "10.1/o1", Source: "openalex"})
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "Transformer Survey", DOI: "10.1/o2", Source: "openalex"})
	// acl: 2 篇
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "NLP Paper", DOI: "10.2/a1", Source: "acl"})
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "ACL Tutorial", DOI: "10.2/a2", Source: "acl"})
	// company: 2 篇
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "GPT-4 Report", DOI: "10.3/c1", Source: "company"})
	mustUpsertPaperMeta(t, s, paper.PaperMeta{Title: "LLaMA Paper", DOI: "10.3/c2", Source: "company"})

	// 设置 level（UpsertPaperMeta 不维护 level，需 SQL 补齐）
	mustSetPaperField(t, s, "arxiv_0002.00001", "level", "beginner")
	mustSetPaperField(t, s, "arxiv_0002.00002", "level", "intermediate")
	mustSetPaperField(t, s, "arxiv_0002.00003", "level", "advanced")
	mustSetPaperField(t, s, "doi_10.1/o1", "level", "beginner")
	mustSetPaperField(t, s, "doi_10.1/o2", "level", "intermediate")
	mustSetPaperField(t, s, "doi_10.2/a1", "level", "intermediate")
	mustSetPaperField(t, s, "doi_10.2/a2", "level", "beginner")
	mustSetPaperField(t, s, "doi_10.3/c1", "level", "advanced")
	mustSetPaperField(t, s, "doi_10.3/c2", "level", "intermediate")

	var resp listPapersResponse

	// ?source=arxiv → 3 篇
	code, body := doGet(t, ts, "/api/papers?source=arxiv")
	if code != 200 {
		t.Fatalf("source=arxiv 状态码: %d, body: %s", code, body)
	}
	json.Unmarshal(body, &resp)
	if resp.Total != 3 {
		t.Errorf("source=arxiv total: got %d want 3", resp.Total)
	}
	for _, p := range resp.Papers {
		if p.Source != "arxiv" {
			t.Errorf("source=arxiv 返回了非 arxiv 源: %s", p.Source)
		}
	}

	// ?level=beginner → 3 篇
	code, body = doGet(t, ts, "/api/papers?level=beginner")
	if code != 200 {
		t.Fatalf("level=beginner 状态码: %d, body: %s", code, body)
	}
	json.Unmarshal(body, &resp)
	if resp.Total != 3 {
		t.Errorf("level=beginner total: got %d want 3", resp.Total)
	}
	for _, p := range resp.Papers {
		if p.Level != "beginner" {
			t.Errorf("level=beginner 返回了非 beginner: %s", p.Level)
		}
	}

	// ?q=transformer → 3 篇（title/abstract 模糊匹配）
	code, body = doGet(t, ts, "/api/papers?q=transformer")
	if code != 200 {
		t.Fatalf("q=transformer 状态码: %d, body: %s", code, body)
	}
	json.Unmarshal(body, &resp)
	if resp.Total != 3 {
		t.Errorf("q=transformer total: got %d want 3", resp.Total)
	}

	// 组合 ?source=arxiv&level=intermediate → 1 篇
	code, body = doGet(t, ts, "/api/papers?source=arxiv&level=intermediate")
	if code != 200 {
		t.Fatalf("source=arxiv&level=intermediate 状态码: %d, body: %s", code, body)
	}
	json.Unmarshal(body, &resp)
	if resp.Total != 1 {
		t.Errorf("source=arxiv&level=intermediate total: got %d want 1", resp.Total)
	}
}

// A5. TestGetPaperWithHistory 验证论文详情含阅读统计，不存在返回 404。
func TestGetPaperWithHistory(t *testing.T) {
	s, ts := newTestServer(t)
	mustUpsertPaperMeta(t, s, paper.PaperMeta{
		Title:   "Detail Paper",
		ArxivID: "0003.00001",
		Source:  "arxiv",
	})

	// 存在的论文
	code, body := doGet(t, ts, "/api/papers/arxiv_0003.00001")
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
		t.Errorf("reading_stats.count: got %d want 0", detail.ReadingStats.Count)
	}
	if detail.ReadingStats.TotalSeconds != 0 {
		t.Errorf("reading_stats.total_seconds: got %d want 0", detail.ReadingStats.TotalSeconds)
	}
	if detail.ReadingStats.LastReadAt != "" {
		t.Errorf("reading_stats.last_read_at: got %q want empty", detail.ReadingStats.LastReadAt)
	}

	// 不存在的 id 返回 404
	code, _ = doGet(t, ts, "/api/papers/nonexistent_id")
	if code != 404 {
		t.Errorf("不存在论文应 404，实际 %d", code)
	}
}

// A6. TestReadingHistoryFlow 验证端到端阅读历史：start → end → 统计。
func TestReadingHistoryFlow(t *testing.T) {
	s, ts := newTestServer(t)
	mustUpsertPaperMeta(t, s, paper.PaperMeta{
		Title:   "Reading Flow Paper",
		ArxivID: "0004.00001",
		Source:  "arxiv",
	})

	// 开始阅读
	code, body := doJSON(t, ts, http.MethodPost, "/api/papers/arxiv_0004.00001/reading-start", nil)
	if code != 200 {
		t.Fatalf("reading-start 状态码: %d, body: %s", code, body)
	}
	var start struct {
		HistoryID string `json:"history_id"`
	}
	if err := json.Unmarshal(body, &start); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if start.HistoryID == "" {
		t.Fatal("history_id 不应为空")
	}

	// 结束阅读
	endBody := fmt.Sprintf(`{"history_id":%q}`, start.HistoryID)
	code, body = doJSON(t, ts, http.MethodPost, "/api/papers/arxiv_0004.00001/reading-end", []byte(endBody))
	if code != 200 {
		t.Fatalf("reading-end 状态码: %d, body: %s", code, body)
	}

	// 验证阅读统计已更新
	code, body = doGet(t, ts, "/api/papers/arxiv_0004.00001")
	if code != 200 {
		t.Fatalf("GET paper 状态码: %d, body: %s", code, body)
	}
	var detail paper.PaperDetail
	if err := json.Unmarshal(body, &detail); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if detail.ReadingStats.Count != 1 {
		t.Errorf("reading_stats.count: got %d want 1", detail.ReadingStats.Count)
	}
	if detail.ReadingStats.TotalSeconds < 0 {
		t.Errorf("reading_stats.total_seconds: got %d want >=0", detail.ReadingStats.TotalSeconds)
	}
}

// A7. TestUpdatePaperStatusFlow 验证状态更新合法/非法校验。
// 注意：与 server_test.go 的 TestUpdatePaperStatus 互补，本测试额外校验响应体与非法值。
func TestUpdatePaperStatusFlow(t *testing.T) {
	s, ts := newTestServer(t)
	mustUpsertPaperMeta(t, s, paper.PaperMeta{
		Title:   "Status Paper",
		ArxivID: "0005.00001",
		Source:  "arxiv",
	})

	// 合法 status → 200 + {id, status}
	code, body := doJSON(t, ts, http.MethodPatch, "/api/papers/arxiv_0005.00001/status",
		[]byte(`{"status":"reading"}`))
	if code != 200 {
		t.Fatalf("合法 status 状态码: %d, body: %s", code, body)
	}
	var resp struct {
		ID     string `json:"id"`
		Status string `json:"status"`
	}
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if resp.ID != "arxiv_0005.00001" {
		t.Errorf("id: got %q want arxiv_0005.00001", resp.ID)
	}
	if resp.Status != "reading" {
		t.Errorf("status: got %q want reading", resp.Status)
	}

	// 非法 status → 400
	code, _ = doJSON(t, ts, http.MethodPatch, "/api/papers/arxiv_0005.00001/status",
		[]byte(`{"status":"bogus"}`))
	if code != 400 {
		t.Errorf("非法 status 应 400，实际 %d", code)
	}
}

// A8. TestProxyPaperPDFNotFound 验证无 pdf_url 或论文不存在时返回 404，不触发真实下载。
func TestProxyPaperPDFNotFound(t *testing.T) {
	s, ts := newTestServer(t)
	// 论文存在但无 pdf_url（UpsertPaperMeta 留空 PDFURL）
	mustUpsertPaperMeta(t, s, paper.PaperMeta{
		Title:   "No PDF Paper",
		ArxivID: "0006.00001",
		Source:  "arxiv",
	})

	// 无 pdf_url → 404
	code, _ := doGet(t, ts, "/api/papers/arxiv_0006.00001/pdf")
	if code != 404 {
		t.Errorf("无 pdf_url 应 404，实际 %d", code)
	}

	// 不存在的 paper id → 404
	code, _ = doGet(t, ts, "/api/papers/nonexistent_id/pdf")
	if code != 404 {
		t.Errorf("不存在论文应 404，实际 %d", code)
	}
}

// A9. TestSyncSourcesEmpty 验证空源管理器同步返回零汇总。
func TestSyncSourcesEmpty(t *testing.T) {
	s, ts := newTestServer(t)
	// 注入空 SourceManager
	s.setSourceManager(paper.NewSourceManager(s.repo))

	code, body := doJSON(t, ts, http.MethodPost, "/api/sources/sync", nil)
	if code != 200 {
		t.Fatalf("状态码: %d, body: %s", code, body)
	}
	var resp syncSourcesResponse
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if resp.TotalSources != 0 {
		t.Errorf("total_sources: got %d want 0", resp.TotalSources)
	}
	if resp.SuccessCount != 0 {
		t.Errorf("success_count: got %d want 0", resp.SuccessCount)
	}
	if resp.FailedCount != 0 {
		t.Errorf("failed_count: got %d want 0", resp.FailedCount)
	}
	if resp.TotalPapers != 0 {
		t.Errorf("total_papers: got %d want 0", resp.TotalPapers)
	}
}

// A10. TestClassifyWithoutClassifier 验证 classifier 为 nil 时分类端点返回 500。
func TestClassifyWithoutClassifier(t *testing.T) {
	s, ts := newTestServer(t)
	// 测试与 server 同包，可直接置空 classifier
	s.classifier = nil

	code, body := doJSON(t, ts, http.MethodPost, "/api/papers/classify", nil)
	if code != 500 {
		t.Fatalf("状态码: got %d want 500, body: %s", code, body)
	}
	var resp map[string]string
	if err := json.Unmarshal(body, &resp); err != nil {
		t.Fatalf("解析失败: %v, body: %s", err, body)
	}
	if resp["error"] != "分类器未初始化" {
		t.Errorf("error: got %q want 分类器未初始化", resp["error"])
	}
}
