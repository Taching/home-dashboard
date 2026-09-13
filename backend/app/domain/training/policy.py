from __future__ import annotations

from app.domain.training.types import (
    FatigueState,
    TrainingPhase,
    WeekQuality,
    WorkoutType,
)

PRIORITY = (
    "bjj",
    "recovery",
    "strength_maintenance",
    "aerobic_conditioning",
    "grip_accessories",
)

SACRIFICE_ORDER = (
    "extra_grip",
    "strength_accessories",
    "strength_b",
    "strength_a",
    "zone_2",
    "secondary_volume",
)

HARD_TYPES = frozenset({
    WorkoutType.BJJ_HARD,
    WorkoutType.STRENGTH_A,
    WorkoutType.COMPETITION,
})

BJJ_TYPES = frozenset({
    WorkoutType.BJJ_TECHNICAL,
    WorkoutType.BJJ_NORMAL,
    WorkoutType.BJJ_HARD,
})

DECISIVE_STATUSES = frozenset({"completed", "partial", "in_progress", "skipped"})
COUNTED_STATUSES = frozenset({"planned", "completed", "partial", "in_progress", "recovery", "competition"})

PREFERRED_BJJ_GROUPS = ((0, 1), (3, 4), (5,))


def weekly_targets(phase: TrainingPhase, *, bjj_count: int = 0) -> dict[str, int]:
    taper = phase in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2}
    four_bjj = bjj_count >= 4
    return {
        "bjj": 2 if taper else 3,
        "strength": 1 if taper or four_bjj else 2,
        "zone_2": 0 if four_bjj else 1,
        "intervals": 0 if taper or four_bjj else 1,
        "grip": 1 if taper or four_bjj else 2,
        "rest": 1,
    }


def is_hard(workout_type: WorkoutType) -> bool:
    return workout_type in HARD_TYPES


def assess_week_quality(
    *,
    bjj: int,
    hard_bjj: bool,
    strength: int,
    zone_2: int,
    intervals: int,
    rest: bool,
) -> WeekQuality:
    if bjj <= 2 and strength >= 3 and intervals >= 2 and not rest:
        return WeekQuality.BAD_PLANNING
    if not rest and strength + intervals >= 4:
        return WeekQuality.BAD_PLANNING
    if bjj >= 3 and hard_bjj and 1 <= strength <= 2 and zone_2 >= 1 and rest:
        return WeekQuality.EXCELLENT
    if bjj >= 3 and strength >= 1 and (zone_2 >= 1 or intervals >= 1) and rest:
        return WeekQuality.GOOD
    if bjj >= 2 and (strength >= 1 or zone_2 >= 1) and rest:
        return WeekQuality.ACCEPTABLE
    if not rest:
        return WeekQuality.BAD_PLANNING
    return WeekQuality.ACCEPTABLE


def fatigue_keeps_bjj(state: FatigueState) -> bool:
    return state in {FatigueState.NORMAL, FatigueState.TIRED}
