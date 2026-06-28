// Package paper 的 arXiv 数据源适配器。
//
// 文件概述：arxiv_source.go 实现 PaperSource 接口的 arXiv 适配器：
//   - 按分类（cs.AI, cs.CL, cs.LG, cs.CV, cs.CR, cs.DC）循环调用 arXiv API；
//   - 解析 Atom XML feed，提取标题/作者/摘要/PDF/arxiv_id/年份；
//   - 返回 []PaperMeta，Source 设为 "arxiv"；
//   - TestConnection 发最小请求验证连通性。
//
// API: {baseURL}/query?search_query=cat:{category}&sortBy=submittedDate&sortOrder=descending&max_results={maxResults}
// 默认 baseURL: https://export.arxiv.org/api
//
// 复用说明：Atom XML 结构（arxivFeed/arxivEntry 等）与 arxivIDFromURL/parseYear
// 已在 company_source.go 中定义，本文件直接复用，避免重复。
package paper

import (
	"context"
	"encoding/xml"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

const (
	arxivDefaultBaseURL    = "https://export.arxiv.org/api"
	arxivDefaultMaxResults = 50
)

// ArxivSource 是 arXiv 预印本数据源适配器。
type ArxivSource struct {
	httpClient *http.Client
	baseURL    string   // 默认 "https://export.arxiv.org/api"
	categories []string // cs.AI, cs.CL, cs.LG, cs.CV, cs.CR, cs.DC
	maxResults int      // 每分类拉取数量，默认 50
}

// NewArxivSource 构造默认配置的 arXiv 数据源。
func NewArxivSource() *ArxivSource {
	return &ArxivSource{
		httpClient: &http.Client{Timeout: 30 * time.Second},
		baseURL:    arxivDefaultBaseURL,
		categories: []string{"cs.AI", "cs.CL", "cs.LG", "cs.CV", "cs.CR", "cs.DC"},
		maxResults: arxivDefaultMaxResults,
	}
}

// NewArxivSourceWithBaseURL 构造指定 baseURL 的 arXiv 数据源，主要供测试注入 mock server。
func NewArxivSourceWithBaseURL(baseURL string) *ArxivSource {
	s := NewArxivSource()
	s.baseURL = baseURL
	return s
}

// ID 返回源标识 "arxiv"。
func (a *ArxivSource) ID() string { return "arxiv" }

// Name 返回源中文名 "arXiv 预印本"。
func (a *ArxivSource) Name() string { return "arXiv 预印本" }

// Sync 按分类循环调用 arXiv API，返回聚合后的 []PaperMeta。
// 单分类失败不阻断其他分类（跳过继续）。
func (a *ArxivSource) Sync(ctx context.Context) ([]PaperMeta, error) {
	var metas []PaperMeta
	for _, cat := range a.categories {
		entries, err := a.fetchCategory(ctx, cat)
		if err != nil {
			// 单分类失败不阻断其余分类
			continue
		}
		for _, e := range entries {
			metas = append(metas, arxivEntryToMeta(e))
		}
	}
	return metas, nil
}

// fetchCategory 拉取单个分类的论文条目。
func (a *ArxivSource) fetchCategory(ctx context.Context, category string) ([]arxivEntry, error) {
	u := fmt.Sprintf("%s/query?search_query=cat:%s&sortBy=submittedDate&sortOrder=descending&max_results=%d",
		a.baseURL, url.QueryEscape(category), a.maxResults)

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Accept", "application/atom+xml")

	resp, err := a.httpClient.Do(req)
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

	var feed arxivFeed
	if err := xml.Unmarshal(body, &feed); err != nil {
		return nil, fmt.Errorf("解析 arXiv Atom XML 失败: %w", err)
	}
	return feed.Entries, nil
}

// arxivIDFromURL 从 arXiv id URL（如 http://arxiv.org/abs/2305.14996v1）提取纯 id。
// 去掉 URL 前缀与版本号后缀（vN），返回 "2305.14996"。
// company_source.go 的 arXiv 同步与本源的 arxivEntryToMeta 共用此函数。
func arxivIDFromURL(idURL string) string {
	id := idURL
	// 取 URL 最后一段
	if idx := strings.LastIndex(idURL, "/"); idx >= 0 && idx < len(idURL)-1 {
		id = idURL[idx+1:]
	}
	// 去除版本号后缀 vN（v 后跟数字）
	for i := len(id) - 1; i > 0; i-- {
		if id[i] == 'v' && i+1 < len(id) && id[i+1] >= '0' && id[i+1] <= '9' {
			return id[:i]
		}
		if !((id[i] >= '0' && id[i] <= '9') || id[i] == '.') {
			break
		}
	}
	return id
}

// arxivEntryToMeta 将单篇 arXiv entry 转为 PaperMeta（Source 设为 "arxiv"）。
//   - title 去多余空白；
//   - authors 逗号拼接所有 author name；
//   - pdf_url 取 link 中 type="application/pdf" 的 href；
//   - arxiv_id 从 id URL 提取并去版本号（arxivIDFromURL）；
//   - year 从 published 解析（复用 parseYear）。
func arxivEntryToMeta(e arxivEntry) PaperMeta {
	return PaperMeta{
		Title:    strings.TrimSpace(strings.Join(strings.Fields(e.Title), " ")),
		Authors:  joinArxivAuthors(e.Authors),
		Abstract: strings.TrimSpace(e.Summary),
		PDFURL:   extractArxivPDFURL(e.Links),
		ArxivID:  arxivIDFromURL(e.ID),
		Year:     parseYear(e.Published),
		Source:   "arxiv",
	}
}

// joinArxivAuthors 将多作者 name 逗号拼接。
func joinArxivAuthors(authors []arxivAuthor) string {
	names := make([]string, 0, len(authors))
	for _, au := range authors {
		n := strings.TrimSpace(au.Name)
		if n != "" {
			names = append(names, n)
		}
	}
	return strings.Join(names, ", ")
}

// extractArxivPDFURL 从 link 列表中找 type="application/pdf" 的 href。
func extractArxivPDFURL(links []arxivLink) string {
	for _, l := range links {
		if l.Type == "application/pdf" && l.Href != "" {
			return l.Href
		}
	}
	return ""
}

// TestConnection 发一个最小请求验证 arXiv API 连通性。
func (a *ArxivSource) TestConnection() error {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	u := fmt.Sprintf("%s/query?search_query=cat:cs.AI&max_results=1", a.baseURL)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return fmt.Errorf("构造请求失败: %w", err)
	}

	resp, err := a.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("连接 arXiv API 失败: %w", err)
	}
	defer resp.Body.Close()
	io.Copy(io.Discard, resp.Body)

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("arXiv API 返回非 200: status=%d", resp.StatusCode)
	}
	return nil
}
