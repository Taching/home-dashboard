import type { WalkingPadToday } from '../types'

type Props = {
  walkingPad: WalkingPadToday
}

function formatGoalClock(minutes: number) {
  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60
  return `${hours}:${String(mins).padStart(2, '0')}`
}

function formatSteps(steps: number) {
  return steps.toLocaleString('en-US')
}

export function WalkingPadBadge({ walkingPad }: Props) {
  if (walkingPad.status === 'not_configured') return null

  const minutes = Math.round(walkingPad.total_minutes)
  const distance = walkingPad.total_distance_km.toFixed(1)
  const steps = walkingPad.total_steps
  const goalClock = formatGoalClock(walkingPad.goal_minutes)
  const isWalking = walkingPad.status === 'walking'

  return (
    <div
      className={[
        'environment-badge',
        'walking-pad-badge',
        isWalking ? 'is-walking' : '',
        walkingPad.goal_met ? 'is-goal-met' : '',
      ].filter(Boolean).join(' ')}
      aria-label={`Walking today: ${minutes} of ${walkingPad.goal_minutes} minutes, ${distance} kilometers, ${steps} steps`}
    >
      <span className="environment-badge-label">Walk</span>
      <strong>
        {minutes}
        <small>min/{goalClock}</small>
      </strong>
      <span>
        {distance} km · {formatSteps(steps)} steps
      </span>
    </div>
  )
}
