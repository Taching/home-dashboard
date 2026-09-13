import type { TrainingOverview } from '../types'

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
  return (
    <section className={`training-card today-training is-glance is-${session?.intensity ?? 'rest'}`} aria-label="Today's training">
      <div className="training-card-heading">
        <div>
          <p className="eyebrow">TODAY</p>
          <h2>{title}</h2>
          <time className="today-training-date">{dateLabel}</time>
        </div>
        {!isRest && session && (
          <div className="training-meta">
            <strong>{timeLabel(session.start_at, session.is_all_day)}</strong>
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
    return {
      day,
      key,
      session: sessions.find((item) => localDateKey(new Date(item.start_at)) === key),
      candidate,
    }
  })
  return (
    <section className="training-week is-upcoming" aria-label="Next six training days">
      {days.map(({ day, key, session, candidate }) => (
        <article key={key} className={`training-day${session ? ` is-${session.planned_type}` : candidate ? ' is-bjj-candidate' : ''}`}>
          <span>{new Intl.DateTimeFormat('en-GB', { weekday: 'short', timeZone: TIME_ZONE }).format(day)}</span>
          <strong>
            {Number(key.slice(-2))}
            <em>{new Intl.DateTimeFormat('en-GB', { month: 'short', timeZone: TIME_ZONE }).format(day)}</em>
          </strong>
          <small>{session ? sessionTitle(session.title) : candidate ? 'BJJ?' : 'Open'}</small>
          {session && !session.is_all_day ? <i>{timeLabel(session.start_at)}</i> : candidate?.preferred_clock ? <i className="is-quiet">{candidate.preferred_clock}</i> : <i className="is-quiet">—</i>}
        </article>
      ))}
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
  const phaseLabel = {
    build_october: 'Building for October',
    taper_october: 'October taper',
    competition_october: 'Competition day',
    recovery_october: 'Recovering',
    build_november: 'Building for November',
    taper_november: 'November taper',
    competition_november: 'Competition weekend',
    post_competition: 'Season recovery',
  }[training.phase] ?? training.phase.replaceAll('_', ' ')
  return (
    <section className="training-insights coach-panel" aria-label="Coach's next training decision">
      <div className="coach-panel-heading">
        <div>
          <p className="eyebrow">COACH'S CALL</p>
          <h2>Tomorrow</h2>
        </div>
        <span>{phaseLabel}</span>
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
      <div className="tournament-list" aria-label="Upcoming tournaments">
        <p className="eyebrow">TOURNAMENTS</p>
        {training.countdowns.slice(0, 2).map((competition) => (
          <div className="tournament-row" key={competition.id}>
            <span>{competition.start_date}<small>{competition.name.replace(' Gi BJJ Tournament', '')}</small></span>
            <strong>{competition.days_remaining}<small> days</small></strong>
          </div>
        ))}
      </div>
    </section>
  )
}
