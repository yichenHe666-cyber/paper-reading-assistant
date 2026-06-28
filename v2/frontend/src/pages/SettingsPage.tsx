// 设置页：健康检查 + 技能管理。
//
// 痛点②验收可视点：health.data_dir 显示绝对路径，启动自检一目了然。
// 痛点③修复：技能 CRUD 走结构化 JSON，错误信息走 toast。
import { useEffect, useState } from 'react'
import { Activity, Sparkles, Trash2, Wand2 } from 'lucide-react'
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
    <div className="h-full overflow-y-auto px-4 py-4">
      <div className="mx-auto flex max-w-3xl flex-col gap-4">
        {/* 健康检查 */}
        <section className="rounded-lg border border-brand-100 bg-white p-4">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <Activity size={16} /> 健康检查
          </h2>
          {healthLoading ? (
            <Loading label="检查中…" />
          ) : healthError ? (
            <ErrorBox message={healthError} />
          ) : health ? (
            <dl className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
              <DescRow label="状态" value={health.status} />
              <DescRow label="LLM" value={`${health.llm_provider}/${health.llm_model}`} />
              <DescRow label="论文数" value={String(health.paper_count)} />
              <DescRow label="主题数" value={String(health.topic_count)} />
              <DescRow label="数据目录" value={health.data_dir} mono />
              <DescRow label="数据库" value={health.db_path} mono />
            </dl>
          ) : null}
          <div className="mt-3 flex gap-2">
            <button
              type="button"
              onClick={loadHealth}
              className="rounded bg-brand-100 px-3 py-1 text-xs text-brand-700 hover:bg-brand-200"
            >
              重新检查
            </button>
          </div>
        </section>

        {/* 技能管理 */}
        <section className="rounded-lg border border-brand-100 bg-white p-4">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <Sparkles size={16} /> 技能管理
            </h2>
            <button
              type="button"
              onClick={loadSkills}
              className="rounded bg-brand-100 px-2 py-1 text-xs text-brand-700 hover:bg-brand-200"
            >
              刷新
            </button>
          </div>
          {skillsLoading ? (
            <Loading label="加载技能…" />
          ) : skills.length === 0 ? (
            <EmptyState title="暂无技能" hint="对话后自动进化或手动添加" />
          ) : (
            <ul className="flex flex-col gap-2">
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
        </section>

        {/* 自进化提示 */}
        <section className="rounded-lg border border-brand-100 bg-brand-50 p-4 text-sm text-brand-700">
          <div className="flex items-start gap-2">
            <Wand2 size={16} className="mt-0.5 shrink-0" />
            <div>
              <p className="font-medium">自进化提示</p>
              <p className="mt-1 text-xs leading-relaxed">
                完成一段对话后，系统会自动评估是否提炼新技能。也可在对话页右上角手动触发「提炼此会话」。
              </p>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}

function DescRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <>
      <dt className="text-xs text-brand-700/70">{label}</dt>
      <dd className={`text-sm ${mono ? 'font-mono' : ''} break-all`}>{value}</dd>
    </>
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
    <li className="flex items-start justify-between gap-2 rounded border border-brand-100 p-2">
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{skill.name}</span>
          <code className="rounded bg-brand-100 px-1 text-xs">{skill.slug}</code>
          <span
            className={`rounded px-1.5 text-xs ${
              skill.enabled ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'
            }`}
          >
            {skill.enabled ? '启用' : '停用'}
          </span>
        </div>
        <p className="mt-0.5 text-xs text-brand-700/80">
          {skill.description || '无描述'}
        </p>
        <p className="mt-1 text-xs text-brand-700/60">
          用 {skill.usage_count} 次 · 成功率 {(skill.success_rate * 100).toFixed(0)}% · v
          {skill.version}
        </p>
      </div>
      <div className="flex shrink-0 gap-1">
        <button
          type="button"
          onClick={onToggle}
          className="rounded bg-brand-100 px-2 py-1 text-xs text-brand-700 hover:bg-brand-200"
        >
          {skill.enabled ? '停用' : '启用'}
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="rounded bg-red-100 px-2 py-1 text-xs text-red-700 hover:bg-red-200"
          aria-label="删除"
        >
          <Trash2 size={12} />
        </button>
      </div>
    </li>
  )
}
