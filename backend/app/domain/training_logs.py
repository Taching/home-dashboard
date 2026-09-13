from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import TrainingLog
from app.database.session import SessionLocal
from app.domain.calendar_bridge import CalendarEvent
from app.domain.training_manual import ParsedTrainingLog, parse_training_message
from app.domain.training_plans import (
    TRAINING_KINDS,
    TrainingKind,
    TrainingPlan,
    all_plans,
    plan_for,
    suggested_kinds_for,
)
from app.domain.training_questions import context_question_lines, questions_for

TrainingCompleted = Literal["yes", "partial", "skipped", "no"]
TrainingFeeling = Literal["fresh", "normal", "tired", "wrecked"]
TrainingSource = Literal["ui", "openclaw", "automation"]
CALENDAR_NAME = "Chili Training"
TITLE_ALIASES: dict[str, TrainingKind] = {
    "strength a": "strength_a",
    "strength-a": "strength_a",
    "strength_a": "strength_a",
    "strength b": "strength_b",
    "strength-b": "strength_b",
    "strength_b": "strength_b",
    "zone 2": "zone2",
    "zone2": "zone2",
    "zone 2 cardio": "zone2",
    "grip": "grip",
    "bjj": "bjj",
    "jiu jitsu": "bjj",
    "jiujitsu": "bjj",
    "bjj hard": "bjj_hard",
    "hard bjj": "bjj_hard",
    "full rest": "rest",
    "rest": "rest",
    "sober": "sober",
    "sober check-in": "sober",
}


@dataclass(frozen=True)
class ExerciseDone:
    name: str
    done: bool


@dataclass(frozen=True)
class PlannedExercise:
    name: str
    prescription: str | None
    details: tuple[str, ...]
    done: bool


@dataclass(frozen=True)
class DailyWorkout:
    kind: TrainingKind
    title: str
    summary: str
    status: Literal["planned", "logged"]
    completed: TrainingCompleted | None
    note: str | None
    exercises: tuple[PlannedExercise, ...]


@dataclass(frozen=True)
class DailyMeeting:
    title: str
    start_at: datetime
    end_at: datetime
    is_all_day: bool


@dataclass(frozen=True)
class DailyBriefing:
    date: date
    timezone: str
    workouts: tuple[DailyWorkout, ...]
    meetings: tuple[DailyMeeting, ...]
    calendar_status: str
    sober_days: int
    sober_answered: TrainingCompleted | None
    sober_note: str | None
    sleep: None
    preview: bool
    daily_url: str


@dataclass(frozen=True)
class TrainingLogRecord:
    id: int
    logged_at: datetime
    kind: TrainingKind
    completed: TrainingCompleted
    feeling: TrainingFeeling | None
    note: str | None
    rounds: str | None
    duration_minutes: float | None
    avg_hr: int | None
    max_hr: int | None
    distance_km: float | None
    exercises: tuple[ExerciseDone, ...]
    source: TrainingSource


@dataclass(frozen=True)
class TrainingTodaySnapshot:
    date: date
    suggested: tuple[TrainingKind, ...]
    suggested_source: Literal["calendar", "week"]
    logs: tuple[TrainingLogRecord, ...]
    sober: TrainingLogRecord | None


@dataclass(frozen=True)
class ManagedCalendarEvent:
    session_id: str
    title: str
    start_at: datetime
    end_at: datetime
    is_all_day: bool
    notes: str


class TrainingService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(settings.timezone)

    @staticmethod
    def plans() -> list[TrainingPlan]:
        return all_plans()

    @staticmethod
    def plan(slug: str) -> TrainingPlan | None:
        return plan_for(slug)

    def nudge_message(self, day: date | None = None) -> str:
        snapshot = self.for_day(day) if day is not None else self.today()
        names = [plan_for(kind).name if plan_for(kind) else kind for kind in snapshot.suggested]
        label = ", ".join(names) if names else "training"
        daily = self.public_url(f"/daily/{snapshot.date.isoformat()}")
        first = snapshot.suggested[0] if snapshot.suggested else None
        workout = self.public_url(f"/workout/{first}") if first else self.public_url("/workout")
        if snapshot.date.weekday() == 6:
            return (
                f"{daily}\n\n"
                "Sunday rest. Open the page, mark what you did, and add a note if it felt easy or hard."
            )
        return (
            f"{workout}\n\n"
            f"Today: {label}. Open the page, mark what you did, and add a note if it felt easy or hard."
        )

    def public_url(self, path: str = "") -> str:
        base = (settings.chili_public_url or "http://127.0.0.1:8080").rstrip("/")
        if not path:
            return base
        return f"{base}/{path.lstrip('/')}"

    def today(
        self,
        now: datetime | None = None,
        calendar_events: list[CalendarEvent] | None = None,
    ) -> TrainingTodaySnapshot:
        current = self._as_local(now or datetime.now(UTC))
        return self.for_day(current.date(), calendar_events=calendar_events)

    def for_day(
        self,
        day: date,
        calendar_events: list[CalendarEvent] | None = None,
    ) -> TrainingTodaySnapshot:
        calendar_kinds = self._kinds_from_calendar(calendar_events or [], day)
        suggested = calendar_kinds or suggested_kinds_for(day)
        logs = self.logs_for(day)
        sober = next((row for row in reversed(logs) if row.kind == "sober"), None)
        return TrainingTodaySnapshot(
            date=day,
            suggested=suggested,
            suggested_source="calendar" if calendar_kinds else "week",
            logs=tuple(logs),
            sober=sober,
        )

    def logs_for(self, day: date) -> list[TrainingLogRecord]:
        start, end = self._day_bounds(day)
        with self._session_factory() as session:
            rows = session.scalars(
                select(TrainingLog)
                .where(TrainingLog.logged_at >= start)
                .where(TrainingLog.logged_at < end)
                .order_by(TrainingLog.logged_at)
            ).all()
            return [self._to_record(row) for row in rows]

    def log(
        self,
        *,
        kind: TrainingKind,
        completed: TrainingCompleted,
        feeling: TrainingFeeling | None = None,
        note: str | None = None,
        rounds: str | None = None,
        duration_minutes: float | None = None,
        avg_hr: int | None = None,
        max_hr: int | None = None,
        distance_km: float | None = None,
        exercises: list[ExerciseDone] | tuple[ExerciseDone, ...] | None = None,
        source: TrainingSource = "ui",
        now: datetime | None = None,
    ) -> TrainingLogRecord:
        if kind not in TRAINING_KINDS:
            raise ValueError("Unknown training kind.")
        completed = self._normalise_completed(kind, completed)
        logged_at = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            row = TrainingLog(
                logged_at=logged_at,
                kind=kind,
                completed=completed,
                feeling=feeling,
                note=self._trim(note, 500),
                rounds=self._trim(rounds, 32),
                duration_minutes=duration_minutes,
                avg_hr=avg_hr,
                max_hr=max_hr,
                distance_km=distance_km,
                exercises=self._dump_exercises(exercises),
                source=source,
            )
            session.add(row)
            session.commit()
            session.refresh(row)
            return self._to_record(row)

    def _update_log(
        self,
        log_id: int,
        *,
        completed: TrainingCompleted,
        note: str | None,
        exercises: list[ExerciseDone] | tuple[ExerciseDone, ...],
        source: TrainingSource,
        now: datetime,
    ) -> TrainingLogRecord:
        with self._session_factory() as session:
            row = session.get(TrainingLog, log_id)
            if row is None:
                raise KeyError(log_id)
            row.completed = completed
            if note is not None:
                row.note = self._trim(note, 500)
            row.exercises = self._dump_exercises(exercises)
            row.source = source
            row.logged_at = now
            session.commit()
            session.refresh(row)
            return self._to_record(row)

    def log_workout(
        self,
        *,
        kind: TrainingKind,
        exercises: list[ExerciseDone] | tuple[ExerciseDone, ...],
        note: str | None = None,
        source: TrainingSource = "ui",
        now: datetime | None = None,
    ) -> TrainingLogRecord:
        if kind == "sober":
            raise ValueError("Sober is logged separately in the evening.")
        cleaned = self._clean_exercises(exercises)
        current = self._as_utc(now or datetime.now(UTC))
        existing = next((row for row in reversed(self.logs_for(current.astimezone(self._timezone).date())) if row.kind == kind), None)
        if existing is not None:
            return self._update_log(
                existing.id,
                completed=self._completed_from_exercises(kind, cleaned),
                note=note,
                exercises=cleaned,
                source=source,
                now=current,
            )
        return self.log(
            kind=kind,
            completed=self._completed_from_exercises(kind, cleaned),
            note=note,
            exercises=cleaned,
            source=source,
            now=now,
        )

    def log_sober(
        self,
        *,
        sober: bool,
        note: str | None = None,
        source: TrainingSource = "ui",
        now: datetime | None = None,
    ) -> TrainingLogRecord:
        return self.log(
            kind="sober",
            completed="yes" if sober else "no",
            note=note,
            source=source,
            now=now,
        )

    def daily(
        self,
        day: date,
        *,
        preview: str | None = None,
        calendar_events: list[CalendarEvent] | None = None,
        calendar_status: str = "ready",
        now: datetime | None = None,
    ) -> DailyBriefing:
        snapshot = self.for_day(day, calendar_events=calendar_events)
        preview_kind = self._preview_kind(preview)
        kinds = (preview_kind,) if preview_kind else snapshot.suggested
        workouts = tuple(self._daily_workout(kind, snapshot.logs) for kind in kinds if plan_for(kind))
        meetings = tuple(
            DailyMeeting(
                title=event.title,
                start_at=event.start_at,
                end_at=event.end_at,
                is_all_day=event.is_all_day,
            )
            for event in calendar_events or []
            if self._event_on_day(event, day) and not self._training_title(event.title)
        )
        return DailyBriefing(
            date=day,
            timezone=settings.timezone,
            workouts=workouts,
            meetings=meetings,
            calendar_status=calendar_status,
            sober_days=self.sober_streak(day),
            sober_answered=snapshot.sober.completed if snapshot.sober else None,
            sober_note=snapshot.sober.note if snapshot.sober else None,
            sleep=None,
            preview=preview_kind is not None,
            daily_url=self.public_url(f"/daily/{day.isoformat()}"),
        )

    def sober_streak(self, day: date) -> int:
        cursor = day
        if not any(row.kind == "sober" for row in self.logs_for(cursor)):
            cursor = cursor - timedelta(days=1)
        count = 0
        while count < 400:
            sober = next((row for row in reversed(self.logs_for(cursor)) if row.kind == "sober"), None)
            if sober is None or sober.completed != "yes":
                break
            count += 1
            cursor = cursor - timedelta(days=1)
        return count

    def stamp_for_day(self, day: date, now: datetime | None = None) -> datetime:
        current = self._as_local(now or datetime.now(UTC))
        if current.date() == day:
            return current
        return datetime.combine(day, time(12, 0), tzinfo=self._timezone)

    def log_manual_message(self, text: str, now: datetime | None = None) -> TrainingLogRecord:
        parsed = parse_training_message(text)
        if parsed is None:
            raise ValueError("Could not parse a training check-in from the message.")
        return self.log_parsed(parsed, source="openclaw", now=now)

    def log_parsed(
        self,
        parsed: ParsedTrainingLog,
        *,
        source: TrainingSource,
        now: datetime | None = None,
    ) -> TrainingLogRecord:
        return self.log(
            kind=parsed.kind,
            completed=parsed.completed,  # type: ignore[arg-type]
            feeling=parsed.feeling,  # type: ignore[arg-type]
            note=parsed.note,
            rounds=parsed.rounds,
            duration_minutes=parsed.duration_minutes,
            avg_hr=parsed.avg_hr,
            max_hr=parsed.max_hr,
            distance_km=parsed.distance_km,
            source=source,
            now=now,
        )

    @staticmethod
    def try_parse_manual_message(text: str) -> ParsedTrainingLog | None:
        return parse_training_message(text)

    def managed_calendar_plan(self, now: datetime | None = None, days: int = 21) -> dict:
        current = self._as_local(now or datetime.now(UTC)).date()
        events: list[ManagedCalendarEvent] = []
        for offset in range(days):
            day = current + timedelta(days=offset)
            for kind in suggested_kinds_for(day):
                if kind == "sober":
                    continue
                plan = plan_for(kind)
                if plan is None:
                    continue
                start = datetime.combine(day, time.min, tzinfo=self._timezone)
                end = start + timedelta(days=1)
                session_id = f"{kind}-{day.isoformat()}"
                events.append(
                    ManagedCalendarEvent(
                        session_id=session_id,
                        title=plan.name,
                        start_at=start,
                        end_at=end,
                        is_all_day=True,
                        notes=(
                            f"{plan.summary}\n"
                            f"{self.public_url(f'/workout/{plan.slug}')}\n"
                            f"chili-training:{session_id}"
                        ),
                    )
                )
        return {
            "calendar_name": CALENDAR_NAME,
            "events": [
                {
                    "session_id": event.session_id,
                    "title": event.title,
                    "start_at": event.start_at.isoformat(),
                    "end_at": event.end_at.isoformat(),
                    "is_all_day": event.is_all_day,
                    "notes": event.notes,
                }
                for event in events
            ],
        }

    def context_lines(
        self,
        calendar_events: list[CalendarEvent] | None = None,
        now: datetime | None = None,
    ) -> list[str]:
        snapshot = self.today(now=now, calendar_events=calendar_events)
        names = [plan_for(kind).name if plan_for(kind) else kind for kind in snapshot.suggested]
        suggested = ", ".join(names) if names else "none"
        sober = "not logged"
        if snapshot.sober is not None:
            sober = snapshot.sober.completed
        logged = ", ".join(f"{row.kind}={row.completed}" for row in snapshot.logs) or "none"
        daily_url = self.public_url(f"/daily/{snapshot.date.isoformat()}")
        lines = [
            f"- Training today ({snapshot.date.isoformat()}, via {snapshot.suggested_source}): {suggested}.",
            f"- Training logs today: {logged}. Sober: {sober}.",
            "- Telegram voice: 3–5 short lines. Put the full https:// URL on its own first line. Never omit the link. Never say tick or checkbox.",
            f"- Gym/BJJ message: first the workout URL, then “Today: {suggested}. Open the page, mark what you did, and add a note if it felt easy or hard.”",
            f"- Evening sober message: first {daily_url}, then “Sober tonight? Answer on the daily page.”",
            "- If the sober answer is still missing after 22:00 or the next morning, send one follow-up with the same dated /daily URL. Do not mention last-check-in dates on the wall.",
            f"- Sunday morning message: first {daily_url}, then “Sunday weigh-in and week review. Compare with last week, then say if next week needs a change.”",
            "- Do not ask sleep, weight (except Sunday), readiness, fatigue, soreness, or pain.",
            "- Sleep will come from Garmin later.",
        ]
        for kind in snapshot.suggested:
            plan = plan_for(kind)
            if plan is None:
                continue
            lines.append(f"  - {plan.name}: {self.public_url(f'/workout/{plan.slug}')}")
        lines.append(f"  - Today page: {self.public_url('/workout')}")
        lines.append(f"  - Daily page: {daily_url}")
        lines.extend(context_question_lines())
        lines.append(
            "- Walks still use POST /api/v1/automation/walkingpad/log — do not duplicate walks here."
        )
        return lines

    @staticmethod
    def questions(kind: TrainingKind) -> tuple[str, ...]:
        return questions_for(kind)

    def _kinds_from_calendar(self, events: list[CalendarEvent], day: date) -> tuple[TrainingKind, ...]:
        found: list[TrainingKind] = []
        for event in events:
            if not self._event_on_day(event, day):
                continue
            kind = TITLE_ALIASES.get(event.title.strip().lower())
            if kind and kind not in found and kind != "sober":
                found.append(kind)
        return tuple(found)

    def _event_on_day(self, event: CalendarEvent, day: date) -> bool:
        local_start = event.start_at.astimezone(self._timezone).date()
        local_end = event.end_at.astimezone(self._timezone).date()
        if event.is_all_day:
            return local_start <= day < local_end or local_start == day
        return local_start <= day <= local_end

    def _day_bounds(self, day: date) -> tuple[datetime, datetime]:
        start = datetime.combine(day, time.min, tzinfo=self._timezone).astimezone(UTC)
        end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=self._timezone).astimezone(UTC)
        return start, end

    def _as_local(self, value: datetime) -> datetime:
        return self._as_utc(value).astimezone(self._timezone)

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @staticmethod
    def _trim(value: str | None, limit: int) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned[:limit] if cleaned else None

    @staticmethod
    def _normalise_completed(kind: TrainingKind, completed: str) -> TrainingCompleted:
        if kind == "sober":
            if completed in {"yes", "no"}:
                return completed  # type: ignore[return-value]
            raise ValueError("Sober check-in must be yes or no.")
        if completed in {"yes", "partial", "skipped"}:
            return completed  # type: ignore[return-value]
        if completed == "no":
            return "skipped"
        raise ValueError("Completed must be yes, partial, or skipped.")

    @classmethod
    def _to_record(cls, row: TrainingLog) -> TrainingLogRecord:
        return TrainingLogRecord(
            id=row.id,
            logged_at=row.logged_at,
            kind=row.kind,  # type: ignore[arg-type]
            completed=row.completed,  # type: ignore[arg-type]
            feeling=row.feeling,  # type: ignore[arg-type]
            note=row.note,
            rounds=row.rounds,
            duration_minutes=row.duration_minutes,
            avg_hr=row.avg_hr,
            max_hr=row.max_hr,
            distance_km=row.distance_km,
            exercises=cls._load_exercises(row.exercises),
            source=row.source,  # type: ignore[arg-type]
        )

    def logs_between(self, start: date, end: date) -> list[TrainingLogRecord]:
        start_utc, _ = self._day_bounds(start)
        _, end_utc = self._day_bounds(end)
        with self._session_factory() as session:
            rows = session.scalars(
                select(TrainingLog)
                .where(TrainingLog.logged_at >= start_utc)
                .where(TrainingLog.logged_at < end_utc)
                .order_by(TrainingLog.logged_at)
            ).all()
            return [self._to_record(row) for row in rows]

    def _daily_workout(self, kind: TrainingKind, logs: tuple[TrainingLogRecord, ...]) -> DailyWorkout:
        plan = plan_for(kind)
        if plan is None:
            raise ValueError("Unknown training kind.")
        last = next((row for row in reversed(logs) if row.kind == kind), None)
        done_map = {item.name: item.done for item in (last.exercises if last else ())}
        exercises = tuple(
            PlannedExercise(
                name=block.title,
                prescription=block.prescription,
                details=block.details,
                done=done_map.get(block.title, False),
            )
            for block in plan.blocks
        )
        if not exercises:
            fallback = "Full rest" if kind == "rest" else plan.name
            exercises = (
                PlannedExercise(
                    name=fallback,
                    prescription=None,
                    details=(),
                    done=last.completed == "yes" if last else False,
                ),
            )
        return DailyWorkout(
            kind=kind,
            title=plan.name,
            summary=plan.summary,
            status="logged" if last else "planned",
            completed=last.completed if last else None,
            note=last.note if last else None,
            exercises=exercises,
        )

    @staticmethod
    def _preview_kind(preview: str | None) -> TrainingKind | None:
        if not preview:
            return None
        cleaned = preview.strip().lower()
        kind = TITLE_ALIASES.get(cleaned)
        if kind is None and cleaned in TRAINING_KINDS:
            kind = cleaned  # type: ignore[assignment]
        if kind in TRAINING_KINDS and kind != "sober":
            return kind
        return None

    @staticmethod
    def _training_title(title: str) -> bool:
        return TITLE_ALIASES.get(title.strip().lower()) is not None

    @staticmethod
    def _clean_exercises(
        exercises: list[ExerciseDone] | tuple[ExerciseDone, ...] | None,
    ) -> tuple[ExerciseDone, ...]:
        cleaned: list[ExerciseDone] = []
        seen: set[str] = set()
        for item in exercises or ():
            name = item.name.strip()[:120]
            if not name or name in seen:
                continue
            seen.add(name)
            cleaned.append(ExerciseDone(name=name, done=bool(item.done)))
        return tuple(cleaned)

    @classmethod
    def _dump_exercises(
        cls,
        exercises: list[ExerciseDone] | tuple[ExerciseDone, ...] | None,
    ) -> str | None:
        cleaned = cls._clean_exercises(exercises)
        if not cleaned:
            return None
        return json.dumps([{"name": item.name, "done": item.done} for item in cleaned])

    @staticmethod
    def _load_exercises(raw: str | None) -> tuple[ExerciseDone, ...]:
        if not raw:
            return ()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return ()
        if not isinstance(payload, list):
            return ()
        items: list[ExerciseDone] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name") or "").strip()[:120]
            if not name:
                continue
            items.append(ExerciseDone(name=name, done=bool(row.get("done"))))
        return tuple(items)

    @staticmethod
    def _completed_from_exercises(
        kind: TrainingKind,
        exercises: tuple[ExerciseDone, ...],
    ) -> TrainingCompleted:
        if not exercises:
            return "yes" if kind == "rest" else "skipped"
        done = sum(1 for item in exercises if item.done)
        if done == len(exercises):
            return "yes"
        if done == 0:
            return "skipped"
        return "partial"
