import unittest
from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import TrainingSession
from app.database.session import Base
from app.domain.wellbeing import WellbeingService

TOKYO = ZoneInfo("Asia/Tokyo")


def add_completed_session(factory, day: date, planned_type: str) -> None:
    start = datetime.combine(day, time(7, 30), TOKYO).astimezone(UTC)
    with factory() as session:
        session.add(TrainingSession(
            id=str(uuid4()),
            planned_type=planned_type,
            status="completed",
            phase="build_october",
            planned_week_start=day - timedelta(days=day.weekday()),
            start_at=start,
            end_at=start + timedelta(minutes=60),
            estimated_minutes=60,
            intensity="normal",
            reason="test",
            created_at=start,
            updated_at=start,
        ))
        session.commit()


def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class WellbeingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = test_session_factory()
        self.service = WellbeingService(
            self.factory,
            timezone_name="Asia/Tokyo",
            sober_baseline_date=date(2026, 8, 23),
            sober_baseline_days=7,
        )

    def test_sober_streak_increments_and_training_counts_once_per_day(self) -> None:
        add_completed_session(self.factory, date(2026, 8, 24), "strength_a")
        add_completed_session(self.factory, date(2026, 8, 25), "bjj_normal")
        self.service.record(
            date(2026, 8, 24), sober=True,
            now=datetime(2026, 8, 24, 13, tzinfo=UTC),
        )
        summary = self.service.record(
            date(2026, 8, 25), sober=True,
            now=datetime(2026, 8, 25, 13, tzinfo=UTC),
        )

        self.assertEqual(summary.sober_days, 9)
        self.assertEqual(summary.workouts_this_week, 2)
        self.assertEqual(summary.week_start, date(2026, 8, 24))
        self.assertFalse(summary.checkin_stale)

    def test_partial_update_preserves_existing_answer_and_false_resets_streak(self) -> None:
        add_completed_session(self.factory, date(2026, 8, 24), "strength_b")
        self.service.record(
            date(2026, 8, 24), trained=True,
            now=datetime(2026, 8, 24, 13, tzinfo=UTC),
        )
        self.service.record(
            date(2026, 8, 24), sober=False,
            now=datetime(2026, 8, 24, 14, tzinfo=UTC),
        )
        summary = self.service.record(
            date(2026, 8, 25), sober=True,
            now=datetime(2026, 8, 25, 13, tzinfo=UTC),
        )

        self.assertEqual(summary.sober_days, 1)
        self.assertEqual(summary.workouts_this_week, 1)

    def test_unanswered_day_leaves_streak_unchanged_and_late_correction_recomputes(self) -> None:
        self.service.record(
            date(2026, 8, 25), sober=True,
            now=datetime(2026, 8, 25, 13, tzinfo=UTC),
        )
        before = self.service.summary(datetime(2026, 8, 26, 13, tzinfo=UTC))
        self.assertEqual(before.sober_days, 8)
        self.assertTrue(before.checkin_stale)

        after = self.service.record(
            date(2026, 8, 25), sober=False,
            now=datetime(2026, 8, 26, 14, tzinfo=UTC),
        )
        self.assertEqual(after.sober_days, 0)

    def test_training_rolls_over_on_monday_in_tokyo(self) -> None:
        self.service.record(
            date(2026, 8, 30), trained=True,
            now=datetime(2026, 8, 30, 12, tzinfo=UTC),
        )
        summary = self.service.summary(datetime(2026, 8, 30, 15, 1, tzinfo=UTC))

        self.assertEqual(summary.week_start, date(2026, 8, 31))
        self.assertEqual(summary.workouts_this_week, 0)
        self.assertFalse(summary.checkin_stale)

    def test_gym_and_jiujitsu_have_separate_weekly_goals(self) -> None:
        add_completed_session(self.factory, date(2026, 8, 24), "strength_a")
        add_completed_session(self.factory, date(2026, 8, 25), "bjj_normal")
        self.service.record(
            date(2026, 8, 24), sober=True,
            now=datetime(2026, 8, 24, 13, tzinfo=UTC),
        )
        summary = self.service.record(
            date(2026, 8, 25), sober=True,
            now=datetime(2026, 8, 25, 13, tzinfo=UTC),
        )

        self.assertEqual(summary.workouts_this_week, 2)
        self.assertEqual(summary.gym_this_week, 1)
        self.assertEqual(summary.jiujitsu_this_week, 1)
        self.assertEqual(summary.gym_weekly_goal, 3)
        self.assertEqual(summary.jiujitsu_weekly_goal, 3)

    def test_checkin_becomes_stale_after_nightly_grace_period(self) -> None:
        self.service.record(
            date(2026, 8, 29), trained=True, sober=True,
            now=datetime(2026, 8, 29, 13, tzinfo=UTC),
        )

        before_cutoff = self.service.summary(datetime(2026, 8, 30, 12, 59, tzinfo=UTC))
        after_cutoff = self.service.summary(datetime(2026, 8, 30, 13, tzinfo=UTC))

        self.assertFalse(before_cutoff.checkin_stale)
        self.assertTrue(after_cutoff.checkin_stale)

    def test_sober_followup_after_missed_evening(self) -> None:
        self.service.record(
            date(2026, 9, 11), sober=True,
            now=datetime(2026, 9, 11, 13, tzinfo=UTC),
        )
        morning = self.service.sober_nudges(datetime(2026, 9, 13, 2, tzinfo=UTC))
        self.assertEqual([nudge.kind for nudge in morning], ["followup"])
        self.assertEqual(morning[0].day, date(2026, 9, 12))
        self.assertIn("/daily/2026-09-12", morning[0].message)

        evening = self.service.sober_nudges(datetime(2026, 9, 13, 12, 30, tzinfo=UTC))
        self.assertEqual({nudge.kind for nudge in evening}, {"ask", "followup"})
        self.assertTrue(any(nudge.day == date(2026, 9, 13) and nudge.kind == "ask" for nudge in evening))

        self.service.record(
            date(2026, 9, 12), sober=True,
            now=datetime(2026, 9, 13, 3, tzinfo=UTC),
        )
        after = self.service.sober_nudges(datetime(2026, 9, 13, 2, 10, tzinfo=UTC))
        self.assertEqual(after, [])

    def test_weight_is_tracked_without_masking_a_missing_checkin(self) -> None:
        summary = self.service.record(
            date(2026, 8, 30), weight_kg=85.0,
            now=datetime(2026, 8, 30, 13, tzinfo=UTC),
        )
        self.assertEqual(summary.current_weight_kg, 85.0)
        self.assertEqual(summary.latest_weight_date, date(2026, 8, 30))
        self.assertTrue(summary.checkin_stale)


if __name__ == "__main__":
    unittest.main()
