from __future__ import annotations

from typing import Any


KIND_ALIASES = {
    "zone2": "zone_2",
    "zone_2": "zone_2",
}

_STATUS_LABELS = (
    ("bjj", "BJJ"),
    ("strength", "Strength"),
    ("zone_2", "Zone 2"),
    ("grip", "Grip"),
    ("rest", "Rest"),
)


def normalize_kind(kind: str | None) -> str:
    return KIND_ALIASES.get((kind or "").strip().lower(), (kind or "").strip().lower())


def kinds_match(planned: str | None, logged: str | None) -> bool:
    planned_kind = normalize_kind(planned)
    logged_kind = normalize_kind(logged)
    if not logged_kind:
        return True
    if planned_kind == "competition":
        return logged_kind in {"competition", "bjj", "bjj_hard", "bjj_normal"}
    if logged_kind == "bjj":
        return planned_kind.startswith("bjj_") or planned_kind == "competition"
    if logged_kind == "rest":
        return planned_kind in {"rest", "recovery"}
    return planned_kind == logged_kind


def exercise_done(session_name: str, done_by_name: dict[str, bool]) -> bool | None:
    if session_name in done_by_name:
        return done_by_name[session_name]
    session_key = session_name.casefold()
    for name, done in done_by_name.items():
        key = name.casefold()
        if key == session_key or key in session_key or session_key in key:
            return done
    return None


def week_counters_text(status: dict | None) -> str:
    if not isinstance(status, dict) or not status:
        return "Weekly status unavailable."
    parts = []
    for key, label in _STATUS_LABELS:
        item = status.get(key)
        if not isinstance(item, dict):
            continue
        if not item.get("target") and not item.get("completed"):
            continue
        parts.append(f"{label} {item.get('completed', 0)}/{item.get('target', 0)}")
    return " · ".join(parts) if parts else "Weekly status unavailable."


def workout_review_prompt(
    *,
    session: dict | None,
    kind: str | None,
    note: str | None,
    exercises: list[dict] | None,
    overview: dict | None,
) -> str:
    title = (session or {}).get("title") or (kind or "session").replace("_", " ").title()
    status = (session or {}).get("status") or "logged"
    done = [item["name"] for item in (exercises or []) if item.get("done") and item.get("name")]
    skipped = [item["name"] for item in (exercises or []) if not item.get("done") and item.get("name")]
    prescription = (overview or {}).get("tomorrow_prescription") or {}
    counters = week_counters_text(
        prescription.get("weekly_status") or (overview or {}).get("compliance")
    )
    tomorrow = _tomorrow_line(prescription)
    note_text = (note or "").strip() or "No extra note."
    return (
        "Takatoshi just logged a workout from the Chili workout page.\n"
        f"Session: {title} — {status}\n"
        f"Done: {', '.join(done) or 'not listed'}\n"
        f"Skipped: {', '.join(skipped) or 'none'}\n"
        f"His note: {note_text}\n"
        f"This week after the log: {counters}\n"
        f"Tomorrow: {tomorrow}\n"
        f"Why tomorrow: {prescription.get('why') or 'Protect recovery.'}\n\n"
        "Reply in 3–6 short lines in Chili's voice from SOUL.md / IDENTITY.md:\n"
        "1. What you think of today's session, using his note.\n"
        "2. What is already done this week, in plain counters.\n"
        "3. What to do next — rest tonight or prepare for tomorrow. "
        "Do not invent extra training.\n"
        "Do not paste the full program. Do not ask sleep or readiness."
    )


def local_workout_review(
    *,
    session: dict | None,
    kind: str | None,
    note: str | None,
    overview: dict | None,
) -> str:
    title = (session or {}).get("title") or (kind or "session").replace("_", " ").title()
    status = (session or {}).get("status") or "logged"
    prescription = (overview or {}).get("tomorrow_prescription") or {}
    counters = week_counters_text(
        prescription.get("weekly_status") or (overview or {}).get("compliance")
    )
    tomorrow = _tomorrow_line(prescription)
    note_text = (note or "").strip()
    first_note = next((line.strip() for line in note_text.splitlines() if line.strip()), "")
    if "bjj" in tomorrow.lower():
        next_line = f"Tomorrow is {tomorrow}. Rest tonight and show up ready. Do not add extra gym."
    elif tomorrow.lower().startswith("rest") or tomorrow.lower().startswith("recovery"):
        next_line = f"Tomorrow is {tomorrow}. Leave it empty."
    else:
        next_line = f"Tomorrow is {tomorrow}."
    lines = [f"{title} is in ({status})."]
    if first_note:
        lines.append(first_note)
    lines.append(f"This week: {counters}.")
    lines.append(next_line)
    why = str(prescription.get("why") or "").strip()
    if why:
        lines.append(why)
    return "\n".join(lines)


def close_day_prompt(*, briefing: dict) -> str:
    answers = briefing.get("answers") or {}
    workout = briefing.get("workout") or {}
    weekly = briefing.get("weekly") or {}
    sober = briefing.get("sobriety") or {}
    tomorrow = (briefing.get("tomorrow") or {}).get("prescription") or {}
    workout_line = "No gym form today."
    if answers.get("items"):
        workout_item = next((item for item in answers["items"] if item.get("id") == "workout"), None)
        if workout_item and workout_item.get("required"):
            title = workout.get("title") or "session"
            status = workout.get("status") or "logged"
            note = (workout.get("notes") or "").strip() or "No extra note."
            workout_line = f"{title} — {status}. Note: {note}"
    weekly_line = "Not a Monday check-in."
    if weekly:
        weight = weekly.get("weight_kg")
        delta = weekly.get("delta_kg")
        weight_text = f"seven-day average {weight:.1f} kg" if weight is not None else "no morning weigh-ins"
        if delta is not None:
            weight_text += f", {delta:+.1f} kg vs last week"
        note = (weekly.get("review_note") or "").strip() or "No extra note."
        weekly_line = f"{weight_text}. Note: {note}"
    cut = briefing.get("cut") or {}
    food = cut.get("nutrition") or {}
    weight_today = cut.get("today_kg")
    cut_line = "No weigh-in today." if weight_today is None else f"Weighed {weight_today:.1f} kg this morning."
    if cut.get("seven_day_average_kg") is not None:
        cut_line += f" Seven-day average {cut['seven_day_average_kg']:.1f} kg, trend target {cut['target_kg']['low']:.1f}."
    if food.get("kcal"):
        cut_line += f" Food target today {food['kcal']} kcal, protein {food['protein_g'][0]}–{food['protein_g'][1]} g."
    sober_line = f"{sober.get('answered') or 'unanswered'}"
    if sober.get("note"):
        sober_line += f". Note: {sober['note']}"
    tomorrow_line = _tomorrow_line(tomorrow) if tomorrow else "unspecified"
    return (
        "Takatoshi just finished every answer on today's Chili daily page.\n"
        f"Date: {briefing.get('date')}\n"
        f"Workout: {workout_line}\n"
        f"Sober: {sober_line}\n"
        f"Weekly check-in: {weekly_line}\n"
        f"Weight: {cut_line}\n"
        f"Tomorrow: {tomorrow_line}\n\n"
        "Reply in 3–5 short lines in Chili's voice from SOUL.md / IDENTITY.md:\n"
        "1. The day is closed. Say good job if he stayed honest.\n"
        "2. Confirm what he logged, including sober.\n"
        "3. What matters tomorrow. Do not invent extra training.\n"
        "Do not ask more questions."
    )


def local_close_day_review(*, briefing: dict) -> str:
    sober = briefing.get("sobriety") or {}
    tomorrow = (briefing.get("tomorrow") or {}).get("prescription") or {}
    tomorrow_line = _tomorrow_line(tomorrow) if tomorrow else "protect recovery"
    sober_answer = sober.get("answered")
    if sober_answer == "yes":
        sober_line = f"Sober is in. {sober.get('days', 0)} day streak."
    elif sober_answer == "no":
        sober_line = "Sober is logged as no. Reset clean tonight."
    else:
        sober_line = "Sober is in."
    if "bjj" in tomorrow_line.lower():
        next_line = f"Tomorrow is {tomorrow_line}. Rest tonight and show up ready."
    elif tomorrow_line.lower().startswith("rest") or tomorrow_line.lower().startswith("recovery"):
        next_line = f"Tomorrow is {tomorrow_line}. Leave it empty."
    else:
        next_line = f"Tomorrow is {tomorrow_line}."
    opening = "Day is closed." if sober_answer == "no" else "Day is closed. Good job."
    return "\n".join([opening, sober_line, next_line])


def weekly_check_in_line(check_in) -> str:
    counts = getattr(check_in, "counts", {}) or {}
    bits = [
        f"Completed BJJ {counts.get('bjj', 0)}, strength {counts.get('strength', 0)}, cardio {counts.get('cardio', 0)}",
    ]
    if getattr(check_in, "sleep_average", None) is not None:
        bits.append(f"sleep average {check_in.sleep_average:.1f} h")
    ratings = [
        f"{label} {value}/5" for label, value in (
            ("energy", getattr(check_in, "energy", None)),
            ("hunger", getattr(check_in, "hunger", None)),
            ("BJJ performance", getattr(check_in, "bjj_performance", None)),
        ) if value is not None
    ]
    if ratings:
        bits.append(", ".join(ratings))
    if getattr(check_in, "pain_note", None):
        bits.append(f"pain/injury: {check_in.pain_note}")
    if getattr(check_in, "kcal_reason", None):
        bits.append(f"intake rule: {check_in.kcal_reason}")
    watch = getattr(check_in, "watch", None) or {}
    watch_bits = [
        f"{label} {watch[key]}" for key, label in (
            ("resting_hr", "resting HR"), ("hrv", "HRV"), ("sleep_score", "sleep score"),
            ("body_battery_high", "Body Battery peak"), ("steps", "steps/day"),
        ) if watch.get(key) is not None
    ]
    if watch_bits:
        bits.append("Watch weekly averages: " + ", ".join(watch_bits))
    division = getattr(check_in, "division", None) or {}
    if division.get("note"):
        bits.append(division["note"])
    return ". ".join(bit.rstrip(".") for bit in bits) + "."


def _counts(week_review: dict) -> str:
    planned = week_review.get("planned") or {}
    completed = week_review.get("completed") or {}
    return " · ".join(
        f"{label} {completed.get(key, 0)}/{planned.get(key, 0)}"
        for key, label in (("bjj", "BJJ"), ("strength", "Strength"), ("zone_2", "Easy cardio"))
    )


def weekly_training_review_prompt(
    *,
    week_review: dict,
    weight_line: str,
    sessions_summary: str,
    preferences: str = "",
    check_in_line: str = "",
) -> str:
    counts = _counts(week_review)
    avg_rpe = week_review.get("average_rpe")
    rpe_line = (
        f"Average RPE {avg_rpe}, trend {(week_review.get('trends') or {}).get('rpe', 'hold')}."
        if avg_rpe is not None else "No RPE logged this week."
    )
    recovery_line = (week_review.get("recovery") or {}).get("notes") or "No recovery flags."
    what_changes = week_review.get("what_changes") or "No adaptation notes."
    prefs_block = f"\n{preferences}" if preferences else ""
    return (
        "Takatoshi just submitted his Monday check-in on the Chili dashboard. He is cutting from 84 kg "
        "toward lightweight (76.0 kg in the gi) for the All Japan Master on 5–7 March 2027, with middleweight "
        "(82.3 kg) as the fallback decided on 15 January. Progress is judged only by the seven-day average.\n"
        f"{weight_line}\n"
        f"{check_in_line}\n"
        f"Planned vs completed: {counts}\n"
        f"{rpe_line}\n"
        f"Recovery: {recovery_line}\n"
        f"Scheduler's own note: {what_changes}\n"
        f"{sessions_summary}"
        f"{prefs_block}\n\n"
        "Reply in 4-7 short lines in Chili's voice from SOUL.md / IDENTITY.md:\n"
        "1. Weight trend vs the target in plain words; no drama about one week.\n"
        "2. What actually got done this week vs the plan, plainly.\n"
        "3. One concrete thing to change next week — be specific (a session type, a day, an intensity, "
        "or a food habit from the plan), not generic encouragement.\n"
        "4. One thing that is working and should stay the same.\n"
        "If pain, dizziness, exhaustion or bingeing is mentioned, say to pause the cut and see a clinician. "
        "Do not invent numbers that were not given. Do not change the intake rule's number. "
        "Do not ask for more metrics. Do not paste the full program."
    )


def local_weekly_training_review(*, week_review: dict, weight_line: str, check_in_line: str = "") -> str:
    what_changes = week_review.get("what_changes") or "Hold the plan steady next week."
    lines = [weight_line, f"This week: {_counts(week_review)}."]
    if check_in_line:
        lines.append(check_in_line)
    lines.append(what_changes)
    return "\n".join(lines)


def _tomorrow_line(prescription: dict[str, Any]) -> str:
    session = str(prescription.get("session") or "rest").replace("_", " ")
    when = prescription.get("time")
    if when:
        return f"{session} at {when}"
    return session
