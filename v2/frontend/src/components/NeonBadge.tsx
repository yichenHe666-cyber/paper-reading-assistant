import type { ReactNode } from 'react'

interface NeonBadgeProps {
  children: ReactNode
  color?: 'cyan' | 'magenta' | 'yellow' | 'purple' | 'green'
  className?: string
}

export function NeonBadge({ children, color = 'cyan', className }: NeonBadgeProps) {
  return <span className={`neon-badge neon-badge--${color} ${className ?? ''}`}>{children}</span>
}
