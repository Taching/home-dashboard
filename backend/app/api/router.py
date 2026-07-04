import asyncio
from datetime import UTC, date, datetime
import hmac
import logging
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.core.settings import settings

api_router = APIRouter()
logger = logging.getLogger(__name__)

ALLOWED_INTENTS = {
    "light.turn_on",
    "light.turn_off",
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


class CommandResponse(BaseModel):
    status: Literal["success", "failed"]
    intent: str
    message: str | None = None
    light: LightResponse | None = None


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


class VoiceTranscriptRequest(BaseModel):
    text: str


class VoiceStateRequest(BaseModel):
    state: Literal["idle", "listening", "thinking", "complete", "error"]
    transcript: str | None = Field(default=None, max_length=500)
    message: str | None = Field(default=None, max_length=200)


class VoiceStateResponse(BaseModel):
    state: Literal["offline", "idle", "listening", "thinking", "complete", "error"]
    updated_at: datetime | None
    transcript: str | None
    message: str | None


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


@api_router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, object]:
    sensor = request.app.state.sensor_service
    light = request.app.state.light_service.snapshot()
    spotify_status = request.app.state.spotify_service.status()
    openclaw_status = request.app.state.openclaw_service.status()
    system_status = request.app.state.system_status_service.snapshot()
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
        },
        "display": {"state": "visible"},
        "integrations": {
            "sensor": sensor.status(),
            "broadlink": "ready" if light.available else "unavailable",
            "calendar": request.app.state.calendar_bridge_service.today()[0],
            "notion": request.app.state.notion_service.status(),
            "spotify": spotify_status,
            "openclaw": openclaw_status,
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
    return _calendar_response(
        *request.app.state.calendar_bridge_service.events_for_range(start, days)
    )


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


@api_router.get("/notion/today", response_model=NotionTodayResponse)
async def notion_today(request: Request) -> NotionTodayResponse:
    status, synced_at, tasks = request.app.state.notion_service.today()
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
    return SpotifyNowPlayingResponse(**request.app.state.spotify_service.now_playing())


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
    except Exception as error:
        raise HTTPException(status_code=503, detail="Spotify playback transfer failed.") from error
    return {"status": "success"}


@api_router.post("/spotify/device")
async def spotify_device(request: Request, body: SpotifyTransferRequest) -> dict[str, str]:
    request.app.state.spotify_service.register_device(body.device_id)
    return {"status": "success"}


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

    light = api_request.app.state.light_service
    if request.intent in {"light.turn_on", "light.turn_off"}:
        result = light.set_state(
            "on" if request.intent == "light.turn_on" else "off", request.source
        )
        return CommandResponse(
            status=result.status,
            intent=request.intent,
            message=result.message,
            light=LightResponse(
                last_command_state=result.light.last_command_state,
                last_command_at=result.light.last_command_at,
                available=result.light.available,
            ),
        )

    return CommandResponse(
        status="failed",
        intent=request.intent,
        message="This dashboard command is not configured yet.",
    )


@api_router.post("/voice/transcripts")
async def voice_transcript(request: Request, body: VoiceTranscriptRequest) -> dict[str, str]:
    try:
        command = request.app.state.voice_command_interpreter.interpret(body.text)
        if command.action == "no_match":
            return {"status": "failed", "message": "I don't know that command yet."}
        if command.action == "spotify.play_artist":
            artist = request.app.state.spotify_service.play_artist(command.artist or "")
            return {"status": "success", "message": f"Playing {artist}."}
        if command.action == "spotify.pause":
            request.app.state.spotify_service.pause()
            return {"status": "success", "message": "Music stopped."}
        if command.action in {"system.volume_up", "system.volume_down"}:
            volume = request.app.state.pi_volume_service.adjust("up" if command.action == "system.volume_up" else "down")
            return {"status": "success", "message": f"Raspberry Pi volume {volume} percent."}
        if command.action == "system.volume_set":
            volume = request.app.state.pi_volume_service.set(command.volume_percent or 0)
            return {"status": "success", "message": f"Raspberry Pi volume {volume} percent."}
        if command.action == "openclaw.send_message":
            request.app.state.openclaw_service.send(command.message or "")
            return {"status": "success", "message": "Sent to Chili."}
        result = request.app.state.light_service.set_state(
            "on" if command.action == "light.turn_on" else "off", "voice"
        )
        return {"status": result.status, "message": result.message}
    except RuntimeError as error:
        logger.info("Voice Spotify command failed: %s", error)
        return {"status": "failed", "message": str(error)}
    except (httpx.HTTPError, ValueError):
        logger.exception("Voice Spotify command failed")
        return {"status": "failed", "message": "Spotify could not complete that command."}
    except Exception:
        logger.exception("Unexpected voice command failure")
        return {"status": "failed", "message": "The voice command could not complete."}


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
