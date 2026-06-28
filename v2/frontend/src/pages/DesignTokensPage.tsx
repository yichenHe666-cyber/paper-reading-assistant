import { HoloCard } from '@/components/HoloCard'
import { NeonBadge } from '@/components/NeonBadge'
import { NeonButton } from '@/components/NeonButton'
import { NeonInput } from '@/components/NeonInput'
import { NeonToggle } from '@/components/NeonToggle'
import { TerminalCard } from '@/components/TerminalCard'
import { BrandIcon } from '@/components/BrandIcon'

const biliDanmakus = [
  { name: '鎏金', class: 'bili-liujin', code: '#ff9a56 → #ffd96a → #ffb347' },
  { name: '炫酷粉蓝', class: 'bili-pinkblue', code: '#ff6eb4 → #6eb5ff → #ff85c0' },
  { name: '星穹蓝', class: 'bili-xingqiong', code: '#1e3a6e → #4a8eff → #2860b8' },
  { name: '幻紫', class: 'bili-huanzi', code: '#a855f7 → #ec4899 → #c084fc' },
  { name: '冰晶', class: 'bili-bingjing', code: '#00d4ff → #7c3aed → #00bfff' },
  { name: '热情', class: 'bili-rengong', code: '#ff6b6b → #ffa07a → #ff4500' },
]

const neonColors = [
  { name: 'neon-cyan', hex: '#4ecdc4', glow: 'glow-cyan' },
  { name: 'neon-magenta', hex: '#ff2d95', glow: 'glow-magenta' },
  { name: 'neon-yellow', hex: '#ffe033', glow: 'glow-yellow' },
  { name: 'neon-purple', hex: '#b44dff', glow: 'glow-purple' },
  { name: 'neon-green', hex: '#39ff14', glow: 'glow-green' },
]

const baseColors = [
  { name: 'bg-primary', hex: '#f8f9fc', border: '#e0e0ea' },
  { name: 'bg-secondary', hex: '#ffffff', border: '#e0e0ea' },
  { name: 'text-primary', hex: '#1a1a2e', border: '#2a2a4e' },
  { name: 'text-secondary', hex: '#5a5a7a', border: '#6a6a8a' },
]

const typeScale = [
  { sample: '标题 H1', font: 'font-rounded', size: 'text-[42px]', weight: 'font-extrabold', family: 'var(--font-rounded)', meta: 'font-size: 42px / font-weight: 800 / line-height: 1.2' },
  { sample: '标题 H2', font: 'font-rounded', size: 'text-[28px]', weight: 'font-bold', family: 'var(--font-rounded)', meta: 'font-size: 28px / font-weight: 700' },
  { sample: '正文 Body', font: 'font-body', size: 'text-lg', weight: 'font-normal', family: 'var(--font-body)', meta: 'font-size: 18px / line-height: 1.7' },
  { sample: 'const x = 42;', font: 'font-mono', size: 'text-sm', weight: 'font-normal', family: 'var(--font-mono)', meta: 'font-size: 14px / font-family: mono', color: 'text-neon-cyan' },
  { sample: 'meta.caption', font: 'font-mono', size: 'text-xs', weight: 'font-normal', family: 'var(--font-mono)', meta: 'font-size: 12px / color: muted', color: 'text-text-muted' },
]

export default function DesignTokensPage() {
  return (
    <section className="page-section">
      <div className="section-label">// design.system</div>
      <h2 className="section-title">设计规范</h2>
      <p className="section-desc">Cyberpunk × Anime 风格设计系统。所有设计 token 均以 CSS 自定义属性定义，确保全局一致性与主题切换能力。</p>

      <div className="grid grid-cols-1 gap-2xl lg:grid-cols-2">
        <HoloCard>
          <div className="block-title mb-lg flex items-center gap-2 font-rounded text-lg font-bold">
            🎬 B站大会员专属弹幕色系
          </div>
          <p className="mb-lg text-sm text-text-secondary">
            复刻自哔哩哔哩大会员专属渐变弹幕配色，流光动画模拟弹幕滚动效果。每色均可用于标题、品牌、强调文字。
          </p>
          <div className="grid grid-cols-3 gap-md">
            {biliDanmakus.map((d) => (
              <div key={d.name} className="flex flex-col items-center gap-sm rounded-md bg-[#0d0d1a] p-lg text-center">
                <div
                  className={`bili-danmaku-preview font-rounded text-xl font-extrabold whitespace-nowrap gradient-text ${d.class}`}
                  style={{ backgroundSize: '300% 100%' }}
                >
                  {d.name}弹幕效果
                </div>
                <div className="flex flex-col items-center gap-0.5">
                  <span className="text-sm font-semibold text-white">{d.name}</span>
                  <code className="text-[10px] text-white/50">{d.code}</code>
                </div>
              </div>
            ))}
          </div>

          <div className="mt-xl">
            <div className="component-group-label mb-2 font-mono text-[11px] uppercase tracking-widest text-text-muted">弹幕流光模拟</div>
            <div className="relative h-[200px] overflow-hidden rounded-md" style={{ background: 'linear-gradient(180deg, #0d0d1a 0%, #1a1a2e 100%)' }}>
              {[
                { text: '这个配色也太绝了吧！', class: 'bili-liujin', top: '18%', duration: '8s', delay: '0.5s' },
                { text: '前方高能预警！', class: 'bili-pinkblue', top: '34%', duration: '10s', delay: '2s' },
                { text: '核动力科研牛马启动！', class: 'bili-huanzi', top: '50%', duration: '7s', delay: '0.5s' },
                { text: '论文精读YYDS', class: 'bili-xingqiong', top: '66%', duration: '9s', delay: '3s' },
                { text: '感谢大佬开源！', class: 'bili-rengong', top: '82%', duration: '6s', delay: '1s' },
              ].map((dm) => (
                <div
                  key={dm.text}
                  className="absolute left-full whitespace-nowrap"
                  style={{ top: dm.top, animation: `dmScrollLeft ${dm.duration} linear infinite`, animationDelay: dm.delay }}
                >
                  <span
                    className={`gradient-text font-rounded text-base font-bold ${dm.class}`}
                    style={{ backgroundSize: '300% 100%' }}
                  >
                    {dm.text}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </HoloCard>

        <HoloCard>
          <div className="block-title mb-lg flex items-center gap-2 font-rounded text-lg font-bold">
            🎨 霓虹色彩系统
          </div>
          <div className="grid grid-cols-5 gap-sm">
            {neonColors.map((c) => (
              <div key={c.name} className="flex flex-col items-center gap-1.5">
                <div
                  className={`aspect-square w-full rounded-md border-2 border-white/60 transition-transform hover:scale-105`}
                  style={{ background: c.hex, boxShadow: `0 0 20px ${c.hex}80` }}
                />
                <div className="font-mono text-[11px] font-semibold text-text-secondary">{c.hex}</div>
                <div className="text-center font-mono text-[10px] text-text-muted">{c.name}</div>
              </div>
            ))}
          </div>

          <div className="mt-xl">
            <div className="component-group-label mb-2 font-mono text-[11px] uppercase tracking-widest text-text-muted">Base Colors</div>
            <div className="grid grid-cols-4 gap-sm">
              {baseColors.map((c) => (
                <div key={c.name} className="flex flex-col items-center gap-1.5">
                  <div
                    className="aspect-square w-full rounded-md border-2"
                    style={{ background: c.hex, borderColor: c.border }}
                  />
                  <div className="font-mono text-[11px] font-semibold text-text-secondary">{c.hex}</div>
                  <div className="text-center font-mono text-[10px] text-text-muted">{c.name}</div>
                </div>
              ))}
            </div>
          </div>
        </HoloCard>

        <HoloCard>
          <div className="block-title mb-lg flex items-center gap-2 font-rounded text-lg font-bold">
            ✏️ 字体排版系统
          </div>
          <div className="flex flex-col gap-md">
            {typeScale.map((t) => (
              <div key={t.sample} className="flex items-baseline gap-md border-b border-black/6 pb-md last:border-b-0 last:pb-0">
                <div className={`min-w-[180px] shrink-0 ${t.font} ${t.size} ${t.weight} leading-tight ${t.color ?? ''}`}>
                  {t.sample}
                </div>
                <div className="font-mono text-[11px] leading-relaxed text-text-muted">
                  <span className="block">{t.meta}</span>
                  <span className="block">font-family: {t.family}</span>
                </div>
              </div>
            ))}
          </div>
        </HoloCard>

        <HoloCard>
          <div className="block-title mb-lg flex items-center gap-2 font-rounded text-lg font-bold">
            🧩 组件示例
          </div>
          <div className="flex flex-col gap-lg">
            <div>
              <div className="component-group-label mb-2 font-mono text-[11px] uppercase tracking-widest text-text-muted">Buttons</div>
              <div className="flex flex-wrap gap-sm">
                <NeonButton>主要操作</NeonButton>
                <NeonButton variant="magenta">次要操作</NeonButton>
                <button className="neon-btn rounded-pill border-2 border-neon-purple bg-gradient-to-br from-neon-purple/10 to-neon-magenta/5 px-6 py-2.5 font-rounded text-sm font-bold text-neon-purple transition-all hover:bg-neon-purple/20">
                  紫色变体
                </button>
              </div>
            </div>

            <div>
              <div className="component-group-label mb-2 font-mono text-[11px] uppercase tracking-widest text-text-muted">Badges / Tags</div>
              <div className="flex flex-wrap gap-sm">
                <NeonBadge color="cyan">✓ 在线</NeonBadge>
                <NeonBadge color="magenta">🔧 工具调用</NeonBadge>
                <NeonBadge color="yellow">⚠ 警告</NeonBadge>
                <NeonBadge color="purple">★ 推荐</NeonBadge>
                <NeonBadge color="green">● 健康</NeonBadge>
              </div>
            </div>

            <div>
              <div className="component-group-label mb-2 font-mono text-[11px] uppercase tracking-widest text-text-muted">Inputs</div>
              <div className="flex flex-col gap-2">
                <NeonInput placeholder="默认输入框..." />
                <NeonInput defaultValue="已聚焦状态示例" className="border-neon-cyan shadow-[0_0_0_4px_rgba(78,205,196,0.08),var(--glow-cyan)]" />
              </div>
            </div>

            <div>
              <div className="component-group-label mb-2 font-mono text-[11px] uppercase tracking-widest text-text-muted">Toggles</div>
              <div className="flex gap-4">
                <NeonToggle checked={true} onChange={() => {}} />
                <NeonToggle checked={false} onChange={() => {}} />
              </div>
            </div>

            <div className="w-full">
              <div className="component-group-label mb-2 font-mono text-[11px] uppercase tracking-widest text-text-muted">Terminal Block</div>
              <TerminalCard className="text-xs">
                <span className="keyword">{'{'}</span>
                {'\n'}  <span className="string">"model"</span>: <span className="string">"niuma-v3"</span>,
                {'\n'}  <span className="string">"max_tokens"</span>: <span className="flag">4096</span>,
                {'\n'}  <span className="string">"temperature"</span>: <span className="flag">0.7</span>,
                {'\n'}  <span className="string">"skills"</span>: [<span className="string">"search"</span>, <span className="string">"read"</span>, <span className="string">"summarize"</span>],
                {'\n'}  <span className="string">"evolution"</span>: {'{'} <span className="string">"enabled"</span>: <span className="flag">true</span>, <span className="string">"level"</span>: <span className="flag">7</span> {'}'}
                {'\n'}<span className="keyword">{'}'}</span>
              </TerminalCard>
            </div>
          </div>
        </HoloCard>

        <HoloCard>
          <div className="block-title mb-lg flex items-center gap-2 font-rounded text-lg font-bold">
            ✨ 动画效果
          </div>
          <div className="grid grid-cols-3 gap-md">
            <div className="text-center p-lg">
              <div className="mx-auto mb-md h-[60px] w-[60px] rounded-md bg-gradient-to-br from-neon-cyan to-neon-purple animate-neon-pulse" />
              <div className="font-mono text-xs text-text-muted">neonPulse</div>
              <div className="text-[11px] text-text-muted">霓虹脉冲辉光效果</div>
            </div>
            <div className="text-center p-lg">
              <div
                className="mx-auto mb-md h-[60px] w-full rounded-md animate-holo-shimmer"
                style={{
                  background: 'linear-gradient(135deg, rgba(78,205,196,0.22), rgba(180,77,255,0.3), rgba(255,45,149,0.3), rgba(255,224,51,0.3), rgba(78,205,196,0.22))',
                  backgroundSize: '400% 400%',
                }}
              />
              <div className="font-mono text-xs text-text-muted">holoShimmer</div>
              <div className="text-[11px] text-text-muted">全息渐变闪光</div>
            </div>
            <div className="text-center p-lg">
              <div className="mx-auto mb-md flex h-[60px] w-[60px] items-center justify-center text-[28px] text-neon-yellow animate-twinkle">✦</div>
              <div className="font-mono text-xs text-text-muted">twinkle</div>
              <div className="text-[11px] text-text-muted">闪烁/星光效果</div>
            </div>
            <div className="text-center p-lg">
              <BrandIcon size="md" className="mx-auto mb-md" />
              <div className="font-mono text-xs text-text-muted">floatUp</div>
              <div className="text-[11px] text-text-muted">悬浮动画</div>
            </div>
            <div className="text-center p-lg">
              <div className="mx-auto mb-md h-[60px] w-full rounded-md border-2 border-transparent bg-bg-card animate-border-glow" />
              <div className="font-mono text-xs text-text-muted">borderGlow</div>
              <div className="text-[11px] text-text-muted">边框颜色渐变</div>
            </div>
            <div className="text-center p-lg">
              <div
                className="mx-auto mb-md h-[60px] w-full rounded-md animate-gradient-shift"
                style={{
                  background: 'linear-gradient(90deg, var(--neon-cyan), var(--neon-purple), var(--neon-magenta), var(--neon-yellow), var(--neon-cyan))',
                  backgroundSize: '300% auto',
                }}
              />
              <div className="font-mono text-xs text-text-muted">gradientShift</div>
              <div className="text-[11px] text-text-muted">渐变位移动画</div>
            </div>
          </div>
        </HoloCard>
      </div>

      <style>{`
        @keyframes dmScrollLeft {
          0% { transform: translateX(0); }
          100% { transform: translateX(calc(-100% - 100vw)); }
        }
        .bili-liujin {
          background-image: linear-gradient(90deg, #ff9a56, #ffd96a, #ffb347, #ffcf7d, #f0a030, #ff9a56);
        }
        .bili-pinkblue {
          background-image: linear-gradient(90deg, #ff6eb4, #6eb5ff, #ff85c0, #5eaeff, #ff6eb4);
        }
        .bili-xingqiong {
          background-image: linear-gradient(90deg, #1e3a6e, #4a8eff, #2860b8, #6eaaff, #1e3a6e);
        }
        .bili-huanzi {
          background-image: linear-gradient(90deg, #a855f7, #ec4899, #c084fc, #f472b6, #a855f7);
        }
        .bili-bingjing {
          background-image: linear-gradient(90deg, #00d4ff, #7c3aed, #00bfff, #8b5cf6, #00d4ff);
        }
        .bili-rengong {
          background-image: linear-gradient(90deg, #ff6b6b, #ffa07a, #ff4500, #ff8c69, #ff6b6b);
        }
        .bili-danmaku-preview {
          animation: biliDanmakuFlow 6s linear infinite;
        }
      `}</style>
    </section>
  )
}
