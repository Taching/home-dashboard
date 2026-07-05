import type { WalkingPadToday } from '../types'

type Props = {
  walkingPad: WalkingPadToday
}

function WalkIcon() {
  return (
    <svg className="walking-pad-badge-icon" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="8.5" cy="5.5" r="2.1" fill="currentColor" />
      <path
        fill="currentColor"
        d="M11.2 9.1 9.4 13.2l1.8 1.1-.7 2.4 2.6-.2.9-3.1-2.4-1.5.9-2.8z"
      />
      <path
        fill="currentColor"
        d="M14.8 8.2c.8-.3 1.7.1 2 1l1.4 4.2-2.1 1.2-.9-2.7-1.8 3.1-2.4-1.4 2.5-4.4z"
        opacity=".88"
      />
    </svg>
  )
}

export function WalkingPadBadge({ walkingPad }: Props) {
  if (walkingPad.status === 'not_configured') return null

  const minutes = Math.round(walkingPad.total_minutes)
  const distance = walkingPad.total_distance_km.toFixed(1)
  const minuteProgress = Math.min(100, (walkingPad.total_minutes / walkingPad.goal_minutes) * 100)
  const isWalking = walkingPad.status === 'walking'
  const isUnavailable = walkingPad.status === 'unavailable'

  const meta = isUnavailable
    ? 'Pad offline'
    : isWalking
      ? `${distance} km · in progress`
      : `${distance} / ${walkingPad.goal_distance_km} km · ${Math.round(minuteProgress)}%`

  return (
    <div
      className={[
        'walking-pad-badge',
        `is-${walkingPad.status}`,
        walkingPad.goal_met ? 'is-goal-met' : '',
      ].filter(Boolean).join(' ')}
      aria-label={
        isUnavailable
          ? 'Walking pad offline'
          : `Walking today: ${minutes} of ${walkingPad.goal_minutes} minutes, ${distance} kilometers`
      }
    >
      <div className="walking-pad-badge-head">
        <WalkIcon />
        <span className="walking-pad-badge-label">Walk</span>
      </div>
      <div className="walking-pad-badge-stat">
        <strong>
          {minutes}
          <small> / {walkingPad.goal_minutes} min</small>
        </strong>
      </div>
      <span className="walking-pad-badge-meta">{meta}</span>
      <span className="walking-pad-badge-progress" aria-hidden="true">
        <span className="walking-pad-badge-progress-fill" style={{ width: `${minuteProgress}%` }} />
      </span>
    </div>
  )
}
