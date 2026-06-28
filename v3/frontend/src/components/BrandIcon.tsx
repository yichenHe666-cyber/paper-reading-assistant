interface BrandIconProps {
  size?: 'sm' | 'md' | 'lg' | 'avatar'
  img?: string
  alt?: string
  className?: string
}

export function BrandIcon({ size = 'md', img, alt, className }: BrandIconProps) {
  if (img) {
    return <img src={img} alt={alt ?? 'avatar'} className={`brand-icon--avatar-img ${className ?? ''}`} />
  }
  return <span className={`brand-icon brand-icon--${size} ${className ?? ''}`}>🐂</span>
}
