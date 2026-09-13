from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.core.settings import settings
from app.domain.training.adjust import CalendarAdjuster, CalendarMutation, explain_adjustment
from app.domain.training.policy import weekly_targets
from app.domain.training.scheduler import phase_for_date


TRAVEL_MARKERS = ("flight", "travel", "airport", "shinkansen", "train to")
DINNER_MARKERS = ("dinner", "izakaya")


class EveningCoach:
    def __init__(self, *, timezone_name: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        self._timezone = ZoneInfo(timezone_name or settings.timezone)
        self._adjuster = CalendarAdjuster(timezone_name=self._timezone.key, api_key=api_key, model=model)

    def review(
        self,
        training,
        *,
        calendar=None,
        notion=None,
        notion_sync=None,
        now: datetime | None = None,
    ) -> dict:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        today = current.astimezone(self._timezone).date()
        if hasattr(training, "reconcile"):
            training.reconcile(current)
        overview = training.overview(current) if hasattr(training, "overview") else {}
        meetings = _meetings(calendar, today)
        mutations = propose_evening_mutations(today, overview, meetings)
        applied = [
            self._adjuster._apply(item, training=training, calendar=calendar, notion=notion, today=today, now=current)
            for item in mutations
        ]
        if mutations and hasattr(training, "overview"):
            overview = training.overview(current)
        if notion_sync is not None and mutations and hasattr(notion_sync, "sync_due"):
            try:
                notion_sync.sync_due()
            except Exception:
                pass
        readiness = evening_readiness(today, overview, meetings)
        decision = explain_adjustment(
            instruction="Evening calendar review for tournament readiness.",
            mutations=mutations,
            before=[],
            overview=overview if isinstance(overview, dict) else {},
            today=today,
            daily_url=_daily_url(today + timedelta(days=1)),
        )
        if not mutations:
            decision["how"] = ["No calendar rewrite tonight. The remaining week already follows the competition rules."]
            decision["why"] = readiness["why"]
            decision["banner"] = readiness["banner"]
            decision["notification"] = _evening_notification(decision["notification"].split("\n", 1)[0], readiness, overview)
        else:
            decision["why"] = list(decision.get("why") or []) + readiness["why"]
            decision["notification"] = self._adjuster._voice_notification(decision)
        decision["id"] = f"training:evening:{today.isoformat()}:{'-'.join(item.op for item in mutations) or 'hold'}"
        decision["readiness"] = readiness
        if hasattr(training, "store_last_adjustment"):
            training.store_last_adjustment(decision)
            if isinstance(overview, dict):
                overview["last_adjustment"] = decision
        return {
            "status": "ok",
            "decision": decision,
            "notification": decision["notification"],
            "applied": applied,
            "overview": overview,
        }


def propose_evening_mutations(
    today: date,
    overview: dict,
    meetings: list[dict],
) -> list[CalendarMutation]:
    week_start = _coach_week_start(today)
    sessions = _relevant_sessions(overview, today, week_start)
    by_date = {_session_date(item): item for item in sessions}
    candidate_days = {
        date.fromisoformat(item["date"])
        for item in (overview.get("bjj_candidates") or [])
        if item.get("date")
    }
    occupied = set(by_date) | candidate_days
    rest_days = {day for day, item in by_date.items() if item.get("planned_type") in {"rest", "recovery"}}
    open_days = [
        week_start + timedelta(days=offset)
        for offset in range(7)
        if week_start + timedelta(days=offset) > today
        and week_start + timedelta(days=offset) not in occupied
    ]
    mutations: list[CalendarMutation] = []

    tomorrow = today + timedelta(days=1)
    tomorrow_session = by_date.get(tomorrow)
    if (
        tomorrow_session
        and str(tomorrow_session.get("planned_type") or "").startswith("strength_")
        and _day_load(tomorrow, meetings) == "heavy"
    ):
        target = next((day for day in open_days if _day_load(day, meetings) != "heavy"), None)
        if target is not None:
            mutations.append(CalendarMutation(op="move_gym", to_date=target))
            occupied.add(target)
            open_days = [day for day in open_days if day != target]
        else:
            mutations.append(CalendarMutation(op="rest_today", date=tomorrow))
            rest_days.add(tomorrow)

    phase = phase_for_date(week_start)
    bjj_count = sum(str(item.get("planned_type") or "").startswith("bjj_") for item in sessions) + len(candidate_days)
    targets = weekly_targets(phase, bjj_count=bjj_count)
    strength = sum(str(item.get("planned_type") or "").startswith("strength_") for item in sessions)
    zone_2 = sum(item.get("planned_type") == "zone_2" for item in sessions)
    hard_bjj_days = {
        _session_date(item) for item in sessions if item.get("planned_type") == "bjj_hard"
    } | {
        date.fromisoformat(item["date"])
        for item in (overview.get("bjj_candidates") or [])
        if item.get("suggested_type") == "bjj_hard" and item.get("date")
    }

    if strength < targets["strength"]:
        chosen = _choose_open(
            open_days, meetings,
            reject=lambda day: any(0 <= (hard - day).days <= 1 for hard in hard_bjj_days),
        )
        if chosen is not None:
            kind = "strength_b" if any(item.get("planned_type") == "strength_a" for item in sessions) else "strength_a"
            mutations.append(CalendarMutation(op="place_session", date=chosen, workout_type=kind))
            open_days = [day for day in open_days if day != chosen]

    if zone_2 < targets["zone_2"]:
        chosen = _choose_open(open_days, meetings)
        if chosen is not None:
            mutations.append(CalendarMutation(op="place_session", date=chosen, workout_type="zone_2"))
            open_days = [day for day in open_days if day != chosen]

    if not rest_days and open_days:
        mutations.append(CalendarMutation(op="rest_today", date=open_days[-1]))

    return mutations


def evening_readiness(today: date, overview: dict, meetings: list[dict]) -> dict:
    week_start = _coach_week_start(today)
    sessions = _relevant_sessions(overview, today, week_start)
    by_date = {_session_date(item): item for item in sessions}
    candidates = overview.get("bjj_candidates") or []
    quality = overview.get("week_quality") or "acceptable"
    phase = phase_for_date(week_start)
    countdown = next((item for item in overview.get("countdowns") or [] if item.get("id") == "oct-2026"), None)
    days_out = countdown.get("days_remaining") if countdown else None
    why: list[str] = []
    open_days = []
    for offset in range(7):
        day = week_start + timedelta(days=offset)
        if day <= today:
            continue
        if day not in by_date and day.isoformat() not in {item.get("date") for item in candidates}:
            open_days.append(day)
    rest_days = [day for day, item in by_date.items() if item.get("planned_type") in {"rest", "recovery"}]
    if rest_days:
        why.append(f"{_day_label(rest_days[0])} rest stays. One full rest day protects BJJ quality.")
    else:
        why.append("The week still needs one complete rest day.")
    if open_days:
        why.append(
            f"{_day_label(open_days[0])} stays Open. Empty time is not extra gym — I only fill it if Strength or Zone 2 is still missing."
        )
    if candidates:
        why.append("BJJ days stay candidates until you confirm or they appear on Apple Calendar.")
    if days_out is not None:
        why.append(f"9th All Japan is in {days_out} days. This is a {phase.value.replace('_', ' ')} week.")
    banner = f"Evening check. Week looks {quality.replace('_', ' ')} for the tournament."
    return {
        "quality": quality,
        "phase": phase.value,
        "days_out": days_out,
        "open_days": [day.isoformat() for day in open_days],
        "rest_days": [day.isoformat() for day in rest_days],
        "why": why,
        "banner": banner,
        "meetings": len(meetings),
    }


def _relevant_sessions(overview: dict, today: date, week_start: date) -> list[dict]:
    items = []
    seen: set[str] = set()
    for item in list(overview.get("week") or []) + list(overview.get("upcoming") or []):
        session_id = str(item.get("id") or item.get("start_at") or "")
        if session_id in seen:
            continue
        day = _session_date(item)
        if day is None:
            continue
        if week_start <= day < week_start + timedelta(days=7) or (today.weekday() == 6 and day == today):
            seen.add(session_id)
            items.append(item)
    return items


def _coach_week_start(today: date) -> date:
    if today.weekday() == 6:
        return today + timedelta(days=1)
    return today - timedelta(days=today.weekday())


def _session_date(item: dict) -> date | None:
    raw = str(item.get("start_at") or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _meetings(calendar, today: date) -> list[dict]:
    if calendar is None or not hasattr(calendar, "events_for_range"):
        return []
    try:
        _, _, events = calendar.events_for_range(today, 8)
    except Exception:
        return []
    meetings = []
    for event in events:
        if getattr(event, "managed_session_id", None):
            continue
        meetings.append({
            "title": getattr(event, "title", "") or "",
            "start_at": getattr(event, "start_at", None),
            "end_at": getattr(event, "end_at", None),
            "is_all_day": bool(getattr(event, "is_all_day", False)),
        })
    return meetings


def _day_load(day: date, meetings: list[dict]) -> str:
    timezone = ZoneInfo(settings.timezone)
    day_start = datetime.combine(day, time.min, timezone)
    day_end = day_start + timedelta(days=1)
    hours = 0.0
    last_end: datetime | None = None
    titles: list[str] = []
    for meeting in meetings:
        start = meeting.get("start_at")
        end = meeting.get("end_at")
        if start is None or end is None:
            continue
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone)
        clipped_start = max(start.astimezone(timezone), day_start)
        clipped_end = min(end.astimezone(timezone), day_end)
        if clipped_end <= clipped_start:
            continue
        hours += (clipped_end - clipped_start).total_seconds() / 3600
        last_end = clipped_end if last_end is None or clipped_end > last_end else last_end
        titles.append(str(meeting.get("title") or "").lower())
    blob = " ".join(titles)
    if any(marker in blob for marker in TRAVEL_MARKERS + DINNER_MARKERS):
        return "heavy"
    if hours >= 6 or (last_end is not None and last_end.astimezone(timezone).time() >= time(18, 0) and hours >= 2):
        return "heavy"
    if hours >= 3:
        return "moderate"
    return "light"


def _choose_open(open_days: list[date], meetings: list[dict], reject=None) -> date | None:
    for day in open_days:
        if _day_load(day, meetings) == "heavy":
            continue
        if reject is not None and reject(day):
            continue
        return day
    return None


def _day_label(day: date) -> str:
    return f"{day.strftime('%a')} {day.day} {day.strftime('%b')}"


def _daily_url(day: date) -> str:
    base = (settings.chili_public_url or settings.daily_briefing_base_url).rstrip("/")
    return f"{base}/daily/{day.isoformat()}"


def _evening_notification(url: str, readiness: dict, overview: dict) -> str:
    prescription = overview.get("tomorrow_prescription") if isinstance(overview, dict) else {}
    tomorrow = str((prescription or {}).get("session") or "rest").replace("_", " ")
    if (prescription or {}).get("time"):
        tomorrow = f"{tomorrow} at {prescription['time']}"
    lines = [url, "", readiness["banner"], "", "How", "• No calendar rewrite tonight.", "", "Why"]
    lines.extend(f"• {item}" for item in readiness["why"])
    lines.extend(["", f"Tomorrow: {tomorrow}."])
    if (prescription or {}).get("why"):
        lines.append(str(prescription["why"]))
    return "\n".join(lines)
