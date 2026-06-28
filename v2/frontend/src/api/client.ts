// 显式 UTF-8 API 客户端。
//
// 痛点③修复要点（spec §4.3）：
//   - 请求头显式 Content-Type: application/json; charset=utf-8，避免浏览器探测；
//   - 响应一律 .json()，错误信息走结构化 JSON {error:string} 而非 text[:200]；
//   - 非 2xx 状态抛 ApiCallError，携带 status 与 server-side message；
//   - SSE 流式通过 fetch + ReadableStream 解析，不依赖 EventSource（后者不支持 POST）。

import type {
  ApiError,
  ClassifyResponse,
  CreateDecisionRequest,
  CreateMemoryRequest,
  DecisionEntry,
  DreamDiaryEntry,
  DreamResult,
  EvolveResult,
  HealthInfo,
  ListPapersResponse,
  Memory,
  Message,
  Paper,
  PaperDetail,
  PaperFilter,
  ReadStatus,
  Session,
  SimilarMemory,
  Skill,
  SkillMode,
  Source,
  StreamEvent,
  SendMessageResponse,
  SyncSourcesResponse,
} from './types'

// API 基地址：优先用 VITE_API_BASE，缺省走相对路径（dev 由 vite proxy 转发）。
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

// ApiCallError 是统一错误类型。携带 HTTP 状态码与服务器返回的错误消息。
export class ApiCallError extends Error {
  constructor(
    public readonly status: number,
    public readonly message: string,
    public readonly url: string,
  ) {
    super(`[${status}] ${message}`)
    this.name = 'ApiCallError'
  }
}

// parseApiError 从 Response 解析错误消息。优先用结构化 {error:string}，回退到 text。
async function parseApiError(resp: Response): Promise<string> {
  try {
    const body = (await resp.clone().json()) as ApiError
    if (body && typeof body.error === 'string' && body.error.length > 0) {
      return body.error
    }
  } catch {
    // 响应非 JSON，回退到 text
  }
  // 限制 text 长度避免超大错误体撑爆 UI
  const text = await resp.text()
  return text.slice(0, 200) || resp.statusText
}

// request 是统一的 JSON 请求封装。
//   - 显式 charset=utf-8，杜绝 ISO-8859-1 误判（旧版 resp.text 真乱码根因）；
//   - 自动 JSON 序列化/反序列化；
//   - 非 2xx 抛 ApiCallError。
async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = `${API_BASE}${path}`
  const headers: Record<string, string> = {
    // 显式声明 UTF-8：服务端按字节读，浏览器按 utf-8 解码
    'Content-Type': 'application/json; charset=utf-8',
    Accept: 'application/json',
  }
  const init: RequestInit = { method, headers }
  if (body !== undefined) {
    init.body = JSON.stringify(body)
  }

  const resp = await fetch(url, init)
  if (!resp.ok) {
    const msg = await parseApiError(resp)
    throw new ApiCallError(resp.status, msg, url)
  }
  // 204/空响应不解析
  if (resp.status === 204) {
    return undefined as T
  }
  return (await resp.json()) as T
}

// --- 健康检查 ---
export function getHealth(): Promise<HealthInfo> {
  return request<HealthInfo>('GET', '/api/health')
}

// --- 论文检索/阅读/分类 ---

// listPapers 按过滤条件分页列出论文。filter 字段作为 query string 传递，空值不传。
export function listPapers(filter: PaperFilter = {}): Promise<ListPapersResponse> {
  const params = new URLSearchParams()
  if (filter.source) params.set('source', filter.source)
  if (filter.level) params.set('level', filter.level)
  if (filter.sub_domain) params.set('sub_domain', filter.sub_domain)
  if (filter.paper_type) params.set('paper_type', filter.paper_type)
  if (filter.q) params.set('q', filter.q)
  if (filter.page) params.set('page', String(filter.page))
  if (filter.page_size) params.set('page_size', String(filter.page_size))
  const qs = params.toString()
  const path = qs ? `/api/papers?${qs}` : '/api/papers'
  return request<ListPapersResponse>('GET', path)
}

// getPaper 查询单篇论文详情（含阅读历史统计）。
export function getPaper(id: string): Promise<PaperDetail> {
  return request<PaperDetail>('GET', `/api/papers/${encodeURIComponent(id)}`)
}

// paperPDFURL 返回论文 PDF 的代理流地址，供 <iframe src>/<embed src> 直接使用。
// 不发起请求——PDF 由浏览器直接拉取渲染，前端不要 fetch 解析（避免 blob 编码问题）。
export function paperPDFURL(id: string): string {
  return `${API_BASE}/api/papers/${encodeURIComponent(id)}/pdf`
}

// getRelatedPapers 返回与指定论文 sub_domain 相同的相关论文（后端取前 10 篇）。
export function getRelatedPapers(id: string): Promise<Paper[]> {
  return request<Paper[]>('GET', `/api/papers/${encodeURIComponent(id)}/related`)
}

// updatePaperStatus 更新论文阅读状态（unread/reading/done/reread）。
export function updatePaperStatus(id: string, status: ReadStatus): Promise<{ id: string; status: ReadStatus }> {
  return request('PATCH', `/api/papers/${encodeURIComponent(id)}/status`, { status })
}

// startReading 开始阅读：创建 reading_history 记录并把论文状态置为 reading。
export function startReading(id: string): Promise<{ history_id: string }> {
  return request<{ history_id: string }>('POST', `/api/papers/${encodeURIComponent(id)}/reading-start`)
}

// endReading 结束阅读：更新 reading_history 的 end_time/duration 与 papers 阅读统计。
export function endReading(id: string, historyId: string): Promise<{ history_id: string; paper_id: string }> {
  return request<{ history_id: string; paper_id: string }>(
    'POST',
    `/api/papers/${encodeURIComponent(id)}/reading-end`,
    { history_id: historyId },
  )
}

// classifyPaper 触发 AI 难度分类。paperId 省略时走全量分类，返回已分类条数。
export function classifyPaper(paperId?: string): Promise<ClassifyResponse> {
  return request<ClassifyResponse>('POST', '/api/papers/classify', { paper_id: paperId ?? '' })
}

// --- 数据源管理 ---

// listSources 列出所有数据源及同步状态。
export function listSources(): Promise<Source[]> {
  return request<Source[]>('GET', '/api/sources')
}

// syncSources 触发数据源同步。source 指定时单源同步，省略（空串）时全量同步。
// 返回各源明细 results 与汇总统计（total_sources/success_count/failed_count/total_papers）。
export function syncSources(source?: string): Promise<SyncSourcesResponse> {
  return request<SyncSourcesResponse>('POST', '/api/sources/sync', { source: source ?? '' })
}

// --- 会话 ---
export interface CreateSessionRequest {
  title?: string
  skill_mode?: SkillMode
  enabled_slugs?: string[]
}

export function createSession(req: CreateSessionRequest = {}): Promise<{ id: string }> {
  return request<{ id: string }>('POST', '/api/chat/sessions', req)
}

export function listSessions(): Promise<Session[]> {
  return request<Session[]>('GET', '/api/chat/sessions')
}

export function getSession(id: string): Promise<Session> {
  return request<Session>('GET', `/api/chat/sessions/${encodeURIComponent(id)}`)
}

export function listMessages(sessionId: string): Promise<Message[]> {
  return request<Message[]>('GET', `/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`)
}

export function sendMessage(sessionId: string, content: string): Promise<SendMessageResponse> {
  return request<SendMessageResponse>('POST', `/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`, { content })
}

// sendMessageStream 通过 SSE 流式发消息。
//
// 设计：fetch + ReadableStream 手写 SSE 解析。
//   - EventSource 不支持 POST，故必须用 fetch；
//   - 逐行扫描，"data: " 前缀的行解析为 JSON StreamEvent；
//   - "data: {\"type\":\"end\"}" 是后端发送的结束标记（chat_handlers.go:196）；
//   - 通过回调 onEvent 推送，onError 上抛，返回 AbortController 供中断。
export interface StreamHandlers {
  onEvent: (ev: StreamEvent) => void
  onError?: (err: Error) => void
  onClose?: () => void
}

export function sendMessageStream(
  sessionId: string,
  content: string,
  handlers: StreamHandlers,
): AbortController {
  const controller = new AbortController()
  const url = `${API_BASE}/api/chat/sessions/${encodeURIComponent(sessionId)}/messages/stream`

  // async IIFE 便于 await，无需顶层 await
  void (async () => {
    let resp: Response
    try {
      resp = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json; charset=utf-8',
          Accept: 'text/event-stream',
        },
        body: JSON.stringify({ content }),
        signal: controller.signal,
      })
    } catch (err) {
      // AbortError 视为正常关闭
      if ((err as Error).name === 'AbortError') {
        handlers.onClose?.()
        return
      }
      handlers.onError?.(err as Error)
      return
    }
    if (!resp.ok) {
      const msg = await parseApiError(resp)
      handlers.onError?.(new ApiCallError(resp.status, msg, url))
      return
    }
    if (!resp.body) {
      handlers.onError?.(new Error('SSE 响应无 body'))
      return
    }

    // 逐 chunk 累积，按 \n\n 切分 SSE 事件块
    const reader = resp.body.getReader()
    const decoder = new TextDecoder('utf-8') // 显式 UTF-8
    let buffer = ''
    try {
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        // SSE 事件块以 \n\n 分隔
        let idx: number
        while ((idx = buffer.indexOf('\n\n')) >= 0) {
          const chunk = buffer.slice(0, idx)
          buffer = buffer.slice(idx + 2)
          handleSseChunk(chunk, handlers)
        }
      }
      // 处理尾部残留
      if (buffer.trim().length > 0) {
        handleSseChunk(buffer, handlers)
      }
      handlers.onClose?.()
    } catch (err) {
      if ((err as Error).name === 'AbortError') {
        handlers.onClose?.()
        return
      }
      handlers.onError?.(err as Error)
    }
  })()

  return controller
}

// handleSseChunk 解析单条 SSE 事件块（可能含多行 data）。
function handleSseChunk(chunk: string, handlers: StreamHandlers): void {
  // SSE 块由多行组成，只关心 data: 前缀行
  const dataLines: string[] = []
  for (const line of chunk.split('\n')) {
    const trimmed = line.trimStart()
    if (trimmed.startsWith('data:')) {
      dataLines.push(trimmed.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) return
  const payload = dataLines.join('\n')
  try {
    const ev = JSON.parse(payload) as StreamEvent
    handlers.onEvent(ev)
  } catch {
    // 忽略无法解析的事件（如注释行），避免单条错误中断整个流
  }
}

// --- 技能 ---
export function listSkills(): Promise<Skill[]> {
  return request<Skill[]>('GET', '/api/skills')
}

export interface UpsertSkillRequest {
  slug: string
  name: string
  description?: string
  content?: string
  enabled?: boolean
  level?: number
}

export function upsertSkill(req: UpsertSkillRequest): Promise<Skill> {
  return request<Skill>('POST', '/api/skills', req)
}

export function deleteSkill(slug: string): Promise<{ slug: string; deleted: boolean }> {
  return request('DELETE', `/api/skills/${encodeURIComponent(slug)}`)
}

export interface SkillStats {
  slug: string
  usage_count: number
  success_rate: number
  version: number
}

export function evolveSkill(slug: string): Promise<SkillStats> {
  return request<SkillStats>('POST', `/api/skills/${encodeURIComponent(slug)}/evolve`)
}

// --- 自进化 ---
export function evolveSession(sessionId: string): Promise<EvolveResult> {
  return request<EvolveResult>('POST', '/api/chat/evolve', { session_id: sessionId })
}

// --- 记忆 / 梦境 / 决策（M4，代理 Rust core）---
// 与后端 /api/memory/* 路由一一对应，类型镜像 memory 包。
// 这些端点由 Go 后端代理转发到 Rust core；core 未启动时返回 502。

// createMemory 创建记忆。Rust 侧异步生成 embedding，返回的 Memory 已含 id。
export function createMemory(req: CreateMemoryRequest): Promise<Memory> {
  return request<Memory>('POST', '/api/memory', req)
}

// getMemory 按 id 查询记忆。未找到时后端返回 404（抛 ApiCallError）。
export function getMemory(id: string): Promise<Memory> {
  return request<Memory>('GET', `/api/memory/${encodeURIComponent(id)}`)
}

// deleteMemory 删除记忆（含向量级联）。204 无响应体。
export function deleteMemory(id: string): Promise<void> {
  return request<void>('DELETE', `/api/memory/${encodeURIComponent(id)}`)
}

// searchMemory 关键字检索（content LIKE）。limit<=0 时后端用默认 20。
export function searchMemory(keyword: string, limit?: number): Promise<Memory[]> {
  const params = new URLSearchParams()
  params.set('keyword', keyword)
  if (limit && limit > 0) params.set('limit', String(limit))
  return request<Memory[]>('GET', `/api/memory/search?${params.toString()}`)
}

// searchVector 向量相似度检索。topK<=0 时后端用默认 5。
export function searchVector(query: string, topK?: number): Promise<SimilarMemory[]> {
  return request<SimilarMemory[]>('POST', '/api/memory/search-vector', {
    query,
    top_k: topK && topK > 0 ? topK : 0,
  })
}

// triggerDream 触发一次完整梦境（Light → REM → Deep）。
export function triggerDream(): Promise<DreamResult> {
  return request<DreamResult>('POST', '/api/memory/dream')
}

// listDreamDiary 列出最近的 Dream Diary。limit<=0 时后端用默认 20。
export function listDreamDiary(limit?: number): Promise<DreamDiaryEntry[]> {
  const params = new URLSearchParams()
  if (limit && limit > 0) params.set('limit', String(limit))
  const qs = params.toString()
  const path = qs ? `/api/memory/dream-diary?${qs}` : '/api/memory/dream-diary'
  return request<DreamDiaryEntry[]>('GET', path)
}

// getDreamDiary 按 id 查询单条 Dream Diary。
export function getDreamDiary(id: string): Promise<DreamDiaryEntry> {
  return request<DreamDiaryEntry>('GET', `/api/memory/dream-diary/${encodeURIComponent(id)}`)
}

// addDecision 记录一条决策到账本。
export function addDecision(req: CreateDecisionRequest): Promise<DecisionEntry> {
  return request<DecisionEntry>('POST', '/api/memory/decision', req)
}

// listDecisions 列出最近的决策。limit<=0 时后端用默认 20。
export function listDecisions(limit?: number): Promise<DecisionEntry[]> {
  const params = new URLSearchParams()
  if (limit && limit > 0) params.set('limit', String(limit))
  const qs = params.toString()
  const path = qs ? `/api/memory/decisions?${qs}` : '/api/memory/decisions'
  return request<DecisionEntry[]>('GET', path)
}
