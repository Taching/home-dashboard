from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Literal

ActivityDirection = Literal["in", "out", "info"]


@dataclass(frozen=True)
class ActivityEvent:
    at: datetime
    direction: ActivityDirection
    service: str
    detail: str


class ActivityFeedService:
    """Ephemeral ring buffer of recent dashboard activity for the live terminal UI."""

    def __init__(self, maxlen: int = 80) -> None:
        self._events: deque[ActivityEvent] = deque(maxlen=maxlen)
        self._dedupe: dict[str, str] = {}
        self._lock = Lock()

    def add_event(
        self,
        direction: ActivityDirection,
        service: str,
        detail: str,
        *,
        dedupe_key: str | None = None,
    ) -> None:
        detail = " ".join(detail.split())
        if not detail:
            return
        service = service.strip().lower()[:32] or "app"
        detail = detail[:240]
        with self._lock:
            if dedupe_key is not None:
                fingerprint = f"{service}:{direction}:{dedupe_key}"
                if fingerprint in self._dedupe:
                    return
                self._dedupe[fingerprint] = detail
            self._events.append(
                ActivityEvent(
                    at=datetime.now(UTC),
                    direction=direction,
                    service=service,
                    detail=detail,
                )
            )

    def recent_events(self, limit: int = 40) -> list[ActivityEvent]:
        with self._lock:
            return list(self._events)[-limit:]
