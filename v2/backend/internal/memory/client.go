// Package memory 的 HTTP client 实现。
//
// 文件概述：client.go 封装对 Rust core（v2/core）11 个 HTTP 端点的调用，
// 为 Go 后端 handler 提供类型安全的 Go API。所有方法带 context 支持超时与取消。
//
// 设计要点：
//   - 显式 UTF-8：请求头 Content-Type/Accept 均带 charset=utf-8（痛点③修复规范）；
//   - 错误透传：Rust core 错误响应 {"error":"..."} 被解码为 Go error，状态码前缀便于定位；
//   - 列表响应：Rust core 用 {"items":[...]} 包装，client 解包后返回裸切片；
//   - 不重试：首期简单透传，重试由调用方决定（梦境触发幂等性弱，重试可能产生重复日志）。
package memory

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"
)

// Client 调用 Rust core 的 HTTP 客户端。并发安全（http.Client 内部线程安全）。
type Client struct {
	baseURL string
	http    *http.Client
}

// New 构造 Client。baseURL 不带尾部 /（传入带 / 的值会被剥离，避免拼接出 //memory 双斜杠），
// timeoutSec 控制单次请求超时。
func New(baseURL string, timeoutSec float64) *Client {
	return &Client{
		baseURL: strings.TrimRight(baseURL, "/"),
		http: &http.Client{
			Timeout: time.Duration(timeoutSec * float64(time.Second)),
		},
	}
}

// --- 内部请求辅助 ---

// doJSON 发送 JSON 请求并返回原始响应。调用方负责 Close resp.Body。
// body 为 nil 时不发送请求体（用于 GET/DELETE）。
func (c *Client) doJSON(ctx context.Context, method, path string, body any) (*http.Response, error) {
	var reader io.Reader
	if body != nil {
		b, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("序列化请求体失败: %w", err)
		}
		reader = bytes.NewReader(b)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.baseURL+path, reader)
	if err != nil {
		return nil, fmt.Errorf("构造请求失败: %w", err)
	}
	if body != nil {
		req.Header.Set("Content-Type", "application/json; charset=utf-8")
	}
	req.Header.Set("Accept", "application/json")
	return c.http.Do(req)
}

// decodeError 解析 Rust core 的错误响应 {"error":"..."}。
// 响应体已读取完毕，调用方无需再 Close。
func decodeError(resp *http.Response) error {
	var body struct {
		Error string `json:"error"`
	}
	_ = json.NewDecoder(resp.Body).Decode(&body)
	if body.Error != "" {
		return fmt.Errorf("core 返回 %d: %s", resp.StatusCode, body.Error)
	}
	return fmt.Errorf("core 返回 %d", resp.StatusCode)
}

// decodeJSON 解码成功响应到目标对象。
func decodeJSON[T any](resp *http.Response, target *T) error {
	if err := json.NewDecoder(resp.Body).Decode(target); err != nil {
		return fmt.Errorf("解析响应失败: %w", err)
	}
	return nil
}

// --- 记忆 CRUD ---

// CreateMemory 创建记忆。Rust 侧会异步生成 embedding，返回的 Memory 已含 id。
func (c *Client) CreateMemory(ctx context.Context, req CreateMemoryRequest) (*Memory, error) {
	resp, err := c.doJSON(ctx, http.MethodPost, "/memory", req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		return nil, decodeError(resp)
	}
	var m Memory
	if err := decodeJSON(resp, &m); err != nil {
		return nil, err
	}
	return &m, nil
}

// GetMemory 按 id 查询记忆。未找到时返回 nil, nil（由调用方决定 404）。
func (c *Client) GetMemory(ctx context.Context, id string) (*Memory, error) {
	resp, err := c.doJSON(ctx, http.MethodGet, "/memory/"+url.PathEscape(id), nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, decodeError(resp)
	}
	var m Memory
	if err := decodeJSON(resp, &m); err != nil {
		return nil, err
	}
	return &m, nil
}

// DeleteMemory 删除记忆（含向量级联）。
func (c *Client) DeleteMemory(ctx context.Context, id string) error {
	resp, err := c.doJSON(ctx, http.MethodDelete, "/memory/"+url.PathEscape(id), nil)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusNoContent {
		return decodeError(resp)
	}
	return nil
}

// SearchMemory 关键字检索。limit<=0 时 Rust 侧用默认值 20。
func (c *Client) SearchMemory(ctx context.Context, keyword string, limit int) ([]Memory, error) {
	q := url.Values{}
	q.Set("keyword", keyword)
	if limit > 0 {
		q.Set("limit", strconv.Itoa(limit))
	}
	resp, err := c.doJSON(ctx, http.MethodGet, "/memory/search?"+q.Encode(), nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, decodeError(resp)
	}
	var wrapped itemsWrapper[Memory]
	if err := decodeJSON(resp, &wrapped); err != nil {
		return nil, err
	}
	return wrapped.Items, nil
}

// SearchVector 向量相似度检索。topK<=0 时 Rust 侧用默认值 5。
func (c *Client) SearchVector(ctx context.Context, query string, topK int) ([]SimilarMemory, error) {
	resp, err := c.doJSON(ctx, http.MethodPost, "/memory/search-vector", searchVectorRequest{
		Query: query,
		TopK:  topK,
	})
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, decodeError(resp)
	}
	var wrapped itemsWrapper[SimilarMemory]
	if err := decodeJSON(resp, &wrapped); err != nil {
		return nil, err
	}
	return wrapped.Items, nil
}

// --- 梦境 ---

// TriggerDream 触发一次完整梦境（Light → REM → Deep）。
// 返回 DreamResult，含评分明细与升级/衰减统计。
func (c *Client) TriggerDream(ctx context.Context) (*DreamResult, error) {
	resp, err := c.doJSON(ctx, http.MethodPost, "/dream", nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, decodeError(resp)
	}
	var r DreamResult
	if err := decodeJSON(resp, &r); err != nil {
		return nil, err
	}
	return &r, nil
}

// ListDreamDiary 列出最近的 Dream Diary（仅 stage='done' 行）。limit<=0 用默认 20。
func (c *Client) ListDreamDiary(ctx context.Context, limit int) ([]DreamDiaryEntry, error) {
	q := url.Values{}
	if limit > 0 {
		q.Set("limit", strconv.Itoa(limit))
	}
	path := "/dream-diary"
	if encoded := q.Encode(); encoded != "" {
		path += "?" + encoded
	}
	resp, err := c.doJSON(ctx, http.MethodGet, path, nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, decodeError(resp)
	}
	var wrapped itemsWrapper[DreamDiaryEntry]
	if err := decodeJSON(resp, &wrapped); err != nil {
		return nil, err
	}
	return wrapped.Items, nil
}

// GetDreamDiary 按 id 查询单条 Dream Diary。未找到返回 nil, nil。
func (c *Client) GetDreamDiary(ctx context.Context, id string) (*DreamDiaryEntry, error) {
	resp, err := c.doJSON(ctx, http.MethodGet, "/dream-diary/"+url.PathEscape(id), nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode == http.StatusNotFound {
		return nil, nil
	}
	if resp.StatusCode != http.StatusOK {
		return nil, decodeError(resp)
	}
	var d DreamDiaryEntry
	if err := decodeJSON(resp, &d); err != nil {
		return nil, err
	}
	return &d, nil
}

// --- 决策账本 ---

// AddDecision 记录一条决策到账本。
func (c *Client) AddDecision(ctx context.Context, req CreateDecisionRequest) (*DecisionEntry, error) {
	resp, err := c.doJSON(ctx, http.MethodPost, "/decision", req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusCreated {
		return nil, decodeError(resp)
	}
	var d DecisionEntry
	if err := decodeJSON(resp, &d); err != nil {
		return nil, err
	}
	return &d, nil
}

// ListDecisions 列出最近的决策。limit<=0 用默认 20。
func (c *Client) ListDecisions(ctx context.Context, limit int) ([]DecisionEntry, error) {
	q := url.Values{}
	if limit > 0 {
		q.Set("limit", strconv.Itoa(limit))
	}
	path := "/decisions"
	if encoded := q.Encode(); encoded != "" {
		path += "?" + encoded
	}
	resp, err := c.doJSON(ctx, http.MethodGet, path, nil)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, decodeError(resp)
	}
	var wrapped itemsWrapper[DecisionEntry]
	if err := decodeJSON(resp, &wrapped); err != nil {
		return nil, err
	}
	return wrapped.Items, nil
}
