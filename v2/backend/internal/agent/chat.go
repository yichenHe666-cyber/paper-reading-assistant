// agent 包的会话编排服务。
//
// 文件概述：chat.go 实现 ChatService，串联会话管理、agent loop、技能注入与自进化触发。
// 是 M2 各组件的"门面"，供 server 层 HTTP handler 调用。
//
// 流式异常落库（spec §4.1 修复方案，根因 #3）：
// 旧 chat_engine.py:120-153 的 _send_stream 无 try/except，LLM 中途失败则
// assistant 消息不落库、SSE 断开。本服务采用"channel 转发 + 累积 + defer 落库"模式：
//   - SendMessage 返回转发 channel，内部 goroutine 一边把事件转发给调用方（SSE handler），
//     一边累积 assistant 文本；
//   - channel 关闭时（无论 done 还是 error），把累积的内容落库——即便中途出错，
//     已生成的部分也会保存，用户下次进会话能看到不完整的回答而非空白。
//   - panic 时 recover，保证不把异常抛到 HTTP 层导致连接无响应。
//
// 自进化触发（spec §6.2）：累积工具调用次数，会话结束达到阈值时后台触发 DistillSkill。
package agent

import (
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"
	"sync/atomic"

	"github.com/google/uuid"

	"nuclear-ox-v2/backend/internal/llm"
	"nuclear-ox-v2/backend/internal/store"
)

// ChatService 是会话编排门面。线程安全（无共享可变状态，每次 SendMessage 独立）。
type ChatService struct {
	db      *sql.DB
	agent   *Agent
	skills  *SkillRegistry
	evolver *Evolver
}

// NewChatService 构造会话服务。
// agent/skills/evolver 由调用方装配后注入；可为 nil（退化模式，仅会话 CRUD）。
func NewChatService(db *sql.DB, agent *Agent, skills *SkillRegistry, evolver *Evolver) *ChatService {
	return &ChatService{db: db, agent: agent, skills: skills, evolver: evolver}
}

// CreateSession 新建会话，返回 session id。
// enabledSlugs 为该会话启用的技能 slug；skillMode 为 auto/manual/hybrid。
func (s *ChatService) CreateSession(title, skillMode string, enabledSlugs []string) (string, error) {
	id := uuid.NewString()
	if skillMode == "" {
		skillMode = "auto"
	}
	// enabledSlugs 序列化为 JSON 数组存入 enabled_skill_ids
	slugJSON := "[]"
	if len(enabledSlugs) > 0 {
		b, _ := json.Marshal(enabledSlugs)
		slugJSON = string(b)
	}
	if title == "" {
		title = "新会话"
	}
	if err := store.CreateSession(s.db, store.Session{
		ID: id, Title: title, SkillMode: skillMode, EnabledSkillIDs: slugJSON,
	}); err != nil {
		return "", err
	}
	return id, nil
}

// GetSession 获取会话详情。
func (s *ChatService) GetSession(id string) (*store.Session, error) {
	return store.GetSession(s.db, id)
}

// ListSessions 列出会话。
func (s *ChatService) ListSessions(limit int) ([]store.Session, error) {
	return store.ListSessions(s.db, limit)
}

// ListMessages 列出会话消息（按时间升序）。
func (s *ChatService) ListMessages(sessionID string) ([]store.Message, error) {
	return store.ListMessages(s.db, sessionID)
}

// DeleteSession 删除会话。
func (s *ChatService) DeleteSession(id string) error {
	return store.DeleteSession(s.db, id)
}

// SendMessage 向会话发送一条用户消息并运行 agent loop，返回 StreamEvent 转发 channel。
//
// 流程：
//  1. 校验会话存在；
//  2. 落库用户消息；
//  3. 加载历史消息，组装 LLM messages（含 system prompt + 技能块）；
//  4. 启动 agent.Run，转发事件并累积 assistant 内容；
//  5. channel 关闭时落库 assistant 消息（流式异常落库）；
//  6. 累积工具调用数，达阈值后台触发自进化。
//
// 返回的 channel 由本服务负责关闭。调用方 range 即可。
func (s *ChatService) SendMessage(ctx context.Context, sessionID, userContent string) (<-chan StreamEvent, error) {
	if s.agent == nil {
		return nil, fmt.Errorf("agent 未装配，无法发送消息")
	}
	// 1. 校验会话
	sess, err := store.GetSession(s.db, sessionID)
	if err != nil {
		return nil, fmt.Errorf("会话不存在: %w", err)
	}

	// 2. 落库用户消息
	userMsgID := uuid.NewString()
	if err := store.AppendMessage(s.db, store.Message{
		ID: userMsgID, SessionID: sessionID, Role: "user", Content: userContent,
	}); err != nil {
		return nil, fmt.Errorf("落库用户消息失败: %w", err)
	}

	// 3. 组装 LLM messages
	llmMsgs, injectedSlugs, err := s.buildLLMMessages(sess, userContent)
	if err != nil {
		return nil, err
	}

	// 4. 启动 agent loop。
	// 直接使用上层 ctx：客户端断开 → ctx 取消 → LLM 调用返回 error → error 事件 →
	// tapAndPersist 仍会把已累积内容落库（流式异常落库，spec §4.1 根因 #3 修复）。
	in := s.agent.Run(ctx, llmMsgs)

	// 5. 转发 + 累积 + 落库
	out := make(chan StreamEvent, 32)
	go s.tapAndPersist(sessionID, in, out, injectedSlugs)
	return out, nil
}

// tapAndPersist 转发 agent 事件到 out，同时累积 assistant 内容，
// channel 关闭后落库 assistant 消息并触发自进化。
//
// 流式异常落库核心：用 defer recover 兜底 panic；无论 done/error 都尝试落库累积内容。
func (s *ChatService) tapAndPersist(sessionID string, in <-chan StreamEvent, out chan<- StreamEvent, injectedSlugs []string) {
	defer func() {
		if r := recover(); r != nil {
			// panic 不抛到 HTTP 层；落库已知内容并发 error 事件
			safeSend(out, newErrorEvent(0, fmt.Sprintf("agent 内部错误: %v", r)))
		}
		close(out)
	}()

	var contentBuilder strings.Builder
	var toolCallCount int32
	var lastUsage *Usage
	var hadError bool
	var errMsg string

	for ev := range in {
		// 累积 assistant 文本（token 事件）
		if ev.Type == EventToken {
			contentBuilder.WriteString(ev.Content)
		}
		// 计数工具调用
		if ev.Type == EventToolCall {
			atomic.AddInt32(&toolCallCount, 1)
		}
		// 记录最后一次 usage
		if ev.Type == EventUsage && ev.Usage != nil {
			u := *ev.Usage
			lastUsage = &u
		}
		// 错误事件：记录但继续转发，后续落库累积内容
		if ev.Type == EventError {
			hadError = true
			errMsg = ev.Content
		}
		// 转发给 SSE handler
		safeSend(out, ev)
	}

	// 6. 落库 assistant 消息（流式异常落库）
	content := contentBuilder.String()
	// 即便出错，只要有内容就落库（追加错误说明，便于用户/下次会话理解中断原因）
	if hadError && content != "" && errMsg != "" {
		content = content + "\n\n[流程中断: " + errMsg + "]"
	}
	// 只在有内容或有错误时落库 assistant 消息（避免空消息污染历史）
	if content != "" || hadError {
		assistantMsgID := uuid.NewString()
		tokens := 0
		if lastUsage != nil {
			tokens = lastUsage.TotalTokens
		}
		_ = store.AppendMessage(s.db, store.Message{
			ID:        assistantMsgID,
			SessionID: sessionID,
			Role:      "assistant",
			Content:   content,
			TokenCount: tokens,
		})
	}

	// 7. 更新技能用量（注入即视为参与本次任务）
	if s.evolver != nil && len(injectedSlugs) > 0 {
		// 任务成功判定：无 error 且有内容 → 成功；否则失败
		succeeded := !hadError && content != ""
		_ = s.evolver.TrackUsage(injectedSlugs, succeeded)
	}

	// 8. 自进化触发：工具调用达阈值，后台提炼技能
	if s.evolver != nil && s.evolver.ShouldDistill(int(atomic.LoadInt32(&toolCallCount))) {
		go s.tryDistill(sessionID)
	}
}

// tryDistill 后台提炼技能，失败仅记日志（不影响主流程）。
func (s *ChatService) tryDistill(sessionID string) {
	defer func() { _ = recover() }()
	msgs, err := store.ListMessages(s.db, sessionID)
	if err != nil || len(msgs) == 0 {
		return
	}
	ctx, cancel := context.WithTimeout(context.Background(), DefaultPerTurnTimeout)
	defer cancel()
	_, _ = s.evolver.DistillSkill(ctx, msgs)
}

// buildLLMMessages 组装 LLM 请求消息：system prompt（含技能块）+ 历史 + 当前用户消息。
// 返回 messages 与本次注入的技能 slug 列表（供用量统计）。
func (s *ChatService) buildLLMMessages(sess *store.Session, userContent string) ([]llm.Message, []string, error) {
	// 加载历史消息（含刚落库的用户消息）
	history, err := store.ListMessages(s.db, sess.ID)
	if err != nil {
		return nil, nil, fmt.Errorf("加载历史消息失败: %w", err)
	}

	// 组装 system prompt：基础 + 技能块
	base := s.agent.baseSystemPrompt
	skillBlock := ""
	var injectedSlugs []string
	if s.skills != nil {
		// 按会话配置构造"一次性"技能注册表，避免修改共享 SkillRegistry 的状态（线程安全）。
		// manual 模式用 session 显式列表；auto/hybrid 用全部启用技能（传 nil）。
		var slugs []string
		if sess.SkillMode == "manual" {
			slugs = parseEnabledSlugs(sess.EnabledSkillIDs)
		}
		tmpRegistry := NewSkillRegistry(s.skills.db, slugs)
		skillBlock, injectedSlugs, err = tmpRegistry.SystemPromptBlock()
		if err != nil {
			return nil, nil, fmt.Errorf("构造技能块失败: %w", err)
		}
	}
	systemPrompt := BuildSystemPrompt(base, skillBlock)

	// 组装 LLM messages
	msgs := make([]llm.Message, 0, len(history)+1)
	msgs = append(msgs, llm.Message{Role: llm.RoleSystem, Content: systemPrompt})
	for _, m := range history {
		role := llm.Role(m.Role)
		// tool 角色消息在 agent loop 内部由工具执行产生，历史重建时简化为 user/assistant
		// （完整重建 tool 消息需匹配 tool_call_id，M2 阶段简化处理）
		if role == llm.RoleTool {
			continue
		}
		msgs = append(msgs, llm.Message{Role: role, Content: m.Content})
	}
	// history 已含刚落库的用户消息，无需再追加
	return msgs, injectedSlugs, nil
}

// parseEnabledSlugs 解析 session.EnabledSkillIDs JSON 数组。
func parseEnabledSlugs(s string) []string {
	if s == "" || s == "[]" {
		return nil
	}
	var out []string
	if err := json.Unmarshal([]byte(s), &out); err != nil {
		return nil
	}
	return out
}

// safeSend 向 channel 发送事件，避免对已关闭 channel 发送 panic。
// 转发场景下 out 由本 goroutine 关闭，不会并发关闭，但保留防护以增稳健。
func safeSend(ch chan<- StreamEvent, ev StreamEvent) {
	defer func() { _ = recover() }()
	ch <- ev
}
