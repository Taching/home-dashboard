from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import WeeklyReview, WeightLog
from app.database.session import SessionLocal
from app.domain import cut_plan
from app.domain.telegram_text import telegram_message
from app.domain.wellbeing import WellbeingService
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
class WeeklyCheckIn:
    """Monday check-in for the Mon–Sun week that just ended (March 2027 plan)."""
    week_start: date
    week_ending: date
    check_in_date: date
    weight_kg: float | None
    previous_weight_kg: float | None
    delta_kg: float | None
    weigh_ins: int
    review_note: str | None
    submitted: bool
    sessions: tuple[WeekSession, ...]
    counts: dict[str, int] = field(default_factory=dict)
    sleep_average: float | None = None
    waist_cm: float | None = None
    energy: int | None = None
    hunger: int | None = None
    bjj_performance: int | None = None
    pain_note: str | None = None
    kcal_adjustment: int | None = None
    kcal_reason: str | None = None
    target_kg: float | None = None
    division: dict = field(default_factory=dict)
    watch: dict | None = None
    coach_review: str | None = None


@dataclass(frozen=True)
class WeeklySaveResult:
    check_in: WeeklyCheckIn
    notify_message: str


class WeeklyService:
    def __init__(self, session_factory=SessionLocal, *, wellbeing=None, garmin=None) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(settings.timezone)
        self._wellbeing = wellbeing if wellbeing is not None else WellbeingService(session_factory)
        self._garmin = garmin

    def weekly_check_in(self, day: date, training) -> WeeklyCheckIn | None:
        if day.weekday() != 0:
            return None
        week_ending = day - timedelta(days=1)
        week_start = week_ending - timedelta(days=6)
        saved = self.review_for(week_ending)
        weights = self._weights(week_start - timedelta(days=14), week_ending)
        average, count = cut_plan.seven_day_average(weights, week_ending)
        previous, _ = cut_plan.seven_day_average(weights, week_ending - timedelta(days=7))
        sleep = self._sleep(week_start, week_ending)
        sessions = self.week_sessions(week_ending, training)
        if saved is not None and saved.weight_kg is not None:
            average = saved.weight_kg
        if saved is not None and saved.previous_weight_kg is not None:
            previous = saved.previous_weight_kg
        delta = round(average - previous, 2) if average is not None and previous is not None else None
        performance_ok = None if saved is None or saved.bjj_performance is None else saved.bjj_performance >= 3
        if saved is not None and saved.kcal_adjustment is not None:
            adjustment, reason = saved.kcal_adjustment, saved.kcal_reason
        else:
            adjustment, reason = self.proposed_adjustment(day, weights)
        return WeeklyCheckIn(
            week_start=week_start,
            week_ending=week_ending,
            check_in_date=day,
            weight_kg=average,
            previous_weight_kg=previous,
            delta_kg=delta,
            weigh_ins=count,
            review_note=saved.note if saved is not None else None,
            submitted=saved is not None,
            sessions=sessions,
            counts=self.session_counts(sessions),
            sleep_average=round(sum(sleep) / len(sleep), 1) if sleep else None,
            waist_cm=saved.waist_cm if saved is not None else None,
            energy=saved.energy if saved is not None else None,
            hunger=saved.hunger if saved is not None else None,
            bjj_performance=saved.bjj_performance if saved is not None else None,
            pain_note=saved.pain_note if saved is not None else None,
            kcal_adjustment=adjustment,
            kcal_reason=reason,
            target_kg=round(sum(cut_plan.target_for(week_ending)) / 2, 1),
            division=cut_plan.division_status(day, average, performance_ok=performance_ok),
            watch=self._watch_week(week_start, week_ending),
            coach_review=saved.coach_review if saved is not None else None,
        )

    def proposed_adjustment(
        self, day: date, weights: dict[date, float], *, performance_worse: bool = False,
    ) -> tuple[int, str]:
        week_ending = day - timedelta(days=1)
        changes = [
            cut_plan.weekly_change(weights, week_ending),
            cut_plan.weekly_change(weights, week_ending - timedelta(days=7)),
        ]
        return cut_plan.intake_adjustment(
            day, changes,
            last_adjustment_on=self.last_adjustment_on(day),
            performance_worse=performance_worse,
        )

    def kcal_adjustment_total(self, day: date) -> int:
        """Sum of every intake change decided at a Monday check-in before `day`."""
        with self._session_factory() as session:
            rows = session.scalars(
                select(WeeklyReview.kcal_adjustment)
                .where(WeeklyReview.week_ending < day)
                .where(WeeklyReview.kcal_adjustment.is_not(None))
            ).all()
        return int(sum(rows))

    def last_adjustment_on(self, day: date) -> date | None:
        with self._session_factory() as session:
            row = session.scalars(
                select(WeeklyReview)
                .where(WeeklyReview.week_ending < day - timedelta(days=1))
                .where(WeeklyReview.kcal_adjustment.is_not(None))
                .where(WeeklyReview.kcal_adjustment != 0)
                .order_by(WeeklyReview.week_ending.desc())
            ).first()
        return row.week_ending + timedelta(days=1) if row is not None else None

    def latest_performance_ok(self, day: date) -> bool | None:
        with self._session_factory() as session:
            row = session.scalars(
                select(WeeklyReview)
                .where(WeeklyReview.week_ending < day)
                .where(WeeklyReview.bjj_performance.is_not(None))
                .order_by(WeeklyReview.week_ending.desc())
            ).first()
        return None if row is None else row.bjj_performance >= 3

    def store_coach_review(self, day: date, text: str) -> None:
        week_ending = day - timedelta(days=1) if day.weekday() == 0 else day
        with self._session_factory() as session:
            row = session.scalars(select(WeeklyReview).where(WeeklyReview.week_ending == week_ending)).first()
            if row is None:
                return
            row.coach_review = text
            session.commit()

    def save_weekly(
        self,
        day: date,
        training,
        *,
        energy: int,
        hunger: int,
        bjj_performance: int,
        waist_cm: float | None = None,
        pain_note: str | None = None,
        note: str | None = None,
        source: str = "ui",
        now: datetime | None = None,
    ) -> WeeklySaveResult:
        if day.weekday() != 0:
            raise ValueError("The weekly check-in is on Monday.")
        for label, value in (("Energy", energy), ("Hunger", hunger), ("BJJ performance", bjj_performance)):
            if value is None or not 1 <= int(value) <= 5:
                raise ValueError(f"{label} must be rated 1–5.")
        if waist_cm is not None and not 50 <= waist_cm <= 150:
            raise ValueError("Waist must be between 50 and 150 cm.")
        current = self._as_local(now or datetime.now(UTC))
        stamped = current if current.date() == day else datetime.combine(day, time(12, 0), tzinfo=self._timezone)
        week_ending = day - timedelta(days=1)
        weights = self._weights(week_ending - timedelta(days=20), week_ending)
        average, _ = cut_plan.seven_day_average(weights, week_ending)
        previous, _ = cut_plan.seven_day_average(weights, week_ending - timedelta(days=7))
        sleep = self._sleep(week_ending - timedelta(days=6), week_ending)
        sessions = self.week_sessions(week_ending, training)
        summary = self.week_summary_text(sessions)
        with self._session_factory() as session:
            row = session.scalars(select(WeeklyReview).where(WeeklyReview.week_ending == week_ending)).first()
            if row is None:
                adjustment, reason = self.proposed_adjustment(
                    day, weights, performance_worse=bjj_performance <= 2 and energy <= 2,
                )
                row = WeeklyReview(week_ending=week_ending, kcal_adjustment=adjustment, kcal_reason=reason[:300])
                session.add(row)
            row.logged_at = self._as_utc(stamped)
            row.weight_kg = average
            row.previous_weight_kg = previous
            row.waist_cm = round(float(waist_cm), 1) if waist_cm is not None else None
            row.energy = int(energy)
            row.hunger = int(hunger)
            row.bjj_performance = int(bjj_performance)
            row.pain_note = self._trim(pain_note, 500)
            row.sleep_average = round(sum(sleep) / len(sleep), 1) if sleep else None
            row.note = self._trim(note, 500)
            row.summary = summary
            row.source = source
            session.commit()
        check_in = self.weekly_check_in(day, training)
        if check_in is None:
            raise RuntimeError("Weekly check-in could not be loaded.")
        return WeeklySaveResult(
            check_in=check_in,
            notify_message=self.notify_message(check_in, self.daily_url(day)),
        )

    def _watch_week(self, start: date, end: date) -> dict | None:
        if self._garmin is None or not hasattr(self._garmin, "week_summary"):
            return None
        try:
            return self._garmin.week_summary(start, end)
        except Exception:
            return None

    def _weights(self, start: date, end: date) -> dict[date, float]:
        if self._wellbeing is None or not hasattr(self._wellbeing, "weights_between"):
            return {}
        return self._wellbeing.weights_between(start, end)

    def _sleep(self, start: date, end: date) -> list[float]:
        if self._wellbeing is None or not hasattr(self._wellbeing, "sleep_between"):
            return []
        return self._wellbeing.sleep_between(start, end)

    @staticmethod
    def session_counts(sessions: tuple[WeekSession, ...] | list[WeekSession]) -> dict[str, int]:
        done = [item for item in sessions if item.completed in {"completed", "partial"}]
        return {
            "bjj": sum(item.kind.startswith("bjj") or item.kind == "competition" for item in done),
            "strength": sum(item.kind.startswith("strength") for item in done),
            # Zone 2 sessions plus Strength A's easy-cardio finisher when it was done.
            "cardio": sum(item.kind in {"zone_2", "zone2"} for item in done) + sum(
                item.kind == "strength_a" and any(ex.name == "Easy cardio" and ex.done for ex in item.exercises)
                for item in done
            ),
        }

    def review_for(self, week_ending: date) -> WeeklyReview | None:
        with self._session_factory() as session:
            return session.scalars(select(WeeklyReview).where(WeeklyReview.week_ending == week_ending)).first()

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
        return f"{settings.public_base_url()}/daily/{day.isoformat()}"

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
        if current.weekday() != 0 or current.hour != 10:
            return None
        return current.date()

    def reminder_message(self, monday: date, daily_url: str) -> str:
        week_ending = monday - timedelta(days=1)
        average, count = cut_plan.seven_day_average(self._weights(week_ending - timedelta(days=6), week_ending), week_ending)
        target = round(sum(cut_plan.target_for(week_ending)) / 2, 1)
        weight = (
            f"Seven-day average {average:.1f} kg from {count} weigh-ins (trend target {target:.1f})."
            if average is not None else "No morning weigh-ins last week — log them on the daily page."
        )
        return telegram_message(f"Monday check-in. {weight}", daily_url)

    @staticmethod
    def notify_message(check_in: WeeklyCheckIn, daily_url: str) -> str:
        lines = [telegram_message("Monday check-in saved.", daily_url), WeeklyService.weight_line(check_in)]
        counts = check_in.counts
        lines.append(f"Done: BJJ {counts.get('bjj', 0)} · Strength {counts.get('strength', 0)} · Cardio {counts.get('cardio', 0)}.")
        if check_in.kcal_reason:
            lines.append(f"Food: {check_in.kcal_reason}")
        if check_in.division.get("note"):
            lines.append(check_in.division["note"])
        return "\n".join(lines)

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
    def weight_line(check_in: WeeklyCheckIn) -> str:
        if check_in.weight_kg is None:
            return "Weight: no morning weigh-ins last week."
        line = f"Seven-day average {check_in.weight_kg:.1f} kg"
        if check_in.weigh_ins:
            line += f" ({check_in.weigh_ins} weigh-ins)"
        delta = check_in.delta_kg
        if delta is None or check_in.previous_weight_kg is None:
            line += ", no previous week to compare"
        elif abs(delta) < 0.05:
            line += ", same as last week"
        else:
            line += f", {'up' if delta > 0 else 'down'} {abs(delta):.1f} kg from {check_in.previous_weight_kg:.1f}"
        if check_in.target_kg is not None:
            line += f". Trend target {check_in.target_kg:.1f} kg"
        if check_in.waist_cm is not None:
            line += f". Waist {check_in.waist_cm:.1f} cm"
        return line + "."

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
