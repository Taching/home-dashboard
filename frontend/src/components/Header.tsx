import { useEffect, useState } from 'react'
import { formatClock, formatDate } from '../lib/format'

export function Header() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const interval = window.setInterval(() => setNow(new Date()), 1_000)
    return () => window.clearInterval(interval)
  }, [])

  return (
    <header className="dashboard-header">
      <div className="brand-block">
        <p className="brand">Chili</p>
        <p className="voice-state"><span aria-hidden="true" />Voice offline</p>
      </div>
      <time className="clock" dateTime={now.toISOString()}>
        <strong>{formatClock(now)}</strong>
        <span>{formatDate(now)}</span>
      </time>
    </header>
  )
}
