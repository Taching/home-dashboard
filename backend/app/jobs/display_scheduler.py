import asyncio
import logging

from app.domain.display import DisplayService

logger = logging.getLogger(__name__)

DISPLAY_POLL_SECONDS = 30


async def run_display_scheduler(service: DisplayService) -> None:
    while True:
        try:
            await asyncio.to_thread(service.sync)
        except Exception:
            logger.exception("Display scheduler tick failed")
        await asyncio.sleep(DISPLAY_POLL_SECONDS)
