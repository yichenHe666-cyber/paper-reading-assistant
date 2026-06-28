// 论文库页：多数据源 AI 论文筛选 / 分页浏览界面。
//
// 单栏布局：Header（同步 + AI 分类）→ 筛选栏 → 数据源状态条 → 论文列表 → 分页。
// 主题已不再主用，改用 source/level/type/sub_domain 筛选 + 关键词搜索。
import { useEffect, useState } from 'react'
import type React from 'react'
import { useNavigate } from 'react-router-dom'
import {
  BookOpen,
  ChevronLeft,
  ChevronRight,
  Clock,
  ExternalLink,
  FileText,
  Filter,
  RefreshCw,
  Search,
  Sparkles,
} from 'lucide-react'
import { ApiCallError, updatePaperStatus, type Paper, type PaperFilter, type ReadStatus } from '@/api'
import { useLibraryStore } from '@/stores/library'
import { useUIStore } from '@/stores/ui'
import { EmptyState, ErrorBox, Loading } from '@/components/Feedback'

const STATUS_LABELS: Record<ReadStatus, string> = {
  unread: '未读',
  reading: '在读',
  done: '已读',
  reread: '重读',
}

const STATUS_ORDER: ReadStatus[] = ['unread', 'reading', 'done', 'reread']

const LEVEL_LABELS: Record<string, string> = {
  beginner: '入门',
  intermediate: '进阶',
  advanced: '高阶',
}

const TYPE_LABELS: Record<string, string> = {
  survey: '综述',
  tutorial: '教程',
  classic: '经典',
  original: '原创',
  research: '研究',
  engineering: '工程',
  report: '报告',
}

const SUB_DOMAIN_LABELS: Record<string, string> = {
  ml: 'ML',
  dl: 'DL',
  llm: 'LLM',
  context_eng: '上下文工程',
  safety: '安全',
  rl: '强化学习',
  reasoning: '推理',
  infra: '基础设施',
  dist_sys: '分布式系统',
  cv: 'CV',
  nlp: 'NLP',
}

const SOURCE_OPTIONS = [
  { value: '', label: '全部来源' },
  { value: 'arxiv', label: 'arXiv' },
  { value: 'openalex', label: 'OpenAlex' },
  { value: 'acl', label: 'ACL' },
  { value: 'company', label: 'Company' },
]

const LEVEL_OPTIONS = [
  { value: '', label: '全部难度' },
  { value: 'beginner', label: '入门' },
  { value: 'intermediate', label: '进阶' },
  { value: 'advanced', label: '高阶' },
]

const TYPE_OPTIONS = [
  { value: '', label: '全部类型' },
  { value: 'survey', label: '综述' },
  { value: 'tutorial', label: '教程' },
  { value: 'classic', label: '经典' },
  { value: 'original', label: '原创' },
  { value: 'research', label: '研究' },
  { value: 'engineering', label: '工程' },
  { value: 'report', label: '报告' },
]

const SUB_DOMAIN_OPTIONS = [
  { value: '', label: '全部子领域' },
  { value: 'ml', label: 'ML' },
  { value: 'dl', label: 'DL' },
  { value: 'llm', label: 'LLM' },
  { value: 'context_eng', label: '上下文工程' },
  { value: 'safety', label: '安全' },
  { value: 'rl', label: '强化学习' },
  { value: 'reasoning', label: '推理' },
  { value: 'infra', label: '基础设施' },
  { value: 'dist_sys', label: '分布式系统' },
  { value: 'cv', label: 'CV' },
  { value: 'nlp', label: 'NLP' },
]

// formatRelativeTime 把 ISO 时间字符串格式化为相对时间。
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

// formatDuration 把秒数格式化为 "N 分钟" / "N 小时 X 分钟"。
function formatDuration(seconds: number): string {
  if (!seconds || seconds <= 0) return '—'
  const min = Math.floor(seconds / 60)
  if (min < 60) return `${min} 分钟`
  const hr = Math.floor(min / 60)
  const remMin = min % 60
  return remMin > 0 ? `${hr} 小时 ${remMin} 分钟` : `${hr} 小时`
}

// parseTags 解析 tags JSON 字符串为数组，失败返回 []。
function parseTags(tagsJSON: string): string[] {
  if (!tagsJSON) return []
  try {
    const parsed = JSON.parse(tagsJSON)
    if (Array.isArray(parsed)) {
      return parsed.filter((t): t is string => typeof t === 'string')
    }
    return []
  } catch {
    return []
  }
}

// levelColor 返回难度徽章的 Tailwind class。
function levelColor(level: string): string {
  switch (level) {
    case 'beginner':
      return 'bg-green-100 text-green-800'
    case 'intermediate':
      return 'bg-yellow-100 text-yellow-800'
    case 'advanced':
      return 'bg-red-100 text-red-800'
    default:
      return 'bg-gray-100 text-gray-800'
  }
}

export default function LibraryPage() {
  const navigate = useNavigate()
  const {
    papers,
    total,
    page,
    pageSize,
    filter,
    loading,
    sources,
    sourcesLoading,
    syncing,
    classifying,
    loadPapers,
    loadSources,
    setFilter,
    setPage,
    syncAll,
    syncOne,
    classifyAll,
  } = useLibraryStore()
  const pushToast = useUIStore((s) => s.pushToast)
  const [error, setError] = useState<string | null>(null)
  const [searchInput, setSearchInput] = useState(filter.q ?? '')

  // 初次挂载：加载数据源与论文
  useEffect(() => {
    setError(null)
    void loadSources().catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      pushToast('error', `加载数据源失败：${msg}`)
    })
    void loadPapers().catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      pushToast('error', `加载论文失败：${msg}`)
    })
  }, [loadSources, loadPapers, pushToast])

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  const errMsg = (err: unknown): string =>
    err instanceof ApiCallError ? err.message : String(err)

  const applyFilter = (f: Partial<PaperFilter>) => {
    setError(null)
    void setFilter(f).catch((err) => {
      const msg = errMsg(err)
      setError(msg)
      pushToast('error', `筛选失败：${msg}`)
    })
  }

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      applyFilter({ q: searchInput.trim() || undefined })
    }
  }

  const handleSyncAll = async () => {
    try {
      const results = await syncAll()
      const parts = results.map((r) =>
        r.success ? `${r.source_id}: +${r.count} 篇` : `${r.source_id}: ${r.error || '失败'}`,
      )
      pushToast('success', `同步完成 · ${parts.join(' / ')}`)
    } catch (err) {
      pushToast('error', `同步失败：${errMsg(err)}`)
    }
  }

  const handleSyncOne = async (sourceId: string, name: string) => {
    try {
      const results = await syncOne(sourceId)
      const r = results.find((x) => x.source_id === sourceId)
      if (r && r.success) {
        pushToast('success', `${name}: +${r.count} 篇`)
      } else if (r) {
        pushToast('error', `${name}: ${r.error || '失败'}`)
      }
    } catch (err) {
      pushToast('error', `${name} 同步失败：${errMsg(err)}`)
    }
  }

  const handleClassifyAll = async () => {
    try {
      const n = await classifyAll()
      pushToast('success', `已分类 ${n} 篇`)
    } catch (err) {
      pushToast('error', `AI 分类失败：${errMsg(err)}`)
    }
  }

  const handleStatusChange = async (paper: Paper, status: ReadStatus) => {
    try {
      await updatePaperStatus(paper.id, status)
      pushToast('success', `已标记「${paper.title.slice(0, 20)}…」为${STATUS_LABELS[status]}`)
      void loadPapers().catch(() => {
        /* 局部刷新失败静默 */
      })
    } catch (err) {
      pushToast('error', `状态更新失败：${errMsg(err)}`)
    }
  }

  const handleOpenReader = (paper: Paper) => {
    navigate(`/papers/${paper.id}/read`)
  }

  const handlePrev = () => {
    if (page <= 1) return
    setError(null)
    void setPage(page - 1).catch((err) => pushToast('error', `翻页失败：${errMsg(err)}`))
  }

  const handleNext = () => {
    if (page >= totalPages) return
    setError(null)
    void setPage(page + 1).catch((err) => pushToast('error', `翻页失败：${errMsg(err)}`))
  }

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <header className="flex shrink-0 items-center justify-between border-b border-brand-100 bg-white px-4 py-2">
        <h2 className="flex items-center gap-2 text-sm font-medium">
          <BookOpen size={16} /> 论文库
          <span className="text-xs font-normal text-brand-700">共 {total} 篇</span>
        </h2>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleSyncAll}
            disabled={syncing}
            className="flex items-center gap-1 rounded border border-brand-100 bg-white px-2 py-1 text-xs hover:bg-brand-50 disabled:opacity-50"
          >
            <RefreshCw size={12} className={syncing ? 'animate-spin' : ''} />
            同步
          </button>
          <button
            type="button"
            onClick={handleClassifyAll}
            disabled={classifying}
            className="flex items-center gap-1 rounded border border-brand-100 bg-white px-2 py-1 text-xs hover:bg-brand-50 disabled:opacity-50"
          >
            <Sparkles size={12} className={classifying ? 'animate-pulse' : ''} />
            AI 分类
          </button>
        </div>
      </header>

      {/* 筛选栏 */}
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-brand-100 bg-white px-4 py-2">
        <Filter size={14} className="text-brand-700" />
        <select
          value={filter.source ?? ''}
          onChange={(e) => applyFilter({ source: e.target.value || undefined })}
          className="rounded border border-brand-100 bg-white px-2 py-1 text-xs outline-none focus:border-brand-500"
        >
          {SOURCE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={filter.level ?? ''}
          onChange={(e) => applyFilter({ level: e.target.value || undefined })}
          className="rounded border border-brand-100 bg-white px-2 py-1 text-xs outline-none focus:border-brand-500"
        >
          {LEVEL_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={filter.paper_type ?? ''}
          onChange={(e) => applyFilter({ paper_type: e.target.value || undefined })}
          className="rounded border border-brand-100 bg-white px-2 py-1 text-xs outline-none focus:border-brand-500"
        >
          {TYPE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <select
          value={filter.sub_domain ?? ''}
          onChange={(e) => applyFilter({ sub_domain: e.target.value || undefined })}
          className="rounded border border-brand-100 bg-white px-2 py-1 text-xs outline-none focus:border-brand-500"
        >
          {SUB_DOMAIN_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <div className="flex flex-1 items-center gap-1">
          <Search size={14} className="shrink-0 text-brand-700" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            onKeyDown={handleSearchKeyDown}
            placeholder="搜索标题/作者/摘要…（回车）"
            className="min-w-0 flex-1 rounded border border-brand-100 bg-white px-2 py-1 text-xs outline-none focus:border-brand-500"
          />
        </div>
      </div>

      {/* 数据源状态条 */}
      <div className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-1 border-b border-brand-100 bg-brand-50/50 px-4 py-1.5 text-xs text-brand-700">
        {sourcesLoading && sources.length === 0 ? (
          <span>加载数据源…</span>
        ) : sources.length === 0 ? (
          <span>暂无数据源</span>
        ) : (
          sources.map((s) => (
            <div key={s.id} className="flex items-center gap-1">
              <span className="font-medium">{s.name}</span>
              <span className="text-brand-700/70">:</span>
              <span>{s.sync_count} 篇</span>
              <span className="text-brand-700/70">/ {formatRelativeTime(s.last_synced_at)}</span>
              <button
                type="button"
                onClick={() => handleSyncOne(s.id, s.name)}
                disabled={syncing}
                title={`同步 ${s.name}`}
                aria-label={`同步 ${s.name}`}
                className="rounded p-0.5 hover:bg-brand-100 disabled:opacity-50"
              >
                <RefreshCw size={11} className={syncing ? 'animate-spin' : ''} />
              </button>
            </div>
          ))
        )}
      </div>

      {/* 论文列表 */}
      <div className="flex-1 overflow-y-auto px-4 py-4">
        {error ? (
          <ErrorBox message={error} />
        ) : loading ? (
          <Loading label="加载论文…" />
        ) : papers.length === 0 ? (
          <EmptyState title="暂无论文" hint="调整筛选条件或点同步" />
        ) : (
          <ul className="mx-auto flex max-w-3xl flex-col gap-2">
            {papers.map((p) => (
              <PaperCard
                key={p.id}
                paper={p}
                onStatusChange={handleStatusChange}
                onOpenReader={handleOpenReader}
              />
            ))}
          </ul>
        )}
      </div>

      {/* 分页 */}
      <footer className="flex shrink-0 items-center justify-center gap-3 border-t border-brand-100 bg-white px-4 py-2 text-xs text-brand-700">
        <button
          type="button"
          onClick={handlePrev}
          disabled={page <= 1 || loading}
          className="flex items-center gap-1 rounded px-2 py-1 hover:bg-brand-100 disabled:opacity-50"
        >
          <ChevronLeft size={14} /> 上一页
        </button>
        <span>
          第 {page} / {totalPages} 页
        </span>
        <button
          type="button"
          onClick={handleNext}
          disabled={page >= totalPages || loading}
          className="flex items-center gap-1 rounded px-2 py-1 hover:bg-brand-100 disabled:opacity-50"
        >
          下一页 <ChevronRight size={14} />
        </button>
      </footer>
    </div>
  )
}

interface PaperCardProps {
  paper: Paper
  onStatusChange: (paper: Paper, status: ReadStatus) => void
  onOpenReader: (paper: Paper) => void
}

function PaperCard({ paper, onStatusChange, onOpenReader }: PaperCardProps) {
  const tags = parseTags(paper.tags).slice(0, 3)
  return (
    <li className="rounded-lg border border-brand-100 bg-white p-3">
      <div className="flex-1">
        <h3 className="text-sm font-medium leading-snug">{paper.title}</h3>
        <p className="mt-0.5 text-xs text-brand-700">
          {paper.authors || '未知作者'}
          {paper.year ? ` · ${paper.year}` : ''}
          {paper.venue ? ` · ${paper.venue}` : ''}
        </p>
        {paper.abstract ? (
          <p className="mt-1 line-clamp-2 text-xs text-brand-700/80">{paper.abstract}</p>
        ) : null}
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        {paper.level ? (
          <span className={`rounded px-1.5 py-0.5 text-xs ${levelColor(paper.level)}`}>
            {LEVEL_LABELS[paper.level] ?? paper.level}
          </span>
        ) : null}
        {paper.paper_type ? (
          <span className="rounded bg-brand-50 px-1.5 py-0.5 text-xs text-brand-700">
            {TYPE_LABELS[paper.paper_type] ?? paper.paper_type}
          </span>
        ) : null}
        {paper.sub_domain ? (
          <span className="rounded bg-brand-50 px-1.5 py-0.5 text-xs text-brand-700">
            {SUB_DOMAIN_LABELS[paper.sub_domain] ?? paper.sub_domain}
          </span>
        ) : null}
        {paper.source ? (
          <span className="rounded bg-brand-50 px-1.5 py-0.5 text-xs text-brand-700">
            {paper.source}
          </span>
        ) : null}
        {tags.map((t, i) => (
          <span key={`${t}-${i}`} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
            #{t}
          </span>
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-3 text-xs text-brand-700/80">
          <span className="flex items-center gap-1">
            <Clock size={12} />
            {paper.last_read_at
              ? `${formatRelativeTime(paper.last_read_at)} · 累计 ${formatDuration(paper.total_read_seconds)}`
              : '未读'}
          </span>
          <span className="flex items-center gap-1">
            <FileText size={12} />
            <select
              value={paper.read_status}
              onChange={(e) => onStatusChange(paper, e.target.value as ReadStatus)}
              className="rounded border border-brand-100 bg-white px-1 py-0.5 text-xs outline-none focus:border-brand-500"
            >
              {STATUS_ORDER.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </select>
          </span>
        </div>
        <button
          type="button"
          onClick={() => onOpenReader(paper)}
          className="flex items-center gap-1 rounded border border-brand-100 bg-white px-2 py-1 text-xs hover:bg-brand-50"
          title="打开阅读器"
        >
          <ExternalLink size={12} /> 打开阅读器
        </button>
      </div>
    </li>
  )
}
