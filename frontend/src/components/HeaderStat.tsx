import type { ReactNode } from 'react'

export type HeaderStatTone = 'sober' | 'bjj' | 'strength' | 'weight' | 'walk' | 'weather' | 'clock'

type HeaderStatProps = {
  label: string
  value: ReactNode
  unit?: string
  hint?: string
  tone?: HeaderStatTone
  stale?: boolean
  live?: boolean
  description: string
}

export function HeaderStat({
  label,
  value,
  unit,
  hint,
  tone = 'clock',
  stale = false,
  live = false,
  description,
}: HeaderStatProps) {
  return (
    <div
      className={`header-stat is-${tone}${stale ? ' is-stale' : ''}${live ? ' is-live' : ''}`}
      aria-label={description}
    >
      <span className="header-stat-label">{label}</span>
      <strong className="header-stat-value">
        <span className="header-stat-number">{value}</span>
        {unit ? <small>{unit}</small> : null}
      </strong>
      <span className="header-stat-hint">{hint || '\u00a0'}</span>
    </div>
  )
}
