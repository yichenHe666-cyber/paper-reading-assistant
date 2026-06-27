// Toast 通知组件。
//
// 痛点③修复要点：
//   - 通知文本走 JSX {message}，React 自动转义，杜绝 HTML 注入；
//   - 不依赖任何 CDN 弹窗库，纯本地实现。
import { CheckCircle2, Info, XCircle, X } from 'lucide-react'
import { useUIStore, type Toast } from '@/stores/ui'

export function ToastViewport() {
  const toasts = useUIStore((s) => s.toasts)
  const dismiss = useUIStore((s) => s.dismissToast)
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2">
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} onDismiss={() => dismiss(t.id)} />
      ))}
    </div>
  )
}

function ToastCard({ toast, onDismiss }: { toast: Toast; onDismiss: () => void }) {
  const Icon = toast.kind === 'success' ? CheckCircle2 : toast.kind === 'error' ? XCircle : Info
  const tone =
    toast.kind === 'success'
      ? 'border-green-200 bg-green-50 text-green-800'
      : toast.kind === 'error'
        ? 'border-red-200 bg-red-50 text-red-800'
        : 'border-brand-100 bg-white text-brand-900'
  return (
    <div
      role="alert"
      className={`pointer-events-auto flex max-w-sm items-start gap-2 rounded-lg border px-3 py-2 shadow-md ${tone}`}
    >
      <Icon size={16} className="mt-0.5 shrink-0" />
      <div className="flex-1 text-sm leading-snug">{toast.message}</div>
      <button
        type="button"
        onClick={onDismiss}
        className="shrink-0 rounded p-0.5 hover:bg-black/5"
        aria-label="关闭"
      >
        <X size={14} />
      </button>
    </div>
  )
}
