// Package paper 的 ACL Anthology 数据源适配器。
//
// 文件概述：acl_source.go 实现 PaperSource 接口的 ACL Anthology 适配器，
// 从 ACL Anthology 网站按会议（acl/emnlp/naacl/coling）抓取论文元数据：
//   1. 访问会议事件页 {baseURL}/events/{conf}-{year}/ 获取论文链接（如 /2023.acl-long.1/）；
//   2. 对每篇论文请求 {baseURL}/{paper_id}.bib 获取 BibTeX；
//   3. 用正则解析 BibTeX 提取 title/author/year/doi/booktitle；
//   4. 拼接 PDF 直链 {baseURL}/{paper_id}.pdf，从 url/note 字段提取 arXiv ID；
//   5. 返回 []PaperMeta，Source 字段统一设为 "acl"。
//
// 简化策略：events 页面结构复杂，仅用正则从 HTML 中提取论文链接，
// 取前 maxPerConf 篇的 .bib；BibTeX 亦用正则提取，不引入完整解析器。
package paper

import (
	"context"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
)

const (
	aclDefaultBaseURL = "https://aclanthology.org"
	aclDefaultMaxPer  = 50
	aclDefaultYear    = 2023
)

// ACLAnthologySource 是 ACL Anthology 数据源适配器。
type ACLAnthologySource struct {
	httpClient  *http.Client
	baseURL     string   // 默认 "https://aclanthology.org"
	conferences []string // 目标会议：acl, emnlp, naacl, coling
	maxPerConf  int      // 每会议拉取数量，默认 50
	year        int      // 抓取年份
}

// 编译期断言：ACLAnthologySource 实现 PaperSource 接口。
var _ PaperSource = (*ACLAnthologySource)(nil)

// NewACLAnthologySource 构造默认配置的 ACL Anthology 数据源。
func NewACLAnthologySource() *ACLAnthologySource {
	return &ACLAnthologySource{
		httpClient:  &http.Client{Timeout: 30 * time.Second},
		baseURL:     aclDefaultBaseURL,
		conferences: []string{"acl", "emnlp", "naacl", "coling"},
		maxPerConf:  aclDefaultMaxPer,
		year:        aclDefaultYear,
	}
}

// ID 返回源标识。
func (s *ACLAnthologySource) ID() string { return "acl" }

// Name 返回源的可读名称。
func (s *ACLAnthologySource) Name() string { return "ACL Anthology NLP 论文" }

// TestConnection 探测 baseURL 是否可达。
func (s *ACLAnthologySource) TestConnection() error {
	if s.httpClient == nil {
		s.httpClient = &http.Client{Timeout: 30 * time.Second}
	}
	if s.baseURL == "" {
		s.baseURL = aclDefaultBaseURL
	}
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, s.baseURL, nil)
	if err != nil {
		return fmt.Errorf("构造请求失败: %w", err)
	}
	resp, err := s.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("连接 ACL Anthology 失败: %w", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return fmt.Errorf("ACL Anthology 返回状态码 %d", resp.StatusCode)
	}
	return nil
}

// paperIDRe 从会议事件页 HTML 中提取论文链接（如 /2023.acl-long.1/）。
var paperIDRe = regexp.MustCompile(`href="(/[0-9]{4}\.[a-z-]+\.[0-9]+)/"`)

// BibTeX 字段提取正则。
var (
	bibTitleRe     = regexp.MustCompile(`title\s*=\s*"\{?([^"}]+)"\}?`)
	bibAuthorRe    = regexp.MustCompile(`author\s*=\s*"([^"]+)"`)
	bibYearRe      = regexp.MustCompile(`year\s*=\s*"(\d{4})"`)
	bibDOIRe       = regexp.MustCompile(`doi\s*=\s*"([^"]+)"`)
	bibBooktitleRe = regexp.MustCompile(`booktitle\s*=\s*"([^"]+)"`)
	bibURLRe       = regexp.MustCompile(`url\s*=\s*"([^"]+)"`)
	bibNoteRe      = regexp.MustCompile(`note\s*=\s*"([^"]+)"`)
)

// arxivIDRe 从 url 或 note 字段中提取 arXiv ID（支持新格式 2305.12345 与旧格式 cs.CL/0703012）。
var arxivIDRe = regexp.MustCompile(`(?i)arxiv\.org/(?:abs|pdf)/([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})|arXiv:\s*([0-9]{4}\.[0-9]{4,5}|[a-z\-]+/[0-9]{7})`)

// Sync 按会议循环抓取论文元数据。
//
// 单个会议页面或单篇 .bib 拉取失败时跳过，不影响其他会议/论文。
func (s *ACLAnthologySource) Sync(ctx context.Context) ([]PaperMeta, error) {
	if s.httpClient == nil {
		s.httpClient = &http.Client{Timeout: 30 * time.Second}
	}
	if s.baseURL == "" {
		s.baseURL = aclDefaultBaseURL
	}
	maxPer := s.maxPerConf
	if maxPer <= 0 {
		maxPer = aclDefaultMaxPer
	}
	year := s.year
	if year == 0 {
		year = aclDefaultYear
	}

	var metas []PaperMeta
	seen := make(map[string]struct{})

	for _, conf := range s.conferences {
		pageURL := fmt.Sprintf("%s/events/%s-%d/", s.baseURL, conf, year)
		html, err := s.fetch(ctx, pageURL)
		if err != nil {
			// 会议页面失败时跳过，继续处理其他会议
			continue
		}
		ids := extractPaperIDs(html)
		if len(ids) > maxPer {
			ids = ids[:maxPer]
		}
		for _, id := range ids {
			if _, ok := seen[id]; ok {
				continue
			}
			seen[id] = struct{}{}
			cleanID := strings.TrimPrefix(id, "/")
			bibURL := fmt.Sprintf("%s/%s.bib", s.baseURL, cleanID)
			bib, err := s.fetch(ctx, bibURL)
			if err != nil {
				continue
			}
			meta := parseBibTeX(bib)
			meta.PDFURL = fmt.Sprintf("%s/%s.pdf", s.baseURL, cleanID)
			meta.Source = "acl"
			metas = append(metas, meta)
		}
	}
	return metas, nil
}

// fetch 发起 GET 请求并返回响应体字符串。
func (s *ACLAnthologySource) fetch(ctx context.Context, url string) (string, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return "", fmt.Errorf("构造请求 %s 失败: %w", url, err)
	}
	req.Header.Set("User-Agent", "nuclear-ox-v2/2.0 (paper sync)")
	resp, err := s.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("请求 %s 失败: %w", url, err)
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 400 {
		return "", fmt.Errorf("%s 返回状态码 %d", url, resp.StatusCode)
	}
	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return "", fmt.Errorf("读取 %s 响应失败: %w", url, err)
	}
	return string(body), nil
}

// extractPaperIDs 从会议事件页 HTML 中正则提取论文 ID（含前导斜杠）。
// 保持首次出现顺序并去重。
func extractPaperIDs(html string) []string {
	matches := paperIDRe.FindAllStringSubmatch(html, -1)
	seen := make(map[string]struct{})
	var ids []string
	for _, m := range matches {
		if len(m) < 2 {
			continue
		}
		id := m[1]
		if _, ok := seen[id]; ok {
			continue
		}
		seen[id] = struct{}{}
		ids = append(ids, id)
	}
	return ids
}

// parseBibTeX 用正则从 BibTeX 文本中提取论文元数据。
func parseBibTeX(bib string) PaperMeta {
	var meta PaperMeta
	if m := bibTitleRe.FindStringSubmatch(bib); len(m) >= 2 {
		meta.Title = strings.TrimSpace(m[1])
	}
	if m := bibAuthorRe.FindStringSubmatch(bib); len(m) >= 2 {
		meta.Authors = parseBibTeXAuthors(m[1])
	}
	if m := bibYearRe.FindStringSubmatch(bib); len(m) >= 2 {
		if y, err := strconv.Atoi(m[1]); err == nil {
			meta.Year = y
		}
	}
	if m := bibDOIRe.FindStringSubmatch(bib); len(m) >= 2 {
		meta.DOI = strings.TrimSpace(m[1])
	}
	if m := bibBooktitleRe.FindStringSubmatch(bib); len(m) >= 2 {
		meta.Venue = strings.TrimSpace(m[1])
	}
	// arXiv ID 优先从 url 字段提取，其次 note 字段
	for _, re := range []*regexp.Regexp{bibURLRe, bibNoteRe} {
		if sm := re.FindStringSubmatch(bib); len(sm) >= 2 {
			if aid := extractArxivIDFromText(sm[1]); aid != "" {
				meta.ArxivID = aid
				break
			}
		}
	}
	return meta
}

// parseBibTeXAuthors 将 BibTeX author 字段按 " and " 分割，取每段姓氏后逗号拼接。
// "Liu, Yajao and Jiang, Xin" -> "Liu, Jiang"
func parseBibTeXAuthors(raw string) string {
	parts := strings.Split(raw, " and ")
	var names []string
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p == "" {
			continue
		}
		// BibTeX "Surname, Given" 格式取逗号前的姓氏
		if i := strings.Index(p, ","); i >= 0 {
			names = append(names, strings.TrimSpace(p[:i]))
		} else {
			names = append(names, p)
		}
	}
	return strings.Join(names, ", ")
}

// extractArxivIDFromText 从单段文本中提取 arXiv ID（用于 BibTeX url/note 字段）。
// 注意：与 company_source.go 中处理 arXiv id URL 的 extractArxivID 区分，避免同名冲突。
func extractArxivIDFromText(text string) string {
	m := arxivIDRe.FindStringSubmatch(text)
	if m == nil {
		return ""
	}
	for _, g := range m[1:] {
		if g != "" {
			return g
		}
	}
	return ""
}
