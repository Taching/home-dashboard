import { useCallback, useEffect, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { EnvironmentalReadings } from './components/EnvironmentalReadings'
import { Header } from './components/Header'
import { LightControl } from './components/LightControl'
import { MediaRegion } from './components/MediaRegion'
import { OpenClawChat } from './components/OpenClawChat'
import { addDays, dayKey, PlanningRegion } from './components/PlanningRegion'
import { SystemStrip } from './components/SystemStrip'
import { TemperatureTrend } from './components/TemperatureTrend'
import { useDashboardCommand } from './hooks/useDashboardCommand'
import { useSpotifyPlayback } from './hooks/useSpotifyPlayback'
import {
  fetchCalendarEvents,
  fetchDashboard,
  fetchNotionToday,
  fetchOpenClawMessages,
  fetchReadings,
  sendOpenClawMessage,
  fetchSpotifyNowPlaying,
} from './lib/api'
import type { CalendarToday, Dashboard, Light, NotionToday, OpenClawConversation, Reading, SpotifyNowPlaying } from './types'
import './styles.css'

const initialState: Dashboard = {
  temperature_c: null,
  humidity_percent: null,
  last_updated_at: null,
  light: { last_command_state: 'unknown', last_command_at: null, available: false },
  display: { state: 'visible' },
  integrations: { sensor: 'pending', broadlink: 'pending', calendar: 'not_configured', notion: 'not_configured', spotify: 'not_configured', openclaw: 'not_configured' },
}

const initialCalendar: CalendarToday = { status: 'not_configured', synced_at: null, events: [] }
const initialNotion: NotionToday = { status: 'not_configured', synced_at: null, tasks: [] }
const initialSpotify: SpotifyNowPlaying = { status: 'not_configured', synced_at: null, track: null, artist: null, artwork_url: null, device_name: null, is_playing: false }
const initialOpenClaw: OpenClawConversation = { status: 'not_configured', messages: [], message: null }

function isStale(updatedAt: string | null) {
  return updatedAt !== null && Date.now() - new Date(updatedAt).getTime() > 15 * 60_000
}

function statusLabel(status: string, stale = false) {
  if (stale) return 'Stale'
  if (status === 'ready') return 'Live'
  if (status === 'unavailable') return 'Unavailable'
  return 'Pending'
}

function isTypingTarget(target: EventTarget | null) {
  return target instanceof HTMLInputElement
    || target instanceof HTMLTextAreaElement
    || target instanceof HTMLSelectElement
    || (target instanceof HTMLElement && target.isContentEditable)
}

function App() {
  const [dashboard, setDashboard] = useState<Dashboard>(initialState)
  const [readings, setReadings] = useState<Reading[]>([])
  const [calendar, setCalendar] = useState<CalendarToday>(initialCalendar)
  const [notion, setNotion] = useState<NotionToday>(initialNotion)
  const [spotify, setSpotify] = useState<SpotifyNowPlaying>(initialSpotify)
  const [openclaw, setOpenClaw] = useState<OpenClawConversation>(initialOpenClaw)
  const [openclawPending, setOpenClawPending] = useState(false)
  const [openclawFeedback, setOpenClawFeedback] = useState<string | null>(null)
  const [selectedCalendarDate, setSelectedCalendarDate] = useState<string | null>(null)
  const { execute, feedback, pendingIntent } = useDashboardCommand()
  const spotifyPlayback = useSpotifyPlayback(spotify.status === 'ready')
  const stale = isStale(dashboard.last_updated_at)
  const today = dayKey(new Date())

  const refresh = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        fetchDashboard(), fetchReadings(), fetchCalendarEvents(today), fetchNotionToday(), fetchSpotifyNowPlaying(), fetchOpenClawMessages(),
      ])
      if (results[0].status === 'fulfilled') setDashboard(results[0].value)
      if (results[1].status === 'fulfilled') setReadings(results[1].value)
      if (results[2].status === 'fulfilled') {
        const nextCalendar = results[2].value
        setCalendar(nextCalendar)
        setSelectedCalendarDate((current) => {
          if (current || nextCalendar.status !== 'ready') return current
          const nextScheduled = nextCalendar.events
            .map((event) => dayKey(event.start_at))
            .find((eventDate) => eventDate >= today)
          return nextScheduled ?? today
        })
      }
      if (results[3].status === 'fulfilled') setNotion(results[3].value)
      if (results[4].status === 'fulfilled') setSpotify(results[4].value)
      if (results[5].status === 'fulfilled') setOpenClaw(results[5].value)
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

  useEffect(() => {
    void refresh()
    const interval = window.setInterval(() => void refresh(), 60_000)
    return () => window.clearInterval(interval)
  }, [refresh])

  useEffect(() => {
    const interval = window.setInterval(async () => {
      try { setOpenClaw(await fetchOpenClawMessages()) } catch { /* retry on next interval */ }
    }, 10_000)
    return () => window.clearInterval(interval)
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

  const sensorStatus = useMemo(
    () => statusLabel(dashboard.integrations.sensor, stale),
    [dashboard.integrations.sensor, stale],
  )
  const broadLinkStatus = statusLabel(dashboard.integrations.broadlink)

  return (
    <main className="dashboard-shell">
      <Header />
      <div className="dashboard-workspace">
        <aside className="environment-region" aria-label="Environment and light">
          <EnvironmentalReadings
            temperature={dashboard.temperature_c}
            humidity={dashboard.humidity_percent}
            updatedAt={dashboard.last_updated_at}
            stale={stale}
          />
          <LightControl
            light={dashboard.light}
            pending={pendingIntent === 'light.turn_on' || pendingIntent === 'light.turn_off'}
            onToggle={toggleLight}
          />
          <section className="history" aria-labelledby="history-title">
            <div className="history-heading">
              <div>
                <p className="eyebrow">TEMPERATURE</p>
                <h2 id="history-title">Last 24 hours</h2>
              </div>
              <p>{readings.length} readings</p>
            </div>
            <TemperatureTrend readings={readings} />
          </section>
        </aside>
        <PlanningRegion
          calendar={calendar}
          notion={notion}
          selectedDate={selectedCalendarDate ?? today}
          onPrevious={() => setSelectedCalendarDate((current) => addDays(current ?? today, -1))}
          onToday={() => setSelectedCalendarDate(today)}
          onNext={() => setSelectedCalendarDate((current) => addDays(current ?? today, 1))}
        />
        <aside className="assistant-region" aria-label="Assistant and media">
          <OpenClawChat conversation={openclaw} pending={openclawPending} feedback={openclawFeedback} onSend={(message) => void sendToOpenClaw(message)} />
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
          />
        </aside>
      </div>
      <SystemStrip sensorStatus={sensorStatus} broadLinkStatus={broadLinkStatus} feedback={feedback} />
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<App />)
