from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.core.settings import settings


TRAVEL_MARKERS = ("flight", "travel", "airport", "shinkansen", "train to")
DINNER_MARKERS = ("dinner", "izakaya")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _clock(value: datetime, timezone: ZoneInfo, all_day: bool = False) -> str:
    if all_day:
        return "all day"
    return value.astimezone(timezone).strftime("%H:%M")


def _meeting_hours(meetings: list[dict], day: date, timezone: ZoneInfo) -> float:
    day_start = datetime.combine(day, time.min, timezone)
    day_end = day_start + timedelta(days=1)
    total = 0.0
    for meeting in meetings:
        if meeting.get("is_all_day"):
            continue
        start = _as_utc(datetime.fromisoformat(meeting["start_at"])).astimezone(timezone)
        end = _as_utc(datetime.fromisoformat(meeting["end_at"])).astimezone(timezone)
        clipped_start = max(start, day_start)
        clipped_end = min(end, day_end)
        if clipped_end > clipped_start:
            total += (clipped_end - clipped_start).total_seconds() / 3600
    return total


def _emphasis(training: dict | None, meetings: list[dict], day: date, timezone: ZoneInfo) -> str:
    hours = _meeting_hours(meetings, day, timezone)
    kind = (training or {}).get("planned_type") or ""
    hard_training = kind.startswith("bjj_") or kind in {"strength_a", "competition"}
    if hours >= 4 or len(meetings) >= 3:
        return "work"
    if hard_training and hours < 3:
        return "training"
    if training and kind not in {"rest", "recovery"}:
        return "mixed"
    return "work" if meetings else "mixed"


def _serialize_meeting(event: Any, timezone: ZoneInfo) -> dict:
    start = _as_utc(event.start_at)
    end = _as_utc(event.end_at)
    return {
        "id": event.external_id,
        "title": event.title,
        "start_at": start.isoformat(),
        "end_at": end.isoformat(),
        "is_all_day": bool(event.is_all_day),
        "clock": _clock(start, timezone, bool(event.is_all_day)),
    }


def _serialize_task(task: Any) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "due_at": task.due_at.isoformat() if task.due_at else None,
        "is_overdue": bool(task.is_overdue),
        "priority": task.priority,
        "task_type": task.task_type,
        "status": task.status,
    }


def _priority_tasks(tasks: list[Any], day: date, timezone: ZoneInfo, *, limit: int = 5) -> list[Any]:
    def rank(task: Any) -> tuple[int, int, datetime, str]:
        due = task.due_at.astimezone(timezone).date() if task.due_at else None
        due_today = 0 if due == day or task.is_overdue else 1
        priority = (task.priority or "").lower()
        urgency = 0 if "urgent" in priority or "high" in priority else 1
        return (
            due_today,
            urgency,
            task.due_at or datetime.max.replace(tzinfo=UTC),
            task.title.lower(),
        )

    return sorted(tasks, key=rank)[:limit]


def _reminders(
    *,
    day: date,
    now: datetime,
    timezone: ZoneInfo,
    walking,
    check_in: dict | None,
) -> list[dict]:
    reminders: list[dict] = []
    if walking is not None and hasattr(walking, "today"):
        try:
            snapshot = walking.today(now)
        except TypeError:
            snapshot = walking.today()
        goal_steps = int(getattr(snapshot, "goal_steps", 0) or 0)
        total_steps = int(getattr(snapshot, "total_steps", 0) or 0)
        remaining = max(0, goal_steps - total_steps)
        if not getattr(snapshot, "goal_met", False) and remaining > 0:
            reminders.append({
                "id": "walk",
                "kind": "walk",
                "title": f"{remaining:,} steps left",
                "detail": f"{total_steps:,} of {goal_steps:,} steps",
            })
    answered = check_in.get("sober") if check_in else None
    if now.astimezone(timezone).date() == day and now.astimezone(timezone).hour >= 18 and answered is None:
        reminders.append({
            "id": "sober",
            "kind": "sober",
            "title": "Evening sober check-in",
            "detail": "Close the day on the daily page",
        })
    return reminders


def _headline(day_label: str, training: dict | None, meetings: list[dict], tasks: list[dict], reminders: list[dict]) -> str:
    parts: list[str] = []
    if meetings:
        first = meetings[0]
        extra = f" +{len(meetings) - 1}" if len(meetings) > 1 else ""
        parts.append(f"{first['clock']} {first['title']}{extra}")
    if training and training.get("planned_type") not in {None, "rest"}:
        start = training.get("start_at")
        clock = ""
        if start and not training.get("is_all_day"):
            clock = datetime.fromisoformat(start).astimezone(ZoneInfo(settings.timezone)).strftime("%H:%M ")
        parts.append(f"{clock}{training.get('title')}")
    elif training and training.get("planned_type") == "rest":
        parts.append("Rest day")
    if tasks:
        parts.append(f"{len(tasks)} priority task{'s' if len(tasks) != 1 else ''}")
    if reminders:
        parts.append(reminders[0]["title"])
    return f"{day_label}: " + ", ".join(parts) if parts else f"{day_label}: protect the open time"


def _tomorrow_preparation(training: dict | None, meetings: list[dict], tasks: list[dict]) -> str:
    bits: list[str] = []
    for meeting in meetings[:3]:
        bits.append(f"{meeting['clock']} {meeting['title']}")
    for task in tasks[:2]:
        bits.append(f"prepare {task['title']}")
    if training and training.get("planned_type") not in {None, "rest"}:
        start = training.get("start_at")
        clock = ""
        if start and not training.get("is_all_day"):
            clock = datetime.fromisoformat(start).astimezone(ZoneInfo(settings.timezone)).strftime("%H:%M ")
        bits.append(f"{clock}{training.get('title')}".strip())
        focus = (training.get("coach_focus") or [None])[0]
        if focus:
            bits.append(focus.split(".")[0])
    elif training and training.get("planned_type") == "rest":
        bits.append("rest — no extra fatigue")
    return "Tomorrow: " + ", ".join(bits) if bits else "Tomorrow: protect recovery and do not fill the space automatically."


def _aware(value: datetime, timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone)
    return value.astimezone(timezone)


def advice_window_name(now: datetime, timezone: ZoneInfo) -> str:
    hour = _aware(now, timezone).hour
    if 6 <= hour < 12:
        return "morning"
    if 12 <= hour < 19:
        return "lunch"
    return "evening"


def _is_rest_day(training: dict | None) -> bool:
    if not training:
        return True
    kind = training.get("planned_type")
    return kind in {None, "rest", "recovery"} or bool(training.get("is_all_day"))


def _session_label(training: dict | None, timezone: ZoneInfo) -> str:
    title = (training or {}).get("title") or "training"
    start = (training or {}).get("start_at")
    if start and not (training or {}).get("is_all_day"):
        clock = datetime.fromisoformat(start).astimezone(timezone).strftime("%H:%M")
        return f"{clock} {title}"
    return title


def _session_start(training: dict | None, timezone: ZoneInfo) -> datetime | None:
    start = (training or {}).get("start_at")
    if not start or (training or {}).get("is_all_day"):
        return None
    return _aware(datetime.fromisoformat(start), timezone)


def _is_generic_rest_note(note: str) -> bool:
    text = note.lower()
    return "rest" in text and any(token in text for token in ("protect", "complete rest", "rest day", "today is rest"))


def _upcoming_meetings(meetings: list[dict], now: datetime, timezone: ZoneInfo) -> list[dict]:
    upcoming: list[dict] = []
    for meeting in meetings:
        if meeting.get("is_all_day"):
            continue
        start = meeting.get("start_at")
        if not start:
            upcoming.append(meeting)
            continue
        start_at = _aware(datetime.fromisoformat(start), timezone)
        if start_at >= now:
            upcoming.append(meeting)
    return upcoming


def _period(text: str) -> str:
    return text if text.endswith((".", "!", "?")) else f"{text}."


def compose_today_advice(
    *,
    stored: str | None,
    training: dict | None,
    meetings: list[dict],
    tasks: list[dict],
    reminders: list[dict],
    tomorrow_training: dict | None,
    timezone: ZoneInfo,
    now: datetime | None = None,
) -> str:
    current = _aware(now or datetime.now(timezone), timezone)
    window = advice_window_name(current, timezone)
    weekday = current.strftime("%A")
    rest = _is_rest_day(training)
    session = _session_label(training, timezone)
    session_start = _session_start(training, timezone)
    walk = next((item for item in reminders if item.get("kind") == "walk"), None)
    extras: list[str] = []

    stored_text = (stored or "").strip()
    if stored_text and not _is_generic_rest_note(stored_text):
        extras.append(_period(stored_text))

    if window == "morning":
        if rest:
            lead = f"{weekday} is rest — keep the morning light and get the walk in before lunch."
        else:
            lead = f"{session} is the work this morning."
        if walk:
            extras.append(f"Walk first — {walk['title']}.")
        if tasks:
            extras.append(
                f"One overdue task: {tasks[0]['title']}."
                if tasks[0].get("is_overdue")
                else f"Then {tasks[0]['title']}."
            )
    elif window == "lunch":
        if rest:
            lead = "Midday check — the afternoon is still open, so walk and one useful task before evening."
        elif session_start and session_start > current:
            lead = f"Still ahead: {session}."
        else:
            lead = "Afternoon left. Finish the walk, then keep the rest of the day honest."
        if walk:
            extras.append(f"Walk is still open — {walk['title']}.")
        elif not rest:
            extras.append("Walk is done. Protect the rest of the afternoon.")
        if tasks:
            extras.append(f"Still open: {tasks[0]['title']}.")
    else:
        if rest:
            lead = "Evening — close the day clean and leave tomorrow ready."
        else:
            lead = "Evening — the session is done or done enough, so wind down."
        if walk:
            extras.append(f"Walk never finished — {walk['title']}. Do not chase it late.")
        if tasks:
            extras.append(f"Leave {tasks[0]['title']} for tomorrow if it is still open.")

    upcoming = _upcoming_meetings(meetings, current, timezone)
    if upcoming and window != "evening":
        first = upcoming[0]
        extra = f", then {len(upcoming) - 1} more" if len(upcoming) > 1 else ""
        extras.append(f"Next meeting is {first['clock']} {first['title']}{extra}.")

    kind = (tomorrow_training or {}).get("planned_type")
    title = (tomorrow_training or {}).get("title")
    if window == "evening" and tomorrow_training and kind not in {None, "rest"}:
        extras.append(f"Tomorrow is {_session_label(tomorrow_training, timezone)}. Keep tonight easy so that session is the work.")
    elif window == "evening" and kind == "rest":
        extras.append("Tomorrow is another rest day. Do not invent extra work.")
    elif window == "lunch" and tomorrow_training and kind not in {None, "rest"} and title:
        extras.append(f"Tonight, leave space for {_session_label(tomorrow_training, timezone)}.")

    return " ".join([lead, *extras[:4]])


class DailyPlanService:
    def __init__(self, timezone_name: str | None = None) -> None:
        self._timezone = ZoneInfo(timezone_name or settings.timezone)

    def build(
        self,
        day: date,
        *,
        calendar,
        training,
        wellbeing,
        notion=None,
        walking=None,
        weekly=None,
        preview_workout: str | None = None,
        now: datetime | None = None,
    ) -> dict:
        current = now or datetime.now(UTC)
        tomorrow = day + timedelta(days=1)
        calendar_status, synced_at, today_events = calendar.events_for_range(day, 1)
        _, _, tomorrow_events = calendar.events_for_range(tomorrow, 1)
        today_meetings = [
            _serialize_meeting(event, self._timezone)
            for event in today_events
            if getattr(event, "source", None) != "training"
        ]
        tomorrow_meetings = [
            _serialize_meeting(event, self._timezone)
            for event in tomorrow_events
            if getattr(event, "source", None) != "training"
        ]
        if preview_workout:
            workout = preview_workout_dict(day, preview_workout)
        else:
            workout = training.for_date(day)
        tomorrow_workout = training.for_date(tomorrow)
        check_in = wellbeing.entry(day)
        summary = wellbeing.summary(current)
        tasks: list[dict] = []
        tomorrow_tasks: list[dict] = []
        if notion is not None and hasattr(notion, "today"):
            _, _, raw_tasks = notion.today()
            tasks = [_serialize_task(item) for item in _priority_tasks(raw_tasks, day, self._timezone)]
            tomorrow_tasks = [
                _serialize_task(item)
                for item in _priority_tasks(raw_tasks, tomorrow, self._timezone, limit=3)
            ]
        today_reminders = _reminders(
            day=day, now=current, timezone=self._timezone, walking=walking, check_in=check_in,
        )
        today_block = {
            "date": day.isoformat(),
            "emphasis": _emphasis(workout, today_meetings, day, self._timezone),
            "headline": _headline("Today", workout, today_meetings, tasks, today_reminders),
            "training": workout,
            "meetings": today_meetings,
            "tasks": tasks,
            "reminders": today_reminders,
        }
        tomorrow_prep = _tomorrow_preparation(tomorrow_workout, tomorrow_meetings, tomorrow_tasks)
        overview = training.overview(current) if hasattr(training, "overview") else {}
        tomorrow_block = {
            "date": tomorrow.isoformat(),
            "emphasis": _emphasis(tomorrow_workout, tomorrow_meetings, tomorrow, self._timezone),
            "headline": tomorrow_prep,
            "training": tomorrow_workout,
            "meetings": tomorrow_meetings,
            "tasks": tomorrow_tasks,
            "reminders": [],
            "preparation": tomorrow_prep,
            "prescription": overview.get("tomorrow_prescription") if isinstance(overview, dict) else None,
            "bjj_candidates": overview.get("bjj_candidates") if isinstance(overview, dict) else [],
            "week_quality": overview.get("week_quality") if isinstance(overview, dict) else None,
        }
        sunday = None
        if weekly is not None and hasattr(weekly, "sunday_check_in"):
            check = weekly.sunday_check_in(day, training)
            if check is not None:
                sunday = {
                    "week_start": check.week_start.isoformat(),
                    "week_ending": check.week_ending.isoformat(),
                    "weight_kg": check.weight_kg,
                    "previous_weight_kg": check.previous_weight_kg,
                    "delta_kg": check.delta_kg,
                    "review_note": check.review_note,
                    "submitted": check.submitted,
                    "sessions": [
                        {
                            "date": session.date.isoformat(),
                            "kind": session.kind,
                            "title": session.title,
                            "completed": session.completed,
                            "note": session.note,
                            "exercises": [{"name": item.name, "done": item.done} for item in session.exercises],
                        }
                        for session in check.sessions
                    ],
                }
        answered = check_in.get("sober") if check_in else None
        stored_advice = check_in.get("advice") if check_in else None
        advice = compose_today_advice(
            stored=stored_advice,
            training=workout,
            meetings=today_meetings,
            tasks=tasks,
            reminders=today_reminders,
            tomorrow_training=tomorrow_workout,
            timezone=self._timezone,
            now=current,
        )
        return {
            "date": day.isoformat(),
            "timezone": self._timezone.key,
            "advice_window": advice_window_name(current, self._timezone),
            "workout": workout,
            "calendar": {
                "status": calendar_status,
                "synced_at": synced_at.isoformat() if synced_at else None,
                "meetings": today_meetings,
            },
            "sobriety": {
                "days": summary.sober_days,
                "answered": None if answered is None else ("yes" if answered else "no"),
                "note": check_in.get("daily_notes") if check_in else None,
            },
            "sleep": None,
            "sunday": sunday,
            "check_in": check_in,
            "advice": advice,
            "preview": bool(preview_workout),
            "daily_url": _daily_url(day),
            "check_in_status": {
                "morning_complete": False,
                "end_of_day_complete": bool(check_in) and check_in.get("sober") is not None,
                "last_saved_at": check_in.get("updated_at") if check_in else None,
            },
            "today": today_block,
            "tomorrow": tomorrow_block,
        }

    def set_fatigue(self, training, day: date, state: str) -> dict:
        return training.record_fatigue(day, state)

    def confirm_bjj(self, training, day: date) -> dict:
        return training.confirm_bjj(day)

    def decline_bjj(self, training, day: date) -> dict:
        return training.decline_bjj(day)

    def gym_today(self, training, day: date, workout_type: str) -> dict:
        return training.schedule_gym(day, workout_type)

    def rest_today(self, training, day: date) -> dict:
        workout = training.for_date(day)
        if workout is None:
            raise KeyError("No training session to rest today.")
        return training.replace_session(workout["id"], "rest")

    def move_gym(self, training, target_date: date, *, now: datetime | None = None) -> dict:
        overview = training.overview(now)
        gym = next(
            (
                item for item in overview.get("week", [])
                if str(item.get("planned_type", "")).startswith("strength_")
                and item.get("status") == "planned"
            ),
            None,
        )
        if gym is None:
            raise KeyError("No planned gym session this week.")
        start = datetime.combine(target_date, time(7, 30), self._timezone)
        return training.update_session(gym["id"], start_at=start)

    def complete_task(self, notion, *, task_id: str | None = None, title: str | None = None) -> dict:
        if notion is None or not hasattr(notion, "complete"):
            raise ValueError("Notion is not available.")
        resolved = task_id
        if resolved is None:
            if not title:
                raise ValueError("Provide a task id or title.")
            _, _, tasks = notion.today()
            match = next((item for item in tasks if title.lower() in item.title.lower()), None)
            if match is None:
                raise KeyError("Task not found.")
            resolved = match.id
        notion.complete(resolved)
        return {"id": resolved, "status": "done"}

    def move_meeting(
        self, calendar, training, event_id: str, start_at: datetime, end_at: datetime | None = None,
    ) -> dict:
        if not hasattr(calendar, "reschedule_event"):
            raise ValueError("Calendar cannot reschedule events.")
        event = calendar.reschedule_event(event_id, start_at, end_at)
        training.reconcile()
        return {
            "id": event.external_id,
            "title": event.title,
            "start_at": _as_utc(event.start_at).isoformat(),
            "end_at": _as_utc(event.end_at).isoformat(),
        }


def _daily_url(day: date) -> str:
    base = (settings.chili_public_url or settings.daily_briefing_base_url).rstrip("/")
    return f"{base}/daily/{day.isoformat()}"


def preview_workout_dict(day: date, workout_type: str) -> dict:
    from app.domain.training.templates import WORKOUT_TEMPLATES
    from app.domain.training.types import WorkoutType

    try:
        template = WORKOUT_TEMPLATES[WorkoutType(workout_type)]
    except (ValueError, KeyError) as error:
        raise ValueError("Workout preview not found.") from error
    start = datetime.combine(day, time(hour=7, minute=30), ZoneInfo(settings.timezone))
    return {
        "id": f"preview-{template.type.value}",
        "planned_type": template.type.value,
        "actual_type": None,
        "original_planned_type": None,
        "title": template.title,
        "status": "preview",
        "phase": "preview",
        "start_at": start.isoformat(),
        "end_at": (start + timedelta(minutes=template.estimated_minutes)).isoformat(),
        "is_all_day": False,
        "estimated_minutes": template.estimated_minutes,
        "intensity": template.intensity,
        "reason": "Dry-run preview only. Today's saved training plan is unchanged.",
        "coach_focus": [template.conditioning] if template.conditioning else [],
        "preparation": None,
        "target_rounds": None,
        "round_length_seconds": None,
        "rest_seconds": None,
        "revision": 0,
        "exercises": [
            {
                "name": item.name, "load_value": item.load_value, "load_unit": item.load_unit,
                "sets": item.sets, "reps": item.reps, "duration_seconds": item.duration_seconds,
                "notes": item.notes, "done": False,
            }
            for item in template.exercises
        ],
        "session_rpe": None,
        "final_round_quality": None,
        "notes": None,
        "calendar_event_id": None,
    }
