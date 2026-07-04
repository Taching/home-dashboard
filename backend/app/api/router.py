import asyncio
from datetime import UTC, date, datetime
import hmac
import logging
from typing import Literal

import httpx
from fastapi import APIRouter, Header, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.settings import settings
from app.api.activity_log import log_activity, preview

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


class CommandResponse(BaseModel):
    status: Literal["success", "failed", "skipped"]
    intent: str
    message: str | None = None
    light: LightResponse | None = None
    water_pump: WaterPumpResponse | None = None


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
        "display": {"state": "visible"},
        "integrations": {
            "sensor": sensor.status(),
            "broadlink": "ready" if light.available else "unavailable",
            "calendar": request.app.state.calendar_bridge_service.today()[0],
            "notion": request.app.state.notion_service.status(),
            "spotify": spotify_status,
            "openclaw": openclaw_status,
            "water_pump": "ready" if water_pump.available else "not_configured",
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
    response = _calendar_response(
        *request.app.state.calendar_bridge_service.events_for_range(start, days)
    )
    log_activity(
        request,
        "out",
        "calendar",
        f"{len(response.events)} events ({response.status})",
        dedupe_key=f"{start}:{days}:{response.status}:{len(response.events)}",
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

    request.app.state.calendar_bridge_service.replace_snapshot(
        [
            CalendarEvent(
                external_id=event.id,
                title=event.title,
                start_at=event.start_at,
                end_at=event.end_at,
                is_all_day=event.is_all_day,
            )
            for event in body.events
        ],
        body.synced_at,
    )
    log_activity(
        request,
        "in",
        "calendar",
        f"bridge sync {len(body.events)} events",
    )


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
    service = request.app.state.openclaw_service
    if not service.configured():
        return OpenClawSendResponse(status="failed", message="OpenClaw is not configured.")
    try:
        result = service.send(message)
        return OpenClawSendResponse(status="success", **result)
    except Exception as error:
        return OpenClawSendResponse(status="failed", message=str(error))


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
