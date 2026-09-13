import asyncio
from datetime import UTC, date, datetime, timedelta
import hmac
import logging
from typing import Literal

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.api.activity_log import log_activity, preview
from app.domain.training import ExerciseDone

api_router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_INTENTS = {
    "light.turn_on",
    "light.turn_off",
    "water.run",
    "water.stop",
    "sensor.get_temperature",
    "sensor.get_humidity",
    "display.show",
    "display.hide",
    "system.get_status",
}


class CommandRequest(BaseModel):
    intent: str
    source: str = "ui"


class LightResponse(BaseModel):
    last_command_state: Literal["on", "off", "unknown"]
    last_command_at: datetime | None
    available: bool


class WaterPumpResponse(BaseModel):
    state: Literal["idle", "running"]
    last_run_at: datetime | None
    last_run_status: str | None
    available: bool


class DisplayResponse(BaseModel):
    state: Literal["visible", "hidden"]
    schedule_enabled: bool
    schedule_on_hour: int
    schedule_off_hour: int
    power_available: bool
    manual_override: bool


class CommandResponse(BaseModel):
    status: Literal["success", "failed", "skipped"]
    intent: str
    message: str | None = None
    light: LightResponse | None = None
    water_pump: WaterPumpResponse | None = None
    display: DisplayResponse | None = None


class AutomationWaterResponse(BaseModel):
    status: Literal["success", "skipped", "failed"]
    message: str | None = None


IntegrationStatus = Literal["not_configured", "ready", "unavailable"]


class CalendarEventResponse(BaseModel):
    id: str
    title: str
    start_at: datetime
    end_at: datetime
    is_all_day: bool = False
    is_current: bool = False


class CalendarTodayResponse(BaseModel):
    status: IntegrationStatus
    synced_at: datetime | None = None
    events: list[CalendarEventResponse] = []


class CalendarBridgeEventRequest(BaseModel):
    id: str
    title: str
    start_at: datetime
    end_at: datetime
    is_all_day: bool = False


class CalendarBridgeSyncRequest(BaseModel):
    synced_at: datetime
    events: list[CalendarBridgeEventRequest] = []


class NotionTaskResponse(BaseModel):
    id: str
    title: str
    due_at: datetime | None = None
    is_overdue: bool = False
    status: str | None = None
    priority: str | None = None
    task_type: str | None = None


class NotionTodayResponse(BaseModel):
    status: IntegrationStatus
    synced_at: datetime | None = None
    tasks: list[NotionTaskResponse] = []


class SpotifyNowPlayingResponse(BaseModel):
    status: IntegrationStatus
    synced_at: datetime | None = None
    track: str | None = None
    artist: str | None = None
    artwork_url: str | None = None
    device_name: str | None = None
    is_playing: bool = False


class SpotifyWebPlaybackTokenResponse(BaseModel):
    access_token: str


class SpotifyTransferRequest(BaseModel):
    device_id: str


class SystemVolumeRequest(BaseModel):
    volume_percent: int = Field(ge=0, le=100)


class SystemVolumeResponse(BaseModel):
    volume_percent: int | None
    available: bool
    output_label: str = "Audio output"


class DisplayScheduleRequest(BaseModel):
    enabled: bool


def _volume_snapshot(request: Request) -> dict[str, object]:
    service = request.app.state.pi_volume_service
    try:
        return {
            "volume_percent": service.current(),
            "volume_available": True,
            "volume_output_label": service.output_label(),
        }
    except RuntimeError:
        return {
            "volume_percent": None,
            "volume_available": False,
            "volume_output_label": "Audio output",
        }


def _display_response(request: Request) -> DisplayResponse:
    snapshot = request.app.state.display_service.snapshot()
    return DisplayResponse(
        state=snapshot.state,
        schedule_enabled=snapshot.schedule_enabled,
        schedule_on_hour=snapshot.schedule_on_hour,
        schedule_off_hour=snapshot.schedule_off_hour,
        power_available=snapshot.power_available,
        manual_override=snapshot.manual_override,
    )


class VoiceTranscriptRequest(BaseModel):
    text: str
    audio_seconds: float | None = Field(default=None, ge=0, le=120)
    wake_score: float | None = Field(default=None, ge=0, le=1)


class VoiceLogRequest(BaseModel):
    transcript: str | None = Field(default=None, max_length=500)
    action: str | None = Field(default=None, max_length=64)
    interpret_source: Literal["fast_path", "gpt"] | None = None
    artist: str | None = Field(default=None, max_length=200)
    volume_percent: int | None = Field(default=None, ge=0, le=100)
    intent_message: str | None = Field(default=None, max_length=500)
    status: Literal["success", "failed", "no_match"]
    response_message: str | None = Field(default=None, max_length=500)
    audio_seconds: float | None = Field(default=None, ge=0, le=120)
    wake_score: float | None = Field(default=None, ge=0, le=1)
    failure_stage: str | None = Field(default=None, max_length=32)


class VoiceLogResponse(BaseModel):
    id: int
    occurred_at: datetime
    transcript: str | None
    action: str | None
    interpret_source: str | None
    artist: str | None
    volume_percent: int | None
    intent_message: str | None
    status: str
    response_message: str | None
    audio_seconds: float | None
    wake_score: float | None
    failure_stage: str | None


class VoiceStateRequest(BaseModel):
    state: Literal["idle", "listening", "thinking", "complete", "error"]
    transcript: str | None = Field(default=None, max_length=500)
    message: str | None = Field(default=None, max_length=200)


class VoiceStateResponse(BaseModel):
    state: Literal["offline", "idle", "listening", "thinking", "complete", "error"]
    updated_at: datetime | None
    transcript: str | None
    message: str | None


class VoiceEventRequest(BaseModel):
    direction: Literal["in", "out", "info"]
    service: str = Field(max_length=32)
    detail: str = Field(max_length=240)


class VoiceEventResponse(BaseModel):
    at: datetime
    direction: Literal["in", "out", "info"]
    service: str
    detail: str


ActivityEventResponse = VoiceEventResponse


def _activity_responses(request: Request, limit: int) -> list[VoiceEventResponse]:
    hidden = {"openclaw", "sensor"}
    events = [
        event
        for event in request.app.state.activity_feed_service.recent_events(80)
        if event.service not in hidden
    ][-limit:]
    return [
        VoiceEventResponse(
            at=event.at,
            direction=event.direction,
            service=event.service,
            detail=event.detail,
        )
        for event in events
    ]


class OpenClawMessageResponse(BaseModel):
    id: str
    role: Literal["user", "assistant", "system"]
    text: str
    created_at: str | None = None


class OpenClawConversationResponse(BaseModel):
    status: IntegrationStatus
    messages: list[OpenClawMessageResponse] = []
    message: str | None = None


class OpenClawSendRequest(BaseModel):
    message: str


class OpenClawSendResponse(BaseModel):
    status: Literal["success", "failed"]
    delivery_status: str | None = None
    reply: str | None = None
    message: str | None = None


class ChiliNotifyRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)
    dedupe_key: str = Field(min_length=1, max_length=200)


class ChiliNotifyResponse(BaseModel):
    status: Literal["sent", "skipped", "not_configured", "failed"]
    message: str | None = None


class WalkingPadActiveSessionResponse(BaseModel):
    external_id: str
    started_at: datetime
    duration_seconds: int
    distance_km: float
    steps: int
    calories: float


class WalkingPadTodayResponse(BaseModel):
    status: IntegrationStatus | Literal["walking"]
    synced_at: datetime | None = None
    total_minutes: float = 0
    total_distance_km: float = 0
    total_steps: int = 0
    total_calories: float = 0
    goal_minutes: int = 120
    goal_distance_km: float = 3.0
    session_count: int = 0
    goal_met: bool = False
    active_session: WalkingPadActiveSessionResponse | None = None


class WalkingPadSessionSyncRequest(BaseModel):
    external_id: str
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int = 0
    distance_km: float = 0
    steps: int = 0
    calories: float = 0
    in_progress: bool = False


class WalkingPadSyncRequest(BaseModel):
    synced_at: datetime
    session: WalkingPadSessionSyncRequest


class WalkReminderResponse(BaseModel):
    active: bool
    message: str = ""
    dedupe_key: str = ""


class AutomationWalkLogRequest(BaseModel):
    duration_minutes: float | None = Field(default=None, gt=0, le=600)
    distance_km: float | None = Field(default=None, gt=0, le=100)
    steps: int | None = Field(default=None, ge=0)
    calories: float | None = Field(default=None, ge=0)
    message: str | None = Field(default=None, min_length=1, max_length=500)


class AutomationWalkLogResponse(BaseModel):
    status: Literal["logged", "failed"]
    message: str
    today: WalkingPadTodayResponse | None = None


class TrainingBlockResponse(BaseModel):
    title: str
    prescription: str | None = None
    details: list[str] = []


class TrainingPlanResponse(BaseModel):
    slug: str
    kind: str
    name: str
    duration: str
    category: str
    summary: str
    blocks: list[TrainingBlockResponse] = []
    notes: list[str] = []
    questions: list[str] = []


class TrainingExerciseResponse(BaseModel):
    name: str
    done: bool


class TrainingLogResponse(BaseModel):
    id: int
    logged_at: datetime
    kind: str
    completed: str
    feeling: str | None = None
    note: str | None = None
    rounds: str | None = None
    duration_minutes: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    distance_km: float | None = None
    exercises: list[TrainingExerciseResponse] = []
    source: str


class TrainingTodayResponse(BaseModel):
    date: date
    suggested: list[TrainingPlanResponse]
    suggested_source: Literal["calendar", "week"]
    logs: list[TrainingLogResponse] = []
    sober: TrainingLogResponse | None = None
    workout_url: str


class TrainingPlansResponse(BaseModel):
    plans: list[TrainingPlanResponse]


class TrainingExerciseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    done: bool = False


class TrainingLogRequest(BaseModel):
    kind: str | None = Field(default=None, max_length=32)
    completed: str | None = Field(default=None, max_length=16)
    feeling: str | None = Field(default=None, max_length=16)
    note: str | None = Field(default=None, max_length=500)
    rounds: str | None = Field(default=None, max_length=32)
    duration_minutes: float | None = Field(default=None, gt=0, le=600)
    avg_hr: int | None = Field(default=None, ge=30, le=230)
    max_hr: int | None = Field(default=None, ge=30, le=230)
    distance_km: float | None = Field(default=None, gt=0, le=200)
    exercises: list[TrainingExerciseRequest] = []
    message: str | None = Field(default=None, min_length=1, max_length=500)


class DailyWorkoutRequest(BaseModel):
    kind: str | None = Field(default=None, max_length=32)
    exercises: list[TrainingExerciseRequest] = []
    note: str | None = Field(default=None, max_length=500)


class DailySoberRequest(BaseModel):
    sober: bool
    note: str | None = Field(default=None, max_length=500)


class DailySundayRequest(BaseModel):
    weight_kg: float | None = Field(default=None, ge=30, le=250)
    same_as_last: bool = False
    note: str | None = Field(default=None, max_length=500)


class TrainingLogApiResponse(BaseModel):
    status: Literal["logged", "failed"]
    message: str
    log: TrainingLogResponse | None = None


class ManagedTrainingEventResponse(BaseModel):
    session_id: str
    title: str
    start_at: datetime
    end_at: datetime
    is_all_day: bool
    notes: str


class ManagedTrainingPlanResponse(BaseModel):
    calendar_name: str
    events: list[ManagedTrainingEventResponse]


class WeatherDayResponse(BaseModel):
    date: date
    label: str
    high_c: float
    low_c: float
    condition: str
    icon: Literal["sunny", "evening", "cloudy", "fog", "rain", "snow", "storm"]
    current_c: float | None = None


class WeatherForecastResponse(BaseModel):
    status: IntegrationStatus
    location: str
    synced_at: datetime | None = None
    today: WeatherDayResponse | None = None
    tomorrow: WeatherDayResponse | None = None


def _water_pump_response(snapshot) -> WaterPumpResponse:
    return WaterPumpResponse(
        state=snapshot.state,
        last_run_at=snapshot.last_run_at,
        last_run_status=snapshot.last_run_status,
        available=snapshot.available,
    )


def _automation_authorized(authorization: str | None) -> bool:
    token = settings.dashboard_automation_token
    if not token or not authorization or not authorization.startswith("Bearer "):
        return False
    provided = authorization.removeprefix("Bearer ").strip()
    return bool(provided) and hmac.compare_digest(provided, token)


def _openclaw_conversation(service) -> OpenClawConversationResponse:
    if not service.configured():
        return OpenClawConversationResponse(status="not_configured")
    try:
        messages = service.history()
    except Exception:
        return OpenClawConversationResponse(status="unavailable", message="OpenClaw is unavailable.")
    return OpenClawConversationResponse(
        status="ready",
        messages=[OpenClawMessageResponse(**message.__dict__) for message in messages],
    )


def _model_json(model: BaseModel) -> str:
    if hasattr(model, "model_dump_json"):
        return model.model_dump_json()
    return model.json()


@api_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _weather_response(forecast) -> WeatherForecastResponse:
    def day(day) -> WeatherDayResponse | None:
        if day is None:
            return None
        return WeatherDayResponse(
            date=day.date,
            label=day.label,
            high_c=day.high_c,
            low_c=day.low_c,
            condition=day.condition,
            icon=day.icon,
            current_c=day.current_c,
        )

    return WeatherForecastResponse(
        status=forecast.status,
        location=forecast.location,
        synced_at=forecast.synced_at,
        today=day(forecast.today),
        tomorrow=day(forecast.tomorrow),
    )


@api_router.get("/weather", response_model=WeatherForecastResponse)
async def weather_forecast(request: Request) -> WeatherForecastResponse:
    return _weather_response(request.app.state.weather_service.forecast())


@api_router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, object]:
    sensor = request.app.state.sensor_service
    light = request.app.state.light_service.snapshot()
    water_pump = request.app.state.water_pump_service.snapshot()
    spotify_status = request.app.state.spotify_service.status()
    openclaw_status = request.app.state.openclaw_service.status()
    system_status = request.app.state.system_status_service.snapshot()
    bluetooth_audio = request.app.state.bluetooth_audio_service.snapshot()
    volume = _volume_snapshot(request)
    reading = sensor.current()
    return {
        "temperature_c": reading.temperature_c if reading else None,
        "humidity_percent": reading.humidity_percent if reading else None,
        "last_updated_at": reading.recorded_at if reading else None,
        "light": {
            "last_command_state": light.last_command_state,
            "last_command_at": light.last_command_at,
            "available": light.available,
        },
        "water_pump": {
            "state": water_pump.state,
            "last_run_at": water_pump.last_run_at,
            "last_run_status": water_pump.last_run_status,
            "available": water_pump.available,
        },
        "system": {
            "cpu_temperature_c": system_status.cpu_temperature_c,
            "load_1m": system_status.load_1m,
            "load_percent": system_status.load_percent,
            "memory_used_percent": system_status.memory_used_percent,
            "memory_used_mb": system_status.memory_used_mb,
            "memory_total_mb": system_status.memory_total_mb,
            "storage_used_percent": system_status.storage_used_percent,
            "storage_free_gb": system_status.storage_free_gb,
            "storage_total_gb": system_status.storage_total_gb,
            "bluetooth_status": bluetooth_audio.status,
            "bluetooth_device_name": bluetooth_audio.device_name,
            "bluetooth_is_default_output": bluetooth_audio.is_default_output,
            "volume_percent": volume["volume_percent"],
            "volume_available": volume["volume_available"],
            "volume_output_label": volume["volume_output_label"],
        },
        "display": _display_response(request).model_dump(),
        "integrations": {
            "sensor": sensor.status(),
            "broadlink": "ready" if light.available else "unavailable",
            "calendar": request.app.state.calendar_bridge_service.today()[0],
            "notion": request.app.state.notion_service.status(),
            "spotify": spotify_status,
            "openclaw": openclaw_status,
            "water_pump": "ready" if water_pump.available else "not_configured",
            "walkingpad": request.app.state.walkingpad_service.today().status,
        },
    }


@api_router.get("/calendar/today", response_model=CalendarTodayResponse)
async def calendar_today(request: Request) -> CalendarTodayResponse:
    return _calendar_response(*request.app.state.calendar_bridge_service.today())


@api_router.get("/calendar/events", response_model=CalendarTodayResponse)
async def calendar_events(
    request: Request,
    start: date = Query(...),
    days: int = Query(default=30, ge=1, le=30),
) -> CalendarTodayResponse:
    service = request.app.state.calendar_bridge_service
    status, synced_at, events = service.events_for_range(start, days)
    response = _calendar_response(status, synced_at, events)
    cache_key = f"{start}:{days}"
    if service.should_log_fetch(cache_key, events):
        log_activity(
            request,
            "out",
            "calendar",
            f"{len(response.events)} events ({response.status})",
            dedupe_key=cache_key,
        )
    return response


def _calendar_response(
    status: IntegrationStatus,
    synced_at: datetime | None,
    events: list[object],
) -> CalendarTodayResponse:
    now = datetime.now(UTC)
    return CalendarTodayResponse(
        status=status,
        synced_at=synced_at,
        events=[
            CalendarEventResponse(
                id=event.external_id,
                title=event.title,
                start_at=event.start_at,
                end_at=event.end_at,
                is_all_day=event.is_all_day,
                is_current=event.start_at <= now < event.end_at,
            )
            for event in events
        ],
    )


@api_router.post("/calendar/apple/sync", status_code=204)
async def sync_apple_calendar(
    request: Request,
    body: CalendarBridgeSyncRequest,
) -> None:
    expected = request.app.state.calendar_bridge_service.configured() and settings.apple_calendar_bridge_token
    provided = request.headers.get("X-Chili-Bridge-Token", "")
    if not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid calendar bridge token.")
    from app.domain.calendar_bridge import CalendarEvent

    snapshot = [
        CalendarEvent(
            external_id=event.id,
            title=event.title,
            start_at=event.start_at,
            end_at=event.end_at,
            is_all_day=event.is_all_day,
        )
        for event in body.events
    ]
    service = request.app.state.calendar_bridge_service
    service.replace_snapshot(snapshot, body.synced_at)
    if service.should_log_sync(snapshot):
        log_activity(
            request,
            "in",
            "calendar",
            f"bridge sync {len(body.events)} events",
        )


@api_router.get("/calendar/apple/training-plan", response_model=ManagedTrainingPlanResponse)
async def apple_training_plan(request: Request) -> ManagedTrainingPlanResponse:
    expected = request.app.state.calendar_bridge_service.configured() and settings.apple_calendar_bridge_token
    provided = request.headers.get("X-Chili-Bridge-Token", "")
    if not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid calendar bridge token.")
    return ManagedTrainingPlanResponse.model_validate(
        request.app.state.training_service.managed_calendar_plan()
    )


def _walkingpad_response(snapshot) -> WalkingPadTodayResponse:
    active = None
    if snapshot.active_session is not None:
        session = snapshot.active_session
        active = WalkingPadActiveSessionResponse(
            external_id=session.external_id,
            started_at=session.started_at,
            duration_seconds=session.duration_seconds,
            distance_km=session.distance_km,
            steps=session.steps,
            calories=session.calories,
        )
    return WalkingPadTodayResponse(
        status=snapshot.status,
        synced_at=snapshot.synced_at,
        total_minutes=snapshot.total_minutes,
        total_distance_km=snapshot.total_distance_km,
        total_steps=snapshot.total_steps,
        total_calories=snapshot.total_calories,
        goal_minutes=snapshot.goal_minutes,
        goal_distance_km=snapshot.goal_distance_km,
        session_count=snapshot.session_count,
        goal_met=snapshot.goal_met,
        active_session=active,
    )


@api_router.post("/walkingpad/sync", status_code=204)
async def sync_walkingpad(
    request: Request,
    body: WalkingPadSyncRequest,
) -> None:
    expected = request.app.state.walkingpad_service.configured() and settings.walkingpad_bridge_token
    provided = request.headers.get("X-Chili-Bridge-Token", "")
    if not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid walking pad bridge token.")
    service = request.app.state.walkingpad_service
    session = body.session
    service.sync_session(
        external_id=session.external_id,
        started_at=session.started_at,
        ended_at=None if session.in_progress else session.ended_at,
        duration_seconds=session.duration_seconds,
        distance_km=session.distance_km,
        steps=session.steps,
        calories=session.calories,
        synced_at=body.synced_at,
    )
    detail = (
        f"session {session.duration_seconds}s"
        if session.in_progress
        else f"session complete {session.duration_seconds}s"
    )
    log_activity(request, "in", "walkingpad", detail)


@api_router.get("/walkingpad/today", response_model=WalkingPadTodayResponse)
async def walkingpad_today(request: Request) -> WalkingPadTodayResponse:
    snapshot = request.app.state.walkingpad_service.today()
    return _walkingpad_response(snapshot)


@api_router.get("/walkingpad/reminder", response_model=WalkReminderResponse)
async def walkingpad_reminder(request: Request) -> WalkReminderResponse:
    service = request.app.state.walkingpad_service
    calendar = request.app.state.calendar_bridge_service
    _, _, events = calendar.today()
    reminder = service.reminder(events)
    return WalkReminderResponse(
        active=reminder.active,
        message=reminder.message,
        dedupe_key=reminder.dedupe_key,
    )


def _log_manual_walk(request: Request, body: AutomationWalkLogRequest) -> AutomationWalkLogResponse:
    service = request.app.state.walkingpad_service
    if not service.configured():
        return AutomationWalkLogResponse(status="failed", message="Walking pad is not configured.")
    try:
        if body.message and not body.duration_minutes and not body.distance_km:
            snapshot = service.log_manual_message(body.message)
        else:
            snapshot = service.log_manual(
                duration_minutes=body.duration_minutes,
                distance_km=body.distance_km,
                steps=body.steps or 0,
                calories=body.calories or 0.0,
            )
    except ValueError as error:
        return AutomationWalkLogResponse(status="failed", message=str(error))
    detail = f"manual {snapshot.total_minutes} min {snapshot.total_distance_km} km"
    log_activity(request, "in", "walkingpad", detail)
    return AutomationWalkLogResponse(
        status="logged",
        message=(
            f"Logged walk: {snapshot.total_minutes} min and "
            f"{snapshot.total_distance_km} km total today."
        ),
        today=_walkingpad_response(snapshot),
    )


@api_router.post("/automation/walkingpad/log", response_model=AutomationWalkLogResponse)
async def automation_walkingpad_log(
    request: Request,
    body: AutomationWalkLogRequest,
    authorization: str | None = Header(default=None),
) -> AutomationWalkLogResponse:
    if not _automation_authorized(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return _log_manual_walk(request, body)


def _training_plan_response(plan) -> TrainingPlanResponse:
    return TrainingPlanResponse(
        slug=plan.slug,
        kind=plan.kind,
        name=plan.name,
        duration=plan.duration,
        category=plan.category,
        summary=plan.summary,
        blocks=[
            TrainingBlockResponse(
                title=block.title,
                prescription=block.prescription,
                details=list(block.details),
            )
            for block in plan.blocks
        ],
        notes=list(plan.notes),
        questions=list(request_training_questions(plan.kind)),
    )


def request_training_questions(kind: str) -> tuple[str, ...]:
    from app.domain.training_questions import questions_for

    return questions_for(kind)  # type: ignore[arg-type]


def _training_log_response(record) -> TrainingLogResponse:
    return TrainingLogResponse(
        id=record.id,
        logged_at=record.logged_at,
        kind=record.kind,
        completed=record.completed,
        feeling=record.feeling,
        note=record.note,
        rounds=record.rounds,
        duration_minutes=record.duration_minutes,
        avg_hr=record.avg_hr,
        max_hr=record.max_hr,
        distance_km=record.distance_km,
        exercises=[
            TrainingExerciseResponse(name=item.name, done=item.done)
            for item in record.exercises
        ],
        source=record.source,
    )


def _today_calendar_events(request: Request) -> list:
    calendar = getattr(request.app.state, "calendar_bridge_service", None)
    if calendar is None:
        return []
    _, _, events = calendar.today()
    return events


def _log_training(
    request: Request,
    body: TrainingLogRequest,
    *,
    source: Literal["ui", "openclaw", "automation"],
) -> TrainingLogApiResponse:
    service = getattr(request.app.state, "training_service", None)
    if service is None:
        return TrainingLogApiResponse(status="failed", message="Training is not configured.")
    try:
        if body.message and not body.kind:
            parsed = service.try_parse_manual_message(body.message)
            if parsed is None:
                return TrainingLogApiResponse(
                    status="failed",
                    message="Could not parse a training check-in from the message.",
                )
            record = service.log_parsed(parsed, source=source)
        else:
            if not body.kind or not body.completed:
                return TrainingLogApiResponse(
                    status="failed",
                    message="kind and completed are required unless message is provided.",
                )
            record = service.log(
                kind=body.kind,
                completed=body.completed,
                feeling=body.feeling,
                note=body.note,
                rounds=body.rounds,
                duration_minutes=body.duration_minutes,
                avg_hr=body.avg_hr,
                max_hr=body.max_hr,
                distance_km=body.distance_km,
                exercises=[
                    ExerciseDone(name=item.name, done=item.done)
                    for item in body.exercises
                ] or None,
                source=source,
            )
    except ValueError as error:
        return TrainingLogApiResponse(status="failed", message=str(error))
    log_activity(request, "in", "training", f"{record.kind} {record.completed}")
    return TrainingLogApiResponse(
        status="logged",
        message=f"Logged {record.kind}: {record.completed}.",
        log=_training_log_response(record),
    )


@api_router.get("/training/plans", response_model=TrainingPlansResponse)
async def training_plans(request: Request) -> TrainingPlansResponse:
    service = request.app.state.training_service
    return TrainingPlansResponse(plans=[_training_plan_response(plan) for plan in service.plans()])


@api_router.get("/training/plans/{slug}", response_model=TrainingPlanResponse)
async def training_plan(request: Request, slug: str) -> TrainingPlanResponse:
    plan = request.app.state.training_service.plan(slug)
    if plan is None:
        raise HTTPException(status_code=404, detail="Unknown training plan.")
    return _training_plan_response(plan)


@api_router.get("/training/today", response_model=TrainingTodayResponse)
async def training_today(request: Request) -> TrainingTodayResponse:
    service = request.app.state.training_service
    snapshot = service.today(calendar_events=_today_calendar_events(request))
    suggested = []
    for kind in snapshot.suggested:
        plan = service.plan(kind)
        if plan is not None:
            suggested.append(_training_plan_response(plan))
    return TrainingTodayResponse(
        date=snapshot.date,
        suggested=suggested,
        suggested_source=snapshot.suggested_source,
        logs=[_training_log_response(row) for row in snapshot.logs],
        sober=_training_log_response(snapshot.sober) if snapshot.sober is not None else None,
        workout_url=service.public_url("/workout"),
    )


@api_router.post("/training/log", response_model=TrainingLogApiResponse)
async def training_log(request: Request, body: TrainingLogRequest) -> TrainingLogApiResponse:
    return _log_training(request, body, source="ui")


@api_router.post("/automation/training/log", response_model=TrainingLogApiResponse)
async def automation_training_log(
    request: Request,
    body: TrainingLogRequest,
    authorization: str | None = Header(default=None),
) -> TrainingLogApiResponse:
    if not _automation_authorized(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return _log_training(request, body, source="automation")


def _calendar_day(request: Request, day: date) -> tuple[str, list]:
    calendar = getattr(request.app.state, "calendar_bridge_service", None)
    if calendar is None:
        return "not_configured", []
    status, _, events = calendar.events_for_range(day, 1)
    return status, events


def _daily_payload(request: Request, day: date, preview: str | None = None) -> dict:
    training = request.app.state.training_service
    weekly = request.app.state.weekly_service
    status, events = _calendar_day(request, day)
    briefing = training.daily(
        day,
        preview=preview,
        calendar_events=events,
        calendar_status=status,
    )
    sunday = weekly.sunday_check_in(day, training)
    return {
        "date": briefing.date.isoformat(),
        "timezone": briefing.timezone,
        "workouts": [
            {
                "kind": workout.kind,
                "title": workout.title,
                "summary": workout.summary,
                "status": workout.status,
                "completed": workout.completed,
                "note": workout.note,
                "exercises": [
                    {
                        "name": item.name,
                        "prescription": item.prescription,
                        "details": list(item.details),
                        "done": item.done,
                    }
                    for item in workout.exercises
                ],
            }
            for workout in briefing.workouts
        ],
        "calendar": {
            "status": briefing.calendar_status,
            "meetings": [
                {
                    "title": meeting.title,
                    "start_at": meeting.start_at.isoformat(),
                    "end_at": meeting.end_at.isoformat(),
                    "is_all_day": meeting.is_all_day,
                }
                for meeting in briefing.meetings
            ],
        },
        "sobriety": {
            "days": briefing.sober_days,
            "answered": briefing.sober_answered,
            "note": briefing.sober_note,
        },
        "sleep": None,
        "sunday": None
        if sunday is None
        else {
            "week_start": sunday.week_start.isoformat(),
            "week_ending": sunday.week_ending.isoformat(),
            "weight_kg": sunday.weight_kg,
            "previous_weight_kg": sunday.previous_weight_kg,
            "delta_kg": sunday.delta_kg,
            "review_note": sunday.review_note,
            "submitted": sunday.submitted,
            "sessions": [
                {
                    "date": session.date.isoformat(),
                    "kind": session.kind,
                    "title": session.title,
                    "completed": session.completed,
                    "note": session.note,
                    "exercises": [
                        {"name": item.name, "done": item.done}
                        for item in session.exercises
                    ],
                }
                for session in sunday.sessions
            ],
        },
        "preview": briefing.preview,
        "daily_url": briefing.daily_url,
    }


def _ask_chili(request: Request, prompt: str) -> str | None:
    openclaw = getattr(request.app.state, "openclaw_service", None)
    if openclaw is None or not openclaw.configured():
        return None
    try:
        result = openclaw.send(prompt)
    except Exception:
        logger.exception("Sunday Chili review failed")
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
        logger.exception("Chili notify failed")


@api_router.get("/daily/{day}")
async def daily_briefing(
    request: Request,
    day: str,
    preview: str | None = Query(default=None),
) -> dict:
    return _daily_payload(request, _parse_iso_date(day), preview)


@api_router.post("/daily/{day}/workout", response_model=TrainingLogApiResponse)
async def daily_workout(request: Request, day: str, body: DailyWorkoutRequest) -> TrainingLogApiResponse:
    parsed = _parse_iso_date(day)
    training = request.app.state.training_service
    kind = body.kind
    if not kind:
        snapshot = training.for_day(parsed, calendar_events=_calendar_day(request, parsed)[1])
        kind = snapshot.suggested[0] if snapshot.suggested else None
    if not kind:
        return TrainingLogApiResponse(status="failed", message="No workout to log.")
    try:
        record = training.log_workout(
            kind=kind,
            exercises=[ExerciseDone(name=item.name, done=item.done) for item in body.exercises],
            note=body.note,
            source="ui",
            now=training.stamp_for_day(parsed),
        )
    except ValueError as error:
        return TrainingLogApiResponse(status="failed", message=str(error))
    log_activity(request, "in", "training", f"{record.kind} {record.completed}")
    return TrainingLogApiResponse(
        status="logged",
        message=f"Logged {record.kind}: {record.completed}.",
        log=_training_log_response(record),
    )


@api_router.post("/training/workout", response_model=TrainingLogApiResponse)
async def training_workout(request: Request, body: DailyWorkoutRequest) -> TrainingLogApiResponse:
    today = request.app.state.training_service.today(
        calendar_events=_today_calendar_events(request)
    )
    return await daily_workout(
        request,
        today.date.isoformat(),
        DailyWorkoutRequest(kind=body.kind, exercises=body.exercises, note=body.note),
    )


@api_router.post("/daily/{day}/sober", response_model=TrainingLogApiResponse)
async def daily_sober(request: Request, day: str, body: DailySoberRequest) -> TrainingLogApiResponse:
    parsed = _parse_iso_date(day)
    training = request.app.state.training_service
    try:
        record = training.log_sober(
            sober=body.sober,
            note=body.note,
            source="ui",
            now=training.stamp_for_day(parsed),
        )
    except ValueError as error:
        return TrainingLogApiResponse(status="failed", message=str(error))
    log_activity(request, "in", "training", f"sober {record.completed}")
    return TrainingLogApiResponse(
        status="logged",
        message=f"Logged sober: {record.completed}.",
        log=_training_log_response(record),
    )


@api_router.post("/daily/{day}/sunday")
async def daily_sunday(request: Request, day: str, body: DailySundayRequest) -> dict:
    parsed = _parse_iso_date(day)
    training = request.app.state.training_service
    weekly = request.app.state.weekly_service
    try:
        saved = weekly.save_sunday(
            parsed,
            training,
            weight_kg=body.weight_kg,
            same_as_last=body.same_as_last,
            note=body.note,
            source="ui",
            now=training.stamp_for_day(parsed),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    log_activity(request, "in", "training", f"sunday weight {saved.check_in.weight_kg}")
    _notify_chili(
        request,
        saved.notify_message,
        f"sunday-saved-{parsed.isoformat()}",
    )
    advice = _ask_chili(request, saved.review_prompt)
    payload = _daily_payload(request, parsed)
    payload["advice"] = advice
    payload["message"] = saved.notify_message
    return payload


def _parse_iso_date(value: str, field_name: str = "date") -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=f"Invalid {field_name}; use YYYY-MM-DD") from error


@api_router.get("/db/{day}")
async def read_db_for_day(
    request: Request,
    day: str,
    end: str | None = Query(default=None, description="Optional inclusive end date YYYY-MM-DD"),
    days: int | None = Query(default=None, ge=1, le=62, description="Inclusive day count starting at day"),
    authorization: str | None = Header(default=None),
) -> dict:
    """Read-only SQLite snapshot for OpenClaw/tools. Requires automation bearer token.

    Examples:
      GET /api/v1/db/2026-07-13
      GET /api/v1/db/2026-07-07?days=7
      GET /api/v1/db/2026-07-01?end=2026-07-31
    """
    if not _automation_authorized(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")
    start_day = _parse_iso_date(day, "day")
    if end is not None and days is not None:
        raise HTTPException(status_code=400, detail="Provide either end or days, not both")
    if end is not None:
        end_day = _parse_iso_date(end, "end")
    elif days is not None:
        end_day = start_day + timedelta(days=days - 1)
    else:
        end_day = start_day
    service = request.app.state.db_read_service
    try:
        return service.snapshot_for_range(start_day, end_day)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@api_router.get("/notion/today", response_model=NotionTodayResponse)
async def notion_today(request: Request) -> NotionTodayResponse:
    status, synced_at, tasks = request.app.state.notion_service.today()
    log_activity(
        request,
        "out",
        "notion",
        f"sync {len(tasks)} open tasks" if status == "ready" else f"status={status}",
        dedupe_key=f"{status}:{len(tasks)}",
    )
    return NotionTodayResponse(
        status=status,
        synced_at=synced_at,
        tasks=[
            NotionTaskResponse(
                id=task.id,
                title=task.title,
                due_at=task.due_at,
                is_overdue=task.is_overdue,
                status=task.status,
                priority=task.priority,
                task_type=task.task_type,
            )
            for task in tasks
        ],
    )


@api_router.get("/openclaw/messages", response_model=OpenClawConversationResponse)
async def openclaw_messages(request: Request) -> OpenClawConversationResponse:
    return _openclaw_conversation(request.app.state.openclaw_service)


@api_router.get("/openclaw/messages/stream")
async def openclaw_message_stream(request: Request) -> StreamingResponse:
    async def events():
        last_payload: str | None = None
        while not await request.is_disconnected():
            payload = await asyncio.to_thread(_openclaw_conversation, request.app.state.openclaw_service)
            serialized = _model_json(payload)
            if serialized != last_payload:
                yield f"event: conversation\ndata: {serialized}\n\n"
                last_payload = serialized
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@api_router.post("/openclaw/messages", response_model=OpenClawSendResponse)
async def send_openclaw_message(
    request: Request, body: OpenClawSendRequest
) -> OpenClawSendResponse:
    message = body.message.strip()
    if not message or len(message) > 3_000:
        raise HTTPException(status_code=400, detail="Message must contain 1 to 3000 characters.")
    walkingpad = request.app.state.walkingpad_service
    if walkingpad.configured() and walkingpad.try_parse_manual_message(message) is not None:
        result = _log_manual_walk(
            request,
            AutomationWalkLogRequest(message=message),
        )
        if result.status == "logged":
            return OpenClawSendResponse(
                status="success",
                reply=result.message,
                message=result.message,
            )
    training = getattr(request.app.state, "training_service", None)
    if training is not None and training.try_parse_manual_message(message) is not None:
        result = _log_training(
            request,
            TrainingLogRequest(message=message),
            source="openclaw",
        )
        if result.status == "logged":
            return OpenClawSendResponse(
                status="success",
                reply=result.message,
                message=result.message,
            )
    service = request.app.state.openclaw_service
    if not service.configured():
        return OpenClawSendResponse(status="failed", message="OpenClaw is not configured.")
    try:
        result = service.send(message)
        return OpenClawSendResponse(status="success", **result)
    except Exception as error:
        return OpenClawSendResponse(status="failed", message=str(error))


@api_router.post("/chili/notify", response_model=ChiliNotifyResponse)
async def chili_notify(request: Request, body: ChiliNotifyRequest) -> ChiliNotifyResponse:
    message = body.message.strip()
    dedupe_key = body.dedupe_key.strip()
    if not message or not dedupe_key:
        raise HTTPException(status_code=400, detail="Message and dedupe_key are required.")

    openclaw = request.app.state.openclaw_service
    if not openclaw.configured():
        return ChiliNotifyResponse(status="not_configured")

    notify_service = request.app.state.chili_notify_service
    if not notify_service.should_send(dedupe_key):
        return ChiliNotifyResponse(status="skipped")

    try:
        notify = getattr(openclaw, "notify_user", None)
        if callable(notify):
            result = notify(message)
        else:
            result = openclaw.send(message)
        delivery = None
        if isinstance(result, dict):
            delivery = result.get("delivery_status")
        if delivery not in {None, "sent", "delivered", "ok"}:
            raise RuntimeError(f"OpenClaw delivery was {delivery}")
        notify_service.mark_sent(dedupe_key)
        log_activity(request, "out", "chili", message, dedupe_key=dedupe_key)
        return ChiliNotifyResponse(status="sent")
    except Exception as error:
        notify_service.release(dedupe_key)
        logger.exception("Chili notify failed")
        return ChiliNotifyResponse(status="failed", message=str(error))


@api_router.get("/spotify/now-playing", response_model=SpotifyNowPlayingResponse)
async def spotify_now_playing(request: Request) -> SpotifyNowPlayingResponse:
    payload = request.app.state.spotify_service.now_playing()
    if payload.get("status") == "ready" and payload.get("track"):
        playing = "playing" if payload.get("is_playing") else "paused"
        detail = f"{payload['track']} · {payload.get('artist') or 'unknown'} ({playing})"
        log_activity(request, "out", "spotify", detail, dedupe_key=f"{payload['track']}:{playing}")
    elif payload.get("status") != "ready":
        log_activity(
            request,
            "out",
            "spotify",
            f"status={payload.get('status')}",
            dedupe_key=str(payload.get("status")),
        )
    return SpotifyNowPlayingResponse(**payload)


@api_router.get("/spotify/web-playback-token", response_model=SpotifyWebPlaybackTokenResponse)
async def spotify_web_playback_token(request: Request) -> SpotifyWebPlaybackTokenResponse:
    try:
        return SpotifyWebPlaybackTokenResponse(
            access_token=request.app.state.spotify_service.web_playback_token()
        )
    except Exception as error:
        raise HTTPException(status_code=503, detail="Spotify playback is not ready.") from error


@api_router.post("/spotify/transfer")
async def spotify_transfer(request: Request, body: SpotifyTransferRequest) -> dict[str, str]:
    try:
        request.app.state.spotify_service.transfer_playback(body.device_id)
        log_activity(request, "in", "spotify", f"transfer playback device={body.device_id[:8]}…")
    except Exception as error:
        raise HTTPException(status_code=503, detail="Spotify playback transfer failed.") from error
    return {"status": "success"}


@api_router.post("/spotify/device")
async def spotify_device(request: Request, body: SpotifyTransferRequest) -> dict[str, str]:
    request.app.state.spotify_service.register_device(body.device_id)
    log_activity(request, "in", "spotify", f"register web player device={body.device_id[:8]}…")
    return {"status": "success"}


@api_router.post("/spotify/dj")
async def spotify_dj(request: Request) -> dict[str, str]:
    try:
        request.app.state.spotify_service.start_dj()
        log_activity(request, "in", "spotify", "start dj")
    except Exception as error:
        raise HTTPException(status_code=503, detail="Spotify DJ could not start.") from error
    return {"status": "success"}


@api_router.post("/system/volume", response_model=SystemVolumeResponse)
async def set_system_volume(request: Request, body: SystemVolumeRequest) -> SystemVolumeResponse:
    try:
        volume = request.app.state.pi_volume_service.set(body.volume_percent)
        log_activity(request, "in", "dashboard", f"volume {volume}%")
        return SystemVolumeResponse(
            volume_percent=volume,
            available=True,
            output_label=request.app.state.pi_volume_service.output_label(),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail="Raspberry Pi volume control is unavailable.") from error


@api_router.post("/display/schedule", response_model=DisplayResponse)
async def set_display_schedule(request: Request, body: DisplayScheduleRequest) -> DisplayResponse:
    display = request.app.state.display_service
    action = "enabled" if body.enabled else "disabled"
    log_activity(request, "in", "dashboard", f"display schedule {action}")
    snapshot = display.set_schedule_enabled(body.enabled)
    response = DisplayResponse(
        state=snapshot.state,
        schedule_enabled=snapshot.schedule_enabled,
        schedule_on_hour=snapshot.schedule_on_hour,
        schedule_off_hour=snapshot.schedule_off_hour,
        power_available=snapshot.power_available,
        manual_override=snapshot.manual_override,
    )
    log_activity(request, "out", "dashboard", f"display state={response.state}")
    return response


@api_router.get("/spotify/connect", include_in_schema=False)
async def spotify_connect(request: Request) -> RedirectResponse:
    try:
        return RedirectResponse(request.app.state.spotify_service.begin_authorization())
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@api_router.get("/spotify/callback", include_in_schema=False)
async def spotify_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    if error:
        return RedirectResponse(f"/?spotify={error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Spotify did not return an authorization code.")
    try:
        request.app.state.spotify_service.complete_authorization(code, state)
        log_activity(request, "info", "spotify", "account connected")
    except (RuntimeError, httpx.HTTPError) as error:
        raise HTTPException(status_code=502, detail="Spotify authorization failed.") from error
    return RedirectResponse("/?spotify=connected")


@api_router.get("/readings")
async def readings(
    request: Request,
    hours: int = Query(default=24, ge=1, le=720),
) -> dict[str, list[dict[str, datetime | float]]]:
    sensor = request.app.state.sensor_service
    return {
        "readings": [
            {
                "recorded_at": reading.recorded_at,
                "temperature_c": reading.temperature_c,
                "humidity_percent": reading.humidity_percent,
            }
            for reading in sensor.history(hours)
        ]
    }


@api_router.post("/commands", response_model=CommandResponse)
async def command(request: CommandRequest, api_request: Request) -> CommandResponse:
    if request.intent not in ALLOWED_INTENTS:
        raise HTTPException(status_code=400, detail="Unsupported command intent")

    log_activity(
        api_request,
        "in",
        "dashboard",
        f"command {request.intent} source={request.source}",
    )

    light = api_request.app.state.light_service
    water_pump = api_request.app.state.water_pump_service
    if request.intent in {"light.turn_on", "light.turn_off"}:
        result = light.set_state(
            "on" if request.intent == "light.turn_on" else "off", request.source
        )
        response = CommandResponse(
            status=result.status,
            intent=request.intent,
            message=result.message,
            light=LightResponse(
                last_command_state=result.light.last_command_state,
                last_command_at=result.light.last_command_at,
                available=result.light.available,
            ),
        )
        log_activity(api_request, "out", "dashboard", f"{request.intent} status={response.status}")
        return response

    if request.intent == "water.run":
        result = await water_pump.start_pulse(request.source)
        response = CommandResponse(
            status=result.status,
            intent=request.intent,
            message=result.message,
            water_pump=_water_pump_response(result.water_pump),
        )
        log_activity(api_request, "out", "dashboard", f"{request.intent} status={response.status}")
        return response

    if request.intent == "water.stop":
        result = await water_pump.stop(request.source)
        response = CommandResponse(
            status="success" if result.status != "failed" else "failed",
            intent=request.intent,
            message=result.message,
            water_pump=_water_pump_response(result.water_pump),
        )
        log_activity(api_request, "out", "dashboard", f"{request.intent} status={response.status}")
        return response

    display = api_request.app.state.display_service
    if request.intent == "display.show":
        snapshot = display.show(request.source)
        response = CommandResponse(
            status="success",
            intent=request.intent,
            message="Screen is on.",
            display=DisplayResponse(
                state=snapshot.state,
                schedule_enabled=snapshot.schedule_enabled,
                schedule_on_hour=snapshot.schedule_on_hour,
                schedule_off_hour=snapshot.schedule_off_hour,
                power_available=snapshot.power_available,
                manual_override=snapshot.manual_override,
            ),
        )
        log_activity(api_request, "out", "dashboard", f"{request.intent} status={response.status}")
        return response

    if request.intent == "display.hide":
        snapshot = display.hide(request.source)
        response = CommandResponse(
            status="success",
            intent=request.intent,
            message="Screen is off.",
            display=DisplayResponse(
                state=snapshot.state,
                schedule_enabled=snapshot.schedule_enabled,
                schedule_on_hour=snapshot.schedule_on_hour,
                schedule_off_hour=snapshot.schedule_off_hour,
                power_available=snapshot.power_available,
                manual_override=snapshot.manual_override,
            ),
        )
        log_activity(api_request, "out", "dashboard", f"{request.intent} status={response.status}")
        return response

    response = CommandResponse(
        status="failed",
        intent=request.intent,
        message="This dashboard command is not configured yet.",
    )
    log_activity(api_request, "out", "dashboard", f"{request.intent} status=failed")
    return response


@api_router.post("/automation/water", response_model=AutomationWaterResponse)
async def automation_water(
    request: Request,
    authorization: str | None = Header(default=None),
) -> AutomationWaterResponse:
    if not _automation_authorized(authorization):
        raise HTTPException(status_code=401, detail="Unauthorized")

    water_pump = request.app.state.water_pump_service
    openclaw = request.app.state.openclaw_service
    result = await water_pump.run_pulse("openclaw")
    log_activity(
        request,
        "in",
        "dashboard",
        f"automation water status={result.status}",
    )

    if result.status == "failed" and openclaw.configured():
        try:
            notify = getattr(openclaw, "notify_user", None)
            if callable(notify):
                notify(f"Plant pump failed: {result.message}")
            else:
                openclaw.send(f"Plant pump failed: {result.message}")
        except Exception:
            logger.exception("Could not notify OpenClaw about plant pump failure")

    return AutomationWaterResponse(status=result.status, message=result.message)


@api_router.post("/voice/transcripts")
async def voice_transcript(request: Request, body: VoiceTranscriptRequest) -> dict[str, str]:
    voice_log = request.app.state.voice_log_service
    transcript = body.text.strip()
    log_activity(request, "in", "backend", f"transcript: {transcript}")
    interpretation = None
    try:
        interpretation = request.app.state.voice_command_interpreter.interpret(body.text)
        command = interpretation.command
        log_activity(request, "out", "openai", f"action={command.action}")

        def respond(status: str, message: str, *, log_status: str | None = None) -> dict[str, str]:
            log_activity(request, "out", "backend", f"action={command.action} status={status}")
            voice_log.record(
                transcript=transcript,
                command=command,
                interpret_source=interpretation.source,
                status=log_status or ("no_match" if command.action == "no_match" else status),
                response_message=message,
                audio_seconds=body.audio_seconds,
                wake_score=body.wake_score,
            )
            return {"status": status, "message": message}

        if command.action == "no_match":
            return respond("failed", "I don't know that command yet.", log_status="no_match")
        if command.action == "spotify.play_artist":
            artist = request.app.state.spotify_service.play_artist(command.artist or "")
            return respond("success", f"Playing {artist}.")
        if command.action == "spotify.pause":
            request.app.state.spotify_service.pause()
            return respond("success", "Music stopped.")
        if command.action in {"system.volume_up", "system.volume_down"}:
            volume = request.app.state.pi_volume_service.adjust("up" if command.action == "system.volume_up" else "down")
            return respond("success", f"Raspberry Pi volume {volume} percent.")
        if command.action == "system.volume_set":
            volume = request.app.state.pi_volume_service.set(command.volume_percent or 0)
            return respond("success", f"Raspberry Pi volume {volume} percent.")
        if command.action == "openclaw.send_message":
            request.app.state.openclaw_service.send(command.message or "")
            return respond("success", "Sent to Chili.")
        result = request.app.state.light_service.set_state(
            "on" if command.action == "light.turn_on" else "off", "voice"
        )
        return respond(result.status, result.message)
    except RuntimeError as error:
        logger.info("Voice Spotify command failed: %s", error)
        log_activity(request, "out", "backend", f"status=failed detail={error}")
        voice_log.record(
            transcript=transcript,
            command=interpretation.command if interpretation else None,
            interpret_source=interpretation.source if interpretation else None,
            status="failed",
            response_message=str(error),
            audio_seconds=body.audio_seconds,
            wake_score=body.wake_score,
            failure_stage="execute",
        )
        return {"status": "failed", "message": str(error)}
    except (httpx.HTTPError, ValueError):
        logger.exception("Voice Spotify command failed")
        log_activity(request, "out", "backend", "status=failed detail=spotify")
        voice_log.record(
            transcript=transcript,
            command=interpretation.command if interpretation else None,
            interpret_source=interpretation.source if interpretation else None,
            status="failed",
            response_message="Spotify could not complete that command.",
            audio_seconds=body.audio_seconds,
            wake_score=body.wake_score,
            failure_stage="execute",
        )
        return {"status": "failed", "message": "Spotify could not complete that command."}
    except Exception:
        logger.exception("Unexpected voice command failure")
        log_activity(request, "out", "backend", "status=failed detail=unexpected")
        voice_log.record(
            transcript=transcript,
            command=interpretation.command if interpretation else None,
            interpret_source=interpretation.source if interpretation else None,
            status="failed",
            response_message="The voice command could not complete.",
            audio_seconds=body.audio_seconds,
            wake_score=body.wake_score,
            failure_stage="execute",
        )
        return {"status": "failed", "message": "The voice command could not complete."}


def _voice_log_response(entry) -> VoiceLogResponse:
    return VoiceLogResponse(
        id=entry.id,
        occurred_at=entry.occurred_at,
        transcript=entry.transcript,
        action=entry.action,
        interpret_source=entry.interpret_source,
        artist=entry.artist,
        volume_percent=entry.volume_percent,
        intent_message=entry.intent_message,
        status=entry.status,
        response_message=entry.response_message,
        audio_seconds=entry.audio_seconds,
        wake_score=entry.wake_score,
        failure_stage=entry.failure_stage,
    )


@api_router.post("/voice/logs", response_model=VoiceLogResponse)
async def create_voice_log(request: Request, body: VoiceLogRequest) -> VoiceLogResponse:
    from app.domain.voice_commands import VoiceCommand

    command = None
    if body.action:
        command = VoiceCommand(
            body.action,
            artist=body.artist,
            volume_percent=body.volume_percent,
            message=body.intent_message,
        )
    entry = request.app.state.voice_log_service.record(
        transcript=body.transcript,
        command=command,
        interpret_source=body.interpret_source,
        status=body.status,
        response_message=body.response_message,
        audio_seconds=body.audio_seconds,
        wake_score=body.wake_score,
        failure_stage=body.failure_stage,
    )
    return _voice_log_response(entry)


@api_router.get("/voice/logs", response_model=list[VoiceLogResponse])
async def list_voice_logs(
    request: Request,
    days: int = Query(default=30, ge=1, le=365),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[VoiceLogResponse]:
    entries = request.app.state.voice_log_service.recent(days=days, limit=limit)
    return [_voice_log_response(entry) for entry in entries]


@api_router.get("/voice/commands")
async def voice_commands() -> dict[str, object]:
    from app.domain.voice_commands import VOICE_COMMANDS

    return {"commands": VOICE_COMMANDS}


@api_router.get("/voice/status", response_model=VoiceStateResponse)
async def voice_status(request: Request) -> VoiceStateResponse:
    snapshot = request.app.state.voice_state_service.current()
    return VoiceStateResponse(
        state=snapshot.state,
        updated_at=snapshot.updated_at,
        transcript=snapshot.transcript,
        message=snapshot.message,
    )


@api_router.get("/voice/events", response_model=list[VoiceEventResponse])
async def voice_events(request: Request, limit: int = Query(default=30, ge=1, le=80)) -> list[VoiceEventResponse]:
    return _activity_responses(request, limit)


@api_router.get("/activity/events", response_model=list[ActivityEventResponse])
async def activity_events(request: Request, limit: int = Query(default=40, ge=1, le=80)) -> list[ActivityEventResponse]:
    return _activity_responses(request, limit)


@api_router.post("/voice/events", response_model=VoiceEventResponse)
async def create_voice_event(request: Request, body: VoiceEventRequest) -> VoiceEventResponse:
    feed = request.app.state.activity_feed_service
    feed.add_event(body.direction, body.service, body.detail)
    event = feed.recent_events(1)[-1]
    return VoiceEventResponse(
        at=event.at,
        direction=event.direction,
        service=event.service,
        detail=event.detail,
    )


@api_router.post("/voice/status", response_model=VoiceStateResponse)
async def update_voice_status(request: Request, body: VoiceStateRequest) -> VoiceStateResponse:
    request.app.state.voice_state_service.set_state(body.state, body.transcript, body.message)
    snapshot = request.app.state.voice_state_service.current()
    return VoiceStateResponse(
        state=snapshot.state,
        updated_at=snapshot.updated_at,
        transcript=snapshot.transcript,
        message=snapshot.message,
    )
