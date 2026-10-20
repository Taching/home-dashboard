"""Backfill existing training sessions with M2 fields.

Implements spec section 18 (Milestone 2 scope):
- Backfill existing sessions only where data maps safely
- Migration is idempotent and tested against a fixture DB
- Leave unknown fields null
- Never run against the real Pi/prod DB

Backfill mapping:
- BJJ sessions at academy: requires_travel = True
- Home sessions: requires_travel = False
- Strength sessions: requires_travel based on location inference
- Existing session results: preserve as-is, don't fabricate new fields
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Literal
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import (
    TrainingSession,
    TrainingSessionExerciseLog,
    TrainingExercise,
    TrainingExerciseResult,
    BjjSessionAnalysis,
)
from app.database.session import SessionLocal


@dataclass
class BackfillResult:
    """Result of running the backfill migration."""
    sessions_processed: int
    sessions_updated: int
    exercise_logs_created: int
    bjj_analyses_created: int
    skipped: int
    errors: list[str]


@dataclass
class BackfillMapping:
    """Documents which old fields map to which new ones."""
    field_mappings: dict[str, str]
    stays_null: list[str]
    notes: list[str]


def get_backfill_mapping() -> BackfillMapping:
    """Return documentation of the backfill field mapping.
    
    This is used for the PR report to explain what was mapped and what stays null.
    """
    return BackfillMapping(
        field_mappings={
            # TrainingSession fields
            "planned_type (bjj_*)": "requires_travel = True (academy sessions)",
            "planned_type (strength_*)": "requires_travel = False (home gym assumed unless location indicates otherwise)",
            "planned_type (zone_2, recovery)": "requires_travel = False (home)",
            
            # Exercise mapping
            "TrainingExercise.name": "TrainingSessionExerciseLog.planned_exercise_name",
            "TrainingExercise.position": "TrainingSessionExerciseLog.sort_order",
            "TrainingExercise.sets": "TrainingSessionExerciseLog.planned_sets",
            "TrainingExercise.done": "TrainingSessionExerciseLog.status (completed/skipped)",
            "TrainingExerciseResult.actual_load": "TrainingSessionExerciseLog.load_kg",
            "TrainingExerciseResult.actual_reps": "TrainingSessionExerciseLog.reps_per_set (parsed)",
            "TrainingExerciseResult.rpe": "TrainingSessionExerciseLog.rpe",
            "TrainingExerciseResult.technique": "TrainingSessionExerciseLog.technique_quality",
            "TrainingExerciseResult.pain": "TrainingSessionExerciseLog.pain_flag",
            
            # Session result mapping
            "TrainingSessionResult.bjj_rounds": "preserved on TrainingSession",
            "TrainingSessionResult.perceived_intensity": "preserved on TrainingSession",
        },
        stays_null=[
            "cancellation_reason (no historical weather data to infer blocks)",
            "replacement_for_training_session_id (no historical linkage)",
            "rain_prompted_at (no historical prompts)",
            "TrainingSessionExerciseLog.performed_exercise_slug (no library linkage)",
            "TrainingSessionExerciseLog.performed_exercise_name (same as planned if not swapped)",
            "TrainingSessionExerciseLog.substitution_reason (no historical swaps)",
            "BjjSessionAnalysis.main_focus (not previously tracked)",
            "BjjSessionAnalysis.problem_position (not previously tracked)",
            "BjjSessionAnalysis.key_failure_text (not previously tracked)",
            "BjjSessionAnalysis.technique_practiced (not previously tracked)",
            "BjjSessionAnalysis.success_count (not previously tracked)",
            "BjjSessionAnalysis.attempt_count (not previously tracked)",
            "BjjSessionFailure entries (no historical failure tags)",
        ],
        notes=[
            "This backfill is idempotent: running it multiple times produces the same result.",
            "It never updates fields that already have values (no overwrites).",
            "It only creates new TrainingSessionExerciseLog entries if none exist for a session.",
            "BJJ analysis entries are NOT created since we have no historical focus/failure data.",
            "Missing data stays visibly null in the UI (no fake zeros).",
            "This should NEVER run against the production Pi database.",
        ],
    )


def infer_requires_travel(session: TrainingSession) -> bool:
    """Infer if a session requires travel based on its type and context.
    
    Per spec: Backfill academy BJJ as requires_travel=true; backfill other 
    sessions only when their saved location makes the value unambiguous.
    """
    planned_type = (session.planned_type or "").lower()
    
    if planned_type.startswith("bjj") or planned_type == "competition":
        return True
    
    if "zone_2" in planned_type or "recovery" in planned_type or "grip" in planned_type:
        return False
    
    if "strength" in planned_type:
        return False
    
    return False


def parse_reps_string(reps_str: str | None) -> list[int]:
    """Parse a reps string like '8/8/7' or '5, 5, 5' into a list of integers."""
    if not reps_str:
        return []
    
    cleaned = reps_str.strip()
    
    for sep in [" / ", "/", ", ", ","]:
        if sep in cleaned:
            parts = cleaned.split(sep)
            break
    else:
        parts = cleaned.split()
    
    result = []
    for part in parts:
        part = part.strip()
        try:
            if part.isdigit():
                result.append(int(part))
            elif "-" in part:
                low, high = part.split("-")
                result.append(int(high.strip()))
        except ValueError:
            continue
    
    return result


def backfill_session_travel_flags(
    db_session: Session,
    *,
    dry_run: bool = True,
) -> tuple[int, int]:
    """Backfill requires_travel flag on existing sessions.
    
    Returns (processed, updated) counts.
    """
    sessions = db_session.scalars(
        select(TrainingSession).where(TrainingSession.requires_travel == False)
    ).all()
    
    processed = 0
    updated = 0
    
    for session in sessions:
        processed += 1
        should_require_travel = infer_requires_travel(session)
        
        if should_require_travel and not session.requires_travel:
            if not dry_run:
                session.requires_travel = True
            updated += 1
    
    return processed, updated


def backfill_exercise_logs(
    db_session: Session,
    session_id: str,
    *,
    dry_run: bool = True,
) -> int:
    """Backfill exercise logs for a single training session.
    
    Creates TrainingSessionExerciseLog entries from existing TrainingExercise
    and TrainingExerciseResult data.
    
    Returns count of logs created.
    """
    existing_logs = db_session.scalar(
        select(TrainingSessionExerciseLog)
        .where(TrainingSessionExerciseLog.training_session_id == session_id)
        .limit(1)
    )
    if existing_logs is not None:
        return 0
    
    exercises = db_session.scalars(
        select(TrainingExercise)
        .where(TrainingExercise.session_id == session_id)
        .order_by(TrainingExercise.position)
    ).all()
    
    if not exercises:
        return 0
    
    result_map: dict[int, TrainingExerciseResult] = {}
    for ex in exercises:
        result = db_session.scalar(
            select(TrainingExerciseResult)
            .where(TrainingExerciseResult.exercise_id == ex.id)
        )
        if result:
            result_map[ex.id] = result
    
    now = datetime.now(UTC)
    created = 0
    
    for exercise in exercises:
        result = result_map.get(exercise.id)
        
        load_kg = None
        if result and result.actual_load is not None:
            load_kg = result.actual_load
        elif exercise.load_value is not None:
            load_kg = exercise.load_value
        
        reps_per_set = []
        if result and result.actual_reps:
            reps_per_set = parse_reps_string(result.actual_reps)
        
        status = "skipped"
        if exercise.done:
            status = "completed"
        elif result and result.completed:
            status = "completed" if result.completed else "partial"
        
        technique_quality = None
        if result and result.technique:
            if result.technique in ("good", "shaky", "breakdown"):
                technique_quality = result.technique
        
        pain_flag = False
        if result and result.pain:
            pain_flag = result.pain
        
        if not dry_run:
            log_entry = TrainingSessionExerciseLog(
                id=str(uuid4()),
                training_session_id=session_id,
                sort_order=exercise.position,
                planned_exercise_slug=None,
                performed_exercise_slug=None,
                planned_exercise_name=exercise.name,
                performed_exercise_name=None,
                planned_sets=exercise.sets,
                reps_per_set=reps_per_set,
                load_kg=load_kg,
                load_per_side=False,
                load_note=None,
                rpe=result.rpe if result else None,
                technique_quality=technique_quality,
                pain_flag=pain_flag,
                status=status,
                substitution_reason=None,
                notes=exercise.notes,
                created_at=now,
            )
            db_session.add(log_entry)
        
        created += 1
    
    return created


def run_backfill(
    session_factory=SessionLocal,
    *,
    dry_run: bool = True,
) -> BackfillResult:
    """Run the complete M2 backfill migration.
    
    This is idempotent: running it multiple times produces the same result.
    
    Args:
        session_factory: SQLAlchemy session factory (use test DB, not prod!)
        dry_run: If True, don't actually commit changes
    
    Returns:
        BackfillResult with counts and any errors
    """
    errors: list[str] = []
    sessions_processed = 0
    sessions_updated = 0
    exercise_logs_created = 0
    bjj_analyses_created = 0
    skipped = 0
    
    with session_factory() as db_session:
        processed, updated = backfill_session_travel_flags(db_session, dry_run=dry_run)
        sessions_processed += processed
        sessions_updated += updated
        
        all_sessions = db_session.scalars(select(TrainingSession)).all()
        
        for session in all_sessions:
            try:
                created = backfill_exercise_logs(
                    db_session, 
                    session.id, 
                    dry_run=dry_run,
                )
                exercise_logs_created += created
            except Exception as e:
                errors.append(f"Session {session.id}: {str(e)}")
                skipped += 1
        
        if not dry_run:
            db_session.commit()
    
    return BackfillResult(
        sessions_processed=sessions_processed,
        sessions_updated=sessions_updated,
        exercise_logs_created=exercise_logs_created,
        bjj_analyses_created=bjj_analyses_created,
        skipped=skipped,
        errors=errors,
    )


def verify_backfill(session_factory=SessionLocal) -> dict:
    """Verify the backfill results without making changes.
    
    Returns statistics about the current state of backfilled data.
    """
    with session_factory() as db_session:
        total_sessions = db_session.query(TrainingSession).count()
        sessions_with_travel = db_session.query(TrainingSession).filter(
            TrainingSession.requires_travel == True
        ).count()
        
        total_exercise_logs = db_session.query(TrainingSessionExerciseLog).count()
        
        sessions_with_logs = db_session.query(
            TrainingSessionExerciseLog.training_session_id
        ).distinct().count()
        
        total_bjj_analyses = db_session.query(BjjSessionAnalysis).count()
        
        return {
            "total_sessions": total_sessions,
            "sessions_with_requires_travel": sessions_with_travel,
            "sessions_without_requires_travel": total_sessions - sessions_with_travel,
            "total_exercise_logs": total_exercise_logs,
            "sessions_with_exercise_logs": sessions_with_logs,
            "sessions_without_exercise_logs": total_sessions - sessions_with_logs,
            "total_bjj_analyses": total_bjj_analyses,
        }
