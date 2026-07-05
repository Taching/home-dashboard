import chiliLogo from '../assets/chili-logo.svg'
import { ChiliNotificationBanner } from './ChiliNotificationBanner'
import { EnvironmentBadge } from './EnvironmentBadge'
import { WalkingPadBadge } from './WalkingPadBadge'
import { WeatherWidget } from './WeatherWidget'
import { useClock } from '../hooks/useClock'
import { formatClock, formatDate } from '../lib/format'
import type { ChiliNotification } from '../lib/chiliNotifications'
import type { VoiceStatus, WalkingPadToday, WeatherForecast } from '../types'
import { voiceLabels } from './VoicePipelinePanel'

type HeaderProps = {
  voiceStatus: VoiceStatus
  temperature: number | null
  humidity: number | null
  weather: WeatherForecast
  walkingPad: WalkingPadToday
  notification: ChiliNotification | null
  notificationExiting?: boolean
}

export function Header({
  voiceStatus,
  temperature,
  humidity,
  weather,
  walkingPad,
  notification,
  notificationExiting = false,
}: HeaderProps) {
  const now = useClock()
  const showNotification = Boolean(notification)

  return (
    <header className="dashboard-header">
      <div className="brand-cluster">
        <a
          className={`brand-mark is-voice-${voiceStatus.state}`}
          href="/"
          aria-label={`Chili · ${voiceLabels[voiceStatus.state]}`}
        >
          <img src={chiliLogo} alt="" className="brand-logo" />
          <span className="sr-only">{voiceLabels[voiceStatus.state]}</span>
        </a>
        {showNotification ? (
          <ChiliNotificationBanner notification={notification} exiting={notificationExiting} />
        ) : (
          <span className={`voice-status-chip is-${voiceStatus.state}`}>{voiceLabels[voiceStatus.state]}</span>
        )}
      </div>
      <div className="header-meta">
        <WalkingPadBadge walkingPad={walkingPad} />
        <EnvironmentBadge temperature={temperature} humidity={humidity} />
        <WeatherWidget forecast={weather} />
        <time className="clock" dateTime={now.toISOString()}>
          <strong>{formatClock(now)}</strong>
          <span>{formatDate(now)}</span>
        </time>
      </div>
    </header>
  )
}
