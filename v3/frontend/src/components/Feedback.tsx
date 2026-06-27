// 加载占位组件。
export function Loading({ label = '加载中…' }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 p-4 text-sm text-brand-700">
      <span className="h-2 w-2 animate-pulse rounded-full bg-brand-500" />
      <span>{label}</span>
    </div>
  )
}

// 空状态占位。
export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 p-8 text-center text-brand-700">
      <p className="text-sm font-medium">{title}</p>
      {hint ? <p className="text-xs text-brand-700/70">{hint}</p> : null}
    </div>
  )
}

// 错误展示。
export function ErrorBox({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      {message}
    </div>
  )
}
