from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select

from app.core.settings import settings
from app.database.models import CalendarBridgeEvent, CalendarBridgeSync
from app.database.session import SessionLocal

APPLE_CALENDAR_SOURCE = "apple_calendar"
STALE_AFTER = timedelta(minutes=15)


@dataclass(frozen=True)
class CalendarEvent:
    external_id: str
    title: str
    start_at: datetime
    end_at: datetime
    is_all_day: bool = False


class CalendarBridgeService:
    def __init__(self, session_factory=SessionLocal, bridge_token: str | None = None) -> None:
        self._session_factory = session_factory
        self._bridge_token = bridge_token
        self._timezone = ZoneInfo(settings.timezone)
        self._sync_fingerprint: str | None = None
        self._fetch_fingerprints: dict[str, str] = {}

    @staticmethod
    def events_fingerprint(events: list[CalendarEvent]) -> str:
        parts = sorted(
            f"{event.external_id}|{event.title}|{event.start_at.isoformat()}|{event.end_at.isoformat()}|{event.is_all_day}"
            for event in events
        )
        digest = hashlib.sha256("\n".join(parts).encode()).hexdigest()[:16]
        return f"{len(parts)}:{digest}"

    def should_log_sync(self, events: list[CalendarEvent]) -> bool:
        fingerprint = self.events_fingerprint(events)
        if fingerprint == self._sync_fingerprint:
            return False
        self._sync_fingerprint = fingerprint
        return True

    def should_log_fetch(self, cache_key: str, events: list[CalendarEvent]) -> bool:
        fingerprint = self.events_fingerprint(events)
        if self._fetch_fingerprints.get(cache_key) == fingerprint:
            return False
        self._fetch_fingerprints[cache_key] = fingerprint
        return True

    def configured(self) -> bool:
        return bool(self._bridge_token if self._bridge_token is not None else settings.apple_calendar_bridge_token)

    def replace_snapshot(self, events: list[CalendarEvent], synced_at: datetime) -> None:
        with self._session_factory() as session:
            session.execute(
                delete(CalendarBridgeEvent).where(
                    CalendarBridgeEvent.source == APPLE_CALENDAR_SOURCE
                )
            )
            session.add_all(
                [
                    CalendarBridgeEvent(
                        source=APPLE_CALENDAR_SOURCE,
                        external_id=event.external_id,
                        title=event.title,
                        start_at=event.start_at,
                        end_at=event.end_at,
                        is_all_day=event.is_all_day,
                    )
                    for event in events
                ]
            )
            sync = session.get(CalendarBridgeSync, APPLE_CALENDAR_SOURCE)
            if sync is None:
                session.add(CalendarBridgeSync(source=APPLE_CALENDAR_SOURCE, synced_at=synced_at))
            else:
                sync.synced_at = synced_at
            session.commit()

    def events_for_range(
        self, start_date: date, days: int
    ) -> tuple[str, datetime | None, list[CalendarEvent]]:
        status, synced_at = self._status()
        if status == "not_configured":
            return status, synced_at, []
        start_at, end_at = self._range_bounds(start_date, days)
        with self._session_factory() as session:
            rows = session.scalars(
                select(CalendarBridgeEvent)
                .where(CalendarBridgeEvent.source == APPLE_CALENDAR_SOURCE)
                .where(CalendarBridgeEvent.start_at < end_at)
                .where(CalendarBridgeEvent.end_at > start_at)
                .order_by(CalendarBridgeEvent.start_at, CalendarBridgeEvent.end_at)
            ).all()
            return status, synced_at, [
                CalendarEvent(
                    external_id=row.external_id,
                    title=row.title,
                    start_at=self._as_utc(row.start_at),
                    end_at=self._as_utc(row.end_at),
                    is_all_day=row.is_all_day,
                )
                for row in rows
            ]

    def today(self) -> tuple[str, datetime | None, list[CalendarEvent]]:
        return self.events_for_range(datetime.now(self._timezone).date(), 1)

    def upcoming(self, days: int) -> tuple[str, datetime | None, list[CalendarEvent]]:
        return self.events_for_range(datetime.now(self._timezone).date(), days)

    def _status(self) -> tuple[str, datetime | None]:
        if not self.configured():
            return "not_configured", None
        with self._session_factory() as session:
            sync = session.get(CalendarBridgeSync, APPLE_CALENDAR_SOURCE)
            if sync is None:
                return "not_configured", None
            synced_at = self._as_utc(sync.synced_at)
            status = "ready" if datetime.now(UTC) - synced_at <= STALE_AFTER else "unavailable"
            return status, synced_at

    def _range_bounds(self, start_date: date, days: int) -> tuple[datetime, datetime]:
        start = datetime.combine(start_date, time.min, tzinfo=self._timezone)
        end = start + timedelta(days=days)
        return start.astimezone(UTC), end.astimezone(UTC)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
