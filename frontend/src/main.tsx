import { useCallback, useMemo, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Header } from './components/Header'
import { RegionBlock } from './components/RegionBlock'
import { DeviceControls } from './components/DeviceControls'
import { VoicePipelinePanel } from './components/VoicePipelinePanel'
import { MediaRegion } from './components/MediaRegion'
import { MotionModeToggle } from './components/MotionModeToggle'
import { OpenClawChat } from './components/OpenClawChat'
import { addDays, dayKey, PlanningRegion } from './components/PlanningRegion'
import { StartupSplash } from './components/StartupSplash'
import { SystemHealthPanel } from './components/SystemHealthPanel'
import { useDashboardCommand } from './hooks/useDashboardCommand'
import { useDashboardData, type DashboardInitialData } from './hooks/useDashboardData'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { useSpotifyPlayback } from './hooks/useSpotifyPlayback'
import { useStartupBoot } from './hooks/useStartupBoot'
import { useVoiceMonitor } from './hooks/useVoiceMonitor'
import { getMotionMode } from './lib/motionMode'
import type { Light, WaterPump } from './types'
import './styles.css'

function isPresentationMode() {
  const params = new URLSearchParams(window.location.search)
  return params.get('mode') === 'kiosk'
    || params.get('fullscreen') === '1'
    || params.get('chromeless') === '1'
}

function AppShell() {
  const today = dayKey(new Date())
  const motionMode = useMemo(getMotionMode, [])
  const boot = useStartupBoot(today)

  if (!boot.isReady || !boot.data) {
    return (
      <StartupSplash
        checks={boot.checks}
        motionMode={motionMode}
        fading={boot.phase === 'fading'}
      />
    )
  }

  return <DashboardApp today={today} motionMode={motionMode} initialData={boot.data} />
}

function DashboardApp({
  today,
  motionMode,
  initialData,
}: {
  today: string
  motionMode: ReturnType<typeof getMotionMode>
  initialData: DashboardInitialData
}) {
  const [djPending, setDjPending] = useState(false)
  const { execute, pendingIntent } = useDashboardCommand()
  const { voiceStatus, activityEvents } = useVoiceMonitor()
  const chromeless = useMemo(isPresentationMode, [])
  const {
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
  } = useDashboardData(today, initialData)
  const spotifyPlayback = useSpotifyPlayback(spotify.status === 'ready')

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
  }, [dashboard.light, execute, setDashboard])

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
  }, [dashboard.water_pump.state, execute, setDashboard])

  const shortcuts = useMemo(() => ({
    l: toggleLight,
    r: () => {
      void refresh()
      void refreshCalendar()
    },
    s: () => void execute('display.hide'),
  }), [execute, refresh, refreshCalendar, toggleLight])
  useKeyboardShortcuts(shortcuts)

  return (
    <main className={`dashboard-shell${chromeless ? ' is-chromeless' : ''}${motionMode === 'lite' ? ' is-lite-motion' : ''}`}>
      <MotionModeToggle mode={motionMode} />
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
            onRefresh={() => void refreshOpenClaw()}
          />
        </aside>
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<AppShell />)
