import { doneMarkLabel } from '../lib/workoutMatch'
import { WeatherIconArt } from './WeatherWidget'
import type { TrainingOverview, TrainingSession, WeatherForecast } from '../types'

const TIME_ZONE = 'Asia/Tokyo'

export function localDateKey(value: Date) {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(value)
  const part = (type: Intl.DateTimeFormatPartTypes) => parts.find((item) => item.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

export function timeLabel(value: string, allDay = false) {
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

export function typeTitle(type: string | undefined) {
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
  const isRest = !session || session.planned_type === 'rest' || (session.is_all_day && session.planned_type !== 'recovery')
  const title = isRest
    ? (session?.title && session.title.toLowerCase() !== 'rest' ? session.title : 'Rest today')
    : session.title
  const doneLabel = session ? doneMarkLabel(session.status) : null
  const href = session && session.planned_type !== 'rest' ? `/workout/${session.id}` : null
  const body = (
    <>
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
    </>
  )
  return href ? (
    <a className={`training-card today-training is-glance is-${session?.intensity ?? 'rest'}${doneLabel ? ' is-done' : ''}`} href={href} aria-label="Today's training">
      {body}
    </a>
  ) : (
    <section className={`training-card today-training is-glance is-${session?.intensity ?? 'rest'}${doneLabel ? ' is-done' : ''}`} aria-label="Today's training">
      {body}
    </section>
  )
}

export function TrainingWeekStrip({ training, weather }: { training: TrainingOverview; weather: WeatherForecast }) {
  const todayKey = localDateKey(training.generated_at ? new Date(training.generated_at) : new Date())
  const start = new Date(`${todayKey}T00:00:00+09:00`)
  const sessions = training.upcoming ?? training.week
  const candidates = training.bjj_candidates ?? []
  const flags = training.day_flags ?? {}
  const weatherByDate = new Map(weather.days.map((item) => [item.date, item]))
  const days = Array.from({ length: 6 }, (_, index) => {
    const day = new Date(start)
    day.setDate(day.getDate() + index + 1)
    const key = localDateKey(day)
    const candidate = candidates.find((item) => item.date === key)
    const session = sessions.find((item) => localDateKey(new Date(item.start_at)) === key)
    const gymYieldsToBjj = Boolean(candidate && session && BJJ_DISPLACEABLE.has(session.planned_type))
    const dayFlags = flags[key] ?? []
    return {
      day,
      key,
      session: gymYieldsToBjj ? undefined : session,
      candidate,
      closed: dayFlags.includes('HOLIDAY') || dayFlags.includes('CLOSED'),
      noClass: dayFlags.includes('NO_CLASS'),
      unavailable: dayFlags.includes('UNAVAILABLE'),
    }
  })
  const visibleKeys = new Set(days.map((item) => item.key))
  const laterClosures = Object.entries(flags)
    .filter(([key, dayFlags]) => !visibleKeys.has(key) && key > todayKey && (dayFlags.includes('HOLIDAY') || dayFlags.includes('CLOSED')))
    .map(([key]) => key)
    .sort()
  return (
    <section className="training-week-group">
      <section className="training-week is-upcoming" aria-label="Next six training days">
      {days.map(({ day, key, session, candidate, closed, noClass, unavailable }) => {
        const href = session && session.planned_type !== 'rest' ? `/workout/${session.id}` : undefined
        const workoutLabel = session ? sessionTitle(session.title) : candidate ? typeTitle(candidate.suggested_type) : undefined
        const mark = unavailable ? 'Away' : workoutLabel ?? (closed ? 'BJJ closed' : noClass ? 'No BJJ class' : 'Open')
        const closureOnly = (closed || noClass) && !workoutLabel
        const dayWeather = weatherByDate.get(key)
        const inner = (
          <>
            {dayWeather && (
              <span className="training-day-weather" title={dayWeather.condition}>
                <WeatherIconArt icon={dayWeather.icon} size={20} />
              </span>
            )}
            <span>{new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: TIME_ZONE }).format(day)}</span>
            <strong>
              {Number(key.slice(-2))}
              <em>{new Intl.DateTimeFormat('en-GB', { month: 'short', timeZone: TIME_ZONE }).format(day)}</em>
            </strong>
            <small>{mark}</small>
            {session && !session.is_all_day ? <i>{timeLabel(session.start_at)}</i> : candidate?.preferred_clock ? <i className="is-quiet">{candidate.preferred_clock}</i> : <i className="is-quiet">—</i>}
          </>
        )
        const className = `training-day${session ? ` is-${session.planned_type}` : candidate ? ` is-${candidate.suggested_type}` : ''}${unavailable || closureOnly ? ' is-blocked' : ''}`
        return href ? (
          <a key={key} className={className} href={href}>{inner}</a>
        ) : (
          <article key={key} className={className}>{inner}</article>
        )
      })}
      </section>
      {laterClosures.length > 0 && (
        <p className="training-week-note">
          BJJ gym also closed: {laterClosures.map((key) => {
            const day = new Date(`${key}T00:00:00+09:00`)
            const weekday = new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: TIME_ZONE }).format(day)
            const month = new Intl.DateTimeFormat('en-GB', { month: 'short', timeZone: TIME_ZONE }).format(day)
            return `${weekday} ${Number(key.slice(-2))} ${month}`
          }).join(', ')}
        </p>
      )}
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
  const quota = /still needs|only fill it if|one complete rest|one full rest day|Rest 0|missing tournament piece|empty time is not extra gym/i
  const raw = training.last_adjustment
  const adjustment = raw?.how?.length ? {
    ...raw,
    how: raw.how.filter((item) => !quota.test(item)),
    why: (raw.why ?? []).filter((item) => !quota.test(item)),
  } : null
  const showAdjustment = Boolean(adjustment?.how.length || adjustment?.why.length)
  return (
    <section className="training-insights coach-panel" aria-label="Chili's next training decision">
      {showAdjustment && adjustment ? (
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
        <span>Why · {prescription?.why ?? tomorrow?.reason ?? 'Rebuild from completed work, recovery, and class availability.'}</span>
        {weekQuality ? <span className="week-quality">{weekQuality}</span> : null}
      </div>
    </section>
  )
}
