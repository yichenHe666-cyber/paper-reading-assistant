// 显式 UTF-8 API 客户端。
//
// 痛点③修复要点（spec §4.3）：
//   - 请求头显式 Content-Type: application/json; charset=utf-8，避免浏览器探测；
//   - 响应一律 .json()，错误信息走结构化 JSON {error:string} 而非 text[:200]；
//   - 非 2xx 状态抛 ApiCallError，携带 status 与 server-side message；
//   - SSE 流式通过 fetch + ReadableStream 解析，不依赖 EventSource（后者不支持 POST）。

import type {
  ApiError,
  HealthInfo,
  Message,
  MigrateLegacyResponse,
  Paper,
  Session,
  Skill,
  StreamEvent,
  SyncResult,
  Topic,
  SendMessageResponse,
  EvolveResult,
  ReadStatus,
  SkillMode,
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

// --- 主题与论文 ---
export function listTopics(): Promise<Topic[]> {
  return request<Topic[]>('GET', '/api/topics')
}

export function listPapers(topicId: string): Promise<Paper[]> {
  return request<Paper[]>(`GET`, `/api/topics/${encodeURIComponent(topicId)}/papers`)
}

export function getPaper(id: string): Promise<Paper> {
  return request<Paper>('GET', `/api/papers/${encodeURIComponent(id)}`)
}

export function updatePaperStatus(id: string, status: ReadStatus): Promise<{ id: string; status: ReadStatus }> {
  return request('PATCH', `/api/papers/${encodeURIComponent(id)}/status`, { status })
}

// --- 同步与迁移 ---
export function syncPapers(owner?: string, repo?: string): Promise<SyncResult> {
  const body = owner || repo ? { owner, repo } : undefined
  return request<SyncResult>('POST', '/api/sync', body)
}

export function migrateLegacy(): Promise<MigrateLegacyResponse> {
  return request<MigrateLegacyResponse>('POST', '/api/migrate-legacy')
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
