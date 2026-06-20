from datetime import UTC, date, datetime, timedelta
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database.session import Base
from app.domain.calendar_bridge import CalendarBridgeService, CalendarEvent


class CalendarBridgeServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        self.service = CalendarBridgeService(
            session_factory=self.session_factory, bridge_token="test-token"
        )
        self.now = datetime.now(UTC)

    def test_snapshot_preserves_all_day_and_timed_events_in_requested_range(self) -> None:
        self.service.replace_snapshot(
            [
                CalendarEvent(
                    external_id="all-day", title="Holiday",
                    start_at=datetime(2026, 6, 21, 15, tzinfo=UTC),
                    end_at=datetime(2026, 6, 22, 15, tzinfo=UTC), is_all_day=True,
                ),
                CalendarEvent(
                    external_id="meeting", title="Standup",
                    start_at=datetime(2026, 6, 22, 1, tzinfo=UTC),
                    end_at=datetime(2026, 6, 22, 2, tzinfo=UTC),
                ),
            ],
            self.now,
        )

        status, _, events = self.service.events_for_range(date(2026, 6, 22), 1)

        self.assertEqual(status, "ready")
        self.assertEqual([event.external_id for event in events], ["all-day", "meeting"])
        self.assertTrue(events[0].is_all_day)

    def test_snapshot_replaces_previous_events(self) -> None:
        self.service.replace_snapshot(
            [CalendarEvent("old", "Old", self.now, self.now + timedelta(hours=1))], self.now
        )
        self.service.replace_snapshot(
            [CalendarEvent("new", "New", self.now, self.now + timedelta(hours=1))], self.now
        )

        _, _, events = self.service.events_for_range(self.now.date(), 1)

        self.assertEqual([event.external_id for event in events], ["new"])

    def test_stale_snapshot_is_marked_unavailable_but_kept_visible(self) -> None:
        self.service.replace_snapshot(
            [CalendarEvent("event", "Event", self.now, self.now + timedelta(hours=1))],
            self.now - timedelta(minutes=16),
        )

        status, _, events = self.service.events_for_range(self.now.date(), 1)

        self.assertEqual(status, "unavailable")
        self.assertEqual(len(events), 1)
