import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { Header } from './components/Header'
import { RegionBlock } from './components/RegionBlock'
import { DeviceControls } from './components/DeviceControls'
import { VoicePipelinePanel } from './components/VoicePipelinePanel'
import { MediaRegion } from './components/MediaRegion'
import { MotionModeToggle } from './components/MotionModeToggle'
import { OpenClawChat } from './components/OpenClawChat'
import { addDays, PlanningRegion } from './components/PlanningRegion'
import { StartupSplash } from './components/StartupSplash'
import { SystemHealthPanel } from './components/SystemHealthPanel'
import { useChiliNotifications } from './hooks/useChiliNotifications'
import { useDashboardCommand } from './hooks/useDashboardCommand'
import { useDashboardData, type DashboardInitialData } from './hooks/useDashboardData'
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts'
import { useSpotifyPlayback } from './hooks/useSpotifyPlayback'
import { useStartupBoot } from './hooks/useStartupBoot'
import { useToday } from './hooks/useClock'
import { useVoiceMonitor } from './hooks/useVoiceMonitor'
import { getMotionMode } from './lib/motionMode'
import { setDisplaySchedule, fetchDashboard } from './lib/api'
import type { Light, WaterPump, Display } from './types'
import './styles.css'

function isPresentationMode() {
  const params = new URLSearchParams(window.location.search)
  return params.get('mode') === 'kiosk'
    || params.get('fullscreen') === '1'
    || params.get('chromeless') === '1'
}

function AppShell() {
  const motionMode = useMemo(getMotionMode, [])
  const boot = useStartupBoot()

  if (!boot.isReady || !boot.data) {
    return (
      <StartupSplash
        checks={boot.checks}
        motionMode={motionMode}
        fading={boot.phase === 'fading'}
      />
    )
  }

  return <DashboardApp motionMode={motionMode} initialData={boot.data} />
}

function DashboardApp({
  motionMode,
  initialData,
}: {
  motionMode: ReturnType<typeof getMotionMode>
  initialData: DashboardInitialData
}) {
  const today = useToday()
  const [djPending, setDjPending] = useState(false)
  const [schedulePending, setSchedulePending] = useState(false)
  const [spotifyIntentToken, setSpotifyIntentToken] = useState(0)
  const processedActivityCountRef = useRef(0)
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
  } = useDashboardData(today, initialData)
  const spotifyPlayback = useSpotifyPlayback(spotify.status === 'ready')

  const markSpotifyIntent = useCallback(() => {
    setSpotifyIntentToken((token) => token + 1)
  }, [])

  useEffect(() => {
    if (activityEvents.length <= processedActivityCountRef.current) return
    const fresh = activityEvents.slice(processedActivityCountRef.current)
    processedActivityCountRef.current = activityEvents.length
    const wantsSpotifyIntent = fresh.some((event) => {
      if (event.service !== 'spotify') return false
      const detail = event.detail.toLowerCase()
      return detail.includes('start dj') || detail.includes('transfer playback')
    })
    if (wantsSpotifyIntent) setSpotifyIntentToken((token) => token + 1)
  }, [activityEvents])

  const { active: chiliNotification, exiting: chiliNotificationExiting } = useChiliNotifications({
    today,
    calendar,
    notion,
    spotify,
    openclaw,
    voiceStatus,
    spotifyIntentToken,
    walkReminder,
  })

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

  const applyDisplay = useCallback((display: Display) => {
    setDashboard((current) => ({ ...current, display }))
  }, [setDashboard])

  const toggleDisplay = useCallback(() => {
    const intent = dashboard.display.state === 'visible' ? 'display.hide' : 'display.show'
    void execute(intent, {
      onSuccess: (result) => {
        if (result.display) applyDisplay(result.display)
      },
    })
  }, [applyDisplay, dashboard.display.state, execute])

  const toggleDisplaySchedule = useCallback(() => {
    const target = !dashboard.display.schedule_enabled
    setSchedulePending(true)
    void setDisplaySchedule(target)
      .then(applyDisplay)
      .finally(() => setSchedulePending(false))
  }, [applyDisplay, dashboard.display.schedule_enabled])

  const screenHidden = dashboard.display.state === 'hidden'

  useEffect(() => {
    if (!dashboard.display.schedule_enabled) return
    const interval = window.setInterval(() => {
      void fetchDashboard().then((data) => {
        setDashboard((current) => ({ ...current, display: data.display }))
      })
    }, 30_000)
    return () => window.clearInterval(interval)
  }, [dashboard.display.schedule_enabled, setDashboard])

  const shortcuts = useMemo(() => ({
    l: toggleLight,
    r: () => {
      void refresh()
      void refreshCalendar()
    },
    s: toggleDisplay,
  }), [refresh, refreshCalendar, toggleDisplay, toggleLight])
  useKeyboardShortcuts(shortcuts)

  return (
    <main className={`dashboard-shell${chromeless ? ' is-chromeless' : ''}${motionMode === 'lite' ? ' is-lite-motion' : ''}${screenHidden ? ' is-display-hidden' : ''}`}>
      <button
        type="button"
        className="display-blanket"
        aria-label="Screen is off. Press S or tap to turn on."
        onClick={toggleDisplay}
        tabIndex={screenHidden ? 0 : -1}
      />
      <MotionModeToggle mode={motionMode} />
      {!chromeless && (
        <Header
          voiceStatus={voiceStatus}
          temperature={dashboard.temperature_c}
          humidity={dashboard.humidity_percent}
          weather={weather}
          walkingPad={walkingPad}
          notification={chiliNotification}
          notificationExiting={chiliNotificationExiting}
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
              display={dashboard.display}
              lightPending={pendingIntent === 'light.turn_on' || pendingIntent === 'light.turn_off'}
              pumpPending={pendingIntent === 'water.run' || pendingIntent === 'water.stop'}
              displayPending={pendingIntent === 'display.show' || pendingIntent === 'display.hide'}
              schedulePending={schedulePending}
              onToggleLight={toggleLight}
              onTogglePump={togglePlantPump}
              onToggleDisplay={toggleDisplay}
              onToggleSchedule={toggleDisplaySchedule}
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
            onPlayHere={() => {
              markSpotifyIntent()
              void spotifyPlayback.playHere()
            }}
            onTogglePlayback={() => void spotifyPlayback.togglePlayback()}
            onPrevious={() => void spotifyPlayback.previousTrack()}
            onNext={() => void spotifyPlayback.nextTrack()}
            djPending={djPending}
            onStartDj={() => {
              markSpotifyIntent()
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
            onSend={(message) => sendToOpenClaw(message)}
            onRefresh={() => void refreshOpenClaw()}
          />
        </aside>
      </div>
    </main>
  )
}

createRoot(document.getElementById('root')!).render(<AppShell />)
