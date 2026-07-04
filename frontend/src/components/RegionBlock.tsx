type Props = {
  label: string
  children: React.ReactNode
  className?: string
}

export function RegionBlock({ label, children, className = '' }: Props) {
  return (
    <section className={`region-block${className ? ` ${className}` : ''}`}>
      <p className="region-block-label">{label}</p>
      {children}
    </section>
  )
}
