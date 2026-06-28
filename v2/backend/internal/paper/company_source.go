// Package paper 的公司论文追踪数据源适配器。
//
// 文件概述：company_source.go 实现 PaperSource 接口，按预设的 AI 公司清单
// （DeepSeek/Kimi/Qwen/智谱/OpenAI/Google/Anthropic/DeepMind/xAI）从两个维度追踪技术产出：
//   1. arXiv 维度：以公司作者名（如 DeepSeek-AI、moonshotai）查询 arXiv API，
//      按提交时间倒序取最近 N 篇，解析 Atom XML 落库；
//   2. GitHub 维度：列出公司 GitHub 组织的公开仓库，按 topic/仓库名筛选
//      paper/research/llm 相关项目，作为"开源项目"追踪（非论文，pdf_url 留空）。
//
// 复用说明：本文件定义 arXiv Atom XML 的共享结构（arxivFeed/arxivEntry 等）
// 与解析辅助函数 parseYear，arxiv_source.go 直接复用，避免重复。
// extractArxivID 定义在 arxiv_source.go 中（本源 arXiv 同步复用）；
// acl_source.go 另有 extractArxivIDFromText（正则版，处理 BibTeX 文本）。
//
// 设计要点：
//   - 单公司失败不阻断其他公司：每公司错误记日志后继续；
//   - arXiv 论文每条设置 Company 字段为公司 Name，Source 覆盖为 "company"；
//   - GitHub 仓库以 Source="company" 标记，GitHubRepo 为仓库全名，与论文区分；
//   - 完全幂等：依赖 UpsertPaperMeta 的 id 生成（arxiv_id > doi > uuid）去重。
package paper

import (
	"context"
	"encoding/json"
	"encoding/xml"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// CompanyInfo 描述一家被追踪的 AI 公司及其在 arXiv/GitHub 上的标识。
type CompanyInfo struct {
	Name        string // deepseek, kimi, openai, ...
	DisplayName string // DeepSeek, Kimi, OpenAI, ...
	ArxivAuthor string // arXiv 作者名：DeepSeek-AI, moonshotai, ...
	GitHubOrg   string // GitHub 组织名：deepseek-ai, moonshotai, ...
	Domain      string // 关注领域
}

// DefaultCompanies 是默认追踪的 9 家 AI 公司清单。
var DefaultCompanies = []CompanyInfo{
	{Name: "deepseek", DisplayName: "DeepSeek", ArxivAuthor: "DeepSeek-AI", GitHubOrg: "deepseek-ai", Domain: "LLM/推理/RL"},
	{Name: "kimi", DisplayName: "Kimi (月之暗面)", ArxivAuthor: "moonshotai", GitHubOrg: "moonshotai", Domain: "长上下文/LLM"},
	{Name: "qwen", DisplayName: "Qwen (阿里)", ArxivAuthor: "Qwen", GitHubOrg: "QwenLM", Domain: "多模态/LLM"},
	{Name: "zhipu", DisplayName: "智谱", ArxivAuthor: "ZhipuAI", GitHubOrg: "THUDM", Domain: "LLM/Agent"},
	{Name: "openai", DisplayName: "OpenAI", ArxivAuthor: "OpenAI", GitHubOrg: "openai", Domain: "LLM/推理/RL"},
	{Name: "google", DisplayName: "Google", ArxivAuthor: "Google AI", GitHubOrg: "google-research", Domain: "ML基础/多模态"},
	{Name: "anthropic", DisplayName: "Anthropic", ArxivAuthor: "Anthropic", GitHubOrg: "anthropics", Domain: "LLM安全/对齐"},
	{Name: "deepmind", DisplayName: "DeepMind", ArxivAuthor: "DeepMind", GitHubOrg: "google-deepmind", Domain: "RL/推理"},
	{Name: "xai", DisplayName: "xAI (Grok)", ArxivAuthor: "xAI", GitHubOrg: "xai-org", Domain: "LLM/推理"},
}

// CompanySource 是公司论文追踪数据源适配器，实现 PaperSource 接口。
type CompanySource struct {
	httpClient    *http.Client
	arxivBaseURL  string // "https://export.arxiv.org/api"
	githubBaseURL string // "https://api.github.com"
	githubToken   string
	companies     []CompanyInfo
	maxPerCompany int // 每公司拉取论文数，默认 20
}

// NewCompanySource 构造默认 CompanySource。
// githubToken 为空时走匿名访问（受 60/hour 限制），建议配置 GITHUB_TOKEN。
func NewCompanySource(githubToken string) *CompanySource {
	return &CompanySource{
		httpClient:    &http.Client{Timeout: 30 * time.Second},
		arxivBaseURL:  "https://export.arxiv.org/api",
		githubBaseURL: "https://api.github.com",
		githubToken:   githubToken,
		companies:     DefaultCompanies,
		maxPerCompany: 20,
	}
}

// ID 返回源标识。
func (c *CompanySource) ID() string { return "company" }

// Name 返回源展示名。
func (c *CompanySource) Name() string { return "AI 公司技术报告" }

// Sync 按公司循环，从 arXiv 与 GitHub 两个维度拉取论文/项目元数据。
// 单公司失败不阻断其他公司：错误记日志后继续，返回已成功收集的全部元数据。
func (c *CompanySource) Sync(ctx context.Context) ([]PaperMeta, error) {
	var metas []PaperMeta

	for _, company := range c.companies {
		// arXiv 维度
		arxivMetas, err := c.syncCompanyArxiv(ctx, company)
		if err != nil {
			// 单公司失败不阻断，记日志后继续
			log.Printf("[company] [WARN] arxiv 同步 %s 失败: %v", company.Name, err)
		} else {
			metas = append(metas, arxivMetas...)
		}

		// GitHub 维度
		ghMetas, err := c.syncCompanyGitHub(ctx, company)
		if err != nil {
			log.Printf("[company] [WARN] github 同步 %s 失败: %v", company.Name, err)
		} else {
			metas = append(metas, ghMetas...)
		}
	}

	return metas, nil
}

// TestConnection 检查 arXiv API 连通性。
func (c *CompanySource) TestConnection() error {
	u := c.arxivBaseURL + "/query?search_query=au:OpenAI&max_results=1"
	req, err := http.NewRequest(http.MethodGet, u, nil)
	if err != nil {
		return fmt.Errorf("构造 arXiv 测试请求失败: %w", err)
	}
	req.Header.Set("User-Agent", "nuclear-ox-v2/1.0")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("arXiv API 不可达: %w", err)
	}
	defer resp.Body.Close()
	// 读取响应体以释放连接
	_, _ = io.Copy(io.Discard, resp.Body)

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("arXiv API 返回非 200: status=%d", resp.StatusCode)
	}
	return nil
}

// === arXiv Atom XML 共享结构（arxiv_source.go 复用） ===

// arxivFeed 对应 arXiv API 返回的 Atom XML feed 根元素。
type arxivFeed struct {
	XMLName xml.Name     `xml:"feed"`
	Entries []arxivEntry `xml:"entry"`
}

// arxivEntry 对应 feed 中的单篇论文。
type arxivEntry struct {
	ID        string       `xml:"id"`        // http://arxiv.org/abs/2303.08774v1
	Title     string       `xml:"title"`     // 标题（含换行/空白，需清洗）
	Summary   string       `xml:"summary"`   // 摘要
	Authors   []arxivAuthor `xml:"author"`   // 作者列表
	Links     []arxivLink  `xml:"link"`      // 含 pdf/related 等链接
	Published string       `xml:"published"` // 2023-03-15T00:00:00Z
}

// arxivAuthor 对应 <author><name>...</name></author>。
type arxivAuthor struct {
	Name string `xml:"name"`
}

// arxivLink 对应 <link> 元素，含 href/rel/type/title 属性。
type arxivLink struct {
	Href  string `xml:"href,attr"`
	Rel   string `xml:"rel,attr"`
	Type  string `xml:"type,attr"`
	Title string `xml:"title,attr"`
}

// parseYear 从 RFC3339 时间字符串（如 2023-03-15T00:00:00Z）解析年份，失败返回 0。
func parseYear(s string) int {
	s = strings.TrimSpace(s)
	if s == "" {
		return 0
	}
	if t, err := time.Parse(time.RFC3339, s); err == nil {
		return t.Year()
	}
	// 兜底：取前 4 位数字作为年份
	if len(s) >= 4 {
		var y int
		if _, err := fmt.Sscanf(s[:4], "%d", &y); err == nil {
			return y
		}
	}
	return 0
}

// syncCompanyArxiv 拉取单家公司在 arXiv 上的最近论文。
// 复用 arxivFeed 结构与 arxivEntryToMeta 解析逻辑，
// 仅覆盖 Company 字段为公司 Name、Source 字段为 "company"。
func (c *CompanySource) syncCompanyArxiv(ctx context.Context, company CompanyInfo) ([]PaperMeta, error) {
	maxResults := c.maxPerCompany
	if maxResults <= 0 {
		maxResults = 20
	}
	// search_query=au:{ArxivAuthor}，作者名含空格需 URL 编码
	u := fmt.Sprintf("%s/query?search_query=au:%s&sortBy=submittedDate&sortOrder=descending&max_results=%d",
		c.arxivBaseURL, url.QueryEscape(company.ArxivAuthor), maxResults)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("构造 arXiv 请求失败: %w", err)
	}
	req.Header.Set("Accept", "application/atom+xml")
	req.Header.Set("User-Agent", "nuclear-ox-v2/1.0")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("请求 arXiv API 失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("arXiv API 返回非 200: status=%d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取 arXiv 响应失败: %w", err)
	}

	// 复用 arxivFeed 结构解析 Atom XML
	var feed arxivFeed
	if err := xml.Unmarshal(body, &feed); err != nil {
		return nil, fmt.Errorf("解析 arXiv Atom XML 失败: %w", err)
	}

	metas := make([]PaperMeta, 0, len(feed.Entries))
	for _, entry := range feed.Entries {
		// 复用 arxivEntryToMeta 提取 title/authors/abstract/pdf_url/arxiv_id/year
		meta := arxivEntryToMeta(entry)
		// 覆盖为公司维度：Company 设为公司 Name，Source 标记为 company
		meta.Company = company.Name
		meta.Source = "company"
		metas = append(metas, meta)
	}
	return metas, nil
}

// === GitHub 维度 ===

// ghRepo 对应 GitHub List Org Repos API 的单条响应（仅保留本源需要的字段）。
type ghRepo struct {
	Name        string   `json:"name"`        // 仓库名（不含组织前缀）
	FullName    string   `json:"full_name"`   // 仓库全名 org/repo
	Description string   `json:"description"` // 仓库描述
	Topics      []string `json:"topics"`      // 仓库 topics
}

// researchTopicKeywords 是用于筛选研究类仓库的 topic 关键词（小写匹配）。
var researchTopicKeywords = []string{"paper", "research", "llm"}

// researchNameKeywords 是用于按仓库名筛选的关键词（小写匹配）。
var researchNameKeywords = []string{"paper", "tech-report"}

// syncCompanyGitHub 拉取单家公司 GitHub 组织下与研究相关的仓库。
// 筛选规则：topic 含 paper/research/llm，或仓库名含 paper/tech-report。
// 注意：GitHub repo 不是论文，但作为"开源项目"追踪，pdf_url 留空。
func (c *CompanySource) syncCompanyGitHub(ctx context.Context, company CompanyInfo) ([]PaperMeta, error) {
	if company.GitHubOrg == "" {
		return nil, nil
	}
	u := fmt.Sprintf("%s/orgs/%s/repos?sort=updated&per_page=30&type=public",
		c.githubBaseURL, url.PathEscape(company.GitHubOrg))

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("构造 GitHub 请求失败: %w", err)
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	if c.githubToken != "" {
		req.Header.Set("Authorization", "Bearer "+c.githubToken)
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("请求 GitHub API 失败: %w", err)
	}
	defer resp.Body.Close()

	// rate limit 处理：403/429 通常表示额度耗尽
	if resp.StatusCode == http.StatusForbidden || resp.StatusCode == http.StatusTooManyRequests {
		remaining := resp.Header.Get("X-RateLimit-Remaining")
		return nil, fmt.Errorf("GitHub API 限流（status=%d, X-RateLimit-Remaining=%s）；请配置 GITHUB_TOKEN 提升额度或稍后重试",
			resp.StatusCode, remaining)
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("GitHub API 返回非 200: status=%d", resp.StatusCode)
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("读取 GitHub 响应失败: %w", err)
	}

	var repos []ghRepo
	if err := json.Unmarshal(body, &repos); err != nil {
		return nil, fmt.Errorf("解析 GitHub 响应失败: %w", err)
	}

	var metas []PaperMeta
	for _, repo := range repos {
		if !isResearchRepo(repo) {
			continue
		}
		meta := PaperMeta{
			Title:      repo.Name,
			Authors:    company.DisplayName,
			GitHubRepo: repo.FullName,
			Source:     "company",
			Company:    company.Name,
			Abstract:   repo.Description,
			// PDFURL 留空：GitHub repo 不是论文
		}
		metas = append(metas, meta)
	}
	return metas, nil
}

// isResearchRepo 判断仓库是否符合研究类筛选条件：
//   - topic 含 paper/research/llm（任一），或
//   - 仓库名含 paper/tech-report（任一）。
func isResearchRepo(repo ghRepo) bool {
	for _, topic := range repo.Topics {
		t := strings.ToLower(strings.TrimSpace(topic))
		for _, kw := range researchTopicKeywords {
			if t == kw {
				return true
			}
		}
	}
	nameLower := strings.ToLower(repo.Name)
	for _, kw := range researchNameKeywords {
		if strings.Contains(nameLower, kw) {
			return true
		}
	}
	return false
}
