import { FormEvent, useEffect, useMemo, useState } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchDailyBriefing, fetchTrainingPlan, fetchTrainingPlans, logDailyWorkout } from '../lib/api'
import { formatDate } from '../lib/format'
import { canLogWorkout, doneMarkLabel, kindsMatch, slugForType, workoutAlreadyLogged } from '../lib/workoutMatch'
import type { DailyBriefing, PlannedWorkout, TrainingKind, TrainingPlan } from '../types'
import '../workout.css'

function workoutPath() {
  return window.location.pathname.replace(/\/+$/, '') || '/'
}

function planSlugFromPath(path: string) {
  const match = path.match(/^\/workout\/([^/]+)$/)
  return match?.[1] ?? null
}

function todayStamp() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
}

function exerciseDone(name: string, doneByName: Map<string, boolean>) {
  if (doneByName.has(name)) return Boolean(doneByName.get(name))
  const needle = name.toLowerCase()
  for (const [key, value] of doneByName) {
    const hay = key.toLowerCase()
    if (hay === needle || hay.includes(needle) || needle.includes(hay)) return Boolean(value)
  }
  return false
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
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null)
  const [plans, setPlans] = useState<TrainingPlan[]>([])
  const [error, setError] = useState<string | null>(null)
  const day = briefing?.date ?? todayStamp()
  const workout = briefing?.workout

  const load = () => {
    Promise.all([fetchDailyBriefing(day), fetchTrainingPlans()])
      .then(([nextBriefing, nextPlans]) => {
        setBriefing(nextBriefing)
        setPlans(nextPlans)
        setError(null)
      })
      .catch(() => setError('Could not load today.'))
  }

  useEffect(() => {
    load()
  }, [])

  const suggestedSlug = workout && workout.planned_type !== 'rest' ? slugForType(workout.planned_type) : null
  const suggested = useMemo(
    () => plans.filter((plan) => plan.kind !== 'sober' && suggestedSlug === plan.slug),
    [plans, suggestedSlug],
  )
  const extraPlans = useMemo(() => {
    return plans.filter((plan) => plan.kind !== 'sober' && plan.slug !== suggestedSlug)
  }, [plans, suggestedSlug])

  const headingDate = briefing ? formatDate(new Date(`${briefing.date}T12:00:00`)) : 'Today'
  const logged = workout && workoutAlreadyLogged(workout.status)

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
        <span>{workout ? workout.title : 'No prescribed session'}</span>
        {logged && workout && <p className="workout-done-badge">✓ {doneMarkLabel(workout.status) ?? 'Done'}</p>}
      </section>
      {error && <p className="workout-status">{error}</p>}
      <section className="workout-section">
        <h2>Suggested</h2>
        {suggested.map((plan) => (
          <a key={plan.slug} className="workout-plan-link" href={`/workout/${plan.slug}`}>
            <strong>{plan.name}</strong>
            <span>{plan.duration} · {plan.summary}</span>
          </a>
        ))}
        {!suggested.length && <p className="workout-empty">No suggested session.</p>}
      </section>
      {logged && workout && (
        <section className="workout-section">
          <h2>Logged today</h2>
          <div className="workout-log">
            <strong>{workout.title}</strong>
            <span>{workout.status}</span>
            {workout.notes && <span>{workout.notes}</span>}
          </div>
        </section>
      )}
      {briefing?.advice && (
        <section className="workout-section workout-chili">
          <h2>Chili</h2>
          <p className="workout-advice">{briefing.advice}</p>
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
  const [session, setSession] = useState<PlannedWorkout | null>(null)
  const [advice, setAdvice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [canLog, setCanLog] = useState(false)
  const day = todayStamp()

  useEffect(() => {
    Promise.all([fetchTrainingPlan(slug), fetchDailyBriefing(day)])
      .then(([next, briefing]) => {
        setPlan(next)
        const workout = briefing.workout
        const matches = Boolean(workout && kindsMatch(workout.planned_type, next.kind))
        setSession(matches ? workout : null)
        setCanLog(Boolean(workout && canLogWorkout(workout.planned_type, next.kind) && workout.status !== 'preview'))
        setAdvice(briefing.advice ?? null)
        setError(null)
        document.title = `${next.name} · Chili`
      })
      .catch(() => setError('Unknown session.'))
  }, [day, slug])

  const saved = Boolean(session && workoutAlreadyLogged(session.status))
  const doneByName = new Map((session?.exercises ?? []).map((item) => [item.name, Boolean(item.done)]))

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
            day={day}
            canLog={canLog}
            items={plan.blocks.length > 0
              ? plan.blocks.map((block) => ({
                  name: block.title,
                  prescription: block.prescription,
                  details: block.details,
                  done: exerciseDone(block.title, doneByName),
                }))
              : [{
                  name: plan.kind === 'rest' ? 'Full rest' : plan.name,
                  prescription: null,
                  details: [],
                  done: saved,
                }]}
            initialNote={session?.notes ?? ''}
            initialSaved={saved}
            initialAdvice={advice}
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
  canLog = true,
  onLogged,
  initialNote = '',
  initialSaved = false,
  initialAdvice = null,
}: {
  kind: TrainingKind
  items: { name: string; prescription: string | null; details: string[]; done: boolean }[]
  day: string
  canLog?: boolean
  onLogged?: () => void
  initialNote?: string
  initialSaved?: boolean
  initialAdvice?: string | null
}) {
  const [done, setDone] = useState<Record<string, boolean>>(
    Object.fromEntries(items.map((item) => [item.name, item.done])),
  )
  const [note, setNote] = useState(initialNote)
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(initialSaved)
  const [advice, setAdvice] = useState<string | null>(initialAdvice)
  const [status, setStatus] = useState<string | null>(null)
  const itemKey = items.map((item) => `${item.name}:${item.done}`).join('|')

  useEffect(() => {
    setDone(Object.fromEntries(items.map((item) => [item.name, item.done])))
  }, [itemKey])

  useEffect(() => {
    setNote(initialNote)
    setSaved(initialSaved)
    setAdvice(initialAdvice)
  }, [initialNote, initialSaved, initialAdvice])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending || saved || !canLog) return
    const payload = {
      kind,
      exercises: items.map((item) => ({ name: item.name, done: Boolean(done[item.name]) })),
      note: note.trim() || undefined,
    }
    setPending(true)
    void logDailyWorkout(day, payload)
      .then((result) => {
        setStatus(result.message)
        if (result.status === 'logged') {
          setSaved(true)
          setAdvice(result.advice ?? null)
          onLogged?.()
        }
      })
      .catch(() => setStatus('Could not save workout.'))
      .finally(() => setPending(false))
  }

  if (!canLog && !saved) {
    return (
      <section className="workout-section">
        <h2>Program</h2>
        <div className="workout-checks">
          {items.map((item) => (
            <div key={item.name} className="workout-check">
              <span>
                <strong>{item.name}</strong>
                {item.prescription && <em>{item.prescription}</em>}
                {item.details.map((detail) => (
                  <small key={detail}>{detail}</small>
                ))}
              </span>
            </div>
          ))}
        </div>
        <p className="workout-status">
          {kind === 'rest'
            ? 'Rest days are not logged here.'
            : "This is not today's session. Ask Chili to change the plan first."}
        </p>
      </section>
    )
  }

  if (saved) {
    return (
      <section className="workout-section">
        <h2>Did you do it?</h2>
        <p className="workout-done-badge">✓ Done</p>
        <div className="workout-checks">
          {items.map((item) => (
            <div key={item.name} className={`workout-check ${done[item.name] ? 'is-checked' : ''}`}>
              <span>{done[item.name] ? '✓' : '–'} {item.name}</span>
            </div>
          ))}
        </div>
        {note.trim() && <p className="workout-status">{note}</p>}
        {advice && (
          <div className="workout-chili">
            <h2>Chili</h2>
            <p className="workout-advice">{advice}</p>
          </div>
        )}
      </section>
    )
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
