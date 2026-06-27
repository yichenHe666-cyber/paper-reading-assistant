// Package paper 的 GitHub 同步测试。
//
// 文件概述：github_test.go 用 httptest mock server 模拟 GitHub Contents API，
// 验证 Sync 流程：根目录列主题 → 主题目录列论文 → 幂等落库。
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

// mockGitHubServer 模拟 GitHub Contents API：
//   - 根目录：返回 1 个主题目录 + 1 个无关文件（README）；
//   - 主题目录：返回 1 个 pdf 文件 + 1 个子目录（论文条目）。
func mockGitHubServer(t *testing.T) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		// 规范化路径：去除末尾斜杠后比较
		p := strings.TrimSuffix(r.URL.Path, "/")

		switch p {
		case "/repos/pwl/papers/contents":
			// 根目录：1 主题目录 + 1 文件
			json.NewEncoder(w).Encode([]ghContent{
				{Name: "distributed_systems", Path: "distributed_systems", Type: "dir"},
				{Name: "README.md", Path: "README.md", Type: "file", DownloadURL: "http://raw/readme"},
			})
		case "/repos/pwl/papers/contents/distributed_systems":
			// 主题目录：1 pdf + 1 子目录
			json.NewEncoder(w).Encode([]ghContent{
				{Name: "mapreduce.pdf", Path: "distributed_systems/mapreduce.pdf", Type: "file", DownloadURL: "http://raw/mr.pdf"},
				{Name: "gfs_subdir", Path: "distributed_systems/gfs_subdir", Type: "dir"},
			})
		default:
			// 未预期的路径返回 404，便于测试发现拼装错误
			t.Errorf("未预期的 GitHub API 请求路径: %s", r.URL.Path)
			w.WriteHeader(http.StatusNotFound)
		}
	}))
}

// TestSyncFromGitHub 验证同步后主题与论文正确落库。
func TestSyncFromGitHub(t *testing.T) {
	srv := mockGitHubServer(t)
	defer srv.Close()

	repo, db, _ := openTestRepo(t)
	defer db.Close()

	// 构造 client 并将 baseURL 指向 mock server
	g := NewGitHubClient("")
	g.baseURL = srv.URL

	result, err := g.Sync(context.Background(), repo, "pwl", "papers")
	if err != nil {
		t.Fatalf("Sync 失败: %v", err)
	}
	if result.TopicsAdded != 1 {
		t.Errorf("TopicsAdded: got %d want 1", result.TopicsAdded)
	}
	// 2 个论文条目（1 pdf + 1 子目录）
	if result.PapersAdded != 2 {
		t.Errorf("PapersAdded: got %d want 2", result.PapersAdded)
	}

	// 验证主题落库
	topics, _ := repo.ListTopics()
	if len(topics) != 1 || topics[0].ID != "distributed_systems" {
		t.Errorf("主题落库错误: %+v", topics)
	}
	// 验证论文落库
	papers, _ := repo.ListPapers("distributed_systems")
	if len(papers) != 2 {
		t.Fatalf("论文数: got %d want 2", len(papers))
	}
	// 验证 pdf 论文的 download_url 正确
	var mr *Paper
	for i := range papers {
		if papers[i].Title == "mapreduce" {
			mr = &papers[i]
		}
	}
	if mr == nil {
		t.Fatal("未找到 mapreduce 论文")
	}
	if mr.PDFURL != "http://raw/mr.pdf" {
		t.Errorf("PDFURL: got %q want http://raw/mr.pdf", mr.PDFURL)
	}
}

// TestSyncIdempotent 验证重复同步不产生重复行。
func TestSyncIdempotent(t *testing.T) {
	srv := mockGitHubServer(t)
	defer srv.Close()

	repo, db, _ := openTestRepo(t)
	defer db.Close()

	g := NewGitHubClient("")
	g.baseURL = srv.URL

	if _, err := g.Sync(context.Background(), repo, "pwl", "papers"); err != nil {
		t.Fatal(err)
	}
	// 第二次同步
	if _, err := g.Sync(context.Background(), repo, "pwl", "papers"); err != nil {
		t.Fatal(err)
	}

	n, _ := repo.CountPapers()
	if n != 2 {
		t.Errorf("重复同步后论文数应为 2（幂等），实际 %d", n)
	}
	topics, _ := repo.ListTopics()
	if len(topics) != 1 {
		t.Errorf("重复同步后主题数应为 1（幂等），实际 %d", len(topics))
	}
}

// TestSyncRateLimit 验证 rate limit 错误被明确识别。
func TestSyncRateLimit(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("X-RateLimit-Remaining", "0")
		w.WriteHeader(http.StatusForbidden)
	}))
	defer srv.Close()

	repo, db, _ := openTestRepo(t)
	defer db.Close()

	g := NewGitHubClient("")
	g.baseURL = srv.URL

	_, err := g.Sync(context.Background(), repo, "pwl", "papers")
	if err == nil {
		t.Fatal("rate limit 应返回错误")
	}
	if !strings.Contains(err.Error(), "限流") {
		t.Errorf("错误应提及限流，实际: %v", err)
	}
}
