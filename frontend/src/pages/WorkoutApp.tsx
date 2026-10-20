import { useEffect, useMemo } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchDailyBriefing, fetchTrainingSession } from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import { formatDate } from '../lib/format'
import { canLogWorkout, doneMarkLabel, slugForType, workoutAlreadyLogged } from '../lib/workoutMatch'
import type { PlannedExercise } from '../types'
import { AlertIcon, ListIcon, SlidersIcon, DumbbellIcon } from '../components/icons'
import { TrainingReport } from '../components/TrainingReport'
import { PageSkeleton } from '../components/PageSkeleton'
import '../workout.css'

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

function IntensityPill({ intensity, deload }: { intensity?: string; deload?: boolean }) {
  if (!intensity && !deload) return null
  return (
    <span className="workout-hero-meta">
      {intensity && <span className={`workout-pill is-${intensity}`}>{intensity}</span>}
      {deload && <span className="workout-pill is-deload">Deload week</span>}
    </span>
  )
}

function WorkoutQuickActions() {
  return (
    <div className="daily-quick-actions" aria-label="Quick actions">
      <a className="daily-quick-action is-alert" href="/schedule-change" title="Something changed?">
        <AlertIcon size={20} />
        <span>Change plan</span>
      </a>
      <a className="daily-quick-action is-neutral" href="/training/preferences" title="Training preferences">
        <SlidersIcon size={20} />
        <span>Preferences</span>
      </a>
      <a className="daily-quick-action is-workout" href="/weekly" title="My workouts">
        <ListIcon size={20} />
        <span>My workouts</span>
      </a>
      <a className="daily-quick-action is-neutral" href="/training/exercises" title="Exercise library">
        <DumbbellIcon size={20} />
        <span>Exercises</span>
      </a>
    </div>
  )
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
        <IntensityPill intensity={workout?.intensity} deload={workout?.deload} />
        {logged && workout && <p className="workout-done-badge">✓ {doneMarkLabel(workout.status) ?? 'Done'}</p>}
        <WorkoutQuickActions />
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
          {canLog ? (
            <TrainingReport day={day} workout={session} coachSessionId={session.id} />
          ) : (
            <p className="workout-status">This session cannot be logged from here.</p>
          )}
          <section className="workout-hero">
            <p>{session.estimated_minutes} min</p>
            <h1>{session.title}</h1>
            <span>{session.reason}</span>
            <IntensityPill intensity={session.intensity} deload={session.deload} />
          </section>
          <details className="workout-section workout-program">
            <summary>Program</summary>
            <div className="workout-checks">
              {session.exercises.map((item) => (
                <div key={item.name} className={`workout-check${item.done ? ' is-checked' : ''}`}>
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
          </details>
        </>
      )}
    </div>
  )
}
