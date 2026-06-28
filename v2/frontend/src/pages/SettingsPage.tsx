import { useEffect, useState } from 'react'
import { Trash2 } from 'lucide-react'
import {
  ApiCallError,
  deleteSkill,
  getHealth,
  listSkills,
  upsertSkill,
  type HealthInfo,
  type Skill,
} from '@/api'
import { useUIStore } from '@/stores/ui'
import { Loading, EmptyState, ErrorBox } from '@/components/Feedback'
import { HoloCard } from '@/components/HoloCard'
import { NeonBadge } from '@/components/NeonBadge'
import { NeonToggle } from '@/components/NeonToggle'

export default function SettingsPage() {
  const pushToast = useUIStore((s) => s.pushToast)
  const [health, setHealth] = useState<HealthInfo | null>(null)
  const [healthLoading, setHealthLoading] = useState(true)
  const [healthError, setHealthError] = useState<string | null>(null)
  const [skills, setSkills] = useState<Skill[]>([])
  const [skillsLoading, setSkillsLoading] = useState(true)

  const loadHealth = async () => {
    setHealthLoading(true)
    try {
      const h = await getHealth()
      setHealth(h)
      setHealthError(null)
    } catch (err) {
      setHealthError(err instanceof Error ? err.message : String(err))
    } finally {
      setHealthLoading(false)
    }
  }

  const loadSkills = async () => {
    setSkillsLoading(true)
    try {
      const list = await listSkills()
      setSkills(list)
    } catch (err) {
      pushToast('error', `技能列表加载失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setSkillsLoading(false)
    }
  }

  useEffect(() => {
    void loadHealth()
    void loadSkills()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleDeleteSkill = async (slug: string) => {
    if (!confirm(`确认删除技能「${slug}」？`)) return
    try {
      await deleteSkill(slug)
      pushToast('success', `已删除技能 ${slug}`)
      await loadSkills()
    } catch (err) {
      pushToast('error', `删除失败：${err instanceof ApiCallError ? err.message : String(err)}`)
    }
  }

  const handleToggleEnabled = async (skill: Skill) => {
    try {
      await upsertSkill({
        slug: skill.slug,
        name: skill.name,
        description: skill.description,
        content: skill.content,
        enabled: !skill.enabled,
        level: skill.level,
      })
      await loadSkills()
    } catch (err) {
      pushToast('error', `切换失败：${err instanceof ApiCallError ? err.message : String(err)}`)
    }
  }

  return (
    <section className="page-section">
      <div className="section-label">// settings.page</div>
      <h2 className="section-title">设置</h2>
      <p className="section-desc">系统健康监控与技能管理。终端风格信息展示配合霓虹状态指示器。</p>

      <div className="grid grid-cols-1 gap-lg md:grid-cols-2">
        <HoloCard>
          <div className="card-title mb-md flex items-center gap-2 font-rounded text-base font-bold">
            <span className="text-xl">❤️</span>
            系统健康检查
          </div>
          {healthLoading ? (
            <Loading label="检查中…" />
          ) : healthError ? (
            <ErrorBox message={healthError} />
          ) : health ? (
            <div className="flex flex-col">
              <HealthItem
                label="Backend API (Go)"
                status="运行中"
                statusColor="#2dbe0e"
                badge={<NeonBadge color="cyan">:8000</NeonBadge>}
              />
              <HealthItem
                label="Database (SQLite)"
                status="正常"
                statusColor="#2dbe0e"
                badge={<NeonBadge color="green">{health.paper_count} 篇</NeonBadge>}
              />
              <HealthItem
                label="LLM Provider"
                status={health.llm_provider || '未配置'}
                statusColor={health.llm_provider ? '#2dbe0e' : '#b8a200'}
                badge={<NeonBadge color="purple">{health.llm_model || '-'}</NeonBadge>}
              />
            </div>
          ) : null}
          <div className="mt-4 flex gap-3">
            <button
              type="button"
              onClick={loadHealth}
              className="rounded-md border border-neon-cyan/25 bg-neon-cyan/8 px-3 py-1.5 text-xs font-semibold text-neon-cyan transition-colors hover:bg-neon-cyan/15"
            >
              重新检查
            </button>
          </div>
        </HoloCard>

        <HoloCard>
          <div className="card-title mb-md flex items-center gap-2 font-rounded text-base font-bold">
            <span className="text-xl">🖥️</span>
            系统信息
          </div>
          <div className="flex flex-col gap-1 font-mono text-xs">
            <InfoRow label="数据目录" value={health?.data_dir ?? '-'} valueClass="text-neon-cyan" />
            <InfoRow label="数据库路径" value={health?.db_path ?? '-'} />
            <InfoRow label="论文数量" value={`${health?.paper_count ?? 0} 篇`} valueClass="text-neon-magenta" />
            <InfoRow label="LLM Provider" value={health?.llm_provider ?? '-'} valueClass="text-neon-cyan" />
            <InfoRow label="LLM Model" value={health?.llm_model ?? '-'} valueClass="text-neon-purple" />
          </div>
        </HoloCard>

        <HoloCard>
          <div className="card-title mb-md flex items-center gap-2 font-rounded text-base font-bold">
            <span className="text-xl">🛠️</span>
            技能管理
          </div>
          {skillsLoading ? (
            <Loading label="加载技能…" />
          ) : skills.length === 0 ? (
            <EmptyState title="暂无技能" hint="对话后自动进化或手动添加" />
          ) : (
            <ul className="flex flex-col">
              {skills.map((s) => (
                <SkillRow
                  key={s.slug}
                  skill={s}
                  onDelete={() => handleDeleteSkill(s.slug)}
                  onToggle={() => handleToggleEnabled(s)}
                />
              ))}
            </ul>
          )}
        </HoloCard>

        <HoloCard className="evolution-card text-center">
          <span className="mb-md block text-5xl animate-float">✨</span>
          <div className="evo-title mb-2 font-rounded text-xl font-extrabold gradient-text text-bili-huanzi">
            自我进化系统
          </div>
          <p className="mb-lg text-sm text-text-secondary">
            基于使用数据自动优化 prompt 策略和检索精度
            <br />
            每一次对话都在让牛马变得更聪明
          </p>
          <div className="mx-auto mb-2 flex justify-center gap-sm">
            {Array.from({ length: 10 }).map((_, i) => (
              <div
                key={i}
                className={`h-2 w-6 rounded-pill transition-colors ${
                  i < 7 ? 'bg-gradient-to-r from-neon-cyan to-neon-purple shadow-[0_0_8px_rgba(78,205,196,0.3)]' : 'bg-[#e0e0ea]'
                }`}
              />
            ))}
          </div>
          <div className="mb-lg font-mono text-xs text-text-muted">进化等级 7/10</div>
        </HoloCard>
      </div>
    </section>
  )
}

function HealthItem({
  label,
  status,
  statusColor,
  badge,
}: {
  label: string
  status: string
  statusColor: string
  badge: React.ReactNode
}) {
  return (
    <div className="flex items-center justify-between border-b border-black/6 py-2.5 last:border-b-0">
      <div className="flex items-center gap-2 text-sm">{label}</div>
      <div className="flex items-center gap-2 font-mono text-xs">
        <span className="status-dot h-2 w-2 rounded-full animate-neon-pulse-fast" style={{ background: statusColor, boxShadow: `0 0 8px ${statusColor}` }} />
        <span style={{ color: statusColor }}>{status}</span>
        {badge}
      </div>
    </div>
  )
}

function InfoRow({
  label,
  value,
  valueClass,
}: {
  label: string
  value: string
  valueClass?: string
}) {
  return (
    <div className="flex justify-between rounded-md px-3 py-1.5 odd:bg-black/[0.02]">
      <span className="text-text-muted">{label}</span>
      <span className={`font-semibold ${valueClass ?? 'text-text-primary'}`}>{value}</span>
    </div>
  )
}

function SkillRow({
  skill,
  onDelete,
  onToggle,
}: {
  skill: Skill
  onDelete: () => void
  onToggle: () => void
}) {
  return (
    <li className="flex items-start justify-between gap-3 border-b border-black/6 py-3 last:border-b-0">
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-semibold">{skill.name}</span>
          <code className="rounded bg-black/[0.04] px-1.5 py-0.5 font-mono text-[10px]">{skill.slug}</code>
          <NeonBadge color={skill.enabled ? 'green' : 'yellow'}>{skill.enabled ? '启用' : '停用'}</NeonBadge>
        </div>
        <p className="mt-0.5 text-xs text-text-secondary">{skill.description || '无描述'}</p>
        <p className="mt-1 text-[11px] text-text-muted">
          用 {skill.usage_count} 次 · 成功率 {(skill.success_rate * 100).toFixed(0)}% · v{skill.version}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <NeonToggle checked={skill.enabled} onChange={onToggle} />
        <button
          type="button"
          onClick={onDelete}
          className="flex h-8 w-8 items-center justify-center rounded-full border border-neon-magenta/25 bg-neon-magenta/8 text-neon-magenta transition-colors hover:bg-neon-magenta/15"
          aria-label="删除"
        >
          <Trash2 size={14} />
        </button>
      </div>
    </li>
  )
}
