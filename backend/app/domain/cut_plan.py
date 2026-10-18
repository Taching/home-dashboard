"""March 2027 weight cut — pure rules from the competition plan.

Toshi weighs in each morning (optional field on /daily). Progress is judged only
from the seven-day average; the checkpoint table is a trend target, not a
pass/fail test. Nutrition is targets only — food is tracked in another app.
"""
from __future__ import annotations

from datetime import date, timedelta

# (date, low, high) seven-day-average targets in kg, morning, no gi.
CHECKPOINTS: tuple[tuple[date, float, float], ...] = (
    (date(2026, 10, 19), 84.0, 84.0),
    (date(2026, 11, 2), 83.0, 83.0),
    (date(2026, 12, 7), 80.5, 81.0),
    (date(2027, 1, 4), 78.5, 79.0),
    (date(2027, 2, 1), 76.5, 77.0),
    (date(2027, 2, 22), 75.0, 75.5),
    (date(2027, 3, 1), 74.0, 74.5),
)
CUT_START = CHECKPOINTS[0][0]
# First 14 days are the calorie trial; the first week's water-weight drop is ignored.
TRIAL_END = CUT_START + timedelta(days=14)

LIGHTWEIGHT_LIMIT_GI_KG = 76.0
MIDDLEWEIGHT_LIMIT_GI_KG = 82.3
DIVISION_DECISION_DATE = date(2027, 1, 15)
LIGHTWEIGHT_KEEP_KG = 78.0
MIDDLEWEIGHT_SWITCH_KG = 79.0

TRAINING_DAY_KCAL = 2300
REST_DAY_KCAL = 2000
PROTEIN_G = (165, 175)
FAT_G = (60, 70)
KCAL_STEP = 150
SLOW_LOSS_KG_PER_WEEK = 0.25
FAST_LOSS_KG_PER_WEEK = 0.75
# Planner session types that count as a "BJJ/strength day" for food.
TRAINING_DAY_TYPES = frozenset({
    "bjj_technical", "bjj_normal", "bjj_hard", "strength_a", "strength_b", "competition",
})
STOP_RULE = (
    "Dizziness, fainting, chest pain, persistent exhaustion or bingeing: stop the cut "
    "and talk to a clinician or sports dietitian."
)


def target_for(day: date) -> tuple[float, float]:
    """Linear trend between checkpoints, clamped at both ends."""
    if day <= CHECKPOINTS[0][0]:
        return CHECKPOINTS[0][1], CHECKPOINTS[0][2]
    for (start, low_a, high_a), (end, low_b, high_b) in zip(CHECKPOINTS, CHECKPOINTS[1:]):
        if start <= day <= end:
            ratio = (day - start).days / (end - start).days
            return round(low_a + (low_b - low_a) * ratio, 1), round(high_a + (high_b - high_a) * ratio, 1)
    return CHECKPOINTS[-1][1], CHECKPOINTS[-1][2]


def next_checkpoint(day: date) -> tuple[date, float, float] | None:
    return next((item for item in CHECKPOINTS if item[0] >= day), None)


def seven_day_average(weights: dict[date, float], day: date) -> tuple[float | None, int]:
    window = [weights[day - timedelta(days=offset)] for offset in range(7) if day - timedelta(days=offset) in weights]
    if not window:
        return None, 0
    return round(sum(window) / len(window), 2), len(window)


def weekly_change(weights: dict[date, float], day: date) -> float | None:
    """Seven-day average today minus the one a week earlier (negative = loss).
    Needs at least three weigh-ins in each window to mean anything."""
    current, count = seven_day_average(weights, day)
    previous, previous_count = seven_day_average(weights, day - timedelta(days=7))
    if current is None or previous is None or count < 3 or previous_count < 3:
        return None
    return round(current - previous, 2)


def trend_status(average: float | None, target: tuple[float, float]) -> str:
    if average is None:
        return "unknown"
    low, high = target
    if average > high + 0.3:
        return "above"
    if average < low - 0.5:
        return "below"
    return "on_trend"


def division_status(day: date, average: float | None, *, performance_ok: bool | None = None) -> dict:
    """Lightweight (76.0 kg in the gi) is the provisional goal; middleweight
    (82.3 kg in the gi) is the safe fallback, decided on January 15."""
    lightweight = {"division": "lightweight", "limit_gi_kg": LIGHTWEIGHT_LIMIT_GI_KG}
    middleweight = {"division": "middleweight", "limit_gi_kg": MIDDLEWEIGHT_LIMIT_GI_KG}
    if day < DIVISION_DECISION_DATE:
        days = (DIVISION_DECISION_DATE - day).days
        return {
            **lightweight, "decided": False,
            "note": f"Lightweight track. Division decision on 15 Jan ({days} days). "
                    "Switch to middleweight early if the cut hurts strength, recovery, sleep, mood or BJJ.",
        }
    if average is None:
        return {**lightweight, "decided": False, "note": "Division decision is due — log morning weights for a seven-day average."}
    if average > MIDDLEWEIGHT_SWITCH_KG or performance_ok is False:
        reason = "performance is deteriorating" if performance_ok is False else f"seven-day average {average:.1f} kg is above {MIDDLEWEIGHT_SWITCH_KG:.1f}"
        return {**middleweight, "decided": True, "note": f"Middleweight: {reason}. Stop cutting; hold weight and train."}
    if average <= LIGHTWEIGHT_KEEP_KG:
        return {**lightweight, "decided": True, "note": f"Lightweight: seven-day average {average:.1f} kg and performance holding. Keep going."}
    return {
        **lightweight, "decided": False,
        "note": f"Seven-day average {average:.1f} kg is between {LIGHTWEIGHT_KEEP_KG:.1f} and {MIDDLEWEIGHT_SWITCH_KG:.1f}: "
                "judgment call. Middleweight unless BJJ and recovery feel good.",
    }


def nutrition_for(session_type: str | None, *, adjustment_kcal: int = 0) -> dict:
    training = (session_type or "") in TRAINING_DAY_TYPES
    kcal = (TRAINING_DAY_KCAL if training else REST_DAY_KCAL) + adjustment_kcal
    protein = sum(PROTEIN_G) / 2
    fat = sum(FAT_G) / 2
    carbs = max(0, round((kcal - protein * 4 - fat * 9) / 4))
    return {
        "kind": "training" if training else "rest",
        "kcal": kcal,
        "protein_g": list(PROTEIN_G),
        "fat_g": list(FAT_G),
        "carbs_g": carbs,
        "adjustment_kcal": adjustment_kcal,
        "carb_timing": "Most rice, noodles, oats, bread, potatoes and fruit before and after training."
        if training else "Lower-carb day; keep protein and vegetables high.",
    }


def intake_adjustment(
    day: date,
    weekly_changes: list[float | None],
    *,
    last_adjustment_on: date | None = None,
    performance_worse: bool = False,
) -> tuple[int, str]:
    """The plan's adjustment rules, evaluated at the Monday check-in.

    `weekly_changes` is newest first (kg/week, negative = loss). Returns
    (kcal/day change, reason). Calories stay put during the 14-day trial and
    for 14 days after any adjustment."""
    if day < TRIAL_END:
        return 0, "First 14 days are the calorie trial. Hold intake steady."
    if last_adjustment_on is not None and (day - last_adjustment_on).days < 14:
        return 0, "Intake changed less than 14 days ago. Hold it steady before judging again."
    latest = weekly_changes[0] if weekly_changes else None
    if latest is not None and -latest > FAST_LOSS_KG_PER_WEEK:
        return KCAL_STEP, f"Lost {-latest:.2f} kg last week (over {FAST_LOSS_KG_PER_WEEK} kg). Add {KCAL_STEP} kcal/day."
    if performance_worse:
        return KCAL_STEP, f"BJJ performance and energy are down. Add {KCAL_STEP} kcal/day."
    recent = [item for item in weekly_changes[:2] if item is not None]
    if len(recent) == 2 and all(-item < SLOW_LOSS_KG_PER_WEEK for item in recent):
        return -KCAL_STEP, (
            f"Under {SLOW_LOSS_KG_PER_WEEK} kg/week loss for two weeks in a row. "
            f"Cut {KCAL_STEP} kcal/day."
        )
    if latest is None:
        return 0, "Not enough morning weigh-ins for a weekly trend. Hold intake steady."
    return 0, f"Weekly change {latest:+.2f} kg is inside the plan. Hold intake steady."


def weight_status(
    day: date,
    weights: dict[date, float],
    *,
    session_type: str | None = None,
    adjustment_kcal: int = 0,
    performance_ok: bool | None = None,
) -> dict:
    average, count = seven_day_average(weights, day)
    target = target_for(day)
    division = division_status(day, average, performance_ok=performance_ok)
    checkpoint = next_checkpoint(day)
    status = trend_status(average, target)
    if division["division"] == "middleweight" and division["decided"]:
        status = "middleweight"
    return {
        "today_kg": weights.get(day),
        "seven_day_average_kg": average,
        "weigh_ins_7d": count,
        "weekly_change_kg": weekly_change(weights, day),
        "target_kg": {"low": target[0], "high": target[1]},
        "checkpoint": {"date": checkpoint[0].isoformat(), "low": checkpoint[1], "high": checkpoint[2]} if checkpoint else None,
        "status": status,
        "division": division,
        "nutrition": nutrition_for(session_type, adjustment_kcal=adjustment_kcal),
        "stop_rule": STOP_RULE,
    }
