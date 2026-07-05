import { useCallback, useEffect, useState } from 'react'
import { dayKey } from '../components/PlanningRegion'
import {
  fetchCalendarEvents,
  fetchDashboard,
  fetchNotionToday,
  fetchOpenClawMessages,
  fetchSpotifyNowPlaying,
  fetchWeather,
  openOpenClawMessageStream,
  sendOpenClawMessage,
  setSystemVolume,
} from '../lib/api'
import type { CalendarToday, Dashboard, NotionToday, OpenClawConversation, SpotifyNowPlaying, WeatherForecast } from '../types'
import { usePolling } from './usePolling'

const initialDashboard: Dashboard = {
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
  display: { state: 'visible' },
  integrations: { sensor: 'pending', broadlink: 'pending', calendar: 'not_configured', notion: 'not_configured', spotify: 'not_configured', openclaw: 'not_configured' },
}

const initialCalendar: CalendarToday = { status: 'not_configured', synced_at: null, events: [] }
const initialNotion: NotionToday = { status: 'not_configured', synced_at: null, tasks: [] }
const initialSpotify: SpotifyNowPlaying = { status: 'not_configured', synced_at: null, track: null, artist: null, artwork_url: null, device_name: null, is_playing: false }
const initialOpenClaw: OpenClawConversation = { status: 'not_configured', messages: [], message: null }
const initialWeather: WeatherForecast = { status: 'not_configured', location: '', synced_at: null, today: null, tomorrow: null }

const DASHBOARD_REFRESH_MS = 60_000
const DASHBOARD_FAST_REFRESH_MS = 2_000
const CALENDAR_REFRESH_MS = 15 * 60_000
const WEATHER_REFRESH_MS = 30 * 60_000
const OPENCLAW_FALLBACK_REFRESH_MS = 5_000

export function useDashboardData(today: string) {
  const [dashboard, setDashboard] = useState<Dashboard>(initialDashboard)
  const [calendar, setCalendar] = useState<CalendarToday>(initialCalendar)
  const [notion, setNotion] = useState<NotionToday>(initialNotion)
  const [spotify, setSpotify] = useState<SpotifyNowPlaying>(initialSpotify)
  const [openclaw, setOpenClaw] = useState<OpenClawConversation>(initialOpenClaw)
  const [weather, setWeather] = useState<WeatherForecast>(initialWeather)
  const [openclawPending, setOpenClawPending] = useState(false)
  const [openclawFeedback, setOpenClawFeedback] = useState<string | null>(null)
  const [selectedCalendarDate, setSelectedCalendarDate] = useState<string | null>(null)
  const [volumePending, setVolumePending] = useState(false)

  const refresh = useCallback(async () => {
    const results = await Promise.allSettled([
      fetchDashboard(), fetchNotionToday(), fetchSpotifyNowPlaying(), fetchOpenClawMessages(),
    ])
    if (results[0].status === 'fulfilled') setDashboard(results[0].value)
    if (results[1].status === 'fulfilled') setNotion(results[1].value)
    if (results[2].status === 'fulfilled') setSpotify(results[2].value)
    if (results[3].status === 'fulfilled') setOpenClaw(results[3].value)
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
      setOpenClawFeedback(null)
      setOpenClaw(await fetchOpenClawMessages())
    } catch (error) {
      setOpenClawFeedback(error instanceof Error ? error.message : 'Telegram delivery failed.')
    } finally {
      setOpenClawPending(false)
    }
  }, [])

  const dashboardRefreshMs = dashboard.water_pump.state === 'running' ? DASHBOARD_FAST_REFRESH_MS : DASHBOARD_REFRESH_MS
  usePolling(refresh, dashboardRefreshMs)
  usePolling(refreshCalendar, CALENDAR_REFRESH_MS)
  usePolling(refreshWeather, WEATHER_REFRESH_MS)

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
