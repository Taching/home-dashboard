import { useCallback, useEffect, useState } from 'react'
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
import { useDashboardData } from './hooks/useDashboardData'
import { useSpotifyPlayback } from './hooks/useSpotifyPlayback'
import { sendOpenClawMessage } from './lib/api'
import type { Light } from './types'
import './styles.css'

function isStale(updatedAt: string | null, staleAfterSeconds: number) {
  return updatedAt !== null && Date.now() - new Date(updatedAt).getTime() > staleAfterSeconds * 1000
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
  const { dashboard, readings, calendar, notion, spotify, openclaw, refresh, refreshOpenClaw, updateDashboard } = useDashboardData()
  const [openclawPending, setOpenClawPending] = useState(false)
  const [openclawFeedback, setOpenClawFeedback] = useState<string | null>(null)
  const [selectedCalendarDate, setSelectedCalendarDate] = useState<string | null>(null)
  const { execute, feedback, pendingIntent } = useDashboardCommand()
  const spotifyPlayback = useSpotifyPlayback(spotify.status === 'ready')
  const stale = isStale(dashboard.last_updated_at, dashboard.ui.sensor_stale_after_seconds)
  const today = dayKey(new Date())
  const initialCalendarDate = calendar.status === 'ready'
    ? calendar.events.map((event) => dayKey(event.start_at)).find((eventDate) => eventDate >= today) ?? today
    : today
  const activeCalendarDate = selectedCalendarDate ?? initialCalendarDate

  const toggleLight = useCallback(() => {
    const previousLight = dashboard.light
    const target = previousLight.last_command_state === 'on' ? 'off' : 'on'
    const intent = target === 'on' ? 'light.turn_on' : 'light.turn_off'

    void execute(intent, {
      optimistic: () => updateDashboard((current) => ({
        ...current,
        light: { ...current.light, last_command_state: target, last_command_at: new Date().toISOString() },
      })),
      onSuccess: (result) => {
        if (result.light) updateDashboard((current) => ({ ...current, light: result.light as Light }))
      },
      onFailure: () => updateDashboard((current) => ({ ...current, light: previousLight })),
    })
  }, [dashboard.light, execute, updateDashboard])

  const sendToOpenClaw = useCallback(async (message: string) => {
    setOpenClawPending(true)
    setOpenClawFeedback(null)
    try {
      const result = await sendOpenClawMessage(message)
      if (result.status !== 'success') throw new Error(result.message ?? 'Telegram delivery failed.')
      setOpenClawFeedback(null)
      await refreshOpenClaw()
    } catch (error) {
      setOpenClawFeedback(error instanceof Error ? error.message : 'Telegram delivery failed.')
    } finally {
      setOpenClawPending(false)
    }
  }, [refreshOpenClaw])

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

  const sensorStatus = statusLabel(dashboard.integrations.sensor, stale)
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
          selectedDate={activeCalendarDate}
          onPrevious={() => setSelectedCalendarDate((current) => addDays(current ?? activeCalendarDate, -1))}
          onToday={() => setSelectedCalendarDate(today)}
          onNext={() => setSelectedCalendarDate((current) => addDays(current ?? activeCalendarDate, 1))}
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
