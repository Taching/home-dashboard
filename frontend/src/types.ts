export type LightState = 'on' | 'off' | 'unknown'
export type IntegrationStatus = 'not_configured' | 'ready' | 'stale' | 'unavailable'

export type Light = {
  last_command_state: LightState
  last_command_at: string | null
  available: boolean
}

export type WaterPump = {
  state: 'idle' | 'running'
  last_run_at: string | null
  last_run_status: string | null
  available: boolean
}

export type Display = {
  state: 'visible' | 'hidden'
  schedule_enabled: boolean
  schedule_on_hour: number
  schedule_off_hour: number
  power_available: boolean
  manual_override: boolean
}

export type Dashboard = {
  temperature_c: number | null
  humidity_percent: number | null
  last_updated_at: string | null
  light: Light
  water_pump: WaterPump
  system: SystemStatus
  display: Display
  integrations: Record<string, string>
  wellbeing: WellbeingSummary
}

export type WellbeingSummary = {
  sober_days: number
  workouts_this_week: number
  gym_this_week: number
  jiujitsu_this_week: number
  gym_weekly_goal: number
  jiujitsu_weekly_goal: number
  week_start: string
  latest_checkin_date: string | null
  checkin_stale: boolean
  current_weight_kg: number | null
  weight_goal_kg: number
  latest_weight_date: string | null
}

export type SystemStatus = {
  cpu_temperature_c: number | null
  load_1m: number | null
  load_percent: number | null
  memory_used_percent: number | null
  memory_used_mb: number | null
  memory_total_mb: number | null
  storage_used_percent: number | null
  storage_free_gb: number | null
  storage_total_gb: number | null
  bluetooth_status: 'connected' | 'disconnected' | 'unavailable'
  bluetooth_device_name: string | null
  bluetooth_is_default_output: boolean
  volume_percent: number | null
  volume_available: boolean
  volume_output_label: string
}

export type Reading = {
  recorded_at: string
  temperature_c: number
  humidity_percent: number
}

export type CommandIntent =
  | 'light.turn_on'
  | 'light.turn_off'
  | 'water.run'
  | 'water.stop'
  | 'display.show'
  | 'display.hide'

export type CommandResult = {
  status: 'success' | 'failed' | 'skipped'
  intent: CommandIntent
  message: string | null
  light: Light | null
  water_pump: WaterPump | null
  display: Display | null
}

export type CalendarEvent = {
  id: string
  title: string
  start_at: string
  end_at: string
  is_all_day: boolean
  is_current: boolean
  source?: string
  training_session_id?: string | null
  calendar_title?: string | null
}

export type CalendarToday = {
  status: IntegrationStatus
  synced_at: string | null
  events: CalendarEvent[]
}

export type NotionTask = {
  id: string
  title: string
  due_at: string | null
  is_overdue: boolean
  status: string | null
  priority: string | null
  task_type: string | null
}

export type NotionToday = {
  status: IntegrationStatus
  synced_at: string | null
  tasks: NotionTask[]
}

export type SpotifyNowPlaying = {
  status: IntegrationStatus
  synced_at: string | null
  track: string | null
  artist: string | null
  artwork_url: string | null
  device_name: string | null
  is_playing: boolean
}

export type WalkingPadStatus = IntegrationStatus | 'walking'

export type WalkingPadToday = {
  status: WalkingPadStatus
  synced_at: string | null
  total_minutes: number
  total_distance_km: number
  total_steps: number
  total_calories: number
  goal_minutes: number
  goal_distance_km: number
  goal_steps: number
  session_count: number
  goal_met: boolean
  active_session: {
    external_id: string
    started_at: string
    duration_seconds: number
    distance_km: number
    steps: number
    calories: number
  } | null
}

export type WalkReminder = {
  active: boolean
  message: string
  dedupe_key: string
}

export type TrainingKind =
  | 'strength_a'
  | 'strength_b'
  | 'zone2'
  | 'grip'
  | 'bjj'
  | 'bjj_hard'
  | 'sober'
  | 'rest'

export type TrainingCompleted = 'yes' | 'partial' | 'skipped' | 'no'
export type TrainingFeeling = 'fresh' | 'normal' | 'tired' | 'wrecked'

export type TrainingBlock = {
  title: string
  prescription: string | null
  details: string[]
}

export type TrainingPlan = {
  slug: string
  kind: TrainingKind
  name: string
  duration: string
  category: 'strength' | 'cardio' | 'grip' | 'bjj' | 'rest' | 'checkin'
  summary: string
  blocks: TrainingBlock[]
  notes: string[]
  questions: string[]
}

export type TrainingExerciseDone = {
  name: string
  done: boolean
}

export type TrainingLog = {
  id: number
  logged_at: string
  kind: TrainingKind
  completed: TrainingCompleted
  feeling: TrainingFeeling | null
  note: string | null
  rounds: string | null
  duration_minutes: number | null
  avg_hr: number | null
  max_hr: number | null
  distance_km: number | null
  exercises: TrainingExerciseDone[]
  source: 'ui' | 'openclaw' | 'automation'
}

export type TrainingToday = {
  date: string
  suggested: TrainingPlan[]
  suggested_source: 'calendar' | 'week'
  logs: TrainingLog[]
  sober: TrainingLog | null
  workout_url: string
  advice?: string | null
  planner_status?: string | null
}

export type TrainingLogPayload = {
  kind?: TrainingKind
  completed?: TrainingCompleted
  feeling?: TrainingFeeling
  note?: string
  rounds?: string
  duration_minutes?: number
  avg_hr?: number
  max_hr?: number
  distance_km?: number
  exercises?: TrainingExerciseDone[]
  message?: string
}

export type WorkoutLogPayload = {
  kind?: string
  exercises: TrainingExerciseDone[]
  note?: string
}

export type DailyExercise = {
  name: string
  prescription: string | null
  details: string[]
  done: boolean
}

export type DailyWorkout = {
  kind: TrainingKind
  title: string
  summary: string
  status: 'planned' | 'logged'
  completed: TrainingCompleted | null
  note: string | null
  exercises: DailyExercise[]
}

export type DailyMeeting = {
  id?: string
  title: string
  start_at: string
  end_at: string
  is_all_day: boolean
}

export type PlannedExercise = {
  name: string
  load_value: number | null
  load_unit: string | null
  sets: number | null
  reps: string | null
  duration_seconds: number | null
  notes: string | null
  done?: boolean
}

export type PlannedWorkout = {
  id: string
  planned_type: string
  title: string
  status: string
  reason: string
  coach_focus: string[]
  exercises: PlannedExercise[]
  estimated_minutes: number
  intensity: string
  is_all_day?: boolean
  notes?: string | null
  start_at?: string
  target_rounds?: number | null
  session_rpe?: number | null
  miss_reason?: string | null
  result?: TrainingSessionResult | null
  exercise_results?: TrainingExerciseResult[]
}

export type TrainingSessionResult = {
  status: string
  miss_reason?: string | null
  session_rpe?: number | null
  difficulty?: number | null
  fatigue?: string | null
  pain?: boolean | null
  soreness?: string | null
  notes?: string | null
  bjj_rounds?: number | null
  perceived_intensity?: string | null
  cardio?: string | null
  grip_fatigue?: string | null
  technical_performance?: string | null
  recovery_activity?: string | null
}

export type TrainingExerciseResult = {
  exercise_id: number
  actual_load?: number | null
  actual_sets?: number | null
  actual_reps?: string | null
  actual_duration_seconds?: number | null
  completed: boolean
}

export type TrainingSession = PlannedWorkout & {
  actual_type: string | null
  original_planned_type: string | null
  phase: string
  start_at: string
  end_at: string
  preparation: string | null
  target_rounds: number | null
  round_length_seconds: number | null
  rest_seconds: number | null
  revision: number
  session_rpe: number | null
  final_round_quality: number | null
  calendar_event_id: string | null
}

export type TrainingWeeklyStatus = Record<string, { completed: number, target: number }>

export type TomorrowPrescription = {
  session: string
  time: string | null
  work: string
  focus: string
  why: string
  weekly_status: TrainingWeeklyStatus
}

export type BjjCandidate = {
  date: string
  suggested_type: string
  reason: string
  preferred_clock: string | null
}

export type PlanAdjustment = {
  id: string
  at: string
  instruction: string
  how: string[]
  why: string[]
  banner: string
  notification: string
  source?: string
  tomorrow?: { session?: string | null, time?: string | null, why?: string | null }
}

export type TrainingOverview = {
  generated_at: string
  timezone: string
  phase: string
  today: TrainingSession | null
  tomorrow: TrainingSession | null
  week_start: string
  week: TrainingSession[]
  upcoming: TrainingSession[]
  countdowns: { id: string, name: string, start_date: string, end_date: string, days_remaining: number }[]
  compliance: TrainingWeeklyStatus
  week_quality?: string
  tomorrow_prescription?: TomorrowPrescription | null
  last_adjustment?: PlanAdjustment | null
  bjj_candidates?: BjjCandidate[]
  trends: {
    bike_decay: { session_id: string, decay_percent: number }[]
    bjj_capacity: { date: string, rounds: number, final_quality: number | null }[]
    weight_7d_average: number | null
  }
  readiness: {
    date: string
    level: string
    fatigue_state?: string | null
    alerts: string[]
    sleep_hours: number | null
    sleep_quality: number | null
    fatigue: number | null
    soreness: number | null
    grip_fatigue: number | null
    pain: boolean | null
    pain_notes: string | null
    motivation: number | null
    weight_kg: number | null
  } | null
  day_flags?: Record<string, string[]>
}

export type WeeklyReview = {
  week_start: string
  sessions: TrainingSession[]
  planned: Record<string, number>
  completed: Record<string, number>
  average_rpe: number | null
  adaptation: Record<string, number | boolean>
  what_changes: string
  trends?: {
    rpe?: string
    average_rpe?: number | null
    strength_load_delta?: number
    strength_volume_delta?: number
  }
  recovery?: {
    fatigue?: string | null
    soreness?: string | null
    notes?: string
  }
}

export type DailyWeekSession = {
  date: string
  kind: TrainingKind
  title: string
  completed: TrainingCompleted | null
  note: string | null
  exercises: TrainingExerciseDone[]
}

export type DailyAnswerItem = {
  id: 'workout' | 'sunday' | 'sober'
  label: string
  required: boolean
  done: boolean
}

export type DailyAnswers = {
  items: DailyAnswerItem[]
  all_answered: boolean
  chili_reply?: string | null
  chili_delivery?: string | null
}

export type DailySunday = {
  week_start: string
  week_ending: string
  weight_kg: number | null
  previous_weight_kg: number | null
  delta_kg: number | null
  review_note: string | null
  submitted: boolean
  sessions: DailyWeekSession[]
}

export type DailyPlanItem = {
  id: string
  title: string
  start_at?: string
  end_at?: string
  is_all_day?: boolean
  clock?: string
  due_at?: string | null
  is_overdue?: boolean
  priority?: string | null
  task_type?: string | null
  status?: string | null
  kind?: string
  detail?: string
}

export type DailyPlanDay = {
  date: string
  emphasis: 'work' | 'training' | 'mixed'
  headline: string
  training: PlannedWorkout | null
  meetings: DailyPlanItem[]
  tasks: DailyPlanItem[]
  reminders: DailyPlanItem[]
  preparation?: string
  prescription?: TomorrowPrescription | null
  bjj_candidates?: BjjCandidate[]
  week_quality?: string | null
}

export type DailyBriefing = {
  date: string
  timezone: string
  workout: PlannedWorkout | null
  workouts?: DailyWorkout[]
  calendar: {
    status: IntegrationStatus
    synced_at?: string | null
    meetings: DailyMeeting[]
  }
  notion?: {
    status: IntegrationStatus
    synced_at?: string | null
    tasks: DailyPlanItem[]
  }
  sobriety: {
    days: number
    answered: 'yes' | 'no' | null
    note: string | null
  }
  sleep: null
  sunday: DailySunday | null
  preview: boolean
  daily_url: string
  answers?: DailyAnswers
  chili_reply?: string | null
  chili_delivery?: string | null
  advice?: string | null
  advice_window?: 'morning' | 'lunch' | 'evening'
  message?: string | null
  today?: DailyPlanDay
  tomorrow?: DailyPlanDay
  last_adjustment?: PlanAdjustment | null
  generated_at?: string
  phase?: string
  week_start?: string
  week?: TrainingSession[]
  upcoming?: TrainingSession[]
  countdowns?: TrainingOverview['countdowns']
  compliance?: TrainingWeeklyStatus
  week_quality?: string | null
  bjj_candidates?: BjjCandidate[]
  trends?: TrainingOverview['trends'] | null
  readiness?: TrainingOverview['readiness']
  day_flags?: Record<string, string[]>
  walk_reminder?: WalkReminder
}

export type TrainingLogResult = {
  status: 'logged' | 'failed'
  message: string
  log?: TrainingLog | null
  advice?: string | null
  briefing?: DailyBriefing
}

export type OpenClawMessage = {
  id: string
  role: 'user' | 'assistant' | 'system'
  text: string
  created_at: string | null
  sender?: 'user' | 'home-dashboard-agent' | 'assistant' | 'system' | null
}

export type OpenClawConversation = {
  status: IntegrationStatus
  messages: OpenClawMessage[]
  message: string | null
}

export type OpenClawSendResult = {
  status: 'success' | 'failed'
  delivery_status: string | null
  reply: string | null
  message: string | null
}

export type VoiceState = 'offline' | 'idle' | 'listening' | 'thinking' | 'complete' | 'error'

export type VoiceStatus = {
  state: VoiceState
  updated_at: string | null
  transcript: string | null
  message: string | null
}

export type VoiceEventDirection = 'in' | 'out' | 'info'

export type ActivityEvent = {
  at: string
  direction: VoiceEventDirection
  service: string
  detail: string
}

export type VoiceEvent = ActivityEvent

export type WeatherIcon = 'sunny' | 'evening' | 'cloudy' | 'fog' | 'rain' | 'snow' | 'storm'

export type WeatherDay = {
  date: string
  label: string
  high_c: number
  low_c: number
  condition: string
  icon: WeatherIcon
  current_c?: number | null
}

export type WeatherForecast = {
  status: IntegrationStatus
  location: string
  synced_at: string | null
  today: WeatherDay | null
  tomorrow: WeatherDay | null
}
