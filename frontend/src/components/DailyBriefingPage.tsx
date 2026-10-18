import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { closeDailyDay, fetchDailyBriefing, logSleep, logWeeklyCheckIn } from '../lib/api'
import { dailyAnswersFromBriefing } from '../lib/dailyPlan'
import { useLiveResource } from '../hooks/useLiveResource'
import { doneMarkLabel, workoutFormLocked } from '../lib/workoutMatch'
import type { DailyAnswerItem, DailyBriefing, DailyWatch } from '../types'
import { AskCoachButton } from './AskCoachButton'
import { AlertIcon, DumbbellIcon, SlidersIcon } from './icons'
import { PageSkeleton } from './PageSkeleton'
import { TrainingReport } from './TrainingReport'

function formatTime(value: string, allDay = false) {
  if (allDay) return 'All day'
  return new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Tokyo', hour: '2-digit', minute: '2-digit' }).format(new Date(value))
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
      <a className="daily-quick-action is-workout" href="/workout" title="Today's workout">
        <DumbbellIcon size={20} />
        <span>Workout</span>
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
    && !briefing.preview,
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
        <a className="daily-streak" href="/sober"><strong>{briefing.sobriety.days}</strong><span>sober days</span></a>
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
                  <p><a className="daily-session-link" href={`/workout/${workout.id}`}>Program</a></p>
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

        {showWorkoutForm && workout && (
          <TrainingReport
            day={briefing.date}
            workout={workout}
            closesDay={remaining.length === 1 && remaining[0].id === 'workout'}
            onLogged={applyBriefing}
          />
        )}
        <div className="daily-actions">
          {briefing.weekly && (
            <WeeklyForm
              briefing={briefing}
              closesDay={remaining.length === 1 && remaining[0].id === 'weekly'}
              onSaved={applyBriefing}
            />
          )}
          <nav className="daily-page-links" aria-label="Logs">
            <a href="/weight">
              <span>Morning weight</span>
              <strong>{briefing.cut?.today_kg != null ? `${briefing.cut.today_kg.toFixed(1)} kg` : 'Log'}</strong>
            </a>
            <a href="/sober">
              <span>Sober</span>
              <strong>{briefing.sobriety.days} days</strong>
            </a>
          </nav>
          {briefing.watch && <WatchCard watch={briefing.watch} />}
          {briefing.watch?.sleep_hours == null && (
            <SleepForm
              day={briefing.date}
              hours={briefing.sleep?.hours ?? null}
              onLogged={applyBriefing}
            />
          )}
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
          {briefing.weekly?.submitted && (
            <li>
              <strong>Monday check-in</strong>
              <span>
                {briefing.weekly.weight_kg != null ? `7-day ${briefing.weekly.weight_kg.toFixed(1)} kg` : 'Saved'}
                {briefing.weekly.delta_kg != null ? ` · ${signed(briefing.weekly.delta_kg)} kg` : ''}
              </span>
            </li>
          )}
          {briefing.cut?.today_kg != null && (
            <li>
              <strong>Morning weight</strong>
              <span>{briefing.cut.today_kg.toFixed(1)} kg</span>
            </li>
          )}
          <li>
            <strong>Sober</strong>
            <span>{briefing.sobriety.answered === 'no' ? 'Drank' : `${briefing.sobriety.days} days`}</span>
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

function signed(value: number) {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}`
}

function WatchCard({ watch }: { watch: DailyWatch }) {
  if (watch.status === 'waiting') {
    return (
      <section className="daily-card">
        <span className="daily-card-label">Fenix</span>
        <p className="daily-done-note">
          {watch.last_error ? `Garmin sync failed: ${watch.last_error}` : 'Waiting for the first Garmin sync today.'}
        </p>
      </section>
    )
  }
  const stats = [
    watch.sleep_hours != null && `Sleep ${watch.sleep_hours.toFixed(1)} h${watch.sleep_score != null ? ` (score ${watch.sleep_score})` : ''}`,
    watch.resting_hr != null && `Resting HR ${watch.resting_hr}`,
    watch.hrv_last_night != null && `HRV ${watch.hrv_last_night}${watch.hrv_status ? ` · ${watch.hrv_status}` : ''}`,
    watch.body_battery_high != null && `Body Battery ${watch.body_battery_low ?? '?'}–${watch.body_battery_high}`,
    watch.steps != null && `${new Intl.NumberFormat('en-US').format(watch.steps)} steps`,
  ].filter(Boolean)
  return (
    <section className="daily-card">
      <span className="daily-card-label">Fenix</span>
      <p>{stats.join(' · ') || 'No data from the watch yet today.'}</p>
      {watch.hint && <p className="daily-done-note">{watch.hint}</p>}
      {(watch.activities ?? []).map((item) => (
        <p key={`${item.start_local}-${item.name}`} className="daily-done-note">
          {item.start_local?.slice(11, 16)} {item.name} · {item.duration_min} min
          {item.avg_hr != null ? ` · avg HR ${item.avg_hr}` : ''}
          {item.distance_km ? ` · ${item.distance_km} km` : ''}
        </p>
      ))}
    </section>
  )
}

function RatingField({
  label,
  low,
  high,
  value,
  onChange,
}: {
  label: string
  low: string
  high: string
  value: number | null
  onChange: (next: number) => void
}) {
  return (
    <div className="daily-field">
      <span>{label} <small>1 {low} · 5 {high}</small></span>
      <div className="daily-choices is-scale" role="radiogroup" aria-label={label}>
        {[1, 2, 3, 4, 5].map((item) => (
          <button
            key={item}
            type="button"
            role="radio"
            aria-checked={value === item}
            className={value === item ? 'is-selected' : ''}
            onClick={() => onChange(item)}
          >
            {item}
          </button>
        ))}
      </div>
    </div>
  )
}

function WeeklyForm({
  briefing,
  closesDay,
  onSaved,
}: {
  briefing: DailyBriefing
  closesDay?: boolean
  onSaved: (next?: DailyBriefing) => void
}) {
  const weekly = briefing.weekly!
  const [waist, setWaist] = useState(weekly.waist_cm?.toString() ?? '')
  const [energy, setEnergy] = useState<number | null>(weekly.energy)
  const [hunger, setHunger] = useState<number | null>(weekly.hunger)
  const [performance, setPerformance] = useState<number | null>(weekly.bjj_performance)
  const [pain, setPain] = useState(weekly.pain_note ?? '')
  const [note, setNote] = useState(weekly.review_note ?? '')
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const sent = saved || weekly.submitted
  const [error, setError] = useState<string | null>(null)
  const counts = weekly.counts ?? {}
  const ready = energy != null && hunger != null && performance != null
  const weightText = weekly.weight_kg != null
    ? `7-day average ${weekly.weight_kg.toFixed(1)} kg${weekly.delta_kg != null ? ` (${signed(weekly.delta_kg)} kg)` : ''}${weekly.target_kg != null ? ` · trend ${weekly.target_kg.toFixed(1)}` : ''}`
    : 'No morning weigh-ins last week.'
  const doneText = `BJJ ${counts.bjj ?? 0} · Strength ${counts.strength ?? 0} · Cardio ${counts.cardio ?? 0}`
    + (weekly.sleep_average != null ? ` · Sleep ${weekly.sleep_average.toFixed(1)} h` : '')
  const watch = weekly.watch
  const watchText = watch
    ? [
        watch.resting_hr != null && `Resting HR ${watch.resting_hr}`,
        watch.hrv != null && `HRV ${watch.hrv}`,
        watch.sleep_score != null && `Sleep score ${watch.sleep_score}`,
        watch.steps != null && `${new Intl.NumberFormat('en-US').format(watch.steps)} steps/day`,
      ].filter(Boolean).join(' · ')
    : ''

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending || sent || !ready) return
    const parsedWaist = waist.trim() ? Number(waist) : undefined
    setPending(true)
    void logWeeklyCheckIn(briefing.date, {
      energy: energy!,
      hunger: hunger!,
      bjj_performance: performance!,
      waist_cm: parsedWaist != null && !Number.isNaN(parsedWaist) ? parsedWaist : undefined,
      pain_note: pain.trim() || undefined,
      note: note.trim() || undefined,
    })
      .then((next) => {
        setSaved(true)
        setError(null)
        onSaved(next)
      })
      .catch(() => setError('Could not save the Monday check-in.'))
      .finally(() => setPending(false))
  }

  if (sent) {
    return (
      <section className="daily-card daily-done">
        <div className="daily-card-title">
          <div><span className="daily-card-label">Monday</span><h2>Weekly check-in</h2></div>
          <DoneBadge />
        </div>
        <p className="daily-done-answer">{weightText}</p>
        <p className="daily-done-note">
          {doneText}
          {weekly.waist_cm != null ? ` · Waist ${weekly.waist_cm.toFixed(1)} cm` : ''}
        </p>
        {watchText && <p className="daily-done-note">Watch: {watchText}</p>}
        {weekly.kcal_reason && <p className="daily-done-note">Food: {weekly.kcal_reason}</p>}
        {weekly.division?.note && <p className="daily-done-note">{weekly.division.note}</p>}
        {weekly.coach_review && (
          <div className="coach-advice">
            <span className="coach-advice-label">Chili says</span>
            <p className="workout-advice">{weekly.coach_review}</p>
          </div>
        )}
      </section>
    )
  }

  return (
    <form className="daily-card daily-form" onSubmit={submit}>
      <div className="daily-card-title">
        <div><span className="daily-card-label">Monday</span><h2>Weekly check-in</h2></div>
      </div>
      <p>{weightText}</p>
      <p>Last week: {doneText}</p>
      {watchText && <p>Watch: {watchText}</p>}
      {weekly.kcal_reason && <p>Food: {weekly.kcal_reason}</p>}
      {weekly.division?.note && <p>{weekly.division.note}</p>}
      <label className="daily-field">
        <span>Waist at the navel, cm (optional)</span>
        <input
          type="number"
          inputMode="decimal"
          step="0.5"
          min="50"
          max="150"
          value={waist}
          onChange={(event) => setWaist(event.target.value)}
        />
      </label>
      <RatingField label="Energy" low="drained" high="great" value={energy} onChange={setEnergy} />
      <RatingField label="Hunger" low="none" high="constant" value={hunger} onChange={setHunger} />
      <RatingField label="BJJ performance" low="poor" high="sharp" value={performance} onChange={setPerformance} />
      <label className="daily-field daily-wide">
        <span>Any pain or injury?</span>
        <textarea value={pain} onChange={(event) => setPain(event.target.value)} maxLength={500} />
      </label>
      <label className="daily-field daily-wide">
        <span>Anything to change next week?</span>
        <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} />
      </label>
      <button className="daily-submit" type="submit" disabled={pending || !ready}>
        {pending ? (closesDay ? 'Asking Chili…' : 'Saving…') : closesDay ? 'Submit and close the day' : 'Submit check-in'}
      </button>
      {error && <p className="daily-form-error">{error}</p>}
    </form>
  )
}
