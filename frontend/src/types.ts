export type LightState = 'on' | 'off' | 'unknown'
export type IntegrationStatus = 'not_configured' | 'ready' | 'unavailable'

export type Light = {
  last_command_state: LightState
  last_command_at: string | null
  available: boolean
}

export type WaterPump = {
  state: 'idle' | 'running'
  last_run_at: string | null
  last_run_status: string | null
  available: boolean
}

export type Display = {
  state: 'visible' | 'hidden'
  schedule_enabled: boolean
  schedule_on_hour: number
  schedule_off_hour: number
  power_available: boolean
  manual_override: boolean
}

export type Dashboard = {
  temperature_c: number | null
  humidity_percent: number | null
  last_updated_at: string | null
  light: Light
  water_pump: WaterPump
  system: SystemStatus
  display: Display
  integrations: Record<string, string>
}

export type SystemStatus = {
  cpu_temperature_c: number | null
  load_1m: number | null
  load_percent: number | null
  memory_used_percent: number | null
  memory_used_mb: number | null
  memory_total_mb: number | null
  storage_used_percent: number | null
  storage_free_gb: number | null
  storage_total_gb: number | null
  bluetooth_status: 'connected' | 'disconnected' | 'unavailable'
  bluetooth_device_name: string | null
  bluetooth_is_default_output: boolean
  volume_percent: number | null
  volume_available: boolean
  volume_output_label: string
}

export type Reading = {
  recorded_at: string
  temperature_c: number
  humidity_percent: number
}

export type CommandIntent =
  | 'light.turn_on'
  | 'light.turn_off'
  | 'water.run'
  | 'water.stop'
  | 'display.show'
  | 'display.hide'

export type CommandResult = {
  status: 'success' | 'failed' | 'skipped'
  intent: CommandIntent
  message: string | null
  light: Light | null
  water_pump: WaterPump | null
  display: Display | null
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
  status: string | null
  priority: string | null
  task_type: string | null
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

export type WalkingPadStatus = IntegrationStatus | 'walking'

export type WalkingPadToday = {
  status: WalkingPadStatus
  synced_at: string | null
  total_minutes: number
  total_distance_km: number
  total_steps: number
  total_calories: number
  goal_minutes: number
  goal_distance_km: number
  session_count: number
  goal_met: boolean
  active_session: {
    external_id: string
    started_at: string
    duration_seconds: number
    distance_km: number
    steps: number
    calories: number
  } | null
}

export type WalkReminder = {
  active: boolean
  message: string
  dedupe_key: string
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

export type VoiceState = 'offline' | 'idle' | 'listening' | 'thinking' | 'complete' | 'error'

export type VoiceStatus = {
  state: VoiceState
  updated_at: string | null
  transcript: string | null
  message: string | null
}

export type VoiceEventDirection = 'in' | 'out' | 'info'

export type ActivityEvent = {
  at: string
  direction: VoiceEventDirection
  service: string
  detail: string
}

export type VoiceEvent = ActivityEvent

export type WeatherIcon = 'sunny' | 'evening' | 'cloudy' | 'fog' | 'rain' | 'snow' | 'storm'

export type WeatherDay = {
  date: string
  label: string
  high_c: number
  low_c: number
  condition: string
  icon: WeatherIcon
  current_c?: number | null
}

export type WeatherForecast = {
  status: IntegrationStatus
  location: string
  synced_at: string | null
  today: WeatherDay | null
  tomorrow: WeatherDay | null
}
