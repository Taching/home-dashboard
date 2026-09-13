from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from enum import StrEnum


class WorkoutType(StrEnum):
    BJJ_TECHNICAL = "bjj_technical"
    BJJ_NORMAL = "bjj_normal"
    BJJ_HARD = "bjj_hard"
    STRENGTH_A = "strength_a"
    STRENGTH_B = "strength_b"
    ZONE_2 = "zone_2"
    GRIP = "grip"
    RECOVERY = "recovery"
    REST = "rest"
    COMPETITION = "competition"


class SessionStatus(StrEnum):
    PLANNED = "planned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    SKIPPED = "skipped"
    RECOVERY = "recovery"
    COMPETITION = "competition"
    CANCELLED = "cancelled"


class TrainingPhase(StrEnum):
    BUILD_1 = "build_october"
    TAPER_1 = "taper_october"
    COMPETITION_1 = "competition_october"
    RECOVERY_1 = "recovery_october"
    BUILD_2 = "build_november"
    TAPER_2 = "taper_november"
    COMPETITION_2 = "competition_november"
    POST_COMPETITION = "post_competition"


class ReadinessLevel(StrEnum):
    UNKNOWN = "unknown"
    GREEN = "green"
    YELLOW = "yellow"
    RED = "red"
    MANUAL_REVIEW = "manual_review"


class FatigueState(StrEnum):
    NORMAL = "normal"
    TIRED = "tired"
    VERY_FATIGUED = "very_fatigued"
    PAIN = "pain"


class WeekQuality(StrEnum):
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    BAD_PLANNING = "bad_planning"


@dataclass(frozen=True)
class ExercisePrescription:
    name: str
    load_value: float | None = None
    load_unit: str | None = None
    sets: int | None = None
    reps: str | None = None
    duration_seconds: int | None = None
    notes: str | None = None


@dataclass(frozen=True)
class WorkoutTemplate:
    type: WorkoutType
    title: str
    estimated_minutes: int
    intensity: str
    exercises: tuple[ExercisePrescription, ...] = ()
    conditioning: str | None = None


@dataclass(frozen=True)
class ReadinessInput:
    sleep_hours: float | None = None
    sleep_quality: int | None = None
    fatigue: int | None = None
    soreness: int | None = None
    grip_fatigue: int | None = None
    pain: bool | None = None
    readiness: int | None = None
    prior_hard_bjj: bool = False


@dataclass(frozen=True)
class ReadinessAssessment:
    level: ReadinessLevel
    alerts: tuple[str, ...]
    suppress_grip: bool = False


@dataclass(frozen=True)
class FixedBjjEvent:
    external_id: str
    title: str
    start_at: datetime
    end_at: datetime


@dataclass(frozen=True)
class ExistingSession:
    id: str
    type: WorkoutType
    start_at: datetime
    end_at: datetime
    status: SessionStatus
    pinned: bool = False
    source_calendar_event_id: str | None = None
    suppresses_type: WorkoutType | None = None
    source: str = "scheduler"


@dataclass(frozen=True)
class BjjCandidate:
    day: date
    suggested_type: WorkoutType
    reason: str
    preferred_clock: time | None = None


@dataclass(frozen=True)
class WeatherHint:
    day: date
    outdoor_impractical: bool = False
    condition: str = ""


@dataclass(frozen=True)
class PlannedSession:
    type: WorkoutType
    start_at: datetime
    end_at: datetime
    phase: TrainingPhase
    reason: str
    intensity: str
    exercises: tuple[ExercisePrescription, ...] = ()
    coach_focus: tuple[str, ...] = ()
    preparation: str | None = None
    target_rounds: int | None = None
    round_length_seconds: int | None = None
    rest_seconds: int | None = None
    source: str = "scheduler"
    pinned: bool = False
    source_calendar_event_id: str | None = None
    is_all_day: bool = False

    @property
    def local_date(self) -> date:
        return self.start_at.date()


@dataclass(frozen=True)
class WeekPlan:
    week_start: date
    sessions: tuple[PlannedSession, ...] = field(default_factory=tuple)
    candidates: tuple[BjjCandidate, ...] = field(default_factory=tuple)
