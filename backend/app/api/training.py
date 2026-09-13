from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import hmac
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.domain.training.templates import WORKOUT_TEMPLATES
from app.domain.training.types import WorkoutType

training_router = APIRouter()


class ReadinessRequest(BaseModel):
    date: date
    sleep_hours: float = Field(ge=0, le=24)
    sleep_quality: int = Field(ge=1, le=5)
    fatigue: int = Field(ge=1, le=5)
    soreness: int = Field(ge=1, le=5)
    grip_fatigue: int = Field(ge=1, le=5)
    pain: bool
    pain_notes: str | None = Field(default=None, max_length=500)
    readiness: int = Field(ge=1, le=5)
    weight_kg: float | None = Field(default=None, ge=30, le=300)


class TrainingMetricRequest(BaseModel):
    metric_type: str = Field(min_length=1, max_length=40)
    sequence: int | None = Field(default=None, ge=1, le=100)
    value: float
    unit: str = Field(min_length=1, max_length=20)


class SessionUpdateRequest(BaseModel):
    status: Literal["planned", "in_progress", "completed", "partial", "skipped"] | None = None
    actual_type: str | None = None
    start_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=3000)
    session_rpe: float | None = Field(default=None, ge=1, le=10)
    final_round_quality: int | None = Field(default=None, ge=1, le=5)
    metrics: list[TrainingMetricRequest] | None = None


class ReplaceSessionRequest(BaseModel):
    workout_type: str


class AddBjjRequest(BaseModel):
    start_at: datetime
    hard: bool = False


class AutomationRunRequest(BaseModel):
    action: Literal["morning", "evening", "dispatch"]


def _authorized(authorization: str | None) -> bool:
    token = settings.dashboard_automation_token
    if not token or not authorization or not authorization.startswith("Bearer "):
        return False
    provided = authorization.removeprefix("Bearer ").strip()
    return bool(provided) and hmac.compare_digest(provided, token)


def _require_auth(authorization: str | None) -> None:
    if not _authorized(authorization):
        raise HTTPException(status_code=401, detail="Invalid automation token.")


def _daily_briefing_url(day: date) -> str:
    base = (settings.chili_public_url or settings.daily_briefing_base_url).rstrip("/")
    return f"{base}/daily/{day.isoformat()}"


@training_router.get("/training/overview")
async def training_overview(request: Request) -> dict:
    return request.app.state.training_service.overview()


@training_router.get("/training/templates/{workout_type}")
async def training_template(workout_type: str) -> dict:
    try:
        template = WORKOUT_TEMPLATES[WorkoutType(workout_type)]
    except (ValueError, KeyError) as error:
        raise HTTPException(status_code=404, detail="Training template not found.") from error
    return {
        "type": template.type.value,
        "title": template.title,
        "estimated_minutes": template.estimated_minutes,
        "intensity": template.intensity,
        "conditioning": template.conditioning,
        "exercises": [
            {
                "name": item.name,
                "load_value": item.load_value,
                "load_unit": item.load_unit,
                "sets": item.sets,
                "reps": item.reps,
                "duration_seconds": item.duration_seconds,
                "notes": item.notes,
            }
            for item in template.exercises
        ],
    }


@training_router.get("/training/sessions/{session_id}")
async def training_session(request: Request, session_id: str) -> dict:
    result = request.app.state.training_service.session(session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Training session not found.")
    return result


@training_router.post("/automation/training/readiness")
async def record_training_readiness(
    request: Request, body: ReadinessRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    return request.app.state.training_service.record_readiness(body.date, body.model_dump(exclude={"date"}))


@training_router.patch("/automation/training/sessions/{session_id}")
async def update_training_session(
    request: Request, session_id: str, body: SessionUpdateRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    if not body.model_fields_set:
        raise HTTPException(status_code=400, detail="Provide at least one session update.")
    try:
        return request.app.state.training_service.update_session(
            session_id,
            status=body.status,
            actual_type=body.actual_type,
            start_at=body.start_at,
            notes=body.notes,
            session_rpe=body.session_rpe,
            final_round_quality=body.final_round_quality,
            metrics=[item.model_dump() for item in body.metrics] if body.metrics is not None else None,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Training session not found.") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@training_router.post("/automation/training/sessions/{session_id}/replace")
async def replace_training_session(
    request: Request, session_id: str, body: ReplaceSessionRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    try:
        return request.app.state.training_service.replace_session(session_id, body.workout_type)
    except KeyError:
        raise HTTPException(status_code=404, detail="Training session not found.") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@training_router.post("/automation/training/bjj")
async def add_training_bjj(
    request: Request, body: AddBjjRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    if body.start_at.tzinfo is None:
        raise HTTPException(status_code=400, detail="start_at must include a timezone offset.")
    return request.app.state.training_service.add_bjj(body.start_at, hard=body.hard)


@training_router.post("/automation/training/replan")
async def replan_training(
    request: Request, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    request.app.state.training_service.reconcile()
    return request.app.state.training_service.overview()


@training_router.post("/automation/training/run")
async def run_training_automation(
    request: Request, body: AutomationRunRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    now = datetime.now(UTC)
    local_today = now.astimezone(request.app.state.training_service._timezone).date()
    if body.action == "morning":
        message = f"{_daily_briefing_url(local_today)}\n\nToday's briefing is ready."
        return _send_once(request, message, f"daily:briefing:{local_today.isoformat()}")
    if body.action == "evening":
        request.app.state.training_service.reconcile(now)
        tomorrow = request.app.state.training_service.overview(now).get("tomorrow")
        message = _tomorrow_message(tomorrow)
        return _send_once(request, message, f"training:evening:{(local_today + timedelta(days=1)).isoformat()}:{tomorrow.get('revision') if tomorrow else 0}")
    sent = 0
    for reminder, session in request.app.state.training_service.due_reminders(now):
        message = _reminder_message(reminder.kind, session)
        result = _send_once(request, message, reminder.dedupe_key)
        if result["status"] in {"sent", "skipped"}:
            request.app.state.training_service.mark_reminder_sent(reminder.id, now)
            sent += result["status"] == "sent"
    return {"status": "ok", "sent": sent}


def _send_once(request: Request, message: str, dedupe_key: str) -> dict:
    openclaw = request.app.state.openclaw_service
    if not openclaw.configured():
        return {"status": "not_configured"}
    notify = request.app.state.chili_notify_service
    if not notify.should_send(dedupe_key):
        return {"status": "skipped"}
    try:
        notify_user = getattr(openclaw, "notify_user", None)
        result = notify_user(message) if callable(notify_user) else openclaw.send(message)
        delivery = result.get("delivery_status") if isinstance(result, dict) else None
        if delivery not in {None, "sent", "delivered", "ok", "accepted"}:
            raise RuntimeError(f"OpenClaw delivery was {delivery}")
        notify.mark_sent(dedupe_key)
        return {"status": "sent"}
    except Exception as error:
        notify.release(dedupe_key)
        return {"status": "failed", "message": str(error)}


def _tomorrow_message(session: dict | None) -> str:
    if session is None:
        return "Tomorrow: no training is prescribed. Protect recovery and do not fill the space automatically."
    lines = [f"Tomorrow: {session['title']}.", f"Why: {session['reason']}"]
    if session.get("coach_focus"):
        lines.append("Focus: " + " ".join(session["coach_focus"][:2]))
    if session.get("target_rounds"):
        lines.append(f"Goal: {session['target_rounds']} × 5-minute rounds, about {int((session.get('rest_seconds') or 120) / 60)} minutes rest.")
    if session.get("preparation"):
        lines.append("Prepare: " + session["preparation"])
    return "\n".join(lines)


def _reminder_message(kind: str, session: dict) -> str:
    if kind == "post_workout":
        day = datetime.fromisoformat(session["start_at"]).astimezone(ZoneInfo(settings.timezone)).date()
        return f"{_daily_briefing_url(day)}\n\nLog today's workout when you are done."
    exercises = []
    for item in session.get("exercises", [])[:7]:
        detail = " × ".join(str(value) for value in (item.get("load_value"), item.get("sets"), item.get("reps")) if value is not None)
        exercises.append(f"{item['name']}{': ' + detail if detail else ''}")
    return f"{session['title']} in 60 minutes.\n" + "\n".join(exercises) + "\nTarget: finish with energy left."
