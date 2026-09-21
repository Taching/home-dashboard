import { useEffect, useMemo, useState, type FormEvent } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchTrainingOverview, requestScheduleChange } from '../lib/api'
import { AlertIcon } from '../components/icons'
import { localDateKey, timeLabel, typeTitle } from '../components/TrainingPlanner'
import { useLiveResource } from '../hooks/useLiveResource'
import type { PlanAdjustment, TrainingSession } from '../types'
import '../workout.css'

function todayStamp() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
}

function ThisWeek() {
  const queryKey = useMemo(() => ['training-overview'] as const, [])
  const { data: training } = useLiveResource((signal) => fetchTrainingOverview(signal), { queryKey })
  if (!training) return null

  const sessions = [training.today, training.tomorrow, ...(training.week ?? []), ...(training.upcoming ?? [])]
    .filter((item): item is TrainingSession => Boolean(item))
  const flags = training.day_flags ?? {}
  const todayKey = localDateKey(new Date())
  const start = new Date(`${todayKey}T00:00:00+09:00`)

  const days = Array.from({ length: 7 }, (_, index) => {
    const day = new Date(start)
    day.setDate(day.getDate() + index)
    const key = localDateKey(day)
    const session = sessions.find((item) => item.start_at && localDateKey(new Date(item.start_at)) === key)
    return { day, key, session, dayFlags: flags[key] ?? [] }
  })

  return (
    <section className="workout-section replan-week">
      <h2>This week</h2>
      <div className="replan-week-list">
        {days.map(({ day, key, session, dayFlags }) => {
          const closed = dayFlags.includes('HOLIDAY') || dayFlags.includes('CLOSED')
          const unavailable = dayFlags.includes('UNAVAILABLE')
          const what = session
            ? typeTitle(session.planned_type)
            : unavailable ? 'Away' : closed ? 'Gym closed' : dayFlags.includes('NO_CLASS') ? 'No BJJ class' : 'Open'
          return (
            <div key={key} className={`replan-week-row${key === todayKey ? ' is-today' : ''}`}>
              <span className="replan-week-date">
                {new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: 'Asia/Tokyo' }).format(day)} {Number(key.slice(-2))}
              </span>
              <span className="replan-week-what">
                {what}
                {session && !session.is_all_day && session.start_at ? ` · ${timeLabel(session.start_at)}` : ''}
              </span>
              {session && session.status !== 'planned' && (
                <span className={`replan-week-status is-${session.status}`}>{session.status}</span>
              )}
            </div>
          )
        })}
      </div>
    </section>
  )
}

type Phase = 'idle' | 'sent' | 'done' | 'error'

export function ScheduleChangePage() {
  const [instruction, setInstruction] = useState('')
  const [phase, setPhase] = useState<Phase>('idle')
  const [sentText, setSentText] = useState('')
  const [decision, setDecision] = useState<PlanAdjustment | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = 'Change my schedule · Chili'
    return () => document.documentElement.classList.remove('is-workout')
  }, [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const text = instruction.trim()
    if (phase === 'sent' || !text) return

    // Optimistic: acknowledge the send immediately, reconcile with the real
    // result (success or failure) once the request comes back.
    setSentText(text)
    setInstruction('')
    setDecision(null)
    setError(null)
    setPhase('sent')

    void requestScheduleChange(text)
      .then((response) => {
        setDecision(response.decision)
        setPhase('done')
      })
      .catch((err: Error) => {
        setError(err.message || 'Could not understand that. Try rephrasing.')
        setInstruction(text)
        setPhase('error')
      })
  }

  const busy = phase === 'sent'

  return (
    <div className="workout-page">
      <header className="workout-top">
        <span className="workout-brand">
          <img src={chiliLogo} alt="" />
          Chili
        </span>
        <a className="workout-back" href={`/daily/${todayStamp()}`}>Daily</a>
      </header>
      <section className="workout-hero">
        <p>Something changed</p>
        <h1>Change my schedule</h1>
        <span>Storm, sick, emergency — tell Chili what happened and it will replan.</span>
      </section>
      <ThisWeek />
      <section className="workout-section">
        <form className="workout-form" onSubmit={submit}>
          <label className="workout-field">
            <span>What's going on?</span>
            <textarea
              value={instruction}
              onChange={(event) => setInstruction(event.target.value)}
              disabled={busy}
              maxLength={2000}
              placeholder="e.g. there's a storm today, I'm sick, emergency — need to move things"
            />
          </label>
          <button type="submit" disabled={busy || !instruction.trim()}>
            {busy ? 'Sending…' : 'Change my schedule'}
          </button>
        </form>
      </section>
      {(phase === 'sent' || phase === 'done') && (
        <section className="workout-section workout-chili replan-result">
          <div className="replan-result-head">
            <span className={`daily-verify is-${phase === 'done' ? 'ok' : 'wait'}`}>
              {phase === 'done' ? 'Plan adjusted' : 'Sending…'}
            </span>
          </div>
          <p className="workout-note">“{sentText}”</p>
          {phase === 'done' && decision && (
            <div className="daily-plan-change">
              <strong>How</strong>
              <ul>{decision.how.map((line) => <li key={line}>{line}</li>)}</ul>
              <strong>Why</strong>
              <ul>{decision.why.map((line) => <li key={line}>{line}</li>)}</ul>
            </div>
          )}
        </section>
      )}
      {phase === 'error' && (
        <section className="workout-section replan-error" role="alert">
          <p className="replan-error-head"><AlertIcon size={16} /> Couldn't understand that</p>
          <p className="workout-status is-error">{error}</p>
        </section>
      )}
    </div>
  )
}
