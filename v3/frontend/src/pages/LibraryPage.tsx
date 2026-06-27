// 论文库页：主题列表 + 论文列表 + 阅读状态切换 + 同步触发。
//
// 痛点②验收可视点：同步后刷新页面，论文计数不变（路径绝对化 + 后端 Upsert 幂等）。
// 痛点③修复：所有文本走 JSX，lucide 本地图标，状态用 URL params 持久化。
import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Download, RefreshCw, BookMarked, FileText } from 'lucide-react'
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

const STATUS_LABELS: Record<ReadStatus, string> = {
  unread: '未读',
  reading: '在读',
  done: '已读',
  reread: '重读',
}

const STATUS_ORDER: ReadStatus[] = ['unread', 'reading', 'done', 'reread']

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

  // topicId 变化 → 加载论文
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
      // 局部刷新当前主题
      if (topicId) await selectTopic(topicId)
    } catch (err) {
      const msg = err instanceof ApiCallError ? err.message : String(err)
      pushToast('error', `状态更新失败：${msg}`)
    }
  }

  return (
    <div className="flex h-full">
      {/* 主题列表 */}
      <section className="hidden w-64 shrink-0 flex-col border-r border-brand-100 bg-white md:flex">
        <div className="flex items-center justify-between border-b border-brand-100 px-3 py-2">
          <span className="flex items-center gap-1 text-xs font-semibold uppercase text-brand-700">
            <BookMarked size={12} /> 主题
          </span>
          <button
            type="button"
            onClick={handleSync}
            disabled={syncing}
            className="rounded p-1 hover:bg-brand-100 disabled:opacity-50"
            title="从 GitHub 同步"
            aria-label="同步"
          >
            <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto">
          {topicsLoading ? (
            <Loading label="加载主题…" />
          ) : topics.length === 0 ? (
            <EmptyState title="暂无主题" hint="点右上 ↻ 同步" />
          ) : (
            <ul className="py-1">
              {topics.map((t) => (
                <li key={t.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/library/${t.id}`)}
                    className={`w-full truncate px-3 py-2 text-left text-sm transition-colors ${
                      selectedTopicId === t.id ? 'bg-brand-100 text-brand-900' : 'hover:bg-brand-50'
                    }`}
                  >
                    <div className="truncate">{t.name_cn || t.name}</div>
                    <div className="text-xs text-brand-700/70">{t.paper_count} 篇</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </section>

      {/* 论文列表 */}
      <section className="flex flex-1 flex-col overflow-hidden">
        <header className="flex items-center justify-between border-b border-brand-100 bg-white px-4 py-2">
          <h2 className="text-sm font-medium">
            {selectedTopicId
              ? topics.find((t) => t.id === selectedTopicId)?.name_cn ||
                topics.find((t) => t.id === selectedTopicId)?.name ||
                '论文'
              : '选择左侧主题'}
          </h2>
          <span className="text-xs text-brand-700">{papers.length} 篇</span>
        </header>
        <div className="flex-1 overflow-y-auto px-4 py-4">
          {error ? (
            <ErrorBox message={error} />
          ) : !selectedTopicId ? (
            <EmptyState title="选择一个主题" hint="查看该主题下的论文" />
          ) : papersLoading ? (
            <Loading label="加载论文…" />
          ) : papers.length === 0 ? (
            <EmptyState title="该主题暂无论文" hint="尝试点左上 ↻ 同步" />
          ) : (
            <ul className="mx-auto flex max-w-3xl flex-col gap-2">
              {papers.map((p) => (
                <PaperCard key={p.id} paper={p} onStatusChange={handleStatusChange} />
              ))}
            </ul>
          )}
        </div>
      </section>
    </div>
  )
}

interface PaperCardProps {
  paper: Paper
  onStatusChange: (paper: Paper, status: ReadStatus) => void
}

function PaperCard({ paper, onStatusChange }: PaperCardProps) {
  return (
    <li className="rounded-lg border border-brand-100 bg-white p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1">
          <h3 className="text-sm font-medium leading-snug">{paper.title}</h3>
          <p className="mt-0.5 text-xs text-brand-700">
            {paper.authors || '未知作者'}
            {paper.year ? ` · ${paper.year}` : ''}
          </p>
          {paper.abstract ? (
            <p className="mt-1 line-clamp-2 text-xs text-brand-700/80">{paper.abstract}</p>
          ) : null}
        </div>
        {paper.pdf_url ? (
          <a
            href={paper.pdf_url}
            target="_blank"
            rel="noreferrer noopener"
            className="shrink-0 rounded p-1.5 hover:bg-brand-100"
            title="下载 PDF"
            aria-label="下载 PDF"
          >
            <Download size={14} />
          </a>
        ) : null}
      </div>
      <div className="mt-2 flex items-center gap-2">
        <FileText size={12} className="text-brand-700/70" />
        <select
          value={paper.read_status}
          onChange={(e) => onStatusChange(paper, e.target.value as ReadStatus)}
          className="rounded border border-brand-100 bg-white px-2 py-0.5 text-xs outline-none focus:border-brand-500"
        >
          {STATUS_ORDER.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABELS[s]}
            </option>
          ))}
        </select>
      </div>
    </li>
  )
}
