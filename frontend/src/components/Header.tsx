import { useEffect, useState } from 'react'
import { formatClock, formatDate } from '../lib/format'
import { fetchVoiceStatus } from '../lib/api'
import type { VoiceState, VoiceStatus } from '../types'

const voiceLabels: Record<VoiceState, string> = {
  offline: 'Voice offline',
  idle: 'Say Hey Jarvis',
  listening: 'Listening…',
  thinking: 'Thinking…',
  complete: 'Done',
  error: 'Try again',
}

export function Header() {
  const [now, setNow] = useState(() => new Date())
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus>({ state: 'offline', updated_at: null, transcript: null, message: null })

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 1_000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    const refreshVoice = () => void fetchVoiceStatus().then(setVoiceStatus).catch(() => setVoiceStatus({ state: 'offline', updated_at: null, transcript: null, message: null }))
    refreshVoice()
    const interval = window.setInterval(refreshVoice, 500)
    return () => window.clearInterval(interval)
  }, [])

  return (
    <header className="dashboard-header">
      <div className="brand-block">
        <p className="brand">Chili</p>
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
