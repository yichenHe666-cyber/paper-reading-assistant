// 对话页：会话列表 + 消息流 + 输入框 + SSE 流式。
//
// 痛点③修复要点（spec §4.3）：
//   - URL 是真相源：/chat/:sessionId 刷新可恢复，不依赖 session_state；
//   - assistant 消息用 Markdown 渲染（含 GFM 表格/任务列表），user 消息纯文本；
//   - SSE 流式逐 token 展示，错误也走结构化 toast 而非 text[:200]；
//   - 流式中可中断（AbortController）。
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Plus, Send, Square, Wrench } from 'lucide-react'
import { ApiCallError, sendMessageStream, type StreamEvent } from '@/api'
import { useChatStore } from '@/stores/chat'
import { useUIStore } from '@/stores/ui'
import { Markdown } from '@/components/Markdown'
import { Loading, EmptyState, ErrorBox } from '@/components/Feedback'

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

  // URL sessionId 变化 → 切换会话
  useEffect(() => {
    void selectSession(sessionId ?? null).catch((err) => {
      pushToast('error', `会话加载失败：${err instanceof Error ? err.message : String(err)}`)
      // 失效会话 id 回退到 /chat
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
    <div className="flex h-full">
      {/* 会话列表 */}
      <section className="hidden w-64 shrink-0 flex-col border-r border-brand-100 bg-white md:flex">
        <div className="flex items-center justify-between border-b border-brand-100 px-3 py-2">
          <span className="text-xs font-semibold uppercase text-brand-700">会话</span>
          <button
            type="button"
            onClick={handleNewSession}
            className="rounded p-1 hover:bg-brand-100"
            aria-label="新建会话"
            title="新建会话"
          >
            <Plus size={16} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {sessionsLoading ? (
            <Loading label="加载会话…" />
          ) : sessions.length === 0 ? (
            <EmptyState title="暂无会话" hint="点右上 + 新建" />
          ) : (
            <ul className="py-1">
              {sessions.map((s) => (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/chat/${s.id}`)}
                    className={`w-full truncate px-3 py-2 text-left text-sm transition-colors ${
                      currentSession?.id === s.id
                        ? 'bg-brand-100 text-brand-900'
                        : 'hover:bg-brand-50'
                    }`}
                  >
                    <div className="truncate">{s.title || '新会话'}</div>
                    <div className="text-xs text-brand-700/70">
                      {s.message_count} 条 · {s.total_tokens} token
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* 消息区 */}
      <section className="flex flex-1 flex-col overflow-hidden">
        {currentSession === null ? (
          <div className="flex flex-1 items-center justify-center p-8">
            <EmptyState title="选择左侧会话或新建" hint="开始与核动力牛马对话" />
          </div>
        ) : (
          <>
            <header className="flex items-center justify-between border-b border-brand-100 bg-white px-4 py-2">
              <h2 className="truncate text-sm font-medium">
                {currentSession.title || '新会话'}
              </h2>
              <span className="text-xs text-brand-700">
                模式：{currentSession.skill_mode}
              </span>
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
  )
}

// --- 消息列表 ---

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
    <div className="flex-1 overflow-y-auto px-4 py-4">
      {messages.length === 0 ? (
        <EmptyState title="开始一段新对话" hint="在下方输入你的问题" />
      ) : (
        <ul className="mx-auto flex max-w-3xl flex-col gap-3">
          {messages.map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        </ul>
      )}
      {streamError ? (
        <div className="mx-auto mt-3 max-w-3xl">
          <ErrorBox message={`流式出错：${streamError}`} />
        </div>
      ) : null}
      <div ref={endRef} />
    </div>
  )
}

// --- 单条消息 ---

interface MessageBubbleProps {
  message: ReturnType<typeof useChatStore.getState>['messages'][number]
}

function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  const isAssistant = message.role === 'assistant'
  // 解析 tool_calls（assistant 可能携带工具调用）
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
      // 解析失败忽略，主内容仍可展示
    }
  }

  return (
    <li className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[85%] rounded-lg px-3 py-2 ${
          isUser
            ? 'bg-brand-500 text-white'
            : isAssistant
              ? 'bg-white text-brand-900 ring-1 ring-brand-100'
              : 'bg-brand-100 text-brand-700'
        }`}
      >
        {message.reasoning_content ? (
          <details className="mb-2 text-xs opacity-80">
            <summary className="cursor-pointer">推理过程</summary>
            <pre className="mt-1 whitespace-pre-wrap">{message.reasoning_content}</pre>
          </details>
        ) : null}
        {isUser ? (
          // user 消息纯文本，保留换行
          <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
            {message.content}
          </div>
        ) : (
          // assistant 消息渲染 Markdown
          <Markdown content={message.content} />
        )}
        {toolCalls.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1">
            {toolCalls.map((tc) => (
              <span
                key={tc.id}
                className="inline-flex items-center gap-1 rounded bg-brand-100 px-1.5 py-0.5 text-xs text-brand-700"
              >
                <Wrench size={10} /> {tc.name}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </li>
  )
}

// --- 输入框 ---

interface MessageInputProps {
  sessionId: string
  disabled: boolean
  onSend: (content: string) => AbortController
}

function MessageInput({ sessionId, disabled, onSend }: MessageInputProps) {
  const [text, setText] = useState('')
  const abortRef = useRef<AbortController | null>(null)

  // 组件卸载或切换会话时中断在途 SSE，避免：
  //   1. 后端 agent loop + LLM 调用继续空跑烧 token（资源泄漏）；
  //   2. 已卸载组件 setState 触发 React 警告/错乱。
  // 依赖 sessionId：切换会话即视为旧流不再需要。
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
    // 接住流式 controller，供"停止"按钮或卸载清理中断
    abortRef.current = onSend(content)
    setText('')
  }

  const handleStop = () => {
    abortRef.current?.abort()
    abortRef.current = null
  }

  // 流式中禁止输入
  return (
    <form
      onSubmit={handleSubmit}
      className="flex items-end gap-2 border-t border-brand-100 bg-white px-4 py-3"
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        rows={2}
        placeholder="输入消息…（Enter 发送，Shift+Enter 换行）"
        className="flex-1 resize-none rounded-lg border border-brand-100 bg-white px-3 py-2 text-sm outline-none focus:border-brand-500 disabled:opacity-50"
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
          className="flex h-9 items-center gap-1 rounded-lg bg-red-500 px-3 text-sm text-white hover:bg-red-600"
        >
          <Square size={14} /> 停止
        </button>
      ) : (
        <button
          type="submit"
          disabled={!text.trim()}
          className="flex h-9 items-center gap-1 rounded-lg bg-brand-500 px-3 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
        >
          <Send size={14} /> 发送
        </button>
      )}
      {/* sessionId 仅用于触发流式接口，此处显式引用避免 lint unused */}
      <span className="sr-only">会话 {sessionId}</span>
    </form>
  )
}

// --- 流式发送逻辑（独立函数便于测试与维护） ---

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

  // 1. 立即把 user 消息塞进 UI（乐观更新）
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

  // 2. 启动 SSE 流，返回 controller 供调用方中断
  return sendMessageStream(sessionId, content, {
    onEvent: (ev: StreamEvent) => {
      switch (ev.type) {
        case 'token':
          if (ev.content) {
            appendAssistantChunk(sessionId, ev.content)
          }
          break
        case 'tool_call':
          // 工具调用事件：UI 上 appendAssistantChunk 已建占位，这里追加提示
          appendAssistantChunk(sessionId, `\n\n> 调用工具 \`${ev.tool_name}\`…\n`)
          break
        case 'tool_result':
          // 工具结果可选展示，简洁起见略
          break
        case 'usage':
        case 'done':
          // done 不直接结束 streamStatus：等 onClose
          break
        case 'error':
          setStreamStatus('error', ev.content ?? '未知错误')
          pushToast('error', `生成失败：${ev.content ?? ''}`)
          break
        case 'end':
          // 后端结束标记
          break
      }
    },
    onError: (err) => {
      const msg = err instanceof ApiCallError ? err.message : err.message
      setStreamStatus('error', msg)
      pushToast('error', `连接失败：${msg}`)
    },
    onClose: () => {
      // 流结束：从后端拉真实消息（含 token_count、tool_calls 落库版）
      void finalizeStreamingMessage(sessionId, '', 0).then(() => {
        setStreamStatus('done')
      })
    },
  })
}
