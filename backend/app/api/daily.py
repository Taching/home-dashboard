from __future__ import annotations

from datetime import date, datetime
import hmac
from typing import Literal

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.domain.daily_plan import DailyPlanService, preview_workout_dict
from app.domain.training.adjust import CalendarAdjuster
from app.domain.training.review import local_workout_review


daily_router = APIRouter()
_plan = DailyPlanService()


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


class PlanCommandRequest(BaseModel):
    action: Literal[
        "rest_today", "move_gym", "complete_task", "move_meeting", "replan",
        "fatigue", "confirm_bjj", "decline_bjj", "gym_today", "adjust_calendar",
    ]
    day: date | None = None
    to_date: date | None = None
    task_id: str | None = None
    task_title: str | None = None
    event_id: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    fatigue_state: Literal["normal", "tired", "very_fatigued", "pain"] | None = None
    workout_type: Literal["strength_a", "strength_b"] | None = None
    instruction: str | None = Field(default=None, max_length=2000)


def _adjuster(request: Request) -> CalendarAdjuster:
    existing = getattr(request.app.state, "calendar_adjuster", None)
    if existing is not None:
        return existing
    return CalendarAdjuster()


def _authorized(authorization: str | None) -> bool:
    token = settings.dashboard_automation_token
    if not token or not authorization or not authorization.startswith("Bearer "):
        return False
    provided = authorization.removeprefix("Bearer ").strip()
    return bool(provided) and hmac.compare_digest(provided, token)


def _daily_url(day: date) -> str:
    base = (settings.chili_public_url or settings.daily_briefing_base_url).rstrip("/")
    return f"{base}/daily/{day.isoformat()}"


def _briefing(request: Request, day: date, preview_workout: str | None = None) -> dict:
    if preview_workout:
        try:
            preview_workout_dict(day, preview_workout)
        except ValueError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error
    return _plan.build(
        day,
        calendar=request.app.state.calendar_bridge_service,
        training=request.app.state.training_service,
        wellbeing=request.app.state.wellbeing_service,
        notion=getattr(request.app.state, "notion_service", None),
        walking=getattr(request.app.state, "walkingpad_service", None),
        weekly=getattr(request.app.state, "weekly_service", None),
        preview_workout=preview_workout,
    )


def review_logged_workout(
    request: Request,
    day: date,
    *,
    kind: str | None,
    note: str | None,
    exercises: list[dict] | None,
    session: dict | None,
) -> str:
    training = getattr(request.app.state, "training_service", None)
    overview = training.overview() if training is not None and hasattr(training, "overview") else {}
    advice = local_workout_review(
        session=session, kind=kind, note=note, overview=overview,
    )
    wellbeing = getattr(request.app.state, "wellbeing_service", None)
    if wellbeing is not None:
        wellbeing.store_advice(day, advice)
    session_id = (session or {}).get("id") or day.isoformat()
    _notify_chili(request, f"{_daily_url(day)}\n\n{advice}", f"workout-review:{session_id}")
    return advice


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


@daily_router.get("/plan/{day}")
def daily_plan(
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
    exercises = [{"name": item.name, "done": item.done} for item in body.exercises]
    advice = review_logged_workout(
        request, day, kind=body.kind or updated.get("planned_type"),
        note=body.note, exercises=exercises, session=updated,
    )
    briefing = _briefing(request, day)
    briefing["advice"] = advice
    return {
        "status": "logged",
        "message": f"Logged {updated['title']}: {updated['status']}.",
        "workout": updated,
        "advice": advice,
        "briefing": briefing,
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
    payload = _briefing(request, day)
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


@daily_router.post("/automation/plan")
def automation_plan(
    request: Request,
    body: PlanCommandRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="Invalid automation token.")
    training = request.app.state.training_service
    calendar = request.app.state.calendar_bridge_service
    notion = getattr(request.app.state, "notion_service", None)
    today = body.day or datetime.now().astimezone(_plan._timezone).date()
    try:
        if body.action == "rest_today":
            result = _plan.rest_today(training, today)
        elif body.action == "move_gym":
            if body.to_date is None:
                raise HTTPException(status_code=400, detail="to_date is required to move gym.")
            result = _plan.move_gym(training, body.to_date)
        elif body.action == "complete_task":
            result = _plan.complete_task(notion, task_id=body.task_id, title=body.task_title)
        elif body.action == "move_meeting":
            if not body.event_id or body.start_at is None:
                raise HTTPException(status_code=400, detail="event_id and start_at are required.")
            result = _plan.move_meeting(calendar, training, body.event_id, body.start_at, body.end_at)
        elif body.action == "fatigue":
            if body.fatigue_state is None:
                raise HTTPException(status_code=400, detail="fatigue_state is required.")
            result = _plan.set_fatigue(training, today, body.fatigue_state)
        elif body.action == "confirm_bjj":
            result = _plan.confirm_bjj(training, today)
        elif body.action == "decline_bjj":
            result = _plan.decline_bjj(training, today)
        elif body.action == "gym_today":
            if body.workout_type is None:
                raise HTTPException(status_code=400, detail="workout_type is required for gym today.")
            result = _plan.gym_today(training, today, body.workout_type)
        elif body.action == "adjust_calendar":
            if not body.instruction:
                raise HTTPException(status_code=400, detail="instruction is required to adjust the calendar.")
            result = _adjuster(request).adjust(
                body.instruction,
                training=training,
                calendar=calendar,
                notion=notion,
                notion_sync=getattr(request.app.state, "training_notion_sync", None),
            )
            message = result.get("notification") if isinstance(result, dict) else None
            if message:
                dedupe = (result.get("decision") or {}).get("id") or f"training:adjust:{today.isoformat()}"
                _notify_chili(request, str(message), str(dedupe))
        else:
            training.reconcile()
            result = {"status": "replanned"}
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "status": "ok",
        "action": body.action,
        "result": result,
        "plan": _briefing(request, today),
    }
