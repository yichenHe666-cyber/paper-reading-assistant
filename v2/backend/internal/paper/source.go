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
type SyncResult struct {
	SourceID string
	Success  bool
	Count    int
	Error    string
	Duration time.Duration
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

			// 更新 sources 表
			m.repo.UpdateSourceSync(source.ID(), len(metas))

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
	return results
}

// SyncOne 同步指定源。
func (m *SourceManager) SyncOne(ctx context.Context, sourceID string) (*SyncResult, error) {
	for _, src := range m.sources {
		if src.ID() == sourceID {
			start := time.Now()
			metas, err := src.Sync(ctx)
			if err != nil {
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
					continue
				}
				count++
			}
			m.repo.UpdateSourceSync(sourceID, len(metas))
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
