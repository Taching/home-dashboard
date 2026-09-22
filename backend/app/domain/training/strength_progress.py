from __future__ import annotations

from dataclasses import dataclass, replace
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
    increment: float = 2.5
    rep_min: int | None = None
    rep_max: int | None = None
    fixed_reps: str | None = None
    unit_suffix: str = ""
    load_optional: bool = False  # bodyweight/accessory lifts the doc explicitly says not to load aggressively


DEFAULT_RECIPE = ExerciseRecipe(kind="load", increment=2.5)

# Per-exercise recipes from the doc. Exercises not listed here (e.g. conditioning
# blocks) fall back to DEFAULT_RECIPE, which is never reached in practice because
# the caller skips non-strength entries entirely (see templates.STRENGTH_SKIP).
RECIPES: dict[str, ExerciseRecipe] = {
    "Deadlift": ExerciseRecipe(kind="load", increment=2.5, fixed_reps="3"),
    "Back Squat": ExerciseRecipe(kind="load", increment=2.5, fixed_reps="3"),
    "Bench Press": ExerciseRecipe(kind="load", increment=2.5, fixed_reps="3"),
    "Standing Landmine Rotation": ExerciseRecipe(kind="load", increment=1.0, fixed_reps="8/side"),
    "Military Press": ExerciseRecipe(kind="double_progression", increment=2.5, rep_min=5, rep_max=7),
    "Weighted Dips": ExerciseRecipe(kind="double_progression", increment=2.5, rep_min=6, rep_max=8),
    "Seated Cable Row": ExerciseRecipe(kind="double_progression", increment=2.5, rep_min=8, rep_max=12),
    "Bulgarian Split Squat": ExerciseRecipe(
        kind="double_progression", increment=1.0, rep_min=6, rep_max=8,
        unit_suffix="/leg", load_optional=True,
    ),
    "Pull-ups": ExerciseRecipe(kind="double_progression", increment=0.0, rep_min=6, rep_max=8, load_optional=True),
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


def decide(classification: Classification) -> Decision:
    if classification == Classification.EASY:
        return Decision.PROGRESS
    if classification == Classification.TOO_HARD:
        return Decision.REDUCE
    return Decision.REPEAT


def _round_half(value: float) -> float:
    return round(value * 2) / 2


def apply_decision(state: ExerciseState, decision: Decision, recipe: ExerciseRecipe) -> ExerciseState:
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
        if recipe.kind == "double_progression" and rep_target is not None and recipe.rep_max is not None and rep_target < recipe.rep_max:
            rep_target = rep_target + 1
        return replace(state, rep_target=rep_target)

    # PROGRESS
    if recipe.kind == "double_progression":
        if rep_target is None:
            rep_target = recipe.rep_min
        if recipe.rep_max is not None and rep_target >= recipe.rep_max:
            rep_target = recipe.rep_min if recipe.rep_min is not None else rep_target
            if not recipe.load_optional and load is not None:
                load = _round_half(load + recipe.increment)
        else:
            rep_target = rep_target + 1
        return replace(state, load_value=load, rep_target=rep_target)
    if load is not None:
        load = _round_half(load + recipe.increment)
    return replace(state, load_value=load)


def deload_prescription(state: ExerciseState, recipe: ExerciseRecipe) -> ExerciseState:
    sets = max(1, state.sets - 1)
    load = state.load_value
    if not recipe.load_optional and load is not None:
        load = _round_half(load * 0.85)
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
