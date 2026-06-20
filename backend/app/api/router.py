from datetime import UTC, date, datetime
import hmac
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.core.settings import settings

api_router = APIRouter()

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


class DashboardUiConfig(BaseModel):
    timezone: str
    sensor_stale_after_seconds: int
    dashboard_refresh_interval_seconds: int
    openclaw_refresh_interval_seconds: int
    readings_history_hours: int
    calendar_range_days: int


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


@api_router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@api_router.get("/dashboard")
async def dashboard(request: Request) -> dict[str, object]:
    sensor = request.app.state.sensor_service
    light = request.app.state.light_service.snapshot()
    spotify_status = request.app.state.spotify_service.status()
    openclaw_status = request.app.state.openclaw_service.status()
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
        "display": {"state": "visible"},
        "ui": DashboardUiConfig(
            timezone=settings.timezone,
            sensor_stale_after_seconds=settings.sensor_stale_after_seconds,
            dashboard_refresh_interval_seconds=settings.dashboard_refresh_interval_seconds,
            openclaw_refresh_interval_seconds=settings.openclaw_refresh_interval_seconds,
            readings_history_hours=settings.readings_history_hours,
            calendar_range_days=settings.calendar_range_days,
        ),
        "integrations": {
            "sensor": sensor.status(),
            "broadlink": "ready" if light.available else "unavailable",
            "calendar": request.app.state.calendar_bridge_service.today()[0],
            "notion": "not_configured",
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
async def notion_today() -> NotionTodayResponse:
    # The Notion integration populates this response in its own phase.
    return NotionTodayResponse(status="not_configured")


@api_router.get("/openclaw/messages", response_model=OpenClawConversationResponse)
async def openclaw_messages(request: Request) -> OpenClawConversationResponse:
    service = request.app.state.openclaw_service
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


@api_router.post("/openclaw/messages", response_model=OpenClawSendResponse)
async def send_openclaw_message(
    request: Request, body: OpenClawSendRequest
) -> OpenClawSendResponse:
    message = body.message.strip()
    if not message or len(message) > settings.openclaw_message_max_length:
        raise HTTPException(
            status_code=400,
            detail=f"Message must contain 1 to {settings.openclaw_message_max_length} characters.",
        )
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
    from app.domain.voice_commands import parse_voice_command

    command = parse_voice_command(body.text)
    if command is None:
        return {"status": "failed", "message": "I don't know that command yet."}
    try:
        if command.action == "spotify.play_artist":
            artist = request.app.state.spotify_service.play_artist(command.argument or "")
            return {"status": "success", "message": f"Playing {artist}."}
        direction = "up" if command.action == "spotify.volume_up" else "down"
        volume = request.app.state.spotify_service.change_volume(direction)
        return {"status": "success", "message": f"Volume {volume} percent."}
    except Exception:
        return {"status": "failed", "message": "Spotify could not complete that command."}
