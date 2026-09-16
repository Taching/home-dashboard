import unittest
from datetime import date

from app.domain.training.adaptation import MAX_LOAD_DELTA, analyze_week, clamp_adaptation
from app.domain.training.templates import WORKOUT_TEMPLATES, apply_adaptation
from app.domain.training.types import WeekAdaptation, WorkoutType


class AdaptationTests(unittest.TestCase):
    def test_easy_strength_b_increases_load_within_cap(self) -> None:
        result = analyze_week([
            {"planned_type": "strength_b", "status": "completed", "session_rpe": 6},
            {"planned_type": "strength_b", "status": "completed", "session_rpe": 6},
        ])
        self.assertGreater(result.strength_load_delta, 0)
        self.assertLessEqual(result.strength_load_delta, MAX_LOAD_DELTA)

    def test_hard_or_incomplete_strength_reduces_volume(self) -> None:
        result = analyze_week([
            {"planned_type": "strength_a", "status": "partial", "session_rpe": 9.5},
            {"planned_type": "strength_a", "status": "completed", "session_rpe": 10},
        ])
        self.assertLess(result.strength_volume_delta, 0)
        self.assertLessEqual(result.strength_load_delta, 0)

    def test_high_bjj_volume_reduces_accessories(self) -> None:
        result = analyze_week([
            {"planned_type": "bjj_normal", "status": "completed"},
            {"planned_type": "bjj_normal", "status": "completed"},
            {"planned_type": "bjj_hard", "status": "completed"},
        ])
        self.assertLess(result.zone2_minutes_delta, 0)
        self.assertLess(result.grip_sets_delta, 0)

    def test_grip_fatigue_reduces_grip_sets(self) -> None:
        result = analyze_week([
            {"planned_type": "bjj_normal", "status": "completed", "result": {"grip_fatigue": "HIGH"}},
            {"planned_type": "bjj_hard", "status": "completed", "result": {"grip_fatigue": "HIGH"}},
        ])
        self.assertEqual(result.grip_sets_delta, -1)

    def test_hard_bjj_quality_drop_protects_next_week(self) -> None:
        result = analyze_week([
            {"planned_type": "strength_b", "status": "completed", "session_rpe": 8},
            {"planned_type": "bjj_hard", "status": "completed", "result": {"technical_performance": "poor"}},
        ])
        self.assertTrue(result.extra_rest_before_hard_bjj)
        self.assertTrue(result.reduce_preceding_strength)

    def test_oversize_proposal_is_clamped(self) -> None:
        clamped = clamp_adaptation(WeekAdaptation(strength_load_delta=0.2, grip_sets_delta=5, zone2_minutes_delta=40))
        self.assertEqual(clamped.strength_load_delta, MAX_LOAD_DELTA)
        self.assertEqual(clamped.grip_sets_delta, 1)
        self.assertEqual(clamped.zone2_minutes_delta, 15)

    def test_adaptation_changes_template_load(self) -> None:
        base = WORKOUT_TEMPLATES[WorkoutType.STRENGTH_B]
        squat = next(item for item in base.exercises if item.name == "Deadlift")
        adapted = apply_adaptation(base, WeekAdaptation(strength_load_delta=0.05))
        deadlift = next(item for item in adapted.exercises if item.name == "Deadlift")
        self.assertGreater(deadlift.load_value or 0, squat.load_value or 0)

    def test_logging_actual_load_does_not_change_prescription(self) -> None:
        from datetime import UTC, date, datetime
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.database.models import TrainingExercise
        from app.database.session import Base
        from app.domain.training.service import TrainingService

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        service = TrainingService(factory, timezone_name="Asia/Tokyo")
        now = datetime(2026, 9, 13, 15, tzinfo=UTC)
        service.bootstrap(now)
        created = service.schedule_gym(date(2026, 9, 13), "strength_a", now=now)
        squat = next(item for item in created["exercises"] if item["name"] == "Back Squat")
        prescribed = squat["load_value"]
        service.log_session_result(
            created["id"],
            status="completed",
            session_rpe=6,
            exercises=[{"name": "Back Squat", "actual_load": 140, "completed": True, "done": True}],
            now=now,
        )
        after = service.session(created["id"])
        logged = next(item for item in after["exercises"] if item["name"] == "Back Squat")
        self.assertEqual(logged["load_value"], prescribed)
        self.assertEqual(after["status"], "completed")
        with factory() as session:
            row = session.scalar(select(TrainingExercise).where(TrainingExercise.session_id == created["id"]).where(TrainingExercise.name == "Back Squat"))
            self.assertEqual(row.load_value, prescribed)

    def test_rebuild_consumes_stored_adaptation(self) -> None:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        from app.domain.training.classes import MITA_CLASS_TEMPLATE
        from app.domain.training.scheduler import TrainingScheduler
        from app.domain.training.types import ExistingSession, SessionStatus

        tokyo = ZoneInfo("Asia/Tokyo")
        scheduler = TrainingScheduler("Asia/Tokyo")
        plan = scheduler.plan_week(
            date(2026, 9, 14),
            now=datetime(2026, 9, 14, 8, tzinfo=tokyo),
            class_template=MITA_CLASS_TEMPLATE,
            adaptation=WeekAdaptation(strength_load_delta=0.05),
            existing=(
                ExistingSession(
                    "sun-a", WorkoutType.STRENGTH_A,
                    datetime(2026, 9, 13, 7, 30, tzinfo=tokyo),
                    datetime(2026, 9, 13, 8, 30, tzinfo=tokyo),
                    SessionStatus.COMPLETED,
                ),
            ),
        )
        strength = next(item for item in plan.sessions if item.type == WorkoutType.STRENGTH_B)
        deadlift = next(item for item in strength.exercises if item.name == "Deadlift")
        base = next(item for item in WORKOUT_TEMPLATES[WorkoutType.STRENGTH_B].exercises if item.name == "Deadlift")
        self.assertGreater(deadlift.load_value or 0, base.load_value or 0)

    def test_completed_exercises_stay_frozen_after_rebuild(self) -> None:
        from datetime import UTC, datetime
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.database.models import TrainingExercise
        from app.database.session import Base
        from app.domain.training.service import TrainingService

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        service = TrainingService(factory, timezone_name="Asia/Tokyo")
        now = datetime(2026, 9, 13, 15, tzinfo=UTC)
        service.bootstrap(now)
        created = service.schedule_gym(date(2026, 9, 13), "strength_a", now=now)
        squat = next(item for item in created["exercises"] if item["name"] == "Back Squat")
        prescribed = squat["load_value"]
        service.log_session_result(
            created["id"],
            status="completed",
            session_rpe=6,
            exercises=[{"name": "Back Squat", "actual_load": 140, "completed": True, "done": True}],
            now=now,
        )
        service.reconcile(now)
        after = service.session(created["id"])
        self.assertEqual(after["status"], "completed")
        logged = next(item for item in after["exercises"] if item["name"] == "Back Squat")
        self.assertEqual(logged["load_value"], prescribed)
        with factory() as session:
            row = session.scalar(select(TrainingExercise).where(TrainingExercise.session_id == created["id"]).where(TrainingExercise.name == "Back Squat"))
            self.assertEqual(row.load_value, prescribed)

    def test_llm_without_key_keeps_default(self) -> None:
        from datetime import date
        from app.domain.training.llm import rerank_and_explain
        from app.domain.training.types import AthleteState, SchedulerInput, WorkoutType
        picked, reason = rerank_and_explain(
            (WorkoutType.BJJ_NORMAL, WorkoutType.STRENGTH_B),
            WorkoutType.BJJ_NORMAL,
            "Default pick.",
            SchedulerInput(today=date(2026, 9, 16), athlete_state=AthleteState()),
            date(2026, 9, 16),
        )
        self.assertEqual(picked, WorkoutType.BJJ_NORMAL)
        self.assertEqual(reason, "Default pick.")


if __name__ == "__main__":
    unittest.main()
