// Package store 的会话与消息数据访问层。
//
// 文件概述：sessions.go 实现 chat_sessions / chat_messages 两表的 CRUD。
// 支撑 M2 agent loop 的"流式异常落库"（spec §4.1 修复方案）：
//   旧 chat_engine.py:120-153 的 _send_stream 无 try/except，LLM 中途失败则
//   assistant 消息不落库、SSE 断开。本层提供原子追加消息接口，ChatService
//   在流式过程中即便中途出错也保证已生成的 assistant 内容落库。
//
// 表结构见 store.go Migrate；本文件只做数据访问，不建表。
package store

import (
	"database/sql"
	"errors"
	"fmt"
	"time"
)

// ErrSessionNotFound 表示按 id 未找到会话。
var ErrSessionNotFound = errors.New("会话不存在")

// Session 对应 chat_sessions 表一行。
type Session struct {
	ID              string `json:"id"`                       // 会话 id（UUID）
	Title           string `json:"title"`                    // 会话标题
	SkillMode       string `json:"skill_mode"`               // 技能模式：auto/manual/hybrid
	EnabledSkillIDs string `json:"enabled_skill_ids"`        // 启用的技能 slug JSON 数组，如 ["summarize","qa"]
	TotalTokens     int    `json:"total_tokens"`             // 累计 token
	MessageCount    int    `json:"message_count"`            // 消息数
	CreatedAt       string `json:"created_at"`               // 创建时间
	UpdatedAt       string `json:"updated_at"`               // 最近更新时间
}

// Message 对应 chat_messages 表一行。
//
// ReasoningContent：仅推理模型返回，单独存储供前端折叠展示（spec §4.1 根因 #7）。
// ToolCalls：助手发起的工具调用 JSON（M2 agent loop 回写）。
// ToolCallID：role=tool 时必填，指明回传哪次调用结果。
type Message struct {
	ID              string `json:"id"`                        // 消息 id（UUID）
	SessionID       string `json:"session_id"`               // 所属会话
	Role            string `json:"role"`                     // user/assistant/system/tool
	Content         string `json:"content"`                  // 文本内容
	ReasoningContent string `json:"reasoning_content"`       // 推理过程（推理模型）
	ToolCalls       string `json:"tool_calls"`               // 工具调用 JSON
	ToolCallID      string `json:"tool_call_id"`             // tool 角色回传 id
	TokenCount      int    `json:"token_count"`              // 本条消息 token 数
	ContextUsagePct float64 `json:"context_usage_pct"`       // 上下文占用率
	CreatedAt       string `json:"created_at"`               // 创建时间
}

// CreateSession 新建一个会话。id 由调用方生成（UUID），保证幂等。
func CreateSession(db *sql.DB, s Session) error {
	if s.ID == "" {
		return fmt.Errorf("会话 id 不能为空")
	}
	if s.SkillMode == "" {
		s.SkillMode = "auto"
	}
	if s.EnabledSkillIDs == "" {
		s.EnabledSkillIDs = "[]"
	}
	const q = `INSERT INTO chat_sessions (id, title, skill_mode, enabled_skill_ids, total_tokens, message_count) VALUES (?, ?, ?, ?, 0, 0)`
	_, err := db.Exec(q, s.ID, s.Title, s.SkillMode, s.EnabledSkillIDs)
	if err != nil {
		return fmt.Errorf("创建会话失败: %w", err)
	}
	return nil
}

// GetSession 按 id 查询会话。未找到返回 ErrSessionNotFound。
func GetSession(db *sql.DB, id string) (*Session, error) {
	const q = `SELECT id, title, skill_mode, enabled_skill_ids, total_tokens, message_count, created_at, updated_at FROM chat_sessions WHERE id = ?`
	row := db.QueryRow(q, id)
	var s Session
	if err := row.Scan(&s.ID, &s.Title, &s.SkillMode, &s.EnabledSkillIDs, &s.TotalTokens, &s.MessageCount, &s.CreatedAt, &s.UpdatedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, ErrSessionNotFound
		}
		return nil, fmt.Errorf("查询会话 %s 失败: %w", id, err)
	}
	return &s, nil
}

// ListSessions 列出全部会话，按最近更新降序（最新在前）。limit<=0 表示不限制。
func ListSessions(db *sql.DB, limit int) ([]Session, error) {
	q := `SELECT id, title, skill_mode, enabled_skill_ids, total_tokens, message_count, created_at, updated_at FROM chat_sessions ORDER BY updated_at DESC`
	args := []any{}
	if limit > 0 {
		q += ` LIMIT ?`
		args = append(args, limit)
	}
	rows, err := db.Query(q, args...)
	if err != nil {
		return nil, fmt.Errorf("查询会话列表失败: %w", err)
	}
	defer rows.Close()
	var out []Session
	for rows.Next() {
		var s Session
		if err := rows.Scan(&s.ID, &s.Title, &s.SkillMode, &s.EnabledSkillIDs, &s.TotalTokens, &s.MessageCount, &s.CreatedAt, &s.UpdatedAt); err != nil {
			return nil, fmt.Errorf("扫描会话行失败: %w", err)
		}
		out = append(out, s)
	}
	return out, rows.Err()
}

// AppendMessage 追加一条消息，并同步更新会话的 message_count / total_tokens / updated_at。
//
// 单事务保证原子性：消息写入与计数更新要么全成功要么全失败，避免半落库。
// 这是流式异常落库的基础——即便流式中断，已落库的消息与计数一致。
func AppendMessage(db *sql.DB, m Message) error {
	if m.ID == "" || m.SessionID == "" {
		return fmt.Errorf("消息 id 与 session_id 不能为空")
	}
	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("开启事务失败: %w", err)
	}
	defer func() { _ = tx.Rollback() }() // 提交成功后 rollback 是 no-op

	const insertMsg = `INSERT INTO chat_messages (id, session_id, role, content, reasoning_content, tool_calls, tool_call_id, token_count, context_usage_pct) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`
	if _, err := tx.Exec(insertMsg, m.ID, m.SessionID, m.Role, m.Content, m.ReasoningContent, m.ToolCalls, m.ToolCallID, m.TokenCount, m.ContextUsagePct); err != nil {
		return fmt.Errorf("写入消息失败: %w", err)
	}
	// 同步会话计数：message_count +1，total_tokens 累加本条 token，updated_at 刷新
	const updateSession = `UPDATE chat_sessions SET message_count = message_count + 1, total_tokens = total_tokens + ?, updated_at = ? WHERE id = ?`
	now := time.Now().UTC().Format(time.RFC3339)
	if _, err := tx.Exec(updateSession, m.TokenCount, now, m.SessionID); err != nil {
		return fmt.Errorf("更新会话计数失败: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return fmt.Errorf("提交消息事务失败: %w", err)
	}
	return nil
}

// ListMessages 按插入顺序（rowid 升序）列出某会话的全部消息。
//
// 注意：created_at 用 datetime('now') 仅秒级精度，同秒内多条消息会 tie；
// id 为 UUID 不可按插入序排序。故改用 SQLite 隐式 rowid（插入自增）保证对话顺序。
// rowid 在 INTEGER PRIMARY KEY 表中会被别名复用，但本表 id 为 TEXT，rowid 独立可用。
func ListMessages(db *sql.DB, sessionID string) ([]Message, error) {
	const q = `SELECT id, session_id, role, content, reasoning_content, tool_calls, tool_call_id, token_count, context_usage_pct, created_at FROM chat_messages WHERE session_id = ? ORDER BY rowid ASC`
	rows, err := db.Query(q, sessionID)
	if err != nil {
		return nil, fmt.Errorf("查询会话 %s 消息失败: %w", sessionID, err)
	}
	defer rows.Close()
	var out []Message
	for rows.Next() {
		var m Message
		if err := rows.Scan(&m.ID, &m.SessionID, &m.Role, &m.Content, &m.ReasoningContent, &m.ToolCalls, &m.ToolCallID, &m.TokenCount, &m.ContextUsagePct, &m.CreatedAt); err != nil {
			return nil, fmt.Errorf("扫描消息行失败: %w", err)
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

// UpdateSessionTitle 更新会话标题。首轮对话后由 LLM 摘要生成标题。
func UpdateSessionTitle(db *sql.DB, id, title string) error {
	now := time.Now().UTC().Format(time.RFC3339)
	res, err := db.Exec(`UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?`, title, now, id)
	if err != nil {
		return fmt.Errorf("更新会话标题失败: %w", err)
	}
	if n, _ := res.RowsAffected(); n == 0 {
		return ErrSessionNotFound
	}
	return nil
}

// DeleteSession 删除会话及其全部消息（外键无 ON DELETE CASCADE，故显式两步删）。
func DeleteSession(db *sql.DB, id string) error {
	tx, err := db.Begin()
	if err != nil {
		return fmt.Errorf("开启事务失败: %w", err)
	}
	defer func() { _ = tx.Rollback() }()
	if _, err := tx.Exec(`DELETE FROM chat_messages WHERE session_id = ?`, id); err != nil {
		return fmt.Errorf("删除会话消息失败: %w", err)
	}
	if _, err := tx.Exec(`DELETE FROM chat_sessions WHERE id = ?`, id); err != nil {
		return fmt.Errorf("删除会话失败: %w", err)
	}
	return tx.Commit()
}
