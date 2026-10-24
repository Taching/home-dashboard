import { useEffect, useMemo, useState } from 'react'
import { fetchLiftHistory } from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import { PageSkeleton } from '../components/PageSkeleton'
import { PhoneChrome } from '../components/PhoneChrome'
import { PhoneNav } from '../components/PhoneNav'
import { StarIcon } from '../components/icons'
import type { Lift, LiftSession } from '../types'
import '../workout.css'

const DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'Asia/Tokyo' })

function dayLabel(stamp: string) {
  return DAY.format(new Date(`${stamp}T12:00:00+09:00`))
}

function kg(value: number) {
  return Number.isInteger(value) ? `${value}` : value.toFixed(1)
}

function loadLabel(load: number | null, unit: string | null) {
  if (load == null) return 'Bodyweight'
  const suffix = unit && unit !== 'kg' ? ` ${unit}` : ' kg'
  return `${kg(load)}${suffix}`
}

function setLine(session: LiftSession) {
  const reps = session.reps.length ? session.reps.join('·') : '—'
  return session.load == null ? `${reps} reps` : `${loadLabel(session.load, session.unit)} × ${reps}`
}

/** One series, so no legend: the card title names it. Last point carries the marker. */
function Sparkline({ sessions }: { sessions: LiftSession[] }) {
  const points = sessions.filter((item) => item.e1rm != null && !item.deload)
  if (points.length < 2) return null
  const values = points.map((item) => item.e1rm as number)
  const low = Math.min(...values)
  const high = Math.max(...values)
  const span = Math.max(high - low, 1)
  const width = 120
  const height = 36
  const coords = points.map((_, index) => {
    const x = (index / (points.length - 1)) * (width - 6) + 3
    const y = height - 4 - (((values[index] - low) / span) * (height - 8))
    return [x, y] as const
  })
  const [lastX, lastY] = coords[coords.length - 1]
  return (
    <svg className="lift-spark" viewBox={`0 0 ${width} ${height}`} aria-hidden="true">
      <polyline points={coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')} />
      <circle cx={lastX} cy={lastY} r="3" />
    </svg>
  )
}

function LiftCard({ lift }: { lift: Lift }) {
  const [open, setOpen] = useState(false)
  const latest = lift.sessions[lift.sessions.length - 1]
  const target = lift.next_target
  const targetLabel = target && target.load != null ? loadLabel(target.load, target.unit) : null
  return (
    <li className={`lift-card${open ? ' is-open' : ''}`}>
      <button type="button" className="lift-head" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        <span className="lift-title">
          <strong>{lift.name}</strong>
          <small>
            {dayLabel(latest.date)} · {setLine(latest)}
            {latest.rpe != null ? ` · RPE ${latest.rpe}` : ''}
          </small>
        </span>
        <span className="lift-figure">
          {lift.best_e1rm != null ? (
            <>
              <strong>{kg(lift.best_e1rm)}</strong>
              <small>est. 1RM</small>
            </>
          ) : (
            <small>{latest.top_reps != null ? `${latest.top_reps} reps` : '—'}</small>
          )}
        </span>
      </button>
      <div className="lift-meta">
        <Sparkline sessions={lift.sessions} />
        {latest.is_pr && (
          <span className="lift-pr"><StarIcon size={12} /> PR {dayLabel(latest.date)}</span>
        )}
        {targetLabel && <span className="lift-next">Next {targetLabel}</span>}
      </div>
      {open && (
        <table className="lift-table">
          <thead>
            <tr><th scope="col">Day</th><th scope="col">Sets</th><th scope="col">RPE</th><th scope="col">1RM</th></tr>
          </thead>
          <tbody>
            {[...lift.sessions].reverse().map((item) => (
              <tr key={item.session_id} className={item.is_pr ? 'is-pr' : undefined}>
                <td><a href={`/workout/${item.session_id}`}>{dayLabel(item.date)}</a></td>
                <td>{setLine(item)}{item.deload ? ' · deload' : ''}</td>
                <td>{item.rpe ?? '—'}</td>
                <td>
                  {item.e1rm != null ? kg(item.e1rm) : '—'}
                  {item.is_pr && <span className="lift-pr-dot" aria-label="Personal record"><StarIcon size={11} /></span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </li>
  )
}

export function LiftHistoryPage() {
  const queryKey = useMemo(() => ['lift-history'] as const, [])
  const { data, error } = useLiveResource((signal) => fetchLiftHistory(signal), { queryKey, intervalMs: null })

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = 'Lift history · Chili'
    return () => document.documentElement.classList.remove('is-workout')
  }, [])

  if (!data && !error) return <PageSkeleton />

  const lifts = data?.lifts ?? []
  const prs = lifts.reduce((sum, lift) => sum + lift.pr_count, 0)

  return (
    <div className="workout-page">
      <PhoneChrome />
      <section className="workout-hero">
        <p>Train</p>
        <h1>Lift history</h1>
        <span>
          {lifts.length
            ? `${lifts.length} lifts · ${prs} PR${prs === 1 ? '' : 's'}. 1RM is estimated from your best set.`
            : error ? '' : 'Log a strength session and each lift shows up here.'}
        </span>
      </section>
      {error && <p className="workout-status is-error">Could not load lift history. Reload the page to try again.</p>}
      {lifts.length > 0 && (
        <ul className="lift-list">
          {lifts.map((lift) => <LiftCard key={lift.name} lift={lift} />)}
        </ul>
      )}
      <PhoneNav />
    </div>
  )
}
