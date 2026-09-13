from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.domain.training.templates import WORKOUT_TEMPLATES
from app.domain.training.types import WorkoutType


daily_router = APIRouter()


class DailyCheckInRequest(BaseModel):
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    fatigue: int | None = Field(default=None, ge=1, le=5)
    soreness: int | None = Field(default=None, ge=1, le=5)
    grip_fatigue: int | None = Field(default=None, ge=1, le=5)
    pain: bool | None = None
    pain_notes: str | None = Field(default=None, max_length=500)
    readiness: int | None = Field(default=None, ge=1, le=5)
    weight_kg: float | None = Field(default=None, ge=30, le=300)
    workout_status: Literal["completed", "partial", "skipped"] | None = None
    sober: bool | None = None
    notes: str | None = Field(default=None, max_length=1500)


class DailyExerciseDone(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    done: bool = False


class DailyWorkoutRequest(BaseModel):
    kind: str | None = None
    exercises: list[DailyExerciseDone] = Field(default_factory=list)
    note: str | None = Field(default=None, max_length=500)


class DailySoberRequest(BaseModel):
    sober: bool
    note: str | None = Field(default=None, max_length=500)


class DailySundayRequest(BaseModel):
    weight_kg: float | None = Field(default=None, ge=30, le=250)
    same_as_last: bool = False
    note: str | None = Field(default=None, max_length=500)


def _daily_url(day: date) -> str:
    base = (settings.chili_public_url or settings.daily_briefing_base_url).rstrip("/")
    return f"{base}/daily/{day.isoformat()}"


def _preview_workout(day: date, workout_type: str) -> dict:
    try:
        template = WORKOUT_TEMPLATES[WorkoutType(workout_type)]
    except (ValueError, KeyError) as error:
        raise HTTPException(status_code=404, detail="Workout preview not found.") from error
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


def _sunday_payload(request: Request, day: date) -> dict | None:
    weekly = getattr(request.app.state, "weekly_service", None)
    if weekly is None:
        return None
    check_in = weekly.sunday_check_in(day, request.app.state.training_service)
    if check_in is None:
        return None
    return {
        "week_start": check_in.week_start.isoformat(),
        "week_ending": check_in.week_ending.isoformat(),
        "weight_kg": check_in.weight_kg,
        "previous_weight_kg": check_in.previous_weight_kg,
        "delta_kg": check_in.delta_kg,
        "review_note": check_in.review_note,
        "submitted": check_in.submitted,
        "sessions": [
            {
                "date": session.date.isoformat(),
                "kind": session.kind,
                "title": session.title,
                "completed": session.completed,
                "note": session.note,
                "exercises": [{"name": item.name, "done": item.done} for item in session.exercises],
            }
            for session in check_in.sessions
        ],
    }


def _briefing(request: Request, day: date, preview_workout: str | None = None) -> dict:
    calendar = request.app.state.calendar_bridge_service
    calendar_status, synced_at, events = calendar.events_for_range(day, 1)
    meetings = [
        {
            "id": event.external_id,
            "title": event.title,
            "start_at": event.start_at.isoformat(),
            "end_at": event.end_at.isoformat(),
            "is_all_day": event.is_all_day,
        }
        for event in events
        if getattr(event, "source", None) != "training"
    ]
    wellbeing_service = request.app.state.wellbeing_service
    check_in = wellbeing_service.entry(day)
    wellbeing = wellbeing_service.summary()
    workout = (
        _preview_workout(day, preview_workout)
        if preview_workout
        else request.app.state.training_service.for_date(day)
    )
    answered = check_in.get("sober") if check_in else None
    return {
        "date": day.isoformat(),
        "timezone": settings.timezone,
        "workout": workout,
        "calendar": {
            "status": calendar_status,
            "synced_at": synced_at.isoformat() if synced_at else None,
            "meetings": meetings,
        },
        "sobriety": {
            "days": wellbeing.sober_days,
            "answered": None if answered is None else ("yes" if answered else "no"),
            "note": check_in.get("daily_notes") if check_in else None,
        },
        "sleep": None,
        "sunday": _sunday_payload(request, day),
        "check_in": check_in,
        "advice": check_in.get("advice") if check_in else None,
        "preview": bool(preview_workout),
        "daily_url": _daily_url(day),
        "check_in_status": {
            "morning_complete": False,
            "end_of_day_complete": bool(check_in) and check_in.get("sober") is not None,
            "last_saved_at": check_in.get("updated_at") if check_in else None,
        },
    }


def _ask_chili(request: Request, prompt: str) -> str | None:
    openclaw = getattr(request.app.state, "openclaw_service", None)
    if openclaw is None or not openclaw.configured():
        return None
    try:
        result = openclaw.send(prompt)
    except Exception:
        return None
    if isinstance(result, dict):
        return result.get("reply")
    return None


def _notify_chili(request: Request, message: str, dedupe_key: str) -> None:
    openclaw = getattr(request.app.state, "openclaw_service", None)
    notify_service = getattr(request.app.state, "chili_notify_service", None)
    if openclaw is None or notify_service is None or not openclaw.configured():
        return
    if not notify_service.should_send(dedupe_key):
        return
    try:
        notify = getattr(openclaw, "notify_user", None)
        result = notify(message) if callable(notify) else openclaw.send(message)
        delivery = result.get("delivery_status") if isinstance(result, dict) else None
        if delivery not in {None, "sent", "delivered", "ok"}:
            raise RuntimeError(f"OpenClaw delivery was {delivery}")
        notify_service.mark_sent(dedupe_key)
    except Exception:
        notify_service.release(dedupe_key)


@daily_router.get("/daily/{day}")
def daily_briefing(
    request: Request, day: date,
    preview: str | None = Query(default=None, description="Optional dry-run workout template"),
) -> dict:
    return _briefing(request, day, preview)


@daily_router.post("/daily/{day}/workout")
def daily_workout(request: Request, day: date, body: DailyWorkoutRequest) -> dict:
    workout = request.app.state.training_service.for_date(day)
    if workout is None or workout.get("planned_type") == "rest" or workout.get("status") == "preview":
        raise HTTPException(status_code=400, detail="There is no workout to log for this date.")
    try:
        updated = request.app.state.training_service.log_workout_check(
            workout["id"],
            exercises=[{"name": item.name, "done": item.done} for item in body.exercises],
            note=body.note,
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Training session not found.") from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "status": "logged",
        "message": f"Logged {updated['title']}: {updated['status']}.",
        "workout": updated,
        "briefing": _briefing(request, day),
    }


@daily_router.post("/daily/{day}/sober")
def daily_sober(request: Request, day: date, body: DailySoberRequest) -> dict:
    request.app.state.wellbeing_service.record(
        day,
        sober=body.sober,
        daily_notes=body.note,
        source="daily-page",
    )
    briefing = _briefing(request, day)
    return {
        "status": "logged",
        "message": f"Logged sober: {'yes' if body.sober else 'no'}.",
        "briefing": briefing,
    }


@daily_router.post("/daily/{day}/sunday")
def daily_sunday(request: Request, day: date, body: DailySundayRequest) -> dict:
    weekly = request.app.state.weekly_service
    try:
        saved = weekly.save_sunday(
            day,
            request.app.state.training_service,
            weight_kg=body.weight_kg,
            same_as_last=body.same_as_last,
            note=body.note,
            source="ui",
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    request.app.state.wellbeing_service.record(
        day,
        weight_kg=saved.check_in.weight_kg,
        daily_notes=body.note,
        source="daily-page",
    )
    _notify_chili(request, saved.notify_message, f"sunday-saved-{day.isoformat()}")
    advice = _ask_chili(request, saved.review_prompt)
    if advice:
        request.app.state.wellbeing_service.store_advice(day, advice)
    payload = _briefing(request, day)
    payload["advice"] = advice or payload.get("advice")
    payload["message"] = saved.notify_message
    return payload


@daily_router.post("/daily/{day}/check-in")
def daily_check_in(request: Request, day: date, body: DailyCheckInRequest) -> dict:
    provided = body.model_dump(exclude_none=True)
    if not provided:
        raise HTTPException(status_code=400, detail="Answer at least one field before submitting.")

    workout_status = provided.pop("workout_status", None)
    notes = provided.pop("notes", None)
    if notes is not None:
        provided["daily_notes"] = notes

    current = _briefing(request, day)
    if workout_status is not None:
        workout = current.get("workout")
        if workout is None or workout.get("planned_type") == "rest":
            raise HTTPException(status_code=400, detail="There is no workout to update for this date.")
        request.app.state.training_service.update_session(workout["id"], status=workout_status)
    if provided:
        request.app.state.wellbeing_service.record(day, **provided, source="daily-page")
    request.app.state.training_service.reconcile()
    return _briefing(request, day)
