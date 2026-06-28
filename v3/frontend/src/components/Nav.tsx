import { NavLink } from 'react-router-dom'
import { Home, MessageSquare, Library, Settings, Palette } from 'lucide-react'
import { BrandIcon } from './BrandIcon'

const links = [
  { to: '/', icon: Home, label: '首页' },
  { to: '/chat', icon: MessageSquare, label: '对话' },
  { to: '/library', icon: Library, label: '论文库' },
  { to: '/settings', icon: Settings, label: '设置' },
  { to: '/design', icon: Palette, label: '设计规范' },
]

export function Nav() {
  return (
    <nav className="nav sticky top-0 z-[1000] border-b border-neon-cyan/25 bg-white/88 px-2xl backdrop-blur-xl saturate-180 animate-border-glow">
      <div className="mx-auto flex h-16 max-w-[1400px] items-center justify-between">
        <NavLink to="/" className="nav-brand flex items-center gap-sm font-rounded text-lg font-extrabold">
          <BrandIcon size="sm" />
          <span className="gradient-text gradient-text-stroke animate-bili-danmaku-flow text-bili-pinkblue">
            核动力科研牛马
          </span>
        </NavLink>
        <ul className="flex gap-xs">
          {links.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.to === '/'}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 rounded-pill px-4 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-neon-cyan/10 text-neon-cyan shadow-[inset_0_0_0_1px_rgba(78,205,196,0.25)] animate-neon-pulse'
                      : 'text-text-secondary hover:bg-neon-cyan/8 hover:text-text-primary'
                  }`
                }
              >
                <link.icon size={16} className="nav-icon" />
                <span>{link.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  )
}
