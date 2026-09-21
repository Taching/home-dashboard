import { FormEvent, useEffect, useMemo, useState } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchDailyBriefing, fetchTrainingSession, logTrainingSessionResult } from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import { formatDate } from '../lib/format'
import { canLogWorkout, doneMarkLabel, slugForType, workoutAlreadyLogged, workoutFormLocked } from '../lib/workoutMatch'
import type { PlannedExercise, PlannedWorkout } from '../types'
import { AskCoachButton } from '../components/AskCoachButton'
import { PageSkeleton } from '../components/PageSkeleton'
import '../workout.css'

const MISS_REASONS = [
  ['OVERSLEPT', 'Overslept'],
  ['WEATHER', 'Weather'],
  ['WORK', 'Work'],
  ['FATIGUE', 'Fatigue'],
  ['POOR_SLEEP', 'Poor sleep'],
  ['INJURY', 'Injury'],
  ['ILLNESS', 'Illness'],
  ['USER_CANCELLED', 'Could not go'],
] as const

function workoutPath() {
  return window.location.pathname.replace(/\/+$/, '') || '/'
}

function planSlugFromPath(path: string) {
  const match = path.match(/^\/workout\/([^/]+)$/)
  return match?.[1] ?? null
}

function isSessionId(value: string) {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)
}

function todayStamp() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
}

function exerciseLine(item: PlannedExercise) {
  return [
    item.load_value != null && `${item.load_value}${item.load_unit ?? ''}`,
    item.sets && `${item.sets} sets`,
    item.reps && `${item.reps} reps`,
    item.duration_seconds && `${Math.round(item.duration_seconds / 60)} min`,
  ].filter(Boolean).join(' · ')
}

export function WorkoutApp() {
  const path = workoutPath()
  const slug = planSlugFromPath(path)

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = slug ? 'Chili workout' : 'Chili today'
    return () => document.documentElement.classList.remove('is-workout')
  }, [slug])

  if (slug) return <SessionOrRedirect slug={slug} />
  return <TodayPage />
}

function SessionOrRedirect({ slug }: { slug: string }) {
  if (isSessionId(slug)) return <SessionPage sessionId={slug} />
  return <LegacySlugRedirect slug={slug} />
}

function LegacySlugRedirect({ slug }: { slug: string }) {
  const day = todayStamp()
  useEffect(() => {
    fetchDailyBriefing(day).then((briefing) => {
      const workout = briefing.workout
      if (workout && slugForType(workout.planned_type) === slug) {
        window.location.replace(`/workout/${workout.id}`)
        return
      }
      window.location.replace('/workout')
    }).catch(() => {
      window.location.replace('/workout')
    })
  }, [day, slug])
  return <div className="workout-page"><p className="workout-status">Opening today’s session…</p></div>
}

function TodayPage() {
  const today = todayStamp()
  const briefingQueryKey = useMemo(() => ['daily-briefing', today, null] as const, [today])
  const { data: briefing, error } = useLiveResource(
    (signal) => fetchDailyBriefing(today, undefined, signal),
    { queryKey: briefingQueryKey },
  )
  const day = briefing?.date ?? todayStamp()
  const workout = briefing?.workout

  if (!briefing && !error) return <PageSkeleton />

  const headingDate = briefing ? formatDate(new Date(`${briefing.date}T12:00:00`)) : 'Today'
  const logged = workout && workoutAlreadyLogged(workout.status)
  const openSession = workout && workout.planned_type !== 'rest'

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
        <h2>Session</h2>
        {openSession ? (
          <a className="workout-plan-link" href={`/workout/${workout.id}`}>
            <strong>{workout.title}</strong>
            <span>{workout.estimated_minutes} min · {workout.intensity}</span>
          </a>
        ) : (
          <p className="workout-empty">{workout?.planned_type === 'rest' ? 'Rest day. Nothing to log.' : 'No suggested session.'}</p>
        )}
      </section>
      {briefing?.advice && (
        <section className="workout-section workout-chili">
          <h2>Chili</h2>
          <p className="workout-advice">{briefing.advice}</p>
        </section>
      )}
      <section className="workout-section">
        <h2>Review</h2>
        <a className="workout-plan-link" href="/weekly">
          <strong>Weekly training review</strong>
          <span>Planned vs actual and next week’s load.</span>
        </a>
      </section>
    </div>
  )
}

function SessionPage({ sessionId }: { sessionId: string }) {
  const sessionQueryKey = useMemo(() => ['training-session', sessionId] as const, [sessionId])
  const { data: session, error } = useLiveResource(
    (signal) => fetchTrainingSession(sessionId, signal),
    { queryKey: sessionQueryKey },
  )

  useEffect(() => {
    if (session) document.title = `${session.title} · Chili`
  }, [session])

  const day = session?.start_at
    ? new Date(session.start_at).toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
    : todayStamp()
  const type = session?.planned_type ?? ''
  const saved = Boolean(session && workoutFormLocked(session.status))
  const canLog = Boolean(session && canLogWorkout(type, type))

  if (!session && !error) return <PageSkeleton />

  return (
    <div className="workout-page">
      <header className="workout-top">
        <span className="workout-brand">
          <img src={chiliLogo} alt="" />
          Chili
        </span>
        <a className="workout-back" href={`/daily/${day}`}>Daily</a>
      </header>
      {error && <p className="workout-status">{error}</p>}
      {session && (
        <>
          <section className="workout-hero">
            <p>{session.estimated_minutes} min · {session.intensity}</p>
            <h1>{session.title}</h1>
            <span>{session.reason}</span>
          </section>
          <section className="workout-section">
            <h2>Prescribed</h2>
            <div className="workout-checks">
              {session.exercises.map((item) => (
                <div key={item.name} className="workout-check">
                  <span>
                    <strong>{item.name}</strong>
                    <em>{exerciseLine(item)}</em>
                    {item.notes && <small>{item.notes}</small>}
                  </span>
                </div>
              ))}
              {type.startsWith('bjj_') && session.target_rounds != null && (
                <div className="workout-check">
                  <span><strong>Round target</strong><em>{session.target_rounds} × 5 min</em></span>
                </div>
              )}
            </div>
          </section>
          <SessionResultForm session={session} canLog={canLog} saved={saved} day={day} />
        </>
      )}
    </div>
  )
}

function SessionResultForm({
  session,
  canLog,
  saved,
  day,
}: {
  session: PlannedWorkout
  canLog: boolean
  saved: boolean
  day: string
}) {
  const type = session.planned_type
  const isBjj = type.startsWith('bjj_') || type === 'competition'
  const [status, setStatus] = useState(saved ? session.status : 'completed')
  const [missReason, setMissReason] = useState(session.miss_reason ?? 'OVERSLEPT')
  const [rpe, setRpe] = useState(String(session.session_rpe ?? session.result?.session_rpe ?? ''))
  const [difficulty, setDifficulty] = useState(String(session.result?.difficulty ?? ''))
  const [notes, setNotes] = useState(session.notes ?? '')
  const [fatigue, setFatigue] = useState(session.result?.fatigue ?? 'NORMAL')
  const [soreness, setSoreness] = useState(session.result?.soreness ?? 'NORMAL')
  const [pain, setPain] = useState(Boolean(session.result?.pain))
  const [pace, setPace] = useState(session.result?.perceived_intensity ?? 'easy')
  const [bjjRounds, setBjjRounds] = useState(String(session.result?.bjj_rounds ?? session.target_rounds ?? ''))
  const [intensity, setIntensity] = useState(session.result?.perceived_intensity ?? 'normal')
  const [grip, setGrip] = useState(session.result?.grip_fatigue ?? 'NORMAL')
  const [recovery, setRecovery] = useState(session.result?.recovery_activity ?? 'mobility')
  const [actuals, setActuals] = useState<Record<string, { load: string; sets: string; reps: string; duration: string }>>(
    Object.fromEntries(session.exercises.map((item) => [item.name, {
      load: String(item.load_value ?? ''),
      sets: String(item.sets ?? ''),
      reps: String(item.reps ?? ''),
      duration: item.duration_seconds ? String(Math.round(item.duration_seconds / 60)) : '',
    }])),
  )
  const [pending, setPending] = useState(false)
  const [message, setMessage] = useState<string | null>(null)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending || !canLog) return
    const payload: Record<string, unknown> = {
      status: status === 'skipped' ? 'skipped' : status,
      miss_reason: status === 'skipped' ? missReason : undefined,
      notes: notes.trim() || undefined,
    }
    if (isBjj) {
      if (status !== 'skipped') {
        payload.bjj_rounds = bjjRounds ? Number(bjjRounds) : undefined
        payload.perceived_intensity = intensity
      }
    } else {
      payload.session_rpe = rpe ? Number(rpe) : undefined
      payload.difficulty = difficulty ? Number(difficulty) : undefined
      payload.fatigue = fatigue
      payload.soreness = soreness
      payload.pain = pain
      if (type === 'zone_2') payload.perceived_intensity = pace
      if (type === 'recovery') payload.recovery_activity = recovery
      if (type === 'grip') payload.grip_fatigue = grip
      payload.exercises = session.exercises.map((item) => {
        const actual = actuals[item.name]
        return {
          name: item.name,
          actual_load: actual?.load ? Number(actual.load) : undefined,
          actual_sets: actual?.sets ? Number(actual.sets) : undefined,
          actual_reps: actual?.reps || undefined,
          actual_duration_seconds: actual?.duration ? Number(actual.duration) * 60 : undefined,
          completed: status !== 'skipped',
          done: status !== 'skipped',
        }
      })
    }
    setPending(true)
    void logTrainingSessionResult(session.id, payload)
      .then(() => {
        window.location.assign(`/daily/${day}`)
      })
      .catch(() => {
        setMessage('Could not save results.')
        setPending(false)
      })
  }

  if (!canLog && !saved) {
    return <p className="workout-status">This session cannot be logged from here.</p>
  }

  return (
    <section className="workout-section">
      <h2>{saved ? 'Logged' : 'How it went'}</h2>
      <form className="workout-form" onSubmit={submit}>
        <div className="workout-choices" role="radiogroup" aria-label="How it went">
          {([['completed', 'Completed'], ['partial', 'Partial'], ['skipped', 'Skipped']] as const).map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={status === value ? 'is-selected' : ''}
              aria-pressed={status === value}
              disabled={saved}
              onClick={() => setStatus(value)}
            >
              {label}
            </button>
          ))}
        </div>
        {status === 'skipped' && (
          <label className="workout-field">
            <span>Why missed</span>
            <select value={missReason} onChange={(event) => setMissReason(event.target.value)} disabled={saved}>
              {MISS_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </label>
        )}
        {type.startsWith('strength_') && (
          <div className="workout-checks">
            {session.exercises.map((item) => (
              <label key={item.name} className="workout-check">
                <span>
                  <strong>{item.name}</strong>
                  <em>Prescribed {exerciseLine(item)}</em>
                  <span className="workout-actuals">
                    <input placeholder="kg" value={actuals[item.name]?.load ?? ''} disabled={saved} onChange={(event) => setActuals((current) => ({ ...current, [item.name]: { ...current[item.name], load: event.target.value } }))} />
                    <input placeholder="sets" value={actuals[item.name]?.sets ?? ''} disabled={saved} onChange={(event) => setActuals((current) => ({ ...current, [item.name]: { ...current[item.name], sets: event.target.value } }))} />
                    <input placeholder="reps" value={actuals[item.name]?.reps ?? ''} disabled={saved} onChange={(event) => setActuals((current) => ({ ...current, [item.name]: { ...current[item.name], reps: event.target.value } }))} />
                  </span>
                </span>
              </label>
            ))}
          </div>
        )}
        {type === 'zone_2' && (
          <>
            <label className="workout-field">
              <span>Actual minutes</span>
              <input value={actuals[session.exercises[0]?.name]?.duration ?? ''} disabled={saved} onChange={(event) => setActuals((current) => ({ ...current, [session.exercises[0]?.name]: { ...current[session.exercises[0]?.name], duration: event.target.value } }))} />
            </label>
            <label className="workout-field">
              <span>Pace</span>
              <select value={pace} disabled={saved} onChange={(event) => setPace(event.target.value)}>
                <option value="easy">Conversation</option>
                <option value="normal">Steady</option>
                <option value="hard">Too hard</option>
              </select>
            </label>
          </>
        )}
        {type === 'grip' && (
          <>
            <label className="workout-field">
              <span>Actual hold load</span>
              <input value={actuals[session.exercises[0]?.name]?.load ?? ''} disabled={saved} onChange={(event) => setActuals((current) => ({ ...current, [session.exercises[0]?.name]: { ...current[session.exercises[0]?.name], load: event.target.value } }))} />
            </label>
            <label className="workout-field">
              <span>Actual hold minutes</span>
              <input value={actuals[session.exercises[0]?.name]?.duration ?? ''} disabled={saved} onChange={(event) => setActuals((current) => ({ ...current, [session.exercises[0]?.name]: { ...current[session.exercises[0]?.name], duration: event.target.value } }))} />
            </label>
            <label className="workout-field">
              <span>Grip fatigue</span>
              <select value={grip} disabled={saved} onChange={(event) => setGrip(event.target.value)}>
                <option value="NORMAL">Normal</option>
                <option value="HIGH">High</option>
              </select>
            </label>
          </>
        )}
        {isBjj && status !== 'skipped' && (
          <>
            <label className="workout-field">
              <span>Rounds</span>
              <input inputMode="numeric" value={bjjRounds} disabled={saved} onChange={(event) => setBjjRounds(event.target.value)} />
            </label>
            <label className="workout-field">
              <span>Intensity</span>
              <select value={intensity} disabled={saved} onChange={(event) => setIntensity(event.target.value)}>
                <option value="easy">Easy</option>
                <option value="normal">Normal</option>
                <option value="hard">Hard</option>
              </select>
            </label>
          </>
        )}
        {type === 'recovery' && (
          <label className="workout-field">
            <span>What did you do?</span>
            <select value={recovery} disabled={saved} onChange={(event) => setRecovery(event.target.value)}>
              <option value="mobility">Mobility</option>
              <option value="walk">Walk</option>
              <option value="nothing">Nothing</option>
            </select>
          </label>
        )}
        {!isBjj && (
          <>
            <label className="workout-field">
              <span>Session RPE</span>
              <input value={rpe} disabled={saved} onChange={(event) => setRpe(event.target.value)} placeholder="1–10" />
            </label>
            <label className="workout-field">
              <span>Difficulty</span>
              <input value={difficulty} disabled={saved} onChange={(event) => setDifficulty(event.target.value)} placeholder="1–10" />
            </label>
            <label className="workout-field">
              <span>Fatigue</span>
              <select value={fatigue} disabled={saved} onChange={(event) => setFatigue(event.target.value)}>
                <option value="LOW">Low</option>
                <option value="NORMAL">Normal</option>
                <option value="HIGH">High</option>
              </select>
            </label>
            <label className="workout-field">
              <span>Soreness</span>
              <select value={soreness} disabled={saved} onChange={(event) => setSoreness(event.target.value)}>
                <option value="LOW">Low</option>
                <option value="NORMAL">Normal</option>
                <option value="HIGH">High</option>
              </select>
            </label>
            <label className="workout-check">
              <input type="checkbox" checked={pain} disabled={saved} onChange={(event) => setPain(event.target.checked)} />
              <span>Pain</span>
            </label>
          </>
        )}
        <label className="workout-field">
          <span>Notes</span>
          <textarea value={notes} disabled={saved} onChange={(event) => setNotes(event.target.value)} maxLength={500} />
        </label>
        {!saved && <button type="submit" disabled={pending}>{pending ? 'Saving…' : 'Save results'}</button>}
        {saved && <p className="workout-done-badge">✓ {doneMarkLabel(session.status) ?? 'Logged'}</p>}
        {message && <p className="workout-status">{message}</p>}
      </form>
      {saved && <AskCoachButton sessionId={session.id} />}
    </section>
  )
}
