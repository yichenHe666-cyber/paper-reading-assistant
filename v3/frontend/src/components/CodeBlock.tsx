import type { ReactNode } from 'react'

interface CodeBlockProps {
  children: ReactNode
  language?: string
  className?: string
}

export function CodeBlock({ children, language = 'text', className }: CodeBlockProps) {
  return (
    <pre className={`my-3 overflow-hidden rounded-sm border border-neon-purple/15 bg-bg-card shadow-md ${className ?? ''}`}>
      <div className="code-block-header">
        <div className="flex gap-1">
          <span className="h-2 w-2 rounded-full bg-red-400" />
          <span className="h-2 w-2 rounded-full bg-yellow-400" />
          <span className="h-2 w-2 rounded-full bg-green-400" />
        </div>
        <span className="lang-label">{language}</span>
      </div>
      <code className="block overflow-x-auto whitespace-pre px-4 py-3.5 font-mono text-sm text-text-primary tab-2">
        {children}
      </code>
    </pre>
  )
}
