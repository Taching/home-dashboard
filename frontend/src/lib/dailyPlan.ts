import type { DailyBriefing, DailyPlanItem, NotionToday, TrainingOverview, WalkReminder } from '../types'

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
