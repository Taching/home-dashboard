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


def _tomorrow_line(prescription: dict[str, Any]) -> str:
    session = str(prescription.get("session") or "rest").replace("_", " ")
    when = prescription.get("time")
    if when:
        return f"{session} at {when}"
    return session
