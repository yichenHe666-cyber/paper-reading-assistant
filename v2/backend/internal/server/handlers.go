// Package server 的路由 handler 实现。
//
// 文件概述：handlers.go 实现 server.go 注册的全部 /api 路由的请求处理。
// 每个 handler 负责：解析入参 → 调用 repo/sourceMgr/classifier → 统一 JSON 响应与错误码。
//
// 响应约定：
//   - 成功：HTTP 200 + 业务数据 JSON；
//   - 未找到：HTTP 404 + {"error": "..."}；
//   - 请求错误：HTTP 400 + {"error": "..."}；
//   - 内部错误：HTTP 500 + {"error": "..."}。
package server

import (
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"

	"nuclear-ox-v2/backend/internal/paper"
)

// healthResponse 是 /api/health 的响应体。
// data_dir 与 db_path 为绝对路径——这是 M1 验收点：健康接口必须返回数据目录绝对路径，
// 用于确认路径绝对化生效（痛点②修复可视验证）。
type healthResponse struct {
	Status      string `json:"status"`       // "ok"
	DataDir     string `json:"data_dir"`     // 数据根目录（绝对路径）
	DBPath      string `json:"db_path"`      // 数据库路径（绝对路径）
	PaperCount  int    `json:"paper_count"`  // 当前论文总数（验证"重启是否为 0"）
	TopicCount  int    `json:"topic_count"`  // 主题数
	LLMProvider string `json:"llm_provider"` // 当前 LLM provider
	LLMModel    string `json:"llm_model"`    // 当前 LLM 模型
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

// listPapersResponse 是 GET /api/papers 的响应体。
type listPapersResponse struct {
	Papers   []paper.Paper `json:"papers"`
	Total    int           `json:"total"`
	Page     int           `json:"page"`
	PageSize int           `json:"page_size"`
}

// listPapers 按过滤条件分页列出论文。
// 查询参数：source, level, sub_domain, paper_type, q, page(默认1), page_size(默认20)。
func (s *Server) listPapers(c *gin.Context) {
	filter := paper.PaperFilter{
		Source:    c.Query("source"),
		Level:     c.Query("level"),
		SubDomain: c.Query("sub_domain"),
		PaperType: c.Query("paper_type"),
		Query:     c.Query("q"),
		Page:      atoiDefault(c.Query("page"), 1),
		PageSize:  atoiDefault(c.Query("page_size"), 20),
	}
	if filter.Page < 1 {
		filter.Page = 1
	}
	if filter.PageSize < 1 {
		filter.PageSize = 20
	}
	// page_size 上限 100，防止恶意请求一次拉取全表导致内存/延迟尖峰
	if filter.PageSize > 100 {
		filter.PageSize = 100
	}

	papers, total, err := s.repo.ListPapers(filter)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if papers == nil {
		papers = []paper.Paper{}
	}
	c.JSON(http.StatusOK, listPapersResponse{
		Papers: papers, Total: total, Page: filter.Page, PageSize: filter.PageSize,
	})
}

// getPaper 查询单篇论文详情（含阅读历史统计）。
func (s *Server) getPaper(c *gin.Context) {
	id := c.Param("id")
	detail, err := s.repo.GetPaperWithHistory(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if detail == nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "论文不存在: " + id})
		return
	}
	c.JSON(http.StatusOK, detail)
}

// pdfProxyClient 是 PDF 代理专用 HTTP 客户端。
// 超时 30s 避免恶意慢速上游拖垮后端；代理仅拉取 PDF，30s 足够。
var pdfProxyClient = &http.Client{Timeout: 30 * time.Second}

// maxPDFSize 限制单次代理的 PDF 体积（50MB），防止恶意上游用大响应撑爆内存。
const maxPDFSize = 50 * 1024 * 1024

// proxyPaperPDF 代理拉取论文 PDF 流。pdf_url 为空或论文不存在时返回 404。
//
// SSRF 防护（修复审查发现的高危项）：
//   - 仅允许 http/https scheme，禁止 file:///、gopher:// 等；
//   - 解析主机名并拒绝内网/回环/链路本地地址，防止容器内代理访问内网元数据服务
//     （如 169.254.169.254 云厂商元数据、127.0.0.1 本机服务、10/172.16/192.168 私网）；
//   - 限制响应体积 50MB，避免恶意上游用大响应耗尽内存；
//   - 超时 30s，避免慢速上游拖垮 gin worker。
func (s *Server) proxyPaperPDF(c *gin.Context) {
	id := c.Param("id")
	p, err := s.repo.GetPaper(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if p == nil || p.PDFURL == "" {
		c.JSON(http.StatusNotFound, gin.H{"error": "PDF 不存在: " + id})
		return
	}

	if err := validatePDFURL(p.PDFURL); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "PDF 地址非法: " + err.Error()})
		return
	}

	resp, err := pdfProxyClient.Get(p.PDFURL)
	if err != nil {
		c.JSON(http.StatusBadGateway, gin.H{"error": "获取 PDF 失败: " + err.Error()})
		return
	}
	defer resp.Body.Close()

	// 仅代理 2xx 响应；上游 4xx/5xx 透传状态码但不流式转发可能的 HTML 错误页
	if resp.StatusCode != http.StatusOK {
		c.JSON(http.StatusBadGateway, gin.H{"error": fmt.Sprintf("PDF 源返回非 200: status=%d", resp.StatusCode)})
		return
	}

	c.Header("Content-Type", "application/pdf")
	c.Status(resp.StatusCode)
	// 限制读取体积，超限即停止（已写入部分仍返回，浏览器会因 PDF 截断报错，但服务器不会被撑爆）
	limited := io.LimitReader(resp.Body, maxPDFSize+1)
	if _, err := io.Copy(c.Writer, limited); err != nil {
		// 客户端可能已断开，仅记日志由 Recovery 兜底
		_ = err
	}
}

// validatePDFURL 校验 PDF URL 安全性：scheme 限定 http/https，主机名禁止指向内网/回环/链路本地。
// 解析主机名后做 DNS 查询，对所有解析到的 IP 逐一校验，防止 DNS rebinding 到内网地址。
func validatePDFURL(rawURL string) error {
	u, err := url.Parse(rawURL)
	if err != nil {
		return fmt.Errorf("URL 解析失败: %w", err)
	}
	scheme := strings.ToLower(u.Scheme)
	if scheme != "http" && scheme != "https" {
		return fmt.Errorf("仅允许 http/https，实际 scheme=%s", scheme)
	}
	host := u.Hostname()
	if host == "" {
		return fmt.Errorf("URL 缺少主机名")
	}
	// 解析主机名到 IP（可能是域名或字面量 IP）
	ips, err := net.LookupIP(host)
	if err != nil {
		return fmt.Errorf("解析主机 %s 失败: %w", host, err)
	}
	for _, ip := range ips {
		if !ip.IsGlobalUnicast() || ip.IsLoopback() || ip.IsPrivate() || ip.IsLinkLocalUnicast() || ip.IsUnspecified() {
			return fmt.Errorf("主机 %s 解析到内网/回环地址 %s，禁止代理", host, ip)
		}
	}
	return nil
}

// getRelatedPapers 返回与指定论文 sub_domain 相同的前 10 篇论文（排除自身）。
func (s *Server) getRelatedPapers(c *gin.Context) {
	id := c.Param("id")
	papers, err := s.repo.GetRelatedPapers(id, 10)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if papers == nil {
		papers = []paper.Paper{}
	}
	c.JSON(http.StatusOK, papers)
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

// startReading 开始阅读：创建 reading_history 记录并把论文状态置为 reading。
func (s *Server) startReading(c *gin.Context) {
	id := c.Param("id")
	historyID, err := s.repo.CreateReadingHistory(id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if err := s.repo.UpdatePaperReadStatus(id, "reading"); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"history_id": historyID})
}

// endReadingRequest 是 POST /papers/:id/reading-end 的请求体。
type endReadingRequest struct {
	HistoryID string `json:"history_id" binding:"required"`
}

// endReading 结束阅读：更新 reading_history 的 end_time/duration 与 papers 阅读统计。
func (s *Server) endReading(c *gin.Context) {
	id := c.Param("id")
	var req endReadingRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "请求体非法: " + err.Error()})
		return
	}
	if err := s.repo.EndReadingHistory(req.HistoryID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"history_id": req.HistoryID, "paper_id": id})
}

// classifyPaperRequest 是 POST /papers/classify 的请求体（paper_id 可空表示全量分类）。
type classifyPaperRequest struct {
	PaperID string `json:"paper_id"`
}

// classifyPaper 调用 AIClassifier 对单篇或全量论文做难度分类。
func (s *Server) classifyPaper(c *gin.Context) {
	var req classifyPaperRequest
	// 请求体可选：空 body 走全量分类
	_ = c.ShouldBindJSON(&req)

	if s.classifier == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "分类器未初始化"})
		return
	}

	var classified int
	if req.PaperID != "" {
		if err := s.classifier.ClassifyPaper(c.Request.Context(), s.repo, req.PaperID); err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		classified = 1
	} else {
		n, err := s.classifier.ClassifyBatch(c.Request.Context(), s.repo)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		classified = n
	}
	c.JSON(http.StatusOK, gin.H{"classified": classified})
}

// listSources 列出所有数据源及状态。
func (s *Server) listSources(c *gin.Context) {
	sources, err := s.repo.ListSources()
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	if sources == nil {
		sources = []paper.Source{}
	}
	c.JSON(http.StatusOK, sources)
}

// syncSourcesRequest 是 POST /sources/sync 的可选请求体（source 可空表示全部同步）。
type syncSourcesRequest struct {
	Source string `json:"source"`
}

// syncSourcesResponse 是 POST /sources/sync 的响应体。
// 除各源明细 results 外，附带汇总统计，便于前端直接展示"成功 X / 失败 Y / 新增 Z 篇"，
// 也便于从日志快速定位"重启后论文丢失"类问题。
type syncSourcesResponse struct {
	Results      []paper.SyncResult `json:"results"`
	TotalSources int                `json:"total_sources"`
	SuccessCount int                `json:"success_count"`
	FailedCount  int                `json:"failed_count"`
	TotalPapers  int                `json:"total_papers"` // 新增论文数（成功源的 count 之和）
}

// syncSources 触发数据源同步。source 指定时单源同步，否则全量同步。
// 同步前后打印日志，便于排查"重启后论文丢失"类问题。
func (s *Server) syncSources(c *gin.Context) {
	var req syncSourcesRequest
	// 请求体可选
	_ = c.ShouldBindJSON(&req)

	if s.sourceMgr == nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "源管理器未初始化"})
		return
	}

	start := time.Now()

	if req.Source != "" {
		// 单源同步
		log.Printf("[SYNC] [INFO] 开始单源同步: %s", req.Source)
		result, err := s.sourceMgr.SyncOne(c.Request.Context(), req.Source)
		if result == nil {
			// 源未注册：SyncOne 返回 (nil, err)，保持原有 502 错误响应
			log.Printf("[SYNC] [WARN] 单源同步失败: %s / 耗时 %v / 原因: %v", req.Source, time.Since(start), err)
			c.JSON(http.StatusBadGateway, gin.H{"error": "同步失败: " + err.Error()})
			return
		}
		resp := syncSourcesResponse{
			Results:      []paper.SyncResult{*result},
			TotalSources: 1,
			TotalPapers:  result.Count,
		}
		if result.Success {
			resp.SuccessCount = 1
		} else {
			resp.FailedCount = 1
		}
		log.Printf("[SYNC] [INFO] 单源同步完成: %s / 成功 %d / 失败 %d / 新增 %d 篇 / 耗时 %v",
			req.Source, resp.SuccessCount, resp.FailedCount, resp.TotalPapers, time.Since(start))
		c.JSON(http.StatusOK, resp)
		return
	}

	// 全量同步
	total := len(s.sourceMgr.ListSources())
	log.Printf("[SYNC] [INFO] 开始全量同步 %d 个源", total)
	results := s.sourceMgr.SyncAll(c.Request.Context())
	resp := syncSourcesResponse{
		Results:      results,
		TotalSources: total,
	}
	for _, r := range results {
		if r.Success {
			resp.SuccessCount++
			resp.TotalPapers += r.Count
		} else {
			resp.FailedCount++
		}
	}
	log.Printf("[SYNC] [INFO] 同步完成: 成功 %d / 失败 %d / 新增 %d 篇 / 耗时 %v",
		resp.SuccessCount, resp.FailedCount, resp.TotalPapers, time.Since(start))
	c.JSON(http.StatusOK, resp)
}

// atoiDefault 将字符串转为 int，失败或 <=0 时返回 def。
func atoiDefault(s string, def int) int {
	if s == "" {
		return def
	}
	n, err := strconv.Atoi(s)
	if err != nil || n <= 0 {
		return def
	}
	return n
}
