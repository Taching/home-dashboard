import { useCallback, useEffect, useRef, useState, type SetStateAction } from 'react'
import { dayKey } from '../components/PlanningRegion'
import {
  fetchCalendarEvents,
  fetchDashboard,
  fetchNotionToday,
  fetchOpenClawMessages,
  fetchReadings,
  fetchSpotifyNowPlaying,
} from '../lib/api'
import type { CalendarToday, Dashboard, DashboardUiConfig, NotionToday, OpenClawConversation, Reading, SpotifyNowPlaying } from '../types'

const BOOTSTRAP_UI_CONFIG: DashboardUiConfig = {
  timezone: 'Asia/Tokyo',
  sensor_stale_after_seconds: 900,
  dashboard_refresh_interval_seconds: 60,
  openclaw_refresh_interval_seconds: 10,
  readings_history_hours: 24,
  calendar_range_days: 30,
}

const initialDashboard: Dashboard = {
  temperature_c: null,
  humidity_percent: null,
  last_updated_at: null,
  light: { last_command_state: 'unknown', last_command_at: null, available: false },
  display: { state: 'visible' },
  ui: BOOTSTRAP_UI_CONFIG,
  integrations: { sensor: 'pending', broadlink: 'pending', calendar: 'not_configured', notion: 'not_configured', spotify: 'not_configured', openclaw: 'not_configured' },
}

const initialCalendar: CalendarToday = { status: 'not_configured', synced_at: null, events: [] }
const initialNotion: NotionToday = { status: 'not_configured', synced_at: null, tasks: [] }
const initialSpotify: SpotifyNowPlaying = { status: 'not_configured', synced_at: null, track: null, artist: null, artwork_url: null, device_name: null, is_playing: false }
const initialOpenClaw: OpenClawConversation = { status: 'not_configured', messages: [], message: null }

type DashboardData = {
  dashboard: Dashboard
  readings: Reading[]
  calendar: CalendarToday
  notion: NotionToday
  spotify: SpotifyNowPlaying
  openclaw: OpenClawConversation
  loading: boolean
  refresh: () => Promise<void>
  refreshOpenClaw: () => Promise<void>
  updateDashboard: (update: SetStateAction<Dashboard>) => void
}

export function useDashboardData(): DashboardData {
  const [dashboard, setDashboard] = useState(initialDashboard)
  const [readings, setReadings] = useState<Reading[]>([])
  const [calendar, setCalendar] = useState(initialCalendar)
  const [notion, setNotion] = useState(initialNotion)
  const [spotify, setSpotify] = useState(initialSpotify)
  const [openclaw, setOpenclaw] = useState(initialOpenClaw)
  const [loading, setLoading] = useState(true)
  const dashboardRef = useRef(initialDashboard)
  const controllerRef = useRef<AbortController | null>(null)
  const refreshRef = useRef<() => Promise<void>>(async () => {})

  const refreshOpenClaw = useCallback(async () => {
    if (dashboardRef.current.integrations.openclaw !== 'ready') return
    try { setOpenclaw(await fetchOpenClawMessages()) } catch { /* Retain the last known transcript. */ }
  }, [])

  const refresh = useCallback(async () => {
    controllerRef.current?.abort()
    const controller = new AbortController()
    controllerRef.current = controller
    const { signal } = controller

    try {
      const nextDashboard = await fetchDashboard(signal)
      if (signal.aborted) return
      dashboardRef.current = nextDashboard
      setDashboard(nextDashboard)
      const { integrations, ui } = nextDashboard
      const requests: Promise<void>[] = [
        fetchReadings(ui.readings_history_hours, signal).then(setReadings),
      ]
      if (integrations.calendar === 'ready') {
        requests.push(fetchCalendarEvents(dayKey(new Date()), ui.calendar_range_days, signal).then(setCalendar))
      } else {
        setCalendar({ ...initialCalendar, status: integrations.calendar as CalendarToday['status'] })
      }
      if (integrations.notion === 'ready') requests.push(fetchNotionToday(signal).then(setNotion))
      else setNotion({ ...initialNotion, status: integrations.notion as NotionToday['status'] })
      if (integrations.spotify === 'ready') requests.push(fetchSpotifyNowPlaying(signal).then(setSpotify))
      else setSpotify({ ...initialSpotify, status: integrations.spotify as SpotifyNowPlaying['status'] })
      if (integrations.openclaw !== 'ready') {
        setOpenclaw({ ...initialOpenClaw, status: integrations.openclaw as OpenClawConversation['status'] })
      }
      await Promise.allSettled(requests)
    } catch (error) {
      if (!(error instanceof DOMException && error.name === 'AbortError')) {
        // Preserve the last successful snapshot; the scheduler will retry.
      }
    } finally {
      if (!signal.aborted) setLoading(false)
    }
  }, [])

  refreshRef.current = refresh

  const updateDashboard = useCallback((update: SetStateAction<Dashboard>) => {
    setDashboard((current) => {
      const next = typeof update === 'function'
        ? (update as (value: Dashboard) => Dashboard)(current)
        : update
      dashboardRef.current = next
      return next
    })
  }, [])

  useEffect(() => {
    let timer: number | undefined
    let disposed = false
    let nextSnapshotAt = 0
    let nextOpenClawAt = 0

    const schedule = () => {
      if (disposed || document.visibilityState !== 'visible') return
      const now = Date.now()
      const delay = Math.max(0, Math.min(nextSnapshotAt || now, nextOpenClawAt || now) - now)
      timer = window.setTimeout(run, delay)
    }

    const run = async () => {
      if (disposed || document.visibilityState !== 'visible' || !navigator.onLine) return
      const now = Date.now()
      if (now >= nextSnapshotAt) {
        await refreshRef.current()
        nextSnapshotAt = Date.now() + dashboardRef.current.ui.dashboard_refresh_interval_seconds * 1000
      }
      if (Date.now() >= nextOpenClawAt) {
        await refreshOpenClaw()
        nextOpenClawAt = Date.now() + dashboardRef.current.ui.openclaw_refresh_interval_seconds * 1000
      }
      schedule()
    }

    const resume = () => {
      if (document.visibilityState !== 'visible' || !navigator.onLine) return
      window.clearTimeout(timer)
      nextSnapshotAt = 0
      nextOpenClawAt = 0
      void run()
    }

    void run()
    document.addEventListener('visibilitychange', resume)
    window.addEventListener('online', resume)
    return () => {
      disposed = true
      window.clearTimeout(timer)
      controllerRef.current?.abort()
      document.removeEventListener('visibilitychange', resume)
      window.removeEventListener('online', resume)
    }
  }, [refreshOpenClaw])

  return { dashboard, readings, calendar, notion, spotify, openclaw, loading, refresh, refreshOpenClaw, updateDashboard }
}
