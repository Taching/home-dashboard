import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { closeDailyDay, fetchDailyBriefing, logDailyWorkout, logSleep, logSober, logSundayReview } from '../lib/api'
import { dailyAnswersFromBriefing } from '../lib/dailyPlan'
import { useLiveResource } from '../hooks/useLiveResource'
import { doneMarkLabel, workoutFormLocked } from '../lib/workoutMatch'
import type { DailyAnswerItem, DailyBriefing, PlannedExercise } from '../types'
import { AskCoachButton } from './AskCoachButton'
import { AlertIcon, SlidersIcon } from './icons'
import { PageSkeleton } from './PageSkeleton'

function formatTime(value: string, allDay = false) {
  if (allDay) return 'All day'
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Tokyo', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
}

function exerciseDetail(item: PlannedExercise) {
  return [
    item.load_value != null && `${item.load_value}${item.load_unit ?? ''}`,
    item.sets && `${item.sets} sets`,
    item.reps && `${item.reps} reps`,
    item.duration_seconds && `${item.duration_seconds}s`,
  ].filter(Boolean).join(' · ')
}

function liveAdjustment(adjustment: { how?: string[]; why?: string[]; banner?: string } | null | undefined) {
  if (!adjustment?.how?.length) return null
  const quota = /still needs|only fill it if|one complete rest|one full rest day|Rest 0|missing tournament piece|empty time is not extra gym/i
  const how = adjustment.how.filter((item) => !quota.test(item))
  const why = (adjustment.why ?? []).filter((item) => !quota.test(item))
  if (!how.length && !why.length) return null
  return { ...adjustment, how, why }
}

function DoneBadge() {
  return <span className="daily-done-badge" aria-label="Done">✓</span>
}

function DailyQuickActions() {
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
    </div>
  )
}

function verifyLabel(delivery: string | null | undefined, reply: string | null | undefined, waiting: boolean) {
  if (waiting && !reply) return { kind: 'wait', text: 'Asking Chili…' }
  if (delivery === 'not_configured') return { kind: 'fail', text: 'OpenClaw is not configured' }
  if (delivery === 'completed') return { kind: 'ok', text: 'Verified · Chili replied' }
  if (reply) return { kind: 'fail', text: 'Chili did not confirm' }
  return { kind: 'wait', text: 'Waiting for Chili…' }
}

function AnswerProgress({ items }: { items: DailyAnswerItem[] }) {
  const visible = items.filter((item) => item.required)
  if (!visible.length) return null
  const done = visible.filter((item) => item.done).length
  return (
    <div className="daily-progress" aria-label={`${done} of ${visible.length} answers in`}>
      {visible.map((item) => (
        <span key={item.id} className={`daily-progress-item${item.done ? ' is-done' : ''}`}>
          {item.done ? '✓' : '○'} {item.label}
        </span>
      ))}
    </div>
  )
}

export function DailyBriefingPage({ day }: { day: string }) {
  const previewWorkout = useMemo(() => new URLSearchParams(window.location.search).get('preview'), [])
  const briefingQueryKey = useMemo(() => ['daily-briefing', day, previewWorkout] as const, [day, previewWorkout])
  const { data: briefing, error, refresh, setData: setBriefing } = useLiveResource(
    (signal) => fetchDailyBriefing(day, previewWorkout ?? undefined, signal),
    { queryKey: briefingQueryKey },
  )
  const [closing, setClosing] = useState(false)
  const [closeError, setCloseError] = useState<string | null>(null)
  const closeAsked = useRef(false)

  const title = useMemo(() => new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Tokyo', weekday: 'long', day: 'numeric', month: 'long',
  }).format(new Date(`${day}T12:00:00+09:00`)), [day])

  useEffect(() => {
    document.documentElement.classList.add('is-daily')
    return () => document.documentElement.classList.remove('is-daily')
  }, [])

  const briefingDate = briefing?.date
  useEffect(() => {
    document.title = briefingDate ? `Daily · ${briefingDate}` : 'Chili daily'
  }, [briefingDate])

  const answers = briefing ? dailyAnswersFromBriefing(briefing) : null

  const shouldClose = Boolean(briefing && !briefing.preview && answers?.all_answered && !answers.chili_reply)

  useEffect(() => {
    if (!briefing || !shouldClose || closeAsked.current) return
    closeAsked.current = true
    setClosing(true)
    void closeDailyDay(briefing.date)
      .then((next) => {
        setBriefing(next)
        setCloseError(null)
      })
      .catch(() => {
        closeAsked.current = false
        setCloseError('Chili did not confirm. Try again.')
      })
      .finally(() => setClosing(false))
  }, [briefing, setBriefing, shouldClose])

  const applyBriefing = (next?: DailyBriefing) => {
    if (next) setBriefing(next)
    else void refresh()
  }

  if (!briefing || !answers) return error
    ? <main className="daily-briefing-shell daily-loading" role="alert">{error}</main>
    : <PageSkeleton />
  const workout = briefing.workout
  const workoutDone = workout && workoutFormLocked(workout.status) ? doneMarkLabel(workout.status) : null
  const adjustment = liveAdjustment(briefing.last_adjustment)
  const remaining = answers.items.filter((item) => item.required && !item.done)
  const showWorkoutForm = Boolean(
    workout
    && workout.planned_type !== 'rest'
    && !briefing.preview
    && !workout.planned_type.startsWith('bjj_')
    && workout.planned_type !== 'competition',
  )
  const closed = answers.all_answered && !briefing.preview

  if (closed) {
    return (
      <CompleteDayPage
        briefing={briefing}
        title={title}
        answers={answers.items}
        reply={answers.chili_reply ?? null}
        delivery={answers.chili_delivery ?? null}
        waiting={closing}
        error={closeError ?? error}
        onRetry={() => {
          closeAsked.current = true
          setClosing(true)
          void closeDailyDay(briefing.date, true)
            .then((next) => {
              setBriefing(next)
              setCloseError(null)
            })
            .catch(() => {
              closeAsked.current = false
              setCloseError('Chili did not confirm. Try again.')
            })
            .finally(() => setClosing(false))
        }}
      />
    )
  }

  return (
    <main className="daily-briefing-shell">
      <header className="daily-hero">
        <div>
          <span className="daily-kicker">
            <img src={chiliLogo} alt="" className="daily-kicker-mark" />
            Chili daily plan
          </span>
          <h1>{title}</h1>
          {briefing.today?.headline && <p className="daily-plan-headline">{briefing.today.headline}</p>}
          <AnswerProgress items={answers.items} />
          {briefing.preview && <span className="daily-preview-badge">Dry run · saved plan unchanged</span>}
          <DailyQuickActions />
        </div>
        <div className="daily-streak"><strong>{briefing.sobriety.days}</strong><span>sober days</span></div>
      </header>

      <div className="daily-layout">
        <div className="daily-summary-stack">
          <section className="daily-card daily-workout-card">
            <span className="daily-card-label">Workout</span>
            {workout ? (
              <>
                <div className="daily-card-title">
                {workout.planned_type !== 'rest' ? (
                  <h2><a className="daily-session-link" href={`/workout/${workout.id}`}>{workout.title}</a></h2>
                ) : (
                  <h2>{workout.title}</h2>
                )}
                  {workoutDone ? <DoneBadge /> : (
                    <span>{workout.is_all_day ? 'Recovery day' : `${workout.estimated_minutes} min · ${workout.intensity}`}</span>
                  )}
                </div>
                {workoutDone && (
                  <span>{workoutDone}{workout.is_all_day ? '' : ` · ${workout.estimated_minutes} min · ${workout.intensity}`}</span>
                )}
                <p>{workout.reason}</p>
                {workout.planned_type !== 'rest' && (
                  <p><a className="daily-session-link" href={`/workout/${workout.id}`}>Open session page</a></p>
                )}
                {workout.coach_focus.length > 0 && <ul>{workout.coach_focus.map((focus) => <li key={focus}>{focus}</li>)}</ul>}
                {adjustment?.how?.length ? (
                  <div className="daily-plan-change">
                    <strong>How Chili changed it</strong>
                    <ul>{adjustment.how.map((item) => <li key={item}>{item}</li>)}</ul>
                    <strong>Why</strong>
                    <ul>{(adjustment.why ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                ) : null}
                {workoutDone && <AskCoachButton sessionId={workout.id} />}
              </>
            ) : (
              <p className="daily-empty">No workout is prescribed. Protect recovery and do not fill the space automatically.</p>
            )}
          </section>

          <section className="daily-card">
            <div className="daily-card-title"><span className="daily-card-label">Meetings</span><span>{briefing.calendar.status}</span></div>
            {briefing.calendar.meetings.length > 0 ? (
              <div className="daily-meetings">
                {briefing.calendar.meetings.map((meeting) => (
                  <div key={meeting.id ?? `${meeting.title}-${meeting.start_at}`}>
                    <time>{formatTime(meeting.start_at, meeting.is_all_day)}</time>
                    <strong>{meeting.title}</strong>
                  </div>
                ))}
              </div>
            ) : <p className="daily-empty">No meetings on the calendar.</p>}
          </section>

          {briefing.tomorrow && (
            <section className="daily-card">
              <span className="daily-card-label">Prepare tomorrow</span>
              <p>{briefing.tomorrow.preparation ?? briefing.tomorrow.headline}</p>
              {briefing.tomorrow.meetings.length > 0 && (
                <div className="daily-meetings">
                  {briefing.tomorrow.meetings.map((meeting) => (
                    <div key={meeting.id ?? meeting.title}>
                      <time>{meeting.clock ?? formatTime(meeting.start_at ?? '', meeting.is_all_day)}</time>
                      <strong>{meeting.title}</strong>
                    </div>
                  ))}
                </div>
              )}
              {briefing.tomorrow.training && (
                <p>{briefing.tomorrow.training.title}{briefing.tomorrow.training.estimated_minutes ? ` · ${briefing.tomorrow.training.estimated_minutes} min` : ''}</p>
              )}
            </section>
          )}

          <section className={`daily-card daily-advice${briefing.advice ? ' has-advice' : ''}`}>
            <span className="daily-card-label">
              {briefing.advice_window === 'morning'
                ? 'Chili’s morning advice'
                : briefing.advice_window === 'lunch'
                  ? 'Chili’s lunch advice'
                  : briefing.advice_window === 'evening'
                    ? 'Chili’s evening advice'
                    : 'Chili’s advice'}
            </span>
            <p>{briefing.advice ?? 'Chili answers after the last check-in.'}</p>
          </section>
        </div>

        <div className="daily-summary-stack">
          {showWorkoutForm && (
            <WorkoutForm
              day={briefing.date}
              workout={workout!}
              storedAdvice={briefing.advice}
              closesDay={remaining.length === 1 && remaining[0].id === 'workout'}
              onLogged={applyBriefing}
            />
          )}
          {briefing.sunday && (
            <SundayForm
              briefing={briefing}
              closesDay={remaining.length === 1 && remaining[0].id === 'sunday'}
              onSaved={applyBriefing}
            />
          )}
          <SleepForm
            day={briefing.date}
            hours={briefing.sleep?.hours ?? null}
            onLogged={applyBriefing}
          />
          <SoberForm
            day={briefing.date}
            answered={briefing.sobriety.answered}
            savedNote={briefing.sobriety.note}
            days={briefing.sobriety.days}
            closesDay={remaining.length === 1 && remaining[0].id === 'sober'}
            onLogged={applyBriefing}
          />
          {error && <p className="daily-form-error" role="alert">{error}</p>}
        </div>
      </div>
    </main>
  )
}

function CompleteDayPage({
  briefing,
  title,
  answers,
  reply,
  delivery,
  waiting,
  error,
  onRetry,
}: {
  briefing: DailyBriefing
  title: string
  answers: DailyAnswerItem[]
  reply: string | null
  delivery: string | null
  waiting: boolean
  error: string | null
  onRetry: () => void
}) {
  const verify = verifyLabel(delivery, reply, waiting)
  const workout = briefing.workout
  return (
    <main className="daily-briefing-shell daily-complete-shell">
      <header className="daily-complete-hero">
        <img src={chiliLogo} alt="" className="daily-complete-mark" />
        <span className="daily-kicker">All answered</span>
        <h1>Good job</h1>
        <p>{title} is closed. Chili has the day.</p>
        <AnswerProgress items={answers} />
        <DailyQuickActions />
      </header>

      <section className="daily-card daily-complete-recap">
        <span className="daily-card-label">Logged</span>
        <ul className="daily-complete-list">
          {workout && workout.planned_type !== 'rest' && (
            <li>
              <strong>{workout.title}</strong>
              <span>{doneMarkLabel(workout.status) ?? workout.status}</span>
            </li>
          )}
          {briefing.sunday?.submitted && (
            <li>
              <strong>Sunday weigh-in</strong>
              <span>
                {briefing.sunday.weight_kg != null ? `${briefing.sunday.weight_kg.toFixed(1)} kg` : 'Saved'}
                {briefing.sunday.delta_kg != null ? ` · ${briefing.sunday.delta_kg > 0 ? '+' : ''}${briefing.sunday.delta_kg.toFixed(1)} kg` : ''}
              </span>
            </li>
          )}
          <li>
            <strong>Sober</strong>
            <span>{briefing.sobriety.answered === 'yes' ? 'Yes' : briefing.sobriety.answered === 'no' ? 'No' : 'Saved'}</span>
          </li>
        </ul>
        {briefing.tomorrow && (
          <p className="daily-complete-tomorrow">{briefing.tomorrow.preparation ?? briefing.tomorrow.headline}</p>
        )}
      </section>

      <section className={`daily-card daily-advice has-advice daily-verify-card is-${verify.kind}`}>
        <div className="daily-card-title">
          <span className="daily-card-label">Chili</span>
          <span className={`daily-verify is-${verify.kind}`}>{verify.text}</span>
        </div>
        <p className="daily-chili-reply">{reply ?? (waiting ? 'Sending the day to OpenClaw…' : 'No reply yet.')}</p>
        {(verify.kind === 'fail' || error) && (
          <button className="daily-submit" type="button" onClick={onRetry} disabled={waiting}>
            {waiting ? 'Asking Chili…' : 'Ask Chili again'}
          </button>
        )}
        {error && <p className="daily-form-error" role="alert">{error}</p>}
      </section>
    </main>
  )
}

function WorkoutForm({
  day,
  workout,
  storedAdvice,
  closesDay,
  onLogged,
}: {
  day: string
  workout: NonNullable<DailyBriefing['workout']>
  storedAdvice?: string | null
  closesDay?: boolean
  onLogged: (next?: DailyBriefing) => void
}) {
  const [done, setDone] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(workout.exercises.map((item) => [item.name, Boolean(item.done)])),
  )
  const [note, setNote] = useState(workout.notes ?? '')
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const [advice, setAdvice] = useState<string | null>(null)
  const sent = saved || workoutFormLocked(workout.status)
  const [error, setError] = useState<string | null>(null)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending || sent) return
    setPending(true)
    void logDailyWorkout(day, {
      kind: workout.planned_type as never,
      exercises: workout.exercises.map((item) => ({ name: item.name, done: Boolean(done[item.name]) })),
      note: note.trim() || undefined,
    })
      .then((result) => {
        if (result.status === 'logged') {
          setSaved(true)
          setAdvice(result.advice ?? null)
          setError(null)
          onLogged(result.briefing)
        } else {
          setError(result.message)
        }
      })
      .catch(() => setError('Could not save workout.'))
      .finally(() => setPending(false))
  }

  if (sent) {
    return (
      <section className="daily-card daily-done">
        <div className="daily-card-title">
          <div><span className="daily-card-label">After training</span><h2>What did you do?</h2></div>
          <DoneBadge />
        </div>
        <ul className="daily-done-list">
          {workout.exercises.map((item) => (
            <li key={item.name} className={done[item.name] ? 'is-done' : 'is-skipped'}>
              <span>{done[item.name] ? '✓' : '–'}</span>
              {item.name}
            </li>
          ))}
        </ul>
        {note.trim() && <p className="daily-done-note">{note}</p>}
        {(advice || storedAdvice) && <p className="daily-chili-reply">{advice || storedAdvice}</p>}
      </section>
    )
  }

  return (
    <form className="daily-card daily-form" onSubmit={submit}>
      <div className="daily-card-title">
        <div><span className="daily-card-label">After training</span><h2>What did you do?</h2></div>
      </div>
      <div className="daily-exercises">
        {workout.exercises.map((item) => (
          <label key={item.name} className="daily-check">
            <input
              type="checkbox"
              checked={Boolean(done[item.name])}
              onChange={(event) => setDone((current) => ({ ...current, [item.name]: event.target.checked }))}
            />
            <span>
              <strong>{item.name}</strong>
              <small>{exerciseDetail(item) || item.notes}</small>
            </span>
          </label>
        ))}
      </div>
      <label className="daily-field daily-wide">
        <span>Easy or hard?</span>
        <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} placeholder="Easy / hard, or what to change next time" />
      </label>
      <button className="daily-submit" type="submit" disabled={pending}>
        {pending ? (closesDay ? 'Asking Chili…' : 'Saving…') : closesDay ? 'Submit and close the day' : 'Submit workout'}
      </button>
      {error && <p className="daily-form-error">{error}</p>}
    </form>
  )
}

function SleepForm({
  day,
  hours,
  onLogged,
}: {
  day: string
  hours: number | null
  onLogged: (next?: DailyBriefing) => void
}) {
  const [value, setValue] = useState(hours != null ? String(hours) : '')
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const parsed = Number(value)
    if (pending || !value.trim() || Number.isNaN(parsed)) return
    setPending(true)
    setError(null)
    void logSleep(day, parsed)
      .then((result) => {
        if (result.status === 'logged') {
          setSaved(true)
          onLogged(result.briefing)
        } else {
          setError(result.message)
        }
      })
      .catch(() => setError('Could not save sleep.'))
      .finally(() => setPending(false))
  }

  return (
    <form className="daily-card daily-form" onSubmit={submit}>
      <div className="daily-card-title">
        <div><span className="daily-card-label">Optional</span><h2>Sleep</h2></div>
      </div>
      <label className="daily-field">
        <span>Hours last night (from your watch, or a guess)</span>
        <input
          type="number"
          inputMode="decimal"
          step="0.5"
          min="0"
          max="14"
          value={value}
          onChange={(event) => { setValue(event.target.value); setSaved(false) }}
        />
      </label>
      <button className="daily-submit" type="submit" disabled={pending || !value.trim()}>
        {pending ? 'Saving…' : saved ? 'Update' : 'Save'}
      </button>
      {saved && <p className="daily-form-success">Saved.</p>}
      {error && <p className="daily-form-error" role="alert">{error}</p>}
    </form>
  )
}

function SoberForm({
  day,
  answered,
  savedNote,
  days,
  closesDay,
  onLogged,
}: {
  day: string
  answered: 'yes' | 'no' | null
  savedNote: string | null
  days: number
  closesDay?: boolean
  onLogged: (next?: DailyBriefing) => void
}) {
  const [sober, setSober] = useState(answered !== 'no')
  const [note, setNote] = useState(savedNote ?? '')
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const sent = saved || answered != null
  const [error, setError] = useState<string | null>(null)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending || sent) return
    setPending(true)
    void logSober(day, { sober, note: note.trim() || undefined })
      .then((result) => {
        if (result.status === 'logged') {
          setSaved(true)
          setError(null)
          onLogged(result.briefing)
        } else {
          setError(result.message)
        }
      })
      .catch(() => setError('Could not save sober check-in.'))
      .finally(() => setPending(false))
  }

  if (sent) {
    return (
      <section className="daily-card daily-done">
        <div className="daily-card-title">
          <div><span className="daily-card-label">Evening</span><h2>Sober</h2></div>
          <DoneBadge />
        </div>
        <p className="daily-done-answer">{sober ? 'Yes' : 'No'}</p>
        {note.trim() && <p className="daily-done-note">{note}</p>}
      </section>
    )
  }

  return (
    <form className="daily-card daily-form" onSubmit={submit}>
      <div className="daily-card-title">
        <div><span className="daily-card-label">Evening</span><h2>Sober</h2></div>
      </div>
      <p>Answer this at night. {days} day streak so far.</p>
      <div className="daily-field">
        <span>Stayed sober?</span>
        <div className="daily-choices">
          <button type="button" className={sober ? 'is-selected' : ''} onClick={() => setSober(true)}>yes</button>
          <button type="button" className={!sober ? 'is-selected' : ''} onClick={() => setSober(false)}>no</button>
        </div>
      </div>
      <label className="daily-field daily-wide">
        <span>Note</span>
        <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} />
      </label>
      <button className="daily-submit" type="submit" disabled={pending}>
        {pending ? (closesDay ? 'Asking Chili…' : 'Saving…') : closesDay ? 'Submit and close the day' : 'Submit sober'}
      </button>
      {error && <p className="daily-form-error">{error}</p>}
    </form>
  )
}

function SundayForm({
  briefing,
  closesDay,
  onSaved,
}: {
  briefing: DailyBriefing
  closesDay?: boolean
  onSaved: (next?: DailyBriefing) => void
}) {
  const sunday = briefing.sunday!
  const [weight, setWeight] = useState(sunday.weight_kg?.toString() ?? '')
  const [sameAsLast, setSameAsLast] = useState(false)
  const [note, setNote] = useState(sunday.review_note ?? '')
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const sent = saved || sunday.submitted
  const [error, setError] = useState<string | null>(null)
  const loggedWeight = sunday.weight_kg != null ? sunday.weight_kg.toFixed(1) : weight
  const delta = sunday.delta_kg

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending || sent) return
    setPending(true)
    void logSundayReview(briefing.date, {
      weight_kg: sameAsLast || !weight ? undefined : Number(weight),
      same_as_last: sameAsLast,
      note: note.trim() || undefined,
    })
      .then((next) => {
        setSaved(true)
        setError(null)
        onSaved(next)
      })
      .catch(() => setError('Could not save Sunday review.'))
      .finally(() => setPending(false))
  }

  if (sent) {
    return (
      <section className="daily-card daily-done">
        <div className="daily-card-title">
          <div><span className="daily-card-label">Sunday</span><h2>Weight and week</h2></div>
          <DoneBadge />
        </div>
        <p className="daily-done-answer">
          {loggedWeight ? `${loggedWeight} kg` : 'Weight not entered'}
          {delta != null ? ` · ${delta > 0 ? '+' : ''}${delta.toFixed(1)} kg` : ''}
        </p>
        {note.trim() && <p className="daily-done-note">{note}</p>}
        {sunday.coach_review && (
          <div className="coach-advice">
            <span className="coach-advice-label">Chili says</span>
            <p className="workout-advice">{sunday.coach_review}</p>
          </div>
        )}
      </section>
    )
  }

  return (
    <form className="daily-card daily-form" onSubmit={submit}>
      <div className="daily-card-title">
        <div><span className="daily-card-label">Sunday</span><h2>Weight and week</h2></div>
      </div>
      <p>
        {sunday.previous_weight_kg != null
          ? `Last week: ${sunday.previous_weight_kg.toFixed(1)} kg`
          : 'No previous Sunday weight yet.'}
      </p>
      {sunday.sessions.map((session) => (
        <p key={`${session.date}-${session.kind}`}>
          {session.date.slice(5)} {session.title}: {session.completed ?? 'not logged'}
          {session.note ? ` · ${session.note}` : ''}
        </p>
      ))}
      <label className="daily-field">
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
      <label className="daily-check">
        <input type="checkbox" checked={sameAsLast} onChange={(event) => setSameAsLast(event.target.checked)} />
        <span>Same as last week</span>
      </label>
      <label className="daily-field daily-wide">
        <span>Anything to change next week?</span>
        <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} />
      </label>
      <button className="daily-submit" type="submit" disabled={pending}>
        {pending ? (closesDay ? 'Asking Chili…' : 'Saving…') : closesDay ? 'Submit and close the day' : 'Submit Sunday review'}
      </button>
      {error && <p className="daily-form-error">{error}</p>}
    </form>
  )
}
