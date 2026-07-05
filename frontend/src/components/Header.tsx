import chiliLogo from '../assets/chili-logo.svg'
import { EnvironmentBadge } from './EnvironmentBadge'
import { WeatherWidget } from './WeatherWidget'
import { useClock } from '../hooks/useClock'
import { formatClock, formatDate } from '../lib/format'
import type { VoiceStatus, WeatherForecast } from '../types'
import { voiceLabels } from './VoicePipelinePanel'

type HeaderProps = {
  voiceStatus: VoiceStatus
  temperature: number | null
  humidity: number | null
  weather: WeatherForecast
}

export function Header({ voiceStatus, temperature, humidity, weather }: HeaderProps) {
  const now = useClock()

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
        <span className={`voice-status-chip is-${voiceStatus.state}`}>{voiceLabels[voiceStatus.state]}</span>
      </div>
      <div className="header-meta">
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
