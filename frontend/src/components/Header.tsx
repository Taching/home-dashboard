import chiliLogo from '../assets/chili-logo.svg'
import { ChiliNotificationBanner } from './ChiliNotificationBanner'
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
  const latestCheckIn = wellbeing.latest_checkin_date
    ? new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
      .format(new Date(`${wellbeing.latest_checkin_date}T00:00:00Z`))
    : null
  const checkInHint = wellbeing.checkin_stale
    ? (latestCheckIn ? `Last ${latestCheckIn}` : 'Check-in missing')
    : 'Current streak'
  const bjj = training.compliance.bjj ?? { completed: wellbeing.jiujitsu_this_week, target: wellbeing.jiujitsu_weekly_goal }
  const strength = training.compliance.strength ?? { completed: wellbeing.gym_this_week, target: 2 }
  const currentWeight = training.readiness?.weight_kg ?? wellbeing.current_weight_kg
  const averageWeight = training.trends.weight_7d_average
  return (
    <header className={`dashboard-header${showNotification ? ' has-notification' : ''}`}>
      <div className="brand-cluster">
        <a
          className="brand-mark"
          href="/"
          aria-label="Chili dashboard"
        >
          <img src={chiliLogo} alt="" className="brand-logo" />
        </a>
      </div>
      <div className="header-meta">
        <div className={`environment-badge wellbeing-badge is-sober${wellbeing.checkin_stale ? ' is-stale' : ''}`} aria-label={`${wellbeing.sober_days} sober days in the current streak. ${checkInHint}`}>
          <span className="environment-badge-label">Sober</span>
          <strong><span>{wellbeing.sober_days}</span><small>days</small></strong>
          <span>{checkInHint}</span>
        </div>
        <div
          className={`wellbeing-badge training-badge is-workout${wellbeing.checkin_stale ? ' is-stale' : ''}`}
          aria-label={`${bjj.completed} of ${bjj.target} BJJ sessions and ${strength.completed} of ${strength.target} strength sessions this week.`}
        >
          <span className="environment-badge-label">Weekly training</span>
          <div className="training-goals">
            <strong><span>{bjj.completed}</span><small>/{bjj.target} BJJ</small></strong>
            <strong><span>{strength.completed}</span><small>/{strength.target} Str</small></strong>
          </div>
          <span>{training.phase.startsWith('taper') ? 'Taper · less is right' : 'Mon–Sun'}</span>
        </div>
        <div className="environment-badge wellbeing-badge weight-badge" aria-label={`Current weight ${currentWeight ?? 'not recorded'} kilograms. Seven-day average ${averageWeight ?? 'not available'} kilograms.`}>
          <span className="environment-badge-label">Weight</span>
          <strong><span>{currentWeight?.toFixed(1) ?? '—'}</span><small>kg</small></strong>
          <span>{averageWeight === null ? '7d avg —' : `7d avg ${averageWeight.toFixed(1)}`}</span>
        </div>
        <WalkingPadBadge walkingPad={walkingPad} />
        <WeatherWidget forecast={weather} />
        <time className="clock" dateTime={now.toISOString()}>
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
