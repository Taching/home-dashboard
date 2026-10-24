from datetime import UTC, date, datetime
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.models import (
    Base,
    TrainingExercise,
    TrainingExerciseProgress,
    TrainingExerciseResult,
    TrainingSession,
    TrainingSessionExerciseLog,
)
from app.domain.lift_history import LiftEntry, LiftHistoryService, estimated_1rm, mark_prs, parse_reps


def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def add_session(db, session_id, day, planned_type="strength_a", deload=False):
    start = datetime(day.year, day.month, day.day, 22, 0, tzinfo=UTC)  # 07:00 next day in Tokyo
    db.add(TrainingSession(
        id=session_id, planned_type=planned_type, status="completed", phase="base",
        planned_week_start=day, start_at=start, end_at=start, estimated_minutes=60,
        reason="", deload=deload, created_at=start, updated_at=start,
    ))


def add_result(db, session_id, position, name, load, reps, sets=3, rpe=7.0, unit="kg", status=None):
    exercise = TrainingExercise(session_id=session_id, position=position, name=name, load_value=load, load_unit=unit, sets=sets, reps=reps)
    db.add(exercise)
    db.flush()
    db.add(TrainingExerciseResult(
        exercise_id=exercise.id, session_id=session_id, actual_load=load, actual_sets=sets,
        actual_reps=reps, completed=True, rpe=rpe, status=status,
    ))


class PureFunctionTests(unittest.TestCase):
    def test_estimated_1rm_matches_the_weekly_analyzer_formula(self):
        self.assertEqual(estimated_1rm(100, 5), 116.7)
        self.assertIsNone(estimated_1rm(100, 12))
        self.assertIsNone(estimated_1rm(0, 5))
        self.assertIsNone(estimated_1rm(None, 5))

    def test_parse_reps_handles_every_stored_shape(self):
        self.assertEqual(parse_reps("5/5/5", 3), [5, 5, 5])
        self.assertEqual(parse_reps("3", 3), [3, 3, 3])
        self.assertEqual(parse_reps("6/leg", 2), [6, 6])
        self.assertEqual(parse_reps("6–8", 3), [6, 6, 6])
        self.assertEqual(parse_reps("30 sec hard / 30 sec easy", 10), [])
        self.assertEqual(parse_reps(None, 3), [])

    def test_first_estimate_is_a_baseline_and_deloads_never_count(self):
        entries = [
            LiftEntry("s1", "2026-09-25", "strength_a", 100, "kg", [5], None, False),
            LiftEntry("s2", "2026-10-02", "strength_a", 105, "kg", [5], None, False),
            LiftEntry("s3", "2026-10-09", "strength_a", 120, "kg", [5], None, True),
            LiftEntry("s4", "2026-10-16", "strength_a", 104, "kg", [5], None, False),
            LiftEntry("s5", "2026-10-23", "strength_a", 110, "kg", [5], None, False),
        ]
        mark_prs(entries)
        self.assertEqual([entry.is_pr for entry in entries], [False, True, False, False, True])

    def test_a_unit_change_starts_a_new_baseline(self):
        entries = [
            LiftEntry("s1", "2026-09-25", "strength_a", 14, "kg/hand", [6], None, False),
            LiftEntry("s2", "2026-09-27", "strength_b", 20, "kg", [6], None, False),
            LiftEntry("s3", "2026-10-04", "strength_b", 22, "kg", [6], None, False),
        ]
        mark_prs(entries)
        self.assertEqual([entry.is_pr for entry in entries], [False, False, True])

    def test_added_weight_gets_no_estimate(self):
        entries = [LiftEntry("s1", "2026-10-21", "strength_b", 10, "kg added", [5], None, False)]
        mark_prs(entries)
        self.assertIsNone(entries[0].e1rm)


class LiftHistoryServiceTests(unittest.TestCase):
    def setUp(self):
        self.factory = session_factory()
        with self.factory() as db:
            add_session(db, "a1", date(2026, 9, 24))
            add_result(db, "a1", 0, "Stationary bike warm-up", None, None, sets=None)
            add_result(db, "a1", 1, "Military Press", 52.0, "5")
            add_result(db, "a1", 2, "Pull-ups", None, "6–8")
            add_result(db, "a1", 3, "Front Squat", 85.0, "4", status="skipped")
            add_session(db, "b1", date(2026, 10, 20), planned_type="strength_b")
            add_result(db, "b1", 1, "Military Press", 60.0, None, sets=None, rpe=8.0)
            db.add(TrainingSessionExerciseLog(
                id="log-1", training_session_id="b1", sort_order=1, planned_exercise_name="Military Press",
                reps_per_set=[5, 5, 5], load_kg=60.0, rpe=8.0, status="completed", created_at=datetime.now(UTC),
            ))
            db.add(TrainingExerciseProgress(
                workout_type="strength_b", exercise_name="Military Press", load_value=61.0, load_unit="kg",
                sets=3, rep_target=None, last_decision="progress", updated_at=datetime.now(UTC),
            ))
            db.commit()
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.lift_history_service = LiftHistoryService(session_factory=self.factory, timezone_name="Asia/Tokyo")
        self.client = TestClient(self.app)

    def test_merges_both_stores_and_flags_the_pr(self):
        payload = self.client.get("/api/v1/training/lifts").json()
        names = [lift["name"] for lift in payload["lifts"]]

        self.assertEqual(names, ["Military Press", "Pull-ups"])  # warm-up and skipped rows dropped
        press = payload["lifts"][0]
        self.assertEqual([item["date"] for item in press["sessions"]], ["2026-09-25", "2026-10-21"])
        self.assertEqual(press["sessions"][1]["reps"], [5, 5, 5])  # compact log wins for the same session
        self.assertEqual(press["sessions"][1]["e1rm"], 70.0)
        self.assertTrue(press["sessions"][1]["is_pr"])
        self.assertFalse(press["sessions"][0]["is_pr"])
        self.assertEqual(press["best_e1rm"], 70.0)
        self.assertEqual(press["pr_count"], 1)
        self.assertEqual(press["slug"], "barbell-overhead-press")
        self.assertEqual(press["next_target"]["load"], 61.0)

    def test_bodyweight_lift_keeps_reps_without_an_estimate(self):
        pullups = next(lift for lift in self.client.get("/api/v1/training/lifts").json()["lifts"] if lift["name"] == "Pull-ups")
        self.assertEqual(pullups["sessions"][0]["reps"], [6, 6, 6])
        self.assertIsNone(pullups["sessions"][0]["e1rm"])
        self.assertIsNone(pullups["best_e1rm"])


if __name__ == "__main__":
    unittest.main()
