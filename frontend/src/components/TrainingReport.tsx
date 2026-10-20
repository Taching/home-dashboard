import { useEffect, useState, type FormEvent } from 'react'
import { logDailyWorkout, putBjjAnalysis, putExerciseResults } from '../lib/api'
import { doneMarkLabel, workoutFormLocked } from '../lib/workoutMatch'
import type { DailyBriefing, PlannedExercise, PlannedWorkout } from '../types'
import { AskCoachButton } from './AskCoachButton'

const TECHNIQUE = [
  ['good', 'Good'],
  ['shaky', 'Shaky'],
  ['breakdown', 'Breakdown'],
] as const

const BJJ_FAILURES = [
  ['grip_lost', 'Grip lost'],
  ['frame_late', 'Frame late'],
  ['posture_broken', 'Posture broken'],
  ['bad_angle', 'Bad angle'],
  ['off_balance_failed', 'Could not off-balance'],
  ['technique_forgotten', 'Technique forgotten'],
  ['poor_decision', 'Poor decision'],
  ['strength_limited', 'Strength limited'],
  ['cardio_limited', 'Cardio limited'],
  ['grip_fatigue', 'Grip fatigue'],
  ['opponent_skill', 'Opponent better'],
  ['other', 'Other'],
] as const

function parseReps(value: string): number[] {
  return value
    .split(/[\/,\s]+/)
    .map((part) => Number(part))
    .filter((n) => Number.isFinite(n) && n > 0 && n <= 100)
    .slice(0, 20)
}

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

const INTENSITY = [
  ['easy', 'Easy'],
  ['normal', 'Normal'],
  ['hard', 'Hard'],
] as const

const RPE_CHOICES = [6, 7, 8, 9] as const
const INTERVAL_NAME = 'Stationary bike intervals'
const UNTRACKED = new Set([
  'Stationary bike warm-up',
  INTERVAL_NAME,
  'Easy cardio',
  'Zone 2 cardio',
])
// Smallest real jump per exercise (dumbbells, bells, cable stack); barbells default to 2.5.
const LOAD_STEP: Record<string, number> = {
  'Dumbbell Bench Press': 2,
  'Bulgarian Split Squat': 2,
  'Kettlebell Swing': 4,
  'Military Press': 1,
  'Weighted Pull-up': 1,
}

function exerciseDetail(item: PlannedExercise) {
  return [
    item.load_value != null && `${item.load_value}${item.load_unit ?? ''}`,
    item.sets && item.reps && `${item.sets}×${item.reps}`,
    item.sets && !item.reps && `${item.sets} sets`,
    item.duration_seconds && `${Math.round(item.duration_seconds / 60)} min`,
  ].filter(Boolean).join(' · ')
}

function isBjj(type: string) {
  return type.startsWith('bjj_') || type === 'competition'
}

function defaultIntensity(type: string): 'easy' | 'normal' | 'hard' {
  if (type === 'bjj_hard' || type === 'competition') return 'hard'
  if (type === 'bjj_technical') return 'easy'
  return 'normal'
}

function loadStep(name: string) {
  return LOAD_STEP[name] ?? 2.5
}

function roundLoad(value: number, step: number) {
  return Math.round(Math.round(value / step) * step * 10) / 10
}

function formatLoad(value: number) {
  return Number.isInteger(value) ? String(value) : String(value)
}

function isTrackedLift(item: PlannedExercise) {
  return !UNTRACKED.has(item.name) && (item.load_value != null || Boolean(item.sets && item.reps))
}

function intervalExercise(workout: PlannedWorkout) {
  return workout.exercises.find((item) => item.name === INTERVAL_NAME) ?? null
}

function initialLifts(workout: PlannedWorkout) {
  const saved = new Map((workout.exercise_results ?? []).map((item) => [item.name, item]))
  return Object.fromEntries(workout.exercises.filter(isTrackedLift).map((item) => {
    const previous = saved.get(item.name)
    const load = previous?.actual_load ?? item.load_value
    const technique = previous?.technique === 'clean' ? 'good' : (previous?.technique ?? 'good')
    return [item.name, {
      load: load == null ? '' : formatLoad(load),
      rpe: previous?.rpe != null ? String(previous.rpe) : '8',
      reps: previous?.actual_reps ?? (item.sets && item.reps ? Array.from({ length: item.sets }, () => String(item.reps).split('-').pop()).join(' / ') : ''),
      technique,
      pain: Boolean(previous?.pain),
    }]
  }))
}

function initialWatts(workout: PlannedWorkout) {
  const interval = intervalExercise(workout)
  const count = Math.min(12, Math.max(1, interval?.sets || 10))
  const values = Array.from({ length: count }, () => '')
  for (const metric of workout.metrics ?? []) {
    if (metric.metric_type !== 'bike_watts' || metric.sequence == null) continue
    const index = metric.sequence - 1
    if (index >= 0 && index < values.length) values[index] = String(metric.value)
  }
  return values
}

export function TrainingReport({
  day,
  workout,
  closesDay = false,
  coachSessionId,
  onLogged,
}: {
  day: string
  workout: PlannedWorkout
  closesDay?: boolean
  coachSessionId?: string
  onLogged?: (next?: DailyBriefing) => void
}) {
  const type = workout.planned_type
  const bjj = isBjj(type)
  const locked = workoutFormLocked(workout.status)
  const lifts = workout.exercises.filter(isTrackedLift)
  const interval = intervalExercise(workout)
  const [status, setStatus] = useState<'completed' | 'partial' | 'skipped'>(
    locked && (workout.status === 'partial' || workout.status === 'skipped') ? workout.status : 'completed',
  )
  const [done, setDone] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(workout.exercises.map((item) => [item.name, status === 'completed' || Boolean(item.done)])),
  )
  const [missReason, setMissReason] = useState(workout.miss_reason ?? 'WORK')
  const [rounds, setRounds] = useState(String(workout.result?.bjj_rounds ?? workout.target_rounds ?? ''))
  const [intensity, setIntensity] = useState<'easy' | 'normal' | 'hard'>(() => {
    const savedIntensity = workout.result?.perceived_intensity
    if (savedIntensity === 'easy' || savedIntensity === 'normal' || savedIntensity === 'hard') return savedIntensity
    return defaultIntensity(type)
  })
  const [liftReport, setLiftReport] = useState(initialLifts(workout))
  const [watts, setWatts] = useState(initialWatts(workout))
  const [note, setNote] = useState(locked ? (workout.notes ?? '') : '')
  const [mainFocus, setMainFocus] = useState('')
  const [problemPosition, setProblemPosition] = useState('')
  const [primaryFailure, setPrimaryFailure] = useState('')
  const [showBjjExtra, setShowBjjExtra] = useState(false)
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sent = saved || locked
  const showDetails = !bjj && status !== 'skipped'
  const sessionId = coachSessionId || workout.id

  useEffect(() => {
    if (window.location.hash !== '#report') return
    document.getElementById('report')?.scrollIntoView({ block: 'start' })
  }, [])

  const choose = (next: 'completed' | 'partial' | 'skipped') => {
    setStatus(next)
    if (next === 'completed') {
      setDone(Object.fromEntries(workout.exercises.map((item) => [item.name, true])))
    }
    if (next === 'skipped') {
      setDone(Object.fromEntries(workout.exercises.map((item) => [item.name, false])))
    }
  }

  const liftIncluded = (name: string) => status === 'completed' || Boolean(done[name])

  const changeLoad = (item: PlannedExercise, direction: -1 | 1) => {
    const step = loadStep(item.name)
    setLiftReport((current) => {
      const existing = Number(current[item.name]?.load)
      const base = Number.isFinite(existing) ? existing : (item.load_value ?? 0)
      const next = Math.max(0, roundLoad(base + direction * step, step))
      return { ...current, [item.name]: { ...current[item.name], load: formatLoad(next) } }
    })
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending || sent) return
    setPending(true)
    setError(null)
    const exercises = workout.exercises.map((item) => {
      const included = status === 'completed' ? true : status === 'skipped' ? false : Boolean(done[item.name])
      const report = liftReport[item.name]
      const load = report ? Number(report.load) : NaN
      const rpe = report ? Number(report.rpe) : NaN
      return {
        name: item.name,
        done: included,
        actual_load: included && item.load_value != null && Number.isFinite(load) ? load : undefined,
        rpe: included && isTrackedLift(item) && Number.isFinite(rpe) ? rpe : undefined,
      }
    })
    const intervalWatts = interval && status !== 'skipped' && (status === 'completed' || done[interval.name])
      ? watts.flatMap((value, index) => {
        const wattsValue = Number(value)
        return value.trim() && Number.isFinite(wattsValue) && wattsValue > 0
          ? [{ round: index + 1, watts: wattsValue }]
          : []
      })
      : undefined
    void logDailyWorkout(day, {
      kind: type,
      status,
      exercises,
      note: note.trim() || undefined,
      miss_reason: status === 'skipped' ? missReason : undefined,
      bjj_rounds: bjj && status !== 'skipped' && rounds.trim() ? Number(rounds) : undefined,
      perceived_intensity: bjj && status !== 'skipped' ? intensity : undefined,
      interval_watts: intervalWatts,
    })
      .then(async (result) => {
        if (result.status !== 'logged') {
          setError(result.message)
          return
        }
        // M2 structured logs (compact reps/technique/pain + optional BJJ analysis).
        // Missing optional fields stay absent — never invent zeros.
        if (!bjj && status !== 'skipped') {
          const structured = lifts.map((item, index) => {
            const included = status === 'completed' ? true : Boolean(done[item.name])
            const report = liftReport[item.name]
            const load = report ? Number(report.load) : NaN
            const rpe = report ? Number(report.rpe) : NaN
            const reps = report?.reps ? parseReps(report.reps) : []
            return {
              sort_order: index,
              planned_exercise_name: item.name,
              performed_exercise_name: item.name,
              planned_sets: item.sets ?? undefined,
              reps_per_set: included && reps.length ? reps : undefined,
              load_kg: included && item.load_value != null && Number.isFinite(load) ? load : undefined,
              rpe: included && Number.isFinite(rpe) ? rpe : undefined,
              technique_quality: included ? (report?.technique || undefined) : undefined,
              pain_flag: included ? Boolean(report?.pain) : false,
              status: included ? 'completed' : 'skipped',
            }
          })
          await putExerciseResults(sessionId, structured).catch(() => undefined)
        }
        if (bjj && status !== 'skipped' && (mainFocus || problemPosition || primaryFailure)) {
          await putBjjAnalysis(sessionId, {
            main_focus: mainFocus.trim() || undefined,
            problem_position: problemPosition.trim() || undefined,
            primary_failure_code: primaryFailure || undefined,
          }).catch(() => undefined)
        }
        setSaved(true)
        onLogged?.(result.briefing)
      })
      .catch(() => setError('Could not save. Try again.'))
      .finally(() => setPending(false))
  }

  const liftLines = lifts
    .filter((item) => liftIncluded(item.name))
    .map((item) => {
      const report = liftReport[item.name]
      const load = report?.load ? `${report.load}${item.load_unit ? ` ${item.load_unit}` : ''}` : null
      return [item.name, load, report?.rpe ? `RPE ${report.rpe}` : null].filter(Boolean).join(' · ')
    })
  const wattLine = watts.filter((value) => value.trim()).join(', ')
  const summary = [
    doneMarkLabel(sent ? (saved ? status : workout.status) : status),
    bjj && status !== 'skipped' && rounds.trim() ? `${rounds} rounds` : null,
    bjj && status !== 'skipped' ? INTENSITY.find(([value]) => value === intensity)?.[1] : null,
    status === 'skipped' ? MISS_REASONS.find(([value]) => value === missReason)?.[1] : null,
  ].filter(Boolean).join(' · ')

  if (sent) {
    return (
      <section id="report" className="daily-card daily-report daily-done">
        <div className="daily-card-title">
          <div>
            <span className="daily-card-label">Training</span>
            <h2>What did you do?</h2>
          </div>
          <span className="daily-done-badge" aria-label="Saved">✓</span>
        </div>
        <p className="daily-done-answer">{summary}</p>
        {liftLines.length > 0 && (
          <ul className="daily-saved-lifts">
            {liftLines.map((line) => <li key={line}>{line}</li>)}
          </ul>
        )}
        {wattLine && <p className="daily-done-note">Intervals {wattLine} W</p>}
        {note.trim() && <p className="daily-done-note">{note}</p>}
        {coachSessionId && <AskCoachButton sessionId={coachSessionId} />}
      </section>
    )
  }

  return (
    <form id="report" className="daily-card daily-form daily-report" onSubmit={submit}>
      <div className="daily-card-title">
        <div>
          <span className="daily-card-label">Training</span>
          <h2>What did you do?</h2>
        </div>
      </div>
      <p className="daily-report-session">{workout.title}</p>
      <div className="daily-report-choices" role="radiogroup" aria-label="How the session went">
        {([
          ['completed', 'Did it'],
          ['partial', 'Part of it'],
          ['skipped', 'Missed'],
        ] as const).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`${status === value ? 'is-selected' : ''}${value === 'skipped' ? ' is-missed' : ''}`}
            aria-pressed={status === value}
            onClick={() => choose(value)}
          >
            {label}
          </button>
        ))}
      </div>

          {bjj && status !== 'skipped' && (
        <>
          <div className="daily-field">
            <span>Rounds</span>
            <div className="daily-rounds">
              <button type="button" aria-label="Fewer rounds" onClick={() => setRounds((current) => String(Math.max(0, (Number(current) || 0) - 1)))}>−</button>
              <input
                inputMode="numeric"
                aria-label="Rounds"
                value={rounds}
                onChange={(event) => setRounds(event.target.value.replace(/[^\d]/g, '').slice(0, 2))}
              />
              <button type="button" aria-label="More rounds" onClick={() => setRounds((current) => String(Math.min(20, (Number(current) || 0) + 1)))}>+</button>
            </div>
          </div>
          <div className="daily-field">
            <span>How it felt</span>
            <div className="daily-report-choices" role="radiogroup" aria-label="How it felt">
              {INTENSITY.map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={intensity === value ? 'is-selected' : ''}
                  aria-pressed={intensity === value}
                  onClick={() => setIntensity(value)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>
          <button
            type="button"
            className="daily-report-hint"
            onClick={() => setShowBjjExtra((current) => !current)}
          >
            {showBjjExtra ? 'Hide optional BJJ review' : 'Optional BJJ review (focus / failure)'}
          </button>
          {showBjjExtra && (
            <>
              <label className="daily-field">
                <span>Main focus</span>
                <input
                  value={mainFocus}
                  onChange={(event) => setMainFocus(event.target.value.slice(0, 200))}
                  placeholder="e.g. half guard sweeps"
                />
              </label>
              <label className="daily-field">
                <span>Problem position</span>
                <input
                  value={problemPosition}
                  onChange={(event) => setProblemPosition(event.target.value.slice(0, 100))}
                  placeholder="e.g. bottom half guard"
                />
              </label>
              <label className="daily-field">
                <span>Primary failure</span>
                <select value={primaryFailure} onChange={(event) => setPrimaryFailure(event.target.value)}>
                  <option value="">—</option>
                  {BJJ_FAILURES.map(([value, label]) => (
                    <option key={value} value={value}>{label}</option>
                  ))}
                </select>
              </label>
            </>
          )}
        </>
      )}

      {status === 'partial' && workout.exercises.length > 0 && (
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
                <small>{exerciseDetail(item)}</small>
              </span>
            </label>
          ))}
        </div>
      )}

      {showDetails && lifts.some((item) => liftIncluded(item.name)) && (
        <div className="daily-lifts">
          <p className="daily-report-hint">Weight is what you lifted. RPE 8 keeps the next session. 6 goes up, 9 comes down.</p>
          {lifts.filter((item) => liftIncluded(item.name)).map((item) => (
            <div key={item.name} className="daily-lift">
              <div>
                <strong>{item.name}</strong>
                <small>{exerciseDetail(item)}</small>
              </div>
              {item.load_value != null && (
                <div className="daily-field">
                  <span>Weight{item.load_unit ? ` (${item.load_unit})` : ''}</span>
                  <div className="daily-rounds">
                    <button type="button" aria-label={`Lighter ${item.name}`} onClick={() => changeLoad(item, -1)}>−</button>
                    <input
                      inputMode="decimal"
                      aria-label={`${item.name} weight`}
                      value={liftReport[item.name]?.load ?? ''}
                      onChange={(event) => {
                        const load = event.target.value.replace(/[^\d.]/g, '').slice(0, 6)
                        setLiftReport((current) => ({ ...current, [item.name]: { ...current[item.name], load } }))
                      }}
                    />
                    <button type="button" aria-label={`Heavier ${item.name}`} onClick={() => changeLoad(item, 1)}>+</button>
                  </div>
                </div>
              )}
              <label className="daily-field">
                <span>Reps (e.g. 8 / 8 / 7)</span>
                <input
                  inputMode="text"
                  aria-label={`${item.name} reps`}
                  value={liftReport[item.name]?.reps ?? ''}
                  placeholder={item.sets ? Array.from({ length: item.sets }, () => item.reps ?? '8').join(' / ') : '8 / 8 / 7'}
                  onChange={(event) => {
                    const reps = event.target.value.slice(0, 40)
                    setLiftReport((current) => ({ ...current, [item.name]: { ...current[item.name], reps } }))
                  }}
                />
              </label>
              <div className="daily-field">
                <span>RPE</span>
                <div className="daily-report-choices daily-rpe" role="radiogroup" aria-label={`${item.name} RPE`}>
                  {RPE_CHOICES.map((value) => (
                    <button
                      key={value}
                      type="button"
                      className={liftReport[item.name]?.rpe === String(value) ? 'is-selected' : ''}
                      aria-pressed={liftReport[item.name]?.rpe === String(value)}
                      onClick={() => setLiftReport((current) => ({
                        ...current,
                        [item.name]: { ...current[item.name], rpe: String(value) },
                      }))}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>
              <div className="daily-field">
                <span>Technique</span>
                <div className="daily-report-choices" role="radiogroup" aria-label={`${item.name} technique`}>
                  {TECHNIQUE.map(([value, label]) => (
                    <button
                      key={value}
                      type="button"
                      className={liftReport[item.name]?.technique === value ? 'is-selected' : ''}
                      aria-pressed={liftReport[item.name]?.technique === value}
                      onClick={() => setLiftReport((current) => ({
                        ...current,
                        [item.name]: { ...current[item.name], technique: value },
                      }))}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
              <label className="daily-check">
                <input
                  type="checkbox"
                  checked={Boolean(liftReport[item.name]?.pain)}
                  onChange={(event) => setLiftReport((current) => ({
                    ...current,
                    [item.name]: { ...current[item.name], pain: event.target.checked },
                  }))}
                />
                <span>Pain during this exercise</span>
              </label>
            </div>
          ))}
        </div>
      )}

      {showDetails && interval && liftIncluded(interval.name) && (
        <div className="daily-field">
          <span>Interval watts</span>
          <p className="daily-report-hint">{interval.sets ?? watts.length} hard rounds. Leave a round blank if you skipped it.</p>
          <div className="daily-watts">
            {watts.map((value, index) => (
              <input
                key={index}
                inputMode="numeric"
                aria-label={`Round ${index + 1} watts`}
                placeholder={String(index + 1)}
                value={value}
                onChange={(event) => {
                  const next = event.target.value.replace(/[^\d]/g, '').slice(0, 4)
                  setWatts((current) => current.map((item, itemIndex) => itemIndex === index ? next : item))
                }}
              />
            ))}
          </div>
        </div>
      )}

      {status === 'skipped' && (
        <label className="daily-field">
          <span>Why</span>
          <select value={missReason} onChange={(event) => setMissReason(event.target.value)}>
            {MISS_REASONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select>
        </label>
      )}

      <label className="daily-field">
        <span>Note</span>
        <textarea
          value={note}
          onChange={(event) => setNote(event.target.value)}
          maxLength={500}
          placeholder="Easy or hard, or what to change"
        />
      </label>
      <button className="daily-submit" type="submit" disabled={pending}>
        {pending ? 'Saving…' : closesDay ? 'Save and close the day' : 'Save'}
      </button>
      {error && <p className="daily-form-error" role="alert">{error}</p>}
    </form>
  )
}
