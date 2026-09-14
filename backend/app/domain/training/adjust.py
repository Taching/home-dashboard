from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import json
import logging
import re
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from app.core.settings import settings
from app.domain.daily_plan import DailyPlanService

logger = logging.getLogger(__name__)

_OPS = (
    "gym_today",
    "rest_today",
    "move_gym",
    "confirm_bjj",
    "decline_bjj",
    "add_bjj",
    "replace_session",
    "move_session",
    "skip_session",
    "fatigue",
    "replan",
    "complete_task",
    "move_meeting",
    "place_session",
)

_WEEKDAYS = {
    "monday": 0, "mon": 0,
    "tuesday": 1, "tue": 1, "tues": 1,
    "wednesday": 2, "wed": 2,
    "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
    "friday": 4, "fri": 4,
    "saturday": 5, "sat": 5,
    "sunday": 6, "sun": 6,
}

_NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
_NULLABLE_BOOL = {"anyOf": [{"type": "boolean"}, {"type": "null"}]}
_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "mutations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "op": {"type": "string", "enum": list(_OPS)},
                    "date": _NULLABLE_STRING,
                    "to_date": _NULLABLE_STRING,
                    "workout_type": _NULLABLE_STRING,
                    "session_id": _NULLABLE_STRING,
                    "start_at": _NULLABLE_STRING,
                    "end_at": _NULLABLE_STRING,
                    "fatigue_state": _NULLABLE_STRING,
                    "task_id": _NULLABLE_STRING,
                    "task_title": _NULLABLE_STRING,
                    "event_id": _NULLABLE_STRING,
                    "hard": _NULLABLE_BOOL,
                },
                "required": [
                    "op", "date", "to_date", "workout_type", "session_id", "start_at",
                    "end_at", "fatigue_state", "task_id", "task_title", "event_id", "hard",
                ],
            },
        },
    },
    "required": ["summary", "mutations"],
}

_SYSTEM = """You adjust Toshi's Chili training calendar. Return only structured mutations.

Priority: Confirmed BJJ → required recovery → Hard/competition BJJ → Strength
maintenance → Zone 2 → Grip. BJJ beats Strength A and Strength B.
Toshi's explicit override always wins. Recalculate the remaining week. Do not
invent makeup work or slide a miss to the next free day.
After missed BJJ, search the next viable BJJ window before assigning strength,
Zone 2, or grip. A lower-priority gym day must not block replacement BJJ.
Completed sessions never move. Tentative BJJ reserves the day and must be
surfaced for confirmation; do not silently create a class.
Do not place Strength A on or immediately before Hard BJJ. Avoid three
consecutive hard days. Grip is the first target sacrificed. Weekly counters
are status, not quotas. Sunday gym counts for the coming week.

Allowed ops: gym_today, rest_today, move_gym, confirm_bjj, decline_bjj, add_bjj,
replace_session, move_session, skip_session, fatigue, replan, complete_task, move_meeting.
Dates are YYYY-MM-DD in Asia/Tokyo. Use session_id or event_id from context when touching
a specific item. If the message is not a calendar or plan change, return no mutations."""


@dataclass(frozen=True)
class CalendarMutation:
    op: str
    date: date | None = None
    to_date: date | None = None
    workout_type: str | None = None
    session_id: str | None = None
    start_at: datetime | None = None
    end_at: datetime | None = None
    fatigue_state: str | None = None
    task_id: str | None = None
    task_title: str | None = None
    event_id: str | None = None
    hard: bool | None = None


@dataclass(frozen=True)
class CalendarAnalysis:
    summary: str
    source: Literal["fast_path", "gpt"]
    mutations: tuple[CalendarMutation, ...] = field(default_factory=tuple)


class CalendarAdjuster:
    def __init__(self, *, timezone_name: str | None = None, api_key: str | None = None, model: str | None = None) -> None:
        self._timezone = ZoneInfo(timezone_name or settings.timezone)
        self._api_key = settings.openai_api_key if api_key is None else api_key
        self._model = model or settings.voice_command_model
        self._plan = DailyPlanService(self._timezone.key)

    def adjust(
        self,
        instruction: str,
        *,
        training,
        calendar=None,
        notion=None,
        notion_sync=None,
        now: datetime | None = None,
    ) -> dict:
        text = " ".join((instruction or "").split())
        if not text:
            raise ValueError("instruction is required.")
        current = self._as_utc(now or datetime.now(UTC))
        today = current.astimezone(self._timezone).date()
        context = self._context(training, calendar, notion, today, current)
        analysis = self.interpret(text, context, today)
        if not analysis.mutations:
            raise ValueError("Could not turn that into a calendar change.")
        applied = [self._apply(item, training=training, calendar=calendar, notion=notion, today=today, now=current) for item in analysis.mutations]
        notion_synced = 0
        if notion_sync is not None and hasattr(notion_sync, "sync_due"):
            try:
                notion_synced = int(notion_sync.sync_due() or 0)
            except Exception:
                logger.exception("Notion training sync failed after calendar adjust")
        overview = training.overview(current) if hasattr(training, "overview") else {}
        calendar_events = training.calendar_plan(current) if hasattr(training, "calendar_plan") else []
        decision = explain_adjustment(
            instruction=text,
            mutations=analysis.mutations,
            before=context.get("sessions") or [],
            overview=overview if isinstance(overview, dict) else {},
            today=today,
            daily_url=_daily_url(today),
        )
        decision["notification"] = self._voice_notification(decision)
        decision["source"] = analysis.source
        if hasattr(training, "store_last_adjustment"):
            training.store_last_adjustment(decision)
            if isinstance(overview, dict):
                overview["last_adjustment"] = decision
        return {
            "status": "ok",
            "analysis": {
                "summary": analysis.summary,
                "source": analysis.source,
                "mutations": [self._public_mutation(item) for item in analysis.mutations],
            },
            "decision": decision,
            "notification": decision["notification"],
            "applied": applied,
            "notion_synced": notion_synced,
            "calendar_events": calendar_events,
            "overview": overview,
        }

    def interpret(self, instruction: str, context: dict, today: date) -> CalendarAnalysis:
        fast = match_calendar_adjust_fast_path(instruction, today)
        if fast is not None:
            logger.info("← calendar adjust fast-path ops=%s", [item.op for item in fast.mutations])
            return fast
        if not self._api_key:
            raise ValueError("Calendar adjust needs a clearer instruction, or OpenAI is not configured.")
        logger.info("→ openai POST /v1/responses model=%s instruction=%s", self._model, instruction[:160])
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            json={
                "model": self._model,
                "store": False,
                "input": [
                    {"role": "system", "content": _SYSTEM},
                    {"role": "user", "content": json.dumps({"today": today.isoformat(), "instruction": instruction, "context": context}, default=str)},
                ],
                "text": {"format": {"type": "json_schema", "name": "calendar_adjust", "strict": True, "schema": _SCHEMA}},
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        raw = payload.get("output_text") or _output_text(payload)
        parsed = json.loads(raw)
        mutations = tuple(item for item in (_mutation_from_payload(item, today) for item in parsed.get("mutations") or []) if item is not None)
        summary = str(parsed.get("summary") or "Adjusted the calendar from the instruction.")
        logger.info("← openai calendar adjust ops=%s", [item.op for item in mutations])
        return CalendarAnalysis(summary, "gpt", mutations)

    def _apply(self, mutation: CalendarMutation, *, training, calendar, notion, today: date, now: datetime) -> dict:
        op = mutation.op
        day = mutation.date or today
        if op == "gym_today":
            if mutation.workout_type not in {"strength_a", "strength_b"}:
                raise ValueError("gym_today requires strength_a or strength_b.")
            return {"op": op, "result": _invoke(training.schedule_gym, day, mutation.workout_type, now=now)}
        if op == "rest_today":
            return {"op": op, "result": self._plan.rest_today(training, day)}
        if op == "move_gym":
            target = mutation.to_date or mutation.date
            if target is None:
                raise ValueError("move_gym requires to_date.")
            return {"op": op, "result": _invoke(self._plan.move_gym, training, target, now=now)}
        if op == "confirm_bjj":
            return {"op": op, "result": _invoke(training.confirm_bjj, day, hard=mutation.hard, now=now)}
        if op == "decline_bjj":
            return {"op": op, "result": _invoke(training.decline_bjj, day, now=now)}
        if op == "add_bjj":
            if mutation.start_at is None:
                raise ValueError("add_bjj requires start_at.")
            return {"op": op, "result": _invoke(training.add_bjj, mutation.start_at, hard=bool(mutation.hard), now=now)}
        if op == "replace_session":
            session_id = mutation.session_id or self._session_id(training, day)
            if not session_id or not mutation.workout_type:
                raise ValueError("replace_session requires a session and workout_type.")
            return {"op": op, "result": _invoke(training.replace_session, session_id, mutation.workout_type, now=now)}
        if op == "move_session":
            session_id = mutation.session_id or self._session_id(training, day)
            if not session_id or mutation.start_at is None:
                raise ValueError("move_session requires a session and start_at.")
            return {"op": op, "result": _invoke(training.update_session, session_id, start_at=mutation.start_at, now=now)}
        if op == "skip_session":
            session_id = mutation.session_id or self._session_id(training, day)
            if not session_id:
                raise ValueError("skip_session requires a session.")
            return {"op": op, "result": _invoke(training.update_session, session_id, status="skipped", now=now)}
        if op == "fatigue":
            if not mutation.fatigue_state:
                raise ValueError("fatigue requires fatigue_state.")
            return {"op": op, "result": _invoke(training.record_fatigue, day, mutation.fatigue_state, now=now)}
        if op == "replan":
            _invoke(training.reconcile, now=now)
            return {"op": op, "result": {"status": "replanned"}}
        if op == "complete_task":
            return {"op": op, "result": self._plan.complete_task(notion, task_id=mutation.task_id, title=mutation.task_title)}
        if op == "move_meeting":
            if not mutation.event_id or mutation.start_at is None:
                raise ValueError("move_meeting requires event_id and start_at.")
            return {"op": op, "result": self._plan.move_meeting(calendar, training, mutation.event_id, mutation.start_at, mutation.end_at)}
        if op == "place_session":
            if not mutation.workout_type:
                raise ValueError("place_session requires workout_type.")
            return {"op": op, "result": _invoke(training.place_session, day, mutation.workout_type, now=now)}
        raise ValueError(f"Unsupported calendar mutation: {op}")

    def _context(self, training, calendar, notion, today: date, now: datetime) -> dict:
        overview = training.overview(now) if hasattr(training, "overview") else {}
        seen: set[str] = set()
        sessions = []
        for item in list(overview.get("week") or []) + list(overview.get("upcoming") or []):
            session_id = str(item.get("id") or "")
            if not session_id or session_id in seen:
                continue
            seen.add(session_id)
            sessions.append({
                "id": session_id,
                "date": str(item.get("start_at") or "")[:10],
                "type": item.get("planned_type"),
                "status": item.get("status"),
                "title": item.get("title"),
                "start_at": item.get("start_at"),
            })
        meetings = []
        if calendar is not None and hasattr(calendar, "events_for_range"):
            try:
                _, _, events = calendar.events_for_range(today, 7)
            except Exception:
                events = []
            for event in events[:24]:
                if getattr(event, "managed_session_id", None):
                    continue
                meetings.append({
                    "id": getattr(event, "external_id", None),
                    "title": getattr(event, "title", ""),
                    "start_at": getattr(event, "start_at", None).isoformat() if getattr(event, "start_at", None) else None,
                })
        tasks = []
        if notion is not None and hasattr(notion, "today"):
            try:
                _, _, rows = notion.today()
            except Exception:
                rows = []
            for task in rows[:15]:
                tasks.append({"id": getattr(task, "id", None), "title": getattr(task, "title", "")})
        return {
            "today": today.isoformat(),
            "weekday": today.strftime("%A"),
            "phase": overview.get("phase"),
            "week_quality": overview.get("week_quality"),
            "sessions": sessions,
            "bjj_candidates": overview.get("bjj_candidates") or [],
            "tomorrow_prescription": overview.get("tomorrow_prescription"),
            "meetings": meetings,
            "tasks": tasks,
        }

    @staticmethod
    def _session_id(training, day: date) -> str | None:
        if not hasattr(training, "for_date"):
            return None
        row = training.for_date(day)
        if isinstance(row, dict):
            return row.get("id")
        return None

    @staticmethod
    def _public_mutation(item: CalendarMutation) -> dict:
        payload = asdict(item)
        payload["date"] = item.date.isoformat() if item.date else None
        payload["to_date"] = item.to_date.isoformat() if item.to_date else None
        payload["start_at"] = item.start_at.isoformat() if item.start_at else None
        payload["end_at"] = item.end_at.isoformat() if item.end_at else None
        return payload

    def _voice_notification(self, decision: dict) -> str:
        drafted = str(decision.get("notification") or "")
        personality = load_chili_personality()
        if not self._api_key or not personality:
            return drafted
        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json={
                    "model": self._model,
                    "store": False,
                    "input": [
                        {
                            "role": "system",
                            "content": (
                                "Rewrite the plan-change notification in Chili's voice using SOUL.md and IDENTITY.md. "
                                "Keep the daily URL on the first line. Keep How and Why. Do not invent extra workouts. "
                                "Do not sound like a corporate coach. Do not add baby talk unless the soul asks for it."
                            ),
                        },
                        {"role": "user", "content": json.dumps({"soul": personality, "draft": drafted, "decision": {
                            "instruction": decision.get("instruction"),
                            "how": decision.get("how"),
                            "why": decision.get("why"),
                            "banner": decision.get("banner"),
                        }}, default=str)},
                    ],
                    "text": {"format": {"type": "json_schema", "name": "chili_notify", "strict": True, "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {"message": {"type": "string"}},
                        "required": ["message"],
                    }}},
                },
                timeout=20,
            )
            response.raise_for_status()
            payload = response.json()
            raw = payload.get("output_text") or _output_text(payload)
            message = str(json.loads(raw).get("message") or "").strip()
            if message:
                return message
        except Exception:
            logger.exception("Chili voice rewrite failed; using the factual draft")
        return drafted

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=self._timezone).astimezone(UTC)
        return value.astimezone(UTC)


def match_calendar_adjust_fast_path(instruction: str, today: date) -> CalendarAnalysis | None:
    text = " ".join(instruction.lower().split())
    if not text:
        return None
    mutations: list[CalendarMutation] = []
    strength = _strength_variant(text)
    if strength:
        mutations.append(CalendarMutation(
            op="gym_today",
            date=_gym_day(text, today),
            workout_type=strength,
        ))
    if _cant_make_tomorrow(text):
        mutations.append(CalendarMutation(op="decline_bjj", date=today + timedelta(days=1)))
    elif re.search(r"\b(?:confirm|i(?:'ll| will) (?:go|make|do))\b.*\b(?:bjj|class)\b", text) or re.search(r"\b(?:bjj|class)\b.*\bconfirm\b", text):
        mutations.append(CalendarMutation(op="confirm_bjj", date=_mentioned_day(text, today) or today))
    if not strength and re.search(r"\brest(?:\s+day)?\s+today\b|\btoday\s+(?:is\s+)?(?:a\s+)?rest\b|\bmake\s+today\s+rest\b", text):
        mutations.append(CalendarMutation(op="rest_today", date=today))
    move = re.search(r"move\s+(?:the\s+)?gym\s+to\s+([a-z]+|\d{4}-\d{2}-\d{2})", text)
    if move:
        target = _parse_day_token(move.group(1), today)
        if target is not None:
            mutations.append(CalendarMutation(op="move_gym", to_date=target))
    if not strength and not mutations:
        fatigue = _fatigue_state(text)
        if fatigue:
            mutations.append(CalendarMutation(op="fatigue", date=today, fatigue_state=fatigue))
    if not mutations:
        return None
    labels = ", ".join(item.op.replace("_", " ") for item in mutations)
    return CalendarAnalysis(f"Apply {labels} from the message.", "fast_path", tuple(mutations))


def _strength_variant(text: str) -> str | None:
    has_a = bool(re.search(r"strength[\s_-]*a\b|\bgym\s*\(?\s*a\b", text))
    has_b = bool(re.search(r"strength[\s_-]*b\b|\bgym\s*\(?\s*b\b", text))
    if has_a and has_b:
        return None
    if has_a:
        return "strength_a"
    if has_b:
        return "strength_b"
    return None


def _gym_day(text: str, today: date) -> date:
    if re.search(r"\b(?:today|tonight|now|this afternoon|this evening)\b", text):
        return today
    return _mentioned_day(text, today) or today


def _cant_make_tomorrow(text: str) -> bool:
    return bool(re.search(
        r"(can'?t|cannot|won'?t)\s+(make|do|go)(?:\s+\w+){0,3}\s+tomorrow"
        r"|(?:skip|miss|no)\s+tomorrow(?:\s+morning)?(?:\s+(?:bjj|class))?",
        text,
    ))


def _fatigue_state(text: str) -> str | None:
    if re.search(r"\bvery fatigued\b|\bexhausted\b", text):
        return "very_fatigued"
    if re.search(r"\b(?:in )?pain\b", text):
        return "pain"
    if re.search(r"\bi(?:'m| am) tired\b|\bfatigue(?:\s+is)?\s+tired\b", text):
        return "tired"
    if re.search(r"\bfatigue(?:\s+is)?\s+normal\b|\bback to normal\b", text):
        return "normal"
    return None


def _mentioned_day(text: str, today: date) -> date | None:
    if re.search(r"\btomorrow\b", text):
        return today + timedelta(days=1)
    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        return date.fromisoformat(iso.group(1))
    for name, index in _WEEKDAYS.items():
        if re.search(rf"\b{name}\b", text):
            return _next_weekday(today, index)
    if re.search(r"\b(?:today|tonight|now|this afternoon|this evening)\b", text):
        return today
    return None


def _parse_day_token(token: str, today: date) -> date | None:
    value = token.strip().lower()
    if value in {"today"}:
        return today
    if value in {"tomorrow"}:
        return today + timedelta(days=1)
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        return date.fromisoformat(value)
    if value in _WEEKDAYS:
        return _next_weekday(today, _WEEKDAYS[value])
    return None


def _next_weekday(today: date, weekday: int) -> date:
    delta = (weekday - today.weekday()) % 7
    return today + timedelta(days=delta)


def _mutation_from_payload(payload: object, today: date) -> CalendarMutation | None:
    if not isinstance(payload, dict) or payload.get("op") not in _OPS:
        return None
    return CalendarMutation(
        op=str(payload["op"]),
        date=_parse_date(payload.get("date")) or today if payload.get("date") else None,
        to_date=_parse_date(payload.get("to_date")),
        workout_type=_clean(payload.get("workout_type")),
        session_id=_clean(payload.get("session_id")),
        start_at=_parse_datetime(payload.get("start_at")),
        end_at=_parse_datetime(payload.get("end_at")),
        fatigue_state=_clean(payload.get("fatigue_state")),
        task_id=_clean(payload.get("task_id")),
        task_title=_clean(payload.get("task_title")),
        event_id=_clean(payload.get("event_id")),
        hard=payload.get("hard") if isinstance(payload.get("hard"), bool) else None,
    )


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _parse_datetime(value: object) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=ZoneInfo(settings.timezone))
    if isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=ZoneInfo(settings.timezone))
        return parsed
    return None


def _clean(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def load_chili_personality() -> str:
    chunks = []
    for raw in (settings.chili_soul_path, settings.chili_identity_path):
        path = Path(raw).expanduser()
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                chunks.append(text)
    return "\n\n".join(chunks)


def explain_adjustment(
    *,
    instruction: str,
    mutations: tuple[CalendarMutation, ...] | list[CalendarMutation],
    before: list[dict],
    overview: dict,
    today: date,
    daily_url: str,
) -> dict:
    how = [_how_line(item, before, today) for item in mutations]
    why = _why_lines(mutations, today)
    week_after = []
    seen: set[str] = set()
    for item in list(overview.get("week") or []) + list(overview.get("upcoming") or []):
        key = f"{str(item.get('start_at') or '')[:10]}:{item.get('planned_type')}"
        if key in seen:
            continue
        seen.add(key)
        week_after.append({
            "date": str(item.get("start_at") or "")[:10],
            "type": item.get("planned_type"),
            "title": item.get("title"),
            "status": item.get("status"),
        })
    prescription = overview.get("tomorrow_prescription") if isinstance(overview.get("tomorrow_prescription"), dict) else {}
    tomorrow = str(prescription.get("session") or "rest").replace("_", " ")
    if prescription.get("time"):
        tomorrow = f"{tomorrow} at {prescription['time']}"
    banner = _banner(mutations, today)
    lines = [daily_url, "", "Changed the week because you asked.", "", "How"]
    lines.extend(f"• {item}" for item in how)
    lines.extend(["", "Why"])
    lines.extend(f"• {item}" for item in why)
    if tomorrow:
        lines.extend(["", f"Tomorrow: {tomorrow}."])
        if prescription.get("why"):
            lines.append(str(prescription["why"]))
    decision_id = f"training:adjust:{today.isoformat()}:{'-'.join(item.op for item in mutations)}"
    return {
        "id": decision_id,
        "at": datetime.now(UTC).isoformat(),
        "instruction": instruction,
        "how": how,
        "why": why,
        "banner": banner,
        "week_after": week_after,
        "tomorrow": {
            "session": prescription.get("session"),
            "time": prescription.get("time"),
            "why": prescription.get("why"),
        },
        "notification": "\n".join(lines),
    }


def _how_line(mutation: CalendarMutation, before: list[dict], today: date) -> str:
    day = mutation.date or mutation.to_date or today
    previous = _previous_title(before, day)
    label = _day_label(day)
    if mutation.op == "gym_today":
        title = _type_title(mutation.workout_type or "strength_a")
        if previous and previous != title:
            return f"{label}: {previous} → {title}."
        return f"{label}: {title} is on the calendar."
    if mutation.op == "rest_today":
        return f"{label}: rest. The week rebuilds around it."
    if mutation.op == "decline_bjj":
        return f"{label}: BJJ is off. Not a timed class."
    if mutation.op == "confirm_bjj":
        return f"{label}: BJJ confirmed as a timed session."
    if mutation.op == "move_gym":
        return f"Gym moves to {label}."
    if mutation.op == "skip_session":
        return f"{label}: skipped. That miss is decided."
    if mutation.op == "replace_session":
        return f"{label}: replaced with {_type_title(mutation.workout_type or 'rest')}."
    if mutation.op == "move_session":
        return f"{label}: session moved to {mutation.start_at}."
    if mutation.op == "fatigue":
        return f"Fatigue set to {mutation.fatigue_state}."
    if mutation.op == "add_bjj":
        return f"{label}: BJJ added to the calendar."
    if mutation.op == "place_session":
        return f"{label}: placed {_type_title(mutation.workout_type or '')} for the remaining week."
    if mutation.op == "complete_task":
        return f"Marked {mutation.task_title or 'a task'} done."
    if mutation.op == "move_meeting":
        return f"Moved {mutation.event_id} on the local calendar snapshot."
    return f"{label}: {mutation.op.replace('_', ' ')}."


def _why_lines(mutations: tuple[CalendarMutation, ...] | list[CalendarMutation], today: date) -> list[str]:
    reasons: list[str] = ["Your call wins. I rebuilt the rest of the week around it."]
    ops = {item.op for item in mutations}
    if "gym_today" in ops:
        gym = next(item for item in mutations if item.op == "gym_today")
        day = gym.date or today
        if day.weekday() == 6:
            reasons.append("Sunday gym counts for the coming week, so I did not keep another Strength A.")
        else:
            reasons.append("I am not adding a makeup lift later.")
    if "decline_bjj" in ops or "skip_session" in ops:
        reasons.append("Missed BJJ searches the next real class window. Strength B does not keep that day.")
    if "rest_today" in ops:
        reasons.append("A rest day is a prescription, not empty capacity.")
    if "fatigue" in ops:
        reasons.append("Fatigue changes tomorrow. It does not invent a makeup session.")
    if "place_session" in ops:
        reasons.append("The evening calendar check found a missing tournament piece and placed it on an Open day, not on rest or BJJ.")
    return reasons


def _banner(mutations: tuple[CalendarMutation, ...] | list[CalendarMutation], today: date) -> str:
    bits = []
    for item in mutations:
        day = item.date or item.to_date or today
        if item.op == "gym_today":
            bits.append(f"{_type_title(item.workout_type or 'strength_a')} is {_day_label(day)}")
        elif item.op == "decline_bjj":
            bits.append(f"{_day_label(day)} BJJ is off")
        elif item.op == "rest_today":
            bits.append(f"{_day_label(day)} is rest")
        elif item.op == "move_gym":
            bits.append(f"gym moves to {_day_label(day)}")
    if bits:
        return "Changed the week. " + "; ".join(bits) + "."
    return "Changed the week. Check How and Why."


def _previous_title(before: list[dict], day: date) -> str | None:
    key = day.isoformat()
    for item in before:
        if str(item.get("date") or "")[:10] == key:
            return str(item.get("title") or _type_title(str(item.get("type") or ""))) or None
    return None


def _day_label(day: date) -> str:
    return f"{day.strftime('%a')} {day.day} {day.strftime('%b')}"


def _type_title(workout_type: str) -> str:
    return {
        "bjj_technical": "BJJ Technical",
        "bjj_normal": "BJJ Normal",
        "bjj_hard": "Hard BJJ",
        "strength_a": "Gym (Strength A)",
        "strength_b": "Gym (Strength B)",
        "zone_2": "Zone 2",
        "grip": "Grip",
        "recovery": "Recovery",
        "rest": "Rest",
        "competition": "Competition",
    }.get(workout_type, workout_type.replace("_", " ").title())


def _daily_url(day: date) -> str:
    base = (settings.chili_public_url or settings.daily_briefing_base_url).rstrip("/")
    return f"{base}/daily/{day.isoformat()}"


def _invoke(method, *args, now=None, **kwargs):
    if now is not None:
        try:
            return method(*args, now=now, **kwargs)
        except TypeError:
            pass
    return method(*args, **kwargs)


def _output_text(payload: dict) -> str:
    for output in payload.get("output", []):
        for content in output.get("content", []):
            if content.get("type") == "output_text":
                return str(content.get("text", ""))
    raise ValueError("Calendar adjust model returned no text.")
