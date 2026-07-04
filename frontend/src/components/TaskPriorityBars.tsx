type PriorityLevel = 'urgent' | 'high' | 'medium' | 'low'

const SLOT_COUNT = 4

function priorityLevel(priority: string | null): PriorityLevel | null {
  const value = priority?.toLowerCase() ?? ''
  if (value.includes('urgent')) return 'urgent'
  if (value.includes('high')) return 'high'
  if (value.includes('medium') || value.includes('normal')) return 'medium'
  if (value.includes('low')) return 'low'
  return null
}

function filledCount(level: PriorityLevel) {
  if (level === 'low') return 1
  if (level === 'medium') return 2
  if (level === 'high') return 3
  return 4
}

export function TaskPriorityBars({ priority }: { priority: string | null }) {
  const level = priorityLevel(priority)
  if (!level) return null

  const active = filledCount(level)
  return (
    <span
      className={`priority-meter is-${level}`}
      title={priority ?? undefined}
      aria-label={priority ?? undefined}
    >
      {Array.from({ length: SLOT_COUNT }, (_, index) => (
        <i key={index} className={index < active ? 'is-filled' : 'is-empty'} />
      ))}
    </span>
  )
}
