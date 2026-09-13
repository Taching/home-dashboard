import unittest
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

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

    def test_skipped_strength_a_is_not_automatically_made_up(self) -> None:
        overview = self.service.overview(self.now)
        strength_a = next(item for item in overview["week"] if item["planned_type"] == "strength_a")

        self.service.update_session(strength_a["id"], status="skipped", notes="work conflict", now=self.now)
        overview = self.service.overview(self.now)

        self.assertFalse(any(item["planned_type"] == "strength_a" and item["status"] == "planned" for item in overview["week"]))
        self.assertTrue(overview["tomorrow_prescription"])
        self.assertIn(overview["week_quality"], {"excellent", "good", "acceptable", "bad_planning"})

    def test_confirm_bjj_creates_a_timed_session_and_replans(self) -> None:
        day = date(2026, 9, 15)
        if not any(item["date"] == day.isoformat() for item in self.service.overview(self.now)["bjj_candidates"]):
            day = date.fromisoformat(self.service.overview(self.now)["bjj_candidates"][0]["date"])

        created = self.service.confirm_bjj(day, now=self.now)
        overview = self.service.overview(self.now)

        self.assertTrue(created["planned_type"].startswith("bjj_"))
        self.assertTrue(any(
            item["planned_type"].startswith("bjj_") and self.service._local_date(item["start_at"]) == day
            for item in overview["week"]
        ))
        self.assertFalse(any(item["date"] == day.isoformat() for item in overview["bjj_candidates"]))

    def test_sunday_gym_counts_as_coming_week_strength_a(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        sunday = datetime(2026, 9, 13, 12, tzinfo=tokyo)
        created = self.service.schedule_gym(date(2026, 9, 13), "strength_a", now=sunday)
        self.assertEqual(created["title"], "Gym (Strength A)")
        monday = datetime(2026, 9, 14, 8, tzinfo=tokyo)
        overview = self.service.overview(monday)
        planned_a = [
            item for item in overview["week"]
            if item["planned_type"] == "strength_a" and item["status"] == "planned"
        ]
        self.assertEqual(planned_a, [])

    def test_recovery_replacement_suppresses_original_workout(self) -> None:
        overview = self.service.overview(self.now)
        strength_a = next(item for item in overview["week"] if item["planned_type"] == "strength_a")

        self.service.replace_session(strength_a["id"], "recovery", now=self.now)
        overview = self.service.overview(self.now)

        self.assertFalse(any(item["planned_type"] == "strength_a" for item in overview["week"]))

    def test_skipped_monday_bjj_does_not_stack_tuesday_gym(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        monday = self.service.add_bjj(datetime(2026, 9, 14, 7, 30, tzinfo=tokyo), now=self.now)
        self.service.add_bjj(datetime(2026, 9, 15, 7, 30, tzinfo=tokyo), now=self.now)
        evening = datetime(2026, 9, 14, 12, tzinfo=UTC)
        self.service.update_session(monday["id"], status="skipped", notes="missed class", now=evening)
        overview = self.service.overview(evening)
        tuesday = [
            item for item in overview["week"]
            if self.service._local_date(item["start_at"]) == date(2026, 9, 15)
        ]
        self.assertEqual([item["planned_type"] for item in tuesday], ["bjj_normal"])

    def test_bjj_capacity_uses_actual_round_metric(self) -> None:
        bjj = self.service.add_bjj(datetime(2026, 9, 15, 7, 30, tzinfo=ZoneInfo("Asia/Tokyo")), now=self.now)

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
