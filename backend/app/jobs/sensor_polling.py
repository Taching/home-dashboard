import asyncio
import logging

from app.core.settings import settings
from app.domain.sensors import SensorService

logger = logging.getLogger(__name__)


async def run_sensor_poller(service: SensorService) -> None:
    """Poll immediately, then continue even when the device is unavailable."""
    while True:
        await asyncio.to_thread(service.poll)
        await asyncio.sleep(settings.sensor_poll_interval_seconds)
