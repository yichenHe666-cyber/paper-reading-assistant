// Package paper 的 OpenAlex 数据源测试。
//
// 文件概述：openalex_source_test.go 用 httptest mock server 模拟 OpenAlex /works 接口，
// 验证 OpenAlexSource 的字段提取契约：
//   - venue 从 primary_location.source.display_name 获取；
//   - abstract_inverted_index 倒排索引正确重建为正常文本；
//   - pdf_url 从 best_oa_location.pdf_url 提取，含 null 情况；
//   - doi 去掉 "https://doi.org/" 前缀；
//   - authors 从 authorships 拼接。
//
// 不依赖真实网络，可在离线环境运行。
package paper

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// mockOpenAlexServer 模拟 OpenAlex /works 接口：
//   - ACL：返回 2 篇论文（一篇有 pdf_url，一篇 best_oa_location 为 null）；
//   - CVPR：返回 1 篇论文；
//   - 其他 venue：返回空结果。
//
// 同时校验请求参数中携带 filter、per_page、mailto。
func mockOpenAlexServer(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")

		// 校验请求路径与关键参数
		if r.URL.Path != "/works" {
			t.Errorf("未预期的请求路径: %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
			return
		}
		filter := r.URL.Query().Get("filter")
		if filter == "" {
			t.Error("请求缺少 filter 参数")
		}
		if r.URL.Query().Get("per_page") == "" {
			t.Error("请求缺少 per_page 参数")
		}
		if r.URL.Query().Get("mailto") == "" {
			t.Error("请求缺少 mailto 参数")
		}

		// 按 filter 中的 venue 名分发不同响应
		var resp oaResponse
		switch {
		case strings.Contains(filter, "ACL"):
			resp = oaResponse{Results: []oaWork{
				{
					ID:              "https://openalex.org/W111",
					DisplayName:     "Attention Is All You Need",
					PublicationYear: 2017,
					DOI:             "https://doi.org/10.5555/3295222.3295349",
					AbstractInvertedIndex: map[string][]int{
						"Attention": {0},
						"is":        {1, 5},
						"all":       {2},
						"you":       {3},
						"need":      {4},
					},
					Authorships: []oaAuthorship{
						{Author: struct {
							DisplayName string `json:"display_name"`
						}{DisplayName: "Ashish Vaswani"}},
						{Author: struct {
							DisplayName string `json:"display_name"`
						}{DisplayName: "Noam Shazeer"}},
					},
					PrimaryLocation: &oaLocation{
						Source: &oaSource{DisplayName: "ACL"},
					},
					BestOALocation: &oaLocation{
						PDFURL: "https://aclanthology.org/P17-1001.pdf",
					},
				},
				{
					ID:              "https://openalex.org/W222",
					DisplayName:     "Closed Access Paper Without PDF",
					PublicationYear: 2020,
					DOI:             "https://doi.org/10.0000/closed",
					AbstractInvertedIndex: map[string][]int{
						"No":     {0},
						"open":   {1},
						"access": {2},
					},
					Authorships: []oaAuthorship{
						{Author: struct {
							DisplayName string `json:"display_name"`
						}{DisplayName: "Anonymous Author"}},
					},
					PrimaryLocation: &oaLocation{
						Source: &oaSource{DisplayName: "ACL"},
					},
					// best_oa_location 为 null（闭源论文）
					BestOALocation: nil,
				},
			}}
		case strings.Contains(filter, "CVPR"):
			resp = oaResponse{Results: []oaWork{
				{
					ID:              "https://openalex.org/W333",
					DisplayName:     "Deep Residual Learning",
					PublicationYear: 2016,
					DOI:             "https://doi.org/10.1109/CVPR.2016.90",
					AbstractInvertedIndex: map[string][]int{
						"Deep":     {0},
						"residual": {1},
						"learning": {2},
						"networks": {3, 4},
					},
					Authorships: []oaAuthorship{
						{Author: struct {
							DisplayName string `json:"display_name"`
						}{DisplayName: "Kaiming He"}},
					},
					PrimaryLocation: &oaLocation{
						Source: &oaSource{DisplayName: "CVPR"},
					},
					BestOALocation: &oaLocation{
						PDFURL: "https://example.com/resnet.pdf",
					},
				},
			}}
		default:
			resp = oaResponse{Results: []oaWork{}}
		}

		_ = json.NewEncoder(w).Encode(resp)
	}))
}

// TestOpenAlexSourceSync 验证 Sync 流程：venue 提取、倒排索引重建、pdf_url null 处理、doi 去前缀。
func TestOpenAlexSourceSync(t *testing.T) {
	srv := mockOpenAlexServer(t)
	defer srv.Close()

	src := NewOpenAlexSourceWithBaseURL(srv.URL, "team@example.com", []string{"ACL", "CVPR"}, 50)

	metas, err := src.Sync(context.Background())
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	// ACL 返回 2 篇 + CVPR 返回 1 篇
	if len(metas) != 3 {
		t.Fatalf("论文数: got %d want 3", len(metas))
	}

	// 定位 ACL 第一篇（Attention Is All You Need）
	var attn *PaperMeta
	var closed *PaperMeta
	var resnet *PaperMeta
	for i := range metas {
		switch metas[i].Title {
		case "Attention Is All You Need":
			attn = &metas[i]
		case "Closed Access Paper Without PDF":
			closed = &metas[i]
		case "Deep Residual Learning":
			resnet = &metas[i]
		}
	}
	if attn == nil || closed == nil || resnet == nil {
		t.Fatalf("未找到全部 3 篇论文: %+v", metas)
	}

	// 1. venue 从 primary_location.source.display_name 获取
	if attn.Venue != "ACL" {
		t.Errorf("attn Venue: got %q want ACL", attn.Venue)
	}
	if resnet.Venue != "CVPR" {
		t.Errorf("resnet Venue: got %q want CVPR", resnet.Venue)
	}

	// 2. abstract_inverted_index 重建正确（注意 "is" 出现在 pos 1 和 5）
	wantAbstract := "Attention is all you need is"
	if attn.Abstract != wantAbstract {
		t.Errorf("attn Abstract: got %q want %q", attn.Abstract, wantAbstract)
	}
	// 3. authors 从 authorships 拼接
	if attn.Authors != "Ashish Vaswani, Noam Shazeer" {
		t.Errorf("attn Authors: got %q want %q", attn.Authors, "Ashish Vaswani, Noam Shazeer")
	}

	// 4. pdf_url 提取（正常情况）
	if attn.PDFURL != "https://aclanthology.org/P17-1001.pdf" {
		t.Errorf("attn PDFURL: got %q want https://aclanthology.org/P17-1001.pdf", attn.PDFURL)
	}
	// 5. pdf_url null 情况：best_oa_location 为 null 时 PDFURL 应为空串
	if closed.PDFURL != "" {
		t.Errorf("closed PDFURL 应为空（best_oa_location=null），实际 %q", closed.PDFURL)
	}
	// closed 论文 venue 仍应正确提取
	if closed.Venue != "ACL" {
		t.Errorf("closed Venue: got %q want ACL", closed.Venue)
	}

	// 6. doi 去掉 "https://doi.org/" 前缀
	if attn.DOI != "10.5555/3295222.3295349" {
		t.Errorf("attn DOI: got %q want 10.5555/3295222.3295349", attn.DOI)
	}
	if resnet.DOI != "10.1109/CVPR.2016.90" {
		t.Errorf("resnet DOI: got %q want 10.1109/CVPR.2016.90", resnet.DOI)
	}

	// 7. year 提取
	if attn.Year != 2017 {
		t.Errorf("attn Year: got %d want 2017", attn.Year)
	}
	if resnet.Year != 2016 {
		t.Errorf("resnet Year: got %d want 2016", resnet.Year)
	}

	// 8. Source 字段固定为 "openalex"
	for i, m := range metas {
		if m.Source != "openalex" {
			t.Errorf("metas[%d].Source: got %q want openalex", i, m.Source)
		}
	}
}

// TestOpenAlexRebuildAbstract 直接验证倒排索引重建逻辑，覆盖乱序、重复 position、空输入。
func TestOpenAlexRebuildAbstract(t *testing.T) {
	cases := []struct {
		name string
		in   map[string][]int
		want string
	}{
		{
			name: "顺序输入应按 position 排序",
			in:   map[string][]int{"This": {0}, "is": {1}, "abstract": {2}},
			want: "This is abstract",
		},
		{
			name: "乱序输入应按 position 排序重建",
			in:   map[string][]int{"abstract": {2}, "This": {0}, "is": {1}},
			want: "This is abstract",
		},
		{
			name: "同一词出现在多个位置应重复出现",
			in:   map[string][]int{"the": {0, 3}, "cat": {1}, "sat": {2}},
			want: "the cat sat the",
		},
		{
			name: "空输入返回空串",
			in:   map[string][]int{},
			want: "",
		},
		{
			name: "nil 输入返回空串",
			in:   nil,
			want: "",
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := rebuildAbstract(c.in)
			if got != c.want {
				t.Errorf("rebuildAbstract() = %q, want %q", got, c.want)
			}
		})
	}
}

// TestOpenAlexStripDOIPrefix 验证 DOI 前缀去除逻辑。
func TestOpenAlexStripDOIPrefix(t *testing.T) {
	cases := []struct {
		in, want string
	}{
		{"https://doi.org/10.5555/3295222.3295349", "10.5555/3295222.3295349"},
		{"http://doi.org/10.1109/CVPR.2016.90", "10.1109/CVPR.2016.90"},
		{"HTTPS://DOI.ORG/10.0000/upper", "10.0000/upper"},
		{"10.0000/no_prefix", "10.0000/no_prefix"},
		{"", ""},
	}
	for _, c := range cases {
		got := stripDOIPrefix(c.in)
		if got != c.want {
			t.Errorf("stripDOIPrefix(%q) = %q, want %q", c.in, got, c.want)
		}
	}
}

// TestOpenAlexSourceIDName 验证源标识与名称。
func TestOpenAlexSourceIDName(t *testing.T) {
	src := NewOpenAlexSource("team@example.com", nil, 0)
	if src.ID() != "openalex" {
		t.Errorf("ID(): got %q want openalex", src.ID())
	}
	if src.Name() != "OpenAlex 学术索引" {
		t.Errorf("Name(): got %q want OpenAlex 学术索引", src.Name())
	}
	// 默认 venues 与 perPage
	if len(src.venues) != 6 {
		t.Errorf("默认 venues 长度: got %d want 6", len(src.venues))
	}
	if src.perPage != 50 {
		t.Errorf("默认 perPage: got %d want 50", src.perPage)
	}
}

// TestOpenAlexSourceTestConnection 验证探针请求成功路径与错误路径。
func TestOpenAlexSourceTestConnection(t *testing.T) {
	// 成功路径：mock 返回 200
	okSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"results":[]}`))
	}))
	defer okSrv.Close()

	src := NewOpenAlexSourceWithBaseURL(okSrv.URL, "team@example.com", []string{"ACL"}, 50)
	if err := src.TestConnection(); err != nil {
		t.Errorf("TestConnection 成功路径应无错误，实际: %v", err)
	}

	// 失败路径：mock 返回 500
	errSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer errSrv.Close()

	srcErr := NewOpenAlexSourceWithBaseURL(errSrv.URL, "team@example.com", []string{"ACL"}, 50)
	if err := srcErr.TestConnection(); err == nil {
		t.Error("TestConnection 失败路径应返回错误")
	}
}

// TestOpenAlexSourceRateLimit 验证 429 限流被识别为明确错误。
func TestOpenAlexSourceRateLimit(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusTooManyRequests)
	}))
	defer srv.Close()

	src := NewOpenAlexSourceWithBaseURL(srv.URL, "team@example.com", []string{"ACL"}, 50)
	_, err := src.Sync(context.Background())
	if err == nil {
		t.Fatal("限流应返回错误")
	}
	if !strings.Contains(err.Error(), "限流") {
		t.Errorf("错误应提及限流，实际: %v", err)
	}
}
