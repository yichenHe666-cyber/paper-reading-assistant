import type { ReactNode } from 'react'

interface HoloCardProps {
  children: ReactNode
  className?: string
}

export function HoloCard({ children, className }: HoloCardProps) {
  return <div className={`holo-card ${className ?? ''}`}>{children}</div>
}
