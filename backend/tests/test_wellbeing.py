import unittest
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.domain.wellbeing import WellbeingService


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
        self.service.record(
            date(2026, 8, 24), trained=True, sober=True,
            now=datetime(2026, 8, 24, 13, tzinfo=UTC),
        )
        summary = self.service.record(
            date(2026, 8, 25), trained=True, sober=True,
            now=datetime(2026, 8, 25, 13, tzinfo=UTC),
        )

        self.assertEqual(summary.sober_days, 9)
        self.assertEqual(summary.workouts_this_week, 2)
        self.assertEqual(summary.week_start, date(2026, 8, 24))
        self.assertFalse(summary.checkin_stale)

    def test_partial_update_preserves_existing_answer_and_false_resets_streak(self) -> None:
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
        self.service.record(
            date(2026, 8, 24), gym=True, jiujitsu=False,
            now=datetime(2026, 8, 24, 13, tzinfo=UTC),
        )
        summary = self.service.record(
            date(2026, 8, 25), gym=False, jiujitsu=True,
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
