import { useEffect, useMemo, useState } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchWeeklyReview, runWeeklyReview } from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import { doneMarkLabel } from '../lib/workoutMatch'
import { PageSkeleton } from '../components/PageSkeleton'
import '../workout.css'

function mondayOf(day = new Date()) {
  const stamp = day.toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
  const date = new Date(`${stamp}T12:00:00+09:00`)
  const offset = (date.getUTCDay() + 6) % 7
  date.setUTCDate(date.getUTCDate() - offset)
  return date.toISOString().slice(0, 10)
}

function weekFromPath() {
  const match = window.location.pathname.match(/^\/weekly\/(\d{4}-\d{2}-\d{2})/)
  return match?.[1] ?? mondayOf()
}

export function WeeklyReviewPage() {
  const [weekStart, setWeekStart] = useState(weekFromPath)
  const reviewQueryKey = useMemo(() => ['weekly-review', weekStart] as const, [weekStart])
  const { data: review, error, setData: setReview } = useLiveResource(
    (signal) => fetchWeeklyReview(weekStart, signal),
    { queryKey: reviewQueryKey },
  )
  const [pending, setPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = 'Weekly review · Chili'
    return () => document.documentElement.classList.remove('is-workout')
  }, [])

  const heading = useMemo(() => {
    const date = new Date(`${weekStart}T12:00:00+09:00`)
    return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long' }).format(date)
  }, [weekStart])

  const run = () => {
    setPending(true)
    void runWeeklyReview(weekStart)
      .then((next) => setReview(next))
      .catch(() => setActionError('Could not run weekly analysis.'))
      .finally(() => setPending(false))
  }

  const shift = (days: number) => {
    const date = new Date(`${weekStart}T12:00:00+09:00`)
    date.setUTCDate(date.getUTCDate() + days)
    const next = date.toISOString().slice(0, 10)
    setWeekStart(next)
    window.history.replaceState(null, '', `/weekly/${next}`)
  }

  if (!review && !error) return <PageSkeleton />

  return (
    <div className="workout-page">
      <header className="workout-top">
        <span className="workout-brand">
          <img src={chiliLogo} alt="" />
          Chili
        </span>
        <a className="workout-back" href="/workout">Today</a>
      </header>
      <section className="workout-hero">
        <p>Weekly training review</p>
        <h1>Week of {heading}</h1>
        <span>Planned vs actual. Next week’s load is capped.</span>
      </section>
      <div className="workout-status-row">
        <button type="button" onClick={() => shift(-7)}>Previous</button>
        <button type="button" onClick={() => shift(7)}>Next</button>
      </div>
      {(error || actionError) && <p className="workout-status">{actionError ?? error}</p>}
      {review && (
        <>
          <section className="workout-section">
            <h2>Workload</h2>
            <ul className="weekly-stats">
              {['bjj', 'strength', 'zone_2', 'grip'].map((key) => (
                <li key={key}>
                  <strong>{key.replace('_', ' ')}</strong>
                  <span>{review.completed[key] ?? 0} / {review.planned[key] ?? 0}</span>
                </li>
              ))}
              <li>
                <strong>Average RPE</strong>
                <span>{review.average_rpe ?? '—'}</span>
              </li>
            </ul>
          </section>
          <section className="workout-section">
            <h2>Sessions</h2>
            <div className="workout-checks">
              {review.sessions.map((item) => (
                <a key={item.id} className="workout-plan-link" href={`/workout/${item.id}`}>
                  <strong>{item.title}</strong>
                  <span>{item.status}{item.miss_reason ? ` · ${item.miss_reason}` : ''}{doneMarkLabel(item.status) ? ` · ${doneMarkLabel(item.status)}` : ''}</span>
                </a>
              ))}
              {!review.sessions.length && <p className="workout-empty">No sessions this week.</p>}
            </div>
          </section>
          <section className="workout-section">
            <h2>Trends</h2>
            <ul className="weekly-stats">
              <li><strong>RPE trend</strong><span>{review.trends?.rpe ?? '—'}</span></li>
              <li><strong>Average RPE</strong><span>{review.trends?.average_rpe ?? review.average_rpe ?? '—'}</span></li>
              <li><strong>Strength load next week</strong><span>{Math.round((Number(review.trends?.strength_load_delta ?? review.adaptation.strength_load_delta) || 0) * 100)}%</span></li>
              <li><strong>Strength volume next week</strong><span>{String(review.trends?.strength_volume_delta ?? review.adaptation.strength_volume_delta ?? 0)}</span></li>
            </ul>
          </section>
          <section className="workout-section">
            <h2>Recovery</h2>
            <p className="workout-advice">{review.recovery?.notes ?? 'No extra recovery flags from logged sessions.'}</p>
            <ul className="weekly-stats">
              <li><strong>Latest fatigue</strong><span>{review.recovery?.fatigue ?? '—'}</span></li>
              <li><strong>Latest soreness</strong><span>{review.recovery?.soreness ?? '—'}</span></li>
            </ul>
          </section>
          <section className="workout-section">
            <h2>What changes next week</h2>
            <p className="workout-advice">{review.what_changes}</p>
            <ul className="weekly-stats">
              <li><strong>Strength load</strong><span>{Math.round((Number(review.adaptation.strength_load_delta) || 0) * 100)}%</span></li>
              <li><strong>Strength volume</strong><span>{String(review.adaptation.strength_volume_delta ?? 0)}</span></li>
              <li><strong>Zone 2 minutes</strong><span>{String(review.adaptation.zone2_minutes_delta ?? 0)}</span></li>
              <li><strong>Grip sets</strong><span>{String(review.adaptation.grip_sets_delta ?? 0)}</span></li>
            </ul>
            <button type="button" disabled={pending} onClick={run}>
              {pending ? 'Saving…' : 'Confirm review and rebuild next week'}
            </button>
          </section>
        </>
      )}
    </div>
  )
}
