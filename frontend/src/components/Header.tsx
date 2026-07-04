import { useEffect, useState } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { formatClock, formatDate } from '../lib/format'
import { fetchVoiceStatus } from '../lib/api'
import type { VoiceState, VoiceStatus } from '../types'

const voiceLabels: Record<VoiceState, string> = {
  offline: 'Voice offline',
  idle: 'Say Hey Chili',
  listening: 'Listening…',
  thinking: 'Thinking…',
  complete: 'Done',
  error: 'Try again',
}

function sameVoiceStatus(first: VoiceStatus, second: VoiceStatus) {
  return first.state === second.state
    && first.updated_at === second.updated_at
    && first.transcript === second.transcript
    && first.message === second.message
}

export function Header() {
  const [now, setNow] = useState(() => new Date())
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>({ state: 'offline', updated_at: null, transcript: null, message: null })

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 1_000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const applyVoiceStatus = (next: VoiceStatus) => {
      setVoiceStatus((current) => sameVoiceStatus(current, next) ? current : next)
    }
    const refreshVoice = () => void fetchVoiceStatus()
      .then(applyVoiceStatus)
      .catch(() => applyVoiceStatus({ state: 'offline', updated_at: null, transcript: null, message: null }))
    refreshVoice()
    const pollMs = voiceStatus.state === 'idle' || voiceStatus.state === 'offline' ? 1_000 : 300
    const interval = window.setInterval(refreshVoice, pollMs)
    return () => window.clearInterval(interval)
  }, [voiceStatus.state])

  return (
    <header className="dashboard-header">
      <div className="brand-block">
        <a className="brand-mark" href="/" aria-label="Chili">
          <img src={chiliLogo} alt="" className="brand-logo" />
        </a>
        <div className={`voice-indicator is-${voiceStatus.state}`} aria-live="polite">
          <p className="voice-state">
            <span className="voice-orb" aria-hidden="true"><i /><i /><i /></span>
            {voiceLabels[voiceStatus.state]}
          </p>
          {voiceStatus.transcript && <p className="voice-transcript">“{voiceStatus.transcript}”</p>}
          {voiceStatus.message && <p className="voice-message">{voiceStatus.message}</p>}
        </div>
      </div>
      <time className="clock" dateTime={now.toISOString()}>
        <strong>{formatClock(now)}</strong>
        <span>{formatDate(now)}</span>
      </time>
    </header>
  )
}
