export type CalendarEventKind = 'work' | 'personal' | 'training'

type KindSource = {
  source?: string
  training_session_id?: string | null
  calendar_title?: string | null
}

export function calendarEventKind(event: KindSource): CalendarEventKind {
  if (event.source === 'training' || event.training_session_id) return 'training'
  const calendar = event.calendar_title?.trim().toLowerCase() ?? ''
  if (calendar.includes('asuene')) return 'work'
  return 'personal'
}
