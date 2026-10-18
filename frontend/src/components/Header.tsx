import chiliLogo from '../assets/chili-logo.svg'
import { ChiliNotificationBanner } from './ChiliNotificationBanner'
import { HeaderStat } from './HeaderStat'
import { WalkingPadBadge } from './WalkingPadBadge'
import { WeatherWidget } from './WeatherWidget'
import { useClock } from '../hooks/useClock'
import { formatClock, formatDate } from '../lib/format'
import type { ChiliNotification } from '../lib/chiliNotifications'
import type { TrainingOverview, WalkingPadToday, WeatherForecast, WellbeingSummary } from '../types'

type HeaderProps = {
  weather: WeatherForecast
  walkingPad: WalkingPadToday
  wellbeing: WellbeingSummary
  notification: ChiliNotification | null
  notificationExiting?: boolean
  training: TrainingOverview
}

export function Header({
  weather,
  walkingPad,
  wellbeing,
  notification,
  notificationExiting = false,
  training,
}: HeaderProps) {
  const now = useClock()
  const showNotification = Boolean(notification)
  const soberHint = 'Streak'
  const bjjDone = wellbeing.jiujitsu_this_week
  const strengthDone = wellbeing.gym_this_week
  const bjjTarget = wellbeing.jiujitsu_weekly_goal
  const strengthTarget = wellbeing.gym_weekly_goal
  const weekHint = training.phase.startsWith('taper') ? 'Taper week' : 'This week'
  // The cut is judged only from the seven-day average; today's scale number is noise.
  const averageWeight = wellbeing.weight_7d_average_kg ?? training.trends.weight_7d_average
  const currentWeight = averageWeight ?? training.readiness?.weight_kg ?? wellbeing.current_weight_kg
  const weightTarget = wellbeing.weight_target_kg
  const weightHint = weightTarget != null
    ? `7d · aim ${weightTarget.toFixed(1)}`
    : averageWeight != null ? '7d avg' : `Goal ${wellbeing.weight_goal_kg}`
  // Last night from the Garmin watch; hidden until it has synced.
  const sleep = wellbeing.watch
  const sleepHint = sleep?.hrv_status
    ? `HRV ${sleep.hrv_status}`
    : sleep?.sleep_score != null ? `Score ${sleep.sleep_score}` : 'Last night'

  return (
    <header className={`dashboard-header${showNotification ? ' has-notification' : ''}`}>
      <a className="brand-mark" href="/" aria-label="Chili dashboard">
        <img src={chiliLogo} alt="" className="brand-logo" />
      </a>
      <div className="header-meta">
        <HeaderStat
          label="Sober"
          value={wellbeing.sober_days}
          unit="days"
          hint={soberHint}
          tone="sober"
          description={`${wellbeing.sober_days} sober days.`}
        />
        <HeaderStat
          label="BJJ"
          value={bjjDone}
          unit={`/ ${bjjTarget}`}
          hint={weekHint}
          tone="bjj"
          description={`${bjjDone} of ${bjjTarget} BJJ sessions this week.`}
        />
        <HeaderStat
          label="Strength"
          value={strengthDone}
          unit={`/ ${strengthTarget}`}
          hint={weekHint}
          tone="strength"
          description={`${strengthDone} of ${strengthTarget} strength sessions this week.`}
        />
        <HeaderStat
          label="Weight"
          value={currentWeight == null ? '—' : currentWeight.toFixed(1)}
          unit={currentWeight == null ? undefined : 'kg'}
          hint={weightHint}
          tone="weight"
          description={`Weight ${currentWeight ?? 'not recorded'} kilograms. ${weightHint}.`}
        />
        {sleep && (
          <HeaderStat
            label="Sleep"
            value={sleep.sleep_hours.toFixed(1)}
            unit="h"
            hint={sleepHint}
            tone="sleep"
            description={`Slept ${sleep.sleep_hours.toFixed(1)} hours last night. ${sleepHint}.`}
          />
        )}
        <WalkingPadBadge walkingPad={walkingPad} />
        <WeatherWidget forecast={weather} />
        <time className="header-clock" dateTime={now.toISOString()}>
          <strong>{formatClock(now)}</strong>
          <span>{formatDate(now)}</span>
        </time>
      </div>
      {showNotification && (
        <div className="header-notification-slot">
          <ChiliNotificationBanner notification={notification} exiting={notificationExiting} />
        </div>
      )}
    </header>
  )
}
