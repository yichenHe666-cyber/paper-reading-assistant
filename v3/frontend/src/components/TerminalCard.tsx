import type { ReactNode } from 'react'

interface TerminalCardProps {
  children: ReactNode
  title?: string
  className?: string
}

export function TerminalCard({ children, title = 'terminal', className }: TerminalCardProps) {
  return (
    <div className={`terminal-card ${className ?? ''}`}>
      <div className="terminal-header">
        <span className="terminal-dot terminal-dot--red" />
        <span className="terminal-dot terminal-dot--yellow" />
        <span className="terminal-dot terminal-dot--green" />
        <span className="terminal-title">{title}</span>
      </div>
      <div className="terminal-body">{children}</div>
    </div>
  )
}
