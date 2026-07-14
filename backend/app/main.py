import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.core.settings import settings
from app.database.session import initialise_database
from app.domain.activity_feed import ActivityFeedService
from app.domain.chili_notify import ChiliNotifyService
from app.domain.dashboard_context import DashboardContextProvider
from app.domain.lights import LightService
from app.domain.openclaw import OpenClawService
from app.domain.calendar_bridge import CalendarBridgeService
from app.domain.notion import NotionService
from app.domain.sensors import SensorService
from app.domain.spotify import SpotifyService
from app.domain.bluetooth_audio import BluetoothAudioService
from app.domain.system_status import SystemStatusService
from app.domain.weather import WeatherService
from app.domain.voice_log import VoiceLogService
from app.domain.voice_state import VoiceStateService
from app.domain.voice_commands import VoiceCommandInterpreter
from app.domain.system_volume import PiVolumeService
from app.domain.water_pump import WaterPumpService
from app.domain.walkingpad import WalkingPadService
from app.domain.db_read import DbReadService
from app.domain.display import DisplayService
from app.jobs.display_scheduler import run_display_scheduler
from app.jobs.sensor_polling import run_sensor_poller


@asynccontextmanager
async def lifespan(application: FastAPI):
    initialise_database()
    sensor_service = SensorService()
    sensor_service.restore_latest()
    application.state.sensor_service = sensor_service
    light_service = LightService()
    light_service.restore_latest()
    application.state.light_service = light_service
    application.state.calendar_bridge_service = CalendarBridgeService()
    application.state.walkingpad_service = WalkingPadService()
    application.state.db_read_service = DbReadService()
    application.state.notion_service = NotionService()
    application.state.spotify_service = SpotifyService()
    application.state.activity_feed_service = ActivityFeedService()
    application.state.chili_notify_service = ChiliNotifyService()
    application.state.voice_state_service = VoiceStateService()
    application.state.weather_service = WeatherService()
    application.state.voice_log_service = VoiceLogService()
    application.state.voice_command_interpreter = VoiceCommandInterpreter()
    application.state.pi_volume_service = PiVolumeService()
    application.state.system_status_service = SystemStatusService()
    application.state.bluetooth_audio_service = BluetoothAudioService()
    water_pump_service = WaterPumpService()
    water_pump_service.restore_latest()
    application.state.water_pump_service = water_pump_service
    application.state.openclaw_service = OpenClawService(
        DashboardContextProvider(
            sensor_service=sensor_service,
            light_service=light_service,
            calendar_service=application.state.calendar_bridge_service,
            notion_service=application.state.notion_service,
            spotify_service=application.state.spotify_service,
            walkingpad_service=application.state.walkingpad_service,
        )
    )
    display_service = DisplayService()
    display_service.restore()
    application.state.display_service = display_service
    poller = asyncio.create_task(run_sensor_poller(sensor_service))
    display_scheduler = asyncio.create_task(run_display_scheduler(display_service))
    try:
        yield
    finally:
        display_scheduler.cancel()
        poller.cancel()
        for task in (display_scheduler, poller):
            try:
                await task
            except asyncio.CancelledError:
                pass


app = FastAPI(
    title="Chili Home Dashboard API",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(api_router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": settings.app_name, "status": "ok"}
