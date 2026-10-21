import { useEffect, useMemo, useState, type FormEvent, type ReactNode } from 'react'
import chiliLogo from '../assets/chili-logo.svg'
import { fetchDailyBriefing, fetchWellbeingHistory, logSober, logWeight } from '../lib/api'
import { useLiveResource } from '../hooks/useLiveResource'
import { PhoneNav } from '../components/PhoneNav'
import type { DailyCut, WellbeingHistory } from '../types'

function todayStamp() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
}

function dayLabel(value: string) {
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: 'Asia/Tokyo' })
    .format(new Date(`${value}T12:00:00+09:00`))
}

function PageFrame({ title, kicker, children }: { title: string; kicker: string; children: ReactNode }) {
  useEffect(() => {
    document.documentElement.classList.add('is-daily')
    document.title = `${title} · Chili`
    return () => document.documentElement.classList.remove('is-daily')
  }, [title])

  return (
    <main className="daily-briefing-shell">
      <header className="daily-hero">
        <div>
          <span className="daily-kicker">
            <img src={chiliLogo} alt="" className="daily-kicker-mark" />
            {kicker}
          </span>
          <h1>{title}</h1>
          <a className="daily-back" href={`/daily/${todayStamp()}`}>Today</a>
          {title.includes('weight') || title.includes('Weight') || title.includes('Sober') || title.includes('sober') ? (
            <p className="daily-plan-headline">
              <a href="/weight">Weight</a>
              {' · '}
              <a href="/sober">Sober</a>
            </p>
          ) : null}
        </div>
      </header>
      {children}
      <PhoneNav />
    </main>
  )
}

function TrendChart({
  points,
  unit,
  goal,
}: {
  points: { date: string; value: number }[]
  unit: string
  goal?: number | null
}) {
  if (points.length < 2) {
    return <p className="daily-done-note">{points.length === 1 ? `${points[0].value}${unit} on ${dayLabel(points[0].date)}.` : 'Not enough days for a trend yet.'}</p>
  }
  const values = points.map((point) => point.value)
  const low = Math.min(...values, goal ?? Infinity)
  const high = Math.max(...values, goal ?? -Infinity)
  const pad = Math.max((high - low) * 0.12, unit === ' kg' ? 0.4 : 1)
  const floor = low - pad
  const span = Math.max(high + pad - floor, 0.1)
  const width = 320
  const height = 150
  const coords = points.map((point, index) => {
    const x = (index / (points.length - 1)) * width
    const y = height - ((point.value - floor) / span) * height
    return [x, y] as const
  })
  const line = coords.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ')
  const goalY = goal == null ? null : height - ((goal - floor) / span) * height
  const latest = points[points.length - 1]
  return (
    <figure className="trend-chart">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${latest.value}${unit} on ${dayLabel(latest.date)}`}>
        {goalY != null && <line x1="0" x2={width} y1={goalY} y2={goalY} className="trend-goal" />}
        <polyline points={line} />
        <circle cx={coords[coords.length - 1][0]} cy={coords[coords.length - 1][1]} r="3.5" />
      </svg>
      <figcaption>
        <span>{dayLabel(points[0].date)}</span>
        <span>{latest.value}{unit}</span>
        <span>{dayLabel(latest.date)}</span>
      </figcaption>
    </figure>
  )
}

function sevenDayAverage(weights: { date: string; kg: number }[]) {
  return weights.map((point) => {
    const end = new Date(`${point.date}T12:00:00+09:00`).getTime()
    const window = weights.filter((item) => {
      const at = new Date(`${item.date}T12:00:00+09:00`).getTime()
      return at <= end && end - at <= 6 * 24 * 60 * 60 * 1000
    })
    const average = window.reduce((sum, item) => sum + item.kg, 0) / window.length
    return { date: point.date, value: Math.round(average * 10) / 10 }
  })
}

export function WeightPage() {
  const day = todayStamp()
  const historyKey = useMemo(() => ['wellbeing-history', 'weight'] as const, [])
  const briefingKey = useMemo(() => ['daily-briefing', day, 'weight'] as const, [day])
  const { data: history, refresh: refreshHistory } = useLiveResource(
    (signal) => fetchWellbeingHistory(90, signal),
    { queryKey: historyKey },
  )
  const { data: briefing, refresh: refreshBriefing } = useLiveResource(
    (signal) => fetchDailyBriefing(day, undefined, signal),
    { queryKey: briefingKey },
  )
  const cut = briefing?.cut ?? null

  return (
    <PageFrame title="Morning weight" kicker="Chili">
      <WeightLog day={day} cut={cut} onLogged={() => { void refreshHistory(); void refreshBriefing() }} />
      <section className="daily-card">
        <span className="daily-card-label">90 days</span>
        <h2>Trend</h2>
        <TrendChart
          points={(history?.weights ?? []).map((point) => ({ date: point.date, value: point.kg }))}
          unit=" kg"
          goal={cut ? (cut.target_kg.low + cut.target_kg.high) / 2 : history?.weight_goal_kg}
        />
        {(history?.weights.length ?? 0) >= 2 && (
          <>
            <p className="daily-done-note">7-day average</p>
            <TrendChart
              points={sevenDayAverage(history?.weights ?? []).map((point) => ({ date: point.date, value: point.value }))}
              unit=" kg"
            />
          </>
        )}
      </section>
    </PageFrame>
  )
}

function WeightLog({
  day,
  cut,
  onLogged,
}: {
  day: string
  cut: DailyCut | null
  onLogged: () => void
}) {
  const [draft, setDraft] = useState<string | null>(null)
  const value = draft ?? (cut?.today_kg != null ? cut.today_kg.toFixed(1) : '')
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const target = cut
    ? (cut.target_kg.low === cut.target_kg.high
      ? cut.target_kg.low.toFixed(1)
      : `${cut.target_kg.low.toFixed(1)}–${cut.target_kg.high.toFixed(1)}`)
    : null

  const submit = (event: FormEvent) => {
    event.preventDefault()
    const parsed = Number(value)
    if (pending || !value.trim() || Number.isNaN(parsed)) return
    setPending(true)
    setError(null)
    void logWeight(day, parsed)
      .then((result) => {
        if (result.status === 'logged') {
          setSaved(true)
          onLogged()
        } else {
          setError(result.message)
        }
      })
      .catch(() => setError('Could not save weight.'))
      .finally(() => setPending(false))
  }

  return (
    <form className="daily-card daily-form" onSubmit={submit}>
      <p>
        {cut?.seven_day_average_kg != null
          ? `7-day average ${cut.seven_day_average_kg.toFixed(1)} kg from ${cut.weigh_ins_7d} weigh-ins.`
          : 'After the bathroom, before eating or drinking.'}
        {target ? ` Trend target ${target} kg.` : ''}
        {cut?.weekly_change_kg != null ? ` ${cut.weekly_change_kg > 0 ? '+' : ''}${cut.weekly_change_kg.toFixed(1)} kg/week.` : ''}
      </p>
      <label className="daily-field">
        <span>This morning (kg)</span>
        <input
          type="number"
          inputMode="decimal"
          step="0.1"
          min="30"
          max="250"
          value={value}
          onChange={(event) => { setDraft(event.target.value); setSaved(false) }}
        />
      </label>
      <button className="daily-submit" type="submit" disabled={pending || !value.trim()}>
        {pending ? 'Saving…' : saved || cut?.today_kg != null ? 'Update' : 'Save'}
      </button>
      {saved && <p className="daily-form-success">Saved.</p>}
      {error && <p className="daily-form-error" role="alert">{error}</p>}
      {cut && (
        <p className="daily-done-note">
          {cut.nutrition.kind === 'training' ? 'Training day' : 'Rest day'}: {cut.nutrition.kcal} kcal
          {' '}· protein {cut.nutrition.protein_g[0]}–{cut.nutrition.protein_g[1]} g
          {' '}· fat {cut.nutrition.fat_g[0]}–{cut.nutrition.fat_g[1]} g
          {' '}· carbs ~{cut.nutrition.carbs_g} g
          {cut.nutrition.adjustment_kcal ? ` (${cut.nutrition.adjustment_kcal > 0 ? '+' : ''}${cut.nutrition.adjustment_kcal} kcal)` : ''}
        </p>
      )}
      {cut?.nutrition.carb_timing && <p className="daily-done-note">{cut.nutrition.carb_timing}</p>}
    </form>
  )
}

export function SoberPage() {
  const day = todayStamp()
  const historyKey = useMemo(() => ['wellbeing-history', 'sober'] as const, [])
  const { data: history, refresh } = useLiveResource(
    (signal) => fetchWellbeingHistory(90, signal),
    { queryKey: historyKey },
  )
  return (
    <PageFrame title="Sober" kicker="Chili">
      <SoberLog day={day} history={history} onLogged={() => { void refresh() }} />
      <section className="daily-card">
        <span className="daily-card-label">90 days</span>
        <h2>Streak</h2>
        <TrendChart
          points={(history?.sober ?? []).map((point) => ({ date: point.date, value: point.days }))}
          unit=" days"
        />
        <DrinkList history={history} />
      </section>
    </PageFrame>
  )
}

function DrinkList({ history }: { history: WellbeingHistory | null }) {
  const drinks = (history?.sober ?? []).filter((point) => point.drank).slice(-8).reverse()
  if (!drinks.length) return <p className="daily-done-note">No drinks in this window.</p>
  return (
    <ul className="daily-saved-lifts">
      {drinks.map((point) => <li key={point.date}>{dayLabel(point.date)}</li>)}
    </ul>
  )
}

function SoberLog({
  day,
  history,
  onLogged,
}: {
  day: string
  history: WellbeingHistory | null
  onLogged: () => void
}) {
  const today = history?.sober.find((point) => point.date === day)
  const [note, setNote] = useState('')
  const [pending, setPending] = useState(false)
  const [saved, setSaved] = useState(false)
  const logged = saved || Boolean(today?.drank)
  const [error, setError] = useState<string | null>(null)
  const days = history?.sober_days ?? 0

  const submit = (event: FormEvent) => {
    event.preventDefault()
    if (pending || logged) return
    setPending(true)
    void logSober(day, { sober: false, note: note.trim() || undefined })
      .then((result) => {
        if (result.status === 'logged') {
          setSaved(true)
          setError(null)
          onLogged()
        } else {
          setError(result.message)
        }
      })
      .catch(() => setError('Could not save.'))
      .finally(() => setPending(false))
  }

  return (
    <form className="daily-card daily-form" onSubmit={submit}>
      <p className="daily-streak-line"><strong>{days}</strong> days. This keeps counting unless you drank.</p>
      {logged ? (
        <p className="daily-done-answer">Logged a drink today.</p>
      ) : (
        <>
          <label className="daily-field">
            <span>Note</span>
            <textarea value={note} onChange={(event) => setNote(event.target.value)} maxLength={500} />
          </label>
          <button className="daily-submit" type="submit" disabled={pending}>
            {pending ? 'Saving…' : 'I drank'}
          </button>
        </>
      )}
      {error && <p className="daily-form-error" role="alert">{error}</p>}
    </form>
  )
}
