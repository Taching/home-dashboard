export type LightState = 'on' | 'off' | 'unknown'
export type IntegrationStatus = 'not_configured' | 'ready' | 'unavailable'

export type Light = {
  last_command_state: LightState
  last_command_at: string | null
  available: boolean
}

export type Dashboard = {
  temperature_c: number | null
  humidity_percent: number | null
  last_updated_at: string | null
  light: Light
  display: { state: string }
  ui: DashboardUiConfig
  integrations: Record<string, string>
}

export type DashboardUiConfig = {
  timezone: string
  sensor_stale_after_seconds: number
  dashboard_refresh_interval_seconds: number
  openclaw_refresh_interval_seconds: number
  readings_history_hours: number
  calendar_range_days: number
}

export type Reading = {
  recorded_at: string
  temperature_c: number
  humidity_percent: number
}

export type CommandIntent =
  | 'light.turn_on'
  | 'light.turn_off'
  | 'display.show'
  | 'display.hide'

export type CommandResult = {
  status: 'success' | 'failed'
  intent: CommandIntent
  message: string | null
  light: Light | null
}

export type CalendarEvent = {
  id: string
  title: string
  start_at: string
  end_at: string
  is_all_day: boolean
  is_current: boolean
}

export type CalendarToday = {
  status: IntegrationStatus
  synced_at: string | null
  events: CalendarEvent[]
}

export type NotionTask = {
  id: string
  title: string
  due_at: string | null
  is_overdue: boolean
}

export type NotionToday = {
  status: IntegrationStatus
  synced_at: string | null
  tasks: NotionTask[]
}

export type SpotifyNowPlaying = {
  status: IntegrationStatus
  synced_at: string | null
  track: string | null
  artist: string | null
  artwork_url: string | null
  device_name: string | null
  is_playing: boolean
}

export type OpenClawMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  created_at: string | null
}

export type OpenClawConversation = {
  status: IntegrationStatus
  messages: OpenClawMessage[]
  message: string | null
}

export type OpenClawSendResult = {
  status: 'success' | 'failed'
  delivery_status: string | null
  reply: string | null
  message: string | null
}
