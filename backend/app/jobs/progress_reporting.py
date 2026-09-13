import asyncio
import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.settings import settings
from app.database.models import ProgressReportPublication
from app.database.session import SessionLocal
from app.domain.notion import NotionService
from app.domain.progress_reports import ProgressReportService

logger = logging.getLogger(__name__)
PROGRESS_REPORT_POLL_SECONDS = 60 * 60


def publish_due_progress_reports(
    notion: NotionService,
    reports: ProgressReportService,
    session_factory=SessionLocal,
    now: datetime | None = None,
) -> None:
    if not notion.progress_configured():
        return
    today = (now or datetime.now(UTC)).astimezone(ZoneInfo(settings.timezone)).date()
    for report in reports.completed_periods(today):
        with session_factory() as session:
            if session.get(ProgressReportPublication, report.key) is not None:
                continue
        page_id = notion.publish_progress(report)
        with session_factory() as session:
            session.merge(ProgressReportPublication(
                period_key=report.key,
                notion_page_id=page_id,
                published_at=datetime.now(UTC),
            ))
            session.commit()


async def run_progress_reporting(notion: NotionService, reports: ProgressReportService) -> None:
    while True:
        try:
            await asyncio.to_thread(publish_due_progress_reports, notion, reports)
        except Exception:
            logger.exception("Progress reporting tick failed")
        await asyncio.sleep(PROGRESS_REPORT_POLL_SECONDS)
