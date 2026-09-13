import { FormEvent, useEffect, useState } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchDailyBriefing, logSober, logSundayReview } from '../lib/api'
import { formatDate } from '../lib/format'
import { WorkoutCheckForm } from './WorkoutApp'
import type { DailyBriefing } from '../types'
import '../workout.css'

function todayStamp() {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function dayFromPath() {
  const match = window.location.pathname.match(/^\/daily\/(\d{4}-\d{2}-\d{2})/)
  return match?.[1] ?? todayStamp()
}

function previewFromQuery() {
  return new URLSearchParams(window.location.search).get('preview') ?? undefined
}

export function DailyBriefingPage() {
  const [day] = useState(dayFromPath)
  const [preview] = useState(previewFromQuery)
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    fetchDailyBriefing(day, preview)
      .then((next) => {
        setBriefing(next)
        setError(null)
        document.title = `Daily · ${next.date}`
      })
      .catch(() => setError('Could not load today.'))
  }

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    load()
    return () => document.documentElement.classList.remove('is-workout')
  }, [day, preview])

  const headingDate = briefing ? formatDate(new Date(`${briefing.date}T12:00:00`)) : day

  return (
    <div className="workout-page">
      <header className="workout-top">
        <span className="workout-brand">
          <img src={chiliLogo} alt="" />
          Chili
        </span>
        <a className="workout-back" href="/workout">Workouts</a>
      </header>
      <section className="workout-hero">
        <p>Daily</p>
        <h1>{headingDate}</h1>
        <span>Workout after training. Sober at night.{briefing?.sunday ? ' Sunday also has weight and week review.' : ''}</span>
      </section>
      {briefing?.preview && <p className="workout-status">Preview only. Today’s saved plan is unchanged.</p>}
      {error && <p className="workout-status">{error}</p>}
      {briefing?.workouts.map((workout) => (
        <section key={workout.kind} className="workout-section">
          <h2>{workout.title}</h2>
          <p className="workout-note">{workout.summary}</p>
          {workout.status === 'logged' && (
            <p className="workout-status">
              Logged {workout.completed}
              {workout.note ? ` · ${workout.note}` : ''}
            </p>
          )}
          <WorkoutCheckForm
            kind={workout.kind}
            items={workout.exercises}
            day={briefing.date}
            onLogged={load}
          />
        </section>
      ))}
      {briefing && briefing.calendar.meetings.length > 0 && (
        <section className="workout-section">
          <h2>Meetings</h2>
          {briefing.calendar.meetings.map((meeting) => (
            <div key={`${meeting.title}-${meeting.start_at}`} className="workout-log">
              <strong>{meeting.title}</strong>
              <span>{meeting.is_all_day ? 'All day' : new Date(meeting.start_at).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}</span>
            </div>
          ))}
        </section>
      )}
      {briefing?.sunday && (
        <SundayForm briefing={briefing} onSaved={setBriefing} />
      )}
      {briefing && <SoberForm day={briefing.date} answered={briefing.sobriety.answered} days={briefing.sobriety.days} onLogged={load} />}
    </div>
  )
}

function SoberForm({
  day,
  answered,
  days,
  onLogged,
}: {
  day: string
  answered: 'yes' | 'no' | null
  days: number
  onLogged: () => void
}) {
  const [sober, setSober] = useState(answered !== 'no')
  const [note, setNote] = useState('')
  const [pending, setPending] = useState(false)
  const [status, setStatus] = useState<string | null>(answered ? `Already logged: ${answered}` : null)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setPending(true)
    void logSober(day, { sober, note: note.trim() || undefined })
      .then((result) => {
        setStatus(result.message)
        if (result.status === 'logged') {
          setNote('')
          onLogged()
        }
      })
      .catch(() => setStatus('Could not save sober check-in.'))
      .finally(() => setPending(false))
  }

  return (
    <section className="workout-section">
      <h2>Evening · Sober</h2>
      <p className="workout-note">{days} day streak so far. Answer this at night.</p>
      <form className="workout-form" onSubmit={submit}>
        <div className="workout-field">
          <span>Stayed sober?</span>
          <div className="workout-choices">
            <button type="button" className={sober ? 'is-selected' : ''} onClick={() => setSober(true)}>yes</button>
            <button type="button" className={!sober ? 'is-selected' : ''} onClick={() => setSober(false)}>no</button>
          </div>
        </div>
        <label className="workout-field">
          <span>Note</span>
          <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} />
        </label>
        <button type="submit" disabled={pending}>{pending ? 'Saving…' : 'Submit sober'}</button>
        {status && <p className="workout-status">{status}</p>}
      </form>
    </section>
  )
}

function SundayForm({
  briefing,
  onSaved,
}: {
  briefing: DailyBriefing
  onSaved: (next: DailyBriefing) => void
}) {
  const sunday = briefing.sunday
  if (!sunday) return null
  const [weight, setWeight] = useState(sunday.weight_kg?.toString() ?? '')
  const [sameAsLast, setSameAsLast] = useState(false)
  const [note, setNote] = useState(sunday.review_note ?? '')
  const [pending, setPending] = useState(false)
  const [status, setStatus] = useState<string | null>(sunday.submitted ? briefing.message ?? 'Saved this Sunday.' : null)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    setPending(true)
    void logSundayReview(briefing.date, {
      weight_kg: sameAsLast || !weight ? undefined : Number(weight),
      same_as_last: sameAsLast,
      note: note.trim() || undefined,
    })
      .then((next) => {
        onSaved(next)
        const weight = next.sunday
          ? next.sunday.delta_kg == null
            ? `Saved. Weight ${next.sunday.weight_kg?.toFixed(1)} kg.`
            : `Saved. Weight ${next.sunday.weight_kg?.toFixed(1)} kg (${next.sunday.delta_kg > 0 ? '+' : ''}${next.sunday.delta_kg.toFixed(1)} from last week).`
          : 'Saved Sunday review.'
        setStatus(next.advice || weight)
      })
      .catch(() => setStatus('Could not save Sunday review.'))
      .finally(() => setPending(false))
  }

  return (
    <section className="workout-section">
      <h2>Sunday · Weight and week</h2>
      <p className="workout-note">
        {sunday.previous_weight_kg != null
          ? `Last week: ${sunday.previous_weight_kg.toFixed(1)} kg`
          : 'No previous Sunday weight yet.'}
        {sunday.delta_kg != null && sunday.submitted
          ? ` · This week ${sunday.delta_kg === 0 ? 'unchanged' : `${sunday.delta_kg > 0 ? '+' : ''}${sunday.delta_kg.toFixed(1)} kg`}`
          : ''}
      </p>
      <div className="workout-card">
        <strong>This week</strong>
        {sunday.sessions.map((session) => (
          <div key={`${session.date}-${session.kind}`} className="workout-note">
            {session.date.slice(5)} {session.title}: {session.completed ?? 'not logged'}
            {session.note ? ` · ${session.note}` : ''}
          </div>
        ))}
      </div>
      <form className="workout-form" onSubmit={submit}>
        <label className="workout-field">
          <span>Weight kg</span>
          <input
            inputMode="decimal"
            value={weight}
            onChange={(event) => {
              setSameAsLast(false)
              setWeight(event.target.value)
            }}
            disabled={sameAsLast}
            placeholder={sunday.previous_weight_kg?.toFixed(1) ?? '82.0'}
          />
        </label>
        <label className="workout-check">
          <input
            type="checkbox"
            checked={sameAsLast}
            onChange={(event) => setSameAsLast(event.target.checked)}
          />
          <span>Same as last week</span>
        </label>
        <label className="workout-field">
          <span>Anything to change next week?</span>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            placeholder="Squats felt heavy, maybe drop Friday if BJJ hits 4 sessions…"
          />
        </label>
        <button type="submit" disabled={pending}>{pending ? 'Saving…' : 'Submit Sunday review'}</button>
        {status && <p className="workout-status">{status}</p>}
        {briefing.advice && <p className="workout-note">{briefing.advice}</p>}
      </form>
    </section>
  )
}
