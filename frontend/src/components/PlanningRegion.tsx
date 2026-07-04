import type { CalendarEvent, CalendarToday, NotionToday } from '../types'

const TIME_ZONE = 'Asia/Tokyo'
const START_HOUR = 7
const END_HOUR = 20
const TOTAL_MINUTES = (END_HOUR - START_HOUR) * 60

type PositionedEvent = CalendarEvent & {
  startMinute: number
  endMinute: number
  column: number
  columns: number
}

function dayKey(value: Date | string) {
  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: TIME_ZONE, year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(new Date(value))
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? ''
  return `${get('year')}-${get('month')}-${get('day')}`
}

function dateAtStartOfDay(key: string) {
  return new Date(`${key}T00:00:00+09:00`)
}

function addDays(key: string, days: number) {
  const value = dateAtStartOfDay(key)
  value.setUTCDate(value.getUTCDate() + days)
  return dayKey(value)
}

function dayLabel(key: string) {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: TIME_ZONE, weekday: 'long', month: 'long', day: 'numeric',
  }).format(dateAtStartOfDay(key))
}

function eventIntersectsDay(event: CalendarEvent, selectedDate: string) {
  const start = dateAtStartOfDay(selectedDate).getTime()
  const end = start + 24 * 60 * 60 * 1000
  return new Date(event.start_at).getTime() < end && new Date(event.end_at).getTime() > start
}

function eventTime(event: CalendarEvent) {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: TIME_ZONE, hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(new Date(event.start_at))
}

function taskDueLabel(value: string | null) {
  if (!value) return null
  const due = new Date(value)
  const now = new Date()
  if (dayKey(due) === dayKey(now) && due.getUTCHours() === 0 && due.getUTCMinutes() === 0) {
    return 'Today'
  }
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: TIME_ZONE, hour: '2-digit', minute: '2-digit', hour12: false,
  }).format(due)
}

function priorityClass(priority: string | null) {
  const value = priority?.toLowerCase() ?? ''
  if (value.includes('high') || value.includes('urgent')) return 'is-high'
  if (value.includes('medium') || value.includes('normal')) return 'is-medium'
  if (value.includes('low')) return 'is-low'
  return ''
}

function statusClass(status: string | null) {
  const value = status?.toLowerCase() ?? ''
  if (value.includes('progress') || value.includes('doing')) return 'is-progress'
  if (value.includes('blocked') || value.includes('waiting')) return 'is-blocked'
  if (value.includes('todo') || value.includes('to do') || value.includes('backlog')) return 'is-todo'
  return ''
}

function layoutEvents(events: CalendarEvent[], selectedDate: string): PositionedEvent[] {
  const dayStart = dateAtStartOfDay(selectedDate).getTime()
  const visible = events
    .filter((event) => !event.is_all_day && eventIntersectsDay(event, selectedDate))
    .map((event) => {
      const rawStart = (new Date(event.start_at).getTime() - dayStart) / 60_000
      const rawEnd = (new Date(event.end_at).getTime() - dayStart) / 60_000
      return {
        ...event,
        startMinute: Math.max(START_HOUR * 60, rawStart),
        endMinute: Math.min(END_HOUR * 60, Math.max(rawEnd, rawStart + 15)),
        column: 0,
        columns: 1,
      }
    })
    .filter((event) => event.endMinute > START_HOUR * 60 && event.startMinute < END_HOUR * 60)
    .sort((first, second) => first.startMinute - second.startMinute || first.endMinute - second.endMinute)

  const completed: PositionedEvent[] = []
  let group: PositionedEvent[] = []
  let active: PositionedEvent[] = []
  let groupEnd = -Infinity
  const completeGroup = () => {
    const columns = Math.max(1, ...group.map((event) => event.column + 1))
    completed.push(...group.map((event) => ({ ...event, columns })))
    group = []
    active = []
    groupEnd = -Infinity
  }

  for (const event of visible) {
    if (group.length && event.startMinute >= groupEnd) completeGroup()
    active = active.filter((activeEvent) => activeEvent.endMinute > event.startMinute)
    const taken = new Set(active.map((activeEvent) => activeEvent.column))
    while (taken.has(event.column)) event.column += 1
    active.push(event)
    group.push(event)
    groupEnd = Math.max(groupEnd, event.endMinute)
  }
  if (group.length) completeGroup()
  return completed
}

function SetupState({ service, status }: { service: string, status: string }) {
  if (status === 'not_configured') return <p className="setup-state">Connect {service}</p>
  if (status === 'unavailable') return <p className="setup-state is-error">{service} is unavailable</p>
  return <p className="setup-state">No events on this day</p>
}

function CalendarSchedule({
  calendar, selectedDate, onPrevious, onToday, onNext,
}: {
  calendar: CalendarToday
  selectedDate: string
  onPrevious: () => void
  onToday: () => void
  onNext: () => void
}) {
  const dayEvents = calendar.events.filter((event) => eventIntersectsDay(event, selectedDate))
  const allDayEvents = dayEvents.filter((event) => event.is_all_day)
  const timedEvents = layoutEvents(dayEvents, selectedDate)
  const before = dayEvents.filter((event) => !event.is_all_day && new Date(event.start_at).getTime() < dateAtStartOfDay(selectedDate).getTime() + START_HOUR * 3_600_000)
  const after = dayEvents.filter((event) => !event.is_all_day && new Date(event.end_at).getTime() > dateAtStartOfDay(selectedDate).getTime() + END_HOUR * 3_600_000)
  const hours = Array.from({ length: END_HOUR - START_HOUR + 1 }, (_, index) => START_HOUR + index)

  return (
    <section className="calendar-schedule" aria-label={`Calendar for ${dayLabel(selectedDate)}`}>
      <div className="calendar-heading">
        <div>
          <p className="eyebrow">SCHEDULE</p>
          <h2>{dayLabel(selectedDate)}</h2>
        </div>
        <div className="calendar-navigation" aria-label="Calendar navigation">
          <button type="button" onClick={onPrevious} aria-label="Previous day">‹</button>
          <button type="button" className="today-button" onClick={onToday}>Today</button>
          <button type="button" onClick={onNext} aria-label="Next day">›</button>
        </div>
      </div>

      <div className="all-day-strip" aria-label="All-day events">
        <span>All day</span>
        {allDayEvents.length === 0 ? <small>—</small> : allDayEvents.slice(0, 2).map((event) => (
          <span className="all-day-event" key={event.id}>{event.title}</span>
        ))}
        {allDayEvents.length > 2 && <small>+{allDayEvents.length - 2}</small>}
      </div>

      {calendar.status !== 'ready' ? <SetupState service="Apple Calendar" status={calendar.status} /> : (
        <>
          {before.length > 0 && <p className="calendar-overflow">↑ {before.length} earlier event{before.length === 1 ? '' : 's'}</p>}
          <div className="calendar-day-grid" aria-label="Hourly calendar grid from 07:00 to 20:00">
            <div className="calendar-hour-labels" aria-hidden="true">
              {hours.map((hour) => <span key={hour} style={{ top: `${((hour - START_HOUR) / (END_HOUR - START_HOUR)) * 100}%` }}>{String(hour).padStart(2, '0')}:00</span>)}
            </div>
            <div className="calendar-canvas">
              {timedEvents.map((event) => {
                const top = ((event.startMinute - START_HOUR * 60) / TOTAL_MINUTES) * 100
                const height = ((event.endMinute - event.startMinute) / TOTAL_MINUTES) * 100
                const compact = event.endMinute - event.startMinute < 45
                return (
                  <article
                    className={`calendar-event${compact ? ' is-compact' : ''}`}
                    key={event.id}
                    style={{
                      top: `${top}%`, height: `${height}%`,
                      left: `calc(${(event.column / event.columns) * 100}% + 3px)`,
                      width: `calc(${100 / event.columns}% - 6px)`,
                    }}
                    aria-label={`${event.title}, ${eventTime(event)}`}
                  >
                    <strong>{compact ? `${eventTime(event)} ${event.title}` : event.title}</strong>
                    {!compact && <span>{eventTime(event)}</span>}
                  </article>
                )
              })}
              {timedEvents.length === 0 && <p className="calendar-empty">No timed events</p>}
            </div>
          </div>
          {after.length > 0 && <p className="calendar-overflow">↓ {after.length} later event{after.length === 1 ? '' : 's'}</p>}
        </>
      )}
    </section>
  )
}

export function PlanningRegion({
  calendar, notion, selectedDate, onPrevious, onToday, onNext,
}: {
  calendar: CalendarToday
  notion: NotionToday
  selectedDate: string
  onPrevious: () => void
  onToday: () => void
  onNext: () => void
}) {
  return (
    <section className="planning-region" aria-label="Today’s plan">
      <CalendarSchedule
        calendar={calendar}
        selectedDate={selectedDate}
        onPrevious={onPrevious}
        onToday={onToday}
        onNext={onNext}
      />
      <div className="task-section">
        <div className="region-heading">
          <div>
            <p className="eyebrow">TASKS</p>
            <h2>Today</h2>
          </div>
          <p>Notion · {notion.tasks.length}</p>
        </div>
        {notion.status !== 'ready' || notion.tasks.length === 0 ? <SetupState service="Notion" status={notion.status} /> : (
          <ul className="task-list">
            {notion.tasks.slice(0, 8).map((task) => (
              <li className={task.is_overdue ? 'is-overdue' : ''} key={task.id}>
                {task.status && <em className={`status-badge ${statusClass(task.status)}`}>{task.status}</em>}
                <div className="task-copy">
                  <span>{task.title}</span>
                  <small>
                    {task.priority && <strong className={`priority-badge ${priorityClass(task.priority)}`}>{task.priority}</strong>}
                    <span>{task.is_overdue ? 'Overdue' : taskDueLabel(task.due_at)}</span>
                  </small>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

export { addDays, dayKey }
