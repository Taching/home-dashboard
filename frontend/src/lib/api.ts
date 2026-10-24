import type {
  ActivityEvent,
  CalendarToday,
  CommandIntent,
  CommandResult,
  DailyBriefing,
  Dashboard,
  Display,
  LiftHistory,
  NotionToday,
  PlanAdjustment,
  Reading,
  SpotifyNowPlaying,
  TrainingLogPayload,
  TrainingLogResult,
  TrainingOverview,
  TrainingPlan,
  TrainingPreferences,
  TrainingSession,
  TrainingToday,
  TrainingWeeklyAnalysis,
  WalkReminder,
  WalkingPadToday,
  WeatherForecast,
  WeeklyReview,
  WellbeingHistory,
  WorkoutLogPayload,
} from '../types'
import { announcePlanningChange } from './planningRefresh'

async function requireJson<T>(response: Response): Promise<T> {
  if (!response.ok) throw new Error(`Request failed with status ${response.status}`)
  return response.json() as Promise<T>
}

const GET_TIMEOUT_MS = 8_000

async function freshGet(path: string, signal?: AbortSignal) {
  const controller = new AbortController()
  const timeout = window.setTimeout(() => controller.abort(), GET_TIMEOUT_MS)
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  try {
    return await fetch(path, {
      cache: 'no-store',
      headers: { 'Cache-Control': 'no-cache' },
      signal: controller.signal,
    })
  } finally {
    window.clearTimeout(timeout)
    signal?.removeEventListener('abort', abort)
  }
}

export async function fetchDashboard(signal?: AbortSignal) {
  return requireJson<Dashboard>(await freshGet('/api/v1/dashboard', signal))
}

export async function fetchReadings() {
  const result = await requireJson<{ readings: Reading[] }>(
    await fetch('/api/v1/readings?hours=24'),
  )
  return result.readings
}

export async function fetchCalendarEvents(start: string, days = 30, signal?: AbortSignal) {
  const query = new URLSearchParams({ start, days: String(days) })
  return requireJson<CalendarToday>(await freshGet(`/api/v1/calendar/events?${query}`, signal))
}

export async function fetchNotionToday() {
  return requireJson<NotionToday>(await fetch('/api/v1/notion/today'))
}

export async function fetchSpotifyNowPlaying(signal?: AbortSignal) {
  return requireJson<SpotifyNowPlaying>(await freshGet('/api/v1/spotify/now-playing', signal))
}

export async function fetchActivityEvents(limit = 40) {
  const query = new URLSearchParams({ limit: String(limit) })
  return requireJson<ActivityEvent[]>(await fetch(`/api/v1/activity/events?${query}`))
}

export async function fetchWeather(signal?: AbortSignal) {
  return requireJson<WeatherForecast>(await freshGet('/api/v1/weather', signal))
}

export async function fetchWalkingPadToday(signal?: AbortSignal) {
  return requireJson<WalkingPadToday>(await freshGet('/api/v1/walkingpad/today', signal))
}

export async function fetchWalkingPadReminder() {
  return requireJson<WalkReminder>(await fetch('/api/v1/walkingpad/reminder'))
}

export async function fetchTrainingOverview(signal?: AbortSignal) {
  return requireJson<TrainingOverview>(await freshGet('/api/v1/training/overview', signal))
}

export async function fetchTrainingPlans() {
  const result = await requireJson<{ plans: TrainingPlan[] }>(await fetch('/api/v1/training/plans'))
  return result.plans
}

export async function fetchTrainingPlan(slug: string) {
  return requireJson<TrainingPlan>(await fetch(`/api/v1/training/plans/${slug}`))
}

export async function fetchLiftHistory(signal?: AbortSignal) {
  return requireJson<LiftHistory>(await freshGet('/api/v1/training/lifts', signal))
}

export async function fetchTrainingSession(sessionId: string, signal?: AbortSignal) {
  return requireJson<TrainingSession>(await freshGet(`/api/v1/training/sessions/${sessionId}`, signal))
}

export async function logTrainingSessionResult(sessionId: string, payload: Record<string, unknown>) {
  const result = await requireJson<TrainingSession>(await fetch(`/api/v1/training/sessions/${sessionId}/result`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  announcePlanningChange()
  return result
}

export async function askCoach(sessionId: string) {
  return requireJson<{ advice: string; source: string }>(
    await fetch(`/api/v1/training/sessions/${sessionId}/coach`, { method: 'POST' }),
  )
}

export async function fetchTrainingPreferences(signal?: AbortSignal) {
  return requireJson<TrainingPreferences>(await freshGet('/api/v1/training/preferences', signal))
}

export async function saveTrainingPreferences(notes: string) {
  return requireJson<TrainingPreferences>(await fetch('/api/v1/training/preferences', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ notes: notes.trim() || null }),
  }))
}

export async function requestScheduleChange(instruction: string) {
  const response = await fetch('/api/v1/training/replan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ instruction }),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `Request failed with status ${response.status}`)
  }
  const result = await response.json() as { decision: PlanAdjustment; status: string }
  announcePlanningChange()
  return result
}

export async function fetchWeeklyReview(weekStart: string, signal?: AbortSignal) {
  return requireJson<WeeklyReview>(await freshGet(`/api/v1/training/weeks/${weekStart}/review`, signal))
}

export async function runWeeklyReview(weekStart: string) {
  const result = await requireJson<WeeklyReview>(await fetch(`/api/v1/training/weeks/${weekStart}/review`, {
    method: 'POST',
  }))
  announcePlanningChange()
  return result
}

export async function fetchTrainingWeeklyAnalysis(weekStart: string, signal?: AbortSignal) {
  return requireJson<TrainingWeeklyAnalysis>(
    await freshGet(`/api/v1/weekly-reviews/${weekStart}`, signal),
  )
}

export async function recomputeWeeklyAnalysis(weekStart: string) {
  return requireJson<TrainingWeeklyAnalysis>(
    await fetch(`/api/v1/weekly-reviews/${weekStart}/recompute`, { method: 'POST' }),
  )
}

export async function askWeeklyCoach(weekStart: string) {
  return requireJson<{ status: string; message?: string; analysis: TrainingWeeklyAnalysis }>(
    await fetch(`/api/v1/weekly-reviews/${weekStart}/ask-coach`, { method: 'POST' }),
  )
}

export async function putExerciseResults(
  sessionId: string,
  exercises: Array<Record<string, unknown>>,
) {
  return requireJson<{ status: string }>(
    await fetch(`/api/v1/training-sessions/${sessionId}/exercise-results`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ exercises }),
    }),
  )
}

export async function putBjjAnalysis(sessionId: string, payload: Record<string, unknown>) {
  return requireJson<{ status: string }>(
    await fetch(`/api/v1/training-sessions/${sessionId}/bjj-analysis`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  )
}

export async function postDailyConstraint(day: string, payload: { kind: 'cannot_train' | 'holiday' | 'no_class' | 'miss'; miss_reason?: string; note?: string }) {
  const result = await requireJson<DailyBriefing>(await fetch(`/api/v1/daily/${day}/constraint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  announcePlanningChange()
  return result
}

export async function fetchTrainingToday() {
  return requireJson<TrainingToday>(await fetch('/api/v1/training/today'))
}

export async function logTraining(payload: TrainingLogPayload) {
  return requireJson<TrainingLogResult>(await fetch('/api/v1/training/log', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function fetchWellbeingHistory(days = 90, signal?: AbortSignal) {
  return requireJson<WellbeingHistory>(await freshGet(`/api/v1/wellbeing/history?days=${days}`, signal))
}

export async function fetchDailyBriefing(day: string, preview?: string, signal?: AbortSignal) {
  const query = preview ? `?preview=${encodeURIComponent(preview)}` : ''
  return requireJson<DailyBriefing>(await freshGet(`/api/v1/daily/${day}${query}`, signal))
}

export async function fetchDailyPlan(day: string, signal?: AbortSignal) {
  return requireJson<DailyBriefing>(await freshGet(`/api/v1/plan/${day}`, signal))
}

export async function logDailyWorkout(day: string, payload: WorkoutLogPayload) {
  const result = await requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/workout`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  announcePlanningChange()
  return result
}

export async function logWorkout(payload: WorkoutLogPayload) {
  const result = await requireJson<TrainingLogResult>(await fetch('/api/v1/training/workout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
  announcePlanningChange()
  return result
}

export async function logSober(day: string, payload: { sober: boolean; note?: string }) {
  return requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/sober`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function logSleep(day: string, hours: number) {
  return requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/sleep`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ hours }),
  }))
}

export async function closeDailyDay(day: string, force = false) {
  return requireJson<DailyBriefing>(await fetch(`/api/v1/daily/${day}/close`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ force }),
  }))
}

export async function logWeight(day: string, weightKg: number) {
  return requireJson<TrainingLogResult>(await fetch(`/api/v1/daily/${day}/weight`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ weight_kg: weightKg }),
  }))
}

export async function logWeeklyCheckIn(
  day: string,
  payload: {
    energy: number
    hunger: number
    bjj_performance: number
    waist_cm?: number
    pain_note?: string
    note?: string
  },
) {
  return requireJson<DailyBriefing>(await fetch(`/api/v1/daily/${day}/weekly`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export async function fetchSpotifyWebPlaybackToken() {
  return requireJson<{ access_token: string }>(await fetch('/api/v1/spotify/web-playback-token'))
}

export async function transferSpotifyPlayback(deviceId: string) {
  return requireJson<{ status: string }>(await fetch('/api/v1/spotify/transfer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device_id: deviceId }),
  }))
}

export async function registerSpotifyDevice(deviceId: string) {
  return requireJson<{ status: string }>(await fetch('/api/v1/spotify/device', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ device_id: deviceId }),
  }))
}

export async function startSpotifyDj() {
  return requireJson<{ status: string }>(await fetch('/api/v1/spotify/dj', { method: 'POST' }))
}

export async function setSystemVolume(volumePercent: number) {
  return requireJson<{ volume_percent: number | null; available: boolean; output_label: string }>(
    await fetch('/api/v1/system/volume', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ volume_percent: volumePercent }),
    }),
  )
}

export async function sendCommand(intent: CommandIntent): Promise<CommandResult> {
  return requireJson<CommandResult>(await fetch('/api/v1/commands', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ intent, source: 'ui' }),
  }))
}

export async function setDisplaySchedule(enabled: boolean) {
  return requireJson<Display>(await fetch('/api/v1/display/schedule', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  }))
}

export async function notifyChili(message: string, dedupeKey: string) {
  return requireJson<{ status: 'sent' | 'skipped' | 'not_configured' | 'failed', message?: string | null }>(
    await fetch('/api/v1/chili/notify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message, dedupe_key: dedupeKey }),
    }),
  )
}

export interface ExerciseItem {
  slug: string
  name: string
  aliases: string[]
  category: string
  movement_pattern: string
  plane: string
  training_intent: string
  primary_region: string
  primary_muscles: string[]
  equipment: string[]
  substitution_group: string
  movement_speed: string
  laterality: string
  difficulty: string
  bjj_tags: string[]
  risk_notes: string | null
  is_active: boolean
}

export interface AlternativeResult {
  slug: string
  name: string
  score: number
  why: string[]
  tradeoff: string | null
}

export interface ExerciseFilters {
  categories: string[]
  movement_patterns: string[]
  planes: string[]
  training_intents: string[]
  primary_regions: string[]
  movement_speeds: string[]
  lateralities: string[]
  difficulties: string[]
  equipment_tokens: string[]
}

export async function fetchExercises(params?: {
  search?: string
  pattern?: string
  intent?: string
  region?: string
  equipment?: string
  bjj_tag?: string
  substitution_group?: string
  category?: string
}, signal?: AbortSignal) {
  const query = new URLSearchParams()
  if (params?.search) query.set('search', params.search)
  if (params?.pattern) query.set('pattern', params.pattern)
  if (params?.intent) query.set('intent', params.intent)
  if (params?.region) query.set('region', params.region)
  if (params?.equipment) query.set('equipment', params.equipment)
  if (params?.bjj_tag) query.set('bjj_tag', params.bjj_tag)
  if (params?.substitution_group) query.set('substitution_group', params.substitution_group)
  if (params?.category) query.set('category', params.category)
  const url = query.toString() ? `/api/v1/exercises?${query}` : '/api/v1/exercises'
  return requireJson<{ exercises: ExerciseItem[]; count: number }>(await freshGet(url, signal))
}

export async function fetchExercise(slug: string, signal?: AbortSignal) {
  return requireJson<ExerciseItem>(await freshGet(`/api/v1/exercises/${slug}`, signal))
}

export async function fetchExerciseFilters(signal?: AbortSignal) {
  return requireJson<ExerciseFilters>(await freshGet('/api/v1/exercises/filters', signal))
}

export async function fetchExerciseAlternatives(
  slug: string,
  params: {
    available_equipment: string[]
    excluded_exercises?: string[]
    limitations?: string[]
    max_results?: number
    allow_advanced?: boolean
  },
) {
  return requireJson<{ source: string; alternatives: AlternativeResult[] }>(
    await fetch(`/api/v1/exercises/${slug}/alternatives`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }),
  )
}

export async function setExerciseOverride(
  source: string,
  target: string,
  decision: 'prefer' | 'allow' | 'exclude',
  reason?: string,
) {
  return requireJson<{ source: string; target: string; decision: string; reason: string | null }>(
    await fetch(`/api/v1/exercise-substitution-overrides/${source}/${target}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ decision, reason: reason || null }),
    }),
  )
}

export async function deleteExerciseOverride(source: string, target: string) {
  return requireJson<{ status: string }>(
    await fetch(`/api/v1/exercise-substitution-overrides/${source}/${target}`, {
      method: 'DELETE',
    }),
  )
}

export async function fetchBjjFailureTypes(signal?: AbortSignal) {
  return requireJson<{ failure_types: { code: string; label: string; description: string }[]; count: number }>(
    await freshGet('/api/v1/bjj-failure-types', signal),
  )
}
