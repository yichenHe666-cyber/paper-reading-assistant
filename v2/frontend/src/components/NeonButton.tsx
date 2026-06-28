import type { ReactNode, ButtonHTMLAttributes } from 'react'
import { SparkleIcon } from './SparkleIcon'

interface NeonButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  children: ReactNode
  variant?: 'cyan' | 'magenta'
  showSparkle?: boolean
}

export function NeonButton({ children, variant = 'cyan', showSparkle = true, className, ...props }: NeonButtonProps) {
  return (
    <button className={`neon-btn ${variant === 'magenta' ? 'neon-btn--magenta' : ''} ${className ?? ''}`} {...props}>
      {showSparkle && <SparkleIcon />}
      {children}
    </button>
  )
}
