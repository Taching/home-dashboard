import { useEffect, useMemo, useState } from 'react'
import {
  askWeeklyCoach,
  fetchTrainingWeeklyAnalysis,
  fetchWeeklyReview,
  recomputeWeeklyAnalysis,
  runWeeklyReview,
} from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import { doneMarkLabel } from '../lib/workoutMatch'
import { PageSkeleton } from '../components/PageSkeleton'
import { PhoneChrome } from '../components/PhoneChrome'
import { PhoneNav } from '../components/PhoneNav'
import type { TrainingWeeklyAnalysis } from '../types'
import '../workout.css'

function mondayOf(day = new Date()) {
  const stamp = day.toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
  const date = new Date(`${stamp}T12:00:00+09:00`)
  const offset = (date.getUTCDay() + 6) % 7
  date.setUTCDate(date.getUTCDate() - offset)
  return date.toISOString().slice(0, 10)
}

function weekFromPath() {
  const match = window.location.pathname.match(/^\/weekly\/(\d{4}-\d{2}-\d{2})/)
  return match?.[1] ?? mondayOf()
}

function EvidenceList({ keys }: { keys?: string[] }) {
  if (!keys?.length) return null
  return (
    <details className="weekly-evidence">
      <summary>Evidence</summary>
      <ul>
        {keys.map((key) => (
          <li key={key}><code>{key}</code></li>
        ))}
      </ul>
    </details>
  )
}

function VerdictSummary({ analysis }: { analysis: TrainingWeeklyAnalysis }) {
  const report = analysis.deterministic_report
  const adherence = analysis.facts?.adherence
  const targets = adherence?.targets
  return (
    <section className="workout-section weekly-verdict" aria-label="Week verdict">
      <p className="weekly-verdict-line">{report.summary_line || 'No report yet.'}</p>
      <p className="workout-advice">
        <strong>{report.main_bottleneck?.cause_code ?? '—'}</strong>
        {' · '}
        {report.main_bottleneck?.statement ?? 'No main bottleneck'}
      </p>
      {targets && (
        <ul className="weekly-stats">
          <li>
            <strong>BJJ</strong>
            <span>
              {targets.bjj?.completed ?? 0}/{targets.bjj?.planned ?? 0}
              {(targets.bjj?.weather_blocked ?? 0) > 0
                ? ` · ${targets.bjj?.weather_blocked} weather-blocked`
                : ''}
            </span>
          </li>
          <li>
            <strong>Strength</strong>
            <span>{targets.strength?.completed ?? 0}/{targets.strength?.planned ?? 0}</span>
          </li>
          <li>
            <strong>Adherence</strong>
            <span>{adherence?.ordinary_adherence_pct ?? '—'}%</span>
          </li>
        </ul>
      )}
      <p className="workout-empty">
        Confidence: {analysis.data_confidence}
        {report.missing_data?.length ? ` · ${report.missing_data.join(' ')}` : ''}
      </p>
      <EvidenceList keys={report.main_bottleneck?.evidence_keys} />
    </section>
  )
}

function DetailSections({ analysis }: { analysis: TrainingWeeklyAnalysis }) {
  const report = analysis.deterministic_report
  const coach = analysis.coach_report
  return (
    <>
      {(report.improved?.length || report.regressed?.length) ? (
        <details className="workout-section weekly-details">
          <summary>Improved / regressed</summary>
          <ul className="weekly-stats">
            {(report.improved ?? []).map((item) => (
              <li key={`up-${item.statement}`}>
                <strong>Up</strong>
                <span>{item.statement}</span>
              </li>
            ))}
            {(report.regressed ?? []).map((item) => (
              <li key={`down-${item.statement}`}>
                <strong>Down</strong>
                <span>{item.statement}</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}

      {report.recurring_problem && (
        <details className="workout-section weekly-details" open>
          <summary>Recurring BJJ problem</summary>
          <p className="workout-advice">{report.recurring_problem.statement}</p>
          <EvidenceList keys={report.recurring_problem.evidence_keys} />
        </details>
      )}

      <details className="workout-section weekly-details">
        <summary>Next-week suggestions ({(report.next_week_suggestions ?? []).length})</summary>
        {(report.next_week_suggestions ?? []).length === 0 && (
          <p className="workout-empty">No suggestions this week.</p>
        )}
        <ul className="weekly-stats">
          {(report.next_week_suggestions ?? []).map((item) => (
            <li key={item.action}>
              <strong>{item.area}</strong>
              <span>{item.action}{item.reason ? ` — ${item.reason}` : ''}</span>
            </li>
          ))}
        </ul>
        {analysis.schedule_change_prefill && (
          <a
            className="workout-plan-link"
            href={`/schedule-change?prefill=${encodeURIComponent(analysis.schedule_change_prefill)}`}
          >
            <strong>Use in schedule change</strong>
            <span>Prefills the form only. Does not submit.</span>
          </a>
        )}
      </details>

      <details className="workout-section weekly-details">
        <summary>Tests for next week ({(report.tests ?? []).length})</summary>
        <ul className="weekly-stats">
          {(report.tests ?? []).map((item) => (
            <li key={item.metric}>
              <strong>{item.metric}</strong>
              <span>{item.target}</span>
            </li>
          ))}
        </ul>
      </details>

      {coach && (
        <section className="workout-section workout-chili">
          <h2>Coach</h2>
          <p className="workout-advice">{coach.verdict}</p>
          {coach.dry_run && <p className="workout-empty">Dry-run: no external AI call was made.</p>}
        </section>
      )}
    </>
  )
}

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

  const heading = useMemo(() => {
    const date = new Date(`${weekStart}T12:00:00+09:00`)
    return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long' }).format(date)
  }, [weekStart])

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
    const date = new Date(`${weekStart}T12:00:00+09:00`)
    date.setUTCDate(date.getUTCDate() + days)
    const next = date.toISOString().slice(0, 10)
    setWeekStart(next)
    window.history.replaceState(null, '', `/weekly/${next}`)
  }

  // Show analyzer as soon as it is ready; do not block on load-cap review.
  if (!analysis && !analysisError) return <PageSkeleton />

  return (
    <div className="workout-page">
      <PhoneChrome />
      <section className="workout-hero">
        <p>Weekly training review</p>
        <h1>Week of {heading}</h1>
        <span>Facts first. Confirm rebuild is the main action; Ask coach is optional.</span>
      </section>
      <div className="workout-week-nav" role="navigation" aria-label="Week">
        <button type="button" className="workout-week-nav-btn" onClick={() => shift(-7)}>Previous</button>
        <button type="button" className="workout-week-nav-btn" onClick={() => shift(7)}>Next</button>
      </div>
      {(error || analysisError || actionError) && (
        <p className="workout-status">{actionError ?? analysisError ?? error}</p>
      )}

      {analysis && <VerdictSummary analysis={analysis} />}

      {review && (
        <section className="workout-section weekly-primary-action">
          <h2>What changes next week</h2>
          <p className="workout-advice">{review.what_changes}</p>
          <ul className="weekly-stats">
            <li><strong>Strength load</strong><span>{Math.round((Number(review.adaptation.strength_load_delta) || 0) * 100)}%</span></li>
            <li><strong>Strength volume</strong><span>{String(review.adaptation.strength_volume_delta ?? 0)}</span></li>
            <li><strong>Zone 2 minutes</strong><span>{String(review.adaptation.zone2_minutes_delta ?? 0)}</span></li>
            <li><strong>Grip sets</strong><span>{String(review.adaptation.grip_sets_delta ?? 0)}</span></li>
          </ul>
          <button type="button" className="workout-primary-button" disabled={pending} onClick={run}>
            {pending ? 'Saving…' : 'Confirm review and rebuild next week'}
          </button>
        </section>
      )}
      {!review && !error && (
        <p className="workout-status">Loading load-cap review…</p>
      )}

      {analysis && <DetailSections analysis={analysis} />}

      <section className="workout-section weekly-secondary-actions">
        <h2>Ask coach about this week</h2>
        <p className="workout-advice">
          Uses the saved facts only. Does not invent metrics or change the schedule.
        </p>
        <button
          type="button"
          className="workout-secondary-button"
          disabled={coachPending || !analysis}
          onClick={askCoach}
        >
          {coachPending ? 'Asking…' : 'Ask coach about this week'}
        </button>
      </section>

      {review && (
        <details className="workout-section weekly-details">
          <summary>Sessions ({review.sessions.length})</summary>
          <div className="workout-checks">
            {review.sessions.map((item) => (
              <a key={item.id} className="workout-plan-link" href={`/workout/${item.id}`}>
                <strong>{item.title}</strong>
                <span>
                  {item.status}
                  {item.miss_reason ? ` · ${item.miss_reason}` : ''}
                  {doneMarkLabel(item.status) ? ` · ${doneMarkLabel(item.status)}` : ''}
                </span>
              </a>
            ))}
            {!review.sessions.length && <p className="workout-empty">No sessions this week.</p>}
          </div>
        </details>
      )}
      <PhoneNav />
    </div>
  )
}
