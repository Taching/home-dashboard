import { useEffect, useState } from 'react'
import { dayKey } from '../components/PlanningRegion'
import {
  fetchCalendarEvents,
  fetchDashboard,
  fetchNotionToday,
  fetchOpenClawMessages,
  fetchSpotifyNowPlaying,
  fetchWeather,
} from '../lib/api'
import type { IntegrationStatus } from '../types'
import type { DashboardInitialData } from './useDashboardData'
import {
  initialCalendar,
  initialDashboard,
  initialNotion,
  initialOpenClaw,
  initialSpotify,
  initialWeather,
} from './useDashboardData'

export type StartupCheckState = 'pending' | 'checking' | 'ok' | 'optional' | 'failed'

export type StartupCheck = {
  id: string
  label: string
  state: StartupCheckState
  detail?: string
}

type BootPhase = 'checking' | 'fading' | 'done'

const MIN_SPLASH_MS = 1_200
const MAX_WAIT_MS = 8_000
const RETRY_DELAY_MS = 800
const MAX_RETRIES = 2
const FADE_MS = 400

const CHECK_DEFS = [
  { id: 'backend', label: 'Backend' },
  { id: 'calendar', label: 'Calendar bridge' },
  { id: 'notion', label: 'Notion' },
  { id: 'spotify', label: 'Spotify' },
  { id: 'openclaw', label: 'OpenClaw' },
  { id: 'weather', label: 'Weather' },
] as const

function initialChecks(): StartupCheck[] {
  return CHECK_DEFS.map((check) => ({ ...check, state: 'pending' as const }))
}

function integrationState(status: IntegrationStatus): StartupCheckState {
  if (status === 'ready') return 'ok'
  if (status === 'not_configured') return 'optional'
  return 'failed'
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => window.setTimeout(resolve, ms))
}

type CheckResult = {
  state: StartupCheckState
  detail?: string
}

type ServiceCheckResult = {
  check: CheckResult
  dashboard?: typeof initialDashboard
  calendar?: typeof initialCalendar
  notion?: typeof initialNotion
  spotify?: typeof initialSpotify
  openclaw?: typeof initialOpenClaw
  weather?: typeof initialWeather
}

async function runBackendCheck(): Promise<{ check: CheckResult, dashboard: typeof initialDashboard }> {
  try {
    const dashboard = await fetchDashboard()
    return { check: { state: 'ok' }, dashboard }
  } catch {
    return { check: { state: 'failed', detail: 'Unreachable' }, dashboard: initialDashboard }
  }
}

async function runCalendarCheck(today: string): Promise<{ check: CheckResult, calendar: typeof initialCalendar }> {
  try {
    const calendar = await fetchCalendarEvents(today)
    return {
      check: {
        state: calendar.status === 'unavailable' ? 'failed' : integrationState(calendar.status),
        detail: calendar.status === 'not_configured' ? 'Optional' : undefined,
      },
      calendar,
    }
  } catch {
    return { check: { state: 'failed', detail: 'Unreachable' }, calendar: initialCalendar }
  }
}

async function runNotionCheck(): Promise<{ check: CheckResult, notion: typeof initialNotion }> {
  try {
    const notion = await fetchNotionToday()
    return {
      check: {
        state: integrationState(notion.status),
        detail: notion.status === 'not_configured' ? 'Optional' : undefined,
      },
      notion,
    }
  } catch {
    return { check: { state: 'failed', detail: 'Unreachable' }, notion: initialNotion }
  }
}

async function runSpotifyCheck(): Promise<{ check: CheckResult, spotify: typeof initialSpotify }> {
  try {
    const spotify = await fetchSpotifyNowPlaying()
    return {
      check: {
        state: integrationState(spotify.status),
        detail: spotify.status === 'not_configured' ? 'Optional' : undefined,
      },
      spotify,
    }
  } catch {
    return { check: { state: 'failed', detail: 'Unreachable' }, spotify: initialSpotify }
  }
}

async function runOpenClawCheck(): Promise<{ check: CheckResult, openclaw: typeof initialOpenClaw }> {
  try {
    const openclaw = await fetchOpenClawMessages()
    return {
      check: {
        state: integrationState(openclaw.status),
        detail: openclaw.status === 'not_configured' ? 'Optional' : undefined,
      },
      openclaw,
    }
  } catch {
    return {
      check: { state: 'failed', detail: 'Unreachable' },
      openclaw: { status: 'unavailable', messages: [], message: 'OpenClaw is unavailable.' },
    }
  }
}

async function runWeatherCheck(): Promise<{ check: CheckResult, weather: typeof initialWeather }> {
  try {
    const weather = await fetchWeather()
    return {
      check: {
        state: integrationState(weather.status),
        detail: weather.status === 'not_configured' ? 'Optional' : undefined,
      },
      weather,
    }
  } catch {
    return { check: { state: 'failed', detail: 'Unreachable' }, weather: initialWeather }
  }
}

function resolveSelectedCalendarDate(calendar: typeof initialCalendar, today: string) {
  if (calendar.status !== 'ready') return null
  const nextScheduled = calendar.events
    .map((event) => dayKey(event.start_at))
    .find((eventDate) => eventDate >= today)
  return nextScheduled ?? today
}

export function useStartupBoot(today: string) {
  const [phase, setPhase] = useState<BootPhase>('checking')
  const [checks, setChecks] = useState<StartupCheck[]>(initialChecks)
  const [data, setData] = useState<DashboardInitialData | null>(null)

  useEffect(() => {
    let cancelled = false

    const updateCheck = (id: string, patch: Partial<StartupCheck>) => {
      setChecks((current) => current.map((check) => (
        check.id === id ? { ...check, ...patch } : check
      )))
    }

    const runCheck = async (id: string) => {
      updateCheck(id, { state: 'checking' })
      switch (id) {
        case 'backend': return runBackendCheck()
        case 'calendar': return runCalendarCheck(today)
        case 'notion': return runNotionCheck()
        case 'spotify': return runSpotifyCheck()
        case 'openclaw': return runOpenClawCheck()
        case 'weather': return runWeatherCheck()
        default: return null
      }
    }

    void (async () => {
      const started = Date.now()
      setChecks(initialChecks().map((check) => ({ ...check, state: 'checking' })))

      let dashboard = initialDashboard
      let calendar = initialCalendar
      let notion = initialNotion
      let spotify = initialSpotify
      let openclaw = initialOpenClaw
      let weather = initialWeather
      const results = new Map<string, CheckResult>()

      const applyResult = (id: string, result: ServiceCheckResult | null) => {
        if (!result) {
          const check: CheckResult = { state: 'failed', detail: 'Unreachable' }
          results.set(id, check)
          updateCheck(id, check)
          return
        }
        if (result.dashboard) dashboard = result.dashboard
        if (result.calendar) calendar = result.calendar
        if (result.notion) notion = result.notion
        if (result.spotify) spotify = result.spotify
        if (result.openclaw) openclaw = result.openclaw
        if (result.weather) weather = result.weather
        results.set(id, result.check)
        updateCheck(id, result.check)
      }

      const runAll = async () => {
        await Promise.all(CHECK_DEFS.map(async (def) => {
          applyResult(def.id, await runCheck(def.id))
        }))
      }

      await runAll()

      for (let attempt = 0; attempt < MAX_RETRIES; attempt += 1) {
        const failed = CHECK_DEFS.filter((def) => results.get(def.id)?.state === 'failed')
        if (failed.length === 0) break
        if (Date.now() - started >= MAX_WAIT_MS) break
        await sleep(RETRY_DELAY_MS)
        if (cancelled) return

        await Promise.all(failed.map(async (def) => {
          applyResult(def.id, await runCheck(def.id))
        }))
      }

      while (Date.now() - started < MIN_SPLASH_MS) {
        await sleep(Math.min(100, MIN_SPLASH_MS - (Date.now() - started)))
        if (cancelled) return
      }

      while (Date.now() - started < MAX_WAIT_MS) {
        const pending = [...results.values()].some((result) => result.state === 'checking')
        if (!pending) break
        await sleep(100)
        if (cancelled) return
      }

      if (cancelled) return

      setData({
        dashboard,
        calendar,
        notion,
        spotify,
        openclaw,
        weather,
        selectedCalendarDate: resolveSelectedCalendarDate(calendar, today),
      })
      setPhase('fading')
      await sleep(FADE_MS)
      if (cancelled) return
      setPhase('done')
    })()

    return () => {
      cancelled = true
    }
  }, [today])

  return {
    phase,
    checks,
    data,
    isReady: phase === 'done',
  }
}
