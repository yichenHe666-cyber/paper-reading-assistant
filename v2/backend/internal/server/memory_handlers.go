// Package server 的记忆相关 handler 实现（M4.6）。
//
// 文件概述：memory_handlers.go 实现 /api/memory/* 路由的请求处理，
// 作为 Go 后端到 Rust core 的 HTTP 代理层（spec §2.1：浏览器 → 前端 → Go → Rust core）。
//
// 职责边界：
//   - 本文件只做参数解析、调用 memory.Client、统一 JSON 响应；
//   - 记忆存储、向量检索、梦境整合逻辑全在 Rust core；
//   - 错误码：core 连接失败 → 502；core 内部错误 → 500；未找到 → 404；请求错误 → 400。
//
// 响应约定与 handlers.go 一致：成功 200 + 业务 JSON，错误 {"error":"..."}。
package server

import (
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"

	"nuclear-ox-v2/backend/internal/memory"
)

// --- 记忆 CRUD ---

// createMemory POST /api/memory
// 请求体：{layer, content, importance_score}
func (s *Server) createMemory(c *gin.Context) {
	var req memory.CreateMemoryRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体无效: " + err.Error()})
		return
	}
	if req.Layer == "" {
		req.Layer = memory.LayerEpisodic
	}
	m, err := s.memory.CreateMemory(c.Request.Context(), req)
	if err != nil {
		respondCoreError(c, err)
		return
	}
	c.JSON(http.StatusCreated, m)
}

// getMemory GET /api/memory/:id
func (s *Server) getMemory(c *gin.Context) {
	id := c.Param("id")
	m, err := s.memory.GetMemory(c.Request.Context(), id)
	if err != nil {
		respondCoreError(c, err)
		return
	}
	if m == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "记忆不存在"})
		return
	}
	c.JSON(http.StatusOK, m)
}

// deleteMemory DELETE /api/memory/:id
func (s *Server) deleteMemory(c *gin.Context) {
	id := c.Param("id")
	if err := s.memory.DeleteMemory(c.Request.Context(), id); err != nil {
		respondCoreError(c, err)
		return
	}
	// 204 No Content 不应携带 body（与 Rust core delete_memory 一致）
	c.Status(http.StatusNoContent)
}

// searchMemory GET /api/memory/search?keyword=&limit=
func (s *Server) searchMemory(c *gin.Context) {
	keyword := c.Query("keyword")
	if keyword == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "缺少 keyword 参数"})
		return
	}
	limit := parseLimitQuery(c.Query("limit"))
	items, err := s.memory.SearchMemory(c.Request.Context(), keyword, limit)
	if err != nil {
		respondCoreError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// searchVectorRequestDTO 向量检索请求体（前端入参）。
type searchVectorRequestDTO struct {
	Query string `json:"query" binding:"required"`
	TopK  int    `json:"top_k"`
}

// searchVector POST /api/memory/search-vector
func (s *Server) searchVector(c *gin.Context) {
	var req searchVectorRequestDTO
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体无效: " + err.Error()})
		return
	}
	items, err := s.memory.SearchVector(c.Request.Context(), req.Query, req.TopK)
	if err != nil {
		respondCoreError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// --- 梦境 ---

// triggerDream POST /api/memory/dream
// 手动触发一次梦境整合（spec §5.2）。无请求体。
func (s *Server) triggerDream(c *gin.Context) {
	result, err := s.memory.TriggerDream(c.Request.Context())
	if err != nil {
		respondCoreError(c, err)
		return
	}
	c.JSON(http.StatusOK, result)
}

// listDreamDiary GET /api/memory/dream-diary?limit=
func (s *Server) listDreamDiary(c *gin.Context) {
	limit := parseLimitQuery(c.Query("limit"))
	items, err := s.memory.ListDreamDiary(c.Request.Context(), limit)
	if err != nil {
		respondCoreError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// getDreamDiary GET /api/memory/dream-diary/:id
func (s *Server) getDreamDiary(c *gin.Context) {
	id := c.Param("id")
	d, err := s.memory.GetDreamDiary(c.Request.Context(), id)
	if err != nil {
		respondCoreError(c, err)
		return
	}
	if d == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Dream Diary 条目不存在"})
		return
	}
	c.JSON(http.StatusOK, d)
}

// --- 决策账本 ---

// addDecision POST /api/memory/decision
func (s *Server) addDecision(c *gin.Context) {
	var req memory.CreateDecisionRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体无效: " + err.Error()})
		return
	}
	if req.Decision == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "decision 不能为空"})
		return
	}
	d, err := s.memory.AddDecision(c.Request.Context(), req)
	if err != nil {
		respondCoreError(c, err)
		return
	}
	c.JSON(http.StatusCreated, d)
}

// listDecisions GET /api/memory/decisions?limit=
func (s *Server) listDecisions(c *gin.Context) {
	limit := parseLimitQuery(c.Query("limit"))
	items, err := s.memory.ListDecisions(c.Request.Context(), limit)
	if err != nil {
		respondCoreError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"items": items})
}

// --- 辅助 ---

// parseLimitQuery 解析 limit 查询参数，非法或缺失返回 0（表示用默认值）。
func parseLimitQuery(s string) int {
	if s == "" {
		return 0
	}
	n, err := strconv.Atoi(s)
	if err != nil || n < 0 {
		return 0
	}
	return n
}

// respondCoreError 统一处理 memory.Client 返回的错误。
// 当前简化实现：core 错误一律视为 502（上游错误），日志由 gin Recovery 兜底。
// 后续可按错误信息细分（如连接拒绝 → 503）。
func respondCoreError(c *gin.Context, err error) {
	c.JSON(http.StatusBadGateway, gin.H{"error": "Rust core 调用失败: " + err.Error()})
}
