// API 类型定义。
//
// 与 Go 后端 struct 一一对应，确保前后端契约稳定。
// 字段名按 JSON tag（snake_case）镜像，避免每次手写转换。
//
// 后端来源：
//   - store.Session / store.Message / store.Skill
//   - paper.Topic / paper.Paper
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

// --- 同步与迁移 ---

export interface SyncResult {
  owner: string
  repo: string
  topics_added: number
  papers_added: number
}

export interface MigrateResult {
  source_db: string
  topics_added?: number
  papers_added?: number
  error?: string
}

export interface MigrateLegacyResponse {
  found: number
  results: MigrateResult[]
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
