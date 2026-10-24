"""Per-lift history: every logged session of each exercise, estimated 1RM and PRs.

Read-only over two stores that both hold lift results:

- ``TrainingExerciseResult`` + ``TrainingExercise`` (the original per-exercise
  result, keyed by the session's exercise row; reps are a free-text string).
- ``TrainingSessionExerciseLog`` (the newer compact log with reps per set).

When both exist for the same session and exercise name, the compact log wins
because it carries the real reps per set. Nothing here writes or feeds the
scheduler; it only explains what the progression already did.
"""
from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import (
    TrainingExercise,
    TrainingExerciseProgress,
    TrainingExerciseResult,
    TrainingSession,
    TrainingSessionExerciseLog,
)
from app.database.session import SessionLocal
from app.domain.weekly_analyzer import TEMPLATE_NAME_TO_SLUG

# Epley caps out above ten reps; past that the estimate means little.
MAX_REPS_FOR_E1RM = 10

# Rows that are warm-ups or conditioning, not lifts.
NON_LIFT_MARKERS = ("bike", "cardio", "warm-up", "warm up", "zone 2", "interval")


def estimated_1rm(load: float | None, reps: int | None) -> float | None:
    """Epley estimate, the formula the weekly analyzer uses: load × (1 + reps / 30)."""
    if load is None or reps is None or load <= 0 or not 1 <= reps <= MAX_REPS_FOR_E1RM:
        return None
    return round(float(load) * (1 + reps / 30), 1)


def parse_reps(text: str | None, sets: int | None) -> list[int]:
    """Turn a stored reps string into reps per set.

    "5/5/5" → [5, 5, 5]; "3" with 3 sets → [3, 3, 3]; "6/leg" or "8/side" → one
    number per set; "6–8" → the lower bound per set. Anything without a leading
    number (e.g. "30 sec hard") yields [].
    """
    value = (text or "").strip()
    if not value or re.search(r"\d\s*(s|sec|secs|seconds?|min|mins|minutes?)\b", value, re.IGNORECASE):
        return []  # timed work, not reps
    tokens = [token.strip() for token in value.split("/")]
    if tokens and all(token.isdigit() for token in tokens) and len(tokens) > 1:
        return [int(token) for token in tokens]
    match = re.match(r"^(\d+)", value)
    if not match:
        return []
    reps = int(match.group(1))
    return [reps] * max(int(sets or 1), 1)


def _is_lift(name: str) -> bool:
    lowered = name.lower()
    return not any(marker in lowered for marker in NON_LIFT_MARKERS)


@dataclass
class LiftEntry:
    session_id: str
    date: str
    workout_type: str
    load: float | None
    unit: str | None
    reps: list[int]
    rpe: float | None
    deload: bool
    e1rm: float | None = None
    is_pr: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "date": self.date,
            "workout_type": self.workout_type,
            "load": self.load,
            "unit": self.unit,
            "reps": self.reps,
            "top_reps": max(self.reps) if self.reps else None,
            "rpe": self.rpe,
            "deload": self.deload,
            "e1rm": self.e1rm,
            "is_pr": self.is_pr,
        }


def _estimates_load(unit: str | None) -> bool:
    """Added weight on a bodyweight lift is not the load moved, so no 1RM from it."""
    return "added" not in (unit or "").lower()


def mark_prs(entries: list[LiftEntry]) -> None:
    """Fill e1rm and flag sessions that beat every earlier estimate for the lift.

    Estimates only compare within the same load unit (kg vs kg/hand are not the
    same number). The first session in a unit is the baseline, not a PR.
    Deload sessions never count as a PR and never raise the bar.
    """
    best: dict[str, float] = {}
    for entry in sorted(entries, key=lambda item: item.date):
        if not _estimates_load(entry.unit):
            entry.e1rm = None
            continue
        entry.e1rm = estimated_1rm(entry.load, max(entry.reps) if entry.reps else None)
        if entry.e1rm is None or entry.deload:
            continue
        unit = (entry.unit or "kg").lower()
        if unit in best and entry.e1rm > best[unit]:
            entry.is_pr = True
        best[unit] = max(best.get(unit, entry.e1rm), entry.e1rm)


@dataclass
class LiftHistoryService:
    session_factory: Callable[[], Any] = SessionLocal
    timezone_name: str = field(default_factory=lambda: settings.timezone)

    def lifts(self) -> dict[str, Any]:
        tz = ZoneInfo(self.timezone_name)
        by_key: dict[tuple[str, str], LiftEntry] = {}
        names: dict[str, str] = {}
        with self.session_factory() as db:
            legacy = db.execute(
                select(TrainingExerciseResult, TrainingExercise, TrainingSession)
                .join(TrainingExercise, TrainingExercise.id == TrainingExerciseResult.exercise_id)
                .join(TrainingSession, TrainingSession.id == TrainingExerciseResult.session_id)
            ).all()
            for result, exercise, session in legacy:
                if result.status == "skipped" or not _is_lift(exercise.name):
                    continue
                load = result.actual_load if result.actual_load and result.actual_load > 0 else None
                reps = parse_reps(result.actual_reps, result.actual_sets)
                if load is None and not reps:
                    continue
                key = (session.id, exercise.name.casefold())
                names.setdefault(exercise.name.casefold(), exercise.name)
                by_key[key] = LiftEntry(
                    session_id=session.id,
                    date=self._local_date(session.start_at, tz),
                    workout_type=session.planned_type,
                    load=load,
                    unit=exercise.load_unit or ("kg" if load is not None else None),
                    reps=reps,
                    rpe=result.rpe,
                    deload=bool(session.deload),
                )

            compact = db.execute(
                select(TrainingSessionExerciseLog, TrainingSession)
                .join(TrainingSession, TrainingSession.id == TrainingSessionExerciseLog.training_session_id)
            ).all()
            for log, session in compact:
                name = (log.performed_exercise_name or log.planned_exercise_name or "").strip()
                if not name or log.status == "skipped" or not _is_lift(name):
                    continue
                load = log.load_kg if log.load_kg and log.load_kg > 0 else None
                reps = [int(r) for r in (log.reps_per_set or []) if isinstance(r, (int, float)) and r > 0]
                if load is None and not reps:
                    continue
                key = (session.id, name.casefold())
                previous = by_key.get(key)
                names.setdefault(name.casefold(), name)
                by_key[key] = LiftEntry(
                    session_id=session.id,
                    date=self._local_date(session.start_at, tz),
                    workout_type=session.planned_type,
                    load=load,
                    unit=self._compact_unit(load, log.load_per_side, previous),
                    reps=reps or (previous.reps if previous else []),
                    rpe=log.rpe if log.rpe is not None else (previous.rpe if previous else None),
                    deload=bool(session.deload),
                )

            targets = {
                row.exercise_name.casefold(): row
                for row in db.execute(select(TrainingExerciseProgress)).scalars()
            }

        grouped: dict[str, list[LiftEntry]] = {}
        for (_, name_key), entry in by_key.items():
            grouped.setdefault(name_key, []).append(entry)

        lifts = []
        for name_key, entries in grouped.items():
            mark_prs(entries)
            entries.sort(key=lambda item: item.date)
            estimates = [item for item in entries if item.e1rm is not None and not item.deload]
            if estimates:
                # Best within the unit the lift is logged in now.
                current_unit = (estimates[-1].unit or "kg").lower()
                estimates = [item for item in estimates if (item.unit or "kg").lower() == current_unit]
            best = max(estimates, key=lambda item: item.e1rm) if estimates else None
            name = names[name_key]
            target = targets.get(name_key)
            lifts.append({
                "name": name,
                "slug": TEMPLATE_NAME_TO_SLUG.get(name),
                "sessions": [item.as_dict() for item in entries],
                "best_e1rm": best.e1rm if best else None,
                "best_date": best.date if best else None,
                "pr_count": sum(1 for item in entries if item.is_pr),
                "next_target": None if target is None else {
                    "load": target.load_value,
                    "unit": target.load_unit,
                    "sets": target.sets,
                    "rep_target": target.rep_target,
                    "decision": target.last_decision,
                },
            })
        # Most recently trained first; alphabetical within the same day.
        lifts.sort(key=lambda lift: lift["name"].casefold())
        lifts.sort(key=lambda lift: lift["sessions"][-1]["date"], reverse=True)
        return {"generated_at": datetime.now(UTC).isoformat(), "lifts": lifts}

    @staticmethod
    def _compact_unit(load: float | None, per_side: bool, previous: LiftEntry | None) -> str | None:
        if load is None:
            return None
        if previous is not None and previous.unit:
            return previous.unit
        return "kg/side" if per_side else "kg"

    @staticmethod
    def _local_date(value: datetime, tz: ZoneInfo) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(tz).date().isoformat()
