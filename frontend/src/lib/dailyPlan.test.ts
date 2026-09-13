import assert from 'node:assert/strict'
import test from 'node:test'

import { notionFromPlan, trainingOverviewFromPlan, walkReminderFromPlan } from './dailyPlan.ts'
import type { DailyBriefing, TrainingOverview } from '../types.ts'

const fallback: TrainingOverview = {
  generated_at: 'fallback',
  timezone: 'Asia/Tokyo',
  phase: 'build_october',
  today: null,
  tomorrow: null,
  week_start: '2026-09-07',
  week: [],
  upcoming: [],
  countdowns: [],
  compliance: {},
  trends: { bike_decay: [], bjj_capacity: [], weight_7d_average: 80 },
  readiness: null,
}

const session = {
  id: 's1',
  planned_type: 'strength_a',
  title: 'Gym (Strength A)',
  status: 'planned',
  reason: 'Build.',
  coach_focus: [],
  exercises: [],
  estimated_minutes: 60,
  intensity: 'normal',
  actual_type: null,
  original_planned_type: null,
  phase: 'build_october',
  start_at: '2026-09-15T07:30:00+09:00',
  end_at: '2026-09-15T08:30:00+09:00',
  preparation: null,
  target_rounds: null,
  round_length_seconds: null,
  rest_seconds: null,
}

function dayBlock(training: typeof session | null) {
  return {
    date: '2026-09-15',
    emphasis: 'training' as const,
    headline: 'Tomorrow: gym',
    training,
    meetings: [],
    tasks: [],
    reminders: [],
  }
}

test('trainingOverviewFromPlan uses tomorrow.training, not the day block', () => {
  const plan = {
    date: '2026-09-14',
    timezone: 'Asia/Tokyo',
    workout: session,
    calendar: { status: 'ready' as const, meetings: [] },
    sobriety: { days: 7, answered: null, note: null },
    sleep: null,
    sunday: null,
    preview: false,
    daily_url: '/daily/2026-09-14',
    today: dayBlock(session),
    tomorrow: {
      ...dayBlock(session),
      date: '2026-09-15',
      headline: 'This is a day block, not a session',
      prescription: { session: 'strength_a', time: '07:30', work: 'Squat', focus: 'RIR', why: 'BJJ' },
      week_quality: 'good',
      bjj_candidates: [{ date: '2026-09-16', suggested_type: 'bjj_normal', reason: 'class', preferred_clock: '07:30' }],
    },
    phase: 'taper_october',
    week_start: '2026-09-14',
    week: [session],
    upcoming: [session],
    countdowns: [{ id: 'oct', name: 'All Japan', start_date: '2026-10-10', end_date: '2026-10-11', days_remaining: 26 }],
    trends: { bike_decay: [], bjj_capacity: [], weight_7d_average: 81.4 },
    readiness: { date: '2026-09-14', level: 'normal', weight_kg: 81.2 },
    last_adjustment: {
      id: 'adj-1', at: '2026-09-14T20:00:00+09:00', instruction: 'rest today',
      how: ['Rest today'], why: ['Fatigue'], banner: 'Changed the week.', notification: 'Changed the week.',
    },
  } as DailyBriefing

  const overview = trainingOverviewFromPlan(plan, fallback)
  assert.equal(overview.tomorrow?.title, 'Gym (Strength A)')
  assert.equal((overview.tomorrow as { headline?: string } | null)?.headline, undefined)
  assert.equal(overview.phase, 'taper_october')
  assert.equal(overview.trends.weight_7d_average, 81.4)
  assert.equal(overview.readiness?.weight_kg, 81.2)
  assert.equal(overview.week_quality, 'good')
  assert.equal(overview.tomorrow_prescription?.time, '07:30')
  assert.equal(overview.last_adjustment?.instruction, 'rest today')
  assert.equal(overview.bjj_candidates?.[0]?.date, '2026-09-16')
})

test('walkReminderFromPlan keeps nudge shape', () => {
  const reminder = walkReminderFromPlan({
    walk_reminder: { active: true, message: 'Walk now', dedupe_key: 'walk:window:2026-09-14:end-of-day' },
  } as DailyBriefing, { active: false, message: '', dedupe_key: '' })
  assert.deepEqual(reminder, {
    active: true,
    message: 'Walk now',
    dedupe_key: 'walk:window:2026-09-14:end-of-day',
  })
})

test('notionFromPlan maps today tasks', () => {
  const notion = notionFromPlan({
    today: {
      date: '2026-09-14',
      emphasis: 'work',
      headline: 'Tasks',
      training: null,
      meetings: [],
      reminders: [],
      tasks: [{ id: 't1', title: 'HMO deck', status: 'To do', is_overdue: false }],
    },
    calendar: { status: 'ready', synced_at: '2026-09-14T07:00:00+09:00', meetings: [] },
  } as DailyBriefing, { status: 'not_configured', synced_at: null, tasks: [] })
  assert.equal(notion.status, 'ready')
  assert.equal(notion.tasks[0]?.title, 'HMO deck')
})
