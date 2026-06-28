// 论文阅读器状态：论文详情、阅读会话计时、AI 对话侧栏。
//
// 职责：
//   - loadPaper 并行拉论文详情 + 相关论文；
//   - startSession 调 startReading 创建阅读历史 + createSession 创建对话会话；
//   - endSession 提交阅读时长（幂等，React strict mode 二次调用安全）；
//   - sendMessage 复用现有 chat SSE 流式接口，在侧栏内渲染对话。
//
// 错误策略：loadPaper/startSession/endSession 抛给页面层 catch 后 pushToast；
// sendMessage 流式内部错误直接 pushToast（流式无返回值，不便上抛）。
import { create } from 'zustand'
import type { Message, Paper, PaperDetail, StreamEvent } from '@/api'
import {
  createSession as apiCreateSession,
  endReading as apiEndReading,
  getPaper as apiGetPaper,
  getRelatedPapers as apiGetRelatedPapers,
  listMessages as apiListMessages,
  sendMessageStream as apiSendMessageStream,
  startReading as apiStartReading,
} from '@/api'
import { useUIStore } from '@/stores/ui'

interface ReaderState {
  paper: PaperDetail | null
  loading: boolean // 论文详情加载中
  error: string | null
  related: Paper[] // 相关论文
  historyId: string | null // 当前阅读会话 id（来自 startReading 返回）
  startedAt: number | null // Date.now() 进入时间戳，用于实时计时

  // AI 对话栏
  sessionId: string | null
  messages: Message[]
  sending: boolean
  streamingContent: string // 流式累积的当前回复
  streamingReasoning: string
  abortController: AbortController | null

  loadPaper: (id: string) => Promise<void>
  startSession: (id: string) => Promise<void> // 调 startReading + createSession
  endSession: () => Promise<void> // 调 endReading（用 historyId）
  sendMessage: (content: string) => void // SSE 流式发送
  abortSend: () => void
  reset: () => void
}

// 本地临时消息 id 序号，避免与后端真实 id 冲突
let msgSeq = 0
function nextLocalId(): string {
  return `reader-local-${Date.now()}-${++msgSeq}`
}

export const useReaderStore = create<ReaderState>((set, get) => {
  // finalizeStreaming 把当前 streamingContent 固化到末尾 assistant 消息，
  // 清空流式状态并置 sending=false。幂等：done/end + onClose 都可能触发，
  // 多次调用安全。
  function finalizeStreaming(): void {
    const { streamingContent, messages } = get()
    const msgs = [...messages]
    const lastIdx = msgs.length - 1
    if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
      const finalContent = streamingContent || msgs[lastIdx].content
      if (!finalContent) {
        // 占位 assistant 仍空：移除避免空消息
        msgs.pop()
      } else {
        msgs[lastIdx] = { ...msgs[lastIdx], content: finalContent }
      }
    }
    set({
      messages: msgs,
      streamingContent: '',
      streamingReasoning: '',
      sending: false,
      abortController: null,
    })
  }

  return {
    paper: null,
    loading: false,
    error: null,
    related: [],
    historyId: null,
    startedAt: null,
    sessionId: null,
    messages: [],
    sending: false,
    streamingContent: '',
    streamingReasoning: '',
    abortController: null,

    loadPaper: async (id) => {
      set({ loading: true, error: null })
      try {
        const [paper, related] = await Promise.all([
          apiGetPaper(id),
          apiGetRelatedPapers(id),
        ])
        set({ paper, related, loading: false })
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        set({ loading: false, error: msg })
        throw err
      }
    },

    startSession: async (id) => {
      // 1. startReading 创建阅读历史记录（后端同时把论文状态置为 reading）
      const { history_id: historyId } = await apiStartReading(id)
      set({ historyId, startedAt: Date.now() })
      // 2. createSession 创建对话会话（标题用论文标题）
      const title = get().paper?.title
      const { id: sessionId } = await apiCreateSession(title ? { title } : {})
      set({ sessionId })
      // 3. 加载历史消息（若有，失败不阻塞对话）
      try {
        const msgs = await apiListMessages(sessionId)
        set({ messages: msgs })
      } catch {
        /* 历史消息加载失败静默 */
      }
    },

    endSession: async () => {
      const { paper, historyId, abortController } = get()
      // 幂等：无 historyId 直接清空本地状态返回（strict mode 二次调用安全）
      if (!historyId || !paper) {
        set({
          historyId: null,
          startedAt: null,
          sessionId: null,
          messages: [],
          streamingContent: '',
          streamingReasoning: '',
          sending: false,
          abortController: null,
        })
        return
      }
      // 中断在途流式，避免后端 agent loop 空跑烧 token
      abortController?.abort()
      try {
        await apiEndReading(paper.id, historyId)
      } catch {
        /* 提交失败静默，不阻塞退出 */
      }
      set({
        historyId: null,
        startedAt: null,
        sessionId: null,
        messages: [],
        streamingContent: '',
        streamingReasoning: '',
        sending: false,
        abortController: null,
      })
    },

    sendMessage: (content) => {
      const { sessionId, sending } = get()
      if (!sessionId || sending) return
      const trimmed = content.trim()
      if (!trimmed) return

      // 乐观更新：先塞 user 消息 + 空 assistant 占位
      const userMsg: Message = {
        id: nextLocalId(),
        session_id: sessionId,
        role: 'user',
        content: trimmed,
        reasoning_content: '',
        tool_calls: '',
        tool_call_id: '',
        token_count: 0,
        context_usage_pct: 0,
        created_at: new Date().toISOString(),
      }
      const assistantMsg: Message = {
        id: nextLocalId(),
        session_id: sessionId,
        role: 'assistant',
        content: '',
        reasoning_content: '',
        tool_calls: '',
        tool_call_id: '',
        token_count: 0,
        context_usage_pct: 0,
        created_at: new Date().toISOString(),
      }
      set((s) => ({
        messages: [...s.messages, userMsg, assistantMsg],
        sending: true,
        streamingContent: '',
        streamingReasoning: '',
      }))

      const pushToast = useUIStore.getState().pushToast

      const controller = apiSendMessageStream(sessionId, trimmed, {
        onEvent: (ev: StreamEvent) => {
          switch (ev.type) {
            case 'token': {
              const chunk = ev.content
              if (!chunk) break
              set((s) => {
                const streamingContent = s.streamingContent + chunk
                const msgs = [...s.messages]
                const lastIdx = msgs.length - 1
                if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
                  msgs[lastIdx] = { ...msgs[lastIdx], content: streamingContent }
                }
                return { streamingContent, messages: msgs }
              })
              break
            }
            case 'tool_call':
            case 'tool_result':
              // 工具调用/结果暂不在阅读器侧栏展示
              break
            case 'usage':
              // token 用量暂不展示
              break
            case 'error':
              pushToast('error', `生成失败：${ev.content ?? '未知错误'}`)
              finalizeStreaming()
              break
            case 'done':
            case 'end':
              finalizeStreaming()
              break
          }
        },
        onError: (err) => {
          const msg = err instanceof Error ? err.message : String(err)
          pushToast('error', `连接失败：${msg}`)
          finalizeStreaming()
        },
        onClose: () => {
          // 兜底：流关闭时确保固化为最终消息（与 done/end 幂等）
          finalizeStreaming()
        },
      })

      set({ abortController: controller })
    },

    abortSend: () => {
      const { abortController } = get()
      abortController?.abort()
      finalizeStreaming()
    },

    reset: () => {
      const { abortController } = get()
      abortController?.abort()
      set({
        paper: null,
        loading: false,
        error: null,
        related: [],
        historyId: null,
        startedAt: null,
        sessionId: null,
        messages: [],
        sending: false,
        streamingContent: '',
        streamingReasoning: '',
        abortController: null,
      })
    },
  }
})
