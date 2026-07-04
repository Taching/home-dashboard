import { useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Header } from './components/Header'
import { RegionBlock } from './components/RegionBlock'
import { DeviceControls } from './components/DeviceControls'
import { VoicePipelinePanel } from './components/VoicePipelinePanel'
import { MediaRegion } from './components/MediaRegion'
import { OpenClawChat } from './components/OpenClawChat'
import { addDays, dayKey, PlanningRegion } from './components/PlanningRegion'
import { SystemHealthPanel } from './components/SystemHealthPanel'
import { useDashboardCommand } from './hooks/useDashboardCommand'
import { useSpotifyPlayback } from './hooks/useSpotifyPlayback'
import { useVoiceMonitor } from './hooks/useVoiceMonitor'
import {
  fetchCalendarEvents,
  fetchDashboard,
  fetchNotionToday,
  fetchOpenClawMessages,
  openOpenClawMessageStream,
  sendOpenClawMessage,
  fetchSpotifyNowPlaying,
  fetchWeather,
  setSystemVolume,
} from './lib/api'
import type { CalendarToday, Dashboard, Light, NotionToday, OpenClawConversation, SpotifyNowPlaying, WaterPump, WeatherForecast } from './types'
import './styles.css'

const initialState: Dashboard = {
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

function isTypingTarget(target: EventTarget | null) {
  return target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || target instanceof HTMLSelectElement
    || (target instanceof HTMLElement && target.isContentEditable)
}

function isPresentationMode() {
  const params = new URLSearchParams(window.location.search)
  return params.get('mode') === 'kiosk'
    || params.get('fullscreen') === '1'
    || params.get('chromeless') === '1'
}

function App() {
  const [dashboard, setDashboard] = useState<Dashboard>(initialState)
  const [calendar, setCalendar] = useState<CalendarToday>(initialCalendar)
  const [notion, setNotion] = useState<NotionToday>(initialNotion)
  const [spotify, setSpotify] = useState<SpotifyNowPlaying>(initialSpotify)
  const [openclaw, setOpenClaw] = useState<OpenClawConversation>(initialOpenClaw)
  const [weather, setWeather] = useState<WeatherForecast>(initialWeather)
  const [openclawPending, setOpenClawPending] = useState(false)
  const [openclawFeedback, setOpenClawFeedback] = useState<string | null>(null)
  const [selectedCalendarDate, setSelectedCalendarDate] = useState<string | null>(null)
  const [djPending, setDjPending] = useState(false)
  const [volumePending, setVolumePending] = useState(false)
  const { execute, pendingIntent } = useDashboardCommand()
  const { voiceStatus, activityEvents } = useVoiceMonitor()
  const spotifyPlayback = useSpotifyPlayback(spotify.status === 'ready')
  const today = dayKey(new Date())
  const chromeless = useMemo(isPresentationMode, [])

  const refresh = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        fetchDashboard(), fetchCalendarEvents(today), fetchNotionToday(), fetchSpotifyNowPlaying(), fetchOpenClawMessages(),
      ])
      if (results[0].status === 'fulfilled') setDashboard(results[0].value)
      if (results[1].status === 'fulfilled') {
        const nextCalendar = results[1].value
        setCalendar(nextCalendar)
        setSelectedCalendarDate((current) => {
          if (current || nextCalendar.status !== 'ready') return current
          const nextScheduled = nextCalendar.events
            .map((event) => dayKey(event.start_at))
            .find((eventDate) => eventDate >= today)
          return nextScheduled ?? today
        })
      }
      if (results[2].status === 'fulfilled') setNotion(results[2].value)
      if (results[3].status === 'fulfilled') setSpotify(results[3].value)
      if (results[4].status === 'fulfilled') setOpenClaw(results[4].value)
    } catch {
      // Existing state remains visible while the next scheduled refresh retries.
    }
  }, [today])

  const toggleLight = useCallback(() => {
    const previousLight = dashboard.light
    const target = previousLight.last_command_state === 'on' ? 'off' : 'on'
    const intent = target === 'on' ? 'light.turn_on' : 'light.turn_off'

    void execute(intent, {
      optimistic: () => setDashboard((current) => ({
        ...current,
        light: { ...current.light, last_command_state: target, last_command_at: new Date().toISOString() },
      })),
      onSuccess: (result) => {
        if (result.light) setDashboard((current) => ({ ...current, light: result.light as Light }))
      },
      onFailure: () => setDashboard((current) => ({ ...current, light: previousLight })),
    })
  }, [dashboard.light, execute])

  const togglePlantPump = useCallback(() => {
    const intent = dashboard.water_pump.state === 'running' ? 'water.stop' : 'water.run'
    if (intent === 'water.run') {
      void execute('water.run', {
        optimistic: () => setDashboard((current) => ({
          ...current,
          water_pump: { ...current.water_pump, state: 'running' },
        })),
        onSuccess: (result) => {
          if (result.water_pump) {
            setDashboard((current) => ({ ...current, water_pump: result.water_pump as WaterPump }))
          }
        },
        onFailure: () => setDashboard((current) => ({
          ...current,
          water_pump: { ...current.water_pump, state: 'idle' },
        })),
      })
      return
    }

    void execute('water.stop', {
      onSuccess: (result) => {
        if (result.water_pump) {
          setDashboard((current) => ({ ...current, water_pump: result.water_pump as WaterPump }))
        }
      },
    })
  }, [dashboard.water_pump.state, execute])

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

  useEffect(() => {
    void refresh()
    const intervalMs = dashboard.water_pump.state === 'running' ? 2_000 : 60_000
    const interval = window.setInterval(() => void refresh(), intervalMs)
    return () => window.clearInterval(interval)
  }, [refresh, dashboard.water_pump.state])

  useEffect(() => {
    void fetchWeather().then(setWeather).catch(() => undefined)
    const interval = window.setInterval(() => {
      void fetchWeather().then(setWeather).catch(() => undefined)
    }, 30 * 60_000)
    return () => window.clearInterval(interval)
  }, [])

  useEffect(() => {
    if (typeof EventSource === 'undefined') {
      const interval = window.setInterval(async () => {
        try { setOpenClaw(await fetchOpenClawMessages()) } catch { /* retry on next interval */ }
      }, 5_000)
      return () => window.clearInterval(interval)
    }

    const stream = openOpenClawMessageStream(setOpenClaw)
    return () => stream.close()
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

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (isTypingTarget(event.target)) return
      if (event.key.toLowerCase() === 'l') toggleLight()
      if (event.key.toLowerCase() === 'r') void refresh()
      if (event.key.toLowerCase() === 's') void execute('display.hide')
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [execute, refresh, toggleLight])

  return (
    <main className={`dashboard-shell${chromeless ? ' is-chromeless' : ''}`}>
      {!chromeless && (
        <Header
          voiceStatus={voiceStatus}
          temperature={dashboard.temperature_c}
          humidity={dashboard.humidity_percent}
          weather={weather}
        />
      )}
      <div className="dashboard-workspace">
        <aside className="environment-region" aria-label="Environment and light">
          <RegionBlock label="Log" className="region-block-log">
            <VoicePipelinePanel status={voiceStatus} events={activityEvents} />
          </RegionBlock>
          <RegionBlock label="Controls">
            <DeviceControls
              light={dashboard.light}
              pump={dashboard.water_pump}
              lightPending={pendingIntent === 'light.turn_on' || pendingIntent === 'light.turn_off'}
              pumpPending={pendingIntent === 'water.run' || pendingIntent === 'water.stop'}
              onToggleLight={toggleLight}
              onTogglePump={togglePlantPump}
            />
          </RegionBlock>
          <RegionBlock label="System">
            <SystemHealthPanel
              system={dashboard.system}
              volumePending={volumePending}
              onSetVolume={setVolume}
            />
          </RegionBlock>
          <MediaRegion
            spotify={spotify}
            playerReady={spotifyPlayback.ready}
            playerActive={spotifyPlayback.active}
            playerPaused={spotifyPlayback.paused}
            playerTrack={spotifyPlayback.track}
            playerError={spotifyPlayback.error}
            onPlayHere={() => void spotifyPlayback.playHere()}
            onTogglePlayback={() => void spotifyPlayback.togglePlayback()}
            onPrevious={() => void spotifyPlayback.previousTrack()}
            onNext={() => void spotifyPlayback.nextTrack()}
            djPending={djPending}
            onStartDj={() => {
              setDjPending(true)
              void spotifyPlayback.startDj().finally(() => setDjPending(false))
            }}
          />
        </aside>
        <PlanningRegion
          calendar={calendar}
          notion={notion}
          selectedDate={selectedCalendarDate ?? today}
          onPrevious={() => setSelectedCalendarDate((current) => addDays(current ?? today, -1))}
          onToday={() => setSelectedCalendarDate(today)}
          onNext={() => setSelectedCalendarDate((current) => addDays(current ?? today, 1))}
        />
        <aside className="assistant-region" aria-label="Assistant">
          <OpenClawChat
            conversation={openclaw}
            pending={openclawPending}
            feedback={openclawFeedback}
            onSend={(message) => void sendToOpenClaw(message)}
            onRefresh={() => void fetchOpenClawMessages().then(setOpenClaw).catch(() => setOpenClaw({ status: 'unavailable', messages: [], message: 'OpenClaw is unavailable.' }))}
          />
        </aside>
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
