from __future__ import annotations

from app.domain.training.types import (
    CAMPAIGN_PHASES,
    TAPER_PHASES,
    FatigueState,
    SessionStatus,
    TrainingPhase,
    WeekQuality,
    WorkoutType,
)

# Hard Rules V2 priority when two sessions conflict.
# Calendar weekday labels are suggestions. Completed training is truth.
PRIORITY = (
    "confirmed_bjj",
    "required_recovery",
    "hard_competition_bjj",
    "strength_maintenance",
    "zone_2",
    "grip_accessories",
)

# First sacrificed when the week is crowded or a BJJ opportunity appears.
SACRIFICE_ORDER = (
    "grip",
    "zone_2",
    "strength_b",
    "strength_a",
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

# Future sessions in this set yield to a BJJ opportunity. They may be
# replanned elsewhere after BJJ and recovery have reserved their space.
BJJ_DISPLACEABLE_TYPES = frozenset({
    WorkoutType.STRENGTH_A,
    WorkoutType.STRENGTH_B,
    WorkoutType.ZONE_2,
    WorkoutType.GRIP,
})

DECISIVE_STATUSES = frozenset({"completed", "partial", "in_progress", "skipped"})
COUNTED_STATUSES = frozenset({"planned", "completed", "partial", "in_progress", "recovery", "competition"})
LIVE_STATUSES = frozenset({
    SessionStatus.PLANNED,
    SessionStatus.IN_PROGRESS,
    SessionStatus.COMPLETED,
    SessionStatus.PARTIAL,
    SessionStatus.RECOVERY,
    SessionStatus.COMPETITION,
})
COMPLETED_STATUSES = frozenset({
    SessionStatus.COMPLETED,
    SessionStatus.PARTIAL,
    SessionStatus.IN_PROGRESS,
})

# Usual class windows live on the explicit Mita class template, not here.


def weekly_targets(phase: TrainingPhase, *, bjj_count: int = 0) -> dict[str, int]:
    four_bjj = bjj_count >= 4
    if phase in CAMPAIGN_PHASES:
        return _campaign_targets(phase, four_bjj=four_bjj)
    taper = phase in TAPER_PHASES
    return {
        "bjj": 2 if taper else 3,
        "strength": 1 if taper or four_bjj else 2,
        "zone_2": 0 if four_bjj else 1,
        "intervals": 0 if taper or four_bjj else 1,
        "grip": 1 if taper or four_bjj else 2,
        "rest": 0,
    }


def _campaign_targets(phase: TrainingPhase, *, four_bjj: bool) -> dict[str, int]:
    """March 2027 plan. BJJ 3–4, strength 2, easy cardio 2 (Strength A carries
    one 20–30 min easy-cardio finisher, so the planner only places the rest as
    separate Zone 2), no sprint intervals, no standalone grip (carries cover
    it), and at least one full rest day. A fourth BJJ removes the second cardio
    first. Final six weeks: four BJJ, two short strength, cardio only if it
    helps recovery. Taper: volume down 40–60%."""
    if phase == TrainingPhase.PEAK_3:
        return {"bjj": 4, "strength": 2, "zone_2": 0, "intervals": 0, "grip": 0, "rest": 1}
    if phase == TrainingPhase.TAPER_3:
        return {"bjj": 3, "strength": 1, "zone_2": 0, "intervals": 0, "grip": 0, "rest": 1}
    return {"bjj": 3, "strength": 2, "zone_2": 0 if four_bjj else 1, "intervals": 0, "grip": 0, "rest": 1}


def is_hard(workout_type: WorkoutType) -> bool:
    return workout_type in HARD_TYPES


def is_bjj(workout_type: WorkoutType) -> bool:
    return workout_type in BJJ_TYPES


def assess_week_quality(
    *,
    bjj: int,
    hard_bjj: bool,
    strength: int,
    zone_2: int,
    intervals: int,
    rest: bool,
) -> WeekQuality:
    if bjj <= 2 and strength >= 3 and intervals >= 2:
        return WeekQuality.BAD_PLANNING
    if strength + intervals >= 4 and bjj <= 1:
        return WeekQuality.BAD_PLANNING
    if bjj >= 3 and hard_bjj and 1 <= strength <= 2:
        return WeekQuality.EXCELLENT
    if bjj >= 3 and strength >= 1:
        return WeekQuality.GOOD
    if bjj >= 2 and (strength >= 1 or zone_2 >= 1):
        return WeekQuality.ACCEPTABLE
    if strength >= 3 and intervals >= 2 and bjj <= 1:
        return WeekQuality.BAD_PLANNING
    return WeekQuality.ACCEPTABLE


def fatigue_keeps_bjj(state: FatigueState) -> bool:
    return state in {FatigueState.NORMAL, FatigueState.TIRED}
