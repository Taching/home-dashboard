import { useCallback, useEffect, useState } from 'react'
import { dayKey } from '../components/PlanningRegion'
import {
  fetchCalendarEvents,
  fetchDashboard,
  fetchNotionToday,
  fetchOpenClawMessages,
  fetchSpotifyNowPlaying,
  fetchWalkingPadReminder,
  fetchWalkingPadToday,
  fetchWeather,
  openOpenClawMessageStream,
  sendOpenClawMessage,
  setSystemVolume,
} from '../lib/api'
import type { CalendarToday, Dashboard, NotionToday, OpenClawConversation, SpotifyNowPlaying, WalkReminder, WalkingPadToday, WeatherForecast } from '../types'
import { usePolling } from './usePolling'

export const initialDashboard: Dashboard = {
  temperature_c: null,
  humidity_percent: null,
  last_updated_at: null,
  light: { last_command_state: 'unknown', last_command_at: null, available: false },
  water_pump: { state: 'idle', last_run_at: null, last_run_status: null, available: false },
  system: {
    cpu_temperature_c: null,
    load_1m: null,
    load_percent: null,
    memory_used_percent: null,
    memory_used_mb: null,
    memory_total_mb: null,
    storage_used_percent: null,
    storage_free_gb: null,
    storage_total_gb: null,
    bluetooth_status: 'unavailable',
    bluetooth_device_name: null,
    bluetooth_is_default_output: false,
    volume_percent: null,
    volume_available: false,
    volume_output_label: 'Audio output',
  },
  display: {
    state: 'visible',
    schedule_enabled: true,
    schedule_on_hour: 8,
    schedule_off_hour: 22,
    power_available: false,
    manual_override: false,
  },
  integrations: { sensor: 'pending', broadlink: 'pending', calendar: 'not_configured', notion: 'not_configured', spotify: 'not_configured', openclaw: 'not_configured' },
}

export const initialCalendar: CalendarToday = { status: 'not_configured', synced_at: null, events: [] }
export const initialNotion: NotionToday = { status: 'not_configured', synced_at: null, tasks: [] }
export const initialSpotify: SpotifyNowPlaying = { status: 'not_configured', synced_at: null, track: null, artist: null, artwork_url: null, device_name: null, is_playing: false }
export const initialOpenClaw: OpenClawConversation = { status: 'not_configured', messages: [], message: null }
export const initialWeather: WeatherForecast = { status: 'not_configured', location: '', synced_at: null, today: null, tomorrow: null }
export const initialWalkingPad: WalkingPadToday = {
  status: 'not_configured',
  synced_at: null,
  total_minutes: 0,
  total_distance_km: 0,
  total_steps: 0,
  total_calories: 0,
  goal_minutes: 45,
  goal_distance_km: 3,
  session_count: 0,
  goal_met: false,
  active_session: null,
}
export const initialWalkReminder: WalkReminder = { active: false, message: '', dedupe_key: '' }

const DASHBOARD_REFRESH_MS = 60_000
const DASHBOARD_FAST_REFRESH_MS = 2_000
const NOTION_REFRESH_MS = 30_000
const WALKINGPAD_REFRESH_MS = 30_000
const CALENDAR_REFRESH_MS = 15 * 60_000
const WEATHER_REFRESH_MS = 30 * 60_000
const OPENCLAW_FALLBACK_REFRESH_MS = 5_000

export type DashboardInitialData = {
  dashboard: Dashboard
  calendar: CalendarToday
  notion: NotionToday
  spotify: SpotifyNowPlaying
  openclaw: OpenClawConversation
  weather: WeatherForecast
  walkingPad?: WalkingPadToday
  walkReminder?: WalkReminder
  selectedCalendarDate?: string | null
}

export function useDashboardData(today: string, initialData?: DashboardInitialData) {
  const [dashboard, setDashboard] = useState(initialData?.dashboard ?? initialDashboard)
  const [calendar, setCalendar] = useState(initialData?.calendar ?? initialCalendar)
  const [notion, setNotion] = useState(initialData?.notion ?? initialNotion)
  const [spotify, setSpotify] = useState(initialData?.spotify ?? initialSpotify)
  const [openclaw, setOpenClaw] = useState(initialData?.openclaw ?? initialOpenClaw)
  const [weather, setWeather] = useState(initialData?.weather ?? initialWeather)
  const [walkingPad, setWalkingPad] = useState(initialData?.walkingPad ?? initialWalkingPad)
  const [walkReminder, setWalkReminder] = useState(initialData?.walkReminder ?? initialWalkReminder)
  const [openclawPending, setOpenClawPending] = useState(false)
  const [openclawFeedback, setOpenClawFeedback] = useState<string | null>(null)
  const [selectedCalendarDate, setSelectedCalendarDate] = useState<string | null>(
    initialData?.selectedCalendarDate ?? null,
  )
  const [volumePending, setVolumePending] = useState(false)
  const skipImmediatePoll = Boolean(initialData)

  const refreshNotion = useCallback(async () => {
    try {
      setNotion(await fetchNotionToday())
    } catch {
      // Keep the last Notion snapshot until the next refresh succeeds.
    }
  }, [])

  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([
      fetchDashboard(), fetchSpotifyNowPlaying(), fetchOpenClawMessages(),
    ])
    if (results[0].status === 'fulfilled') setDashboard(results[0].value)
    if (results[1].status === 'fulfilled') setSpotify(results[1].value)
    if (results[2].status === 'fulfilled') setOpenClaw(results[2].value)
  }, [])

  const refreshCalendar = useCallback(async () => {
    try {
      const nextCalendar = await fetchCalendarEvents(today)
      setCalendar(nextCalendar)
      setSelectedCalendarDate((current) => {
        if (current || nextCalendar.status !== 'ready') return current
        const nextScheduled = nextCalendar.events
          .map((event) => dayKey(event.start_at))
          .find((eventDate) => eventDate >= today)
        return nextScheduled ?? today
      })
    } catch {
      // Keep the last calendar snapshot visible until the next bridge sync lands.
    }
  }, [today])

  const refreshWeather = useCallback(async () => {
    try {
      setWeather(await fetchWeather())
    } catch {
      // Retry on the next scheduled weather refresh.
    }
  }, [])

  const refreshWalkingPad = useCallback(async () => {
    try {
      const [todaySnapshot, reminder] = await Promise.all([
        fetchWalkingPadToday(),
        fetchWalkingPadReminder(),
      ])
      setWalkingPad(todaySnapshot)
      setWalkReminder(reminder)
    } catch {
      // Keep the last walking snapshot until the next refresh succeeds.
    }
  }, [])

  const refreshOpenClaw = useCallback(async () => {
    try {
      setOpenClaw(await fetchOpenClawMessages())
    } catch {
      setOpenClaw({ status: 'unavailable', messages: [], message: 'OpenClaw is unavailable.' })
    }
  }, [])

  const setVolume = useCallback((volumePercent: number) => {
    setVolumePending(true)
    void setSystemVolume(volumePercent)
      .then((result) => {
        if (result.volume_percent === null) return
        setDashboard((current) => ({
          ...current,
          system: {
            ...current.system,
            volume_percent: result.volume_percent,
            volume_available: result.available,
            volume_output_label: result.output_label,
          },
        }))
      })
      .finally(() => setVolumePending(false))
  }, [])

  const sendToOpenClaw = useCallback(async (message: string) => {
    setOpenClawPending(true)
    setOpenClawFeedback(null)
    try {
      const result = await sendOpenClawMessage(message)
      if (result.status !== 'success') throw new Error(result.message ?? 'Telegram delivery failed.')
      if (result.reply?.startsWith('Logged walk:')) {
        await refreshWalkingPad()
        setOpenClawFeedback(result.reply)
        return
      }
      setOpenClawFeedback(null)
      setOpenClaw(await fetchOpenClawMessages())
    } catch (error) {
      setOpenClawFeedback(error instanceof Error ? error.message : 'Telegram delivery failed.')
    } finally {
      setOpenClawPending(false)
    }
  }, [refreshWalkingPad])

  const dashboardRefreshMs = dashboard.water_pump.state === 'running' ? DASHBOARD_FAST_REFRESH_MS : DASHBOARD_REFRESH_MS
  usePolling(refresh, dashboardRefreshMs, !skipImmediatePoll)
  usePolling(refreshNotion, NOTION_REFRESH_MS, !skipImmediatePoll)
  usePolling(refreshCalendar, CALENDAR_REFRESH_MS, !skipImmediatePoll)
  usePolling(refreshWeather, WEATHER_REFRESH_MS, !skipImmediatePoll)
  usePolling(refreshWalkingPad, WALKINGPAD_REFRESH_MS, true)

  useEffect(() => {
    if (typeof EventSource === 'undefined') {
      const interval = window.setInterval(async () => {
        try { setOpenClaw(await fetchOpenClawMessages()) } catch { /* retry on next interval */ }
      }, OPENCLAW_FALLBACK_REFRESH_MS)
      return () => window.clearInterval(interval)
    }

    const stream = openOpenClawMessageStream(setOpenClaw)
    return () => stream.close()
  }, [])

  return {
    dashboard,
    calendar,
    notion,
    spotify,
    openclaw,
    weather,
    walkingPad,
    walkReminder,
    openclawPending,
    openclawFeedback,
    selectedCalendarDate,
    volumePending,
    setDashboard,
    setSelectedCalendarDate,
    refresh,
    refreshCalendar,
    refreshOpenClaw,
    setVolume,
    sendToOpenClaw,
  }
}
