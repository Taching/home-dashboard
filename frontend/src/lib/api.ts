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
  VoiceStatus,
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
