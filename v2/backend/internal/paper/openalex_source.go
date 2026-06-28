// Package paper 的 OpenAlex 数据源适配器。
//
// 文件概述：openalex_source.go 实现 PaperSource 接口的 OpenAlex 变体：
//   - 按 venue（ACL/CVPR/ICLR/NeurIPS/ICML/EMNLP）循环调用 /works 接口拉取论文；
//   - 解析倒排索引格式的摘要（abstract_inverted_index）重建为正常文本；
//   - 提取 title/authors/year/abstract/pdf_url/doi/venue 字段，组装 PaperMeta；
//   - 通过 mailto 参数走 OpenAlex polite pool，获得更稳定的访问配额。
//
// 数据源：https://api.openalex.org
// API：GET /works?filter=primary_location.source.display_name:{venue}&per_page={n}&mailto={email}
//   - 摘要返回倒排索引：{"word": [position1, position2]}，需按 position 排序重建文本。
//   - best_oa_location.pdf_url 可能为 null（闭源论文），此时 PDFURL 留空。
//   - doi 形如 "https://doi.org/10.xxxx/yyy"，统一去掉前缀只保留 DOI 本体。
//
// 设计要点：
//   - 完全幂等：依赖 Repository.UpsertPaperMeta 的主键去重（doi_{doi}）；
//   - 不依赖网络 mock 之外的状态，单 venue 失败不阻断其余 venue；
//   - 同步只取元数据，不下载 PDF 内容。
package paper

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"
)

// OpenAlexSource 是 OpenAlex 学术索引数据源适配器。
// httpClient 复用于所有 venue 请求；baseURL 默认指向官方 API，可覆盖用于测试。
type OpenAlexSource struct {
	httpClient *http.Client
	baseURL    string   // "https://api.openalex.org"
	mailto     string   // polite pool 邮箱（建议配置以获得更高速率）
	venues     []string // 目标会议/期刊名：ACL, CVPR, ICLR, NeurIPS, ICML, EMNLP
	perPage    int      // 默认 50
}

// NewOpenAlexSource 构造默认配置的 OpenAlex 数据源。
// venues 为空时使用一组默认顶会列表；perPage<=0 时使用 50。
func NewOpenAlexSource(mailto string, venues []string, perPage int) *OpenAlexSource {
	if len(venues) == 0 {
		venues = []string{"ACL", "CVPR", "ICLR", "NeurIPS", "ICML", "EMNLP"}
	}
	if perPage <= 0 {
		perPage = 50
	}
	return &OpenAlexSource{
		httpClient: &http.Client{Timeout: 30 * time.Second},
		baseURL:    "https://api.openalex.org",
		mailto:     mailto,
		venues:     venues,
		perPage:    perPage,
	}
}

// NewOpenAlexSourceWithBaseURL 构造指定 baseURL 的数据源。
// 主要供测试注入 httptest mock server；生产代码用 NewOpenAlexSource。
func NewOpenAlexSourceWithBaseURL(baseURL, mailto string, venues []string, perPage int) *OpenAlexSource {
	src := NewOpenAlexSource(mailto, venues, perPage)
	src.baseURL = baseURL
	return src
}

// ID 返回源标识 "openalex"。
func (o *OpenAlexSource) ID() string { return "openalex" }

// Name 返回源的中文名称。
func (o *OpenAlexSource) Name() string { return "OpenAlex 学术索引" }

// oaAuthorship 对应 OpenAlex works 响应中的 authorships 数组元素。
type oaAuthorship struct {
	Author struct {
		DisplayName string `json:"display_name"`
	} `json:"author"`
}

// oaSource 对应 primary_location.source 子对象。
type oaSource struct {
	DisplayName string `json:"display_name"`
}

// oaLocation 同时承载 primary_location 与 best_oa_location 两种位置信息：
//   - primary_location 仅使用 Source 字段提取 venue；
//   - best_oa_location 仅使用 PDFURL 字段提取 PDF 地址。
type oaLocation struct {
	Source *oaSource `json:"source"`
	PDFURL string    `json:"pdf_url"`
}

// oaWork 对应 OpenAlex /works 响应中的单篇论文。
type oaWork struct {
	ID                    string           `json:"id"`
	DisplayName           string           `json:"display_name"`
	PublicationYear       int              `json:"publication_year"`
	DOI                   string           `json:"doi"`
	AbstractInvertedIndex map[string][]int `json:"abstract_inverted_index"`
	Authorships           []oaAuthorship   `json:"authorships"`
	PrimaryLocation       *oaLocation      `json:"primary_location"`
	BestOALocation        *oaLocation      `json:"best_oa_location"`
}

// oaResponse 对应 /works 接口的顶层响应。
type oaResponse struct {
	Results []oaWork `json:"results"`
}

// Sync 按 venue 循环调用 OpenAlex /works 接口，聚合所有论文元数据。
//
// 错误隔离策略（修复审查发现的问题）：
//   - 单个 venue 请求失败不阻断其余 venue：仅记日志并 continue，已成功拉取的部分仍会返回；
//   - 部分 venue 成功 → 返回 (partial, nil)，SyncAll 能 upsert 已成功部分的论文；
//   - 全部 venue 失败 → 返回 (nil, err)，便于上层感知（如 429 限流、网络不通）整源不可用。
//
// 每篇 PaperMeta 的 Source 字段固定为 "openalex"。
func (o *OpenAlexSource) Sync(ctx context.Context) ([]PaperMeta, error) {
	var all []PaperMeta
	var failedVenues []string
	var firstErr error
	for _, venue := range o.venues {
		works, err := o.fetchWorks(ctx, venue)
		if err != nil {
			log.Printf("[openalex] [WARN] 拉取 venue %s 失败（跳过，继续其余 venue）: %v", venue, err)
			failedVenues = append(failedVenues, venue)
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		for _, w := range works {
			all = append(all, o.workToMeta(w))
		}
	}
	// 全部 venue 失败时返回错误，便于上层感知整源不可用；
	// 部分 venue 成功时返回已拉取数据 + nil，保证已成功部分能被 upsert（错误隔离）。
	if len(failedVenues) > 0 && len(all) == 0 {
		return all, fmt.Errorf("全部 %d 个 venue 拉取失败（%s）；首个错误: %w",
			len(failedVenues), strings.Join(failedVenues, ","), firstErr)
	}
	return all, nil
}

// TestConnection 发一个最小请求验证连通性。
// 使用第一个 venue（若有）发起 per_page=1 的探针请求。
func (o *OpenAlexSource) TestConnection() error {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	venue := ""
	if len(o.venues) > 0 {
		venue = o.venues[0]
	}
	u := o.buildURL(venue, 1)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return fmt.Errorf("构造探针请求失败: %w", err)
	}
	resp, err := o.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("请求 OpenAlex 失败: %w", err)
	}
	defer resp.Body.Close()
	// 丢弃响应体，仅校验状态码
	_, _ = io.Copy(io.Discard, resp.Body)
	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("OpenAlex 探针请求返回非 200: status=%d", resp.StatusCode)
	}
	return nil
}

// fetchWorks 拉取指定 venue 的一页 works。
func (o *OpenAlexSource) fetchWorks(ctx context.Context, venue string) ([]oaWork, error) {
	u := o.buildURL(venue, o.perPage)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Accept", "application/json")

	resp, err := o.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("请求 OpenAlex API 失败: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusTooManyRequests {
		return nil, fmt.Errorf("OpenAlex API 限流（status=429），请配置 mailto 走 polite pool 或稍后重试")
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("OpenAlex API 返回非 200: status=%d", resp.StatusCode)
	}

	var body oaResponse
	if err := json.NewDecoder(resp.Body).Decode(&body); err != nil {
		return nil, fmt.Errorf("解析 OpenAlex 响应失败: %w", err)
	}
	return body.Results, nil
}

// buildURL 拼装 /works 请求 URL。
// filter 的冒号保持字面量（OpenAlex 约定），venue 与 mailto 经 QueryEscape 转义。
func (o *OpenAlexSource) buildURL(venue string, perPage int) string {
	u := o.baseURL + "/works?filter=primary_location.source.display_name:" + url.QueryEscape(venue) +
		"&per_page=" + fmt.Sprintf("%d", perPage)
	if o.mailto != "" {
		u += "&mailto=" + url.QueryEscape(o.mailto)
	}
	return u
}

// workToMeta 将单篇 oaWork 转换为 PaperMeta。
//   - authors：拼接 authorships 中所有 author.display_name（逗号分隔）；
//   - abstract：由 abstract_inverted_index 倒排索引重建；
//   - pdf_url：取 best_oa_location.pdf_url，location 为 null 或字段为空时留空；
//   - doi：去掉 "https://doi.org/" 前缀，只保留 DOI 本体；
//   - venue：取 primary_location.source.display_name。
func (o *OpenAlexSource) workToMeta(w oaWork) PaperMeta {
	// authors 拼接
	authorNames := make([]string, 0, len(w.Authorships))
	for _, a := range w.Authorships {
		if a.Author.DisplayName != "" {
			authorNames = append(authorNames, a.Author.DisplayName)
		}
	}

	// venue 提取
	venue := ""
	if w.PrimaryLocation != nil && w.PrimaryLocation.Source != nil {
		venue = w.PrimaryLocation.Source.DisplayName
	}

	// pdf_url 提取（best_oa_location 可能为 null）
	pdfURL := ""
	if w.BestOALocation != nil {
		pdfURL = w.BestOALocation.PDFURL
	}

	return PaperMeta{
		Title:    w.DisplayName,
		Authors:  strings.Join(authorNames, ", "),
		Year:     w.PublicationYear,
		Abstract: rebuildAbstract(w.AbstractInvertedIndex),
		PDFURL:   pdfURL,
		DOI:      stripDOIPrefix(w.DOI),
		Source:   "openalex",
		Venue:    venue,
	}
}

// rebuildAbstract 由 OpenAlex 倒排索引重建摘要文本。
// 输入：{"word": [pos1, pos2]}；输出：按 position 排序后空格拼接的字符串。
// 空输入返回空串。
func rebuildAbstract(inverted map[string][]int) string {
	if len(inverted) == 0 {
		return ""
	}
	type posWord struct {
		pos  int
		word string
	}
	pairs := make([]posWord, 0, len(inverted))
	for word, positions := range inverted {
		for _, pos := range positions {
			pairs = append(pairs, posWord{pos: pos, word: word})
		}
	}
	sort.Slice(pairs, func(i, j int) bool {
		return pairs[i].pos < pairs[j].pos
	})
	words := make([]string, len(pairs))
	for i, p := range pairs {
		words[i] = p.word
	}
	return strings.Join(words, " ")
}

// stripDOIPrefix 去掉 DOI 字段的 "https://doi.org/" 前缀。
// 同时兼容 "http://doi.org/" 与大小写差异；无前缀时原样返回。
func stripDOIPrefix(doi string) string {
	for _, prefix := range []string{"https://doi.org/", "http://doi.org/"} {
		if strings.HasPrefix(strings.ToLower(doi), prefix) {
			return doi[len(prefix):]
		}
	}
	return doi
}
