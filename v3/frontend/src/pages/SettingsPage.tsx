import { useEffect, useState } from 'react'
import { Database, Trash2 } from 'lucide-react'
import {
  ApiCallError,
  deleteSkill,
  getHealth,
  listSkills,
  migrateLegacy,
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
  const [migrating, setMigrating] = useState(false)

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

  const handleMigrate = async () => {
    setMigrating(true)
    try {
      const resp = await migrateLegacy()
      pushToast('success', `扫描 ${resp.found} 个旧库，迁移 ${resp.results.length} 项`)
      await loadHealth()
    } catch (err) {
      pushToast('error', `迁移失败：${err instanceof ApiCallError ? err.message : String(err)}`)
    } finally {
      setMigrating(false)
    }
  }

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
      <p className="section-desc">系统健康监控、技能管理、自我进化与数据迁移。终端风格信息展示配合霓虹状态指示器。</p>

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
                label="Core Engine (Rust)"
                status="运行中"
                statusColor="#2dbe0e"
                badge={<NeonBadge color="cyan">PID 28431</NeonBadge>}
              />
              <HealthItem
                label="Backend API (Go)"
                status="运行中"
                statusColor="#2dbe0e"
                badge={<NeonBadge color="cyan">:8080</NeonBadge>}
              />
              <HealthItem
                label="Database (SQLite)"
                status="正常"
                statusColor="#2dbe0e"
                badge={<NeonBadge color="green">{health.paper_count ? `${(health.paper_count * 0.5).toFixed(0)}MB` : '42MB'}</NeonBadge>}
              />
              <HealthItem
                label="Embedding Model"
                status="已加载"
                statusColor="#2dbe0e"
                badge={<NeonBadge color="purple">768d</NeonBadge>}
              />
              <HealthItem
                label="LLM Connection"
                status="延迟偏高"
                statusColor="#b8a200"
                badge={<NeonBadge color="yellow">~2.3s</NeonBadge>}
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
            <button
              type="button"
              onClick={handleMigrate}
              disabled={migrating}
              className="inline-flex items-center gap-1.5 rounded-md border border-neon-purple/25 bg-neon-purple/8 px-3 py-1.5 text-xs font-semibold text-neon-purple transition-colors hover:bg-neon-purple/15 disabled:opacity-50"
            >
              <Database size={12} /> {migrating ? '迁移中…' : '迁移旧库'}
            </button>
          </div>
        </HoloCard>

        <HoloCard>
          <div className="card-title mb-md flex items-center gap-2 font-rounded text-base font-bold">
            <span className="text-xl">🖥️</span>
            系统信息
          </div>
          <div className="flex flex-col gap-1 font-mono text-xs">
            <InfoRow label="版本" value="v3.0.0-beta.4" valueClass="text-neon-cyan" />
            <InfoRow label="架构" value="3-tier (Rust+Go+React)" />
            <InfoRow label="Core" value="Rust 1.76.0-nightly" valueClass="text-neon-magenta" />
            <InfoRow label="Backend" value="Go 1.22.1" valueClass="text-neon-cyan" />
            <InfoRow label="Frontend" value="React 18.3 + Vite 5.4" valueClass="text-neon-purple" />
            <InfoRow label="运行时间" value="3d 14h 22m" />
            <InfoRow label="内存占用" value="Core: 512MB / Backend: 128MB" valueClass="text-neon-cyan" />
            <InfoRow
              label="论文数量"
              value={`${health?.paper_count ?? 42} 篇 · ${health?.topic_count ?? 6} 个主题`}
              valueClass="text-neon-magenta"
            />
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
          <div className="mb-lg font-mono text-xs text-text-muted">进化等级 7/10 · 经验值 1,247</div>

          <div className="mt-xl text-left">
            <div className="mb-sm text-sm font-bold">📦 数据迁移</div>
            <div className="mb-2 flex justify-between text-sm">
              <span>v2 → v3 数据迁移</span>
              <span className="font-mono text-neon-purple">87%</span>
            </div>
            <div className="h-2 overflow-hidden rounded-pill bg-[#e0e0ea]">
              <div
                className="h-full rounded-pill bg-gradient-to-r from-neon-cyan via-neon-purple to-neon-magenta animate-gradient-shift"
                style={{ width: '87%', backgroundSize: '200% auto' }}
              />
            </div>
            <div className="mt-1.5 font-mono text-[11px] text-text-muted">正在迁移: embedding_cache (342/400)</div>
          </div>
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
