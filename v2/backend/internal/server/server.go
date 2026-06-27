// Package server 装配 HTTP 服务，将 config/store/llm/paper 各层组装为可运行的后端。
//
// 文件概述：server.go 定义 Server 结构与生命周期：
//   - New：依据 config 与已打开的 db 构造 Server，注入 LLM 成本记录器与响应缓存，
//     装配 agent loop / 工具 / 技能 / 自进化 / 会话服务，并注册 gin 路由；
//   - Run：监听 cfg.Server.Host:Port 启动 HTTP 服务；
//   - Handler：返回 http.Handler 供 httptest 测试使用。
//
// 路由清单（前缀 /api）：
//   GET   /health                       健康检查（M1 验收：返回数据目录绝对路径）
//   GET   /topics                       列出全部主题
//   GET   /topics/:id/papers            列出某主题下论文
//   GET   /papers/:id                   查询单篇论文
//   PATCH /papers/:id/status            更新论文阅读状态
//   POST  /sync                         触发 GitHub 仓库同步
//   POST  /migrate-legacy               触发旧库迁移（找回历史数据）
//   POST  /chat/sessions                新建会话（M2）
//   GET   /chat/sessions                列出会话（M2）
//   GET   /chat/sessions/:id            查询会话详情（M2）
//   GET   /chat/sessions/:id/messages   列出会话消息（M2）
//   POST  /chat/sessions/:id/messages   非流式发消息（M2）
//   POST  /chat/sessions/:id/messages/stream  SSE 流式发消息（M2）
//   POST  /chat/evolve                  手动触发会话自进化（M2）
//   GET   /skills                       列出全部技能（M2）
//   POST  /skills                       创建/更新技能（M2）
//   DELETE /skills/:slug                删除技能（M2）
//   POST  /skills/:slug/evolve          查询技能自进化统计（M2）
//   POST  /memory                       创建记忆（M4，代理 Rust core）
//   GET   /memory/:id                   查询记忆（M4）
//   DELETE /memory/:id                  删除记忆（M4）
//   GET   /memory/search                关键字检索（M4）
//   POST  /memory/search-vector         向量相似度检索（M4）
//   POST  /memory/dream                 触发梦境整合（M4）
//   GET   /memory/dream-diary           列出 Dream Diary（M4）
//   GET   /memory/dream-diary/:id       查询单条 Dream Diary（M4）
//   POST  /memory/decision              记录决策到账本（M4）
//   GET   /memory/decisions             列出决策（M4）
//
// 设计要点：
//   - gin ReleaseMode 避免日志噪音；测试用 TestMode（newTestServer）；
//   - handler 在 handlers.go / chat_handlers.go 实现，本文件只负责装配；
//   - LLM 成本记录与缓存在此注入，后续 handler 调用 LLM 时自动生效。
package server

import (
	"database/sql"
	"fmt"
	"net/http"

	"github.com/gin-gonic/gin"

	"nuclear-ox-v2/backend/internal/agent"
	"nuclear-ox-v2/backend/internal/config"
	"nuclear-ox-v2/backend/internal/llm"
	"nuclear-ox-v2/backend/internal/memory"
	"nuclear-ox-v2/backend/internal/paper"
)

// Server 是后端 HTTP 服务。持有各层依赖，构造后调用 Run 启动。
type Server struct {
	cfg     *config.Config      // 全局配置
	db      *sql.DB             // 数据库连接（供技能等 handler 直接查询）
	repo    *paper.Repository   // 论文/主题数据访问
	llm     *llm.Client         // LLM 客户端
	github  *paper.GitHubClient // GitHub 同步客户端
	chat    *agent.ChatService  // 会话编排服务（M2）
	evolver *agent.Evolver      // 自进化器（M2，供手动触发端点使用）
	memory  *memory.Client      // Rust core 记忆/梦境客户端（M4）
	router  *gin.Engine         // gin 路由引擎
}

// New 依据 config 与已打开的 db 构造 Server。
// db 应为 store.Open 返回且已 Migrate 的连接（*sql.DB）。
// 构造时自动为 LLM 客户端注入成本记录器与响应缓存，并装配 M2 的 agent 链路。
func New(cfg *config.Config, db *sql.DB) *Server {
	// 生产模式：抑制 gin 启动日志噪音
	gin.SetMode(gin.ReleaseMode)

	s := &Server{
		cfg:    cfg,
		db:     db,
		repo:   paper.NewRepository(db),
		llm:    llm.New(cfg.LLM.Provider, cfg.LLM.Model, cfg.LLM.APIBase, cfg.LLM.APIKey, cfg.LLM.Timeout),
		github: paper.NewGitHubClient(cfg.GitHub.Token),
		// M4：Rust core HTTP 客户端（记忆/梦境/向量）。core 可能未启动，
		// 此处不探测连接，由实际请求时的 502 错误暴露（懒连接）。
		memory: memory.New(cfg.Core.BaseURL, cfg.Core.Timeout),
	}
	// 注入成本记录器：每次成功 LLM 调用写入 llm_calls 表
	s.llm.SetRecorder(llm.NewDBRecorder(db))
	// 注入响应缓存：相同请求命中 llm_cache 表，替代 Redis
	s.llm.SetCache(llm.NewCache(db))

	// --- M2 装配：工具 → agent loop → 技能 → 自进化 → 会话服务 ---
	// 工具注册表：内置 list_topics / search_papers / get_paper
	tools := agent.NewToolRegistry()
	agent.RegisterBuiltinTools(tools, s.repo)
	// agent loop：maxTurns/超时/预算用默认值（见 loop.go）
	ag := agent.NewAgent(s.llm, tools)
	// 技能注册表：auto 模式注入全部启用技能
	skills := agent.NewSkillRegistry(db, nil)
	// 自进化器
	s.evolver = agent.NewEvolver(s.llm, db)
	// 会话服务：串联上述组件
	s.chat = agent.NewChatService(db, ag, skills, s.evolver)

	s.router = s.buildRouter()
	return s
}

// setGitHubClient 替换 GitHub 客户端。供测试注入 mock baseURL 客户端。
func (s *Server) setGitHubClient(c *paper.GitHubClient) { s.github = c }

// buildRouter 注册全部路由。返回 gin.Engine。
func (s *Server) buildRouter() *gin.Engine {
	r := gin.New()
	// Recovery 中间件：捕获 panic 返回 500，避免单请求崩溃整个进程
	r.Use(gin.Recovery())

	api := r.Group("/api")
	{
		// --- M1：论文/主题/健康 ---
		api.GET("/health", s.getHealth)
		api.GET("/topics", s.listTopics)
		api.GET("/topics/:id/papers", s.listPapers)
		api.GET("/papers/:id", s.getPaper)
		api.PATCH("/papers/:id/status", s.updatePaperStatus)
		api.POST("/sync", s.syncPapers)
		api.POST("/migrate-legacy", s.migrateLegacy)

		// --- M2：会话与流式对话 ---
		api.POST("/chat/sessions", s.createSession)
		api.GET("/chat/sessions", s.listSessions)
		api.GET("/chat/sessions/:id", s.getSession)
		api.GET("/chat/sessions/:id/messages", s.listMessages)
		api.POST("/chat/sessions/:id/messages", s.sendMessage)
		api.POST("/chat/sessions/:id/messages/stream", s.sendMessageStream)
		api.POST("/chat/evolve", s.evolveSession)

		// --- M2：技能 CRUD + 自进化查询 ---
		api.GET("/skills", s.listSkills)
		api.POST("/skills", s.upsertSkill)
		api.DELETE("/skills/:slug", s.deleteSkill)
		api.POST("/skills/:slug/evolve", s.evolveSkill)

		// --- M4：记忆 / 梦境 / 决策（代理 Rust core） ---
		api.POST("/memory", s.createMemory)
		api.GET("/memory/:id", s.getMemory)
		api.DELETE("/memory/:id", s.deleteMemory)
		api.GET("/memory/search", s.searchMemory)
		api.POST("/memory/search-vector", s.searchVector)
		api.POST("/memory/dream", s.triggerDream)
		api.GET("/memory/dream-diary", s.listDreamDiary)
		api.GET("/memory/dream-diary/:id", s.getDreamDiary)
		api.POST("/memory/decision", s.addDecision)
		api.GET("/memory/decisions", s.listDecisions)
	}
	return r
}

// Handler 返回底层 http.Handler，供 httptest 测试使用。
// gin.Engine 实现了 http.Handler 接口（ServeHTTP）。
func (s *Server) Handler() http.Handler { return s.router }

// Run 启动 HTTP 服务，阻塞直至出错。
func (s *Server) Run() error {
	addr := fmt.Sprintf("%s:%d", s.cfg.Server.Host, s.cfg.Server.Port)
	return s.router.Run(addr)
}
