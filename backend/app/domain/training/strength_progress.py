from __future__ import annotations

import math
from dataclasses import dataclass, replace
from datetime import date, timedelta
from enum import StrEnum


class Classification(StrEnum):
    EASY = "easy"
    APPROPRIATE = "appropriate"
    HARD = "hard"
    TOO_HARD = "too_hard"


class Decision(StrEnum):
    PROGRESS = "progress"
    REPEAT = "repeat"
    REDUCE = "reduce"


@dataclass(frozen=True)
class ExerciseRecipe:
    kind: str  # "load" (fixed reps, load-only progression) or "double_progression" (rep range then load)
    increment: float = 2.5  # step after a comfortable session (logged RPE 7.5–8)
    rep_min: int | None = None
    rep_max: int | None = None
    fixed_reps: str | None = None
    unit_suffix: str = ""
    load_optional: bool = False  # bodyweight/accessory lifts the doc explicitly says not to load aggressively
    increment_easy: float | None = None  # bigger step when the logged RPE was 7 or lower
    round_to: float = 0.5  # real plate/dumbbell/kettlebell step for deload loads


# October 2026 program. Strength A/B run in four-week blocks from this Monday:
# three building weeks, then a deload week. The taper replaces the block.
PROGRAM_START = date(2026, 10, 19)
DELOAD_EVERY_WEEKS = 4
COMFORTABLE_RPE = 8.0
DELOAD_LOAD_FACTOR = 0.875  # 10–15% lighter


DEFAULT_RECIPE = ExerciseRecipe(kind="load", increment=2.5)

# Per-exercise recipes from the doc. Exercises not listed here (e.g. conditioning
# blocks) fall back to DEFAULT_RECIPE, which is never reached in practice because
# the caller skips non-strength entries entirely (see templates.STRENGTH_SKIP).
RECIPES: dict[str, ExerciseRecipe] = {
    # Big lower-body lifts: +2.5–5 kg once the prescribed reps feel comfortable.
    "Trap-bar Deadlift": ExerciseRecipe(kind="double_progression", increment=2.5, increment_easy=5.0, rep_min=3, rep_max=4, round_to=2.5),
    "Front Squat": ExerciseRecipe(kind="double_progression", increment=2.5, increment_easy=5.0, rep_min=4, rep_max=5, round_to=2.5),
    "Romanian Deadlift": ExerciseRecipe(kind="load", increment=2.5, increment_easy=5.0, fixed_reps="6", round_to=2.5),
    # Presses and weighted pull-ups: +1–2.5 kg.
    "Dumbbell Bench Press": ExerciseRecipe(kind="double_progression", increment=2.0, rep_min=6, rep_max=8, round_to=2.0),
    "Military Press": ExerciseRecipe(kind="load", increment=1.0, increment_easy=2.5, fixed_reps="5", round_to=0.5),
    "Weighted Pull-up": ExerciseRecipe(kind="double_progression", increment=1.0, increment_easy=2.5, rep_min=5, rep_max=6, round_to=0.5),
    "Bulgarian Split Squat": ExerciseRecipe(kind="double_progression", increment=2.0, rep_min=6, rep_max=8, unit_suffix="/leg", round_to=2.0),
    "Kettlebell Swing": ExerciseRecipe(kind="load", increment=4.0, fixed_reps="8", round_to=4.0),
    # Cable work: reps to the top of the range first, then one stack step.
    "Cable Row": ExerciseRecipe(kind="double_progression", increment=2.5, rep_min=8, rep_max=10, round_to=2.5),
    "Cable Face Pull": ExerciseRecipe(kind="double_progression", increment=2.5, rep_min=12, rep_max=15, round_to=2.5),
    # Core: reps first, resistance gradually.
    "Pallof Press": ExerciseRecipe(kind="double_progression", increment=2.5, rep_min=10, rep_max=12, unit_suffix="/side", round_to=2.5),
    "Hanging Knee Raise": ExerciseRecipe(kind="double_progression", increment=0.0, rep_min=8, rep_max=12, load_optional=True),
    # Retired programs; kept so logged history still resolves.
    "Chest-Supported Row": ExerciseRecipe(kind="double_progression", increment=2.0, rep_min=6, rep_max=10),
    "Deadlift": ExerciseRecipe(kind="load", increment=2.5, fixed_reps="3"),
    "Back Squat": ExerciseRecipe(kind="load", increment=2.5, fixed_reps="3"),
    "Bench Press": ExerciseRecipe(kind="load", increment=2.5, fixed_reps="3"),
    "Standing Landmine Rotation": ExerciseRecipe(kind="load", increment=1.0, fixed_reps="8/side"),
    "Weighted Dips": ExerciseRecipe(kind="double_progression", increment=2.5, rep_min=6, rep_max=8),
    "Seated Cable Row": ExerciseRecipe(kind="double_progression", increment=2.5, rep_min=8, rep_max=12),
    "Pull-ups": ExerciseRecipe(kind="double_progression", increment=0.0, rep_min=6, rep_max=10, load_optional=True),
    "Leg Raise": ExerciseRecipe(kind="double_progression", increment=0.0, rep_min=6, rep_max=10, load_optional=True),
}


def recipe_for(exercise_name: str) -> ExerciseRecipe:
    return RECIPES.get(exercise_name, DEFAULT_RECIPE)


@dataclass(frozen=True)
class ExerciseState:
    workout_type: str
    exercise_name: str
    load_value: float | None
    load_unit: str | None
    sets: int
    rep_target: int | None


def classify(
    *,
    rpe: float | None,
    technique: str | None,
    pain: bool | None,
    sets_done: int | None,
    sets_prescribed: int | None,
) -> Classification:
    if pain:
        return Classification.TOO_HARD
    if technique == "breakdown":
        return Classification.TOO_HARD
    if sets_done is not None and sets_prescribed is not None and sets_done < sets_prescribed:
        return Classification.TOO_HARD
    if rpe is not None and rpe >= 9:
        return Classification.TOO_HARD
    if technique == "shaky" or (rpe is not None and rpe >= 8.5):
        return Classification.HARD
    if rpe is not None and rpe <= 7:
        return Classification.EASY
    return Classification.APPROPRIATE


def decide(classification: Classification, *, rpe: float | None = None) -> Decision:
    """Add weight only on evidence: a logged RPE of 8 or less ("prescribed reps
    completed comfortably"). Plain done-ticks without an RPE hold steady."""
    if classification == Classification.EASY:
        return Decision.PROGRESS
    if classification == Classification.TOO_HARD:
        return Decision.REDUCE
    if classification == Classification.APPROPRIATE and rpe is not None and rpe <= COMFORTABLE_RPE:
        return Decision.PROGRESS
    return Decision.REPEAT


def _round_half(value: float) -> float:
    return round(value * 2) / 2


def _round_to(value: float, step: float) -> float:
    step = step or 0.5
    return round(round(value / step) * step, 2)


def _step(recipe: ExerciseRecipe, rpe: float | None) -> float:
    if rpe is not None and rpe <= 7 and recipe.increment_easy is not None:
        return recipe.increment_easy
    return recipe.increment


def apply_decision(
    state: ExerciseState, decision: Decision, recipe: ExerciseRecipe, *, rpe: float | None = None,
) -> ExerciseState:
    load = state.load_value
    sets = state.sets
    rep_target = state.rep_target

    if decision == Decision.REDUCE:
        sets = max(1, sets - 1)
        if recipe.kind == "double_progression" and rep_target is not None and recipe.rep_min is not None:
            rep_target = max(recipe.rep_min, rep_target - 1)
        if not recipe.load_optional and load is not None:
            load = _round_half(load * 0.93)
        return replace(state, load_value=load, sets=sets, rep_target=rep_target)

    if decision == Decision.REPEAT:
        return state

    # PROGRESS: reps first inside the range, then load at the top.
    step = _step(recipe, rpe)
    if recipe.kind == "double_progression":
        if rep_target is None:
            rep_target = recipe.rep_min
        if recipe.rep_max is not None and rep_target >= recipe.rep_max:
            if recipe.load_optional or load is None or not step:
                # Nothing to add yet (bodyweight, or no logged load): stay at the top.
                return replace(state, rep_target=recipe.rep_max)
            return replace(state, load_value=_round_half(load + step), rep_target=recipe.rep_min)
        return replace(state, rep_target=rep_target + 1)
    if load is not None:
        load = _round_half(load + step)
    return replace(state, load_value=load)


def _week_index(day: date) -> int | None:
    # Training weeks run Monday–Saturday; Sunday already belongs to the next week.
    anchor = day + timedelta(days=1) if day.weekday() == 6 else day
    if anchor < PROGRAM_START:
        return None
    return (anchor - PROGRAM_START).days // 7


def is_deload_week(day: date) -> bool:
    """Every fourth training week of the block, counted from PROGRAM_START."""
    index = _week_index(day)
    return index is not None and index % DELOAD_EVERY_WEEKS == DELOAD_EVERY_WEEKS - 1


def block_week(day: date) -> int | None:
    """1–4 within the current block (4 is the deload), or None before the program."""
    index = _week_index(day)
    return None if index is None else index % DELOAD_EVERY_WEEKS + 1


def next_deload_week(day: date) -> date:
    start = PROGRAM_START + timedelta(days=((max(day, PROGRAM_START) - PROGRAM_START).days // 7) * 7)
    while not is_deload_week(start):
        start += timedelta(days=7)
    return start


def deload_prescription(state: ExerciseState, recipe: ExerciseRecipe) -> ExerciseState:
    """Deload week: about half the working sets at 10–15% less weight."""
    sets = max(1, math.ceil(state.sets / 2))
    load = state.load_value
    if load is not None and not recipe.load_optional:
        load = _round_to(load * DELOAD_LOAD_FACTOR, recipe.round_to)
    rep_target = state.rep_target
    if recipe.kind == "double_progression" and recipe.rep_min is not None:
        rep_target = recipe.rep_min
    return replace(state, load_value=load, sets=sets, rep_target=rep_target)


def seed_state(workout_type: str, *, name: str, load_value: float | None, load_unit: str | None, sets: int | None, recipe: ExerciseRecipe) -> ExerciseState:
    rep_target = recipe.rep_min if recipe.kind == "double_progression" else None
    return ExerciseState(
        workout_type=workout_type, exercise_name=name, load_value=load_value,
        load_unit=load_unit, sets=sets or 3, rep_target=rep_target,
    )


def render_reps(state: ExerciseState, recipe: ExerciseRecipe) -> str | None:
    if recipe.kind == "load":
        return recipe.fixed_reps
    if state.rep_target is None:
        return recipe.fixed_reps
    return f"{state.rep_target}{recipe.unit_suffix}"


DELOAD_FATIGUE_THRESHOLD = 2


def evaluate_deload_triggers(sessions: list[dict], sleep_hours: list[float]) -> dict[str, bool]:
    """Doc's §Automatic Deload Triggers, approximated with the signals the app
    actually logs today. "Low motivation" from the doc isn't tracked anywhere
    and is left out. Localizing the deload to one muscle group/track isn't
    modeled either — a trigger deloads both Strength A and B's next occurrence.
    """
    hard_strength = [
        item for item in sessions
        if str(item.get("planned_type") or "").startswith("strength_")
        and item.get("status") in {"completed", "partial"}
        and (item.get("result") or {}).get("session_rpe") is not None
        and float(item["result"]["session_rpe"]) >= 8.5
    ]
    grip_fatigue_high = any((item.get("result") or {}).get("grip_fatigue") in {"HIGH", "high"} for item in sessions)
    hard_bjj_poor = any(
        str(item.get("planned_type") or "") == "bjj_hard"
        and (item.get("result") or {}).get("technical_performance") in {"poor", "down"}
        for item in sessions
    )
    high_soreness_count = sum(1 for item in sessions if (item.get("result") or {}).get("soreness") in {"HIGH", "high"})
    avg_sleep = sum(sleep_hours) / len(sleep_hours) if sleep_hours else None
    signals = [
        len(hard_strength) >= 2,
        grip_fatigue_high,
        hard_bjj_poor,
        high_soreness_count >= 2,
        avg_sleep is not None and avg_sleep < 6,
    ]
    force = sum(1 for signal in signals if signal) >= DELOAD_FATIGUE_THRESHOLD
    return {"strength_a": force, "strength_b": force}
