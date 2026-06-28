interface NeonToggleProps {
  checked: boolean
  onChange: (checked: boolean) => void
  className?: string
}

export function NeonToggle({ checked, onChange, className }: NeonToggleProps) {
  return (
    <label className={`neon-toggle ${className ?? ''}`}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="slider" />
    </label>
  )
}
