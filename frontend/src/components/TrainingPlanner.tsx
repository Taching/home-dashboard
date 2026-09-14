import { doneMarkLabel } from '../lib/workoutMatch'
import type { TrainingOverview, TrainingSession } from '../types'

const TIME_ZONE = 'Asia/Tokyo'

function localDateKey(value: Date) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(value)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

function timeLabel(value: string, allDay = false) {
  if (allDay) return 'All day'
  return new Intl.DateTimeFormat('en-GB', { timeZone: TIME_ZONE, hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}

function sessionTitle(title: string | undefined) {
  if (!title) return 'Open'
  if (title.startsWith('Gym (')) return title
  return title
    .replace('BJJ Competition / Hard', 'Hard BJJ')
    .replace('Strength A + Intervals', 'Gym (Strength A)')
    .replace(/^Strength A$/, 'Gym (Strength A)')
    .replace(/^Strength B$/, 'Gym (Strength B)')
}

const BJJ_DISPLACEABLE = new Set(['strength_a', 'strength_b', 'zone_2', 'grip'])

function phaseLabel(phase: string) {
  return ({
    build_october: 'Build · October',
    taper_october: 'Taper · October',
    competition_october: 'Competition · October',
    recovery_october: 'Recover · October',
    build_november: 'Build · November',
    taper_november: 'Taper · November',
    competition_november: 'Competition · November',
    post_competition: 'Season recovery',
  } as Record<string, string>)[phase] ?? phase.replaceAll('_', ' ')
}

function eventName(name: string) {
  if (/all japan/i.test(name)) return 'All Japan'
  if (/asian open/i.test(name)) return 'Asian Open'
  return name.replace(/ Gi BJJ Tournament/i, '').replace(/\s+2026$/, '')
}

function eventDateRange(start: string, end: string) {
  const first = new Date(`${start}T12:00:00+09:00`)
  const last = new Date(`${end}T12:00:00+09:00`)
  const monthDay = new Intl.DateTimeFormat('en-GB', { timeZone: TIME_ZONE, day: 'numeric', month: 'short' })
  if (start === end) return monthDay.format(first)
  if (first.getUTCMonth() === last.getUTCMonth()) {
    return `${first.getUTCDate()}–${monthDay.format(last)}`
  }
  return `${monthDay.format(first)} – ${monthDay.format(last)}`
}

function daysLeftLabel(days: number) {
  if (days <= 0) return 'Today'
  if (days === 1) return 'Tomorrow'
  return `${days} days`
}

function typeTitle(type: string | undefined) {
  return ({
    bjj_technical: 'BJJ Technical',
    bjj_normal: 'BJJ Normal',
    bjj_hard: 'Hard BJJ',
    strength_a: 'Gym (Strength A)',
    strength_b: 'Gym (Strength B)',
    zone_2: 'Zone 2',
    grip: 'Grip',
    recovery: 'Recovery',
    rest: 'Rest',
    competition: 'Competition',
  } as Record<string, string>)[type ?? ''] ?? sessionTitle(type)
}

export function sessionOnDate(training: TrainingOverview, dateKey: string): TrainingSession | null {
  const sessions = [training.today, training.tomorrow, ...(training.week ?? []), ...(training.upcoming ?? [])]
  return sessions.find((session) => session
    && session.status !== 'skipped'
    && session.status !== 'cancelled'
    && localDateKey(new Date(session.start_at)) === dateKey) ?? null
}

export function TodayTrainingCard({ training }: { training: TrainingOverview }) {
  const session = training.today
  const today = training.generated_at ? new Date(training.generated_at) : new Date()
  const dateLabel = new Intl.DateTimeFormat('en-GB', {
    timeZone: TIME_ZONE, weekday: 'long', day: 'numeric', month: 'long',
  }).format(today)
  const isRest = !session || session.planned_type === 'rest' || session.is_all_day
  const title = isRest
    ? (session?.title && session.title.toLowerCase() !== 'rest' ? session.title : 'Rest today')
    : session.title
  const doneLabel = session ? doneMarkLabel(session.status) : null
  return (
    <section className={`training-card today-training is-glance is-${session?.intensity ?? 'rest'}${doneLabel ? ' is-done' : ''}`} aria-label="Today's training">
      <div className="training-card-heading">
        <div>
          <p className="eyebrow">TODAY</p>
          <h2>{title}</h2>
          <time className="today-training-date">{dateLabel}</time>
        </div>
        {!isRest && session && (
          <div className="training-meta">
            <strong>{timeLabel(session.start_at, session.is_all_day)}</strong>
            {doneLabel && <span className="today-done-mark">✓ {doneLabel}</span>}
          </div>
        )}
      </div>
    </section>
  )
}

export function TrainingWeekStrip({ training }: { training: TrainingOverview }) {
  const todayKey = localDateKey(training.generated_at ? new Date(training.generated_at) : new Date())
  const start = new Date(`${todayKey}T00:00:00+09:00`)
  const sessions = training.upcoming ?? training.week
  const candidates = training.bjj_candidates ?? []
  const days = Array.from({ length: 6 }, (_, index) => {
    const day = new Date(start)
    day.setDate(day.getDate() + index + 1)
    const key = localDateKey(day)
    const candidate = candidates.find((item) => item.date === key)
    const session = sessions.find((item) => localDateKey(new Date(item.start_at)) === key)
    const gymYieldsToBjj = Boolean(candidate && session && BJJ_DISPLACEABLE.has(session.planned_type))
    return {
      day,
      key,
      session: gymYieldsToBjj ? undefined : session,
      candidate,
    }
  })
  return (
    <section className="training-week is-upcoming" aria-label="Next six training days">
      {days.map(({ day, key, session, candidate }) => (
        <article key={key} className={`training-day${session ? ` is-${session.planned_type}` : candidate ? ` is-${candidate.suggested_type}` : ''}`}>
          <span>{new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: TIME_ZONE }).format(day)}</span>
          <strong>
            {Number(key.slice(-2))}
            <em>{new Intl.DateTimeFormat('en-GB', { month: 'short', timeZone: TIME_ZONE }).format(day)}</em>
          </strong>
          <small>{session ? sessionTitle(session.title) : candidate ? typeTitle(candidate.suggested_type) : 'Open'}</small>
          {session && !session.is_all_day ? <i>{timeLabel(session.start_at)}</i> : candidate?.preferred_clock ? <i className="is-quiet">{candidate.preferred_clock}</i> : <i className="is-quiet">—</i>}
        </article>
      ))}
    </section>
  )
}

export function EventsPanel({ training }: { training: TrainingOverview }) {
  const events = training.countdowns.slice(0, 2)
  if (events.length === 0) return null
  return (
    <section className="events-panel" aria-label="Upcoming events">
      <div className="events-panel-heading">
        <div>
          <p className="eyebrow">EVENTS</p>
          <h2>Next up</h2>
        </div>
        <span className="events-phase">{phaseLabel(training.phase)}</span>
      </div>
      <ol className="events-list">
        {events.map((event, index) => (
          <li className={`events-item${index === 0 ? ' is-next' : ''}`} key={event.id}>
            <div>
              <strong>{eventName(event.name)}</strong>
              <time dateTime={event.start_date}>{eventDateRange(event.start_date, event.end_date)}</time>
            </div>
            <em>{daysLeftLabel(event.days_remaining)}</em>
          </li>
        ))}
      </ol>
    </section>
  )
}

export function TrainingInsights({ training }: { training: TrainingOverview }) {
  const tomorrow = training.tomorrow
  const prescription = training.tomorrow_prescription
  const weekQuality = {
    excellent: 'Excellent week',
    good: 'Good week',
    acceptable: 'Acceptable week',
    bad_planning: 'Bad planning',
  }[training.week_quality ?? ''] ?? null
  const adjustment = training.last_adjustment
  return (
    <section className="training-insights coach-panel" aria-label="Chili's next training decision">
      {adjustment?.how?.length ? (
        <div className="plan-change" aria-label="Why Chili changed the week">
          <p className="eyebrow">PLAN CHANGE</p>
          <p className="plan-change-banner">{adjustment.banner}</p>
          <p className="plan-change-label">How</p>
          <ul>{adjustment.how.map((item) => <li key={item}>{item}</li>)}</ul>
          <p className="plan-change-label">Why</p>
          <ul>{adjustment.why.map((item) => <li key={item}>{item}</li>)}</ul>
        </div>
      ) : null}
      <div className="coach-panel-heading">
        <div>
          <p className="eyebrow">CHILI</p>
          <h2>Tomorrow</h2>
        </div>
      </div>
      <div className={`tomorrow-decision is-${tomorrow?.intensity ?? 'rest'}`}>
        <div className="tomorrow-decision-title">
          <strong>{tomorrow?.title ?? typeTitle(prescription?.session) ?? 'Recovery / open'}</strong>
          <time>{prescription?.time ?? (tomorrow ? timeLabel(tomorrow.start_at, tomorrow.is_all_day) : 'No session')}</time>
        </div>
        <p>{prescription?.work ?? tomorrow?.reason ?? 'No workout is added merely because time is free.'}</p>
        <span>Focus · {prescription?.focus ?? tomorrow?.coach_focus?.slice(0, 2).join(' ') ?? 'Protect recovery'}</span>
        <span>Why · {prescription?.why ?? tomorrow?.reason ?? 'The weekly goal survives; the original calendar does not have to.'}</span>
        {weekQuality ? <span className="week-quality">{weekQuality}</span> : null}
      </div>
    </section>
  )
}
