import { useMemo } from 'react'
import { createRoot } from 'react-dom/client'
import { Header } from './components/Header'
import { MediaRegion } from './components/MediaRegion'
import { addDays, PlanningRegion, TaskRegion } from './components/PlanningRegion'
import { ChiliAdvice } from './components/TodayHero'
import { StartupSplash } from './components/StartupSplash'
import { useChiliNotifications } from './hooks/useChiliNotifications'
import { useDashboardData, type DashboardInitialData } from './hooks/useDashboardData'
import { useStartupBoot } from './hooks/useStartupBoot'
import { useToday } from './hooks/useClock'
import { getMotionMode } from './lib/motionMode'
import { EventsPanel, TrainingInsights } from './components/TrainingPlanner'
import { DailyBriefingPage } from './components/DailyBriefingPage'
import { WorkoutApp } from './pages/WorkoutApp'
import './styles.css'
import './workout.css'

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
  const chromeless = useMemo(isPresentationMode, [])
  const {
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
    setSelectedCalendarDate,
  } = useDashboardData(today, initialData)

  const { active: chiliNotification, exiting: chiliNotificationExiting } = useChiliNotifications({
    today,
    calendar,
    notion,
    spotify,
    openclaw: { status: 'not_configured', messages: [], message: null },
    voiceStatus: { state: 'offline', updated_at: null, transcript: null, message: null },
    spotifyIntentToken: 0,
    walkReminder,
    lastAdjustment: training.last_adjustment,
  })

  const screenHidden = dashboard.display.state === 'hidden'

  return (
    <main className={`dashboard-shell${chromeless ? ' is-chromeless' : ''}${motionMode === 'lite' ? ' is-lite-motion' : ''}${screenHidden ? ' is-display-hidden' : ''}`}>
      <button
        type="button"
        className="display-blanket"
        aria-label="Screen is off"
        tabIndex={-1}
      />
      {!chromeless && (
        <Header
          weather={weather}
          walkingPad={walkingPad}
          wellbeing={dashboard.wellbeing}
          training={training}
          notification={chiliNotification}
          notificationExiting={chiliNotificationExiting}
        />
      )}
      <div className="dashboard-workspace">
        <aside className="environment-region" aria-label="Chili's advice, events, and music">
          <ChiliAdvice plan={plan} />
          <EventsPanel training={training} />
          <MediaRegion spotify={spotify} />
        </aside>
        <PlanningRegion
          calendar={calendar}
          training={training}
          selectedDate={selectedCalendarDate ?? today}
          onPrevious={() => setSelectedCalendarDate((current) => addDays(current ?? today, -1))}
          onToday={() => setSelectedCalendarDate(today)}
          onNext={() => setSelectedCalendarDate((current) => addDays(current ?? today, 1))}
        />
        <aside className="daily-rail training-rail" aria-label="Training and tasks">
          <TrainingInsights training={training} />
          <TaskRegion notion={notion} />
        </aside>
      </div>
    </main>
  )
}

function isWorkoutPath() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  return path === '/workout' || path.startsWith('/workout/')
}

function isDailyPath() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  return path === '/daily' || path.startsWith('/daily/')
}

if (isWorkoutPath()) document.documentElement.classList.add('is-workout')

function PhoneApp() {
  if (isDailyPath()) {
    const match = window.location.pathname.match(/^\/daily\/(\d{4}-\d{2}-\d{2})/)
    const day = match?.[1] ?? new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
    return <DailyBriefingPage day={day} />
  }
  return <WorkoutApp />
}

createRoot(document.getElementById('root')!).render(
  isWorkoutPath() || isDailyPath() ? <PhoneApp /> : <AppShell />,
)
