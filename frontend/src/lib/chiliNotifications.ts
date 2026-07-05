import type { CalendarEvent, CalendarToday, NotionTask, OpenClawMessage, VoiceStatus } from '../types'

export type NotificationKind =
  | 'meeting_soon'
  | 'walk_reminder'
  | 'task_completed'
  | 'openclaw_message'
  | 'voice_complete'
  | 'voice_error'
  | 'spotify_playing'

export type ChiliNotification = {
  id: string
  kind: NotificationKind
  message: string
  priority: number
  dedupeKey: string
  sendTelegram?: boolean
  createdAt: number
}

export const NOTIFICATION_TTL_MS = 8_000
export const NOTIFICATION_FADE_MS = 350
export const MEETING_LEAD_MINUTES = 10
export const MEETING_TOLERANCE_MS = 30_000
const STORAGE_KEY = 'chili-notification-seen'
const TELEGRAM_STORAGE_KEY = 'chili-telegram-sent'

const PRIORITY: Record<NotificationKind, number> = {
  meeting_soon: 1,
  walk_reminder: 2,
  task_completed: 3,
  openclaw_message: 4,
  voice_complete: 5,
  voice_error: 5,
  spotify_playing: 6,
}

export function notificationPriority(kind: NotificationKind): number {
  return PRIORITY[kind]
}

export function formatSpotifyPlaying(track: string, artist: string | null): string {
  return artist ? `Playing for you: ${track} — ${artist}` : `Playing for you: ${track}`
}

export function formatTaskCompleted(title: string): string {
  return `Good job finishing ${title}`
}

export function formatMeetingSoon(title: string, minutes: number): string {
  return `${title} starts in ${minutes} minutes`
}

export function formatVoiceHandled(transcript: string): string {
  const trimmed = transcript.trim()
  if (!trimmed) return 'Got it'
  const short = trimmed.length > 80 ? `${trimmed.slice(0, 77)}…` : trimmed
  return `Got it — ${short}`
}

export function formatVoiceError(message: string | null): string {
  return message?.trim() || 'Sorry, I could not handle that'
}

export function formatOpenClawMessageWaiting(): string {
  return 'New message from Chili on Telegram'
}

export function loadSeenKeys(): Set<string> {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((item): item is string => typeof item === 'string'))
  } catch {
    return new Set()
  }
}

export function markSeenKey(key: string, seen: Set<string>): Set<string> {
  const next = new Set(seen)
  next.add(key)
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify([...next]))
  } catch {
    // Ignore storage failures in kiosk profiles.
  }
  return next
}

export function hasSeenKey(key: string, seen: Set<string>): boolean {
  return seen.has(key)
}

export function loadTelegramSentKeys(): Set<string> {
  try {
    const raw = sessionStorage.getItem(TELEGRAM_STORAGE_KEY)
    if (!raw) return new Set()
    const parsed = JSON.parse(raw) as unknown
    if (!Array.isArray(parsed)) return new Set()
    return new Set(parsed.filter((item): item is string => typeof item === 'string'))
  } catch {
    return new Set()
  }
}

export function markTelegramSentKey(key: string, sent: Set<string>): Set<string> {
  const next = new Set(sent)
  next.add(key)
  try {
    sessionStorage.setItem(TELEGRAM_STORAGE_KEY, JSON.stringify([...next]))
  } catch {
    // Ignore storage failures in kiosk profiles.
  }
  return next
}

export function hasTelegramSentKey(key: string, sent: Set<string>): boolean {
  return sent.has(key)
}

export function insertByPriority(queue: ChiliNotification[], item: ChiliNotification): ChiliNotification[] {
  const next = [...queue, item]
  next.sort((left, right) => left.priority - right.priority || left.createdAt - right.createdAt)
  return next
}

export function eventIntersectsDay(event: CalendarEvent, dayKey: string): boolean {
  const start = new Date(`${dayKey}T00:00:00+09:00`).getTime()
  const end = start + 24 * 60 * 60 * 1000
  return new Date(event.start_at).getTime() < end && new Date(event.end_at).getTime() > start
}

export function findMeetingSoonEvents(
  calendar: CalendarToday,
  today: string,
  nowMs: number,
  leadMinutes = MEETING_LEAD_MINUTES,
  toleranceMs = MEETING_TOLERANCE_MS,
): CalendarEvent[] {
  if (calendar.status !== 'ready') return []
  const targetMs = leadMinutes * 60_000
  return calendar.events.filter((event) => {
    if (event.is_all_day) return false
    if (!eventIntersectsDay(event, today)) return false
    const delta = new Date(event.start_at).getTime() - nowMs
    return Math.abs(delta - targetMs) <= toleranceMs
  })
}

export function findCompletedTasks(
  previous: Map<string, string>,
  current: NotionTask[],
): Array<{ id: string, title: string }> {
  const currentIds = new Set(current.map((task) => task.id))
  const completed: Array<{ id: string, title: string }> = []
  for (const [id, title] of previous) {
    if (!currentIds.has(id)) completed.push({ id, title })
  }
  return completed
}

export function findNewAssistantMessages(
  previousIds: Set<string>,
  messages: OpenClawMessage[],
): OpenClawMessage[] {
  return messages.filter((message) => message.role === 'assistant' && !previousIds.has(message.id))
}

export function lastAssistantFingerprint(messages: OpenClawMessage[]): string | null {
  const last = [...messages].reverse().find((message) => message.role === 'assistant')
  if (!last) return null
  return `${last.created_at ?? ''}|${last.text}`
}

export function buildNotification(
  kind: NotificationKind,
  message: string,
  dedupeKey: string,
  options?: { sendTelegram?: boolean },
): ChiliNotification {
  return {
    id: `${kind}:${dedupeKey}:${Date.now()}`,
    kind,
    message,
    priority: notificationPriority(kind),
    dedupeKey,
    sendTelegram: options?.sendTelegram,
    createdAt: Date.now(),
  }
}

export function shouldPreempt(active: ChiliNotification | null, incoming: ChiliNotification): boolean {
  if (!active) return true
  return incoming.priority < active.priority
}

export function voiceTransitionNotification(
  previous: VoiceStatus,
  next: VoiceStatus,
): ChiliNotification | null {
  if (previous.state === next.state && previous.updated_at === next.updated_at) return null
  if (next.state === 'complete') {
    const text = next.transcript || next.message || ''
    const dedupeKey = `voice:complete:${next.updated_at ?? text}`
    return buildNotification('voice_complete', formatVoiceHandled(text), dedupeKey)
  }
  if (next.state === 'error') {
    const dedupeKey = `voice:error:${next.updated_at ?? next.message ?? 'error'}`
    return buildNotification('voice_error', formatVoiceError(next.message), dedupeKey)
  }
  return null
}

export function tasksFingerprint(tasks: NotionTask[]): string {
  return tasks.map((task) => task.id).sort().join(',')
}

export function tasksSnapshot(tasks: NotionTask[]): Map<string, string> {
  return new Map(tasks.map((task) => [task.id, task.title]))
}

export function assistantMessageIds(messages: OpenClawMessage[]): Set<string> {
  return new Set(messages.filter((message) => message.role === 'assistant').map((message) => message.id))
}
