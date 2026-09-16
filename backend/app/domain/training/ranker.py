from __future__ import annotations

from datetime import date, timedelta

from app.domain.training.constraints import BJJ_TYPES, STRENGTH_TYPES, DayAvailability, needs_rest
from app.domain.training.types import AthleteState, SchedulerInput, WorkoutType

PRIORITY = (
    WorkoutType.BJJ_HARD,
    WorkoutType.BJJ_NORMAL,
    WorkoutType.BJJ_TECHNICAL,
    WorkoutType.STRENGTH_A,
    WorkoutType.STRENGTH_B,
    WorkoutType.REST,
    WorkoutType.RECOVERY,
    WorkoutType.ZONE_2,
    WorkoutType.GRIP,
)

SCORE = {
    WorkoutType.BJJ_HARD: 100,
    WorkoutType.BJJ_NORMAL: 90,
    WorkoutType.BJJ_TECHNICAL: 88,
    WorkoutType.STRENGTH_A: 70,
    WorkoutType.STRENGTH_B: 70,
    WorkoutType.REST: 25,
    WorkoutType.RECOVERY: 28,
    WorkoutType.ZONE_2: 40,
    WorkoutType.GRIP: 30,
}


def valid_candidates(
    day: date,
    avail: DayAvailability,
    inp: SchedulerInput,
    *,
    next_strength: WorkoutType | None,
    strength_remaining: bool,
    hard_bjj_day: date | None,
    protect_hard: bool,
) -> list[WorkoutType]:
    if not avail.user_available:
        return []
    options: list[WorkoutType] = []
    if avail.allows(WorkoutType.BJJ_HARD) and (hard_bjj_day == day or _class_hard(avail)):
        options.append(WorkoutType.BJJ_HARD)
    if avail.allows(WorkoutType.BJJ_NORMAL) and WorkoutType.BJJ_HARD not in options:
        options.append(WorkoutType.BJJ_NORMAL)
    if strength_remaining and next_strength and avail.allows(next_strength):
        if not (hard_bjj_day is not None and day == hard_bjj_day - timedelta(days=1)):
            if not (protect_hard and hard_bjj_day is not None and day == hard_bjj_day - timedelta(days=1)):
                options.append(next_strength)
    if avail.allows(WorkoutType.ZONE_2):
        options.append(WorkoutType.ZONE_2)
    if avail.allows(WorkoutType.GRIP):
        options.append(WorkoutType.GRIP)
    options.append(WorkoutType.REST)
    if needs_rest(inp.athlete_state) and day == inp.today:
        return [WorkoutType.REST, WorkoutType.RECOVERY]
    if inp.athlete_state.injured:
        return [item for item in options if item not in BJJ_TYPES and item not in STRENGTH_TYPES] or [WorkoutType.REST]
    return options


def score_session(
    session: WorkoutType,
    day: date,
    inp: SchedulerInput,
    *,
    hard_bjj_day: date | None,
    missed_bjj: bool,
) -> int:
    value = SCORE.get(session, 0)
    if session in BJJ_TYPES and missed_bjj:
        value += 15
    if hard_bjj_day is not None and day == hard_bjj_day - timedelta(days=1):
        if session in STRENGTH_TYPES:
            return 0
        if session in {WorkoutType.REST, WorkoutType.RECOVERY}:
            value = 95
        elif session == WorkoutType.ZONE_2:
            value = 45
        elif session == WorkoutType.GRIP:
            value = 35
    if needs_rest(inp.athlete_state) and day == inp.today:
        if session in {WorkoutType.REST, WorkoutType.RECOVERY}:
            value = 100
        else:
            value = 0
    return value


def pick_default(candidates: list[WorkoutType], scores: dict[WorkoutType, int]) -> WorkoutType | None:
    if not candidates:
        return None
    ranked = sorted(candidates, key=lambda item: (-scores.get(item, 0), PRIORITY.index(item) if item in PRIORITY else 99))
    return ranked[0]


def close_set(candidates: list[WorkoutType], scores: dict[WorkoutType, int], default: WorkoutType | None) -> tuple[WorkoutType, ...]:
    if default is None:
        return ()
    ordered = sorted(candidates, key=lambda item: (-scores.get(item, 0), PRIORITY.index(item) if item in PRIORITY else 99))
    chosen = [default]
    top = scores.get(default, 0)
    for item in ordered:
        if item == default:
            continue
        if top - scores.get(item, 0) <= 15 and len(chosen) < 3:
            chosen.append(item)
    return tuple(chosen)


def deterministic_reason(
    session: WorkoutType | None,
    day: date,
    inp: SchedulerInput,
    blocked: tuple[str, ...],
    *,
    missed_bjj: bool,
    hard_bjj_day: date | None,
) -> str:
    athlete = inp.athlete_state
    bits = []
    completed = [item for item in inp.history if item.status.value == "COMPLETED"]
    missed = [item for item in inp.history if item.status.value == "MISSED"]
    if completed:
        bits.append("Completed: " + ", ".join(f"{item.date.isoformat()} {item.session.value}" for item in completed[-3:]))
    if missed:
        bits.append("Missed: " + ", ".join(
            f"{item.date.isoformat()} {item.session.value}" + (f" ({item.miss_reason.value})" if item.miss_reason else "")
            for item in missed[-3:]
        ) + ". Misses did not add fatigue.")
    bits.append(
        f"Recovery is {athlete.fatigue.value.lower()} fatigue, {athlete.soreness.value.lower()} soreness"
        + (f", sleep {athlete.sleep_quality.value.lower()}" if athlete.sleep_quality else "")
        + "."
    )
    if hard_bjj_day:
        bits.append(f"Next hard BJJ is {hard_bjj_day.isoformat()}.")
    if session is None:
        bits.append("No workout: " + (", ".join(blocked) or "unavailable") + ".")
    elif session == WorkoutType.REST and hard_bjj_day == day + timedelta(days=1):
        bits.append("Rest protects hard BJJ quality tomorrow.")
    elif session in BJJ_TYPES and missed_bjj:
        bits.append("BJJ is the highest-value session after logistical misses.")
    elif session in STRENGTH_TYPES:
        bits.append(f"{session.value.replace('_', ' ').title()} is the next useful indoor session.")
    else:
        bits.append(f"{session.value.replace('_', ' ').title()} has the highest value among valid options.")
    return " ".join(bits)


def _class_hard(avail: DayAvailability) -> bool:
    if avail.bjj_class is None:
        return False
    return avail.bjj_class.class_type.value == "COMPETITION"
