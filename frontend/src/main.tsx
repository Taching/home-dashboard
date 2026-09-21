import { lazy, Suspense, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { QueryClientProvider } from '@tanstack/react-query'
import { AppErrorBoundary } from './components/AppErrorBoundary'
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
import { PageSkeleton } from './components/PageSkeleton'
import { queryClient } from './lib/queryClient'
import './styles.css'
import './workout.css'

const DailyBriefingPage = lazy(() => import('./components/DailyBriefingPage').then((module) => ({ default: module.DailyBriefingPage })))
const WorkoutApp = lazy(() => import('./pages/WorkoutApp').then((module) => ({ default: module.WorkoutApp })))
const WeeklyReviewPage = lazy(() => import('./pages/WeeklyReviewPage').then((module) => ({ default: module.WeeklyReviewPage })))
const ScheduleChangePage = lazy(() => import('./pages/ScheduleChangePage').then((module) => ({ default: module.ScheduleChangePage })))
const TrainingPreferencesPage = lazy(() => import('./pages/TrainingPreferencesPage').then((module) => ({ default: module.TrainingPreferencesPage })))

function isPresentationMode() {
  const params = new URLSearchParams(window.location.search)
  return params.get('mode') === 'kiosk'
    || params.get('fullscreen') === '1'
    || params.get('chromeless') === '1'
}

function AppShell() {
  const [motionMode] = useState(getMotionMode)
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
  const [chromeless] = useState(isPresentationMode)
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
          weather={weather}
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

function isWeeklyPath() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  return path === '/weekly' || path.startsWith('/weekly/')
}

function isScheduleChangePath() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  return path === '/schedule-change'
}

function isTrainingPreferencesPath() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  return path === '/training/preferences'
}

if (isWorkoutPath() || isWeeklyPath() || isScheduleChangePath() || isTrainingPreferencesPath()) {
  document.documentElement.classList.add('is-workout')
}
if (isDailyPath()) document.documentElement.classList.add('is-daily')

function PhoneApp() {
  if (isDailyPath()) {
    const match = window.location.pathname.match(/^\/daily\/(\d{4}-\d{2}-\d{2})/)
    const day = match?.[1] ?? new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Tokyo' })
    return <DailyBriefingPage day={day} />
  }
  if (isWeeklyPath()) return <WeeklyReviewPage />
  if (isScheduleChangePath()) return <ScheduleChangePage />
  if (isTrainingPreferencesPath()) return <TrainingPreferencesPage />
  return <WorkoutApp />
}

createRoot(document.getElementById('root')!).render(
  <AppErrorBoundary>
    <QueryClientProvider client={queryClient}>
      {isWorkoutPath() || isDailyPath() || isWeeklyPath() || isScheduleChangePath() || isTrainingPreferencesPath() ? (
        <Suspense fallback={<PageSkeleton />}><PhoneApp /></Suspense>
      ) : <AppShell />}
    </QueryClientProvider>
  </AppErrorBoundary>,
)
