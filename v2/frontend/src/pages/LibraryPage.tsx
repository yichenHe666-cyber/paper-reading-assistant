import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Download, RefreshCw, Star } from 'lucide-react'
import {
  ApiCallError,
  syncSources,
  updatePaperStatus,
  type Paper,
  type ReadStatus,
} from '@/api'
import { useLibraryStore } from '@/stores/library'
import { useUIStore } from '@/stores/ui'
import { Loading, EmptyState, ErrorBox } from '@/components/Feedback'
import { NeonBadge } from '@/components/NeonBadge'

const STATUS_LABELS: Record<ReadStatus, string> = {
  unread: '未读',
  reading: '在读',
  done: '已读',
  reread: '重读',
}

const STATUS_ORDER: ReadStatus[] = ['unread', 'reading', 'done', 'reread']

const STATUS_BADGE: Record<ReadStatus, { color: 'cyan' | 'yellow' | 'green' | 'purple'; text: string }> = {
  unread: { color: 'cyan', text: '🔵 未读' },
  reading: { color: 'yellow', text: '📖 在读' },
  done: { color: 'green', text: '✓ 已读' },
  reread: { color: 'purple', text: '🔄 重读' },
}

// level 难度对应的霓虹徽章颜色
const LEVEL_BADGE: Record<string, 'cyan' | 'yellow' | 'purple'> = {
  beginner: 'cyan',
  intermediate: 'yellow',
  advanced: 'purple',
}

// 解析 tags JSON 字符串为数组（后端存 JSON 字符串如 '["transformer","attention"]'）
function parseTags(tags: string): string[] {
  if (!tags) return []
  try {
    const arr = JSON.parse(tags)
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export default function LibraryPage() {
  const { sourceId } = useParams<{ sourceId?: string }>()
  const navigate = useNavigate()
  const {
    sources,
    papers,
    sourcesLoading,
    papersLoading,
    loadSources,
    applyFilter,
  } = useLibraryStore()
  const pushToast = useUIStore((s) => s.pushToast)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 初次加载源列表
  useEffect(() => {
    void loadSources().catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      pushToast('error', `加载数据源失败：${msg}`)
    })
  }, [loadSources, pushToast])

  // 按 sourceId 筛选论文
  useEffect(() => {
    const filter = sourceId ? { source: sourceId, page: 1, page_size: 50 } : { page: 1, page_size: 50 }
    void applyFilter(filter).catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      pushToast('error', `加载论文失败：${msg}`)
    })
  }, [sourceId, applyFilter, pushToast])

  const handleSync = async () => {
    setSyncing(true)
    setError(null)
    try {
      const result = await syncSources()
      pushToast('success', `同步完成：${result.success_count}/${result.total_sources} 源成功，新增 ${result.total_papers} 篇论文`)
      await loadSources()
      // 重新应用当前筛选
      const filter = sourceId ? { source: sourceId, page: 1, page_size: 50 } : { page: 1, page_size: 50 }
      await applyFilter(filter)
    } catch (err) {
      const msg = err instanceof ApiCallError ? err.message : String(err)
      setError(msg)
      pushToast('error', `同步失败：${msg}`)
    } finally {
      setSyncing(false)
    }
  }

  const handleStatusChange = async (paper: Paper, status: ReadStatus) => {
    try {
      await updatePaperStatus(paper.id, status)
      pushToast('success', `已标记「${paper.title.slice(0, 20)}…」为${STATUS_LABELS[status]}`)
      // 重新应用当前筛选以刷新列表
      const filter = sourceId ? { source: sourceId, page: 1, page_size: 50 } : { page: 1, page_size: 50 }
      await applyFilter(filter)
    } catch (err) {
      const msg = err instanceof ApiCallError ? err.message : String(err)
      pushToast('error', `状态更新失败：${msg}`)
    }
  }

  return (
    <section className="page-section !min-h-[80vh] !py-0">
      <div className="library-layout grid min-h-[80vh] grid-cols-[240px_1fr] gap-lg py-lg">
        <aside className="library-sidebar flex flex-col gap-sm">
          <div className="sidebar-header mb-sm flex items-center justify-between">
            <span className="font-rounded text-sm font-bold text-text-secondary">
              <span className="mr-1">📂</span> 数据源
            </span>
          </div>
          {sourcesLoading ? (
            <Loading label="加载数据源…" />
          ) : sources.length === 0 ? (
            <EmptyState title="暂无数据源" hint="点同步按钮获取论文" />
          ) : (
            <ul className="flex flex-col gap-0.5">
              <li
                onClick={() => navigate('/library')}
                className={`topic-item flex cursor-pointer items-center justify-between rounded-md border border-transparent px-3.5 py-2.5 transition-colors ${
                  !sourceId
                    ? 'border-neon-purple/35 bg-gradient-to-br from-neon-purple/10 to-neon-magenta/5'
                    : 'hover:border-neon-purple/15 hover:bg-neon-purple/5'
                }`}
              >
                <span className={`text-sm ${!sourceId ? 'font-semibold text-neon-purple' : 'font-medium'}`}>
                  全部论文
                </span>
              </li>
              {sources.map((s) => (
                <li
                  key={s.id}
                  onClick={() => navigate(`/library/${s.id}`)}
                  className={`topic-item flex cursor-pointer items-center justify-between rounded-md border border-transparent px-3.5 py-2.5 transition-colors ${
                    sourceId === s.id
                      ? 'border-neon-purple/35 bg-gradient-to-br from-neon-purple/10 to-neon-magenta/5'
                      : 'hover:border-neon-purple/15 hover:bg-neon-purple/5'
                  }`}
                >
                  <span className={`truncate text-sm ${sourceId === s.id ? 'font-semibold text-neon-purple' : 'font-medium'}`}>
                    {s.name}
                  </span>
                  <span className={`rounded-pill px-2 py-0.5 font-mono text-[11px] ${
                    sourceId === s.id ? 'bg-neon-purple/15 text-neon-purple' : 'bg-black/6 text-text-muted'
                  }`}>
                    {s.sync_count}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="flex flex-col py-lg">
          <header className="library-header mb-lg flex items-center justify-between">
            <h3 className="font-rounded text-lg font-bold">
              {sourceId
                ? sources.find((s) => s.id === sourceId)?.name ?? '论文'
                : '全部论文'}
              <span className="ml-2 text-sm font-normal text-text-muted">· {papers.length} 篇</span>
            </h3>
            <button
              type="button"
              onClick={handleSync}
              disabled={syncing}
              className="inline-flex items-center gap-1.5 rounded-pill border-2 border-neon-purple bg-neon-purple/8 px-4 py-2 font-rounded text-sm font-semibold text-neon-purple transition-all hover:bg-neon-purple/15 hover:shadow-glow-purple disabled:opacity-50"
            >
              <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
              同步文献库
            </button>
          </header>

          <div className="flex-1 overflow-y-auto">
            {error ? (
              <ErrorBox message={error} />
            ) : papersLoading ? (
              <Loading label="加载论文…" />
            ) : papers.length === 0 ? (
              <EmptyState title="暂无论文" hint="尝试点同步按钮获取" />
            ) : (
              <div className="grid grid-cols-[repeat(auto-fill,minmax(320px,1fr))] gap-lg">
                {papers.map((p) => (
                  <PaperCard key={p.id} paper={p} onStatusChange={handleStatusChange} />
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </section>
  )
}

interface PaperCardProps {
  paper: Paper
  onStatusChange: (paper: Paper, status: ReadStatus) => void
}

function PaperCard({ paper, onStatusChange }: PaperCardProps) {
  const status = STATUS_BADGE[paper.read_status ?? 'unread']
  const tags = parseTags(paper.tags)
  return (
    <div className="paper-card group relative overflow-hidden rounded-lg border border-black/6 bg-bg-card p-lg transition-all hover:-translate-y-1.5 hover:border-neon-purple/30 hover:shadow-glow-purple">
      <div className="absolute inset-0 -z-10 opacity-0 transition-opacity group-hover:opacity-100">
        <div
          className="absolute inset-0 animate-holo-shimmer"
          style={{
            background: 'linear-gradient(135deg, rgba(78,205,196,0.12), rgba(180,77,255,0.12), rgba(255,45,149,0.08), rgba(255,224,51,0.06), rgba(78,205,196,0.12))',
            backgroundSize: '300% 300%',
          }}
        />
      </div>
      <div className="absolute right-3 top-3 flex gap-1.5">
        {paper.level ? (
          <NeonBadge color={LEVEL_BADGE[paper.level] ?? 'cyan'}>{paper.level}</NeonBadge>
        ) : null}
        <NeonBadge color={status.color}>{status.text}</NeonBadge>
      </div>
      <h3 className="mb-1.5 pr-32 font-rounded text-[15px] font-bold leading-snug">{paper.title}</h3>
      <p className="mb-md text-xs" style={{ color: '#4a4a6a', textShadow: '0 0 0.3px rgba(0,0,0,0.15)' }}>
        {paper.authors || '未知作者'}
        {paper.year ? ` · ${paper.year}` : ''}
        {paper.venue ? ` · ${paper.venue}` : ''}
      </p>
      {paper.abstract ? (
        <p
          className="mb-md line-clamp-3 text-[13px] leading-relaxed"
          style={{ color: '#3a3a5a', textShadow: '0 0 0.3px rgba(0,0,0,0.2)', WebkitTextStroke: '0.15px rgba(0,0,0,0.08)', paintOrder: 'stroke fill' }}
        >
          {paper.abstract}
        </p>
      ) : null}
      {tags.length > 0 ? (
        <div className="mb-md flex flex-wrap gap-1">
          {tags.slice(0, 4).map((t) => (
            <NeonBadge key={t} color="purple">{t}</NeonBadge>
          ))}
        </div>
      ) : null}
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-text-muted">
          {paper.difficulty_score ? `难度 ${paper.difficulty_score}/10` : (paper.year ?? '-')}
        </span>
        <div className="flex items-center gap-sm">
          {paper.pdf_url ? (
            <a
              href={paper.pdf_url}
              target="_blank"
              rel="noreferrer noopener"
              className="action-btn flex h-8 w-8 items-center justify-center rounded-full border border-black/6 bg-bg-secondary text-text-muted transition-all hover:border-neon-magenta hover:bg-neon-magenta/8 hover:text-neon-magenta hover:shadow-[0_0_12px_rgba(255,45,149,0.2)]"
              title="下载 PDF"
            >
              <Download size={14} />
            </a>
          ) : null}
          <button
            type="button"
            className="action-btn flex h-8 w-8 items-center justify-center rounded-full border border-black/6 bg-bg-secondary text-text-muted transition-all hover:border-neon-magenta hover:bg-neon-magenta/8 hover:text-neon-magenta hover:shadow-[0_0_12px_rgba(255,45,149,0.2)]"
            title="收藏"
          >
            <Star size={14} />
          </button>
          <select
            value={paper.read_status ?? 'unread'}
            onChange={(e) => onStatusChange(paper, e.target.value as ReadStatus)}
            className="h-8 rounded-pill border border-black/6 bg-bg-secondary px-2.5 text-xs text-text-secondary outline-none focus:border-neon-purple"
          >
            {STATUS_ORDER.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  )
}
