import type { DailyAnswers, DailyBriefing, DailyPlanItem, NotionToday, TrainingOverview, WalkReminder } from '../types'
import { workoutAlreadyLogged } from './workoutMatch'

export function dailyAnswersFromBriefing(briefing: DailyBriefing): DailyAnswers {
  const chiliReply = briefing.chili_reply ?? briefing.answers?.chili_reply ?? null
  const chiliDelivery = briefing.chili_delivery ?? briefing.answers?.chili_delivery ?? null
  if (briefing.answers?.items?.length) {
    return {
      ...briefing.answers,
      chili_reply: chiliReply,
      chili_delivery: chiliDelivery,
    }
  }
  const kind = briefing.workout?.planned_type ?? ''
  const workoutRequired = Boolean(
    briefing.workout
    && !briefing.preview
    && kind !== 'rest'
    && !kind.startsWith('bjj_')
    && kind !== 'competition'
    && briefing.workout.status !== 'preview',
  )
  const sundayRequired = Boolean(briefing.sunday) && !briefing.preview
  const items = [
    {
      id: 'workout' as const,
      label: 'Workout',
      required: workoutRequired,
      done: !workoutRequired || workoutAlreadyLogged(briefing.workout?.status),
    },
    {
      id: 'sunday' as const,
      label: 'Sunday review',
      required: sundayRequired,
      done: !sundayRequired || Boolean(briefing.sunday?.submitted),
    },
    {
      id: 'sober' as const,
      label: 'Sober',
      required: !briefing.preview,
      done: briefing.preview || briefing.sobriety.answered != null,
    },
  ]
  return {
    items,
    all_answered: items.every((item) => !item.required || item.done),
    chili_reply: chiliReply,
    chili_delivery: chiliDelivery,
  }
}

export function trainingOverviewFromPlan(
  plan: DailyBriefing | null,
  fallback: TrainingOverview,
): TrainingOverview {
  if (!plan) return fallback
  return {
    generated_at: plan.generated_at ?? fallback.generated_at,
    timezone: plan.timezone,
    phase: plan.phase ?? fallback.phase,
    today: (plan.today?.training ?? plan.workout ?? null) as TrainingOverview['today'],
    tomorrow: (plan.tomorrow?.training ?? null) as TrainingOverview['tomorrow'],
    week_start: plan.week_start ?? fallback.week_start,
    week: plan.week ?? [],
    upcoming: plan.upcoming ?? [],
    countdowns: plan.countdowns ?? [],
    compliance: plan.compliance ?? {},
    week_quality: plan.tomorrow?.week_quality ?? plan.week_quality ?? undefined,
    tomorrow_prescription: plan.tomorrow?.prescription ?? null,
    last_adjustment: plan.last_adjustment,
    bjj_candidates: plan.tomorrow?.bjj_candidates ?? plan.bjj_candidates ?? [],
    trends: plan.trends ?? fallback.trends,
    readiness: plan.readiness ?? null,
    day_flags: plan.day_flags ?? fallback.day_flags,
  }
}

export function notionFromPlan(
  plan: DailyBriefing | null,
  fallback: NotionToday,
): NotionToday {
  if (plan?.notion) {
    return {
      status: plan.notion.status,
      synced_at: plan.notion.synced_at ?? null,
      tasks: (plan.notion.tasks ?? []).map(taskFromPlanItem),
    }
  }
  if (!plan?.today) return fallback
  return {
    status: fallback.status,
    synced_at: fallback.synced_at,
    tasks: (plan.today.tasks ?? []).map(taskFromPlanItem),
  }
}

export function walkReminderFromPlan(
  plan: DailyBriefing | null,
  fallback: WalkReminder,
): WalkReminder {
  const reminder = plan?.walk_reminder
  if (!reminder) return fallback
  return {
    active: Boolean(reminder.active),
    message: reminder.message ?? '',
    dedupe_key: reminder.dedupe_key ?? '',
  }
}

function taskFromPlanItem(task: DailyPlanItem) {
  return {
    id: task.id,
    title: task.title,
    due_at: task.due_at ?? null,
    is_overdue: Boolean(task.is_overdue),
    status: task.status ?? null,
    priority: task.priority ?? null,
    task_type: task.task_type ?? null,
  }
}
