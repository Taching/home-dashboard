from datetime import UTC, datetime, timedelta
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.settings import settings
from app.database.session import Base
from app.domain.calendar_bridge import CalendarEvent
from app.domain.walkingpad import WalkingPadService


class WalkingPadServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        self.session_factory = sessionmaker(bind=engine, expire_on_commit=False)
        self.service = WalkingPadService(
            session_factory=self.session_factory,
            bridge_token="test-token",
        )
        self.now = datetime(2026, 7, 6, 3, 0, tzinfo=UTC)

    def test_sync_and_roll_up_daily_totals(self) -> None:
        started = datetime(2026, 7, 6, 0, 30, tzinfo=UTC)
        self.service.sync_session(
            external_id="session-1",
            started_at=started,
            ended_at=datetime(2026, 7, 6, 1, 0, tzinfo=UTC),
            duration_seconds=1800,
            distance_km=1.2,
            steps=2200,
            calories=90.0,
            synced_at=self.now,
        )

        snapshot = self.service.today(self.now)

        self.assertEqual(snapshot.status, "ready")
        self.assertEqual(snapshot.total_minutes, 30.0)
        self.assertEqual(snapshot.total_distance_km, 1.2)
        self.assertEqual(snapshot.session_count, 1)
        self.assertFalse(snapshot.goal_met)

    def test_active_session_marks_walking_status(self) -> None:
        started = datetime(2026, 7, 6, 2, 30, tzinfo=UTC)
        self.service.sync_session(
            external_id="session-live",
            started_at=started,
            ended_at=None,
            duration_seconds=600,
            distance_km=0.4,
            steps=800,
            calories=20.0,
            synced_at=self.now,
        )

        snapshot = self.service.today(self.now)

        self.assertEqual(snapshot.status, "walking")
        self.assertIsNotNone(snapshot.active_session)
        self.assertEqual(snapshot.active_session.external_id, "session-live")

    def test_reminder_requires_gap_before_meeting_and_unmet_goal(self) -> None:
        started = datetime(2026, 7, 6, 0, 30, tzinfo=UTC)
        self.service.sync_session(
            external_id="session-1",
            started_at=started,
            ended_at=datetime(2026, 7, 6, 1, 0, tzinfo=UTC),
            duration_seconds=900,
            distance_km=0.5,
            steps=1000,
            calories=40.0,
            synced_at=self.now,
        )
        local_now = datetime(2026, 7, 6, 3, 0, tzinfo=UTC).astimezone(
            __import__("zoneinfo").ZoneInfo(settings.timezone)
        )
        next_meeting = CalendarEvent(
            external_id="meeting-1",
            title="Standup",
            start_at=local_now + timedelta(minutes=75),
            end_at=local_now + timedelta(minutes=105),
        )

        reminder = self.service.reminder([next_meeting], local_now.astimezone(UTC))

        self.assertTrue(reminder.active)
        self.assertIn("Standup", reminder.message)
        self.assertTrue(reminder.dedupe_key.startswith("walk:window:"))

    def test_reminder_skips_when_goal_met(self) -> None:
        started = datetime(2026, 7, 6, 0, 0, tzinfo=UTC)
        self.service.sync_session(
            external_id="session-1",
            started_at=started,
            ended_at=datetime(2026, 7, 6, 1, 30, tzinfo=UTC),
            duration_seconds=5400,
            distance_km=4.0,
            steps=7000,
            calories=300.0,
            synced_at=self.now,
        )
        local_now = datetime(2026, 7, 6, 3, 0, tzinfo=UTC)

        reminder = self.service.reminder([], local_now)

        self.assertFalse(reminder.active)


if __name__ == "__main__":
    unittest.main()
