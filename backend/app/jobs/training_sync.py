import asyncio
import logging

from app.domain.training.notion_sync import TrainingNotionSync

logger = logging.getLogger(__name__)
TRAINING_SYNC_SECONDS = 5 * 60


async def run_training_sync(notion: TrainingNotionSync) -> None:
    while True:
        try:
            await asyncio.to_thread(notion.sync_due)
        except Exception:
            logger.exception("Training Notion sync tick failed")
        await asyncio.sleep(TRAINING_SYNC_SECONDS)
