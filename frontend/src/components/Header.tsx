import { useEffect, useState } from 'react'
import { formatClock, formatDate } from '../lib/format'

export function Header() {
  const [now, setNow] = useState(() => new Date())

  useEffect(() => {
    const update = () => setNow(new Date())
    const delay = 60_000 - (Date.now() % 60_000)
    let interval: number | undefined
    const timeout = window.setTimeout(() => {
      update()
      interval = window.setInterval(update, 60_000)
    }, delay)
    return () => {
      window.clearTimeout(timeout)
      if (interval !== undefined) window.clearInterval(interval)
    }
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
