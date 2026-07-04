from fastapi import Request

from app.domain.activity_feed import ActivityFeedService, ActivityDirection


def activity_feed(request: Request) -> ActivityFeedService:
    return request.app.state.activity_feed_service


def log_activity(
    request: Request,
    direction: ActivityDirection,
    service: str,
    detail: str,
    *,
    dedupe_key: str | None = None,
) -> None:
    activity_feed(request).add_event(direction, service, detail, dedupe_key=dedupe_key)


def preview(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return f"{compact[: limit - 1]}…"
