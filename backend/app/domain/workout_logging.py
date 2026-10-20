"""Workout logging service for structured exercise-level results.

Implements spec section 9 (Logging requirements) and section 6.2 (TrainingSessionExerciseLog).
Milestone 2 scope.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    BjjFailureType,
    BjjSessionAnalysis,
    BjjSessionFailure,
    Exercise,
    TrainingSession,
    TrainingSessionExerciseLog,
)
from app.database.session import SessionLocal


TechniqueQuality = Literal["good", "shaky", "breakdown"]
ExerciseLogStatus = Literal["completed", "partial", "skipped"]


@dataclass
class ExerciseLogInput:
    """Input for logging a single exercise result."""
    sort_order: int
    planned_exercise_name: str
    planned_exercise_slug: str | None = None
    performed_exercise_name: str | None = None
    performed_exercise_slug: str | None = None
    planned_sets: int | None = None
    reps_per_set: list[int] | None = None
    load_kg: float | None = None
    load_per_side: bool = False
    load_note: str | None = None
    rpe: float | None = None
    technique_quality: TechniqueQuality | None = None
    pain_flag: bool = False
    status: ExerciseLogStatus = "completed"
    substitution_reason: str | None = None
    notes: str | None = None


@dataclass
class BjjAnalysisInput:
    """Input for logging BJJ session analysis."""
    main_focus: str | None = None
    problem_position: str | None = None
    key_failure_text: str | None = None
    technique_practiced: str | None = None
    success_count: int | None = None
    attempt_count: int | None = None
    primary_failure_code: str | None = None
    additional_failure_codes: list[str] | None = None
    failure_notes: dict[str, str] | None = None


@dataclass
class ExerciseLogResult:
    """Result of logging an exercise."""
    id: str
    sort_order: int
    planned_exercise_name: str
    performed_exercise_name: str | None
    status: str
    load_kg: float | None
    reps_per_set: list[int]
    rpe: float | None
    technique_quality: str | None
    pain_flag: bool


@dataclass
class BjjAnalysisResult:
    """Result of logging BJJ analysis."""
    training_session_id: str
    main_focus: str | None
    problem_position: str | None
    primary_failure: str | None
    failure_codes: list[str]


class WorkoutLoggingService:
    """Service for structured workout logging."""

    VALID_TECHNIQUE_QUALITIES = frozenset({"good", "shaky", "breakdown"})
    VALID_EXERCISE_STATUSES = frozenset({"completed", "partial", "skipped"})
    VALID_CANCELLATION_REASONS = frozenset({
        "weather_blocked", "pain", "illness", "schedule_conflict", "user_cancelled", "other"
    })

    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory

    def log_exercise_results(
        self,
        session_id: str,
        exercises: list[ExerciseLogInput],
    ) -> list[ExerciseLogResult]:
        """Log structured exercise-level results for a training session.
        
        Implements spec section 9.1 (Strength logging):
        - One compact result per exercise (not set-by-set)
        - Preserves planned vs performed exercise history
        - Stores compact reps_per_set like [8, 8, 7]
        """
        with self._session_factory() as session:
            training_session = session.get(TrainingSession, session_id)
            if training_session is None:
                raise KeyError(f"Training session not found: {session_id}")

            now = datetime.now(UTC)
            results: list[ExerciseLogResult] = []

            for exercise_input in exercises:
                self._validate_exercise_input(exercise_input)
                
                existing = session.scalar(
                    select(TrainingSessionExerciseLog).where(
                        TrainingSessionExerciseLog.training_session_id == session_id,
                        TrainingSessionExerciseLog.sort_order == exercise_input.sort_order,
                    )
                )
                
                if existing:
                    self._update_exercise_log(existing, exercise_input)
                    log_id = existing.id
                else:
                    log_id = str(uuid4())
                    log_entry = TrainingSessionExerciseLog(
                        id=log_id,
                        training_session_id=session_id,
                        sort_order=exercise_input.sort_order,
                        planned_exercise_slug=exercise_input.planned_exercise_slug,
                        performed_exercise_slug=exercise_input.performed_exercise_slug,
                        planned_exercise_name=exercise_input.planned_exercise_name,
                        performed_exercise_name=exercise_input.performed_exercise_name,
                        planned_sets=exercise_input.planned_sets,
                        reps_per_set=exercise_input.reps_per_set or [],
                        load_kg=exercise_input.load_kg,
                        load_per_side=exercise_input.load_per_side,
                        load_note=exercise_input.load_note,
                        rpe=exercise_input.rpe,
                        technique_quality=exercise_input.technique_quality,
                        pain_flag=exercise_input.pain_flag,
                        status=exercise_input.status,
                        substitution_reason=exercise_input.substitution_reason,
                        notes=exercise_input.notes,
                        created_at=now,
                    )
                    session.add(log_entry)
                
                results.append(ExerciseLogResult(
                    id=log_id,
                    sort_order=exercise_input.sort_order,
                    planned_exercise_name=exercise_input.planned_exercise_name,
                    performed_exercise_name=exercise_input.performed_exercise_name,
                    status=exercise_input.status,
                    load_kg=exercise_input.load_kg,
                    reps_per_set=exercise_input.reps_per_set or [],
                    rpe=exercise_input.rpe,
                    technique_quality=exercise_input.technique_quality,
                    pain_flag=exercise_input.pain_flag,
                ))

            session.commit()
            return results

    def log_bjj_analysis(
        self,
        session_id: str,
        analysis: BjjAnalysisInput,
    ) -> BjjAnalysisResult:
        """Log optional BJJ analysis fields for a training session.
        
        Implements spec section 9.2 (BJJ quick review):
        - Optional main focus, problem position, failure tags
        - Links to the seeded 12 failure types from M1
        - Under 60 seconds to complete
        """
        with self._session_factory() as session:
            training_session = session.get(TrainingSession, session_id)
            if training_session is None:
                raise KeyError(f"Training session not found: {session_id}")

            self._validate_bjj_analysis(session, analysis)
            now = datetime.now(UTC)

            existing = session.get(BjjSessionAnalysis, session_id)
            if existing:
                existing.main_focus = analysis.main_focus
                existing.problem_position = analysis.problem_position
                existing.key_failure_text = analysis.key_failure_text
                existing.technique_practiced = analysis.technique_practiced
                existing.success_count = analysis.success_count
                existing.attempt_count = analysis.attempt_count
                existing.updated_at = now
                session.execute(
                    BjjSessionFailure.__table__.delete().where(
                        BjjSessionFailure.training_session_id == session_id
                    )
                )
            else:
                bjj_analysis = BjjSessionAnalysis(
                    training_session_id=session_id,
                    main_focus=analysis.main_focus,
                    problem_position=analysis.problem_position,
                    key_failure_text=analysis.key_failure_text,
                    technique_practiced=analysis.technique_practiced,
                    success_count=analysis.success_count,
                    attempt_count=analysis.attempt_count,
                    updated_at=now,
                )
                session.add(bjj_analysis)
                session.flush()

            failure_codes: list[str] = []
            if analysis.primary_failure_code:
                failure_codes.append(analysis.primary_failure_code)
                session.add(BjjSessionFailure(
                    training_session_id=session_id,
                    failure_code=analysis.primary_failure_code,
                    is_primary=True,
                    note=(analysis.failure_notes or {}).get(analysis.primary_failure_code),
                ))

            for code in (analysis.additional_failure_codes or []):
                if code != analysis.primary_failure_code:
                    failure_codes.append(code)
                    session.add(BjjSessionFailure(
                        training_session_id=session_id,
                        failure_code=code,
                        is_primary=False,
                        note=(analysis.failure_notes or {}).get(code),
                    ))

            session.commit()

            return BjjAnalysisResult(
                training_session_id=session_id,
                main_focus=analysis.main_focus,
                problem_position=analysis.problem_position,
                primary_failure=analysis.primary_failure_code,
                failure_codes=failure_codes,
            )

    def get_exercise_logs(self, session_id: str) -> list[dict]:
        """Get all exercise logs for a training session."""
        with self._session_factory() as session:
            logs = session.scalars(
                select(TrainingSessionExerciseLog)
                .where(TrainingSessionExerciseLog.training_session_id == session_id)
                .order_by(TrainingSessionExerciseLog.sort_order)
            ).all()
            return [self._log_to_dict(log) for log in logs]

    def get_bjj_analysis(self, session_id: str) -> dict | None:
        """Get BJJ analysis for a training session."""
        with self._session_factory() as session:
            analysis = session.get(BjjSessionAnalysis, session_id)
            if analysis is None:
                return None
            
            failures = list(session.scalars(
                select(BjjSessionFailure)
                .where(BjjSessionFailure.training_session_id == session_id)
            ).all())
            
            return {
                "training_session_id": analysis.training_session_id,
                "main_focus": analysis.main_focus,
                "problem_position": analysis.problem_position,
                "key_failure_text": analysis.key_failure_text,
                "technique_practiced": analysis.technique_practiced,
                "success_count": analysis.success_count,
                "attempt_count": analysis.attempt_count,
                "primary_failure": next(
                    (f.failure_code for f in failures if f.is_primary), None
                ),
                "failure_codes": [f.failure_code for f in failures],
            }

    def set_rain_prompted(self, session_id: str, prompted_at: datetime | None = None) -> None:
        """Record when rain warning was shown for a session."""
        with self._session_factory() as session:
            training_session = session.get(TrainingSession, session_id)
            if training_session is None:
                raise KeyError(f"Training session not found: {session_id}")
            training_session.rain_prompted_at = prompted_at or datetime.now(UTC)
            session.commit()

    def set_cancellation_reason(
        self,
        session_id: str,
        reason: str,
        replacement_session_id: str | None = None,
    ) -> None:
        """Set cancellation reason for a session (e.g., weather_blocked).
        
        Per spec: weather_blocked is stored only after athlete confirmation.
        """
        if reason not in self.VALID_CANCELLATION_REASONS:
            raise ValueError(f"Invalid cancellation reason: {reason}")
        
        with self._session_factory() as session:
            training_session = session.get(TrainingSession, session_id)
            if training_session is None:
                raise KeyError(f"Training session not found: {session_id}")
            
            training_session.cancellation_reason = reason
            if replacement_session_id:
                training_session.replacement_for_training_session_id = replacement_session_id
            session.commit()

    def _validate_exercise_input(self, exercise_input: ExerciseLogInput) -> None:
        """Validate exercise log input."""
        if exercise_input.technique_quality is not None:
            if exercise_input.technique_quality not in self.VALID_TECHNIQUE_QUALITIES:
                raise ValueError(
                    f"Invalid technique quality: {exercise_input.technique_quality}"
                )
        if exercise_input.status not in self.VALID_EXERCISE_STATUSES:
            raise ValueError(f"Invalid exercise status: {exercise_input.status}")
        if exercise_input.rpe is not None and not (1 <= exercise_input.rpe <= 10):
            raise ValueError("RPE must be between 1 and 10")
        if exercise_input.reps_per_set:
            if len(exercise_input.reps_per_set) > 20:
                raise ValueError("Maximum 20 sets allowed")
            if any(r <= 0 or r > 100 for r in exercise_input.reps_per_set):
                raise ValueError("Reps must be between 1 and 100")

    def _validate_bjj_analysis(self, session: Session, analysis: BjjAnalysisInput) -> None:
        """Validate BJJ analysis input."""
        if analysis.success_count is not None and analysis.success_count < 0:
            raise ValueError("Success count cannot be negative")
        if analysis.attempt_count is not None:
            if analysis.attempt_count < 0:
                raise ValueError("Attempt count cannot be negative")
            if analysis.success_count is not None and analysis.attempt_count < analysis.success_count:
                raise ValueError("Attempt count cannot be less than success count")

        all_codes = []
        if analysis.primary_failure_code:
            all_codes.append(analysis.primary_failure_code)
        if analysis.additional_failure_codes:
            all_codes.extend(analysis.additional_failure_codes)
        
        for code in all_codes:
            if session.get(BjjFailureType, code) is None:
                raise ValueError(f"Invalid failure code: {code}")

    def _update_exercise_log(
        self,
        existing: TrainingSessionExerciseLog,
        exercise_input: ExerciseLogInput,
    ) -> None:
        """Update an existing exercise log entry."""
        existing.performed_exercise_slug = exercise_input.performed_exercise_slug
        existing.performed_exercise_name = exercise_input.performed_exercise_name
        existing.reps_per_set = exercise_input.reps_per_set or []
        existing.load_kg = exercise_input.load_kg
        existing.load_per_side = exercise_input.load_per_side
        existing.load_note = exercise_input.load_note
        existing.rpe = exercise_input.rpe
        existing.technique_quality = exercise_input.technique_quality
        existing.pain_flag = exercise_input.pain_flag
        existing.status = exercise_input.status
        existing.substitution_reason = exercise_input.substitution_reason
        existing.notes = exercise_input.notes

    def _log_to_dict(self, log: TrainingSessionExerciseLog) -> dict:
        """Convert exercise log to dictionary."""
        return {
            "id": log.id,
            "training_session_id": log.training_session_id,
            "sort_order": log.sort_order,
            "planned_exercise_slug": log.planned_exercise_slug,
            "performed_exercise_slug": log.performed_exercise_slug,
            "planned_exercise_name": log.planned_exercise_name,
            "performed_exercise_name": log.performed_exercise_name,
            "planned_sets": log.planned_sets,
            "reps_per_set": list(log.reps_per_set) if log.reps_per_set else [],
            "load_kg": log.load_kg,
            "load_per_side": log.load_per_side,
            "load_note": log.load_note,
            "rpe": log.rpe,
            "technique_quality": log.technique_quality,
            "pain_flag": log.pain_flag,
            "status": log.status,
            "substitution_reason": log.substitution_reason,
            "notes": log.notes,
        }


def parse_compact_reps(reps_string: str) -> list[int]:
    """Parse compact reps notation like '8 / 8 / 7' into a list of integers.
    
    Handles various separators: '/', ',', ' '
    """
    if not reps_string or not reps_string.strip():
        return []
    
    cleaned = reps_string.strip()
    for sep in [" / ", "/", ", ", ","]:
        if sep in cleaned:
            parts = cleaned.split(sep)
            break
    else:
        parts = cleaned.split()
    
    result = []
    for part in parts:
        part = part.strip()
        if part and part.isdigit():
            result.append(int(part))
    
    return result


def format_compact_reps(reps: list[int]) -> str:
    """Format a list of reps as compact notation like '8 / 8 / 7'."""
    return " / ".join(str(r) for r in reps)
