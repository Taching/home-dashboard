from __future__ import annotations

from datetime import UTC, datetime, timedelta
from threading import Lock

from app.database.models import ChiliNotifyDedupe
from app.database.session import SessionLocal


class ChiliNotifyService:
    """Deduped OpenClaw/Telegram notifications for dashboard-triggered alerts."""

    def __init__(self, session_factory=SessionLocal, ttl_seconds: int = 86_400) -> None:
        self._session_factory = session_factory
        self._ttl = timedelta(seconds=ttl_seconds)
        self._memory: dict[str, datetime] = {}
        self._in_flight: set[str] = set()
        self._lock = Lock()

    def should_send(self, dedupe_key: str) -> bool:
        now = datetime.now(UTC)
        with self._lock:
            cached = self._memory.get(dedupe_key)
            if cached is not None and now - cached < self._ttl:
                return False
            if dedupe_key in self._in_flight:
                return False

            with self._session_factory() as session:
                row = session.get(ChiliNotifyDedupe, dedupe_key)
                if row is not None:
                    sent_at = row.sent_at.replace(tzinfo=UTC) if row.sent_at.tzinfo is None else row.sent_at.astimezone(UTC)
                    if now - sent_at < self._ttl:
                        self._memory[dedupe_key] = sent_at
                        return False
            self._in_flight.add(dedupe_key)
            return True

    def mark_sent(self, dedupe_key: str) -> None:
        now = datetime.now(UTC)
        with self._lock:
            with self._session_factory() as session:
                row = session.get(ChiliNotifyDedupe, dedupe_key)
                if row is not None:
                    row.sent_at = now
                else:
                    session.add(ChiliNotifyDedupe(dedupe_key=dedupe_key, sent_at=now))
                session.commit()
            self._memory[dedupe_key] = now
            self._in_flight.discard(dedupe_key)

    def release(self, dedupe_key: str) -> None:
        with self._lock:
            self._in_flight.discard(dedupe_key)
