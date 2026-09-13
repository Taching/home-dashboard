from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import WeeklyReview, WeightLog
from app.database.session import SessionLocal
from app.domain.training_logs import ExerciseDone, TrainingLogRecord, TrainingService
from app.domain.training_plans import plan_for, suggested_kinds_for


@dataclass(frozen=True)
class WeightRecord:
    logged_at: datetime
    weight_kg: float


@dataclass(frozen=True)
class WeekSession:
    date: date
    kind: str
    title: str
    completed: str | None
    note: str | None
    exercises: tuple[ExerciseDone, ...]


@dataclass(frozen=True)
class SundayCheckIn:
    week_start: date
    week_ending: date
    weight_kg: float | None
    previous_weight_kg: float | None
    delta_kg: float | None
    review_note: str | None
    submitted: bool
    sessions: tuple[WeekSession, ...]


@dataclass(frozen=True)
class SundaySaveResult:
    check_in: SundayCheckIn
    notify_message: str
    review_prompt: str


class WeeklyService:
    def __init__(self, session_factory=SessionLocal) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(settings.timezone)

    def sunday_check_in(self, day: date, training: TrainingService) -> SundayCheckIn | None:
        if day.weekday() != 6:
            return None
        week_start = day - timedelta(days=6)
        saved = self.review_for(day)
        previous = self.latest_weight_before(day)
        current_kg = saved.weight_kg if saved is not None else None
        previous_kg = (
            saved.previous_weight_kg
            if saved is not None and saved.previous_weight_kg is not None
            else (previous.weight_kg if previous is not None else None)
        )
        delta = None
        if current_kg is not None and previous_kg is not None:
            delta = round(current_kg - previous_kg, 2)
        return SundayCheckIn(
            week_start=week_start,
            week_ending=day,
            weight_kg=current_kg,
            previous_weight_kg=previous_kg,
            delta_kg=delta,
            review_note=saved.note if saved is not None else None,
            submitted=saved is not None,
            sessions=self.week_sessions(day, training),
        )

    def save_sunday(
        self,
        day: date,
        training: TrainingService,
        *,
        weight_kg: float | None,
        same_as_last: bool = False,
        note: str | None = None,
        source: str = "ui",
        now: datetime | None = None,
    ) -> SundaySaveResult:
        if day.weekday() != 6:
            raise ValueError("Weight and week review are Sunday only.")
        current = self._as_local(now or datetime.now(UTC))
        stamped = current if current.date() == day else datetime.combine(day, time(12, 0), tzinfo=self._timezone)
        previous = self.latest_weight_before(day)
        previous_kg = previous.weight_kg if previous is not None else None
        resolved = previous_kg if same_as_last and previous_kg is not None else weight_kg
        if resolved is None:
            raise ValueError("Weight is required, or mark same as last week.")
        resolved = self._normalise_weight(resolved)
        sessions = self.week_sessions(day, training)
        summary = self.week_summary_text(sessions)
        with self._session_factory() as session:
            session.add(
                WeightLog(
                    logged_at=self._as_utc(stamped),
                    weight_kg=resolved,
                    source=source,
                )
            )
            row = session.scalars(select(WeeklyReview).where(WeeklyReview.week_ending == day)).first()
            if row is None:
                session.add(
                    WeeklyReview(
                        week_ending=day,
                        logged_at=self._as_utc(stamped),
                        weight_kg=resolved,
                        previous_weight_kg=previous_kg,
                        note=self._trim(note, 500),
                        summary=summary,
                        source=source,
                    )
                )
            else:
                row.logged_at = self._as_utc(stamped)
                row.weight_kg = resolved
                row.previous_weight_kg = previous_kg
                row.note = self._trim(note, 500)
                row.summary = summary
                row.source = source
            session.commit()
        check_in = self.sunday_check_in(day, training)
        if check_in is None:
            raise RuntimeError("Sunday check-in could not be loaded.")
        return SundaySaveResult(
            check_in=check_in,
            notify_message=self.notify_message(check_in, self.daily_url(day)),
            review_prompt=self.review_prompt(check_in),
        )

    def review_for(self, sunday: date) -> WeeklyReview | None:
        with self._session_factory() as session:
            return session.scalars(select(WeeklyReview).where(WeeklyReview.week_ending == sunday)).first()

    def latest_weight_before(self, day: date) -> WeightRecord | None:
        start = datetime.combine(day, time.min, tzinfo=self._timezone).astimezone(UTC)
        with self._session_factory() as session:
            row = session.scalars(
                select(WeightLog)
                .where(WeightLog.logged_at < start)
                .order_by(WeightLog.logged_at.desc())
            ).first()
            if row is None:
                return None
            return WeightRecord(logged_at=row.logged_at, weight_kg=row.weight_kg)

    def daily_url(self, day: date) -> str:
        base = (settings.chili_public_url or settings.daily_briefing_base_url).rstrip("/")
        return f"{base}/daily/{day.isoformat()}"

    def week_sessions(self, sunday: date, training) -> tuple[WeekSession, ...]:
        if not hasattr(training, "logs_between"):
            return self._week_sessions_from_overview(sunday, training)
        week_start = sunday - timedelta(days=6)
        logs = [row for row in training.logs_between(week_start, sunday) if row.kind != "sober"]
        by_day: dict[date, list[TrainingLogRecord]] = {}
        for row in logs:
            local_day = self._as_local(row.logged_at).date()
            by_day.setdefault(local_day, []).append(row)
        sessions: list[WeekSession] = []
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            day_logs = by_day.get(day, [])
            used: set[int] = set()
            for kind in suggested_kinds_for(day):
                if kind == "sober":
                    continue
                match = next((row for row in reversed(day_logs) if row.kind == kind), None)
                plan = plan_for(kind)
                sessions.append(
                    WeekSession(
                        date=day,
                        kind=kind,
                        title=plan.name if plan else kind,
                        completed=match.completed if match else None,
                        note=match.note if match else None,
                        exercises=match.exercises if match else (),
                    )
                )
                if match is not None:
                    used.add(match.id)
            for row in day_logs:
                if row.id in used:
                    continue
                plan = plan_for(row.kind)
                sessions.append(
                    WeekSession(
                        date=day,
                        kind=row.kind,
                        title=plan.name if plan else row.kind,
                        completed=row.completed,
                        note=row.note,
                        exercises=row.exercises,
                    )
                )
        return tuple(sessions)

    def _week_sessions_from_overview(self, sunday: date, training) -> tuple[WeekSession, ...]:
        now = datetime.combine(sunday, time(12), tzinfo=self._timezone)
        overview = training.overview(now)
        by_day: dict[date, list[dict]] = {}
        for item in overview.get("week") or []:
            day = date.fromisoformat(item["start_at"][:10]) if isinstance(item.get("start_at"), str) else sunday
            try:
                day = datetime.fromisoformat(item["start_at"]).astimezone(self._timezone).date()
            except Exception:
                pass
            by_day.setdefault(day, []).append(item)
        sessions: list[WeekSession] = []
        week_start = sunday - timedelta(days=6)
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            for item in by_day.get(day, []):
                status = item.get("status")
                completed = status if status in {"completed", "partial", "skipped"} else None
                sessions.append(
                    WeekSession(
                        date=day,
                        kind=item.get("planned_type") or "rest",
                        title=item.get("title") or item.get("planned_type") or "Session",
                        completed=completed,
                        note=item.get("notes"),
                        exercises=tuple(
                            ExerciseDone(name=exercise["name"], done=bool(exercise.get("done")))
                            for exercise in item.get("exercises") or []
                            if exercise.get("name")
                        ),
                    )
                )
        return tuple(sessions)

    def reminder_due(self, now: datetime | None = None) -> date | None:
        current = self._as_local(now or datetime.now(UTC))
        if current.weekday() != 6 or current.hour != 10:
            return None
        return current.date()

    def reminder_message(self, sunday: date, daily_url: str) -> str:
        previous = self.latest_weight_before(sunday)
        if previous is not None:
            last = f"Last Sunday was {previous.weight_kg:.1f} kg. "
        else:
            last = "No last-Sunday weight yet. "
        return (
            f"{daily_url}\n\n"
            "Sunday weigh-in and week review.\n"
            f"{last}Compare with this week, then say if next week needs a change."
        )

    @staticmethod
    def notify_message(check_in: SundayCheckIn, daily_url: str) -> str:
        weight = WeeklyService._weight_line(check_in)
        return (
            f"{daily_url}\n\n"
            f"Sunday saved.\n"
            f"{weight}\n"
            "I'll reply if next week needs a change."
        )

    @staticmethod
    def review_prompt(check_in: SundayCheckIn) -> str:
        weight = WeeklyService._weight_line(check_in)
        note = check_in.review_note or "No extra note."
        return (
            "Takatoshi submitted the Sunday weigh-in and week review.\n"
            f"{weight}\n"
            f"{WeeklyService.week_summary_text(check_in.sessions)}\n"
            f"His note: {note}\n\n"
            "Reply in Telegram in 3–6 short lines:\n"
            "1. Weight change in plain words.\n"
            "2. How the week actually went.\n"
            "3. One keep-or-change for next week.\n"
            "Do not ask sleep, readiness, or morning metrics. "
            "Do not paste the full program."
        )

    @staticmethod
    def week_summary_text(sessions: tuple[WeekSession, ...] | list[WeekSession]) -> str:
        logged = [session for session in sessions if session.completed]
        missing = [session for session in sessions if session.completed is None]
        if not logged:
            return "No workouts logged this week."
        lines = [f"Logged {len(logged)} session(s):"]
        for session in logged:
            line = f"- {session.date.strftime('%a')} {session.title}: {session.completed}"
            done = [item.name for item in session.exercises if item.done]
            skipped = [item.name for item in session.exercises if not item.done]
            if session.completed == "partial" and done:
                line += f" · did {', '.join(done)}"
            if session.completed in {"partial", "skipped"} and skipped:
                line += f" · skipped {', '.join(skipped)}"
            if session.note:
                line += f" · {session.note}"
            lines.append(line)
        if missing:
            titles = ", ".join(f"{session.date.strftime('%a')} {session.title}" for session in missing)
            lines.append(f"Not logged: {titles}.")
        return "\n".join(lines)

    @staticmethod
    def _weight_line(check_in: SundayCheckIn) -> str:
        if check_in.weight_kg is None:
            return "Weight: not logged."
        if check_in.previous_weight_kg is None:
            return f"Weight: {check_in.weight_kg:.1f} kg (no previous Sunday)."
        delta = check_in.delta_kg or 0
        if abs(delta) < 0.05:
            return f"Weight: {check_in.weight_kg:.1f} kg, same as last week."
        direction = "up" if delta > 0 else "down"
        return (
            f"Weight: {check_in.weight_kg:.1f} kg, "
            f"{direction} {abs(delta):.1f} kg from last week "
            f"({check_in.previous_weight_kg:.1f} kg)."
        )

    @staticmethod
    def _normalise_weight(weight_kg: float) -> float:
        value = round(float(weight_kg), 1)
        if value < 30 or value > 250:
            raise ValueError("Weight must be between 30 and 250 kg.")
        return value

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
