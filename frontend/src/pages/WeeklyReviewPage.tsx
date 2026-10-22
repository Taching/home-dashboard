import { useEffect, useMemo, useState } from 'react'
import {
  askWeeklyCoach,
  fetchTrainingWeeklyAnalysis,
  fetchWeeklyReview,
  recomputeWeeklyAnalysis,
  runWeeklyReview,
} from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import { PageSkeleton } from '../components/PageSkeleton'
import { PhoneChrome } from '../components/PhoneChrome'
import { PhoneNav } from '../components/PhoneNav'
import {
  AlertIcon,
  CheckCircleIcon,
  ChevronBackIcon,
  ChevronForwardIcon,
  CloudIcon,
  HalfCircleIcon,
  XCircleIcon,
} from '../components/icons'
import type { TrainingWeeklyAnalysis, WeeklyReview } from '../types'
import '../workout.css'

const TZ = 'Asia/Tokyo'

function stampOf(date: Date) {
  return date.toLocaleDateString('en-CA', { timeZone: TZ })
}

function todayStamp() {
  return stampOf(new Date())
}

function noon(stamp: string) {
  return new Date(`${stamp}T12:00:00+09:00`)
}

function addDays(stamp: string, days: number) {
  const date = noon(stamp)
  date.setUTCDate(date.getUTCDate() + days)
  return date.toISOString().slice(0, 10)
}

function mondayOf(day = new Date()) {
  const date = noon(stampOf(day))
  const offset = (date.getUTCDay() + 6) % 7
  date.setUTCDate(date.getUTCDate() - offset)
  return date.toISOString().slice(0, 10)
}

function weekFromPath() {
  const match = window.location.pathname.match(/^\/weekly\/(\d{4}-\d{2}-\d{2})/)
  return match?.[1] ?? mondayOf()
}

function weekLabel(weekStart: string) {
  const start = noon(weekStart)
  const end = noon(addDays(weekStart, 6))
  const dayOnly = new Intl.DateTimeFormat('en-GB', { day: 'numeric', timeZone: TZ })
  const dayMonth = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: TZ })
  if (start.getUTCMonth() === end.getUTCMonth()) return `${dayOnly.format(start)}–${dayMonth.format(end)}`
  return `${dayMonth.format(start)} – ${dayMonth.format(end)}`
}

// ---------- verdict ----------

const CAUSE_LABELS: Record<string, { label: string; tone: 'good' | 'warn' | 'muted' }> = {
  progressing_as_expected: { label: 'On track', tone: 'good' },
  insufficient_data: { label: 'Not enough data', tone: 'muted' },
  weather_constraint: { label: 'Weather', tone: 'muted' },
  execution: { label: 'Execution', tone: 'warn' },
  recovery: { label: 'Recovery', tone: 'warn' },
  specificity: { label: 'Specificity', tone: 'warn' },
  technical_recurrence: { label: 'Technique', tone: 'warn' },
  possible_program_issue: { label: 'Program', tone: 'warn' },
}

function WeekStepper({ weekStart, onShift }: { weekStart: string; onShift: (days: number) => void }) {
  return (
    <div className="weekly-stepper" role="navigation" aria-label="Week">
      <button type="button" className="workout-week-nav-btn" onClick={() => onShift(-7)} aria-label="Previous week">
        <ChevronBackIcon size={20} />
      </button>
      <h1>{weekLabel(weekStart)}</h1>
      <button type="button" className="workout-week-nav-btn" onClick={() => onShift(7)} aria-label="Next week">
        <ChevronForwardIcon size={20} />
      </button>
    </div>
  )
}

function AdherenceHero({ analysis }: { analysis: TrainingWeeklyAnalysis }) {
  const report = analysis.deterministic_report
  const adherence = analysis.facts?.adherence
  const pct = adherence?.ordinary_adherence_pct
  const controllable = adherence?.controllable_adherence_pct
  const showControllable = Boolean(adherence?.has_weather_blocks) && controllable != null && controllable !== pct
  const cause = report.main_bottleneck?.cause_code ?? ''
  const tone = CAUSE_LABELS[cause] ?? { label: cause.replace(/_/g, ' ') || 'No verdict', tone: 'muted' as const }
  return (
    <section className="weekly-hero" aria-label="Week verdict">
      <div className="weekly-figure">
        <strong>{pct == null ? '—' : `${Math.round(pct)}%`}</strong>
        <span>
          adherence · {analysis.data_confidence} confidence
          {showControllable ? ` · ${Math.round(controllable)}% controllable` : ''}
        </span>
      </div>
      <p className="weekly-hero-cause">
        <span className={`weekly-chip is-${tone.tone}`}>
          {tone.tone === 'good' ? <CheckCircleIcon size={13} /> : <AlertIcon size={13} />}
          {tone.label}
        </span>
        {report.main_bottleneck?.statement && <span>{report.main_bottleneck.statement}</span>}
      </p>
    </section>
  )
}

// ---------- targets ----------

type Targets = NonNullable<NonNullable<TrainingWeeklyAnalysis['facts']['adherence']>['targets']>
type MeterRow = { key: string; label: string; done: number; target: number; targetLabel: string; note?: string }

function meterRows(targets: Targets): MeterRow[] {
  const rows: MeterRow[] = []
  if (targets.bjj) {
    const target = targets.bjj.target ?? 3
    const weather = targets.bjj.weather_blocked ?? 0
    rows.push({
      key: 'bjj', label: 'BJJ', done: targets.bjj.completed, target, targetLabel: String(target),
      note: weather > 0 ? `${weather} weather` : undefined,
    })
  }
  if (targets.strength) {
    const target = targets.strength.target ?? 2
    rows.push({ key: 'strength', label: 'Strength', done: targets.strength.completed, target, targetLabel: String(target) })
  }
  if (targets.easy_cardio) {
    const min = targets.easy_cardio.target_min ?? 1
    const max = targets.easy_cardio.target_max ?? min
    rows.push({
      key: 'cardio', label: 'Cardio', done: targets.easy_cardio.completed, target: min,
      targetLabel: max > min ? `${min}–${max}` : String(min),
    })
  }
  if (targets.rest_days) {
    const min = targets.rest_days.target_min ?? 1
    rows.push({ key: 'rest', label: 'Rest', done: targets.rest_days.count, target: min, targetLabel: String(min) })
  }
  return rows
}

function TargetMeters({ targets }: { targets: Targets }) {
  const rows = meterRows(targets)
  if (!rows.length) return null
  return (
    <section className="workout-section" aria-label="Targets">
      <ul className="weekly-meters">
        {rows.map((row) => {
          const ratio = row.target > 0 ? Math.min(row.done / row.target, 1) : 0
          return (
            <li key={row.key} className="weekly-meter">
              <span className="weekly-meter-label">{row.label}</span>
              <div
                className="weekly-meter-track"
                role="meter"
                aria-label={`${row.label} ${row.done} of ${row.targetLabel}`}
                aria-valuemin={0}
                aria-valuemax={row.target}
                aria-valuenow={Math.min(row.done, row.target)}
              >
                <div className="weekly-meter-fill" style={{ width: `${ratio * 100}%` }} />
              </div>
              <span className="weekly-meter-value">
                {row.done}/{row.targetLabel}
                {row.note && <small> · {row.note}</small>}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}

// ---------- session strip ----------

type StripSession = {
  id: string
  type: string
  status: string
  weather: boolean
  rpe: number | null
  title: string
  date: string
}

type Mark = 'completed' | 'partial' | 'missed' | 'weather' | 'planned'

const MARK_LABELS: Record<Mark, string> = {
  completed: 'completed',
  partial: 'partial',
  missed: 'missed',
  weather: 'weather-blocked',
  planned: 'planned',
}

const MARK_ICONS: Record<Mark, ((props: { size?: number }) => React.ReactElement) | null> = {
  completed: CheckCircleIcon,
  partial: HalfCircleIcon,
  missed: XCircleIcon,
  weather: CloudIcon,
  planned: null,
}

const TYPE_LETTERS: [RegExp, string][] = [
  [/^bjj/, 'B'],
  [/^competition/, 'C'],
  [/^strength_a/, 'SA'],
  [/^strength_b/, 'SB'],
  [/^strength/, 'S'],
  [/^zone/, 'Z2'],
  [/^grip/, 'G'],
  [/^rest|^recovery/, 'R'],
]

function typeLetter(type: string) {
  return TYPE_LETTERS.find(([pattern]) => pattern.test(type))?.[1] ?? type.slice(0, 2).toUpperCase()
}

function markFor(session: StripSession, today: string): Mark {
  if (session.weather) return 'weather'
  if (/^rest|^recovery/.test(session.type)) return session.date <= today ? 'completed' : 'planned'
  switch (session.status) {
    case 'completed':
    case 'recovery':
    case 'competition':
      return 'completed'
    case 'partial':
      return 'partial'
    case 'skipped':
    case 'cancelled':
      return 'missed'
    default:
      return session.date < today ? 'missed' : 'planned'
  }
}

function stripSessions(analysis: TrainingWeeklyAnalysis | null, review: WeeklyReview | null): StripSession[] {
  const facts = new Map((analysis?.facts?.sessions ?? []).map((item) => [item.id, item]))
  const live = review?.sessions ?? []
  if (live.length) {
    return live.filter((item) => item.start_at).map((item) => {
      const fact = facts.get(item.id)
      return {
        id: item.id,
        type: item.planned_type,
        status: item.status,
        weather: fact?.cancellation_reason === 'weather_blocked',
        rpe: item.session_rpe ?? fact?.result?.session_rpe ?? null,
        title: item.title,
        date: stampOf(new Date(item.start_at as string)),
      }
    })
  }
  return [...facts.values()].filter((item) => item.start_at).map((item) => ({
    id: item.id,
    type: item.planned_type,
    status: item.status,
    weather: item.cancellation_reason === 'weather_blocked',
    rpe: item.result?.session_rpe ?? null,
    title: item.planned_type.replace(/_/g, ' '),
    date: stampOf(new Date(item.start_at as string)),
  }))
}

function SessionStrip({ weekStart, sessions }: { weekStart: string; sessions: StripSession[] }) {
  const today = todayStamp()
  const days = Array.from({ length: 7 }, (_, index) => addDays(weekStart, index))
  const narrow = new Intl.DateTimeFormat('en-GB', { weekday: 'narrow', timeZone: TZ })
  const long = new Intl.DateTimeFormat('en-GB', { weekday: 'short', day: 'numeric', month: 'short', timeZone: TZ })
  return (
    <section className="workout-section" aria-label="Sessions by day">
      <ol className="weekly-strip">
        {days.map((date) => {
          const items = sessions.filter((item) => item.date === date)
          const stamp = noon(date)
          const rpe = items.map((item) => item.rpe).filter((value): value is number => value != null)
          return (
            <li key={date} className={`weekly-day${date === today ? ' is-today' : ''}`}>
              <span className="weekly-day-name">{narrow.format(stamp)}</span>
              {items.length ? items.map((item) => {
                const mark = markFor(item, today)
                const Icon = MARK_ICONS[mark]
                const label = `${long.format(stamp)} · ${item.title} · ${MARK_LABELS[mark]}${item.rpe != null ? ` · RPE ${item.rpe}` : ''}`
                return (
                  <a key={item.id} href={`/workout/${item.id}`} className={`weekly-mark is-${mark}`} aria-label={label}>
                    <strong>{typeLetter(item.type)}</strong>
                    {Icon && <Icon size={14} />}
                  </a>
                )
              }) : (
                <span className="weekly-mark is-empty" aria-label={`${long.format(stamp)} · nothing planned`}>·</span>
              )}
              <span className="weekly-day-rpe">{rpe.length ? rpe.join('/') : ' '}</span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}

// ---------- recovery tiles ----------

type Tile = { key: string; label: string; value: string; note?: string }

function KpiRow({ analysis, review }: { analysis: TrainingWeeklyAnalysis; review: WeeklyReview | null }) {
  const recovery = analysis.facts?.recovery
  const garmin = recovery?.garmin
  const body = analysis.facts?.body_trend
  const tiles: Tile[] = []
  if (recovery?.average_sleep_hours != null) {
    const rough = recovery.rough_nights ?? 0
    tiles.push({
      key: 'sleep', label: 'Sleep', value: `${recovery.average_sleep_hours.toFixed(1)} h`,
      note: rough > 0 ? `${rough} rough night${rough === 1 ? '' : 's'}` : undefined,
    })
  }
  if (garmin?.hrv_avg != null) tiles.push({ key: 'hrv', label: 'HRV', value: `${Math.round(garmin.hrv_avg)}` })
  if (garmin?.resting_hr_avg != null) tiles.push({ key: 'rhr', label: 'Resting HR', value: `${Math.round(garmin.resting_hr_avg)}` })
  if (garmin?.body_battery_avg != null) tiles.push({ key: 'battery', label: 'Body battery', value: `${Math.round(garmin.body_battery_avg)}` })
  if (body?.seven_day_average_kg != null) tiles.push({ key: 'weight', label: 'Weight, 7-day', value: `${body.seven_day_average_kg.toFixed(1)} kg` })
  if (review?.average_rpe != null) tiles.push({ key: 'rpe', label: 'Average RPE', value: `${review.average_rpe}` })
  if (!tiles.length) return null
  return (
    <section className="workout-section" aria-label="Recovery">
      <ul className="weekly-kpis">
        {tiles.map((tile) => (
          <li key={tile.key} className="weekly-kpi">
            <span>{tile.label}</span>
            <strong>{tile.value}</strong>
            {tile.note && <small>{tile.note}</small>}
          </li>
        ))}
      </ul>
    </section>
  )
}

// ---------- next week ----------

function DeltaChips({ adaptation }: { adaptation: WeeklyReview['adaptation'] }) {
  const chips = [
    { label: 'Load', value: Math.round((Number(adaptation.strength_load_delta) || 0) * 100), unit: '%' },
    { label: 'Volume', value: Number(adaptation.strength_volume_delta) || 0, unit: '' },
    { label: 'Zone 2', value: Number(adaptation.zone2_minutes_delta) || 0, unit: ' min' },
    { label: 'Grip', value: Number(adaptation.grip_sets_delta) || 0, unit: ' sets' },
  ]
  return (
    <ul className="weekly-deltas" aria-label="Changes for next week">
      {chips.map((chip) => {
        const tone = chip.value > 0 ? 'up' : chip.value < 0 ? 'down' : 'flat'
        return (
          <li key={chip.label} className={`weekly-delta is-${tone}`}>
            <span>{chip.label}</span>
            <strong>{chip.value > 0 ? '+' : ''}{chip.value}{chip.unit}</strong>
          </li>
        )
      })}
    </ul>
  )
}

// ---------- the prose, folded away ----------

function Details({ analysis, review }: { analysis: TrainingWeeklyAnalysis; review: WeeklyReview | null }) {
  const report = analysis.deterministic_report
  const suggestions = report.next_week_suggestions ?? []
  const tests = report.tests ?? []
  const evidence = report.main_bottleneck?.evidence_keys ?? []
  return (
    <details className="workout-section weekly-details">
      <summary>Details</summary>
      <div className="weekly-details-body">
        {review?.what_changes && <p className="workout-advice">{review.what_changes}</p>}
        {report.summary_line && <p className="workout-advice">{report.summary_line}</p>}
        {(report.improved?.length || report.regressed?.length) ? (
          <>
            <h3>Improved / regressed</h3>
            <ul>
              {(report.improved ?? []).map((item) => <li key={`up-${item.statement}`}>Up: {item.statement}</li>)}
              {(report.regressed ?? []).map((item) => <li key={`down-${item.statement}`}>Down: {item.statement}</li>)}
            </ul>
          </>
        ) : null}
        {report.recurring_problem && (
          <>
            <h3>Recurring BJJ problem</h3>
            <p>{report.recurring_problem.statement}</p>
          </>
        )}
        <h3>Next week ({suggestions.length})</h3>
        {suggestions.length ? (
          <ul>
            {suggestions.map((item) => (
              <li key={item.action}>
                <strong>{item.area}</strong>: {item.action}{item.reason ? ` (${item.reason})` : ''}
              </li>
            ))}
          </ul>
        ) : <p>No suggestions this week.</p>}
        {analysis.schedule_change_prefill && (
          <a
            className="workout-plan-link"
            href={`/schedule-change?prefill=${encodeURIComponent(analysis.schedule_change_prefill)}`}
          >
            <strong>Use in schedule change</strong>
            <span>Prefills the form only. Does not submit.</span>
          </a>
        )}
        {tests.length > 0 && (
          <>
            <h3>Tests for next week</h3>
            <ul>{tests.map((item) => <li key={item.metric}><strong>{item.metric}</strong>: {item.target}</li>)}</ul>
          </>
        )}
        {report.missing_data?.length ? (
          <>
            <h3>Missing data</h3>
            <ul>{report.missing_data.map((item) => <li key={item}>{item}</li>)}</ul>
          </>
        ) : null}
        {evidence.length > 0 && (
          <details className="weekly-evidence">
            <summary>Evidence</summary>
            <ul>{evidence.map((key) => <li key={key}><code>{key}</code></li>)}</ul>
          </details>
        )}
      </div>
    </details>
  )
}

// ---------- page ----------

export function WeeklyReviewPage() {
  const [weekStart, setWeekStart] = useState(weekFromPath)
  const reviewQueryKey = useMemo(() => ['weekly-review', weekStart] as const, [weekStart])
  const analysisQueryKey = useMemo(() => ['weekly-analysis', weekStart] as const, [weekStart])
  const { data: review, error, setData: setReview } = useLiveResource(
    (signal) => fetchWeeklyReview(weekStart, signal),
    { queryKey: reviewQueryKey },
  )
  const { data: analysis, error: analysisError, setData: setAnalysis } = useLiveResource(
    (signal) => fetchTrainingWeeklyAnalysis(weekStart, signal),
    { queryKey: analysisQueryKey },
  )
  const [pending, setPending] = useState(false)
  const [coachPending, setCoachPending] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    document.documentElement.classList.add('is-workout')
    document.title = 'Weekly review · Chili'
    return () => document.documentElement.classList.remove('is-workout')
  }, [])

  const run = () => {
    setPending(true)
    setActionError(null)
    void Promise.all([
      runWeeklyReview(weekStart),
      recomputeWeeklyAnalysis(weekStart),
    ])
      .then(([nextReview, nextAnalysis]) => {
        setReview(nextReview)
        setAnalysis(nextAnalysis)
      })
      .catch(() => setActionError('Could not run weekly analysis.'))
      .finally(() => setPending(false))
  }

  const askCoach = () => {
    setCoachPending(true)
    setActionError(null)
    void askWeeklyCoach(weekStart)
      .then((result) => {
        if (result.analysis) setAnalysis(result.analysis)
        if (result.status === 'unavailable' || result.status === 'validation_failed') {
          setActionError(result.message ?? 'Coach unavailable. Deterministic report stays visible.')
        }
      })
      .catch(() => setActionError('Coach unavailable. Deterministic report stays visible.'))
      .finally(() => setCoachPending(false))
  }

  const shift = (days: number) => {
    const next = addDays(weekStart, days)
    setWeekStart(next)
    window.history.replaceState(null, '', `/weekly/${next}`)
  }

  // Show analyzer as soon as it is ready; do not block on load-cap review.
  if (!analysis && !analysisError) return <PageSkeleton />

  const sessions = stripSessions(analysis, review)
  const targets = analysis?.facts?.adherence?.targets
  const coach = analysis?.coach_report ?? null

  return (
    <div className="workout-page">
      <PhoneChrome />
      <WeekStepper weekStart={weekStart} onShift={shift} />
      {(error || analysisError || actionError) && (
        <p className="workout-status">{actionError ?? analysisError ?? error}</p>
      )}

      {analysis && <AdherenceHero analysis={analysis} />}
      {targets && <TargetMeters targets={targets} />}
      {(sessions.length > 0 || review) && <SessionStrip weekStart={weekStart} sessions={sessions} />}
      {analysis && <KpiRow analysis={analysis} review={review} />}

      {review ? (
        <section className="workout-section weekly-primary-action">
          <h2>Next week</h2>
          <DeltaChips adaptation={review.adaptation} />
          <button type="button" className="workout-primary-button" disabled={pending} onClick={run}>
            {pending ? 'Saving…' : 'Confirm review and rebuild next week'}
          </button>
        </section>
      ) : !error && (
        <p className="workout-status">Loading load-cap review…</p>
      )}

      <section className="workout-section weekly-secondary-actions">
        <button
          type="button"
          className="workout-secondary-button"
          disabled={coachPending || !analysis}
          onClick={askCoach}
        >
          {coachPending ? 'Asking…' : 'Ask coach about this week'}
        </button>
        {coach && (
          <div className="weekly-coach">
            <p className="workout-advice">{coach.verdict}</p>
            {coach.dry_run && <p className="workout-empty">Dry run: no external AI call was made.</p>}
          </div>
        )}
      </section>

      {analysis && <Details analysis={analysis} review={review} />}
      <PhoneNav />
    </div>
  )
}
