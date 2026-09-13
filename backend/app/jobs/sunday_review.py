import asyncio
import logging
from collections.abc import Callable
from datetime import datetime

from app.domain.chili_notify import ChiliNotifyService
from app.domain.weekly import WeeklyService

logger = logging.getLogger(__name__)

SUNDAY_POLL_SECONDS = 60


def maybe_send_sunday_review(
    *,
    weekly: WeeklyService,
    notify_service: ChiliNotifyService,
    openclaw,
    public_url: Callable[[str], str],
    now: datetime | None = None,
) -> str | None:
    sunday = weekly.reminder_due(now)
    if sunday is None:
        return None
    if weekly.review_for(sunday) is not None:
        return None
    if not getattr(openclaw, "configured", lambda: False)():
        return None
    dedupe_key = f"sunday-review-{sunday.isoformat()}"
    if not notify_service.should_send(dedupe_key):
        return None
    message = weekly.reminder_message(sunday, public_url(f"/daily/{sunday.isoformat()}"))
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
        logger.exception("Sunday review reminder failed")
        return "failed"


async def run_sunday_review_reminder(application) -> None:
    while True:
        try:
            weekly = application.state.weekly_service
            training = application.state.training_service
            maybe_send_sunday_review(
                weekly=weekly,
                notify_service=application.state.chili_notify_service,
                openclaw=application.state.openclaw_service,
                public_url=training.public_url,
            )
        except Exception:
            logger.exception("Sunday review reminder tick failed")
        await asyncio.sleep(SUNDAY_POLL_SECONDS)
