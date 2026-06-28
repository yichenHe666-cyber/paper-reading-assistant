import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react'

interface NeonInputProps extends InputHTMLAttributes<HTMLInputElement> {}

export function NeonInput({ className, ...props }: NeonInputProps) {
  return <input className={`neon-input ${className ?? ''}`} {...props} />
}

interface NeonTextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {}

export function NeonTextarea({ className, ...props }: NeonTextareaProps) {
  return <textarea className={`neon-input ${className ?? ''}`} {...props} />
}
