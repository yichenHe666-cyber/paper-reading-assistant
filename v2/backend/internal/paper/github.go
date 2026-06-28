// Package paper 的 GitHub 同步实现。
//
// 文件概述：github.go 通过 GitHub Contents API 从 Papers We Love 仓库同步论文元数据：
//   1. 列仓库根目录 → 得到主题分类（type=dir 的条目）；
//   2. 列每个主题目录 → 得到论文条目（.pdf 文件或子目录）；
//   3. 通过 Repository.UpsertTopic / UpsertPaper 幂等落库；
//   4. UpdatePaperCount 刷新各主题论文计数。
//
// 数据源：https://github.com/papers-we-love/papers-we-love
// API：GET /repos/{owner}/{repo}/contents/{path}
//   - 无 token：60 次/小时；带 token：5000 次/小时（推荐配置 GITHUB_TOKEN）。
//
// 设计要点：
//   - 同步只取元数据（标题/路径/下载地址），不下载 PDF 内容（PDF 阅读器首期跳过）；
//   - 完全幂等：重复同步靠 Upsert 去重，不会产生重复行；
//   - rate limit 友好：API 调用数 = 1 + 主题数（约几十次），单次同步在免费额度内。
package paper

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// GitHubClient 是 GitHub Contents API 的最小客户端。
type GitHubClient struct {
	token  string
	http   *http.Client
	baseURL string // 默认 https://api.github.com，可覆盖用于测试
}

// NewGitHubClient 构造客户端。token 为空时走匿名访问（受 60/hour 限制）。
func NewGitHubClient(token string) *GitHubClient {
	return &GitHubClient{
		token:   token,
		http:    &http.Client{Timeout: 30 * time.Second},
		baseURL: "https://api.github.com",
	}
}

// NewGitHubClientWithBaseURL 构造指定 baseURL 的客户端。
// 主要供测试注入 httptest mock server；生产代码用 NewGitHubClient。
func NewGitHubClientWithBaseURL(token, baseURL string) *GitHubClient {
	c := NewGitHubClient(token)
	c.baseURL = baseURL
	return c
}

// ghContent 对应 GitHub Contents API 的单条响应。
type ghContent struct {
	Name        string `json:"name"`          // 文件/目录名
	Path        string `json:"path"`          // 仓库内相对路径
	Type        string `json:"type"`          // "dir" | "file" | "symlink"
	DownloadURL string `json:"download_url"`  // 文件下载地址（目录为空）
}

// GitHubSyncResult 描述一次 GitHub 同步的统计。
type GitHubSyncResult struct {
	TopicsAdded int // 处理的主题数（含已存在的，因 Upsert 幂等）
	PapersAdded int // 处理的论文数
}

// Sync 从指定 GitHub 仓库同步论文元数据到本地 Repository。
// owner/repoName 如 "papers-we-love/papers-we-love"。
//
// 流程幂等：可安全重复调用。失败时返回已处理部分与错误。
func (g *GitHubClient) Sync(ctx context.Context, repo *Repository, owner, repoName string) (GitHubSyncResult, error) {
	var result GitHubSyncResult

	// 1. 列根目录 → 主题目录
	rootEntries, err := g.listContents(ctx, owner, repoName, "")
	if err != nil {
		return result, fmt.Errorf("列出根目录失败: %w", err)
	}

	// 2. 逐个主题处理
	for _, entry := range rootEntries {
		if entry.Type != "dir" {
			continue // 跳过根目录下的文件（如 README/LICENSE）
		}
		topicID := Slugify(entry.Name)
		if topicID == "" {
			continue
		}
		// 写入主题
		if err := repo.UpsertTopic(Topic{ID: topicID, Name: entry.Name}); err != nil {
			return result, fmt.Errorf("写入主题 %s 失败: %w", topicID, err)
		}
		result.TopicsAdded++

		// 3. 列主题目录 → 论文条目
		paperEntries, err := g.listContents(ctx, owner, repoName, entry.Path)
		if err != nil {
			// 单个主题失败不阻断其余主题，继续同步
			continue
		}
		for _, pe := range paperEntries {
			paper := buildPaperFromEntry(topicID, pe)
			if paper.ID == "" {
				continue
			}
			if err := repo.UpsertPaper(paper); err != nil {
				continue // 单篇失败跳过
			}
			result.PapersAdded++
		}
		// 刷新该主题论文计数
		_ = repo.UpdatePaperCount(topicID)
	}
	return result, nil
}

// buildPaperFromEntry 由 GitHub 目录条目构造 Paper。
//   - .pdf 文件：title 去扩展名，pdf_url 取 download_url；
//   - 子目录：title 用目录名，pdf_url 留空（PDF 阅读器首期跳过，后续可按目录再深入）。
//
// id 用 "topicID_slug" 格式（下划线分隔，不含 "/"），避免 HTTP 路由 :id 匹配失败。
func buildPaperFromEntry(topicID string, entry ghContent) Paper {
	name := entry.Name
	pdfURL := entry.DownloadURL
	// 去除 .pdf 扩展名作为标题
	title := strings.TrimSuffix(name, ".pdf")
	slug := Slugify(title)
	return Paper{
		ID:      topicID + "_" + slug, // 稳定 id：topic_slug（下划线分隔，路由安全）
		Title:   title,
		TopicID: topicID,
		PDFURL:  pdfURL,
		// 新同步论文默认未读
		ReadStatus: "unread",
	}
}

// listContents 调用 GitHub Contents API 列出指定路径下的条目。
// path 为空表示仓库根目录。
func (g *GitHubClient) listContents(ctx context.Context, owner, repoName, path string) ([]ghContent, error) {
	// URL 拼装：/repos/{owner}/{repo}/contents[/{path}]。
	// path 为空时不追加尾斜杠，避免部分 mock/网关对 /contents/ 与 /contents 区分。
	// path 整体作为一个路径段，PathEscape 会编码其中的 /（目录名不含 /，符合预期）。
	u := g.baseURL + "/repos/" + url.PathEscape(owner) + "/" + url.PathEscape(repoName) + "/contents"
	if path != "" {
		u += "/" + url.PathEscape(path)
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	if err != nil {
		return nil, fmt.Errorf("构造请求失败: %w", err)
	}
	req.Header.Set("Accept", "application/vnd.github+json")
	if g.token != "" {
		req.Header.Set("Authorization", "Bearer "+g.token)
	}

	resp, err := g.http.Do(req)
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

	var entries []ghContent
	if err := json.NewDecoder(resp.Body).Decode(&entries); err != nil {
		return nil, fmt.Errorf("解析 GitHub 响应失败: %w", err)
	}
	return entries, nil
}
