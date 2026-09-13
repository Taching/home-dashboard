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

function exerciseLabel(item: TrainingSession['exercises'][number]) {
  const load = item.load_value === null ? '' : ` ${item.load_value}${item.load_unit ? ` ${item.load_unit}` : ''}`
  const work = item.sets === null ? (item.reps ?? '') : `${item.sets} × ${item.reps ?? ''}`
  const duration = item.duration_seconds ? `${Math.round(item.duration_seconds / 60)} min` : ''
  return `${item.name}${load}${work ? ` · ${work}` : ''}${duration ? ` · ${duration}` : ''}`
}

export function TodayTrainingCard({ training }: { training: TrainingOverview }) {
  const session = training.today
  const conditioning = session?.exercises.filter((item) => item.name.toLowerCase().includes('interval')) ?? []
  const mainWork = session?.exercises.filter((item) => !item.name.toLowerCase().includes('interval')) ?? []
  return (
    <section className={`training-card today-training is-${session?.intensity ?? 'rest'}`} aria-label="Today's training">
      <div className="training-card-heading">
        <div><p className="eyebrow">TODAY</p><h2>{session?.title ?? 'Rest today'}</h2></div>
        <div className="training-meta">
          {session && <strong>{session.estimated_minutes} min</strong>}
          <span>{training.readiness?.level?.replace('_', ' ') ?? 'readiness pending'}</span>
        </div>
      </div>
      {session ? (
        <>
          {mainWork.length > 0 && <div className="training-prescription">
            <strong>Main work</strong>
            <div className="training-main-work">
              {mainWork.map((item) => <span key={item.name}>{exerciseLabel(item)}</span>)}
            </div>
          </div>}
          {conditioning.length > 0 && <div className="training-prescription is-conditioning">
            <strong>Conditioning</strong>
            <div className="training-main-work">
              {conditioning.map((item) => <span key={item.name}>{exerciseLabel(item)}</span>)}
            </div>
          </div>}
          <div className="training-main-work">
            {session.target_rounds && <span>{session.target_rounds} × 5-minute rounds · {Math.round((session.rest_seconds ?? 120) / 60)} min rest</span>}
          </div>
          {session.coach_focus.length > 0 && <p className="training-focus">Focus · {session.coach_focus.slice(0, 2).join(' ')}</p>}
          <p className="training-why">Why today · {session.reason}</p>
          {session.preparation && <p className="training-preparation">Prepare · {session.preparation}</p>}
          <p className="training-command">OpenClaw: “start training”, “move this”, “recovery day”, or “completed”.</p>
        </>
      ) : <p className="training-why">No session is prescribed. An empty calendar is not an invitation to add fatigue.</p>}
    </section>
  )
}

export function TrainingWeekStrip({ training }: { training: TrainingOverview }) {
  const todayKey = localDateKey(training.generated_at ? new Date(training.generated_at) : new Date())
  const start = new Date(`${todayKey}T00:00:00+09:00`)
  const sessions = training.upcoming ?? training.week
  const days = Array.from({ length: 7 }, (_, index) => {
    const day = new Date(start)
    day.setDate(day.getDate() + index)
    const key = localDateKey(day)
    return { day, key, session: sessions.find((item) => localDateKey(new Date(item.start_at)) === key) }
  })
  return (
    <section className="training-week" aria-label="This week's training plan">
      {days.map(({ day, key, session }) => (
        <article key={key} className={`training-day${key === todayKey ? ' is-today' : ''}${session ? ` is-${session.planned_type}` : ''}`}>
          <span>{new Intl.DateTimeFormat('en-US', { weekday: 'short', timeZone: TIME_ZONE }).format(day)}</span>
          <strong>{Number(key.slice(-2))}</strong>
          <small>{session?.title.replace('BJJ Competition / Hard', 'Hard BJJ').replace('Strength A + Intervals', 'Strength A') ?? 'No training'}</small>
          {session && !session.is_all_day && <i>{timeLabel(session.start_at)}</i>}
        </article>
      ))}
    </section>
  )
}

export function TrainingInsights({ training }: { training: TrainingOverview }) {
  const tomorrow = training.tomorrow
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
          <strong>{tomorrow?.title ?? 'Recovery / open'}</strong>
          <time>{tomorrow ? timeLabel(tomorrow.start_at, tomorrow.is_all_day) : 'No session'}</time>
        </div>
        <p>{tomorrow?.reason ?? 'No workout is added merely because time is free.'}</p>
        {tomorrow?.coach_focus.length ? <span>Focus · {tomorrow.coach_focus.slice(0, 2).join(' ')}</span> : null}
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
