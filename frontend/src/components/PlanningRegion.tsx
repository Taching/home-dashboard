import { useClock } from '../hooks/useClock'
import type { CalendarEvent, CalendarToday, NotionTask, NotionToday } from '../types'
import { priorityLevel } from './TaskPriorityBars'

const TIME_ZONE = 'Asia/Tokyo'
const START_HOUR = 7
const END_HOUR = 20
const TOTAL_MINUTES = (END_HOUR - START_HOUR) * 60
const TASK_VISIBLE_LIMIT = 14

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

function overflowHint(events: CalendarEvent[], direction: 'earlier' | 'later') {
  if (events.length === 0) return null
  const arrow = direction === 'earlier' ? '↑' : '↓'
  const first = events[0]?.title?.trim() || 'Event'
  if (events.length === 1) return `${arrow} ${first}`
  return `${arrow} ${first} · +${events.length - 1} ${direction}`
}

function taskDueDateKey(value: string | null) {
  return value ? dayKey(new Date(value)) : 'none'
}

function taskDueGroupLabel(key: string, todayKey: string) {
  if (key === 'none') return 'No due date'

  const dueDate = dateAtStartOfDay(key)
  const todayDate = dateAtStartOfDay(todayKey)
  const dayDiff = Math.round((dueDate.getTime() - todayDate.getTime()) / 86_400_000)
  const dateLabel = new Intl.DateTimeFormat('en-GB', {
    timeZone: TIME_ZONE,
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  }).format(dueDate)

  if (dayDiff < 0) return `${dateLabel} · overdue`
  if (dayDiff === 0) return 'Today'
  if (dayDiff === 1) return 'Tomorrow'
  return dateLabel
}

function groupTasksByDue(tasks: NotionToday['tasks']) {
  const todayKey = dayKey(new Date())
  const groups = new Map<string, NotionToday['tasks']>()

  for (const task of tasks) {
    const key = taskDueDateKey(task.due_at)
    const bucket = groups.get(key)
    if (bucket) bucket.push(task)
    else groups.set(key, [task])
  }

  return [...groups.entries()]
    .sort(([first], [second]) => {
      if (first === 'none') return 1
      if (second === 'none') return -1
      return first.localeCompare(second)
    })
    .map(([key, groupedTasks]) => ({
      key,
      label: taskDueGroupLabel(key, todayKey),
      tasks: groupedTasks,
      isOverdue: key !== 'none' && key < todayKey,
    }))
}

function taskTypeClass(taskType: string | null) {
  const value = taskType?.trim().toLowerCase() ?? ''
  if (!value) return 'is-unsorted'
  if (value.includes('personal') || value.includes('home') || value.includes('life')) return 'is-personal'
  return 'is-work'
}

function taskTypeLabel(taskType: string | null) {
  const kind = taskTypeClass(taskType)
  if (kind === 'is-personal') return 'Personal'
  if (kind === 'is-work') return 'Work'
  return 'Task'
}

function taskSummary(tasks: NotionToday['tasks']) {
  let overdue = 0
  for (const task of tasks) {
    if (task.is_overdue) overdue += 1
  }
  return { total: tasks.length, overdue }
}

function priorityMetaLabel(priority: string | null) {
  const level = priorityLevel(priority)
  if (!level) return null
  if (level === 'urgent') return 'Urgent'
  if (level === 'high') return 'High'
  if (level === 'medium') return 'Med'
  return 'Low'
}

function taskMetaLine(task: NotionTask, todayKey: string) {
  const dueKey = taskDueDateKey(task.due_at)
  const dueLabel = taskDueGroupLabel(dueKey, todayKey)
  const type = taskTypeLabel(task.task_type)
  const priority = priorityMetaLabel(task.priority)
  return [dueLabel, type, priority].filter(Boolean).join(' · ')
}

function flattenTasksByDue(tasks: NotionToday['tasks']) {
  return groupTasksByDue(tasks).flatMap((group) => group.tasks)
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

function SetupState({ service, status, emptyLabel }: { service: string, status: string, emptyLabel?: string }) {
  if (status === 'not_configured') return <p className="setup-state">Connect {service}</p>
  if (status === 'unavailable') return <p className="setup-state is-error">{service} is unavailable</p>
  return <p className="setup-state">{emptyLabel ?? 'No events on this day'}</p>
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
  const now = useClock()
  const todayKey = dayKey(now)
  const isToday = selectedDate === todayKey
  const dayEvents = calendar.events.filter((event) => eventIntersectsDay(event, selectedDate))
  const allDayEvents = dayEvents.filter((event) => event.is_all_day)
  const timedEvents = layoutEvents(dayEvents, selectedDate)
  const dayStartMs = dateAtStartOfDay(selectedDate).getTime()
  const before = dayEvents
    .filter((event) => !event.is_all_day && new Date(event.start_at).getTime() < dayStartMs + START_HOUR * 3_600_000)
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())
  const after = dayEvents
    .filter((event) => !event.is_all_day && new Date(event.end_at).getTime() > dayStartMs + END_HOUR * 3_600_000)
    .sort((a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime())
  const hours = Array.from({ length: END_HOUR - START_HOUR + 1 }, (_, index) => START_HOUR + index)

  const nowMinutes = (() => {
    if (!isToday) return null
    const parts = new Intl.DateTimeFormat('en-GB', {
      timeZone: TIME_ZONE, hour: '2-digit', minute: '2-digit', hour12: false,
    }).formatToParts(now)
    const hour = Number(parts.find((part) => part.type === 'hour')?.value ?? '0')
    const minute = Number(parts.find((part) => part.type === 'minute')?.value ?? '0')
    const total = hour * 60 + minute
    if (total < START_HOUR * 60 || total > END_HOUR * 60) return null
    return total
  })()
  const nowTop = nowMinutes === null
    ? null
    : ((nowMinutes - START_HOUR * 60) / TOTAL_MINUTES) * 100

  const beforeHint = overflowHint(before, 'earlier')
  const afterHint = overflowHint(after, 'later')

  return (
    <section className="calendar-schedule" aria-label={`Calendar for ${dayLabel(selectedDate)}`}>
      <div className="calendar-heading">
        <div>
          <p className="eyebrow">SCHEDULE</p>
          <h2>{dayLabel(selectedDate)}</h2>
        </div>
        <div className="calendar-navigation" aria-label="Calendar navigation">
          <button type="button" onClick={onPrevious} aria-label="Previous day">‹</button>
          <button
            type="button"
            className={`today-button${isToday ? ' is-active' : ''}`}
            onClick={onToday}
            disabled={isToday}
            aria-current={isToday ? 'date' : undefined}
          >
            Today
          </button>
          <button type="button" onClick={onNext} aria-label="Next day">›</button>
        </div>
      </div>

      <div className="all-day-strip" aria-label="All-day events">
        <span>All day</span>
        {allDayEvents.length === 0 ? <small>—</small> : allDayEvents.map((event) => (
          <span className="all-day-event" key={event.id}>{event.title}</span>
        ))}
      </div>

      {calendar.status !== 'ready' ? <SetupState service="Apple Calendar" status={calendar.status} /> : (
        <>
          {beforeHint && <p className="calendar-overflow">{beforeHint}</p>}
          <div className="calendar-day-grid" aria-label="Hourly calendar grid from 07:00 to 20:00">
            <div className="calendar-hour-labels" aria-hidden="true">
              {hours.map((hour) => (
                <span
                  key={hour}
                  style={{ top: `${((hour - START_HOUR) / (END_HOUR - START_HOUR)) * 100}%` }}
                >
                  {String(hour).padStart(2, '0')}:00
                </span>
              ))}
            </div>
            <div className="calendar-canvas">
              {timedEvents.map((event) => {
                const top = ((event.startMinute - START_HOUR * 60) / TOTAL_MINUTES) * 100
                const height = ((event.endMinute - event.startMinute) / TOTAL_MINUTES) * 100
                const compact = event.endMinute - event.startMinute < 45
                return (
                  <article
                    className={`calendar-event${compact ? ' is-compact' : ''}${event.is_current ? ' is-current' : ''}`}
                    key={event.id}
                    style={{
                      top: `${top}%`, height: `${height}%`,
                      left: `calc(${(event.column / event.columns) * 100}% + 3px)`,
                      width: `calc(${100 / event.columns}% - 6px)`,
                    }}
                    aria-label={`${event.title}, ${eventTime(event)}${event.is_current ? ', now' : ''}`}
                  >
                    <strong>{compact ? `${eventTime(event)} ${event.title}` : event.title}</strong>
                    {!compact && (
                      <span>
                        {eventTime(event)}
                        {event.is_current ? ' · NOW' : ''}
                      </span>
                    )}
                  </article>
                )
              })}
              {nowTop !== null && (
                <div
                  className="calendar-now-line"
                  style={{ top: `${nowTop}%` }}
                  aria-hidden="true"
                />
              )}
              {timedEvents.length === 0 && <p className="calendar-empty">No timed events</p>}
            </div>
          </div>
          {afterHint && <p className="calendar-overflow">{afterHint}</p>}
        </>
      )}
    </section>
  )
}

function TaskRow({ task, todayKey }: { task: NotionTask, todayKey: string }) {
  const typeClass = taskTypeClass(task.task_type)
  const typeLabel = taskTypeLabel(task.task_type)
  const meta = taskMetaLine(task, todayKey)

  return (
    <li
      className={`task-row is-clean ${typeClass}${task.is_overdue ? ' is-overdue' : ''}`}
      aria-label={`${typeLabel}: ${task.title}. ${meta}`}
    >
      <span className="task-rail" aria-hidden="true" />
      <div className="task-copy">
        <span className="task-title">{task.title}</span>
        <span className={`task-meta-line${task.is_overdue ? ' is-overdue' : ''}`}>{meta}</span>
      </div>
    </li>
  )
}

function TaskSection({ notion }: { notion: NotionToday }) {
  const todayKey = dayKey(new Date())

  if (notion.status !== 'ready') {
    return (
      <section className="task-section" aria-label="Tasks">
        <SetupState service="Notion" status={notion.status} emptyLabel="No open tasks" />
      </section>
    )
  }

  const allTasks = notion.tasks
  const summary = taskSummary(allTasks)
  const ordered = flattenTasksByDue(allTasks)
  const visibleTasks = ordered.slice(0, TASK_VISIBLE_LIMIT)
  const hiddenCount = Math.max(0, ordered.length - visibleTasks.length)

  return (
    <section className="task-section" aria-label="Tasks">
      <div className="task-heading is-clean">
        <div>
          <p className="eyebrow">TASKS</p>
          <p className="task-summary">
            <strong>{summary.total} open</strong>
          </p>
        </div>
        {summary.overdue > 0 && (
          <p className="task-summary is-end">
            <span className="is-overdue">{summary.overdue} overdue</span>
          </p>
        )}
      </div>

      {allTasks.length === 0 ? (
        <p className="setup-state">No open tasks</p>
      ) : (
        <>
          <ul className="task-list is-clean">
            {visibleTasks.map((task) => (
              <TaskRow key={task.id} task={task} todayKey={todayKey} />
            ))}
          </ul>
          {hiddenCount > 0 && (
            <p className="task-more" aria-label={`${hiddenCount} more tasks not shown`}>
              +{hiddenCount} more
            </p>
          )}
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
      <TaskSection notion={notion} />
    </section>
  )
}

export { addDays, dayKey }
