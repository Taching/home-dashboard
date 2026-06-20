import type {
  CalendarToday,
  CommandIntent,
  CommandResult,
  Dashboard,
  NotionToday,
  Reading,
  SpotifyNowPlaying,
  OpenClawConversation,
  OpenClawSendResult,
} from '../types'

async function requireJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`)
  return response.json() as Promise<T>
}

export async function fetchDashboard(signal?: AbortSignal) {
  return requireJson<Dashboard>(await fetch('/api/v1/dashboard', { signal }))
}

export async function fetchReadings(hours: number, signal?: AbortSignal) {
  const result = await requireJson<{ readings: Reading[] }>(
    await fetch(`/api/v1/readings?hours=${hours}`, { signal }),
  )
  return result.readings
}

export async function fetchCalendarEvents(start: string, days: number, signal?: AbortSignal) {
  const query = new URLSearchParams({ start, days: String(days) })
  return requireJson<CalendarToday>(await fetch(`/api/v1/calendar/events?${query}`, { signal }))
}

export async function fetchNotionToday(signal?: AbortSignal) {
  return requireJson<NotionToday>(await fetch('/api/v1/notion/today', { signal }))
}

export async function fetchSpotifyNowPlaying(signal?: AbortSignal) {
  return requireJson<SpotifyNowPlaying>(await fetch('/api/v1/spotify/now-playing', { signal }))
}

export async function fetchOpenClawMessages(signal?: AbortSignal) {
  return requireJson<OpenClawConversation>(await fetch('/api/v1/openclaw/messages', { signal }))
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

export async function sendCommand(intent: CommandIntent): Promise<CommandResult> {
  return requireJson<CommandResult>(await fetch('/api/v1/commands', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ intent, source: 'ui' }),
  }))
}
