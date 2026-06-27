// Package server 的路由 handler 实现。
//
// 文件概述：handlers.go 实现 server.go 注册的全部 /api 路由的请求处理。
// 每个 handler 负责：解析入参 → 调用 repo/github → 统一 JSON 响应与错误码。
//
// 响应约定：
//   - 成功：HTTP 200 + 业务数据 JSON；
//   - 未找到：HTTP 404 + {"error": "..."}；
//   - 请求错误：HTTP 400 + {"error": "..."}；
//   - 内部错误：HTTP 500 + {"error": "..."}。
package server

import (
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"

	"nuclear-ox-v2/backend/internal/paper"
)

// healthResponse 是 /api/health 的响应体。
// data_dir 与 db_path 为绝对路径——这是 M1 验收点：健康接口必须返回数据目录绝对路径，
// 用于确认路径绝对化生效（痛点②修复可视验证）。
type healthResponse struct {
	Status      string `json:"status"`         // "ok"
	DataDir     string `json:"data_dir"`        // 数据根目录（绝对路径）
	DBPath      string `json:"db_path"`         // 数据库路径（绝对路径）
	PaperCount  int    `json:"paper_count"`     // 当前论文总数（验证"重启是否为 0"）
	TopicCount  int    `json:"topic_count"`     // 主题数
	LLMProvider string `json:"llm_provider"`    // 当前 LLM provider
	LLMModel    string `json:"llm_model"`       // 当前 LLM 模型
}

// getHealth 健康检查。返回数据目录绝对路径与基本统计，供前端启动自检与 M1 验收。
func (s *Server) getHealth(c *gin.Context) {
	paperCount, err := s.repo.CountPapers()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "查询论文数失败: " + err.Error()})
		return
	}
	topics, err := s.repo.ListTopics()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "查询主题失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, healthResponse{
		Status:      "ok",
		DataDir:     s.cfg.DataDir,
		DBPath:      s.cfg.DBPath,
		PaperCount:  paperCount,
		TopicCount:  len(topics),
		LLMProvider: s.cfg.LLM.Provider,
		LLMModel:    s.cfg.LLM.Model,
	})
}

// listTopics 列出全部主题。
func (s *Server) listTopics(c *gin.Context) {
	topics, err := s.repo.ListTopics()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	// 空切片也返回 [] 而非 null（前端友好）
	if topics == nil {
		topics = []paper.Topic{}
	}
	c.JSON(http.StatusOK, topics)
}

// listPapers 列出指定主题下的论文。
func (s *Server) listPapers(c *gin.Context) {
	topicID := c.Param("id")
	if topicID == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "缺少主题 id"})
		return
	}
	papers, err := s.repo.ListPapers(topicID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if papers == nil {
		papers = []paper.Paper{}
	}
	c.JSON(http.StatusOK, papers)
}

// getPaper 查询单篇论文。
func (s *Server) getPaper(c *gin.Context) {
	id := c.Param("id")
	p, err := s.repo.GetPaper(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if p == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "论文不存在: " + id})
		return
	}
	c.JSON(http.StatusOK, p)
}

// updateStatusRequest 是 PATCH /papers/:id/status 的请求体。
type updateStatusRequest struct {
	Status string `json:"status" binding:"required"` // unread/reading/done/reread
}

// updatePaperStatus 更新论文阅读状态。用户操作，不被后续同步覆盖（见 repository.go）。
func (s *Server) updatePaperStatus(c *gin.Context) {
	id := c.Param("id")
	var req updateStatusRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体非法: " + err.Error()})
		return
	}
	// 简单校验状态值，防脏数据
	switch req.Status {
	case "unread", "reading", "done", "reread":
	default:
		c.JSON(http.StatusBadRequest, gin.H{"error": "非法状态值: " + req.Status})
		return
	}
	if err := s.repo.UpdateReadStatus(id, req.Status); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"id": id, "status": req.Status})
}

// syncRequest 是 POST /sync 的可选请求体。
type syncRequest struct {
	Owner string `json:"owner"` // 仓库 owner，缺省取 cfg.GitHub.DefaultRepo
	Repo  string `json:"repo"`  // 仓库名
}

// syncResultResponse 是 /sync 的响应体。
type syncResultResponse struct {
	Owner       string `json:"owner"`
	Repo        string `json:"repo"`
	TopicsAdded int    `json:"topics_added"`
	PapersAdded int    `json:"papers_added"`
}

// syncPapers 触发 GitHub 仓库同步。owner/repo 缺省时用配置的默认仓库。
func (s *Server) syncPapers(c *gin.Context) {
	var req syncRequest
	// 请求体可选；忽略绑定错误（允许空 body 用默认值）
	_ = c.ShouldBindJSON(&req)

	owner, repo := req.Owner, req.Repo
	if owner == "" || repo == "" {
		// 解析默认仓库 "owner/repo"
		parts := strings.SplitN(s.cfg.GitHub.DefaultRepo, "/", 2)
		if len(parts) != 2 || parts[0] == "" || parts[1] == "" {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "默认仓库配置非法: " + s.cfg.GitHub.DefaultRepo})
			return
		}
		owner, repo = parts[0], parts[1]
	}

	result, err := s.github.Sync(c.Request.Context(), s.repo, owner, repo)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "同步失败: " + err.Error()})
		return
	}
	c.JSON(http.StatusOK, syncResultResponse{
		Owner: owner, Repo: repo,
		TopicsAdded: result.TopicsAdded, PapersAdded: result.PapersAdded,
	})
}

// migrateLegacyResponse 是 /migrate-legacy 的响应体。
type migrateLegacyResponse struct {
	Found   int                  `json:"found"`    // 发现的旧库数
	Results []paper.MigrateResult `json:"results"` // 各旧库迁移结果
}

// migrateLegacy 扫描并迁移旧版相对路径遗留的数据库，找回历史论文数据（痛点②）。
// 尽力而为：单个旧库失败不阻断其余。
func (s *Server) migrateLegacy(c *gin.Context) {
	legacyDBs := paper.FindLegacyDBs(s.cfg.DBPath)
	resp := migrateLegacyResponse{Found: len(legacyDBs)}
	for _, p := range legacyDBs {
		result, err := paper.MigrateLegacyDB(s.repo, p)
		if err != nil {
			// 失败也记录来源，便于排查
			result.SourceDB = p
		}
		resp.Results = append(resp.Results, result)
	}
	if resp.Results == nil {
		resp.Results = []paper.MigrateResult{}
	}
	c.JSON(http.StatusOK, resp)
}
