// API 类型定义。
//
// 与 Go 后端 struct 一一对应，确保前后端契约稳定。
// 字段名按 JSON tag（snake_case）镜像，避免每次手写转换。
//
// 后端来源：
//   - store.Session / store.Message / store.Skill
//   - paper.Paper / paper.Source / paper.PaperDetail / paper.ReadingStats
//   - paper.PaperFilter / paper.SyncResult
//   - agent.StreamEvent / agent.Usage
//   - server handlers 的响应 gin.H

// --- 论文与主题 ---

export interface Topic {
  id: string
  name: string
  name_cn: string
  paper_count: number
  created_at: string
}

export type ReadStatus = 'unread' | 'reading' | 'done' | 'reread'

// Paper 表示一篇论文的元数据。
// 字段名按后端 json tag（snake_case）镜像，与 paper.Paper struct 一一对应。
export interface Paper {
  id: string
  title: string
  authors: string
  year: number
  topic_id: string
  pdf_url: string
  doi: string
  abstract: string
  read_status: ReadStatus
  obsidian_path: string
  created_at: string
  // --- 多数据源扩展字段（arXiv/OpenAlex/ACL/Company） ---
  source: string // 数据源：arxiv/openalex/acl/company
  venue: string // 发表会议/期刊
  level: string // AI 分类难度：beginner/intermediate/advanced
  paper_type: string // 论文类型：survey/tutorial/classic/original/research/...
  sub_domain: string // 子领域：ml/dl/llm/safety/rl/reasoning/infra/dist_sys/...
  difficulty_score: number // 难度评分 1-10
  tags: string // 标签 JSON 数组字符串，如 '["transformer","attention"]'
  ai_classified: number // 分类状态：0=未分类（待 AI 分类），1=已分类（AI 或人工预设种子）
  company: string // 公司名（company 源用）
  github_repo: string // GitHub 仓库全名（company 源用）
  arxiv_id: string // arXiv ID
  last_read_at: string // 上次阅读时间
  total_read_seconds: number // 累计阅读时长（秒）
}

// Source 表示一个论文数据源（arxiv/openalex/acl/company 等）。
export interface Source {
  id: string
  name: string
  source_type: string
  enabled: number // 0/1（SQLite 整数布尔）
  last_synced_at: string
  sync_count: number
  config: string
}

// ReadingStats 是论文阅读历史统计。
export interface ReadingStats {
  count: number // 阅读次数（reading_history 记录数）
  total_seconds: number // 累计阅读时长（秒）
  last_read_at: string // 上次阅读时间
}

// PaperDetail 是论文详情（论文元数据 + 阅读统计）。
// 对应后端 paper.PaperDetail（内嵌 Paper + ReadingStats）。
export interface PaperDetail extends Paper {
  reading_stats: ReadingStats
}

// ListPapersResponse 是 GET /api/papers 的响应体。
export interface ListPapersResponse {
  papers: Paper[]
  total: number
  page: number
  page_size: number
}

// PaperFilter 是 listPapers 的过滤条件，字段对应后端 query string 参数。
// 空值不传递，由 client.listPapers 负责剔除。
export interface PaperFilter {
  source?: string // 数据源：arxiv/openalex/acl/company
  level?: string // 难度：beginner/intermediate/advanced
  sub_domain?: string // 子领域：ml/dl/llm/...
  paper_type?: string // 论文类型：survey/tutorial/...
  q?: string // 关键词（标题/作者/摘要模糊匹配）
  page?: number // 页码，从 1 开始
  page_size?: number // 每页条数
}

// SyncResult 记录单个数据源的同步结果。
export interface SyncResult {
  source_id: string
  success: boolean
  count: number
  error: string
  duration: number // 同步耗时（纳秒，time.Duration 序列化值）
}

// SyncSourcesResponse 是 POST /api/sources/sync 的响应体。
// 除各源明细 results 外，附带汇总统计，与后端 server.syncSourcesResponse 对齐。
export interface SyncSourcesResponse {
  results: SyncResult[]
  total_sources: number // 参与同步的源总数
  success_count: number // 成功源数
  failed_count: number // 失败源数
  total_papers: number // 新增论文数（成功源的 count 之和）
}

// ClassifyResponse 是 POST /api/papers/classify 的响应体。
export interface ClassifyResponse {
  classified: number
}

// --- 会话与消息 ---

export type SkillMode = 'auto' | 'manual' | 'hybrid'

export interface Session {
  id: string
  title: string
  skill_mode: SkillMode
  enabled_skill_ids: string // JSON 数组字符串，如 '["summarize","qa"]'
  total_tokens: number
  message_count: number
  created_at: string
  updated_at: string
}

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool'

export interface Message {
  id: string
  session_id: string
  role: MessageRole
  content: string
  reasoning_content: string
  tool_calls: string // JSON 字符串
  tool_call_id: string
  token_count: number
  context_usage_pct: number
  created_at: string
}

// --- 技能 ---

export interface Skill {
  id: string
  slug: string
  name: string
  description: string
  content: string
  enabled: boolean
  level: number
  usage_count: number
  success_rate: number
  version: number
  last_improved_at: string
  created_at: string
}

// --- 健康检查 ---

export interface HealthInfo {
  status: string
  data_dir: string
  db_path: string
  paper_count: number
  topic_count: number
  llm_provider: string
  llm_model: string
}

// --- 发消息响应（非流式） ---

export interface ToolCallInfo {
  id: string
  name: string
  args: string
}

export interface Usage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface SendMessageResponse {
  content: string
  tool_calls: ToolCallInfo[]
  turns: number
  usage?: Usage
  error?: string
}

// --- 自进化草稿 ---

export interface EvolveResult {
  slug: string
  name: string
  description: string
  worth_saving: boolean
  saved: boolean
}

// --- SSE 流式事件（与 agent.StreamEvent 对齐） ---

export type StreamEventType = 'token' | 'tool_call' | 'tool_result' | 'usage' | 'error' | 'done' | 'end'

export interface StreamEvent {
  type: StreamEventType
  content?: string
  tool_name?: string
  tool_call_id?: string
  tool_args?: string
  tool_result?: string
  usage?: Usage
  turn?: number
}

// --- 统一错误响应 ---

export interface ApiError {
  error: string
}

// --- 记忆 / 梦境 / 决策（M4，代理 Rust core）---
// 与后端 memory 包的 Go 类型镜像，字段名按 snake_case 对齐 Rust serde 序列化。

// 记忆层级常量（与 Rust core MemoryLayer::as_str 对齐）。
export type MemoryLayer = 'episodic' | 'long_term' | 'index'

export interface Memory {
  id: string
  layer: MemoryLayer
  content: string
  importance_score: number
  decay_state: string // active / decaying / promoted
  embedding_id: string
  created_at: string
}

export interface CreateMemoryRequest {
  layer: MemoryLayer
  content: string
  importance_score?: number // 缺省由 Rust 侧补 0.5
}

// 向量相似度检索结果。
export interface SimilarMemory {
  memory: Memory
  similarity: number
}

// 六信号评分明细（spec §5.2），用于 Dream Diary 详情。
export interface ScoreBreakdown {
  memory_id: string
  relevance: number
  frequency: number
  diversity: number
  recency: number
  integration: number
  richness: number
  reinforcement: number
  total: number
  promoted: boolean
  reason: string
}

// 一次梦境整合的结果。
export interface DreamResult {
  diary_id: string
  started_at: string
  finished_at: string
  reviewed_count: number
  promoted_count: number
  decayed_count: number
  summary: string
  breakdowns: ScoreBreakdown[]
}

// Dream Diary 单条记录。
export interface DreamDiaryEntry {
  id: string
  run_id: string
  started_at: string
  finished_at: string
  stage: string // light / rem / deep / done
  reviewed_count: number
  promoted_count: number
  decayed_count: number
  summary: string
  details_json: string
}

// 决策账本条目（spec §5.5）。
export interface DecisionEntry {
  id: string
  context: string
  decision: string
  rationale: string
  outcome: string
  created_at: string
}

export interface CreateDecisionRequest {
  context: string
  decision: string
  rationale?: string
  outcome?: string
}
