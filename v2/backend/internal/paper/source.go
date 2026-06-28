// Package paper 的数据源接口与 Source Manager。
//
// 文件概述：source.go 定义统一的论文数据源适配器接口 PaperSource 与多源管理器 SourceManager。
// 不同来源（arxiv/openalex/acl/company）实现 PaperSource 后注册到 SourceManager，
// 由 SyncAll 并发同步、幂等落库，单源失败不影响其他源。
package paper

import (
	"context"
	"fmt"
	"log"
	"sync"
	"time"
)

// PaperMeta 是数据源返回的论文元数据。
type PaperMeta struct {
	Title      string
	Authors    string
	Year       int
	Abstract   string
	PDFURL     string
	DOI        string
	ArxivID    string
	Source     string // arxiv/openalex/acl/company
	Venue      string
	Company    string
	GitHubRepo string
	Tags       []string
}

// PaperSource 是数据源适配器接口。
type PaperSource interface {
	ID() string // 源标识（arxiv/openalex/acl/company）
	Name() string
	Sync(ctx context.Context) ([]PaperMeta, error)
	TestConnection() error
}

// SyncResult 记录单个源的同步结果。
// JSON tag 必须为 snake_case，与前端 types.ts 对齐。
// Duration 是 time.Duration（int64 纳秒），JSON 序列化为整数；前端按需换算。
type SyncResult struct {
	SourceID string        `json:"source_id"`
	Success  bool          `json:"success"`
	Count    int           `json:"count"`
	Error    string        `json:"error"`
	Duration time.Duration `json:"duration"`
}

// SourceManager 管理多个数据源。
type SourceManager struct {
	sources []PaperSource
	repo    *Repository
	mu      sync.Mutex
}

func NewSourceManager(repo *Repository) *SourceManager {
	return &SourceManager{repo: repo}
}

func (m *SourceManager) Register(source PaperSource) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.sources = append(m.sources, source)
}

// SyncAll 并发同步所有源，单源失败不影响其他源。
func (m *SourceManager) SyncAll(ctx context.Context) []SyncResult {
	syncAllStart := time.Now()
	log.Printf("[SYNC] [INFO] SyncAll 启动，共 %d 个源", len(m.sources))

	var wg sync.WaitGroup
	results := make([]SyncResult, len(m.sources))

	for i, src := range m.sources {
		wg.Add(1)
		go func(idx int, source PaperSource) {
			defer wg.Done()
			start := time.Now()

			// panic recover
			defer func() {
				if r := recover(); r != nil {
					results[idx] = SyncResult{
						SourceID: source.ID(),
						Success:  false,
						Error:    fmt.Sprintf("panic: %v", r),
						Duration: time.Since(start),
					}
					log.Printf("[%s] [ERROR] panic: %v", source.ID(), r)
				}
			}()

			metas, err := source.Sync(ctx)
			if err != nil {
				results[idx] = SyncResult{
					SourceID: source.ID(),
					Success:  false,
					Error:    err.Error(),
					Duration: time.Since(start),
				}
				log.Printf("[%s] [ERROR] sync failed: %v", source.ID(), err)
				return
			}

			// 幂等写入数据库
			count := 0
			for _, meta := range metas {
				if err := m.repo.UpsertPaperMeta(meta); err != nil {
					log.Printf("[%s] [WARN] upsert failed for %s: %v", source.ID(), meta.Title, err)
					continue
				}
				count++
			}

			// 更新 sources 表（失败仅记日志，不阻断——论文已写入 papers 表，仅 sources 状态未刷新）
			if err := m.repo.UpdateSourceSync(source.ID(), len(metas)); err != nil {
				log.Printf("[%s] [WARN] UpdateSourceSync 失败: %v", source.ID(), err)
			}

			results[idx] = SyncResult{
				SourceID: source.ID(),
				Success:  true,
				Count:    count,
				Duration: time.Since(start),
			}
			log.Printf("[%s] [INFO] synced %d papers in %v", source.ID(), count, time.Since(start))
		}(i, src)
	}

	wg.Wait()

	// 汇总统计
	successCount, totalCount := 0, 0
	for _, r := range results {
		if r.Success {
			successCount++
			totalCount += r.Count
		}
	}
	failedCount := len(results) - successCount
	log.Printf("[SYNC] [INFO] SyncAll 完成: 成功 %d / 失败 %d / 新增 %d 篇 / 耗时 %v",
		successCount, failedCount, totalCount, time.Since(syncAllStart))

	return results
}

// SyncOne 同步指定源。
func (m *SourceManager) SyncOne(ctx context.Context, sourceID string) (*SyncResult, error) {
	for _, src := range m.sources {
		if src.ID() == sourceID {
			log.Printf("[%s] [INFO] SyncOne 启动", sourceID)
			start := time.Now()
			metas, err := src.Sync(ctx)
			if err != nil {
				log.Printf("[%s] [ERROR] SyncOne 失败: %v", sourceID, err)
				return &SyncResult{
					SourceID: sourceID,
					Success:  false,
					Error:    err.Error(),
					Duration: time.Since(start),
				}, err
			}
			count := 0
			for _, meta := range metas {
				if err := m.repo.UpsertPaperMeta(meta); err != nil {
					log.Printf("[%s] [WARN] upsert failed for %s: %v", sourceID, meta.Title, err)
					continue
				}
				count++
			}
			// 更新 sources 表（失败仅记日志，不阻断——论文已写入 papers 表，仅 sources 状态未刷新）
			if err := m.repo.UpdateSourceSync(sourceID, len(metas)); err != nil {
				log.Printf("[%s] [WARN] UpdateSourceSync 失败: %v", sourceID, err)
			}
			log.Printf("[%s] [INFO] SyncOne 完成: 新增 %d 篇 / 耗时 %v", sourceID, count, time.Since(start))
			return &SyncResult{
				SourceID: sourceID,
				Success:  true,
				Count:    count,
				Duration: time.Since(start),
			}, nil
		}
	}
	return nil, fmt.Errorf("source %s not found", sourceID)
}

func (m *SourceManager) ListSources() []PaperSource {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.sources
}
