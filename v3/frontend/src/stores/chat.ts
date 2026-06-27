// 会话与消息状态：集中管理当前会话列表、消息列表、流式状态。
//
// 痛点③修复要点（spec §4.3）：
//   - 用 Zustand 集中管理导航与会话状态，取代散落的 session_state；
//   - URL 路由（react-router）是"刷新可恢复"的真相源，store 只是缓存；
//   - 流式状态机：idle → streaming → done/error，UI 据此切换渲染。
import { create } from 'zustand'
import type { Message, Session } from '@/api'
import {
  createSession as apiCreateSession,
  listSessions as apiListSessions,
  listMessages as apiListMessages,
  getSession as apiGetSession,
} from '@/api'

export type StreamStatus = 'idle' | 'streaming' | 'done' | 'error'

interface ChatState {
  sessions: Session[]
  sessionsLoading: boolean
  currentSession: Session | null
  messages: Message[]
  messagesLoading: boolean
  streamStatus: StreamStatus
  streamError: string | ''

  loadSessions: () => Promise<void>
  selectSession: (id: string | null) => Promise<void>
  refreshMessages: (sessionId: string) => Promise<void>
  createNewSession: (title?: string) => Promise<string>
  appendMessage: (m: Message) => void
  appendAssistantChunk: (sessionId: string, chunk: string) => void
  finalizeStreamingMessage: (sessionId: string, fullContent: string, tokenCount: number) => void
  setStreamStatus: (s: StreamStatus, errMsg?: string) => void
  reset: () => void
}

// 局部缓存"流式中"的 assistant 消息 id，便于 chunk 追加
let streamingMsgId: string | null = null
let msgSeq = 0
function nextMsgId(): string {
  return `local-${Date.now()}-${++msgSeq}`
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessions: [],
  sessionsLoading: false,
  currentSession: null,
  messages: [],
  messagesLoading: false,
  streamStatus: 'idle',
  streamError: '',

  loadSessions: async () => {
    set({ sessionsLoading: true })
    try {
      const list = await apiListSessions()
      set({ sessions: list, sessionsLoading: false })
    } catch (err) {
      set({ sessionsLoading: false })
      throw err
    }
  },

  selectSession: async (id) => {
    if (id === null) {
      set({ currentSession: null, messages: [] })
      return
    }
    set({ messagesLoading: true })
    try {
      const [sess, msgs] = await Promise.all([apiGetSession(id), apiListMessages(id)])
      set({ currentSession: sess, messages: msgs, messagesLoading: false })
    } catch (err) {
      set({ messagesLoading: false, currentSession: null, messages: [] })
      throw err
    }
  },

  refreshMessages: async (sessionId) => {
    const msgs = await apiListMessages(sessionId)
    set({ messages: msgs })
  },

  createNewSession: async (title) => {
    const { id } = await apiCreateSession({ title })
    // 立即把新会话塞进列表，无需重新拉全表
    const sess = await apiGetSession(id)
    set((s) => ({ sessions: [sess, ...s.sessions], currentSession: sess, messages: [] }))
    return id
  },

  appendMessage: (m) => set((s) => ({ messages: [...s.messages, m] })),

  // 流式开始时插入空 assistant 占位，后续 chunk 追加到该消息
  appendAssistantChunk: (sessionId, chunk) => {
    set((s) => {
      const msgs = [...s.messages]
      // 找当前会话最后一条 local 流式 assistant 消息
      const lastIdx = msgs.length - 1
      if (lastIdx >= 0 && msgs[lastIdx].id === streamingMsgId && msgs[lastIdx].role === 'assistant') {
        const updated = { ...msgs[lastIdx], content: msgs[lastIdx].content + chunk }
        msgs[lastIdx] = updated
      } else {
        // 新建占位 assistant 消息
        streamingMsgId = nextMsgId()
        msgs.push({
          id: streamingMsgId,
          session_id: sessionId,
          role: 'assistant',
          content: chunk,
          reasoning_content: '',
          tool_calls: '',
          tool_call_id: '',
          token_count: 0,
          context_usage_pct: 0,
          created_at: new Date().toISOString(),
        })
      }
      return { messages: msgs }
    })
  },

  // 流结束：刷新该会话消息（确保用后端真实数据，含 token_count）
  finalizeStreamingMessage: async (sessionId, _fullContent, _tokenCount) => {
    streamingMsgId = null
    await get().refreshMessages(sessionId)
  },

  setStreamStatus: (s, errMsg = '') => set({ streamStatus: s, streamError: errMsg }),

  reset: () => set({ sessions: [], currentSession: null, messages: [], streamStatus: 'idle' }),
}))
