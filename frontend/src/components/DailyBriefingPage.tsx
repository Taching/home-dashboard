import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { fetchDailyBriefing, logDailyWorkout, logSober, logSundayReview } from '../lib/api'
import { doneMarkLabel, workoutAlreadyLogged } from '../lib/workoutMatch'
import type { DailyBriefing, PlannedExercise } from '../types'

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

function DoneBadge() {
  return <span className="daily-done-badge" aria-label="Done">✓</span>
}

export function DailyBriefingPage({ day }: { day: string }) {
  const previewWorkout = useMemo(() => new URLSearchParams(window.location.search).get('preview'), [])
  const [briefing, setBriefing] = useState<DailyBriefing | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    fetchDailyBriefing(day, previewWorkout ?? undefined)
      .then((data) => {
        setBriefing(data)
        setError(null)
        document.title = `Daily · ${data.date}`
      })
      .catch(() => setError('The daily briefing could not be loaded.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    load()
  }, [day, previewWorkout])

  const title = useMemo(() => new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Tokyo', weekday: 'long', day: 'numeric', month: 'long',
  }).format(new Date(`${day}T12:00:00+09:00`)), [day])

  if (loading) return <main className="daily-briefing-shell daily-loading">Loading your day…</main>
  if (!briefing) return <main className="daily-briefing-shell daily-loading">{error}</main>
  const workout = briefing.workout
  const workoutDone = workout ? doneMarkLabel(workout.status) : null

  return (
    <main className="daily-briefing-shell">
      <header className="daily-hero">
        <div>
          <span className="daily-kicker">Chili daily plan</span>
          <h1>{title}</h1>
          {briefing.today?.headline && <p className="daily-plan-headline">{briefing.today.headline}</p>}
          {briefing.preview && <span className="daily-preview-badge">Dry run · saved plan unchanged</span>}
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
                  <h2>{workout.title}</h2>
                  {workoutDone ? <DoneBadge /> : (
                    <span>{workout.is_all_day ? 'Recovery day' : `${workout.estimated_minutes} min · ${workout.intensity}`}</span>
                  )}
                </div>
                {workoutDone && (
                  <span>{workoutDone}{workout.is_all_day ? '' : ` · ${workout.estimated_minutes} min · ${workout.intensity}`}</span>
                )}
                <p>{workout.reason}</p>
                {workout.coach_focus.length > 0 && <ul>{workout.coach_focus.map((focus) => <li key={focus}>{focus}</li>)}</ul>}
                {briefing.last_adjustment?.how?.length ? (
                  <div className="daily-plan-change">
                    <strong>How Chili changed it</strong>
                    <ul>{briefing.last_adjustment.how.map((item) => <li key={item}>{item}</li>)}</ul>
                    <strong>Why</strong>
                    <ul>{briefing.last_adjustment.why.map((item) => <li key={item}>{item}</li>)}</ul>
                  </div>
                ) : null}
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
            <p>{briefing.advice ?? 'Chili answers after a workout or Sunday review.'}</p>
          </section>
        </div>

        <div className="daily-summary-stack">
          {workout && workout.planned_type !== 'rest' && !briefing.preview && (
            <WorkoutForm day={briefing.date} workout={workout} storedAdvice={briefing.advice} onLogged={load} />
          )}
          {briefing.sunday && <SundayForm briefing={briefing} onSaved={setBriefing} />}
          <SoberForm
            day={briefing.date}
            answered={briefing.sobriety.answered}
            savedNote={briefing.sobriety.note}
            days={briefing.sobriety.days}
            onLogged={load}
          />
          {error && <p className="daily-form-error" role="alert">{error}</p>}
        </div>
      </div>
    </main>
  )
}

function WorkoutForm({
  day,
  workout,
  storedAdvice,
  onLogged,
}: {
  day: string
  workout: NonNullable<DailyBriefing['workout']>
  storedAdvice?: string | null
  onLogged: () => void
}) {
  const [done, setDone] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(workout.exercises.map((item) => [item.name, Boolean(item.done)])),
  )
  const [note, setNote] = useState(workout.notes ?? '')
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const [advice, setAdvice] = useState<string | null>(null)
  const sent = saved || workoutAlreadyLogged(workout.status)
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
          onLogged()
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
      <button className="daily-submit" type="submit" disabled={pending}>{pending ? 'Asking Chili…' : 'Submit workout'}</button>
      {error && <p className="daily-form-error">{error}</p>}
    </form>
  )
}

function SoberForm({
  day,
  answered,
  savedNote,
  days,
  onLogged,
}: {
  day: string
  answered: 'yes' | 'no' | null
  savedNote: string | null
  days: number
  onLogged: () => void
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
          onLogged()
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
      <button className="daily-submit" type="submit" disabled={pending}>{pending ? 'Saving…' : 'Submit sober'}</button>
      {error && <p className="daily-form-error">{error}</p>}
    </form>
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
      <button className="daily-submit" type="submit" disabled={pending}>{pending ? 'Saving…' : 'Submit Sunday review'}</button>
      {error && <p className="daily-form-error">{error}</p>}
    </form>
  )
}
