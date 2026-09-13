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
  VoiceStatus,
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
} from '../types'

async function requireJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`)
  return response.json() as Promise<T>
}

export async function fetchDashboard() {
  return requireJson<Dashboard>(await fetch('/api/v1/dashboard'))
}

export async function fetchReadings() {
  const result = await requireJson<{ readings: Reading[] }>(
    await fetch('/api/v1/readings?hours=24'),
  )
  return result.readings
}

export async function fetchCalendarEvents(start: string, days = 30) {
  const query = new URLSearchParams({ start, days: String(days) })
  return requireJson<CalendarToday>(await fetch(`/api/v1/calendar/events?${query}`))
}

export async function fetchNotionToday() {
  return requireJson<NotionToday>(await fetch('/api/v1/notion/today'))
}

export async function fetchSpotifyNowPlaying() {
  return requireJson<SpotifyNowPlaying>(await fetch('/api/v1/spotify/now-playing'))
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

export async function fetchVoiceStatus() {
  return requireJson<VoiceStatus>(await fetch('/api/v1/voice/status'))
}

export async function fetchActivityEvents(limit = 40) {
  const query = new URLSearchParams({ limit: String(limit) })
  return requireJson<ActivityEvent[]>(await fetch(`/api/v1/activity/events?${query}`))
}

export async function fetchVoiceEvents(limit = 40) {
  return fetchActivityEvents(limit)
}

export async function fetchWeather() {
  return requireJson<WeatherForecast>(await fetch('/api/v1/weather'))
}

export async function fetchWalkingPadToday() {
  return requireJson<WalkingPadToday>(await fetch('/api/v1/walkingpad/today'))
}

export async function fetchWalkingPadReminder() {
  return requireJson<WalkReminder>(await fetch('/api/v1/walkingpad/reminder'))
}

export async function fetchTrainingOverview() {
  return requireJson<TrainingOverview>(await fetch('/api/v1/training/overview'))
}

export async function fetchTrainingPlans() {
  const result = await requireJson<{ plans: TrainingPlan[] }>(await fetch('/api/v1/training/plans'))
  return result.plans
}

export async function fetchTrainingPlan(slug: string) {
  return requireJson<TrainingPlan>(await fetch(`/api/v1/training/plans/${slug}`))
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

export async function fetchDailyBriefing(day: string, preview?: string) {
  const query = preview ? `?preview=${encodeURIComponent(preview)}` : ''
  return requireJson<DailyBriefing>(await fetch(`/api/v1/daily/${day}${query}`))
}

export async function logDailyWorkout(day: string, payload: WorkoutLogPayload) {
  return requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/workout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function logWorkout(payload: WorkoutLogPayload) {
  return requireJson<TrainingLogResult>(await fetch('/api/v1/training/workout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function logSober(day: string, payload: { sober: boolean; note?: string }) {
  return requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/sober`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
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
