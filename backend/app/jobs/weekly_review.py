import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from app.core.settings import settings
from app.domain.chili_notify import ChiliNotifyService
from app.domain.weekly import WeeklyService

logger = logging.getLogger(__name__)

WEEKLY_POLL_SECONDS = 60


def maybe_send_weekly_review(
    *,
    weekly: WeeklyService,
    notify_service: ChiliNotifyService,
    openclaw,
    public_url: Callable[[str], str],
    now: datetime | None = None,
) -> str | None:
    monday = weekly.reminder_due(now)
    if monday is None:
        return None
    if weekly.review_for(monday - timedelta(days=1)) is not None:
        return None
    if not getattr(openclaw, "configured", lambda: False)():
        return None
    dedupe_key = f"weekly-review-{monday.isoformat()}"
    if not notify_service.should_send(dedupe_key):
        return None
    message = weekly.reminder_message(monday, public_url(f"/daily/{monday.isoformat()}"))
    try:
        notify = getattr(openclaw, "notify_user", None)
        result = notify(message) if callable(notify) else openclaw.send(message)
        delivery = result.get("delivery_status") if isinstance(result, dict) else None
        if delivery not in {None, "sent", "delivered", "ok"}:
            raise RuntimeError(f"OpenClaw delivery was {delivery}")
        notify_service.mark_sent(dedupe_key)
        return "sent"
    except Exception:
        notify_service.release(dedupe_key)
        logger.exception("Monday check-in reminder failed")
        return "failed"


async def run_weekly_review_reminder(application) -> None:
    while True:
        try:
            weekly = application.state.weekly_service
            base = settings.public_base_url()
            maybe_send_weekly_review(
                weekly=weekly,
                notify_service=application.state.chili_notify_service,
                openclaw=application.state.openclaw_service,
                public_url=lambda path: f"{base}{path}",
            )
        except Exception:
            logger.exception("Monday check-in reminder tick failed")
        await asyncio.sleep(WEEKLY_POLL_SECONDS)
