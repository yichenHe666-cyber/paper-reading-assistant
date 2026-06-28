import { useEffect } from 'react'
import { Route, Routes } from 'react-router-dom'
import { useChatStore } from '@/stores/chat'
import { useLibraryStore } from '@/stores/library'
import { Nav } from '@/components/Nav'
import { Particles } from '@/components/Particles'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ToastViewport } from '@/components/Toast'
import HeroPage from '@/pages/HeroPage'
import ChatPage from '@/pages/ChatPage'
import LibraryPage from '@/pages/LibraryPage'
import SettingsPage from '@/pages/SettingsPage'
import DesignTokensPage from '@/pages/DesignTokensPage'

export default function App() {
  const loadSessions = useChatStore((s) => s.loadSessions)
  const loadSources = useLibraryStore((s) => s.loadSources)

  useEffect(() => {
    void loadSessions().catch(() => {})
    void loadSources().catch(() => {})
  }, [loadSessions, loadSources])

  return (
    <div className="relative min-h-screen bg-bg-primary font-body text-text-primary">
      <Particles />
      <Nav />
      <main className="relative z-10">
        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<HeroPage />} />
            <Route path="/chat" element={<ChatPage />} />
            <Route path="/chat/:sessionId" element={<ChatPage />} />
            <Route path="/library" element={<LibraryPage />} />
            <Route path="/library/:sourceId" element={<LibraryPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/design" element={<DesignTokensPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </main>
      <ToastViewport />
    </div>
  )
}

function NotFound() {
  return (
    <div className="page-section flex min-h-[60vh] flex-col items-center justify-center text-center">
      <h2 className="section-title">404</h2>
      <p className="section-desc">页面不存在，请从导航选择功能。</p>
    </div>
  )
}
