// 应用根组件 + 路由 + 布局。
//
// 痛点③修复要点：
//   - 路由用 react-router，URL 是真相源，刷新可恢复（取代散落的 session_state）；
//   - 侧边栏导航固定，主区域按路由切换；
//   - 用 lucide-react 本地图标，杜绝运行时 CDN 依赖导致方框。
import { useEffect } from 'react'
import { NavLink, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { BookOpen, MessageSquare, Settings, Library } from 'lucide-react'
import { useChatStore } from '@/stores/chat'
import { useLibraryStore } from '@/stores/library'
import { ToastViewport } from '@/components/Toast'
import ChatPage from '@/pages/ChatPage'
import LibraryPage from '@/pages/LibraryPage'
import SettingsPage from '@/pages/SettingsPage'

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const loadSessions = useChatStore((s) => s.loadSessions)
  const loadTopics = useLibraryStore((s) => s.loadTopics)

  // 首次挂载预加载会话与主题列表
  useEffect(() => {
    void loadSessions().catch(() => {
      /* 后端未起时静默，UI 显示空状态 */
    })
    void loadTopics().catch(() => {})
  }, [loadSessions, loadTopics])

  // 路由变化时不做事；具体页内 useEffect 处理 query param
  useEffect(() => {
    // 占位：保留 hook 以便未来扩展（如埋点）
    void location
    void navigate
  }, [location, navigate])

  return (
    <div className="flex h-screen flex-col md:flex-row">
      <aside className="flex shrink-0 flex-col border-r border-brand-100 bg-white md:w-56">
        <div className="flex items-center gap-2 border-b border-brand-100 px-4 py-3">
          <span className="text-lg">🐂</span>
          <h1 className="text-sm font-semibold text-brand-900">核动力科研牛马</h1>
        </div>
        <nav className="flex flex-1 flex-col gap-1 p-2">
          <NavItem to="/chat" icon={<MessageSquare size={16} />} label="对话" />
          <NavItem to="/library" icon={<Library size={16} />} label="论文库" />
          <NavItem to="/settings" icon={<Settings size={16} />} label="设置" />
        </nav>
        <div className="border-t border-brand-100 p-2 text-xs text-brand-700">
          <a
            href="https://github.com/pwl/papers"
            target="_blank"
            rel="noreferrer noopener"
            className="flex items-center gap-1 hover:text-brand-500"
          >
            <BookOpen size={12} /> Papers We Love
          </a>
        </div>
      </aside>

      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<ChatPage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/chat/:sessionId" element={<ChatPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/library/:topicId" element={<LibraryPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="*" element={<ChatPage />} />
        </Routes>
      </main>

      <ToastViewport />
    </div>
  )
}

interface NavItemProps {
  to: string
  icon: React.ReactNode
  label: string
}

function NavItem({ to, icon, label }: NavItemProps) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `flex items-center gap-2 rounded px-3 py-2 text-sm transition-colors ${
          isActive ? 'bg-brand-500 text-white' : 'text-brand-700 hover:bg-brand-100'
        }`
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  )
}
