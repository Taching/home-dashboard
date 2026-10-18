import asyncio
import logging

from app.core.settings import settings
from app.domain.garmin import GarminService

logger = logging.getLogger(__name__)

# Garmin rate-limits aggressively; back off for two hours after a 429.
RATE_LIMIT_BACKOFF_SECONDS = 2 * 60 * 60


async def run_garmin_sync(garmin: GarminService) -> None:
    while True:
        delay = settings.garmin_poll_seconds
        try:
            if garmin.configured():
                await asyncio.to_thread(garmin.sync_recent)
        except Exception as error:
            if "TooManyRequests" in type(error).__name__:
                delay = RATE_LIMIT_BACKOFF_SECONDS
            logger.warning("Garmin sync failed: %s", garmin.last_error or error)
        await asyncio.sleep(delay)
