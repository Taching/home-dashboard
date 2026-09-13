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
  const currentWeight = training.readiness?.weight_kg ?? wellbeing.current_weight_kg
  const averageWeight = training.trends.weight_7d_average
  const weightHint = averageWeight != null
    ? `7d ${averageWeight.toFixed(1)}`
    : `Goal ${wellbeing.weight_goal_kg}`

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
