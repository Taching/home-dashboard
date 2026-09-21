import type {
  CalendarToday,
  CommandIntent,
  CommandResult,
  Dashboard,
  Display,
  NotionToday,
  Reading,
  SpotifyNowPlaying,
  OpenClawConversation,
  OpenClawSendResult,
  ActivityEvent,
  WeatherForecast,
  WalkReminder,
  WalkingPadToday,
  TrainingOverview,
  TrainingPlan,
  TrainingToday,
  TrainingLogPayload,
  TrainingLogResult,
  WorkoutLogPayload,
  DailyBriefing,
  TrainingSession,
  WeeklyReview,
  PlanAdjustment,
  TrainingPreferences,
} from '../types'
import { announcePlanningChange } from './planningRefresh'

async function requireJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`)
  return response.json() as Promise<T>
}

const GET_TIMEOUT_MS = 8_000

async function freshGet(path: string, signal?: AbortSignal) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), GET_TIMEOUT_MS)
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  try {
    return await fetch(path, {
      cache: 'no-store',
      headers: { 'Cache-Control': 'no-cache' },
      signal: controller.signal,
    })
  } finally {
    window.clearTimeout(timeout)
    signal?.removeEventListener('abort', abort)
  }
}

export async function fetchDashboard(signal?: AbortSignal) {
  return requireJson<Dashboard>(await freshGet('/api/v1/dashboard', signal))
}

export async function fetchReadings() {
  const result = await requireJson<{ readings: Reading[] }>(
    await fetch('/api/v1/readings?hours=24'),
  )
  return result.readings
}

export async function fetchCalendarEvents(start: string, days = 30, signal?: AbortSignal) {
  const query = new URLSearchParams({ start, days: String(days) })
  return requireJson<CalendarToday>(await freshGet(`/api/v1/calendar/events?${query}`, signal))
}

export async function fetchNotionToday() {
  return requireJson<NotionToday>(await fetch('/api/v1/notion/today'))
}

export async function fetchSpotifyNowPlaying(signal?: AbortSignal) {
  return requireJson<SpotifyNowPlaying>(await freshGet('/api/v1/spotify/now-playing', signal))
}

export async function fetchOpenClawMessages() {
  return requireJson<OpenClawConversation>(await fetch('/api/v1/openclaw/messages'))
}

export function openOpenClawMessageStream(
  onConversation: (conversation: OpenClawConversation) => void,
  onError?: () => void,
) {
  const stream = new EventSource('/api/v1/openclaw/messages/stream')
  stream.addEventListener('conversation', (event) => {
    onConversation(JSON.parse((event as MessageEvent).data) as OpenClawConversation)
  })
  stream.onerror = () => onError?.()
  return stream
}

export async function fetchActivityEvents(limit = 40) {
  const query = new URLSearchParams({ limit: String(limit) })
  return requireJson<ActivityEvent[]>(await fetch(`/api/v1/activity/events?${query}`))
}

export async function fetchWeather(signal?: AbortSignal) {
  return requireJson<WeatherForecast>(await freshGet('/api/v1/weather', signal))
}

export async function fetchWalkingPadToday(signal?: AbortSignal) {
  return requireJson<WalkingPadToday>(await freshGet('/api/v1/walkingpad/today', signal))
}

export async function fetchWalkingPadReminder() {
  return requireJson<WalkReminder>(await fetch('/api/v1/walkingpad/reminder'))
}

export async function fetchTrainingOverview(signal?: AbortSignal) {
  return requireJson<TrainingOverview>(await freshGet('/api/v1/training/overview', signal))
}

export async function fetchTrainingPlans() {
  const result = await requireJson<{ plans: TrainingPlan[] }>(await fetch('/api/v1/training/plans'))
  return result.plans
}

export async function fetchTrainingPlan(slug: string) {
  return requireJson<TrainingPlan>(await fetch(`/api/v1/training/plans/${slug}`))
}

export async function fetchTrainingSession(sessionId: string, signal?: AbortSignal) {
  return requireJson<TrainingSession>(await freshGet(`/api/v1/training/sessions/${sessionId}`, signal))
}

export async function logTrainingSessionResult(sessionId: string, payload: Record<string, unknown>) {
  const result = await requireJson<TrainingSession>(await fetch(`/api/v1/training/sessions/${sessionId}/result`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  announcePlanningChange()
  return result
}

export async function askCoach(sessionId: string) {
  return requireJson<{ advice: string; source: string }>(
    await fetch(`/api/v1/training/sessions/${sessionId}/coach`, { method: 'POST' }),
  )
}

export async function fetchTrainingPreferences(signal?: AbortSignal) {
  return requireJson<TrainingPreferences>(await freshGet('/api/v1/training/preferences', signal))
}

export async function saveTrainingPreferences(notes: string) {
  return requireJson<TrainingPreferences>(await fetch('/api/v1/training/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes: notes.trim() || null }),
  }))
}

export async function requestScheduleChange(instruction: string) {
  const response = await fetch('/api/v1/training/replan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `Request failed with status ${response.status}`)
  }
  const result = await response.json() as { decision: PlanAdjustment; status: string }
  announcePlanningChange()
  return result
}

export async function fetchWeeklyReview(weekStart: string, signal?: AbortSignal) {
  return requireJson<WeeklyReview>(await freshGet(`/api/v1/training/weeks/${weekStart}/review`, signal))
}

export async function runWeeklyReview(weekStart: string) {
  const result = await requireJson<WeeklyReview>(await fetch(`/api/v1/training/weeks/${weekStart}/review`, {
    method: 'POST',
  }))
  announcePlanningChange()
  return result
}

export async function postDailyConstraint(day: string, payload: { kind: 'cannot_train' | 'holiday' | 'no_class' | 'miss'; miss_reason?: string; note?: string }) {
  const result = await requireJson<DailyBriefing>(await fetch(`/api/v1/daily/${day}/constraint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  announcePlanningChange()
  return result
}

export async function fetchTrainingToday() {
  return requireJson<TrainingToday>(await fetch('/api/v1/training/today'))
}

export async function logTraining(payload: TrainingLogPayload) {
  return requireJson<TrainingLogResult>(await fetch('/api/v1/training/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function fetchDailyBriefing(day: string, preview?: string, signal?: AbortSignal) {
  const query = preview ? `?preview=${encodeURIComponent(preview)}` : ''
  return requireJson<DailyBriefing>(await freshGet(`/api/v1/daily/${day}${query}`, signal))
}

export async function fetchDailyPlan(day: string, signal?: AbortSignal) {
  return requireJson<DailyBriefing>(await freshGet(`/api/v1/plan/${day}`, signal))
}

export async function logDailyWorkout(day: string, payload: WorkoutLogPayload) {
  const result = await requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/workout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  announcePlanningChange()
  return result
}

export async function logWorkout(payload: WorkoutLogPayload) {
  const result = await requireJson<TrainingLogResult>(await fetch('/api/v1/training/workout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  announcePlanningChange()
  return result
}

export async function logSober(day: string, payload: { sober: boolean; note?: string }) {
  return requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/sober`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function logSleep(day: string, hours: number) {
  return requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/sleep`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hours }),
  }))
}

export async function closeDailyDay(day: string, force = false) {
  return requireJson<DailyBriefing>(await fetch(`/api/v1/daily/${day}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force }),
  }))
}

export async function logSundayReview(
  day: string,
  payload: { weight_kg?: number; same_as_last?: boolean; note?: string },
) {
  return requireJson<DailyBriefing>(await fetch(`/api/v1/daily/${day}/sunday`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function sendOpenClawMessage(message: string) {
  return requireJson<OpenClawSendResult>(await fetch('/api/v1/openclaw/messages', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  }))
}

export async function fetchSpotifyWebPlaybackToken() {
  return requireJson<{ access_token: string }>(await fetch('/api/v1/spotify/web-playback-token'))
}

export async function transferSpotifyPlayback(deviceId: string) {
  return requireJson<{ status: string }>(await fetch('/api/v1/spotify/transfer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_id: deviceId }),
  }))
}

export async function registerSpotifyDevice(deviceId: string) {
  return requireJson<{ status: string }>(await fetch('/api/v1/spotify/device', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: deviceId }),
  }))
}

export async function startSpotifyDj() {
  return requireJson<{ status: string }>(await fetch('/api/v1/spotify/dj', { method: 'POST' }))
}

export async function setSystemVolume(volumePercent: number) {
  return requireJson<{ volume_percent: number | null; available: boolean; output_label: string }>(
    await fetch('/api/v1/system/volume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume_percent: volumePercent }),
    }),
  )
}

export async function sendCommand(intent: CommandIntent): Promise<CommandResult> {
  return requireJson<CommandResult>(await fetch('/api/v1/commands', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ intent, source: 'ui' }),
  }))
}

export async function setDisplaySchedule(enabled: boolean) {
  return requireJson<Display>(await fetch('/api/v1/display/schedule', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  }))
}

export async function notifyChili(message: string, dedupeKey: string) {
  return requireJson<{ status: 'sent' | 'skipped' | 'not_configured' | 'failed', message?: string | null }>(
    await fetch('/api/v1/chili/notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, dedupe_key: dedupeKey }),
    }),
  )
}
