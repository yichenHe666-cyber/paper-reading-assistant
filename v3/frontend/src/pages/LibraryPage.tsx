import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Download, RefreshCw, BookMarked, Star } from 'lucide-react'
import {
  ApiCallError,
  syncPapers,
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

const STATUS_BADGE: Record<ReadStatus, { color: 'cyan' | 'yellow' | 'green' | 'purple'; text: string; icon: string }> = {
  unread: { color: 'cyan', text: '🔵 未读', icon: '🔵' },
  reading: { color: 'yellow', text: '📖 在读', icon: '📖' },
  done: { color: 'green', text: '✓ 已读', icon: '✓' },
  reread: { color: 'purple', text: '🔄 重读', icon: '🔄' },
}

export default function LibraryPage() {
  const { topicId } = useParams<{ topicId?: string }>()
  const navigate = useNavigate()
  const {
    topics,
    papers,
    topicsLoading,
    papersLoading,
    selectedTopicId,
    loadTopics,
    selectTopic,
  } = useLibraryStore()
  const pushToast = useUIStore((s) => s.pushToast)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    void selectTopic(topicId ?? null).catch((err) => {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      pushToast('error', `加载论文失败：${msg}`)
    })
  }, [topicId, selectTopic, pushToast])

  const handleSync = async () => {
    setSyncing(true)
    setError(null)
    try {
      const result = await syncPapers()
      pushToast('success', `同步完成：新增 ${result.topics_added} 主题 / ${result.papers_added} 论文`)
      await loadTopics()
      if (topicId) {
        await selectTopic(topicId)
      }
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
      if (topicId) await selectTopic(topicId)
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
            <span className="flex items-center gap-1.5 font-rounded text-base font-bold">
              <BookMarked size={16} /> 主题分类
            </span>
          </div>
          {topicsLoading ? (
            <Loading label="加载主题…" />
          ) : topics.length === 0 ? (
            <EmptyState title="暂无主题" hint="点同步按钮获取论文" />
          ) : (
            <ul className="flex flex-col gap-0.5">
              <li
                onClick={() => navigate('/library')}
                className={`topic-item flex cursor-pointer items-center justify-between rounded-md border border-transparent px-3.5 py-2.5 transition-colors ${
                  selectedTopicId === null
                    ? 'border-neon-purple/35 bg-gradient-to-br from-neon-purple/10 to-neon-magenta/5'
                    : 'hover:border-neon-purple/15 hover:bg-neon-purple/5'
                }`}
              >
                <span className={`text-sm ${selectedTopicId === null ? 'font-semibold text-neon-purple' : 'font-medium'}`}>
                  全部论文
                </span>
                <span className={`rounded-pill px-2 py-0.5 font-mono text-[11px] ${
                  selectedTopicId === null ? 'bg-neon-purple/15 text-neon-purple' : 'bg-black/6 text-text-muted'
                }`}>
                  {topics.reduce((sum, t) => sum + (t.paper_count ?? 0), 0)}
                </span>
              </li>
              {topics.map((t) => (
                <li
                  key={t.id}
                  onClick={() => navigate(`/library/${t.id}`)}
                  className={`topic-item flex cursor-pointer items-center justify-between rounded-md border border-transparent px-3.5 py-2.5 transition-colors ${
                    selectedTopicId === t.id
                      ? 'border-neon-purple/35 bg-gradient-to-br from-neon-purple/10 to-neon-magenta/5'
                      : 'hover:border-neon-purple/15 hover:bg-neon-purple/5'
                  }`}
                >
                  <span className={`truncate text-sm ${selectedTopicId === t.id ? 'font-semibold text-neon-purple' : 'font-medium'}`}>
                    {t.name_cn || t.name}
                  </span>
                  <span className={`rounded-pill px-2 py-0.5 font-mono text-[11px] ${
                    selectedTopicId === t.id ? 'bg-neon-purple/15 text-neon-purple' : 'bg-black/6 text-text-muted'
                  }`}>
                    {t.paper_count}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </aside>

        <section className="flex flex-col py-lg">
          <header className="library-header mb-lg flex items-center justify-between">
            <h3 className="font-rounded text-lg font-bold">
              {selectedTopicId
                ? topics.find((t) => t.id === selectedTopicId)?.name_cn ||
                  topics.find((t) => t.id === selectedTopicId)?.name ||
                  '论文'
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
            ) : !selectedTopicId && topics.length > 0 ? (
              <EmptyState title="选择一个主题" hint="查看该主题下的论文" />
            ) : papersLoading ? (
              <Loading label="加载论文…" />
            ) : papers.length === 0 ? (
              <EmptyState title="该主题暂无论文" hint="尝试点同步按钮获取" />
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
      <div className="absolute right-3 top-3">
        <NeonBadge color={status.color}>{status.text}</NeonBadge>
      </div>
      <h3 className="mb-1.5 pr-16 font-rounded text-[15px] font-bold leading-snug">{paper.title}</h3>
      <p className="mb-md text-xs" style={{ color: '#4a4a6a', textShadow: '0 0 0.3px rgba(0,0,0,0.15)' }}>
        {paper.authors || '未知作者'}
        {paper.year ? ` · ${paper.year}` : ''}
      </p>
      {paper.abstract ? (
        <p
          className="mb-md line-clamp-3 text-[13px] leading-relaxed"
          style={{ color: '#3a3a5a', textShadow: '0 0 0.3px rgba(0,0,0,0.2)', WebkitTextStroke: '0.15px rgba(0,0,0,0.08)', paintOrder: 'stroke fill' }}
        >
          {paper.abstract}
        </p>
      ) : null}
      <div className="flex items-center justify-between">
        <span className="font-mono text-xs text-text-muted">
          {paper.year ?? '-'}
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
