import unittest
from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import DailyWellbeingCheckIn, TrainingSession, WalkingPadSession
from app.database.session import Base
from app.domain.progress_reports import ProgressReportService


class ProgressReportServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        self.factory = sessionmaker(bind=engine, expire_on_commit=False)
        self.service = ProgressReportService(self.factory, timezone_name="Asia/Tokyo")
        with self.factory() as session:
            session.add_all([
                DailyWellbeingCheckIn(
                    local_date=date(2026, 8, 31), gym=True, sober=True, weight_kg=85.0,
                    updated_at=datetime(2026, 8, 31, tzinfo=UTC), source="test",
                ),
                DailyWellbeingCheckIn(
                    local_date=date(2026, 9, 2), jiujitsu=True, sober=True, weight_kg=84.5,
                    updated_at=datetime(2026, 9, 2, tzinfo=UTC), source="test",
                ),
                WalkingPadSession(
                    external_id="walk", started_at=datetime(2026, 9, 2, 6, tzinfo=UTC),
                    ended_at=datetime(2026, 9, 2, 6, 30, tzinfo=UTC), duration_seconds=1800,
                    distance_km=2.5, steps=4000, calories=100,
                ),
                TrainingSession(
                    id="gym-1", planned_type="strength_a", status="completed",
                    phase="build_october", planned_week_start=date(2026, 8, 31),
                    start_at=datetime(2026, 8, 31, 7, 30, tzinfo=UTC),
                    end_at=datetime(2026, 8, 31, 8, 30, tzinfo=UTC),
                    estimated_minutes=60, intensity="normal", reason="test",
                    created_at=datetime(2026, 8, 31, tzinfo=UTC),
                    updated_at=datetime(2026, 8, 31, tzinfo=UTC),
                ),
                TrainingSession(
                    id="bjj-1", planned_type="bjj_normal", status="completed",
                    phase="build_october", planned_week_start=date(2026, 8, 31),
                    start_at=datetime(2026, 9, 2, 7, 30, tzinfo=UTC),
                    end_at=datetime(2026, 9, 2, 9, 0, tzinfo=UTC),
                    estimated_minutes=90, intensity="normal", reason="test",
                    created_at=datetime(2026, 9, 2, tzinfo=UTC),
                    updated_at=datetime(2026, 9, 2, tzinfo=UTC),
                ),
            ])
            session.commit()

    def test_aggregates_weekly_progress(self) -> None:
        report = self.service.report("Weekly", date(2026, 8, 31), date(2026, 9, 6))
        self.assertEqual(report.weight_kg, 84.5)
        self.assertEqual(report.weight_change_kg, -0.5)
        self.assertEqual(report.sober_days, 2)
        self.assertEqual(report.gym_sessions, 1)
        self.assertEqual(report.jiujitsu_sessions, 1)
        self.assertEqual(report.walk_minutes, 30)
        self.assertEqual(report.steps, 4000)

    def test_completed_periods_select_previous_week_and_month(self) -> None:
        weekly, monthly = self.service.completed_periods(date(2026, 9, 3))
        self.assertEqual((weekly.start, weekly.end), (date(2026, 8, 24), date(2026, 8, 30)))
        self.assertEqual((monthly.start, monthly.end), (date(2026, 8, 1), date(2026, 8, 31)))


if __name__ == "__main__":
    unittest.main()
