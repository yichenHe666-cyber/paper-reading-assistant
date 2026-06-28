// Package paper 的 arXiv 数据源测试。
//
// 文件概述：arxiv_source_test.go 用 httptest mock server 模拟 arXiv Atom API，
// 验证：
//   - XML 解析正确（标题/摘要/年份）；
//   - arxiv_id 提取（去版本号 vN）；
//   - 多作者逗号拼接；
//   - pdf_url 从 type="application/pdf" 的 link 提取；
//   - 全部分类被拉取；
//   - TestConnection 连通性判定。
// 不依赖真实网络，可在离线环境运行。
package paper

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

// arxivSampleXML 模拟 arXiv API 返回的 Atom feed：
//   - 第一篇：id 带版本号 v1、标题含多余空白、2 作者、含 alternate+pdf 两个 link；
//   - 第二篇：id 无版本号、1 作者。
const arxivSampleXML = `<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2305.14996v1</id>
    <title>  QLoRA: Efficient Finetuning   of Quantized LLMs  </title>
    <summary>We introduce QLoRA, an efficient finetuning approach.</summary>
    <author><name>Tim Dettmers</name></author>
    <author><name>Mike Wu</name></author>
    <link href="http://arxiv.org/abs/2305.14996v1" rel="alternate" type="text/html"/>
    <link href="http://arxiv.org/pdf/2305.14996v1" rel="related" type="application/pdf" title="pdf"/>
    <published>2023-05-24T18:59:00Z</published>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/1706.03762</id>
    <title>Attention Is All You Need</title>
    <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks.</summary>
    <author><name>Ashish Vaswani</name></author>
    <link href="http://arxiv.org/pdf/1706.03762" rel="related" type="application/pdf" title="pdf"/>
    <published>2017-06-12T17:59:00Z</published>
  </entry>
</feed>`

// mockArxivServer 模拟 arXiv API，并记录被请求的分类（用于验证分类全覆盖）。
func mockArxivServer(t *testing.T, requestedCats *[]string, mu *sync.Mutex) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/atom+xml")
		// 解析 search_query=cat:cs.AI 提取分类
		cat := r.URL.Query().Get("search_query")
		cat = strings.TrimPrefix(cat, "cat:")
		mu.Lock()
		*requestedCats = append(*requestedCats, cat)
		mu.Unlock()
		w.Write([]byte(arxivSampleXML))
	}))
}

// TestArxivSync 验证 XML 解析、arxiv_id 提取、作者拼接、pdf_url 提取、分类全覆盖。
func TestArxivSync(t *testing.T) {
	var (
		mu            sync.Mutex
		requestedCats []string
	)
	srv := mockArxivServer(t, &requestedCats, &mu)
	defer srv.Close()

	src := NewArxivSourceWithBaseURL(srv.URL)
	metas, err := src.Sync(context.Background())
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}

	// 6 分类 × 2 条目 = 12
	if len(metas) != 12 {
		t.Fatalf("论文数: got %d want 12", len(metas))
	}

	// 验证所有默认分类被拉取
	wantCats := map[string]bool{
		"cs.AI": false, "cs.CL": false, "cs.LG": false,
		"cs.CV": false, "cs.CR": false, "cs.DC": false,
	}
	mu.Lock()
	for _, c := range requestedCats {
		if _, ok := wantCats[c]; ok {
			wantCats[c] = true
		}
	}
	mu.Unlock()
	if got := len(requestedCats); got != 6 {
		t.Errorf("请求数: got %d want 6", got)
	}
	for c, hit := range wantCats {
		if !hit {
			t.Errorf("分类 %s 未被拉取", c)
		}
	}

	// 验证第一篇（QLoRA）字段：arxiv_id 去版本号、标题去空白、多作者拼接、pdf_url、年份
	var qlora *PaperMeta
	for i := range metas {
		if metas[i].ArxivID == "2305.14996" {
			qlora = &metas[i]
			break
		}
	}
	if qlora == nil {
		t.Fatal("未找到 arxiv_id=2305.14996 的论文（版本号未正确去除？）")
	}
	if qlora.Title != "QLoRA: Efficient Finetuning of Quantized LLMs" {
		t.Errorf("Title: got %q want %q", qlora.Title, "QLoRA: Efficient Finetuning of Quantized LLMs")
	}
	if qlora.Authors != "Tim Dettmers, Mike Wu" {
		t.Errorf("Authors: got %q want %q", qlora.Authors, "Tim Dettmers, Mike Wu")
	}
	if qlora.PDFURL != "http://arxiv.org/pdf/2305.14996v1" {
		t.Errorf("PDFURL: got %q want http://arxiv.org/pdf/2305.14996v1", qlora.PDFURL)
	}
	if qlora.Year != 2023 {
		t.Errorf("Year: got %d want 2023", qlora.Year)
	}
	if qlora.Source != "arxiv" {
		t.Errorf("Source: got %q want arxiv", qlora.Source)
	}
	if qlora.Abstract == "" {
		t.Error("Abstract 不应为空")
	}

	// 验证无版本号的 id 也能正确提取
	var attn *PaperMeta
	for i := range metas {
		if metas[i].ArxivID == "1706.03762" {
			attn = &metas[i]
			break
		}
	}
	if attn == nil {
		t.Fatal("未找到 arxiv_id=1706.03762 的论文")
	}
	if attn.Year != 2017 {
		t.Errorf("Year: got %d want 2017", attn.Year)
	}
	if attn.Authors != "Ashish Vaswani" {
		t.Errorf("Authors: got %q want %q", attn.Authors, "Ashish Vaswani")
	}
}

// TestArxivIDExtraction 验证 arxiv_id 提取与版本号去除的边界情况。
func TestArxivIDExtraction(t *testing.T) {
	cases := []struct{ in, want string }{
		{"http://arxiv.org/abs/2305.14996v1", "2305.14996"},
		{"http://arxiv.org/abs/1706.03762", "1706.03762"},
		{"http://arxiv.org/abs/2303.08774v12", "2303.08774"},
	}
	for _, c := range cases {
		got := arxivIDFromURL(c.in)
		if got != c.want {
			t.Errorf("arxivIDFromURL(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

// TestArxivTestConnection 验证连通性测试成功路径。
func TestArxivTestConnection(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/atom+xml")
		w.Write([]byte(`<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>`))
	}))
	defer srv.Close()

	src := NewArxivSourceWithBaseURL(srv.URL)
	if err := src.TestConnection(); err != nil {
		t.Fatalf("TestConnection 应成功: %v", err)
	}
}

// TestArxivTestConnectionFailure 验证非 200 返回错误。
func TestArxivTestConnectionFailure(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	src := NewArxivSourceWithBaseURL(srv.URL)
	if err := src.TestConnection(); err == nil {
		t.Fatal("500 应返回错误")
	}
}
