// 论文阅读器：左 PDF + 右 AI 对话栏 + 阅读计时 + 阅读历史。
//
// 布局参考 VS Code 插件侧栏风格 + Office 标准工具栏：
//   - 顶部工具栏：返回 / 标题·作者·年份 / 阅读状态 / 结束阅读
//   - 左侧 PDF 渲染（iframe 嵌入浏览器原生预览，不走 fetch+blob）
//   - 右侧 AI 助手侧栏（w-96）：阅读计时 + 消息流 + 输入框
//   - 底部状态栏：上次阅读 / 累计时长 / 难度圆点
//
// 阅读计时长效：进入页面 startReading 创建历史，退出（卸载/按钮）endReading 提交。
// 卸载时 useEffect cleanup 调 endSession 是防止"重启丢数据"的关键，必须保证触发。
import { useEffect, useRef, useState } from 'react'
import type React from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  BookOpen,
  Clock,
  ExternalLink,
  SendHorizontal,
  Sparkles,
  Square,
} from 'lucide-react'
import {
  ApiCallError,
  paperPDFURL,
  updatePaperStatus,
  type Message,
  type ReadStatus,
} from '@/api'
import { useReaderStore } from '@/stores/reader'
import { useUIStore } from '@/stores/ui'
import { Markdown } from '@/components/Markdown'
import { EmptyState, ErrorBox, Loading } from '@/components/Feedback'

const STATUS_LABELS: Record<ReadStatus, string> = {
  unread: '未读',
  reading: '在读',
  done: '已读',
  reread: '重读',
}

const STATUS_ORDER: ReadStatus[] = ['unread', 'reading', 'done', 'reread']

// formatClock 把秒数格式化为 HH:MM:SS。
function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  const hh = Math.floor(s / 3600)
  const mm = Math.floor((s % 3600) / 60)
  const ss = s % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(hh)}:${pad(mm)}:${pad(ss)}`
}

// formatRelativeTime 把 ISO 时间字符串格式化为相对时间（同 LibraryPage）。
function formatRelativeTime(iso: string): string {
  if (!iso) return '—'
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return '—'
  const diff = Date.now() - then
  if (diff < 0) return '刚刚'
  const sec = Math.floor(diff / 1000)
  if (sec < 60) return '刚刚'
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} 分钟前`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} 小时前`
  const day = Math.floor(hr / 24)
  if (day < 7) return `${day} 天前`
  const week = Math.floor(day / 7)
  return `${week} 周前`
}

// formatDuration 把秒数格式化为 "N 分钟" / "N 小时 X 分钟"（同 LibraryPage）。
function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '—'
  const min = Math.floor(seconds / 60)
  if (min < 60) return `${min} 分钟`
  const hr = Math.floor(min / 60)
  const remMin = min % 60
  return remMin > 0 ? `${hr} 小时 ${remMin} 分钟` : `${hr} 小时`
}

// difficultyDots 渲染 10 个圆点，前 score 个填充，rest 空心。
function difficultyDots(score: number) {
  const n = Math.max(0, Math.min(10, Math.floor(score) || 0))
  return (
    <span className="inline-flex items-center gap-0.5" title={`难度 ${n}/10`}>
      {Array.from({ length: 10 }, (_, i) => (
        <span
          key={i}
          className={`h-1.5 w-1.5 rounded-full ${i < n ? 'bg-brand-500' : 'bg-brand-100'}`}
        />
      ))}
    </span>
  )
}

export default function PaperReader() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const pushToast = useUIStore((s) => s.pushToast)

  const {
    paper,
    loading,
    error,
    startedAt,
    sessionId,
    messages,
    sending,
    loadPaper,
    startSession,
    endSession,
    sendMessage,
    abortSend,
    reset,
  } = useReaderStore()

  const [now, setNow] = useState(Date.now())

  // 进入页面：加载论文 + 启动阅读会话
  useEffect(() => {
    if (!id) return
    void (async () => {
      try {
        await loadPaper(id)
        // startSession 失败仅 toast，不阻塞 PDF 显示
        await startSession(id).catch((err) => {
          const msg = err instanceof Error ? err.message : String(err)
          pushToast('error', `启动阅读会话失败：${msg}`)
        })
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        pushToast('error', `加载论文失败：${msg}`)
      }
    })()

    // 卸载时提交阅读时长并清空 store（防止丢数据）
    return () => {
      void endSession()
      reset()
    }
    // 仅依赖 id：store action 引用稳定，避免重复触发
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id])

  // 实时计时：每秒刷新
  useEffect(() => {
    if (!startedAt) return
    const timer = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(timer)
  }, [startedAt])

  const elapsedSeconds = startedAt ? Math.max(0, Math.floor((now - startedAt) / 1000)) : 0

  const handleBack = async () => {
    await endSession()
    reset()
    navigate(-1)
  }

  const handleEndReading = async () => {
    await endSession()
    reset()
    navigate('/library')
  }

  const handleStatusChange = async (status: ReadStatus) => {
    if (!paper) return
    try {
      await updatePaperStatus(paper.id, status)
      useReaderStore.setState((s) => ({
        paper: s.paper ? { ...s.paper, read_status: status } : null,
      }))
      pushToast('success', `已标记为${STATUS_LABELS[status]}`)
    } catch (err) {
      const msg = err instanceof ApiCallError ? err.message : String(err)
      pushToast('error', `状态更新失败：${msg}`)
    }
  }

  if (!id) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <ErrorBox message="缺少论文 ID" />
      </div>
    )
  }

  return (
    <div className="flex h-full flex-col">
      {/* 顶部 Office 风格工具栏 */}
      <header className="flex shrink-0 items-center gap-3 border-b border-brand-100 bg-white px-4 py-2">
        <button
          type="button"
          onClick={handleBack}
          className="flex items-center gap-1 rounded px-2 py-1 text-sm text-brand-700 hover:bg-brand-100"
          title="返回"
        >
          <ArrowLeft size={16} /> 返回
        </button>
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <BookOpen size={14} className="shrink-0 text-brand-700" />
          <span className="truncate text-sm font-medium text-brand-900">
            {paper?.title ?? '加载中…'}
          </span>
          {paper ? (
            <span className="hidden shrink-0 text-xs text-brand-700 sm:inline">
              {paper.authors || '未知作者'}
              {paper.year ? ` · ${paper.year}` : ''}
            </span>
          ) : null}
        </div>
        {paper ? (
          <div className="flex shrink-0 items-center gap-2">
            <select
              value={paper.read_status}
              onChange={(e) => void handleStatusChange(e.target.value as ReadStatus)}
              className="rounded border border-brand-100 bg-white px-2 py-1 text-xs outline-none focus:border-brand-500"
              title="阅读状态"
            >
              {STATUS_ORDER.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={handleEndReading}
              className="flex items-center gap-1 rounded bg-brand-500 px-3 py-1 text-xs text-white hover:bg-brand-600"
            >
              结束阅读
            </button>
          </div>
        ) : null}
      </header>

      {/* 主区域 */}
      {error && !paper ? (
        <div className="flex flex-1 items-center justify-center p-8">
          <ErrorBox message={error} />
        </div>
      ) : loading && !paper ? (
        <div className="flex flex-1 items-center justify-center">
          <Loading label="加载论文…" />
        </div>
      ) : paper ? (
        <div className="flex flex-1 overflow-hidden">
          {/* 左：PDF 渲染（iframe 嵌入浏览器原生预览） */}
          <div className="relative flex-1 bg-gray-100">
            <iframe
              src={paperPDFURL(paper.id)}
              title={paper.title}
              className="h-full w-full border-0"
            />
            {/* PDF 加载失败兜底：iframe onError 不可靠，常驻一个新窗口链接 */}
            <a
              href={paper.pdf_url}
              target="_blank"
              rel="noreferrer"
              className="absolute bottom-2 right-2 flex items-center gap-1 rounded bg-white/90 px-2 py-1 text-xs text-brand-700 shadow-sm hover:bg-white"
            >
              <ExternalLink size={12} /> PDF 无法加载？新窗口打开
            </a>
          </div>

          {/* 右：AI 助手侧栏（VS Code 插件风格） */}
          <aside className="flex w-96 shrink-0 flex-col border-l border-brand-100 bg-white">
            {/* 顶部统计区 */}
            <div className="shrink-0 border-b border-brand-100 px-4 py-3">
              <div className="flex items-center gap-1.5 text-sm font-medium text-brand-900">
                <Sparkles size={14} /> AI 助手
              </div>
              <div className="mt-2 flex items-center gap-1.5 text-sm">
                <Clock size={14} className="text-brand-700" />
                <span className="font-medium tabular-nums text-brand-900">
                  {formatClock(elapsedSeconds)}
                </span>
                <span className="text-xs text-brand-700">本次阅读</span>
              </div>
              <div className="mt-0.5 text-xs text-brand-700">
                累计 {paper.reading_stats?.count ?? 0} 次 ·{' '}
                {formatDuration(paper.reading_stats?.total_seconds ?? 0)}
              </div>
            </div>

            {/* 消息列表 */}
            <MessageList messages={messages} sending={sending} hasSession={!!sessionId} />

            {/* 输入区 */}
            <ChatInput
              sending={sending}
              disabled={!sessionId}
              onSend={sendMessage}
              onAbort={abortSend}
            />
          </aside>
        </div>
      ) : null}

      {/* 底部状态栏 */}
      {paper ? (
        <footer className="flex shrink-0 items-center justify-between gap-4 border-t border-brand-100 bg-white px-4 py-1.5 text-xs text-brand-700">
          <span>
            上次阅读：{formatRelativeTime(paper.reading_stats?.last_read_at ?? paper.last_read_at)}
          </span>
          <span>
            累计：{formatDuration(paper.reading_stats?.total_seconds ?? paper.total_read_seconds)}
          </span>
          <span className="flex items-center gap-1.5">难度 {difficultyDots(paper.difficulty_score)}</span>
        </footer>
      ) : null}
    </div>
  )
}

// --- 消息列表 ---

interface MessageListProps {
  messages: Message[]
  sending: boolean
  hasSession: boolean
}

function MessageList({ messages, sending, hasSession }: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null)
  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  return (
    <div className="flex-1 overflow-y-auto px-3 py-3">
      {!hasSession ? (
        <EmptyState title="正在准备对话…" hint="阅读会话启动后即可提问" />
      ) : messages.length === 0 ? (
        <EmptyState title="向 AI 提问论文内容" hint="例如：这篇论文的核心贡献是什么？" />
      ) : (
        <ul className="flex flex-col gap-3">
          {messages.map((m, i) => (
            <MessageBubble
              key={m.id}
              message={m}
              isStreaming={sending && i === messages.length - 1 && m.role === 'assistant'}
            />
          ))}
        </ul>
      )}
      <div ref={endRef} />
    </div>
  )
}

// --- 单条消息 ---

interface MessageBubbleProps {
  message: Message
  isStreaming: boolean
}

function MessageBubble({ message, isStreaming }: MessageBubbleProps) {
  const isUser = message.role === 'user'
  return (
    <li className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
      <div
        className={`max-w-[90%] rounded-lg px-3 py-2 ${
          isUser
            ? 'bg-brand-500 text-white'
            : 'bg-brand-50 text-brand-900 ring-1 ring-brand-100'
        }`}
      >
        {isUser ? (
          <div className="whitespace-pre-wrap break-words text-sm leading-relaxed">
            {message.content}
          </div>
        ) : message.content ? (
          <Markdown content={message.content} />
        ) : isStreaming ? (
          <span className="inline-flex items-center gap-1 text-xs text-brand-700">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
            思考中…
          </span>
        ) : null}
      </div>
    </li>
  )
}

// --- 输入框 ---

interface ChatInputProps {
  sending: boolean
  disabled: boolean
  onSend: (content: string) => void
  onAbort: () => void
}

function ChatInput({ sending, disabled, onSend, onAbort }: ChatInputProps) {
  const [text, setText] = useState('')

  const submit = () => {
    const content = text.trim()
    if (!content || sending || disabled) return
    onSend(content)
    setText('')
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter（无 Shift）/ Ctrl+Enter 发送，Shift+Enter 换行
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
      className="flex shrink-0 items-end gap-2 border-t border-brand-100 bg-white px-3 py-3"
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled || sending}
        rows={2}
        placeholder={disabled ? '准备对话中…' : '输入问题…（Enter 发送，Shift+Enter 换行）'}
        className="flex-1 resize-none rounded-lg border border-brand-100 bg-white px-3 py-2 text-sm outline-none focus:border-brand-500 disabled:opacity-50"
        onKeyDown={handleKeyDown}
      />
      {sending ? (
        <button
          type="button"
          onClick={onAbort}
          className="flex h-9 items-center gap-1 rounded-lg bg-red-500 px-3 text-sm text-white hover:bg-red-600"
          title="停止生成"
        >
          <Square size={14} /> 停止
        </button>
      ) : (
        <button
          type="submit"
          disabled={!text.trim() || disabled}
          className="flex h-9 items-center gap-1 rounded-lg bg-brand-500 px-3 text-sm text-white hover:bg-brand-600 disabled:opacity-50"
          title="发送（Enter）"
        >
          <SendHorizontal size={14} /> 发送
        </button>
      )}
    </form>
  )
}
