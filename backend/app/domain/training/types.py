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


class MissReason(StrEnum):
    WEATHER = "WEATHER"
    OVERSLEPT = "OVERSLEPT"
    GYM_HOLIDAY = "GYM_HOLIDAY"
    GYM_CLOSED = "GYM_CLOSED"
    NO_CLASS = "NO_CLASS"
    SCHEDULE_CONFLICT = "SCHEDULE_CONFLICT"
    WORK = "WORK"
    TRANSPORTATION = "TRANSPORTATION"
    FATIGUE = "FATIGUE"
    POOR_SLEEP = "POOR_SLEEP"
    INJURY = "INJURY"
    ILLNESS = "ILLNESS"
    USER_CANCELLED = "USER_CANCELLED"
    OTHER = "OTHER"


class RecordStatus(StrEnum):
    COMPLETED = "COMPLETED"
    MISSED = "MISSED"
    PLANNED = "PLANNED"


class FatigueLevel(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class SorenessLevel(StrEnum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class SleepQuality(StrEnum):
    POOR = "POOR"
    NORMAL = "NORMAL"
    GOOD = "GOOD"


class ClassType(StrEnum):
    NORMAL = "NORMAL"
    COMPETITION = "COMPETITION"
    OPEN_MAT = "OPEN_MAT"
    DRILLING = "DRILLING"


class ClosureType(StrEnum):
    HOLIDAY = "HOLIDAY"
    SPECIAL_CLOSURE = "SPECIAL_CLOSURE"
    TOURNAMENT = "TOURNAMENT"
    MAINTENANCE = "MAINTENANCE"
    NO_CLASS = "NO_CLASS"


INJURY_EXCLUDED_DEFAULT = frozenset({
    WorkoutType.BJJ_TECHNICAL,
    WorkoutType.BJJ_NORMAL,
    WorkoutType.BJJ_HARD,
    WorkoutType.STRENGTH_A,
    WorkoutType.STRENGTH_B,
})


@dataclass(frozen=True)
class TrainingRecord:
    date: date
    session: WorkoutType
    status: RecordStatus
    miss_reason: MissReason | None = None


@dataclass(frozen=True)
class GymAvailability:
    date: date
    is_open: bool
    gym_id: str | None = None
    reason: str | None = None


@dataclass(frozen=True)
class BjjClassAvailability:
    date: date
    start_time: time
    class_type: ClassType
    available: bool
    gym_id: str = "mita"


@dataclass(frozen=True)
class ClassTemplate:
    weekday: int
    start_time: time
    class_type: ClassType
    gym_id: str = "mita"


@dataclass(frozen=True)
class WeatherCondition:
    date: date
    precipitation_probability: float = 0
    precipitation_mm: float | None = None
    wind_kph: float | None = None
    severe_weather: bool = False
    weather_code: str | None = None
    blocks_travel: bool | None = None


@dataclass(frozen=True)
class AthleteState:
    fatigue: FatigueLevel = FatigueLevel.NORMAL
    soreness: SorenessLevel = SorenessLevel.NORMAL
    injured: bool = False
    sleep_quality: SleepQuality | None = None
    exclude_types: frozenset[WorkoutType] = field(default_factory=frozenset)


@dataclass(frozen=True)
class WeekAdaptation:
    strength_load_delta: float = 0.0
    strength_volume_delta: float = 0.0
    zone2_minutes_delta: int = 0
    grip_sets_delta: int = 0
    bjj_rounds_delta: int = 0
    extra_rest_before_hard_bjj: bool = False
    reduce_preceding_strength: bool = False
    notes: str = ""


@dataclass(frozen=True)
class SchedulerInput:
    today: date
    history: tuple[TrainingRecord, ...] = ()
    gym_availability: tuple[GymAvailability, ...] = ()
    weather: tuple[WeatherCondition, ...] = ()
    athlete_state: AthleteState = field(default_factory=AthleteState)
    class_availability: tuple[BjjClassAvailability, ...] = ()
    class_template: tuple[ClassTemplate, ...] = ()
    unavailability: tuple[date, ...] = ()
    upcoming_hard_bjj: date | None = None
    tournament_date: date | None = None
    adaptation: WeekAdaptation | None = None
    planned_future: tuple[TrainingRecord, ...] = ()
    horizon_days: int = 7
    pinned_bjj: tuple[tuple[date, WorkoutType], ...] = ()
    locked_sessions: tuple[tuple[date, WorkoutType], ...] = ()
    as_of: datetime | None = None


@dataclass(frozen=True)
class DayPlan:
    session: WorkoutType | None
    recovery_penalty: float = 0
    reason: str = ""
    blocked: tuple[str, ...] = ()
    close_set: tuple[WorkoutType, ...] = ()
    status: str = "planned"

    @property
    def sessions(self) -> tuple[WorkoutType, ...]:
        return (self.session,) if self.session is not None else ()


class RebuildResult:
    def __init__(self, days: dict[date, DayPlan]) -> None:
        self.days = days

    def __getitem__(self, key: date | str) -> DayPlan:
        if isinstance(key, str):
            key = date.fromisoformat(key)
        return self.days[key]

    def get(self, key: date | str, default: DayPlan | None = None) -> DayPlan | None:
        if isinstance(key, str):
            key = date.fromisoformat(key)
        return self.days.get(key, default)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, str):
            key = date.fromisoformat(key)
        return key in self.days

    def values(self):
        return self.days.values()

    def items(self):
        return self.days.items()

    def future_sessions(self, today: date) -> dict[date, WorkoutType | None]:
        return {day: plan.session for day, plan in self.days.items() if day >= today}
