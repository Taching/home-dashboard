from __future__ import annotations

import asyncio
from datetime import UTC, date, datetime, timedelta
import hmac
import logging
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.domain.daily_plan import _is_rest_day
from app.domain.garmin import recovery_hint, watch_line
from app.domain.telegram_text import telegram_message
from app.domain.training.adjust import CalendarAdjuster
from app.domain.training.coach import EveningCoach
from app.domain.training.review import local_workout_review, workout_review_prompt
from app.domain.training.templates import WORKOUT_TEMPLATES
from app.domain.training.types import WorkoutType

training_router = APIRouter()
logger = logging.getLogger(__name__)


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
    miss_reason: str | None = Field(default=None, max_length=32)
    metrics: list[TrainingMetricRequest] | None = None


class SessionResultRequest(BaseModel):
    status: Literal["planned", "in_progress", "completed", "partial", "skipped"] | None = None
    miss_reason: str | None = Field(default=None, max_length=32)
    session_rpe: float | None = Field(default=None, ge=1, le=10)
    difficulty: int | None = Field(default=None, ge=1, le=10)
    fatigue: str | None = None
    pain: bool | None = None
    soreness: str | None = None
    notes: str | None = Field(default=None, max_length=3000)
    bjj_rounds: int | None = Field(default=None, ge=0, le=20)
    perceived_intensity: str | None = None
    cardio: str | None = None
    grip_fatigue: str | None = None
    technical_performance: str | None = None
    recovery_activity: str | None = None
    exercises: list[dict] | None = None


class GymClosureRequest(BaseModel):
    date: date
    gym_id: str = "mita"
    closure_type: Literal["HOLIDAY", "NO_CLASS", "CLOSED"] = "HOLIDAY"
    note: str | None = Field(default=None, max_length=500)


class UnavailabilityRequest(BaseModel):
    date: date
    reason: str = "USER_CANCELLED"
    note: str | None = Field(default=None, max_length=500)


class ClassExceptionRequest(BaseModel):
    day: date | None = None
    unavailable: bool = True
    template: list[dict] | None = None
    note: str | None = Field(default=None, max_length=500)


class ReplaceSessionRequest(BaseModel):
    workout_type: str


class AddBjjRequest(BaseModel):
    start_at: datetime
    hard: bool = False


class FatigueRequest(BaseModel):
    date: date
    state: Literal["normal", "tired", "very_fatigued", "pain"]


class BjjDayRequest(BaseModel):
    date: date
    hard: bool | None = None


class GymDayRequest(BaseModel):
    date: date
    workout_type: Literal["strength_a", "strength_b"]


class AdjustCalendarRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


class ReplanRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


class TrainingPreferencesRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


# M2: Exercise-level logging request models
class ExerciseLogItem(BaseModel):
    """Single exercise log entry for structured workout logging."""
    sort_order: int = Field(ge=0, le=20)
    planned_exercise_name: str = Field(min_length=1, max_length=120)
    planned_exercise_slug: str | None = Field(default=None, max_length=80)
    performed_exercise_name: str | None = Field(default=None, max_length=120)
    performed_exercise_slug: str | None = Field(default=None, max_length=80)
    planned_sets: int | None = Field(default=None, ge=1, le=20)
    reps_per_set: list[int] | None = Field(default=None, max_length=20)
    load_kg: float | None = Field(default=None, ge=0, le=500)
    load_per_side: bool = False
    load_note: str | None = Field(default=None, max_length=100)
    rpe: float | None = Field(default=None, ge=1, le=10)
    technique_quality: Literal["good", "shaky", "breakdown"] | None = None
    pain_flag: bool = False
    status: Literal["completed", "partial", "skipped"] = "completed"
    substitution_reason: str | None = Field(default=None, max_length=200)
    notes: str | None = Field(default=None, max_length=500)


class ExerciseResultsRequest(BaseModel):
    """Request to log structured exercise results for a session."""
    exercises: list[ExerciseLogItem] = Field(min_length=1, max_length=20)


class BjjAnalysisRequest(BaseModel):
    """Request to log BJJ session analysis."""
    main_focus: str | None = Field(default=None, max_length=200)
    problem_position: str | None = Field(default=None, max_length=100)
    key_failure_text: str | None = Field(default=None, max_length=500)
    technique_practiced: str | None = Field(default=None, max_length=200)
    success_count: int | None = Field(default=None, ge=0, le=100)
    attempt_count: int | None = Field(default=None, ge=0, le=100)
    primary_failure_code: str | None = Field(default=None, max_length=32)
    additional_failure_codes: list[str] | None = Field(default=None, max_length=5)
    failure_notes: dict[str, str] | None = None


class RainActionRequest(BaseModel):
    """Request to handle a rain warning action."""
    action: Literal["move_session", "use_home_fallback", "keep_original_plan"]
    move_to_date: date | None = None


class CancellationRequest(BaseModel):
    """Request to set a session cancellation reason."""
    reason: Literal[
        "weather_blocked", "pain", "illness", 
        "schedule_conflict", "user_cancelled", "other"
    ]
    replacement_session_id: str | None = None



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
    return f"{settings.public_base_url()}/daily/{day.isoformat()}"


@training_router.get("/training/lifts")
async def training_lifts(request: Request) -> dict:
    """Every logged session per lift with estimated 1RM and PR flags. Read-only."""
    service = getattr(request.app.state, "lift_history_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Lift history not configured.")
    return await asyncio.to_thread(service.lifts)


@training_router.get("/training/overview")
async def training_overview(request: Request) -> dict:
    return request.app.state.training_service.overview()


@training_router.get("/training/preferences")
async def get_training_preferences(request: Request) -> dict:
    return request.app.state.training_preferences_service.get()


@training_router.put("/training/preferences")
async def put_training_preferences(request: Request, body: TrainingPreferencesRequest) -> dict:
    return request.app.state.training_preferences_service.save(body.notes)


@training_router.get("/training/weeks/{week_start}/review")
async def training_week_review(request: Request, week_start: date) -> dict:
    return request.app.state.training_service.week_review(week_start)


@training_router.post("/training/weeks/{week_start}/review")
async def run_training_week_review(request: Request, week_start: date) -> dict:
    return request.app.state.training_service.run_weekly_analysis(week_start)


@training_router.post("/training/sessions/{session_id}/result")
async def log_training_session_result(request: Request, session_id: str, body: SessionResultRequest) -> dict:
    try:
        return request.app.state.training_service.log_session_result(session_id, **body.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(status_code=404, detail="Training session not found.") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@training_router.post("/training/sessions/{session_id}/coach")
async def coach_review_session(request: Request, session_id: str) -> dict:
    training = request.app.state.training_service
    session = training.session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found.")
    result = session.get("result") or {}
    if not result:
        raise HTTPException(status_code=400, detail="Log this session before asking the coach.")

    overview = training.overview()
    preferences = getattr(request.app.state, "training_preferences_service", None)
    prefs_text = preferences.prompt_snippet() if preferences else ""

    prompt = workout_review_prompt(
        session=session,
        kind=session.get("planned_type"),
        note=result.get("notes"),
        exercises=session.get("exercises") or [],
        overview=overview,
    )
    if prefs_text:
        prompt = f"{prompt}\n\n{prefs_text}"

    openclaw = getattr(request.app.state, "openclaw_service", None)
    if openclaw is not None and openclaw.configured():
        try:
            reply = openclaw.send(prompt).get("reply")
            if reply:
                return {"advice": str(reply).strip(), "source": "openclaw"}
        except Exception:
            logger.exception("Coach review via OpenClaw failed; falling back to local review")

    advice = local_workout_review(
        session=session, kind=session.get("planned_type"), note=result.get("notes"), overview=overview,
    )
    return {"advice": advice, "source": "local"}


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
            miss_reason=body.miss_reason,
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


@training_router.post("/automation/training/fatigue")
async def record_training_fatigue(
    request: Request, body: FatigueRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    try:
        return request.app.state.training_service.record_fatigue(body.date, body.state)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@training_router.post("/automation/training/gym-closures")
async def add_gym_closure(
    request: Request, body: GymClosureRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    return request.app.state.training_service.add_gym_closure(
        body.date, gym_id=body.gym_id, closure_type=body.closure_type, note=body.note,
    )


@training_router.post("/automation/training/unavailability")
async def add_unavailability(
    request: Request, body: UnavailabilityRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    return request.app.state.training_service.add_unavailability(body.date, reason=body.reason, note=body.note)


@training_router.post("/automation/training/classes")
async def update_training_classes(
    request: Request, body: ClassExceptionRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    if body.template is not None:
        return request.app.state.training_service.update_class_template(body.template)
    if body.day is None:
        raise HTTPException(status_code=400, detail="Provide a date or a class template.")
    if body.unavailable:
        return request.app.state.training_service.mark_no_class(body.day, note=body.note)
    raise HTTPException(status_code=400, detail="Class updates need unavailable=true or a template.")


@training_router.post("/automation/training/bjj/confirm")
async def confirm_training_bjj(
    request: Request, body: BjjDayRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    return request.app.state.training_service.confirm_bjj(body.date, hard=body.hard)


@training_router.post("/automation/training/bjj/decline")
async def decline_training_bjj(
    request: Request, body: BjjDayRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    return request.app.state.training_service.decline_bjj(body.date)


@training_router.post("/automation/training/gym")
async def schedule_training_gym(
    request: Request, body: GymDayRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    try:
        return request.app.state.training_service.schedule_gym(body.date, body.workout_type)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@training_router.post("/automation/training/adjust")
async def adjust_training_calendar(
    request: Request, body: AdjustCalendarRequest, authorization: str | None = Header(default=None),
) -> dict:
    _require_auth(authorization)
    adjuster = getattr(request.app.state, "calendar_adjuster", None) or CalendarAdjuster()
    try:
        result = adjuster.adjust(
            body.instruction,
            training=request.app.state.training_service,
            calendar=getattr(request.app.state, "calendar_bridge_service", None),
            notion=getattr(request.app.state, "notion_service", None),
            notion_sync=getattr(request.app.state, "training_notion_sync", None),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    decision = result.get("decision") if isinstance(result, dict) else None
    message = result.get("notification") if isinstance(result, dict) else None
    if message:
        dedupe = (decision or {}).get("id") or f"training:adjust:{body.instruction[:40]}"
        result["notify"] = _send_once(request, str(message), str(dedupe))
    return result


@training_router.post("/training/replan")
async def request_schedule_change(request: Request, body: ReplanRequest) -> dict:
    adjuster = getattr(request.app.state, "calendar_adjuster", None) or CalendarAdjuster()
    preferences = getattr(request.app.state, "training_preferences_service", None)
    prefs_text = preferences.prompt_snippet() if preferences else ""
    instruction = f"{body.instruction}\n\n{prefs_text}" if prefs_text else body.instruction
    try:
        result = adjuster.adjust(
            instruction,
            training=request.app.state.training_service,
            calendar=getattr(request.app.state, "calendar_bridge_service", None),
            notion=getattr(request.app.state, "notion_service", None),
            notion_sync=getattr(request.app.state, "training_notion_sync", None),
        )
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error) or "Could not understand that. Try describing it in plainer words.",
        ) from error
    decision = result.get("decision") if isinstance(result, dict) else None
    message = result.get("notification") if isinstance(result, dict) else None
    if message:
        dedupe = (decision or {}).get("id") or f"training:replan-request:{body.instruction[:40]}"
        result["notify"] = _send_once(request, str(message), str(dedupe))
    return result


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
        message = await _morning_message(request, local_today)
        return _send_once(request, message, f"daily:briefing:{local_today.isoformat()}")
    if body.action == "evening":
        coach = getattr(request.app.state, "evening_coach", None) or EveningCoach()
        review = coach.review(
            request.app.state.training_service,
            calendar=getattr(request.app.state, "calendar_bridge_service", None),
            notion=getattr(request.app.state, "notion_service", None),
            notion_sync=getattr(request.app.state, "training_notion_sync", None),
            now=now,
        )
        message = review.get("notification") or _tomorrow_message(
            (review.get("overview") or {}).get("tomorrow"),
            (review.get("overview") or {}).get("tomorrow_prescription"),
        )
        notify = _send_once(request, str(message), str((review.get("decision") or {}).get("id") or f"training:evening:{local_today.isoformat()}"))
        review["notify"] = notify
        return review
    sent = 0
    for reminder, session in request.app.state.training_service.due_reminders(now):
        message = _reminder_message(reminder.kind, session, request=request)
        result = _send_once(request, message, reminder.dedupe_key)
        if result["status"] in {"sent", "skipped"}:
            request.app.state.training_service.mark_reminder_sent(reminder.id, now)
            sent += result["status"] == "sent"
    wellbeing = getattr(request.app.state, "wellbeing_service", None)
    if wellbeing is not None:
        for nudge in wellbeing.sober_nudges(now):
            result = _send_once(request, nudge.message, nudge.dedupe_key)
            if result["status"] == "sent":
                sent += 1
    return {"status": "ok", "sent": sent}


async def _morning_message(request: Request, day: date) -> str:
    lines = ["Today's briefing is ready."]
    garmin = getattr(request.app.state, "garmin_service", None)
    if garmin is not None and garmin.configured():
        # One fresh pull so last night's sleep is in, even between 30-min polls.
        try:
            await asyncio.to_thread(garmin.sync_day, day)
        except Exception:
            logger.warning("Morning Garmin sync failed: %s", garmin.last_error)
        snapshot = garmin.snapshot(day)
        line = watch_line(snapshot)
        if line:
            lines.append(line)
            rest = _is_rest_day(request.app.state.training_service.for_date(day))
            hint = recovery_hint(snapshot, rest_day=rest)
            if hint:
                lines.append(hint)
    return telegram_message("\n".join(lines), _daily_briefing_url(day))


def _send_once(request: Request, message: str, dedupe_key: str) -> dict:
    openclaw = getattr(request.app.state, "openclaw_service", None)
    if openclaw is None or not openclaw.configured():
        return {"status": "not_configured"}
    notify = getattr(request.app.state, "chili_notify_service", None)
    if notify is None:
        return {"status": "not_configured"}
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
        logger.exception("Training notify failed for %s", dedupe_key)
        return {"status": "failed", "message": str(error)}


def _tomorrow_message(session: dict | None, prescription: dict | None = None) -> str:
    if prescription:
        status = prescription.get("weekly_status") or {}
        counters = " · ".join(
            f"{key.replace('_', ' ').title()} {item.get('completed', 0)}/{item.get('target', 0)}"
            for key, item in status.items()
        )
        lines = [
            f"Tomorrow: {prescription.get('session', 'rest')}.",
            f"Time: {prescription.get('time') or 'unscheduled'}",
            f"Work: {prescription.get('work')}",
            f"Focus: {prescription.get('focus')}",
            f"Why: {prescription.get('why')}",
        ]
        if counters:
            lines.append(counters)
        return "\n".join(lines)
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


def _reminder_message(kind: str, session: dict, *, request: Request | None = None) -> str:
    if kind == "post_workout":
        day = datetime.fromisoformat(session["start_at"]).astimezone(ZoneInfo(settings.timezone)).date()
        return telegram_message("Log today's workout when you are done.", _daily_briefing_url(day))
    exercises = []
    for item in session.get("exercises", [])[:7]:
        detail = " × ".join(str(value) for value in (item.get("load_value"), item.get("sets"), item.get("reps")) if value is not None)
        exercises.append(f"{item['name']}{': ' + detail if detail else ''}")
    message = f"{session['title']} in 60 minutes.\n" + "\n".join(exercises) + "\nTarget: finish with energy left."
    # Spec 10.5 / 15: append three-action rain warning to existing pre-workout flow.
    if request is not None and session.get("requires_travel"):
        rain_line = _rain_warning_for_session(request, session)
        if rain_line:
            message = f"{message}\n\n{rain_line}"
    return message


def _rain_warning_for_session(request: Request, session: dict) -> str | None:
    weather_service = getattr(request.app.state, "weather_service", None)
    if weather_service is None or not weather_service.configured():
        return None
    from app.domain.rain_handling import assess_rain_risk, build_rain_prompt, format_rain_warning

    session_start = datetime.fromisoformat(session["start_at"])
    assessment = assess_rain_risk(
        session_start,
        weather_service.travel_conditions(),
        departure_buffer_minutes=30,
    )
    if not assessment.at_risk:
        return None
    # Mark that the athlete was prompted (does not cancel the session).
    logging_service = getattr(request.app.state, "workout_logging_service", None)
    if logging_service is not None and hasattr(logging_service, "set_rain_prompted"):
        try:
            logging_service.set_rain_prompted(session["id"])
        except Exception:  # noqa: BLE001
            logger.exception("Could not mark rain_prompted_at for %s", session.get("id"))
    prompt = build_rain_prompt(
        session["id"],
        session.get("title") or "Session",
        session_start,
        assessment,
    )
    return format_rain_warning(prompt)


# M2: Exercise-level logging endpoints (spec section 14)

@training_router.put("/training-sessions/{session_id}/exercise-results")
async def log_exercise_results(
    request: Request, 
    session_id: str, 
    body: ExerciseResultsRequest,
) -> dict:
    """Log structured exercise-level results for a training session.
    
    Implements spec section 9.1 (Strength logging):
    - One compact result per exercise (not set-by-set)
    - Preserves planned vs performed exercise history
    - Stores compact reps_per_set like [8, 8, 7]
    """
    service = getattr(request.app.state, "workout_logging_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Workout logging service not configured.")
    
    from app.domain.workout_logging import ExerciseLogInput
    
    try:
        inputs = [
            ExerciseLogInput(
                sort_order=item.sort_order,
                planned_exercise_name=item.planned_exercise_name,
                planned_exercise_slug=item.planned_exercise_slug,
                performed_exercise_name=item.performed_exercise_name,
                performed_exercise_slug=item.performed_exercise_slug,
                planned_sets=item.planned_sets,
                reps_per_set=item.reps_per_set,
                load_kg=item.load_kg,
                load_per_side=item.load_per_side,
                load_note=item.load_note,
                rpe=item.rpe,
                technique_quality=item.technique_quality,
                pain_flag=item.pain_flag,
                status=item.status,
                substitution_reason=item.substitution_reason,
                notes=item.notes,
            )
            for item in body.exercises
        ]
        results = service.log_exercise_results(session_id, inputs)
        return {
            "status": "logged",
            "session_id": session_id,
            "exercise_count": len(results),
            "exercises": [
                {
                    "id": r.id,
                    "sort_order": r.sort_order,
                    "planned_exercise_name": r.planned_exercise_name,
                    "performed_exercise_name": r.performed_exercise_name,
                    "status": r.status,
                    "load_kg": r.load_kg,
                    "reps_per_set": r.reps_per_set,
                    "rpe": r.rpe,
                    "technique_quality": r.technique_quality,
                    "pain_flag": r.pain_flag,
                }
                for r in results
            ],
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Training session not found.") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@training_router.get("/training-sessions/{session_id}/exercise-results")
async def get_exercise_results(request: Request, session_id: str) -> dict:
    """Get exercise-level results for a training session."""
    service = getattr(request.app.state, "workout_logging_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Workout logging service not configured.")
    
    training_service = request.app.state.training_service
    session = training_service.session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found.")
    
    logs = service.get_exercise_logs(session_id)
    return {
        "session_id": session_id,
        "exercises": logs,
        "count": len(logs),
    }


@training_router.put("/training-sessions/{session_id}/bjj-analysis")
async def log_bjj_analysis(
    request: Request,
    session_id: str,
    body: BjjAnalysisRequest,
) -> dict:
    """Log optional BJJ analysis fields for a training session.
    
    Implements spec section 9.2 (BJJ quick review):
    - Optional main focus, problem position, failure tags
    - Links to the seeded 12 failure types from M1
    - Should be completable in under 60 seconds
    """
    service = getattr(request.app.state, "workout_logging_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Workout logging service not configured.")
    
    from app.domain.workout_logging import BjjAnalysisInput
    
    try:
        analysis_input = BjjAnalysisInput(
            main_focus=body.main_focus,
            problem_position=body.problem_position,
            key_failure_text=body.key_failure_text,
            technique_practiced=body.technique_practiced,
            success_count=body.success_count,
            attempt_count=body.attempt_count,
            primary_failure_code=body.primary_failure_code,
            additional_failure_codes=body.additional_failure_codes,
            failure_notes=body.failure_notes,
        )
        result = service.log_bjj_analysis(session_id, analysis_input)
        return {
            "status": "logged",
            "training_session_id": result.training_session_id,
            "main_focus": result.main_focus,
            "problem_position": result.problem_position,
            "primary_failure": result.primary_failure,
            "failure_codes": result.failure_codes,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Training session not found.") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@training_router.get("/training-sessions/{session_id}/bjj-analysis")
async def get_bjj_analysis(request: Request, session_id: str) -> dict:
    """Get BJJ analysis for a training session."""
    service = getattr(request.app.state, "workout_logging_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Workout logging service not configured.")
    
    training_service = request.app.state.training_service
    session = training_service.session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found.")
    
    analysis = service.get_bjj_analysis(session_id)
    if analysis is None:
        return {"session_id": session_id, "analysis": None}
    return {"session_id": session_id, "analysis": analysis}


@training_router.post("/training-sessions/{session_id}/rain-action")
async def handle_rain_action(
    request: Request,
    session_id: str,
    body: RainActionRequest,
    authorization: str | None = Header(default=None),
) -> dict:
    """Handle a rain warning action for a session.
    
    Implements spec section 10.5:
    - Move session: reschedule within this week
    - Use home fallback: record weather_blocked and create home session
    - Keep original plan: no change
    """
    _require_auth(authorization)
    
    training_service = request.app.state.training_service
    session = training_service.session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found.")
    
    workout_logging_service = getattr(request.app.state, "workout_logging_service", None)
    
    if body.action == "keep_original_plan":
        return {"status": "unchanged", "session_id": session_id, "message": "Plan kept as is."}
    
    if body.action == "move_session":
        if body.move_to_date is None:
            raise HTTPException(status_code=400, detail="move_to_date required for move_session action.")
        try:
            result = training_service.move_session(
                session_id, 
                body.move_to_date,
                reason="weather_blocked",
            )
            return {
                "status": "moved",
                "session_id": session_id,
                "new_date": body.move_to_date.isoformat(),
                "result": result,
            }
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from None
    
    if body.action == "use_home_fallback":
        from app.domain.rain_handling import get_home_alternative
        
        session_type = session.get("planned_type", "")
        alternative = get_home_alternative(session_type)
        
        if workout_logging_service:
            workout_logging_service.set_cancellation_reason(
                session_id, 
                "weather_blocked",
            )
        
        return {
            "status": "home_fallback",
            "session_id": session_id,
            "original_type": alternative.original_session_type,
            "alternative_type": alternative.alternative_type,
            "description": alternative.description,
            "counts_as": alternative.counts_as,
        }
    
    raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")


@training_router.post("/training-sessions/{session_id}/cancellation")
async def set_session_cancellation(
    request: Request,
    session_id: str,
    body: CancellationRequest,
) -> dict:
    """Set a cancellation reason for a training session.
    
    Per spec: weather_blocked is stored only after explicit athlete confirmation.
    """
    service = getattr(request.app.state, "workout_logging_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Workout logging service not configured.")
    
    try:
        service.set_cancellation_reason(
            session_id,
            body.reason,
            body.replacement_session_id,
        )
        return {
            "status": "updated",
            "session_id": session_id,
            "cancellation_reason": body.reason,
        }
    except KeyError:
        raise HTTPException(status_code=404, detail="Training session not found.") from None
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from None


@training_router.get("/training-sessions/{session_id}/rain-check")
async def check_rain_risk(request: Request, session_id: str) -> dict:
    """Check rain risk for a session requiring travel.
    
    This is used by the pre-workout flow to determine if a rain warning
    should be shown.
    """
    training_service = request.app.state.training_service
    session = training_service.session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Training session not found.")
    
    if not session.get("requires_travel", False):
        return {
            "session_id": session_id,
            "requires_travel": False,
            "at_risk": False,
            "message": "This session does not require travel.",
        }
    
    weather_service = getattr(request.app.state, "weather_service", None)
    if weather_service is None or not weather_service.configured():
        return {
            "session_id": session_id,
            "requires_travel": True,
            "at_risk": False,
            "message": "Weather service not configured.",
        }
    
    from app.domain.rain_handling import assess_rain_risk, build_rain_prompt, format_rain_warning
    
    session_start = datetime.fromisoformat(session["start_at"])
    travel_conditions = weather_service.travel_conditions()
    
    assessment = assess_rain_risk(
        session_start,
        travel_conditions,
        departure_buffer_minutes=30,
    )
    
    response = {
        "session_id": session_id,
        "requires_travel": True,
        "at_risk": assessment.at_risk,
        "precipitation_probability": assessment.precipitation_probability,
        "precipitation_mm": assessment.precipitation_mm,
        "message": assessment.message,
    }
    
    if assessment.at_risk:
        prompt = build_rain_prompt(
            session_id,
            session.get("title", "Training"),
            session_start,
            assessment,
        )
        response["warning_text"] = format_rain_warning(prompt)
        response["actions"] = list(prompt.actions)
    
    return response
