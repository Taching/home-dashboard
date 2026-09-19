import { useCallback, useEffect, useState, type SetStateAction } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { addDays } from '../components/PlanningRegion'
import {
  fetchCalendarEvents,
  fetchDashboard,
  fetchSpotifyNowPlaying,
  fetchWalkingPadToday,
  fetchWeather,
  fetchDailyPlan,
  fetchTrainingOverview,
  setSystemVolume,
} from '../lib/api'
import { notionFromPlan, trainingOverviewFromPlan, walkReminderFromPlan } from '../lib/dailyPlan'
import { subscribeToPlanningChanges } from '../lib/planningRefresh'
import type { CalendarToday, DailyBriefing, Dashboard, NotionToday, SpotifyNowPlaying, TrainingOverview, WalkReminder, WalkingPadToday, WeatherForecast } from '../types'
import { usePolling } from './usePolling'

/** Calendar API max is 30 days; anchor 7 days before the selected day. */
const CALENDAR_LOOKBACK_DAYS = 7
const CALENDAR_WINDOW_DAYS = 30

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
  wellbeing: {
    sober_days: 0,
    workouts_this_week: 0,
    gym_this_week: 0,
    jiujitsu_this_week: 0,
    gym_weekly_goal: 3,
    jiujitsu_weekly_goal: 3,
    week_start: '2026-09-07',
    latest_checkin_date: null,
    checkin_stale: true,
    current_weight_kg: null,
    weight_goal_kg: 74,
    latest_weight_date: null,
  },
}

export const initialCalendar: CalendarToday = { status: 'not_configured', synced_at: null, events: [] }
export const initialNotion: NotionToday = { status: 'not_configured', synced_at: null, tasks: [] }
export const initialSpotify: SpotifyNowPlaying = { status: 'not_configured', synced_at: null, track: null, artist: null, artwork_url: null, device_name: null, is_playing: false }
export const initialWeather: WeatherForecast = { status: 'not_configured', location: '', synced_at: null, today: null, tomorrow: null, days: [] }
export const initialWalkingPad: WalkingPadToday = {
  status: 'not_configured',
  synced_at: null,
  total_minutes: 0,
  total_distance_km: 0,
  total_steps: 0,
  total_calories: 0,
  goal_minutes: 120,
  goal_distance_km: 3,
  goal_steps: 10_000,
  session_count: 0,
  goal_met: false,
  active_session: null,
}
export const initialWalkReminder: WalkReminder = { active: false, message: '', dedupe_key: '' }
export const initialTraining: TrainingOverview = {
  generated_at: '', timezone: 'Asia/Tokyo', phase: 'build_october', today: null, tomorrow: null,
  week_start: '2026-09-07', week: [], upcoming: [], countdowns: [], compliance: {},
  week_quality: undefined, tomorrow_prescription: null, bjj_candidates: [],
  trends: { bike_decay: [], bjj_capacity: [], weight_7d_average: null }, readiness: null, day_flags: {},
}

const DASHBOARD_REFRESH_MS = 60_000
const DASHBOARD_FAST_REFRESH_MS = 2_000
const WALKINGPAD_REFRESH_MS = 30_000
const PLANNING_SAFETY_REFRESH_MS = 60_000
const WEATHER_REFRESH_MS = 30 * 60_000
const FRONTEND_VERSION_REFRESH_MS = 60_000

function bundlePathFromHtml(html: string) {
  const match = html.match(/<script[^>]+type=["']module["'][^>]+src=["']([^"']+)["']/i)
    ?? html.match(/<script[^>]+src=["']([^"']+)["'][^>]+type=["']module["']/i)
  if (!match?.[1]) return null
  return new URL(match[1], window.location.href).pathname
}

function activeBundlePath() {
  const source = document.querySelector<HTMLScriptElement>('script[type="module"][src]')?.src
  return source ? new URL(source, window.location.href).pathname : null
}

export type DashboardInitialData = {
  dashboard: Dashboard
  calendar: CalendarToday
  notion: NotionToday
  spotify: SpotifyNowPlaying
  weather: WeatherForecast
  walkingPad?: WalkingPadToday
  walkReminder?: WalkReminder
  selectedCalendarDate?: string | null
  training?: TrainingOverview
  plan?: DailyBriefing | null
}

export function useDashboardData(today: string, initialData?: DashboardInitialData) {
  const [calendarSelection, setCalendarSelection] = useState({ today, value: today })
  const selectedCalendarDate = calendarSelection.today === today ? calendarSelection.value : today
  const setSelectedCalendarDate = useCallback((next: SetStateAction<string>) => {
    setCalendarSelection((current) => {
      const currentValue = current.today === today ? current.value : today
      return {
        today,
        value: typeof next === 'function' ? next(currentValue) : next,
      }
    })
  }, [today])
  const [volumePending, setVolumePending] = useState(false)
  const queryClient = useQueryClient()
  const calendarStart = addDays(selectedCalendarDate, -CALENDAR_LOOKBACK_DAYS)

  const dashboardQuery = useQuery({
    queryKey: ['dashboard'],
    queryFn: ({ signal }) => fetchDashboard(signal),
    initialData: initialData?.dashboard,
    staleTime: 30_000,
    refetchInterval: (query) => query.state.data?.water_pump.state === 'running'
      ? DASHBOARD_FAST_REFRESH_MS
      : DASHBOARD_REFRESH_MS,
  })
  const spotifyQuery = useQuery({
    queryKey: ['spotify-now-playing'],
    queryFn: ({ signal }) => fetchSpotifyNowPlaying(signal),
    initialData: initialData?.spotify,
    staleTime: 30_000,
    refetchInterval: DASHBOARD_REFRESH_MS,
  })
  const weatherQuery = useQuery({
    queryKey: ['weather'],
    queryFn: ({ signal }) => fetchWeather(signal),
    initialData: initialData?.weather,
    staleTime: 20 * 60_000,
    refetchInterval: WEATHER_REFRESH_MS,
  })
  const walkingPadQuery = useQuery({
    queryKey: ['walking-pad-today', today],
    queryFn: ({ signal }) => fetchWalkingPadToday(signal),
    initialData: initialData?.walkingPad,
    staleTime: 15_000,
    refetchInterval: WALKINGPAD_REFRESH_MS,
  })
  const planQuery = useQuery({
    queryKey: ['daily-plan', today],
    queryFn: ({ signal }) => fetchDailyPlan(today, signal),
    initialData: initialData?.plan ?? undefined,
    staleTime: 30_000,
    refetchInterval: PLANNING_SAFETY_REFRESH_MS,
  })
  const trainingQuery = useQuery({
    queryKey: ['training-overview'],
    queryFn: ({ signal }) => fetchTrainingOverview(signal),
    initialData: initialData?.training,
    staleTime: 30_000,
    refetchInterval: PLANNING_SAFETY_REFRESH_MS,
  })
  const calendarQuery = useQuery({
    queryKey: ['calendar-events', calendarStart, CALENDAR_WINDOW_DAYS],
    queryFn: ({ signal }) => fetchCalendarEvents(calendarStart, CALENDAR_WINDOW_DAYS, signal),
    initialData: selectedCalendarDate === today ? initialData?.calendar : undefined,
    placeholderData: (previous) => previous,
    staleTime: 30_000,
    refetchInterval: PLANNING_SAFETY_REFRESH_MS,
  })

  const dashboardValue = dashboardQuery.data ?? initialDashboard
  const dashboard = {
    ...dashboardValue,
    wellbeing: dashboardValue.wellbeing ?? initialDashboard.wellbeing,
  }
  const calendar = calendarQuery.data ?? initialCalendar
  const spotify = spotifyQuery.data ?? initialSpotify
  const weather = weatherQuery.data ?? initialWeather
  const walkingPad = walkingPadQuery.data ?? initialWalkingPad
  const plan = planQuery.data ?? null
  const notion = plan ? notionFromPlan(plan, initialNotion) : (initialData?.notion ?? initialNotion)
  const walkReminder = plan ? walkReminderFromPlan(plan, initialWalkReminder) : (initialData?.walkReminder ?? initialWalkReminder)
  const training = trainingQuery.data
    ?? (plan ? trainingOverviewFromPlan(plan, initialTraining) : (initialData?.training ?? initialTraining))

  const refresh = useCallback(async () => {
    await Promise.all([dashboardQuery.refetch(), spotifyQuery.refetch()])
  }, [dashboardQuery, spotifyQuery])
  const refreshCalendar = useCallback(async () => {
    await calendarQuery.refetch({ cancelRefetch: true })
  }, [calendarQuery])
  const refreshPlanning = useCallback(async () => {
    await Promise.all([
      planQuery.refetch({ cancelRefetch: true }),
      trainingQuery.refetch({ cancelRefetch: true }),
      calendarQuery.refetch({ cancelRefetch: true }),
    ])
  }, [calendarQuery, planQuery, trainingQuery])

  const refreshFrontendVersion = useCallback(async () => {
    try {
      const response = await fetch('/index.html', {
        cache: 'no-store',
        headers: { 'Cache-Control': 'no-cache' },
      })
      if (!response.ok) return
      const availableBundle = bundlePathFromHtml(await response.text())
      const activeBundle = activeBundlePath()
      if (availableBundle && activeBundle && availableBundle !== activeBundle) {
        window.location.reload()
      }
    } catch {
      // Keep the current kiosk bundle running and retry after the next deploy check.
    }
  }, [])

  const setVolume = useCallback((volumePercent: number) => {
    setVolumePending(true)
    void setSystemVolume(volumePercent)
      .then((result) => {
        if (result.volume_percent === null) return
        queryClient.setQueryData<Dashboard>(['dashboard'], (current = initialDashboard) => ({
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
  }, [queryClient])

  usePolling(refreshFrontendVersion, FRONTEND_VERSION_REFRESH_MS, false)

  useEffect(() => subscribeToPlanningChanges(() => {
    void queryClient.invalidateQueries({ queryKey: ['daily-plan', today] })
    void queryClient.invalidateQueries({ queryKey: ['training-overview'] })
    void queryClient.invalidateQueries({ queryKey: ['calendar-events'] })
  }), [queryClient, today])

  return {
    dashboard,
    calendar,
    notion,
    spotify,
    weather,
    walkingPad,
    walkReminder,
    training,
    plan,
    selectedCalendarDate,
    volumePending,
    setDashboard: (next: Dashboard) => queryClient.setQueryData(['dashboard'], next),
    setSelectedCalendarDate,
    refresh,
    refreshCalendar,
    refreshPlanning,
    setVolume,
  }
}
