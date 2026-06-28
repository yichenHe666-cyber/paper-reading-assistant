// Package memory 是 Go 后端调用 Rust core（向量化/记忆/梦境）的编排层。
//
// 文件概述：types.go 定义与 Rust core（v2/core/src）对齐的 Go 数据结构。
// 所有字段名与 Rust 侧 serde JSON 序列化保持一致（snake_case），确保透传无歧义。
//
// 对应关系：
//   - Memory            ↔ core::memory::Memory
//   - CreateMemoryRequest ↔ core::memory::CreateMemoryRequest（layer 用字符串，与 Rust as_str 对齐）
//   - SimilarMemory     ↔ core::memory::SimilarMemory
//   - DreamResult       ↔ core::dreaming::DreamResult
//   - ScoreBreakdown    ↔ core::dreaming::ScoreBreakdown（六信号明细）
//   - DreamDiaryEntry   ↔ core::dreaming::DreamDiaryEntry
//   - DecisionEntry     ↔ core::memory::DecisionEntry
package memory

// Memory 对应 memories 表一行，与 Rust core Memory 结构镜像。
type Memory struct {
	ID              string  `json:"id"`
	Layer           string  `json:"layer"`
	Content         string  `json:"content"`
	ImportanceScore float64 `json:"importance_score"`
	DecayState      string  `json:"decay_state"`
	EmbeddingID     string  `json:"embedding_id"`
	CreatedAt       string  `json:"created_at"`
}

// 记忆层级常量（与 Rust core MemoryLayer::as_str 对齐）。
// 注意：procedural 层在 spec §5.1 中存在，但 Rust core 首期未实现该层 CRUD
// （程序记忆复用 skills 表，由 Go 侧管理），故此处不导出 procedural 常量。
const (
	LayerEpisodic = "episodic"
	LayerLongTerm = "long_term"
	LayerIndex    = "index"
)

// CreateMemoryRequest 创建记忆请求。ImportanceScore 缺省由 Rust 侧补 0.5。
type CreateMemoryRequest struct {
	Layer           string  `json:"layer"`
	Content         string  `json:"content"`
	ImportanceScore float64 `json:"importance_score"`
}

// SimilarMemory 向量相似度检索结果。
type SimilarMemory struct {
	Memory     Memory  `json:"memory"`
	Similarity float64 `json:"similarity"`
}

// ScoreBreakdown 六信号评分明细（spec §5.2）。
// 用于 Dream Diary 详情展示，便于调试"为何忘记/为何升级"。
type ScoreBreakdown struct {
	MemoryID      string  `json:"memory_id"`
	Relevance     float64 `json:"relevance"`
	Frequency     float64 `json:"frequency"`
	Diversity     float64 `json:"diversity"`
	Recency       float64 `json:"recency"`
	Integration   float64 `json:"integration"`
	Richness      float64 `json:"richness"`
	Reinforcement float64 `json:"reinforcement"`
	Total         float64 `json:"total"`
	Promoted      bool    `json:"promoted"`
	Reason        string  `json:"reason"`
}

// DreamResult 一次梦境整合的结果（对应 Rust core DreamResult）。
type DreamResult struct {
	DiaryID       string           `json:"diary_id"`
	StartedAt     string           `json:"started_at"`
	FinishedAt    string           `json:"finished_at"`
	ReviewedCount int              `json:"reviewed_count"`
	PromotedCount int              `json:"promoted_count"`
	DecayedCount  int              `json:"decayed_count"`
	Summary       string           `json:"summary"`
	Breakdowns    []ScoreBreakdown `json:"breakdowns"`
}

// DreamDiaryEntry Dream Diary 单条记录（对应 dream_diary 表）。
// run_id 关联同一次梦境的 light/rem/deep/done 四阶段日志。
type DreamDiaryEntry struct {
	ID            string `json:"id"`
	RunID         string `json:"run_id"`
	StartedAt     string `json:"started_at"`
	FinishedAt    string `json:"finished_at"`
	Stage         string `json:"stage"`
	ReviewedCount int64  `json:"reviewed_count"`
	PromotedCount int64  `json:"promoted_count"`
	DecayedCount  int64  `json:"decayed_count"`
	Summary       string `json:"summary"`
	DetailsJSON   string `json:"details_json"`
}

// DecisionEntry 决策账本条目（对应 decision_ledger 表，spec §5.5）。
type DecisionEntry struct {
	ID        string `json:"id"`
	Context   string `json:"context"`
	Decision  string `json:"decision"`
	Rationale string `json:"rationale"`
	Outcome   string `json:"outcome"`
	CreatedAt string `json:"created_at"`
}

// CreateDecisionRequest 创建决策请求。
type CreateDecisionRequest struct {
	Context   string `json:"context"`
	Decision  string `json:"decision"`
	Rationale string `json:"rationale"`
	Outcome   string `json:"outcome"`
}

// searchVectorRequest 向量检索请求体（Go 内部用，对应 Rust core SearchVectorRequest）。
//
// TopK 用 omitempty：当调用方传 0（表示"用 Rust 侧默认值"）时，该字段不写入 JSON，
// Rust 侧 serde #[serde(default = "default_top_k")] 才能生效（serde default 仅在字段缺失时触发，
// 字段存在但值为 0 时不会用 default）。修复审查发现的核心 Blocker：原实现始终发送 top_k:0，
// 导致向量检索永远返回空。
type searchVectorRequest struct {
	Query string `json:"query"`
	TopK  int    `json:"top_k,omitempty"`
}

// itemsWrapper 是 Rust core 列表响应的统一包装 {"items": [...]}。
// 仅 client 内部解码用，对外暴露切片。
type itemsWrapper[T any] struct {
	Items []T `json:"items"`
}
