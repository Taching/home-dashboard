"""Tests for workout backfill migration (Milestone 2).

Tests spec section 18 (backfill requirements):
- Backfill existing sessions only where data maps safely
- Migration is idempotent and tested against a fixture DB
- Leave unknown fields null
"""

import unittest
from datetime import datetime, UTC
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.database.models import (
    TrainingSession,
    TrainingExercise,
    TrainingExerciseResult,
    TrainingSessionExerciseLog,
)
from app.domain.workout_backfill import (
    get_backfill_mapping,
    infer_requires_travel,
    parse_reps_string,
    backfill_session_travel_flags,
    backfill_exercise_logs,
    run_backfill,
    verify_backfill,
)


def create_test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_session(factory, session_id: str, planned_type: str) -> str:
    """Create a test training session."""
    with factory() as session:
        now = datetime.now(UTC)
        training_session = TrainingSession(
            id=session_id,
            planned_type=planned_type,
            status="completed",
            phase="base",
            planned_week_start=now.date(),
            start_at=now,
            end_at=now,
            estimated_minutes=60,
            intensity="normal",
            reason="Test session",
            requires_travel=False,
            created_at=now,
            updated_at=now,
        )
        session.add(training_session)
        session.commit()
    return session_id


def seed_exercise(factory, session_id: str, position: int, name: str, done: bool = True) -> int:
    """Create a test exercise for a session."""
    with factory() as session:
        exercise = TrainingExercise(
            session_id=session_id,
            position=position,
            name=name,
            load_value=100.0,
            load_unit="kg",
            sets=3,
            reps="5",
            done=done,
        )
        session.add(exercise)
        session.commit()
        return exercise.id


def seed_exercise_result(factory, exercise_id: int, session_id: str, **kwargs) -> None:
    """Create a test exercise result."""
    with factory() as session:
        result = TrainingExerciseResult(
            exercise_id=exercise_id,
            session_id=session_id,
            completed=kwargs.get("completed", True),
            actual_load=kwargs.get("actual_load", 105.0),
            actual_reps=kwargs.get("actual_reps", "5/5/5"),
            rpe=kwargs.get("rpe", 7.5),
            technique=kwargs.get("technique", "good"),
            pain=kwargs.get("pain", False),
            status=kwargs.get("status", "completed"),
        )
        session.add(result)
        session.commit()


class BackfillMappingTests(unittest.TestCase):
    """Tests for backfill mapping documentation."""
    
    def test_mapping_has_required_fields(self):
        """Test that mapping documents all required fields."""
        mapping = get_backfill_mapping()
        
        self.assertIn("field_mappings", dir(mapping))
        self.assertIn("stays_null", dir(mapping))
        self.assertIn("notes", dir(mapping))
    
    def test_mapping_documents_travel_field(self):
        """Test that requires_travel mapping is documented."""
        mapping = get_backfill_mapping()
        
        bjj_mapping = None
        for key, value in mapping.field_mappings.items():
            if "bjj" in key.lower():
                bjj_mapping = value
                break
        
        self.assertIsNotNone(bjj_mapping)
        self.assertIn("requires_travel", bjj_mapping)
    
    def test_mapping_lists_null_fields(self):
        """Test that fields staying null are listed."""
        mapping = get_backfill_mapping()
        
        null_field_names = " ".join(mapping.stays_null)
        self.assertIn("cancellation_reason", null_field_names)
        self.assertIn("rain_prompted_at", null_field_names)


class InferTravelTests(unittest.TestCase):
    """Tests for requires_travel inference."""
    
    def setUp(self):
        self.factory = create_test_session_factory()
    
    def test_bjj_requires_travel(self):
        """Test that BJJ sessions require travel."""
        session_id = seed_session(self.factory, str(uuid4()), "bjj_normal")
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, session_id)
            result = infer_requires_travel(training_session)
        
        self.assertTrue(result)
    
    def test_bjj_hard_requires_travel(self):
        """Test that BJJ hard sessions require travel."""
        session_id = seed_session(self.factory, str(uuid4()), "bjj_hard")
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, session_id)
            result = infer_requires_travel(training_session)
        
        self.assertTrue(result)
    
    def test_competition_requires_travel(self):
        """Test that competition sessions require travel."""
        session_id = seed_session(self.factory, str(uuid4()), "competition")
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, session_id)
            result = infer_requires_travel(training_session)
        
        self.assertTrue(result)
    
    def test_strength_does_not_require_travel(self):
        """Test that strength sessions do not require travel."""
        session_id = seed_session(self.factory, str(uuid4()), "strength_a")
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, session_id)
            result = infer_requires_travel(training_session)
        
        self.assertFalse(result)
    
    def test_zone_2_does_not_require_travel(self):
        """Test that zone 2 does not require travel."""
        session_id = seed_session(self.factory, str(uuid4()), "zone_2")
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, session_id)
            result = infer_requires_travel(training_session)
        
        self.assertFalse(result)


class ParseRepsTests(unittest.TestCase):
    """Tests for reps string parsing."""
    
    def test_parse_slash_notation(self):
        result = parse_reps_string("5/5/5")
        self.assertEqual(result, [5, 5, 5])
    
    def test_parse_space_slash_notation(self):
        result = parse_reps_string("5 / 5 / 5")
        self.assertEqual(result, [5, 5, 5])
    
    def test_parse_comma_notation(self):
        result = parse_reps_string("8, 8, 7")
        self.assertEqual(result, [8, 8, 7])
    
    def test_parse_range_takes_high(self):
        result = parse_reps_string("6-8")
        self.assertEqual(result, [8])
    
    def test_parse_empty(self):
        result = parse_reps_string("")
        self.assertEqual(result, [])
    
    def test_parse_none(self):
        result = parse_reps_string(None)
        self.assertEqual(result, [])


class BackfillTravelFlagsTests(unittest.TestCase):
    """Tests for travel flag backfill."""
    
    def setUp(self):
        self.factory = create_test_session_factory()
    
    def test_backfill_bjj_travel_flag(self):
        """Test that BJJ sessions get requires_travel set."""
        seed_session(self.factory, str(uuid4()), "bjj_normal")
        seed_session(self.factory, str(uuid4()), "bjj_hard")
        
        with self.factory() as session:
            processed, updated = backfill_session_travel_flags(session, dry_run=False)
            session.commit()
        
        self.assertEqual(processed, 2)
        self.assertEqual(updated, 2)
        
        with self.factory() as session:
            sessions = session.query(TrainingSession).all()
            for s in sessions:
                self.assertTrue(s.requires_travel)
    
    def test_backfill_is_idempotent(self):
        """Test that backfill is idempotent."""
        seed_session(self.factory, str(uuid4()), "bjj_normal")
        
        with self.factory() as session:
            first_processed, first_updated = backfill_session_travel_flags(session, dry_run=False)
            session.commit()
        
        with self.factory() as session:
            second_processed, second_updated = backfill_session_travel_flags(session, dry_run=False)
            session.commit()
        
        self.assertEqual(first_updated, 1)
        self.assertEqual(second_updated, 0)


class BackfillExerciseLogsTests(unittest.TestCase):
    """Tests for exercise log backfill."""
    
    def setUp(self):
        self.factory = create_test_session_factory()
    
    def test_backfill_creates_logs(self):
        """Test that backfill creates exercise logs from existing data."""
        session_id = str(uuid4())
        seed_session(self.factory, session_id, "strength_a")
        exercise_id = seed_exercise(self.factory, session_id, 0, "Deadlift")
        seed_exercise_result(self.factory, exercise_id, session_id)
        
        with self.factory() as session:
            created = backfill_exercise_logs(session, session_id, dry_run=False)
            session.commit()
        
        self.assertEqual(created, 1)
        
        with self.factory() as session:
            logs = session.query(TrainingSessionExerciseLog).filter(
                TrainingSessionExerciseLog.training_session_id == session_id
            ).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].planned_exercise_name, "Deadlift")
    
    def test_backfill_preserves_load(self):
        """Test that backfill preserves load values."""
        session_id = str(uuid4())
        seed_session(self.factory, session_id, "strength_a")
        exercise_id = seed_exercise(self.factory, session_id, 0, "Squat")
        seed_exercise_result(self.factory, exercise_id, session_id, actual_load=125.0)
        
        with self.factory() as session:
            backfill_exercise_logs(session, session_id, dry_run=False)
            session.commit()
        
        with self.factory() as session:
            log = session.query(TrainingSessionExerciseLog).filter(
                TrainingSessionExerciseLog.training_session_id == session_id
            ).first()
            self.assertEqual(log.load_kg, 125.0)
    
    def test_backfill_parses_reps(self):
        """Test that backfill parses reps correctly."""
        session_id = str(uuid4())
        seed_session(self.factory, session_id, "strength_a")
        exercise_id = seed_exercise(self.factory, session_id, 0, "Press")
        seed_exercise_result(self.factory, exercise_id, session_id, actual_reps="5/5/4")
        
        with self.factory() as session:
            backfill_exercise_logs(session, session_id, dry_run=False)
            session.commit()
        
        with self.factory() as session:
            log = session.query(TrainingSessionExerciseLog).filter(
                TrainingSessionExerciseLog.training_session_id == session_id
            ).first()
            self.assertEqual(log.reps_per_set, [5, 5, 4])
    
    def test_backfill_skips_existing_logs(self):
        """Test that backfill is idempotent."""
        session_id = str(uuid4())
        seed_session(self.factory, session_id, "strength_a")
        exercise_id = seed_exercise(self.factory, session_id, 0, "Deadlift")
        seed_exercise_result(self.factory, exercise_id, session_id)
        
        with self.factory() as session:
            first_created = backfill_exercise_logs(session, session_id, dry_run=False)
            session.commit()
        
        with self.factory() as session:
            second_created = backfill_exercise_logs(session, session_id, dry_run=False)
            session.commit()
        
        self.assertEqual(first_created, 1)
        self.assertEqual(second_created, 0)


class FullBackfillTests(unittest.TestCase):
    """Tests for the complete backfill process."""
    
    def setUp(self):
        self.factory = create_test_session_factory()
    
    def test_run_backfill_dry_run(self):
        """Test dry run does not modify data."""
        session_id = str(uuid4())
        seed_session(self.factory, session_id, "bjj_normal")
        
        result = run_backfill(self.factory, dry_run=True)
        
        self.assertEqual(result.sessions_processed, 1)
        self.assertEqual(result.sessions_updated, 1)
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, session_id)
            self.assertFalse(training_session.requires_travel)
    
    def test_run_backfill_actual(self):
        """Test actual backfill modifies data."""
        session_id = str(uuid4())
        seed_session(self.factory, session_id, "bjj_normal")
        
        result = run_backfill(self.factory, dry_run=False)
        
        self.assertEqual(result.sessions_updated, 1)
        self.assertEqual(len(result.errors), 0)
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, session_id)
            self.assertTrue(training_session.requires_travel)
    
    def test_verify_backfill(self):
        """Test backfill verification."""
        seed_session(self.factory, str(uuid4()), "bjj_normal")
        seed_session(self.factory, str(uuid4()), "strength_a")
        
        run_backfill(self.factory, dry_run=False)
        
        stats = verify_backfill(self.factory)
        
        self.assertEqual(stats["total_sessions"], 2)
        self.assertEqual(stats["sessions_with_requires_travel"], 1)


if __name__ == "__main__":
    unittest.main()
