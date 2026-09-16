from __future__ import annotations

from datetime import date

from app.domain.training.types import WeekAdaptation, WorkoutType

MAX_LOAD_DELTA = 0.05
MAX_VOLUME_UP = 1.0
MAX_VOLUME_DOWN = 2.0
MAX_ZONE2_MINUTES = 15
MAX_GRIP_DELTA = 1
MAX_BJJ_ROUNDS = 1


def clamp_adaptation(raw: WeekAdaptation) -> WeekAdaptation:
    return WeekAdaptation(
        strength_load_delta=max(-MAX_LOAD_DELTA, min(MAX_LOAD_DELTA, raw.strength_load_delta)),
        strength_volume_delta=max(-MAX_VOLUME_DOWN, min(MAX_VOLUME_UP, raw.strength_volume_delta)),
        zone2_minutes_delta=max(-MAX_ZONE2_MINUTES, min(MAX_ZONE2_MINUTES, raw.zone2_minutes_delta)),
        grip_sets_delta=max(-MAX_GRIP_DELTA, min(MAX_GRIP_DELTA, raw.grip_sets_delta)),
        bjj_rounds_delta=max(-MAX_BJJ_ROUNDS, min(MAX_BJJ_ROUNDS, raw.bjj_rounds_delta)),
        extra_rest_before_hard_bjj=raw.extra_rest_before_hard_bjj,
        reduce_preceding_strength=raw.reduce_preceding_strength,
        notes=raw.notes,
    )


def analyze_week(sessions: list[dict], *, next_week_start: date | None = None) -> WeekAdaptation:
    del next_week_start
    strength = [item for item in sessions if str(item.get("planned_type") or "").startswith("strength_")]
    bjj = [item for item in sessions if str(item.get("planned_type") or "").startswith("bjj_")]
    grip_fatigue = [item for item in sessions if (item.get("result") or {}).get("grip_fatigue") in {"HIGH", "high"}]
    rpes = [float(item["session_rpe"]) for item in sessions if item.get("session_rpe")]
    avg_rpe = sum(rpes) / len(rpes) if rpes else None
    completed = [item for item in sessions if item.get("status") in {"completed", "partial"}]
    incomplete = [item for item in strength if item.get("status") in {"partial", "skipped"}]
    easy_strength = [item for item in strength if item.get("status") == "completed" and (item.get("session_rpe") or 10) <= 6]
    hard_strength = [item for item in strength if (item.get("session_rpe") or 0) >= 9]
    load = 0.0
    volume = 0.0
    zone2 = 0
    grip = 0
    notes: list[str] = []
    extra_rest = False
    reduce_strength = False
    if easy_strength and not hard_strength:
        load = 0.025
        volume = 0.0
        notes.append("Strength felt easy. Small load increase next week.")
    if hard_strength or incomplete:
        load = -0.025
        volume = -1
        notes.append("Strength was too hard or incomplete. Reduce volume/intensity.")
    if len(bjj) >= 3:
        zone2 = -10
        grip = -1
        notes.append("BJJ volume is high. Accessory work comes down.")
    if grip_fatigue:
        grip = -1
        notes.append("Grip fatigue is showing up on the mat. Fewer grip sets.")
    hard_bjj = [item for item in bjj if item.get("planned_type") == "bjj_hard"]
    if hard_bjj and any((item.get("result") or {}).get("technical_performance") in {"poor", "down"} for item in hard_bjj):
        extra_rest = True
        reduce_strength = True
        notes.append("Hard BJJ quality dropped. Protect it with more separation and lighter strength.")
    if avg_rpe is not None and avg_rpe <= 6 and not incomplete and len(completed) >= 3:
        load = max(load, 0.025)
        notes.append("Recovery has been good. Useful load can rise slightly.")
    if not notes:
        notes.append("Hold current prescriptions. Weekly counters stay informational.")
    return clamp_adaptation(WeekAdaptation(
        strength_load_delta=load,
        strength_volume_delta=volume,
        zone2_minutes_delta=zone2,
        grip_sets_delta=grip,
        extra_rest_before_hard_bjj=extra_rest,
        reduce_preceding_strength=reduce_strength,
        notes=" ".join(notes),
    ))


def adaptation_payload(item: WeekAdaptation) -> dict:
    return {
        "strength_load_delta": item.strength_load_delta,
        "strength_volume_delta": item.strength_volume_delta,
        "zone2_minutes_delta": item.zone2_minutes_delta,
        "grip_sets_delta": item.grip_sets_delta,
        "bjj_rounds_delta": item.bjj_rounds_delta,
        "extra_rest_before_hard_bjj": item.extra_rest_before_hard_bjj,
        "reduce_preceding_strength": item.reduce_preceding_strength,
    }
