import { Link } from 'react-router-dom'
import { BrandIcon } from '@/components/BrandIcon'
import { HoloCard } from '@/components/HoloCard'
import { TerminalCard } from '@/components/TerminalCard'
import { NeonButton } from '@/components/NeonButton'

const quickStarts = [
  {
    step: '1',
    color: 'cyan',
    title: '启动 Core (Rust)',
    body: `<span class="prompt">$</span> <span class="cmd">cd</span> core && <span class="cmd">cargo</span> <span class="flag">run</span> <span class="flag">--release</span>
<span class="comment"># Core engine started on :8081</span>
<span class="comment"># ✓ NLP pipeline ready</span>
<span class="comment"># ✓ Embedding model loaded</span>`,
  },
  {
    step: '2',
    color: 'magenta',
    title: '启动 Backend (Go)',
    body: `<span class="prompt">$</span> <span class="cmd">cd</span> backend && <span class="cmd">go</span> <span class="flag">run</span> <span class="flag">main.go</span>
<span class="comment"># Server started on :8080</span>
<span class="comment"># ✓ Connected to Core gRPC</span>
<span class="comment"># ✓ Database migration complete</span>`,
  },
  {
    step: '3',
    color: 'purple',
    title: '启动 Frontend (React)',
    body: `<span class="prompt">$</span> <span class="cmd">cd</span> frontend && <span class="cmd">pnpm</span> <span class="flag">dev</span>
<span class="comment"># VITE v5.4 ready in 320ms</span>
<span class="comment"># ➜ Local: http://localhost:5173</span>
<span class="comment"># ✓ API proxy → :8080</span>`,
  },
]

const architecture = [
  { icon: '⚛️', name: 'Frontend', tech: 'React 18 + TypeScript' },
  { icon: '🔧', name: 'Backend', tech: 'Go + Gin' },
  { icon: '⚡', name: 'Core', tech: 'Rust + PyO3' },
]

export default function HeroPage() {
  return (
    <section className="page-section hero relative overflow-hidden text-center">
      <div
        className="hero-bg-gradient pointer-events-none absolute left-1/2 top-1/2 -z-10 h-[600px] w-[800px] -translate-x-1/2 -translate-y-1/2"
        style={{
          background: 'radial-gradient(ellipse at center, rgba(78,205,196,0.15) 0%, rgba(180,77,255,0.1) 40%, rgba(255,45,149,0.08) 70%, transparent 100%)',
          filter: 'blur(60px)',
        }}
      />

      <BrandIcon size="lg" className="mx-auto mb-lg" />

      <h1 className="hero-title mx-auto mb-md max-w-4xl font-rounded text-[56px] font-black leading-tight">
        <span className="gradient-text gradient-text-stroke animate-bili-danmaku-flow text-bili-pinkblue">
          核动力科研牛马
        </span>
        <span className="hero-version ml-2 inline-block rounded-pill px-3.5 py-1 font-mono text-base font-bold text-white">
          v3.0
        </span>
      </h1>

      <p className="hero-tagline mx-auto mb-2xl max-w-2xl text-lg text-text-secondary">
        <strong className="text-text-primary">学术论文精读工具</strong> — Go + Rust + TypeScript 多语言架构
        <br />
        前端 React 18 + Vite 5 · 状态管理 Zustand · 样式 TailwindCSS
      </p>

      <div className="mb-2xl flex justify-center gap-4">
        <Link to="/chat">
          <NeonButton>开始对话</NeonButton>
        </Link>
        <Link to="/library">
          <NeonButton variant="magenta">浏览论文库</NeonButton>
        </Link>
      </div>

      <div className="mx-auto mb-2xl grid max-w-[900px] grid-cols-[1fr_auto_1fr_auto_1fr] items-center gap-md">
        {architecture.map((item) => (
          <HoloCard key={item.name} className="arch-card p-md text-center">
            <span className="mb-sm block text-[32px]">{item.icon}</span>
            <div className="font-rounded text-base font-bold">{item.name}</div>
            <div className="font-mono text-xs text-text-muted">{item.tech}</div>
          </HoloCard>
        ))}
        <div className="arch-arrow animate-neon-pulse-fast font-mono text-2xl text-neon-cyan">
          ⟷
        </div>
        <div className="arch-arrow animate-neon-pulse-fast font-mono text-2xl text-neon-cyan">
          ⟷
        </div>
      </div>

      <div className="mx-auto grid max-w-[900px] grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-lg">
        {quickStarts.map((qs) => (
          <HoloCard key={qs.step} className="quickstart-card text-left">
            <div className="mb-md flex items-center gap-2">
              <span
                className={`flex h-6 w-6 items-center justify-center rounded-full font-mono text-xs font-extrabold text-white ${
                  qs.color === 'cyan' ? 'bg-neon-cyan' : qs.color === 'magenta' ? 'bg-neon-magenta' : 'bg-neon-purple'
                }`}
              >
                {qs.step}
              </span>
              <span className="text-sm font-bold">{qs.title}</span>
            </div>
            <TerminalCard className="text-xs">
              <div dangerouslySetInnerHTML={{ __html: qs.body }} />
            </TerminalCard>
          </HoloCard>
        ))}
      </div>

      <footer className="footer relative z-10 mt-3xl border-t border-black/6 px-2xl py-3xl text-center">
        <BrandIcon size="md" className="mx-auto mb-md" />
        <p className="font-mono text-xs text-text-muted">
          <span className="footer-brand gradient-text gradient-text-stroke animate-bili-danmaku-flow text-bili-pinkblue font-rounded text-lg font-extrabold">
            核动力科研牛马 v3
          </span>
          <br />
          Crafted with <span className="inline-block text-neon-magenta animate-neon-pulse-fast">♥</span> · Cyberpunk × Anime Aesthetic
          <br />
          <span className="mt-2 inline-block">React 18 + Vite 5 + Zustand + TailwindCSS · Go + Rust + TypeScript</span>
        </p>
      </footer>
    </section>
  )
}
