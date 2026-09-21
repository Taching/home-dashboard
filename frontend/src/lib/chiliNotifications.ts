import type { CalendarEvent, CalendarToday, NotionTask, OpenClawMessage } from '../types'

export type NotificationKind =
  | 'meeting_soon'
  | 'plan_adjusted'
  | 'walk_reminder'
  | 'task_completed'
  | 'openclaw_message'
  | 'spotify_playing'

export type ChiliNotification = {
  id: string
  kind: NotificationKind
  message: string
  priority: number
  dedupeKey: string
  sendTelegram?: boolean
  ttlMs?: number
  createdAt: number
}

export const NOTIFICATION_TTL_MS = 8_000
export const NOTIFICATION_FADE_MS = 350
export const MEETING_LEAD_MINUTES = 10
export const MEETING_TOLERANCE_MS = 30_000
const STORAGE_KEY = 'chili-notification-seen'
const TELEGRAM_STORAGE_KEY = 'chili-telegram-sent'

export const PLAN_ADJUST_TTL_MS = 20_000

const PRIORITY: Record<NotificationKind, number> = {
  meeting_soon: 1,
  plan_adjusted: 2,
  walk_reminder: 3,
  task_completed: 4,
  openclaw_message: 5,
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

export function formatPlanAdjusted(banner: string): string {
  const text = banner.trim()
  return text || 'Changed the week. Check How and Why.'
}

export function buildNotification(
  kind: NotificationKind,
  message: string,
  dedupeKey: string,
  options?: { sendTelegram?: boolean, ttlMs?: number },
): ChiliNotification {
  return {
    id: `${kind}:${dedupeKey}:${Date.now()}`,
    kind,
    message,
    priority: notificationPriority(kind),
    dedupeKey,
    sendTelegram: options?.sendTelegram,
    ttlMs: options?.ttlMs,
    createdAt: Date.now(),
  }
}

export function shouldPreempt(active: ChiliNotification | null, incoming: ChiliNotification): boolean {
  if (!active) return true
  return incoming.priority < active.priority
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
