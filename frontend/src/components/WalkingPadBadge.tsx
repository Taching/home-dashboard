import { HeaderStat } from './HeaderStat'
import type { WalkingPadToday } from '../types'

function formatSteps(value: number) {
  return new Intl.NumberFormat('en-US').format(value)
}

export function WalkingPadBadge({ walkingPad }: { walkingPad: WalkingPadToday }) {
  if (walkingPad.status === 'not_configured') return null

  const steps = walkingPad.total_steps
  const goal = walkingPad.goal_steps || 10_000
  const isWalking = walkingPad.status === 'walking'
  const hint = walkingPad.goal_met ? 'Goal met' : `of ${formatSteps(goal)}`

  return (
    <HeaderStat
      label="Walk"
      value={formatSteps(steps)}
      unit="steps"
      hint={hint}
      tone="walk"
      live={isWalking}
      description={`Walked ${formatSteps(steps)} of ${formatSteps(goal)} steps.`}
    />
  )
}
