// Package paper 的 ACL Anthology 数据源适配器测试。
//
// 文件概述：acl_source_test.go 用 httptest mock server 验证 ACLAnthologySource：
//   - 论文链接正则提取（忽略非论文链接）；
//   - BibTeX 正则解析（title/author/year/doi/booktitle）；
//   - author 按 " and " 分割并取姓氏；
//   - arXiv ID 从 url/note 字段提取；
//   - Sync 端到端：HTML 页面 + .bib 响应 → PaperMeta，含 PDF 直链拼接；
//   - maxPerConf 限量拉取。
package paper

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

// aclMockHTML 模拟会议事件页 HTML，含论文链接与非论文链接（应被忽略）。
const aclMockHTML = `<html><body>
<div class="main">
  <a href="/2023.acl-long.1/">Paper 1</a>
  <a href="/2023.acl-long.2/">Paper 2</a>
  <a href="/2023.acl-short.3/">Paper 3</a>
  <a href="/about/">About</a>
  <a href="/archives/">Archives</a>
</div>
</body></html>`

// aclMockBib1 模拟标准 BibTeX（无 arXiv）。
const aclMockBib1 = `@inproceedings{liu-etal-2023-one,
    title = "One Cannot Stand for Everyone!",
    author = "Liu, Yajao and Jiang, Xin",
    booktitle = "Proceedings of the 61st Annual Meeting of the ACL",
    year = "2023",
    url = "https://aclanthology.org/2023.acl-long.1/",
    doi = "10.18653/v1/2023.acl-long.1"
}`

// aclMockBib2 模拟 BibTeX，url 字段含 arXiv 链接。
const aclMockBib2 = `@inproceedings{smith-2023-transformer,
    title = "A Transformer Approach for NLP",
    author = "Smith, John and Doe, Jane and Brown, Charlie",
    booktitle = "Proceedings of the 61st Annual Meeting of the ACL",
    year = "2023",
    url = "https://arxiv.org/abs/2305.12345",
    doi = "10.18653/v1/2023.acl-long.2"
}`

// aclMockBib3 模拟 BibTeX，note 字段含 arXiv: 前缀。
const aclMockBib3 = `@inproceedings{short-2023-paper,
    title = "Short Paper Example",
    author = "Wang, Wei",
    booktitle = "Proceedings of the 61st Annual Meeting of the ACL",
    year = "2023",
    note = "arXiv:2306.67890",
    doi = "10.18653/v1/2023.acl-short.3"
}`

// newMockACLServer 启动一个 httptest server 模拟 ACL Anthology 站点。
func newMockACLServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	mux.HandleFunc("/events/acl-2023/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/html")
		_, _ = w.Write([]byte(aclMockHTML))
	})
	mux.HandleFunc("/2023.acl-long.1.bib", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		_, _ = w.Write([]byte(aclMockBib1))
	})
	mux.HandleFunc("/2023.acl-long.2.bib", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		_, _ = w.Write([]byte(aclMockBib2))
	})
	mux.HandleFunc("/2023.acl-short.3.bib", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		_, _ = w.Write([]byte(aclMockBib3))
	})
	return httptest.NewServer(mux)
}

// TestACLAnthologySourceIDs 验证 ID/Name 常量。
func TestACLAnthologySourceIDs(t *testing.T) {
	src := &ACLAnthologySource{}
	if src.ID() != "acl" {
		t.Errorf("ID(): got %q want %q", src.ID(), "acl")
	}
	if src.Name() != "ACL Anthology NLP 论文" {
		t.Errorf("Name(): got %q want %q", src.Name(), "ACL Anthology NLP 论文")
	}
}

// TestACLExtractPaperIDs 验证从 HTML 正则提取论文链接，忽略非论文链接。
func TestACLExtractPaperIDs(t *testing.T) {
	ids := extractPaperIDs(aclMockHTML)
	want := []string{"/2023.acl-long.1", "/2023.acl-long.2", "/2023.acl-short.3"}
	if len(ids) != len(want) {
		t.Fatalf("extractPaperIDs 长度: got %d want %d (ids=%v)", len(ids), len(want), ids)
	}
	for i, id := range ids {
		if id != want[i] {
			t.Errorf("extractPaperIDs[%d]: got %q want %q", i, id, want[i])
		}
	}
}

// TestACLParseBibTeX 验证 BibTeX 解析：title/author/year/doi/booktitle。
func TestACLParseBibTeX(t *testing.T) {
	meta := parseBibTeX(aclMockBib1)
	if meta.Title != "One Cannot Stand for Everyone!" {
		t.Errorf("Title: got %q want %q", meta.Title, "One Cannot Stand for Everyone!")
	}
	// "Liu, Yajao and Jiang, Xin" -> 取姓氏 -> "Liu, Jiang"
	if meta.Authors != "Liu, Jiang" {
		t.Errorf("Authors: got %q want %q", meta.Authors, "Liu, Jiang")
	}
	if meta.Year != 2023 {
		t.Errorf("Year: got %d want 2023", meta.Year)
	}
	if meta.DOI != "10.18653/v1/2023.acl-long.1" {
		t.Errorf("DOI: got %q want %q", meta.DOI, "10.18653/v1/2023.acl-long.1")
	}
	if meta.Venue != "Proceedings of the 61st Annual Meeting of the ACL" {
		t.Errorf("Venue: got %q want %q", meta.Venue, "Proceedings of the 61st Annual Meeting of the ACL")
	}
}

// TestACLParseBibTeXAuthors 验证 author 按 " and " 分割（三作者场景）。
func TestACLParseBibTeXAuthors(t *testing.T) {
	meta := parseBibTeX(aclMockBib2)
	// "Smith, John and Doe, Jane and Brown, Charlie" -> "Smith, Doe, Brown"
	if meta.Authors != "Smith, Doe, Brown" {
		t.Errorf("Authors: got %q want %q", meta.Authors, "Smith, Doe, Brown")
	}
}

// TestACLExtractArxivID 验证从 url/note 字段提取 arXiv ID。
func TestACLExtractArxivID(t *testing.T) {
	// url 字段含 arxiv 链接
	meta2 := parseBibTeX(aclMockBib2)
	if meta2.ArxivID != "2305.12345" {
		t.Errorf("ArxivID (url): got %q want %q", meta2.ArxivID, "2305.12345")
	}
	// note 字段含 arXiv: 前缀
	meta3 := parseBibTeX(aclMockBib3)
	if meta3.ArxivID != "2306.67890" {
		t.Errorf("ArxivID (note): got %q want %q", meta3.ArxivID, "2306.67890")
	}
	// 无 arxiv 时为空
	meta1 := parseBibTeX(aclMockBib1)
	if meta1.ArxivID != "" {
		t.Errorf("ArxivID (none): got %q want empty", meta1.ArxivID)
	}
}

// TestACLAnthologySourceSync 端到端验证：mock HTML + .bib → PaperMeta。
func TestACLAnthologySourceSync(t *testing.T) {
	server := newMockACLServer(t)
	defer server.Close()

	src := &ACLAnthologySource{
		httpClient:  &http.Client{},
		baseURL:     server.URL,
		conferences: []string{"acl"},
		maxPerConf:  50,
		year:        2023,
	}

	metas, err := src.Sync(context.Background())
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	if len(metas) != 3 {
		t.Fatalf("Sync 论文数: got %d want 3", len(metas))
	}

	// 第一篇验证全字段
	p1 := metas[0]
	if p1.Title != "One Cannot Stand for Everyone!" {
		t.Errorf("p1 Title: got %q", p1.Title)
	}
	if p1.Authors != "Liu, Jiang" {
		t.Errorf("p1 Authors: got %q want %q", p1.Authors, "Liu, Jiang")
	}
	if p1.Year != 2023 {
		t.Errorf("p1 Year: got %d want 2023", p1.Year)
	}
	if p1.DOI != "10.18653/v1/2023.acl-long.1" {
		t.Errorf("p1 DOI: got %q", p1.DOI)
	}
	if p1.Source != "acl" {
		t.Errorf("p1 Source: got %q want %q", p1.Source, "acl")
	}
	// PDF 直链拼接验证
	wantPDF1 := server.URL + "/2023.acl-long.1.pdf"
	if p1.PDFURL != wantPDF1 {
		t.Errorf("p1 PDFURL: got %q want %q", p1.PDFURL, wantPDF1)
	}

	// 第二篇验证 arxiv_id 从 url 提取 + PDF 直链
	p2 := metas[1]
	if p2.ArxivID != "2305.12345" {
		t.Errorf("p2 ArxivID: got %q want %q", p2.ArxivID, "2305.12345")
	}
	wantPDF2 := server.URL + "/2023.acl-long.2.pdf"
	if p2.PDFURL != wantPDF2 {
		t.Errorf("p2 PDFURL: got %q want %q", p2.PDFURL, wantPDF2)
	}

	// 第三篇验证 arxiv_id 从 note 提取
	p3 := metas[2]
	if p3.ArxivID != "2306.67890" {
		t.Errorf("p3 ArxivID: got %q want %q", p3.ArxivID, "2306.67890")
	}
}

// TestACLAnthologySourceMaxPerConf 验证 maxPerConf 限量拉取。
func TestACLAnthologySourceMaxPerConf(t *testing.T) {
	server := newMockACLServer(t)
	defer server.Close()

	src := &ACLAnthologySource{
		httpClient:  &http.Client{},
		baseURL:     server.URL,
		conferences: []string{"acl"},
		maxPerConf:  2,
		year:        2023,
	}
	metas, err := src.Sync(context.Background())
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	if len(metas) != 2 {
		t.Errorf("maxPerConf=2 应只拉取 2 篇: got %d want 2", len(metas))
	}
}
