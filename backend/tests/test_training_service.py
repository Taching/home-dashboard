import unittest
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import TrainingReminder, TrainingSession
from app.database.session import Base
from app.domain.training.service import TrainingService


def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class TrainingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = factory()
        self.service = TrainingService(self.factory, timezone_name="Asia/Tokyo")
        self.now = datetime(2026, 9, 13, 15, tzinfo=UTC)  # Monday 00:00 JST
        self.service.bootstrap(self.now)

    def test_reconcile_is_idempotent(self) -> None:
        with self.factory() as session:
            before = [(row.id, row.revision) for row in session.scalars(select(TrainingSession)).all()]
            reminder_count = len(session.scalars(select(TrainingReminder)).all())

        self.service.reconcile(self.now)

        with self.factory() as session:
            after = [(row.id, row.revision) for row in session.scalars(select(TrainingSession)).all()]
            self.assertEqual(before, after)
            self.assertEqual(reminder_count, len(session.scalars(select(TrainingReminder)).all()))

    def test_overview_exposes_rolling_seven_day_plan(self) -> None:
        saturday = datetime(2026, 9, 12, 8, tzinfo=UTC)  # Saturday 17:00 JST
        service = TrainingService(self.factory, timezone_name="Asia/Tokyo")
        service.bootstrap(saturday)

        overview = service.overview(saturday)
        upcoming_dates = {
            datetime.fromisoformat(item["start_at"]).astimezone(service._timezone).date()
            for item in overview["upcoming"]
        }

        self.assertTrue(upcoming_dates)
        self.assertTrue(all(date(2026, 9, 12) <= item < date(2026, 9, 19) for item in upcoming_dates))
        self.assertTrue(any(item >= date(2026, 9, 14) for item in upcoming_dates))

    def test_moving_strength_does_not_recreate_original(self) -> None:
        overview = self.service.overview(self.now)
        strength_a = next(item for item in overview["week"] if item["planned_type"] == "strength_a")
        moved = datetime.fromisoformat(strength_a["start_at"]) + timedelta(days=1)

        self.service.update_session(strength_a["id"], start_at=moved, now=self.now)
        overview = self.service.overview(self.now)

        self.assertEqual(sum(item["planned_type"] == "strength_a" for item in overview["week"]), 1)

    def test_skipped_session_is_not_readded_to_same_day(self) -> None:
        overview = self.service.overview(self.now)
        strength_a = next(item for item in overview["week"] if item["planned_type"] == "strength_a")
        original_start = strength_a["start_at"]

        self.service.update_session(strength_a["id"], status="skipped", notes="work conflict", now=self.now)
        overview = self.service.overview(self.now)

        replacements = [item for item in overview["week"] if item["planned_type"] == "strength_a" and item["status"] == "planned"]
        self.assertTrue(all(item["start_at"] != original_start for item in replacements))

    def test_recovery_replacement_suppresses_original_workout(self) -> None:
        overview = self.service.overview(self.now)
        strength_a = next(item for item in overview["week"] if item["planned_type"] == "strength_a")

        self.service.replace_session(strength_a["id"], "recovery", now=self.now)
        overview = self.service.overview(self.now)

        self.assertFalse(any(item["planned_type"] == "strength_a" for item in overview["week"]))

    def test_bjj_capacity_uses_actual_round_metric(self) -> None:
        overview = self.service.overview(self.now)
        bjj = next(item for item in overview["week"] if item["planned_type"].startswith("bjj_"))

        self.service.update_session(
            bjj["id"], status="completed", final_round_quality=3,
            metrics=[{"metric_type": "bjj_rounds", "sequence": None, "value": 4, "unit": "rounds"}],
            now=self.now,
        )
        trend = self.service.overview(self.now)["trends"]["bjj_capacity"][-1]

        self.assertEqual(trend["rounds"], 4)
        self.assertEqual(trend["final_quality"], 3)


if __name__ == "__main__":
    unittest.main()
