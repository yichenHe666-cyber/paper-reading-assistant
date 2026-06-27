// server 包的会话/技能 HTTP 路由 handler。
//
// 文件概述：chat_handlers.go 实现 M2 的 /api/chat/* 与 /api/skills/* 路由。
//   - 会话 CRUD + 非流式发消息 + SSE 流式发消息
//   - 技能 CRUD + 手动触发自进化
//
// SSE 约定（POST /api/chat/sessions/:id/messages/stream）：
//   Content-Type: text/event-stream
//   每个事件编码为 `data: {StreamEvent JSON}\n\n`
//   客户端按 data 行解析；channel 关闭后连接结束。
//   即便中途出错也会发 error 事件再结束（不会无声断开）。
package server

import (
	"encoding/json"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"nuclear-ox-v2/backend/internal/agent"
	"nuclear-ox-v2/backend/internal/store"
)

// --- 会话路由 ---

// createSessionRequest 是 POST /api/chat/sessions 的请求体。
type createSessionRequest struct {
	Title        string   `json:"title"`         // 可选，缺省"新会话"
	SkillMode    string   `json:"skill_mode"`    // 可选，auto/manual/hybrid，缺省 auto
	EnabledSlugs []string `json:"enabled_slugs"` // 可选，manual 模式启用的技能 slug
}

// createSession 新建会话。
func (s *Server) createSession(c *gin.Context) {
	var req createSessionRequest
	_ = c.ShouldBindJSON(&req) // 允许空 body
	id, err := s.chat.CreateSession(req.Title, req.SkillMode, req.EnabledSlugs)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"id": id})
}

// listSessions 列出会话。
func (s *Server) listSessions(c *gin.Context) {
	sessions, err := s.chat.ListSessions(0)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if sessions == nil {
		sessions = []store.Session{}
	}
	c.JSON(http.StatusOK, sessions)
}

// getSession 查询会话详情。
func (s *Server) getSession(c *gin.Context) {
	id := c.Param("id")
	sess, err := s.chat.GetSession(id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, sess)
}

// listMessages 列出会话消息。
func (s *Server) listMessages(c *gin.Context) {
	id := c.Param("id")
	msgs, err := s.chat.ListMessages(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if msgs == nil {
		msgs = []store.Message{}
	}
	c.JSON(http.StatusOK, msgs)
}

// sendMessageRequest 是发消息的请求体。
type sendMessageRequest struct {
	Content string `json:"content" binding:"required"`
}

// sendMessage 非流式发消息：同步收集所有事件，返回最终 assistant 内容与统计。
// 适合不需要逐 token 展示的场景（如脚本调用）。
func (s *Server) sendMessage(c *gin.Context) {
	id := c.Param("id")
	var req sendMessageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体非法: " + err.Error()})
		return
	}

	ch, err := s.chat.SendMessage(c.Request.Context(), id, req.Content)
	if err != nil {
		status := http.StatusInternalServerError
		// 会话不存在等已由 chat 层包装为错误，统一 500/404 判断
		if isNotFound(err) {
			status = http.StatusNotFound
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}

	// 同步消费全部事件，聚合为响应
	var content string
	var toolCalls []map[string]any
	var usage *agent.Usage
	var hadError bool
	var errMsg string
	turns := 0
	for ev := range ch {
		switch ev.Type {
		case agent.EventToken:
			content += ev.Content
		case agent.EventToolCall:
			toolCalls = append(toolCalls, map[string]any{
				"id": ev.ToolCallID, "name": ev.ToolName, "args": ev.ToolArgs,
			})
		case agent.EventUsage:
			u := *ev.Usage
			usage = &u
		case agent.EventError:
			hadError = true
			errMsg = ev.Content
			turns = ev.Turn
		case agent.EventDone:
			turns = ev.Turn
		}
	}

	resp := gin.H{
		"content":    content,
		"tool_calls": toolCallsOrEmpty(toolCalls),
		"turns":      turns,
	}
	if usage != nil {
		resp["usage"] = usage
	}
	if hadError {
		resp["error"] = errMsg
		c.JSON(http.StatusInternalServerError, resp)
		return
	}
	c.JSON(http.StatusOK, resp)
}

// sendMessageStream 流式发消息（SSE）：逐事件推送给客户端。
func (s *Server) sendMessageStream(c *gin.Context) {
	id := c.Param("id")
	var req sendMessageRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体非法: " + err.Error()})
		return
	}

	ch, err := s.chat.SendMessage(c.Request.Context(), id, req.Content)
	if err != nil {
		status := http.StatusInternalServerError
		if isNotFound(err) {
			status = http.StatusNotFound
		}
		c.JSON(status, gin.H{"error": err.Error()})
		return
	}

	// SSE 响应头
	c.Header("Content-Type", "text/event-stream")
	c.Header("Cache-Control", "no-cache")
	c.Header("Connection", "keep-alive")
	// X-Accel-Buffering: no 让 nginx 不缓冲（生产部署友好）
	c.Header("X-Accel-Buffering", "no")

	flusher, _ := c.Writer.(http.Flusher)
	// 逐事件写 SSE
	for ev := range ch {
		b, err := json.Marshal(ev)
		if err != nil {
			continue
		}
		// SSE 数据行：data: {json}\n\n
		if _, err := c.Writer.WriteString("data: " + string(b) + "\n\n"); err != nil {
			// 客户端断开，停止写入
			return
		}
		if flusher != nil {
			flusher.Flush()
		}
	}
	// 发送结束标记事件，便于客户端明确知道流结束
	c.Writer.WriteString("data: {\"type\":\"end\"}\n\n")
	if flusher != nil {
		flusher.Flush()
	}
}

// --- 技能路由 ---

// listSkills 列出全部技能。
func (s *Server) listSkills(c *gin.Context) {
	skills, err := store.ListSkills(s.db, false)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if skills == nil {
		skills = []store.Skill{}
	}
	c.JSON(http.StatusOK, skills)
}

// upsertSkillRequest 是 POST /api/skills 的请求体。
type upsertSkillRequest struct {
	Slug        string `json:"slug" binding:"required"`
	Name        string `json:"name" binding:"required"`
	Description string `json:"description"`
	Content     string `json:"content"`
	Enabled     *bool  `json:"enabled"` // 指针区分未传与 false
	Level       int    `json:"level"`
}

// upsertSkill 创建或更新技能。
func (s *Server) upsertSkill(c *gin.Context) {
	var req upsertSkillRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体非法: " + err.Error()})
		return
	}
	enabled := true
	if req.Enabled != nil {
		enabled = *req.Enabled
	}
	if err := store.UpsertSkill(s.db, store.Skill{
		Slug: req.Slug, Name: req.Name, Description: req.Description,
		Content: req.Content, Enabled: enabled, Level: req.Level,
	}); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}
	got, _ := store.GetSkillBySlug(s.db, req.Slug)
	c.JSON(http.StatusOK, got)
}

// deleteSkill 删除技能。
func (s *Server) deleteSkill(c *gin.Context) {
	slug := c.Param("slug")
	if err := store.DeleteSkill(s.db, slug); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"slug": slug, "deleted": true})
}

// evolveSkill 手动触发某技能的自进化评估。
// 实际自进化是基于"会话"提炼，这里的 :slug 语义为"对该技能做一次统计刷新"。
// 更有意义的端点是按会话提炼——见 evolveSession。
func (s *Server) evolveSkill(c *gin.Context) {
	// M2：手动触发仅返回技能当前统计，真正提炼走 POST /api/chat/sessions/:id/evolve
	slug := c.Param("slug")
	got, err := store.GetSkillBySlug(s.db, slug)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"slug": got.Slug, "usage_count": got.UsageCount,
		"success_rate": got.SuccessRate, "version": got.Version,
	})
}

// evolveSessionRequest 是手动触发会话自进化的请求体。
type evolveSessionRequest struct {
	SessionID string `json:"session_id" binding:"required"`
}

// evolveSession 手动触发某会话的自进化提炼（spec §6.2 手动触发）。
func (s *Server) evolveSession(c *gin.Context) {
	var req evolveSessionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体非法: " + err.Error()})
		return
	}
	msgs, err := store.ListMessages(s.db, req.SessionID)
	if err != nil || len(msgs) == 0 {
		c.JSON(http.StatusNotFound, gin.H{"error": "会话无消息或不存在"})
		return
	}
	draft, err := s.evolver.DistillSkill(c.Request.Context(), msgs)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"slug":         draft.Slug,
		"name":         draft.Name,
		"description":  draft.Description,
		"worth_saving": draft.WorthSaving,
		"saved":        draft.WorthSaving && draft.Slug != "",
	})
}

// --- 辅助函数 ---

// toolCallsOrEmpty 保证空切片序列化为 [] 而非 null。
func toolCallsOrEmpty(t []map[string]any) []map[string]any {
	if t == nil {
		return []map[string]any{}
	}
	return t
}

// isNotFound 判断是否"未找到"类错误（会话/技能不存在）。
func isNotFound(err error) bool {
	if err == nil {
		return false
	}
	msg := err.Error()
	// chat 层包装的"会话不存在"或 store 的 ErrSessionNotFound/ErrSkillNotFound
	return strings.Contains(msg, "不存在") || strings.Contains(msg, "not found")
}
