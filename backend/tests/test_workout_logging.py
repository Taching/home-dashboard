"""Tests for workout logging service (Milestone 2).

Tests spec sections 6.2, 6.3, 9.1, 9.2 (exercise-level logging, BJJ analysis).
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
    BjjFailureType,
)
from app.domain.workout_logging import (
    WorkoutLoggingService,
    ExerciseLogInput,
    BjjAnalysisInput,
    parse_compact_reps,
    format_compact_reps,
)
from app.domain.exercise_library import ExerciseLibraryService


def create_test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def seed_test_session(factory, session_id: str | None = None) -> str:
    """Create a test training session."""
    session_id = session_id or str(uuid4())
    with factory() as session:
        now = datetime.now(UTC)
        training_session = TrainingSession(
            id=session_id,
            planned_type="strength_a",
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


def seed_bjj_failure_types(factory):
    """Seed BJJ failure types (normally done by exercise library)."""
    with factory() as session:
        failures = [
            BjjFailureType(code="grip_lost", label="Grip lost", description="Grip was lost"),
            BjjFailureType(code="frame_late", label="Frame late", description="Frame was late"),
            BjjFailureType(code="posture_broken", label="Posture broken", description="Posture collapsed"),
            BjjFailureType(code="other", label="Other", description="Other failure"),
        ]
        for f in failures:
            session.merge(f)
        session.commit()


class CompactRepsParsingTests(unittest.TestCase):
    """Tests for compact reps notation parsing."""
    
    def test_parse_slash_notation(self):
        result = parse_compact_reps("8 / 8 / 7")
        self.assertEqual(result, [8, 8, 7])
    
    def test_parse_comma_notation(self):
        result = parse_compact_reps("8, 8, 7")
        self.assertEqual(result, [8, 8, 7])
    
    def test_parse_space_notation(self):
        result = parse_compact_reps("8 8 7")
        self.assertEqual(result, [8, 8, 7])
    
    def test_parse_compact_slash(self):
        result = parse_compact_reps("8/8/7")
        self.assertEqual(result, [8, 8, 7])
    
    def test_parse_empty_string(self):
        result = parse_compact_reps("")
        self.assertEqual(result, [])
    
    def test_parse_none(self):
        result = parse_compact_reps(None)
        self.assertEqual(result, [])
    
    def test_format_compact_reps(self):
        result = format_compact_reps([8, 8, 7])
        self.assertEqual(result, "8 / 8 / 7")


class ExerciseLoggingTests(unittest.TestCase):
    """Tests for exercise-level logging."""
    
    def setUp(self):
        self.factory = create_test_session_factory()
        self.service = WorkoutLoggingService(session_factory=self.factory)
        self.session_id = seed_test_session(self.factory)
    
    def test_log_single_exercise(self):
        """Test logging a single exercise result."""
        inputs = [
            ExerciseLogInput(
                sort_order=0,
                planned_exercise_name="Trap-bar Deadlift",
                planned_sets=3,
                reps_per_set=[4, 4, 3],
                load_kg=130.0,
                rpe=7.5,
                technique_quality="good",
                pain_flag=False,
                status="completed",
            )
        ]
        
        results = self.service.log_exercise_results(self.session_id, inputs)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].sort_order, 0)
        self.assertEqual(results[0].planned_exercise_name, "Trap-bar Deadlift")
        self.assertEqual(results[0].load_kg, 130.0)
        self.assertEqual(results[0].reps_per_set, [4, 4, 3])
        self.assertEqual(results[0].rpe, 7.5)
        self.assertEqual(results[0].technique_quality, "good")
        self.assertFalse(results[0].pain_flag)
    
    def test_log_multiple_exercises(self):
        """Test logging multiple exercises in one session."""
        inputs = [
            ExerciseLogInput(
                sort_order=0,
                planned_exercise_name="Trap-bar Deadlift",
                planned_sets=3,
                reps_per_set=[4, 4, 4],
                load_kg=125.0,
                status="completed",
            ),
            ExerciseLogInput(
                sort_order=1,
                planned_exercise_name="Dumbbell Bench Press",
                planned_sets=3,
                reps_per_set=[8, 8, 7],
                load_kg=30.0,
                load_per_side=True,
                status="completed",
            ),
            ExerciseLogInput(
                sort_order=2,
                planned_exercise_name="Bulgarian Split Squat",
                status="skipped",
                pain_flag=True,
            ),
        ]
        
        results = self.service.log_exercise_results(self.session_id, inputs)
        
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].status, "completed")
        self.assertEqual(results[1].status, "completed")
        self.assertEqual(results[2].status, "skipped")
        self.assertTrue(results[2].pain_flag)
    
    def test_log_exercise_with_substitution(self):
        """Test logging an exercise that was substituted."""
        inputs = [
            ExerciseLogInput(
                sort_order=0,
                planned_exercise_name="Front Squat",
                planned_exercise_slug="front-squat",
                performed_exercise_name="Goblet Squat",
                performed_exercise_slug="goblet-squat",
                planned_sets=3,
                reps_per_set=[5, 5, 5],
                load_kg=24.0,
                substitution_reason="No barbell available",
                status="completed",
            ),
        ]
        
        results = self.service.log_exercise_results(self.session_id, inputs)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].planned_exercise_name, "Front Squat")
        self.assertEqual(results[0].performed_exercise_name, "Goblet Squat")
    
    def test_log_exercise_updates_existing(self):
        """Test that logging updates existing entries."""
        inputs = [
            ExerciseLogInput(
                sort_order=0,
                planned_exercise_name="Deadlift",
                reps_per_set=[3, 3, 3],
                load_kg=120.0,
                status="completed",
            ),
        ]
        self.service.log_exercise_results(self.session_id, inputs)
        
        updated_inputs = [
            ExerciseLogInput(
                sort_order=0,
                planned_exercise_name="Deadlift",
                reps_per_set=[4, 4, 4],
                load_kg=125.0,
                rpe=8.0,
                status="completed",
            ),
        ]
        results = self.service.log_exercise_results(self.session_id, updated_inputs)
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].load_kg, 125.0)
        self.assertEqual(results[0].rpe, 8.0)
        
        logs = self.service.get_exercise_logs(self.session_id)
        self.assertEqual(len(logs), 1)
    
    def test_reject_invalid_rpe(self):
        """Test that invalid RPE values are rejected."""
        inputs = [
            ExerciseLogInput(
                sort_order=0,
                planned_exercise_name="Test",
                rpe=11.0,
                status="completed",
            ),
        ]
        
        with self.assertRaises(ValueError) as ctx:
            self.service.log_exercise_results(self.session_id, inputs)
        self.assertIn("RPE", str(ctx.exception))
    
    def test_reject_invalid_technique_quality(self):
        """Test that invalid technique quality is rejected."""
        inputs = [
            ExerciseLogInput(
                sort_order=0,
                planned_exercise_name="Test",
                technique_quality="excellent",
                status="completed",
            ),
        ]
        
        with self.assertRaises(ValueError) as ctx:
            self.service.log_exercise_results(self.session_id, inputs)
        self.assertIn("technique", str(ctx.exception).lower())
    
    def test_reject_session_not_found(self):
        """Test that non-existent session raises KeyError."""
        inputs = [
            ExerciseLogInput(
                sort_order=0,
                planned_exercise_name="Test",
                status="completed",
            ),
        ]
        
        with self.assertRaises(KeyError):
            self.service.log_exercise_results("nonexistent-id", inputs)


class BjjAnalysisTests(unittest.TestCase):
    """Tests for BJJ session analysis logging."""
    
    def setUp(self):
        self.factory = create_test_session_factory()
        self.service = WorkoutLoggingService(session_factory=self.factory)
        seed_bjj_failure_types(self.factory)
        self.session_id = seed_test_session(self.factory)
    
    def test_log_basic_analysis(self):
        """Test logging basic BJJ analysis."""
        analysis = BjjAnalysisInput(
            main_focus="Half guard sweeps",
            problem_position="Bottom half guard",
        )
        
        result = self.service.log_bjj_analysis(self.session_id, analysis)
        
        self.assertEqual(result.training_session_id, self.session_id)
        self.assertEqual(result.main_focus, "Half guard sweeps")
        self.assertEqual(result.problem_position, "Bottom half guard")
    
    def test_log_analysis_with_primary_failure(self):
        """Test logging BJJ analysis with primary failure tag."""
        analysis = BjjAnalysisInput(
            main_focus="Guard retention",
            primary_failure_code="frame_late",
        )
        
        result = self.service.log_bjj_analysis(self.session_id, analysis)
        
        self.assertEqual(result.primary_failure, "frame_late")
        self.assertIn("frame_late", result.failure_codes)
    
    def test_log_analysis_with_multiple_failures(self):
        """Test logging BJJ analysis with multiple failure tags."""
        analysis = BjjAnalysisInput(
            primary_failure_code="grip_lost",
            additional_failure_codes=["posture_broken", "frame_late"],
        )
        
        result = self.service.log_bjj_analysis(self.session_id, analysis)
        
        self.assertEqual(result.primary_failure, "grip_lost")
        self.assertEqual(len(result.failure_codes), 3)
        self.assertIn("grip_lost", result.failure_codes)
        self.assertIn("posture_broken", result.failure_codes)
        self.assertIn("frame_late", result.failure_codes)
    
    def test_log_analysis_with_success_count(self):
        """Test logging BJJ analysis with success/attempt counts."""
        analysis = BjjAnalysisInput(
            main_focus="Underhook sweep",
            success_count=3,
            attempt_count=7,
        )
        
        result = self.service.log_bjj_analysis(self.session_id, analysis)
        
        stored = self.service.get_bjj_analysis(self.session_id)
        self.assertEqual(stored["success_count"], 3)
        self.assertEqual(stored["attempt_count"], 7)
    
    def test_log_analysis_updates_existing(self):
        """Test that logging updates existing analysis."""
        first = BjjAnalysisInput(main_focus="Guard passing")
        self.service.log_bjj_analysis(self.session_id, first)
        
        second = BjjAnalysisInput(
            main_focus="Half guard retention",
            primary_failure_code="grip_lost",
        )
        result = self.service.log_bjj_analysis(self.session_id, second)
        
        stored = self.service.get_bjj_analysis(self.session_id)
        self.assertEqual(stored["main_focus"], "Half guard retention")
        self.assertEqual(stored["primary_failure"], "grip_lost")
    
    def test_reject_invalid_failure_code(self):
        """Test that invalid failure codes are rejected."""
        analysis = BjjAnalysisInput(
            primary_failure_code="invalid_code",
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.service.log_bjj_analysis(self.session_id, analysis)
        self.assertIn("failure code", str(ctx.exception).lower())
    
    def test_reject_success_greater_than_attempts(self):
        """Test that success_count > attempt_count is rejected."""
        analysis = BjjAnalysisInput(
            success_count=5,
            attempt_count=3,
        )
        
        with self.assertRaises(ValueError) as ctx:
            self.service.log_bjj_analysis(self.session_id, analysis)
        self.assertIn("attempt", str(ctx.exception).lower())
    
    def test_get_nonexistent_analysis_returns_none(self):
        """Test that getting analysis for a session without one returns None."""
        result = self.service.get_bjj_analysis(self.session_id)
        self.assertIsNone(result)


class CancellationReasonTests(unittest.TestCase):
    """Tests for session cancellation reasons."""
    
    def setUp(self):
        self.factory = create_test_session_factory()
        self.service = WorkoutLoggingService(session_factory=self.factory)
        self.session_id = seed_test_session(self.factory)
    
    def test_set_weather_blocked(self):
        """Test setting weather_blocked cancellation reason."""
        self.service.set_cancellation_reason(self.session_id, "weather_blocked")
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, self.session_id)
            self.assertEqual(training_session.cancellation_reason, "weather_blocked")
    
    def test_set_pain_cancellation(self):
        """Test setting pain cancellation reason."""
        self.service.set_cancellation_reason(self.session_id, "pain")
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, self.session_id)
            self.assertEqual(training_session.cancellation_reason, "pain")
    
    def test_reject_invalid_cancellation_reason(self):
        """Test that invalid cancellation reasons are rejected."""
        with self.assertRaises(ValueError) as ctx:
            self.service.set_cancellation_reason(self.session_id, "laziness")
        self.assertIn("reason", str(ctx.exception).lower())
    
    def test_set_rain_prompted(self):
        """Test recording when rain warning was shown."""
        self.service.set_rain_prompted(self.session_id)
        
        with self.factory() as session:
            training_session = session.get(TrainingSession, self.session_id)
            self.assertIsNotNone(training_session.rain_prompted_at)


if __name__ == "__main__":
    unittest.main()
