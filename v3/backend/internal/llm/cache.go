// Package llm 的响应缓存（替代 Redis，见 spec §2.3）。
//
// 文件概述：cache.go 基于 SQLite llm_cache 表实现 LLM 响应缓存：
//   - CacheKey：对 (model, messages, temperature, max_tokens) 做 SHA256 指纹；
//   - Get/Set：按指纹读写 llm_cache 表。
//
// 缓存策略：
//   - 仅缓存"无工具调用"的请求（带 tools 的 agent 调用结果不缓存，避免副作用）；
//   - 命中时直接反序列化返回，跳过网络请求与成本记录（未实际调用 provider）；
//   - 未命中则正常请求，成功后写入缓存。
//
// 设计为可选：Client.cache 为 nil 时不启用，便于测试与按需开关。
package llm

import (
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"fmt"
)

// Cache 是基于 SQLite llm_cache 表的响应缓存。
type Cache struct {
	db *sql.DB
}

// NewCache 构造缓存实例。db 应为 store.Open 返回的连接。
func NewCache(db *sql.DB) *Cache {
	return &Cache{db: db}
}

// Get 按指纹读取缓存的响应 JSON。未命中返回 ("", false)。
func (c *Cache) Get(key string) (string, bool) {
	var resp string
	err := c.db.QueryRow(
		`SELECT response FROM llm_cache WHERE cache_key=?`, key,
	).Scan(&resp)
	if err == sql.ErrNoRows {
		return "", false
	}
	if err != nil {
		// 缓存读失败不应阻断主流程，按未命中处理
		return "", false
	}
	return resp, true
}

// Set 写入一条缓存。失败仅返回 error，调用方忽略即可。
func (c *Cache) Set(key, respJSON string) error {
	_, err := c.db.Exec(
		`INSERT OR REPLACE INTO llm_cache(cache_key, response) VALUES(?, ?)`,
		key, respJSON,
	)
	if err != nil {
		return fmt.Errorf("写入 llm_cache 失败: %w", err)
	}
	return nil
}

// cacheKeyPayload 是参与指纹计算的字段集合。
// 故意不含 tools（带工具的请求不缓存）、不含 reasoning_effort/thinking
// （这些由能力矩阵确定性派生，对同一模型固定，无需入 key）。
type cacheKeyPayload struct {
	Model       string    `json:"m"`
	Messages    []Message `json:"msg"`
	Temperature float64   `json:"t"`
	MaxTokens   int       `json:"mt"`
}

// CacheKey 依据请求生成 SHA256 指纹。带 tools 的请求返回空串表示"不缓存"。
func CacheKey(req *Request) string {
	// 带工具声明的请求一律不缓存（agent 调用有副作用语义）
	if len(req.Tools) > 0 {
		return ""
	}
	payload := cacheKeyPayload{
		Model:       req.Model,
		Messages:    req.Messages,
		Temperature: req.Temperature,
		MaxTokens:   req.MaxTokens,
	}
	b, err := json.Marshal(payload)
	if err != nil {
		return ""
	}
	sum := sha256.Sum256(b)
	return hex.EncodeToString(sum[:])
}
