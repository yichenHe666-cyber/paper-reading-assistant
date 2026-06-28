// Package paper 的公司论文追踪数据源测试。
//
// 文件概述：company_source_test.go 用 httptest mock server 同时模拟
// arXiv API（Atom XML）与 GitHub Org Repos API（JSON），验证 CompanySource：
//   - arXiv 维度：每篇论文 Company 字段正确标记为公司 Name，Source 为 "company"；
//   - GitHub 维度：仓库按 topic（paper/research/llm）与仓库名（paper/tech-report）筛选；
//   - 9 家预设公司全部被遍历（arXiv 与 GitHub 各 9 次请求）。
//
// 不依赖真实网络，可在离线环境运行。
package paper

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

// companyTracker 记录 mock server 收到的 arXiv/GitHub 请求涉及的公司标识，
// 用于验证 9 家公司是否全部被遍历。
type companyTracker struct {
	mu        sync.Mutex
	arxivSeen map[string]bool // key: ArxivAuthor
	ghSeen    map[string]bool // key: GitHubOrg
}

func newCompanyTracker() *companyTracker {
	return &companyTracker{
		arxivSeen: make(map[string]bool),
		ghSeen:    make(map[string]bool),
	}
}

func (ct *companyTracker) markArxiv(author string) {
	ct.mu.Lock()
	defer ct.mu.Unlock()
	ct.arxivSeen[author] = true
}

func (ct *companyTracker) markGitHub(org string) {
	ct.mu.Lock()
	defer ct.mu.Unlock()
	ct.ghSeen[org] = true
}

func (ct *companyTracker) arxivCount() int {
	ct.mu.Lock()
	defer ct.mu.Unlock()
	return len(ct.arxivSeen)
}

func (ct *companyTracker) ghCount() int {
	ct.mu.Lock()
	defer ct.mu.Unlock()
	return len(ct.ghSeen)
}

// mockCompanyServer 启动一个同时处理 arXiv /query 与 GitHub /orgs/{org}/repos
// 的 httptest.Server。返回 tracker 以便测试断言哪些公司被请求过。
//
// arXiv 维度：按 search_query=au:{author} 返回 1 篇论文，title 含 author 便于定位。
// GitHub 维度：每个 org 返回固定的一组仓库（含匹配/不匹配 topic 的混合）。
func mockCompanyServer(t *testing.T) (*httptest.Server, *companyTracker) {
	t.Helper()
	tr := newCompanyTracker()

	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		switch {
		case path == "/query":
			// arXiv API
			w.Header().Set("Content-Type", "application/atom+xml")
			author := strings.TrimPrefix(r.URL.Query().Get("search_query"), "au:")
			tr.markArxiv(author)
			_, _ = w.Write([]byte(mockArxivFeed(author)))
			return
		case strings.HasPrefix(path, "/orgs/") && strings.HasSuffix(path, "/repos"):
			// GitHub API: /orgs/{org}/repos
			w.Header().Set("Content-Type", "application/json")
			trimmed := strings.TrimPrefix(path, "/orgs/")
			org := strings.TrimSuffix(trimmed, "/repos")
			tr.markGitHub(org)
			_ = json.NewEncoder(w).Encode(mockGitHubRepos(org))
			return
		default:
			t.Errorf("未预期的请求路径: %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	return srv, tr
}

// mockArxivFeed 生成包含 1 篇论文的 arXiv Atom XML。
// title 与 abstract 嵌入 author 便于测试定位断言。
func mockArxivFeed(author string) string {
	// arxiv_id 用 author 的稳定哈希片段，避免不同公司论文 id 重复
	aid := stableArxivID(author)
	return fmt.Sprintf(`<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/%sv1</id>
    <title>Test Paper from %s</title>
    <summary>Abstract for %s technical report.</summary>
    <author><name>%s</name></author>
    <link href="http://arxiv.org/pdf/%s" rel="related" type="application/pdf"/>
    <published>2024-01-15T00:00:00Z</published>
  </entry>
</feed>`, aid, author, author, author, aid)
}

// stableArxivID 由 author 生成一个稳定的 arXiv id 片段（4位.5位数字格式）。
// 不同 author 映射到不同 id，保证去重逻辑可被验证。
func stableArxivID(author string) string {
	var sum int
	for _, c := range author {
		sum += int(c)
	}
	return fmt.Sprintf("2401.%05d", sum%100000)
}

// mockGitHubRepos 为指定 org 返回一组仓库，混合匹配与不匹配筛选条件的样本：
//   - {org}/paper-repo：topic=[paper]，应被选中（topic 匹配）
//   - {org}/research-lab：topic=[research]，应被选中（topic 匹配）
//   - {org}/llm-models：topic=[llm]，应被选中（topic 匹配）
//   - {org}/tech-report-2024：topic=[tool]，应被选中（name 含 tech-report）
//   - {org}/paper-notes：topic=[notes]，应被选中（name 含 paper）
//   - {org}/random-tool：topic=[tool]，不应被选中（topic/name 均不匹配）
func mockGitHubRepos(org string) []ghRepo {
	return []ghRepo{
		{Name: "paper-repo", FullName: org + "/paper-repo", Description: "paper repo", Topics: []string{"paper"}},
		{Name: "research-lab", FullName: org + "/research-lab", Description: "research lab", Topics: []string{"research"}},
		{Name: "llm-models", FullName: org + "/llm-models", Description: "llm models", Topics: []string{"llm"}},
		{Name: "tech-report-2024", FullName: org + "/tech-report-2024", Description: "tech report", Topics: []string{"tool"}},
		{Name: "paper-notes", FullName: org + "/paper-notes", Description: "notes", Topics: []string{"notes"}},
		{Name: "random-tool", FullName: org + "/random-tool", Description: "unrelated", Topics: []string{"tool"}},
	}
}

// newTestCompanySource 构造指向 mock server 的 CompanySource（9 家默认公司）。
func newTestCompanySource(arxivURL, ghURL string) *CompanySource {
	c := NewCompanySource("")
	c.arxivBaseURL = arxivURL
	c.githubBaseURL = ghURL
	return c
}

// TestCompanySourceSync 验证完整 Sync 流程：arXiv + GitHub 双维度聚合，
// 9 家公司全部遍历，arXiv 论文 Company 字段正确，GitHub 仓库按规则筛选。
func TestCompanySourceSync(t *testing.T) {
	srv, tr := mockCompanyServer(t)
	defer srv.Close()

	src := newTestCompanySource(srv.URL, srv.URL)

	metas, err := src.Sync(context.Background())
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	// 9 家公司 × (1 arXiv 论文 + 5 匹配 GitHub 仓库) = 54 条
	const expectArxiv = 9
	const expectGHPerCompany = 5 // paper-repo/research-lab/llm-models/tech-report-2024/paper-notes
	const expectTotal = expectArxiv + 9*expectGHPerCompany
	if len(metas) != expectTotal {
		t.Fatalf("metas 数: got %d want %d", len(metas), expectTotal)
	}

	// 9 家公司 arXiv 与 GitHub 各被请求一次
	if tr.arxivCount() != 9 {
		t.Errorf("arXiv 维度遍历公司数: got %d want 9", tr.arxivCount())
	}
	if tr.ghCount() != 9 {
		t.Errorf("GitHub 维度遍历公司数: got %d want 9", tr.ghCount())
	}

	// 统计 arXiv 与 GitHub 两类元数据数量
	arxivCount := 0
	ghCount := 0
	for _, m := range metas {
		if m.Source != "company" {
			t.Errorf("Source: got %q want company", m.Source)
		}
		if m.GitHubRepo == "" {
			arxivCount++
		} else {
			ghCount++
		}
	}
	if arxivCount != expectArxiv {
		t.Errorf("arXiv 论文数: got %d want %d", arxivCount, expectArxiv)
	}
	if ghCount != 9*expectGHPerCompany {
		t.Errorf("GitHub 仓库数: got %d want %d", ghCount, 9*expectGHPerCompany)
	}
}

// TestCompanyArxivCompanyField 验证 arXiv 维度论文的 Company/Source/ArxivID 字段。
func TestCompanyArxivCompanyField(t *testing.T) {
	srv, _ := mockCompanyServer(t)
	defer srv.Close()

	src := newTestCompanySource(srv.URL, srv.URL)

	metas, err := src.Sync(context.Background())
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	// 收集所有 arXiv 论文（GitHubRepo 为空）
	arxivMetas := make(map[string]PaperMeta) // key: company.Name
	for _, m := range metas {
		if m.GitHubRepo == "" {
			arxivMetas[m.Company] = m
		}
	}
	if len(arxivMetas) != 9 {
		t.Fatalf("arXiv 论文覆盖公司数: got %d want 9", len(arxivMetas))
	}

	// 逐公司验证字段
	for _, company := range DefaultCompanies {
		m, ok := arxivMetas[company.Name]
		if !ok {
			t.Errorf("公司 %s 缺少 arXiv 论文", company.Name)
			continue
		}
		// Company 应为公司 Name（小写标识）
		if m.Company != company.Name {
			t.Errorf("公司 %s: Company 字段 got %q want %q", company.Name, m.Company, company.Name)
		}
		// Source 必须为 company
		if m.Source != "company" {
			t.Errorf("公司 %s: Source got %q want company", company.Name, m.Source)
		}
		// ArxivID 应非空且去版本号
		wantAID := stableArxivID(company.ArxivAuthor)
		if m.ArxivID != wantAID {
			t.Errorf("公司 %s: ArxivID got %q want %q", company.Name, m.ArxivID, wantAID)
		}
		// PDFURL 应含 application/pdf 链接
		if !strings.Contains(m.PDFURL, wantAID) {
			t.Errorf("公司 %s: PDFURL got %q 应含 %q", company.Name, m.PDFURL, wantAID)
		}
		// Title 应含 author 名
		if !strings.Contains(m.Title, company.ArxivAuthor) {
			t.Errorf("公司 %s: Title got %q 应含 %q", company.Name, m.Title, company.ArxivAuthor)
		}
		// Year 应解析为 2024
		if m.Year != 2024 {
			t.Errorf("公司 %s: Year got %d want 2024", company.Name, m.Year)
		}
		// GitHubRepo 应为空（这是 arXiv 论文，非仓库）
		if m.GitHubRepo != "" {
			t.Errorf("公司 %s: arXiv 论文 GitHubRepo 应为空，got %q", company.Name, m.GitHubRepo)
		}
	}
}

// TestCompanyGitHubFilter 验证 GitHub 仓库按 topic/name 关键词筛选：
// topic 匹配（paper/research/llm）与 name 匹配（paper/tech-report）的仓库应入选，
// 不匹配的仓库（random-tool）应被排除。
func TestCompanyGitHubFilter(t *testing.T) {
	srv, _ := mockCompanyServer(t)
	defer srv.Close()

	src := newTestCompanySource(srv.URL, srv.URL)

	metas, err := src.Sync(context.Background())
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	// 收集所有 GitHub 仓库元数据（GitHubRepo 非空）
	type ghMeta struct {
		Company    string
		GitHubRepo string
		Title      string
	}
	ghByCompany := make(map[string][]ghMeta)
	for _, m := range metas {
		if m.GitHubRepo != "" {
			ghByCompany[m.Company] = append(ghByCompany[m.Company], ghMeta{
				Company:    m.Company,
				GitHubRepo: m.GitHubRepo,
				Title:      m.Title,
			})
		}
	}

	// 每家公司应恰好 5 个仓库入选（6 个中排除 random-tool）
	for _, company := range DefaultCompanies {
		repos := ghByCompany[company.Name]
		if len(repos) != 5 {
			t.Errorf("公司 %s: GitHub 仓库数 got %d want 5", company.Name, len(repos))
			continue
		}
		// random-tool 必须被排除
		for _, r := range repos {
			if strings.HasSuffix(r.GitHubRepo, "/random-tool") {
				t.Errorf("公司 %s: random-tool 不应入选", company.Name)
			}
		}
		// 验证 5 个预期仓库全部入选
		expected := map[string]bool{
			"paper-repo":      false,
			"research-lab":    false,
			"llm-models":      false,
			"tech-report-2024": false,
			"paper-notes":     false,
		}
		for _, r := range repos {
			expected[r.Title] = true
		}
		for name, found := range expected {
			if !found {
				t.Errorf("公司 %s: 仓库 %s 应入选但未找到", company.Name, name)
			}
		}
		// Authors 应为公司 DisplayName
		// （通过 Title 间接已验证；此处补一个 Authors 字段断言需重新遍历 metas）
	}

	// 补充验证 Authors 字段：GitHub 仓库的 Authors 应为公司 DisplayName
	for _, m := range metas {
		if m.GitHubRepo != "" {
			expected := ""
			for _, company := range DefaultCompanies {
				if company.Name == m.Company {
					expected = company.DisplayName
					break
				}
			}
			if m.Authors != expected {
				t.Errorf("仓库 %s: Authors got %q want %q", m.GitHubRepo, m.Authors, expected)
			}
			// GitHub 仓库的 PDFURL 应为空
			if m.PDFURL != "" {
				t.Errorf("仓库 %s: PDFURL 应为空，got %q", m.GitHubRepo, m.PDFURL)
			}
		}
	}
}

// TestCompanyAllCompaniesTraversed 验证 9 家预设公司全部被 arXiv/GitHub 两个维度遍历。
func TestCompanyAllCompaniesTraversed(t *testing.T) {
	srv, tr := mockCompanyServer(t)
	defer srv.Close()

	src := newTestCompanySource(srv.URL, srv.URL)

	if _, err := src.Sync(context.Background()); err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	// arXiv 维度：所有公司的 ArxivAuthor 都应被请求
	for _, company := range DefaultCompanies {
		if !tr.arxivSeen[company.ArxivAuthor] {
			t.Errorf("arXiv 维度未遍历公司 %s (author=%s)", company.Name, company.ArxivAuthor)
		}
	}
	// GitHub 维度：所有公司的 GitHubOrg 都应被请求
	for _, company := range DefaultCompanies {
		if !tr.ghSeen[company.GitHubOrg] {
			t.Errorf("GitHub 维度未遍历公司 %s (org=%s)", company.Name, company.GitHubOrg)
		}
	}
	// 总数应为 9（arXiv）+ 9（GitHub）
	if tr.arxivCount() != 9 {
		t.Errorf("arXiv 维度遍历公司数: got %d want 9", tr.arxivCount())
	}
	if tr.ghCount() != 9 {
		t.Errorf("GitHub 维度遍历公司数: got %d want 9", tr.ghCount())
	}
}

// TestCompanySourceIDName 验证源标识与名称。
func TestCompanySourceIDName(t *testing.T) {
	src := NewCompanySource("")
	if src.ID() != "company" {
		t.Errorf("ID(): got %q want company", src.ID())
	}
	if src.Name() != "AI 公司技术报告" {
		t.Errorf("Name(): got %q want AI 公司技术报告", src.Name())
	}
	// DefaultCompanies 应含 9 家公司
	if len(DefaultCompanies) != 9 {
		t.Errorf("DefaultCompanies 长度: got %d want 9", len(DefaultCompanies))
	}
}

// TestCompanySourceSingleCompanyFailure 验证单公司 arXiv/GitHub 失败不阻断其他公司。
// 通过一个 mock server：对特定 org 返回 500，其余正常。
func TestCompanySourceSingleCompanyFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path := r.URL.Path
		// 对 deepseek-ai 的 GitHub 请求返回 500，模拟单公司单维度失败
		if path == "/orgs/deepseek-ai/repos" {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		if path == "/query" {
			w.Header().Set("Content-Type", "application/atom+xml")
			author := strings.TrimPrefix(r.URL.Query().Get("search_query"), "au:")
			_, _ = w.Write([]byte(mockArxivFeed(author)))
			return
		}
		if strings.HasPrefix(path, "/orgs/") && strings.HasSuffix(path, "/repos") {
			w.Header().Set("Content-Type", "application/json")
			trimmed := strings.TrimPrefix(path, "/orgs/")
			org := strings.TrimSuffix(trimmed, "/repos")
			_ = json.NewEncoder(w).Encode(mockGitHubRepos(org))
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer srv.Close()

	src := newTestCompanySource(srv.URL, srv.URL)

	metas, err := src.Sync(context.Background())
	if err != nil {
		t.Fatalf("Sync 应在单公司失败时仍返回 nil error，got: %v", err)
	}
	// 应仍有结果：9 arXiv 论文 + 8 家 GitHub 仓库（deepseek GitHub 失败）
	// deepseek 的 arXiv 论文仍在，GitHub 仓库丢失
	if len(metas) == 0 {
		t.Fatal("单公司失败不应导致整体返回空")
	}
	// 验证 deepseek 的 arXiv 论文仍在
	foundDeepSeekArxiv := false
	for _, m := range metas {
		if m.Company == "deepseek" && m.GitHubRepo == "" {
			foundDeepSeekArxiv = true
		}
	}
	if !foundDeepSeekArxiv {
		t.Error("deepseek arXiv 论文应仍在（GitHub 失败不影响 arXiv 维度）")
	}
	// 验证 deepseek 的 GitHub 仓库不在
	for _, m := range metas {
		if m.Company == "deepseek" && strings.HasPrefix(m.GitHubRepo, "deepseek-ai/") {
			t.Error("deepseek GitHub 仓库不应出现（模拟 500 失败）")
		}
	}
}
