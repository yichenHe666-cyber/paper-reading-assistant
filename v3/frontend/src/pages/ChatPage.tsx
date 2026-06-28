import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Plus, Send, Square, Wrench } from 'lucide-react'
import { ApiCallError, sendMessageStream, type StreamEvent } from '@/api'
import { useChatStore } from '@/stores/chat'
import { useUIStore } from '@/stores/ui'
import { Markdown } from '@/components/Markdown'
import { Loading, EmptyState, ErrorBox } from '@/components/Feedback'
import { BrandIcon } from '@/components/BrandIcon'
import { NeonBadge } from '@/components/NeonBadge'
import { NeonTextarea } from '@/components/NeonInput'

export default function ChatPage() {
  const { sessionId } = useParams<{ sessionId?: string }>()
  const navigate = useNavigate()
  const {
    sessions,
    sessionsLoading,
    currentSession,
    messages,
    messagesLoading,
    streamStatus,
    streamError,
    selectSession,
    createNewSession,
    appendMessage,
    appendAssistantChunk,
    finalizeStreamingMessage,
    setStreamStatus,
    loadSessions,
  } = useChatStore()
  const pushToast = useUIStore((s) => s.pushToast)

  useEffect(() => {
    void selectSession(sessionId ?? null).catch((err) => {
      pushToast('error', `会话加载失败：${err instanceof Error ? err.message : String(err)}`)
      navigate('/chat', { replace: true })
    })
  }, [sessionId, selectSession, pushToast, navigate])

  const handleNewSession = async () => {
    try {
      const id = await createNewSession()
      navigate(`/chat/${id}`)
      void loadSessions()
    } catch (err) {
      pushToast('error', `新建会话失败：${err instanceof Error ? err.message : String(err)}`)
    }
  }

  return (
    <section className="page-section !min-h-[80vh] !py-0">
      <div className="chat-layout grid min-h-[80vh] grid-cols-[260px_1fr] gap-lg">
        <aside className="chat-sidebar flex flex-col gap-sm py-lg">
          <div className="sidebar-header mb-sm flex items-center justify-between">
            <h3 className="font-rounded text-base font-bold">💬 对话列表</h3>
            <button
              type="button"
              onClick={handleNewSession}
              className="flex h-8 w-8 items-center justify-center rounded-full border-2 border-neon-cyan bg-neon-cyan/7 text-neon-cyan transition-colors hover:bg-neon-cyan/15 hover:shadow-glow-cyan"
              title="新建对话"
              aria-label="新建对话"
            >
              <Plus size={18} />
            </button>
          </div>
          {sessionsLoading ? (
            <Loading label="加载会话…" />
          ) : sessions.length === 0 ? (
            <EmptyState title="暂无会话" hint="点右上 + 新建" />
          ) : (
            <ul className="flex flex-col gap-0.5">
              {sessions.map((s) => (
                <li
                  key={s.id}
                  onClick={() => navigate(`/chat/${s.id}`)}
                  className={`session-item cursor-pointer rounded-md border border-transparent px-3.5 py-2.5 transition-colors ${
                    currentSession?.id === s.id
                      ? 'border-neon-cyan/25 bg-gradient-to-br from-neon-cyan/8 to-neon-purple/5 shadow-[0_0_16px_rgba(78,205,196,0.12)]'
                      : 'hover:border-neon-cyan/12 hover:bg-neon-cyan/5'
                  }`}
                >
                  <div className={`truncate text-sm ${currentSession?.id === s.id ? 'font-semibold text-neon-cyan' : 'font-medium'}`}>
                    {s.title || '新会话'}
                  </div>
                  <div className="font-mono text-[11px] text-text-muted">
                    {s.message_count} 条 · {s.total_tokens} token
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="chat-main my-lg flex flex-col overflow-hidden rounded-lg border border-black/6 bg-bg-secondary shadow-sm">
          {currentSession === null ? (
            <div className="flex flex-1 items-center justify-center p-8">
              <EmptyState title="选择左侧会话或新建" hint="开始与核动力牛马对话" />
            </div>
          ) : (
            <>
              <header className="chat-header flex items-center justify-between border-b border-black/6 bg-neon-cyan/[0.02] px-5 py-3.5">
                <div className="font-rounded text-[15px] font-bold">{currentSession.title || '新会话'}</div>
                <div className="flex items-center gap-2 text-xs text-text-muted">
                  <span className="status-dot h-2 w-2 rounded-full bg-neon-green shadow-[0_0_8px_rgba(57,255,20,0.5)] animate-neon-pulse-fast" />
                  <span>模型就绪</span>
                  <span className="ml-1 flex gap-0.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-neon-cyan animate-twinkle" />
                    <span className="h-1.5 w-1.5 rounded-full bg-neon-cyan animate-twinkle [animation-delay:0.2s]" />
                    <span className="h-1.5 w-1.5 rounded-full bg-neon-cyan animate-twinkle [animation-delay:0.4s]" />
                  </span>
                  <NeonBadge color="purple" className="ml-2">
                    {currentSession.total_tokens?.toLocaleString() ?? 0} tokens
                  </NeonBadge>
                </div>
              </header>

              <MessageList
                messages={messages}
                loading={messagesLoading}
                streamStatus={streamStatus}
                streamError={streamError}
              />
              <MessageInput
                sessionId={currentSession.id}
                disabled={streamStatus === 'streaming'}
                onSend={(content) =>
                  handleSend({
                    content,
                    sessionId: currentSession.id,
                    appendMessage,
                    appendAssistantChunk,
                    finalizeStreamingMessage,
                    setStreamStatus,
                    pushToast,
                  })
                }
              />
            </>
          )}
        </section>
      </div>
    </section>
  )
}

interface MessageListProps {
  messages: ReturnType<typeof useChatStore.getState>['messages']
  loading: boolean
  streamStatus: 'idle' | 'streaming' | 'done' | 'error'
  streamError: string
}

function MessageList({ messages, loading, streamStatus, streamError }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamStatus])

  if (loading) {
    return (
      <div className="flex-1 overflow-y-auto">
        <Loading label="加载消息…" />
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto px-6 py-6">
      {messages.length === 0 ? (
        <EmptyState title="开始一段新对话" hint="在下方输入你的问题" />
      ) : (
        <ul className="mx-auto flex max-w-3xl flex-col gap-6">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </ul>
      )}
      {streamError ? (
        <div className="mx-auto mt-4 max-w-3xl">
          <ErrorBox message={`流式出错：${streamError}`} />
        </div>
      ) : null}
      <div ref={endRef} />
    </div>
  )
}

interface MessageBubbleProps {
  message: ReturnType<typeof useChatStore.getState>['messages'][number]
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  let toolCalls: Array<{ id: string; name: string; arguments: string }> = []
  if (message.tool_calls) {
    try {
      const parsed = JSON.parse(message.tool_calls) as Array<{
        id: string
        type: string
        function: { name: string; arguments: string }
      }>
      toolCalls = parsed.map((tc) => ({
        id: tc.id,
        name: tc.function?.name ?? '',
        arguments: tc.function?.arguments ?? '',
      }))
    } catch {
      // ignore
    }
  }

  return (
    <li className={`chat-msg flex max-w-[85%] animate-[fadeInUp_0.3s_ease] ${isUser ? 'flex-row-reverse self-end' : 'self-start'}`}>
      {isUser ? (
        <BrandIcon img="/monocle-capitalist-icon.jpg" alt="user" />
      ) : (
        <BrandIcon size="avatar" />
      )}
      <div className="flex flex-col gap-1.5">
        <div
          className={`msg-bubble px-4.5 py-3.5 text-sm leading-relaxed ${
            isUser
              ? 'rounded-bubble border border-neon-cyan/18 bg-gradient-to-br from-neon-cyan/12 to-cyan-500/20 text-text-primary'
              : 'rounded-lg rounded-tl-sm border border-black/6 bg-bg-card shadow-sm'
          }`}
        >
          {message.reasoning_content ? (
            <details className="mb-2 text-xs opacity-80">
              <summary className="cursor-pointer">推理过程</summary>
              <pre className="mt-1 whitespace-pre-wrap">{message.reasoning_content}</pre>
            </details>
          ) : null}
          {isUser ? (
            <div className="whitespace-pre-wrap break-words">{message.content}</div>
          ) : (
            <Markdown content={message.content} />
          )}
          {toolCalls.length > 0 ? (
            <div className="mt-3 flex flex-wrap gap-2">
              {toolCalls.map((tc) => (
                <span
                  key={tc.id}
                  className="inline-flex items-center gap-1.5 rounded-pill border border-neon-magenta/20 bg-neon-magenta/8 px-3 py-1 text-xs text-neon-magenta animate-neon-pulse"
                >
                  <Wrench size={12} /> {tc.name}
                </span>
              ))}
            </div>
          ) : null}
        </div>
        <div className={`font-mono text-[11px] text-text-muted ${isUser ? 'text-right' : ''}`}>
          {new Date(message.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} · {message.token_count ?? 0} tokens
        </div>
      </div>
    </li>
  )
}

interface MessageInputProps {
  sessionId: string
  disabled: boolean
  onSend: (content: string) => AbortController
}

function MessageInput({ sessionId, disabled, onSend }: MessageInputProps) {
  const [text, setText] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    return () => {
      abortRef.current?.abort()
      abortRef.current = null
    }
  }, [sessionId])

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const content = text.trim()
    if (!content || disabled) return
    abortRef.current = onSend(content)
    setText('')
  }

  const handleStop = () => {
    abortRef.current?.abort()
    abortRef.current = null
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="chat-input-area flex items-end gap-sm border-t border-black/6 bg-neon-cyan/[0.02] px-6 py-4"
    >
      <NeonTextarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        rows={1}
        placeholder="输入消息…（Enter 发送，Shift+Enter 换行）"
        className="min-h-[44px] max-h-[120px] resize-none rounded-xl"
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            handleSubmit(e)
          }
        }}
      />
      {disabled ? (
        <button
          type="button"
          onClick={handleStop}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 border-neon-magenta bg-neon-magenta text-white transition-colors hover:bg-neon-magenta/90"
        >
          <Square size={16} />
        </button>
      ) : (
        <button
          type="submit"
          disabled={!text.trim()}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full border-2 border-neon-cyan bg-gradient-to-br from-neon-cyan to-cyan-600 text-white shadow-glow-cyan transition-transform hover:scale-105 disabled:opacity-50"
        >
          <Send size={18} />
        </button>
      )}
      <span className="sr-only">会话 {sessionId}</span>
    </form>
  )
}

interface SendArgs {
  content: string
  sessionId: string
  appendMessage: ReturnType<typeof useChatStore.getState>['appendMessage']
  appendAssistantChunk: ReturnType<typeof useChatStore.getState>['appendAssistantChunk']
  finalizeStreamingMessage: ReturnType<typeof useChatStore.getState>['finalizeStreamingMessage']
  setStreamStatus: ReturnType<typeof useChatStore.getState>['setStreamStatus']
  pushToast: ReturnType<typeof useUIStore.getState>['pushToast']
}

function handleSend(args: SendArgs): AbortController {
  const {
    content,
    sessionId,
    appendMessage,
    appendAssistantChunk,
    finalizeStreamingMessage,
    setStreamStatus,
    pushToast,
  } = args

  appendMessage({
    id: `local-user-${Date.now()}`,
    session_id: sessionId,
    role: 'user',
    content,
    reasoning_content: '',
    tool_calls: '',
    tool_call_id: '',
    token_count: 0,
    context_usage_pct: 0,
    created_at: new Date().toISOString(),
  })

  setStreamStatus('streaming')

  return sendMessageStream(sessionId, content, {
    onEvent: (ev: StreamEvent) => {
      switch (ev.type) {
        case 'token':
          if (ev.content) {
            appendAssistantChunk(sessionId, ev.content)
          }
          break
        case 'tool_call':
          appendAssistantChunk(sessionId, `\n\n> 调用工具 \`${ev.tool_name}\`…\n`)
          break
        case 'tool_result':
          break
        case 'usage':
        case 'done':
          break
        case 'error':
          setStreamStatus('error', ev.content ?? '未知错误')
          pushToast('error', `生成失败：${ev.content ?? ''}`)
          break
        case 'end':
          break
      }
    },
    onError: (err) => {
      const msg = err instanceof ApiCallError ? err.message : err.message
      setStreamStatus('error', msg)
      pushToast('error', `连接失败：${msg}`)
    },
    onClose: () => {
      void (async () => {
        await finalizeStreamingMessage(sessionId, '', 0)
        setStreamStatus('done')
      })()
    },
  })
}
