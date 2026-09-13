import { FormEvent, useEffect, useMemo, useState } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchTrainingPlan, fetchTrainingPlans, fetchTrainingToday, logDailyWorkout, logWorkout } from '../lib/api'
import { formatDate } from '../lib/format'
import type { TrainingKind, TrainingLog, TrainingPlan, TrainingToday } from '../types'
import '../workout.css'

function workoutPath() {
  return window.location.pathname.replace(/\/+$/, '') || '/'
}

function planSlugFromPath(path: string) {
  const match = path.match(/^\/workout\/([^/]+)$/)
  return match?.[1] ?? null
}

function todayStamp() {
  const now = new Date()
  const offset = now.getTimezoneOffset() * 60_000
  return new Date(now.getTime() - offset).toISOString().slice(0, 10)
}

function logSummary(log: TrainingLog) {
  const bits: string[] = [log.completed]
  const done = (log.exercises ?? []).filter((item) => item.done).map((item) => item.name)
  if (done.length) bits.push(done.join(', '))
  return bits.join(' · ')
}

export function WorkoutApp() {
  const path = workoutPath()
  const slug = planSlugFromPath(path)

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = slug ? 'Chili workout' : 'Chili today'
    return () => document.documentElement.classList.remove('is-workout')
  }, [slug])

  if (slug) return <PlanPage slug={slug} />
  return <TodayPage />
}

function TodayPage() {
  const [today, setToday] = useState<TrainingToday | null>(null)
  const [plans, setPlans] = useState<TrainingPlan[]>([])
  const [error, setError] = useState<string | null>(null)
  const day = today?.date ?? todayStamp()

  const load = () => {
    Promise.all([fetchTrainingToday(), fetchTrainingPlans()])
      .then(([nextToday, nextPlans]) => {
        setToday(nextToday)
        setPlans(nextPlans)
        setError(null)
      })
      .catch(() => setError('Could not load today.'))
  }

  useEffect(() => {
    load()
  }, [])

  const extraPlans = useMemo(() => {
    const suggested = new Set((today?.suggested ?? []).map((plan) => plan.slug))
    return plans.filter((plan) => plan.kind !== 'sober' && !suggested.has(plan.slug))
  }, [plans, today])

  const headingDate = today ? formatDate(new Date(`${today.date}T12:00:00`)) : 'Today'

  return (
    <div className="workout-page">
      <header className="workout-top">
        <span className="workout-brand">
          <img src={chiliLogo} alt="" />
          Chili
        </span>
        <a className="workout-back" href={`/daily/${day}`}>Daily</a>
      </header>
      <section className="workout-hero">
        <p>Today</p>
        <h1>{headingDate}</h1>
        <span>
          {today?.suggested_source === 'calendar' ? 'From Chili Training calendar' : 'Week plan fallback'}
        </span>
      </section>
      {error && <p className="workout-status">{error}</p>}
      <section className="workout-section">
        <h2>Suggested</h2>
        {(today?.suggested ?? []).map((plan) => (
          <a key={plan.slug} className="workout-plan-link" href={`/workout/${plan.slug}`}>
            <strong>{plan.name}</strong>
            <span>{plan.duration} · {plan.summary}</span>
          </a>
        ))}
        {!today?.suggested.length && <p className="workout-empty">No suggested session.</p>}
      </section>
      {today && today.logs.filter((log) => log.kind !== 'sober').length > 0 && (
        <section className="workout-section">
          <h2>Logged today</h2>
          {today.logs.filter((log) => log.kind !== 'sober').map((log) => (
            <div key={log.id} className="workout-log">
              <strong>{log.kind.replaceAll('_', ' ')}</strong>
              <span>{logSummary(log)}</span>
              {log.note && <span>{log.note}</span>}
            </div>
          ))}
        </section>
      )}
      <section className="workout-section">
        <h2>Evening</h2>
        <a className="workout-plan-link" href={`/daily/${day}`}>
          <strong>Sober check-in</strong>
          <span>Answer this at night on the daily page.</span>
        </a>
      </section>
      <section className="workout-section">
        <h2>Other sessions</h2>
        {extraPlans.map((plan) => (
          <a key={plan.slug} className="workout-plan-link" href={`/workout/${plan.slug}`}>
            <strong>{plan.name}</strong>
            <span>{plan.duration}</span>
          </a>
        ))}
      </section>
    </div>
  )
}

function PlanPage({ slug }: { slug: string }) {
  const [plan, setPlan] = useState<TrainingPlan | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetchTrainingPlan(slug)
      .then((next) => {
        setPlan(next)
        setError(null)
        document.title = `${next.name} · Chili`
      })
      .catch(() => setError('Unknown session.'))
  }, [slug])

  return (
    <div className="workout-page">
      <header className="workout-top">
        <span className="workout-brand">
          <img src={chiliLogo} alt="" />
          Chili
        </span>
        <a className="workout-back" href="/workout">Today</a>
      </header>
      {error && <p className="workout-status">{error}</p>}
      {plan && (
        <>
          <section className="workout-hero">
            <p>{plan.duration}</p>
            <h1>{plan.name}</h1>
            <span>{plan.summary}</span>
          </section>
          <WorkoutCheckForm
            kind={plan.kind}
            items={plan.blocks.length > 0
              ? plan.blocks.map((block) => ({
                  name: block.title,
                  prescription: block.prescription,
                  details: block.details,
                  done: false,
                }))
              : [{
                  name: plan.kind === 'rest' ? 'Full rest' : plan.name,
                  prescription: null,
                  details: [],
                  done: false,
                }]}
          />
          {plan.notes.length > 0 && (
            <section className="workout-section">
              <h2>Notes</h2>
              {plan.notes.map((note) => (
                <p key={note} className="workout-note">{note}</p>
              ))}
            </section>
          )}
        </>
      )}
    </div>
  )
}

export function WorkoutCheckForm({
  kind,
  items,
  day,
  onLogged,
}: {
  kind: TrainingKind
  items: { name: string; prescription: string | null; details: string[]; done: boolean }[]
  day?: string
  onLogged?: () => void
}) {
  const [done, setDone] = useState<Record<string, boolean>>(
    Object.fromEntries(items.map((item) => [item.name, item.done])),
  )
  const [note, setNote] = useState('')
  const [pending, setPending] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const itemKey = items.map((item) => `${item.name}:${item.done}`).join('|')

  useEffect(() => {
    setDone(Object.fromEntries(items.map((item) => [item.name, item.done])))
  }, [itemKey])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const payload = {
      kind,
      exercises: items.map((item) => ({ name: item.name, done: Boolean(done[item.name]) })),
      note: note.trim() || undefined,
    }
    setPending(true)
    const request = day ? logDailyWorkout(day, payload) : logWorkout(payload)
    void request
      .then((result) => {
        setStatus(result.message)
        if (result.status === 'logged') {
          setNote('')
          onLogged?.()
        }
      })
      .catch(() => setStatus('Could not save workout.'))
      .finally(() => setPending(false))
  }

  return (
    <section className="workout-section">
      <h2>Did you do it?</h2>
      <form className="workout-form" onSubmit={submit}>
        <div className="workout-checks">
          {items.map((item) => (
            <label key={item.name} className={`workout-check ${done[item.name] ? 'is-checked' : ''}`}>
              <input
                type="checkbox"
                checked={Boolean(done[item.name])}
                onChange={(event) => setDone((current) => ({ ...current, [item.name]: event.target.checked }))}
              />
              <span>
                <strong>{item.name}</strong>
                {item.prescription && <em>{item.prescription}</em>}
                {item.details.map((detail) => (
                  <small key={detail}>{detail}</small>
                ))}
              </span>
            </label>
          ))}
        </div>
        <label className="workout-field">
          <span>Easy or hard?</span>
          <textarea
            value={note}
            onChange={(event) => setNote(event.target.value)}
            maxLength={500}
            placeholder="Felt easy, squat was heavy, skipped the last interval…"
          />
        </label>
        <button type="submit" disabled={pending}>{pending ? 'Saving…' : 'Submit workout'}</button>
        {status && <p className="workout-status">{status}</p>}
      </form>
    </section>
  )
}
