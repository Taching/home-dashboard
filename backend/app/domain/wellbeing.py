from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import DailyWellbeingCheckIn, TrainingSession
from app.database.session import SessionLocal
from app.domain import cut_plan
from app.domain.training.phases import phase_for_date
from app.domain.training.policy import weekly_targets
from app.domain.telegram_text import telegram_message
from app.domain.training.types import CAMPAIGN_PHASES

COMPLETED_TRAINING = {"completed", "partial", "competition"}


@dataclass(frozen=True)
class SoberNudge:
    day: date
    kind: Literal["ask", "followup"]
    message: str
    dedupe_key: str


@dataclass(frozen=True)
class WellbeingSummary:
    sober_days: int
    workouts_this_week: int
    gym_this_week: int
    jiujitsu_this_week: int
    gym_weekly_goal: int
    jiujitsu_weekly_goal: int
    week_start: date
    latest_checkin_date: date | None
    checkin_stale: bool
    current_weight_kg: float | None
    weight_goal_kg: float
    latest_weight_date: date | None
    weight_7d_average_kg: float | None = None
    weight_target_kg: float | None = None


class WellbeingService:
    def __init__(
        self,
        session_factory=SessionLocal,
        *,
        timezone_name: str | None = None,
        sober_baseline_date: date | None = None,
        sober_baseline_days: int | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(timezone_name or settings.timezone)
        self._baseline_date = sober_baseline_date or date.fromisoformat(settings.sober_baseline_date)
        self._baseline_days = (
            sober_baseline_days
            if sober_baseline_days is not None
            else settings.sober_baseline_days
        )

    def record(
        self,
        local_date: date,
        *,
        trained: bool | None = None,
        gym: bool | None = None,
        jiujitsu: bool | None = None,
        sober: bool | None = None,
        weight_kg: float | None = None,
        sleep_hours: float | None = None,
        sleep_quality: int | None = None,
        fatigue: int | None = None,
        soreness: int | None = None,
        grip_fatigue: int | None = None,
        pain: bool | None = None,
        pain_notes: str | None = None,
        readiness: int | None = None,
        fatigue_state: str | None = None,
        daily_notes: str | None = None,
        source: str = "openclaw",
        now: datetime | None = None,
    ) -> WellbeingSummary:
        values = {
            "trained": trained, "gym": gym, "jiujitsu": jiujitsu, "sober": sober,
            "weight_kg": weight_kg, "sleep_hours": sleep_hours, "sleep_quality": sleep_quality,
            "fatigue": fatigue, "soreness": soreness, "grip_fatigue": grip_fatigue,
            "pain": pain, "pain_notes": pain_notes, "readiness": readiness,
            "fatigue_state": fatigue_state, "daily_notes": daily_notes,
        }
        if all(value is None for value in values.values()):
            raise ValueError("Provide at least one check-in answer.")
        updated_at = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            row = session.get(DailyWellbeingCheckIn, local_date)
            if row is None:
                row = DailyWellbeingCheckIn(
                    local_date=local_date,
                    trained=trained,
                    gym=gym,
                    jiujitsu=jiujitsu,
                    sober=sober,
                    weight_kg=weight_kg, sleep_hours=sleep_hours, sleep_quality=sleep_quality,
                    fatigue=fatigue, soreness=soreness, grip_fatigue=grip_fatigue,
                    pain=pain, pain_notes=pain_notes, readiness=readiness,
                    fatigue_state=fatigue_state, daily_notes=daily_notes,
                    updated_at=updated_at,
                    source=source,
                )
                session.add(row)
            else:
                for key, value in values.items():
                    if value is not None:
                        setattr(row, key, value)
                row.updated_at = updated_at
                row.source = source
            if row.gym is True or row.jiujitsu is True:
                row.trained = True
            elif gym is not None and jiujitsu is not None:
                row.trained = False
            session.commit()
        return self.summary(updated_at)

    def weights_between(self, start: date, end: date) -> dict[date, float]:
        """Morning weigh-ins by local date, inclusive."""
        with self._session_factory() as session:
            rows = session.execute(
                select(DailyWellbeingCheckIn.local_date, DailyWellbeingCheckIn.weight_kg)
                .where(DailyWellbeingCheckIn.local_date >= start)
                .where(DailyWellbeingCheckIn.local_date <= end)
                .where(DailyWellbeingCheckIn.weight_kg.is_not(None))
            ).all()
        return {row[0]: float(row[1]) for row in rows}

    def history(self, days: int = 90, now: datetime | None = None) -> dict:
        span = max(7, min(days, 400))
        today = self._as_utc(now or datetime.now(UTC)).astimezone(self._timezone).date()
        start = today - timedelta(days=span - 1)
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(DailyWellbeingCheckIn)
                .where(DailyWellbeingCheckIn.local_date <= today)
                .order_by(DailyWellbeingCheckIn.local_date)
            ).all())
        weights = [
            {"date": row.local_date.isoformat(), "kg": row.weight_kg}
            for row in rows
            if row.weight_kg is not None and start <= row.local_date <= today
        ]
        drank = {
            row.local_date
            for row in rows
            if row.sober is False and self._baseline_date < row.local_date <= today
        }
        sober: list[dict] = []
        streak = self._baseline_days
        day = self._baseline_date + timedelta(days=1)
        while day <= today:
            drank_today = day in drank
            streak = 0 if drank_today else streak + 1
            if day >= start:
                sober.append({"date": day.isoformat(), "days": streak, "drank": drank_today})
            day += timedelta(days=1)
        return {
            "start": start.isoformat(),
            "end": today.isoformat(),
            "weights": weights,
            "sober": sober,
            "sober_days": streak if today > self._baseline_date else self._baseline_days,
            "weight_goal_kg": settings.weight_goal_kg,
        }

    def sleep_between(self, start: date, end: date) -> list[float]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(DailyWellbeingCheckIn.sleep_hours)
                .where(DailyWellbeingCheckIn.local_date >= start)
                .where(DailyWellbeingCheckIn.local_date <= end)
                .where(DailyWellbeingCheckIn.sleep_hours.is_not(None))
            ).all()
        return [float(value) for value in rows]

    def entry(self, local_date: date) -> dict | None:
        with self._session_factory() as session:
            row = session.get(DailyWellbeingCheckIn, local_date)
            if row is None:
                return None
            result = {
                key: getattr(row, key)
                for key in (
                    "trained", "gym", "jiujitsu", "sober", "weight_kg", "sleep_hours",
                    "sleep_quality", "fatigue", "soreness", "grip_fatigue", "pain",
                    "pain_notes", "readiness", "fatigue_state", "daily_notes", "advice",
                    "chili_reply", "chili_delivery",
                )
            }
            result["updated_at"] = self._as_utc(row.updated_at).isoformat()
            return result

    def store_advice(self, local_date: date, advice: str, *, now: datetime | None = None) -> None:
        updated_at = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            row = session.get(DailyWellbeingCheckIn, local_date)
            if row is None:
                row = DailyWellbeingCheckIn(
                    local_date=local_date, updated_at=updated_at, source="daily-page",
                )
                session.add(row)
            row.advice = advice
            row.updated_at = updated_at
            session.commit()

    def store_chili_close(
        self,
        local_date: date,
        reply: str,
        delivery: str | None,
        *,
        now: datetime | None = None,
    ) -> None:
        updated_at = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            row = session.get(DailyWellbeingCheckIn, local_date)
            if row is None:
                row = DailyWellbeingCheckIn(
                    local_date=local_date, updated_at=updated_at, source="daily-page",
                )
                session.add(row)
            row.chili_reply = reply
            row.chili_delivery = delivery
            row.advice = reply
            row.updated_at = updated_at
            session.commit()

    def summary(self, now: datetime | None = None) -> WellbeingSummary:
        current = self._as_utc(now or datetime.now(UTC)).astimezone(self._timezone)
        today = current.date()
        week_start = today - timedelta(days=today.weekday())
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(DailyWellbeingCheckIn)
                .where(DailyWellbeingCheckIn.local_date <= today)
                .order_by(DailyWellbeingCheckIn.local_date)
            ).all())

        sober_days = self._sober_streak(rows, today)

        workouts, gym, jiujitsu = self._session_counts(week_start, today)
        average, _ = cut_plan.seven_day_average(
            {row.local_date: row.weight_kg for row in rows if row.weight_kg is not None}, today,
        )
        target = cut_plan.target_for(today)
        phase = phase_for_date(today)
        targets = weekly_targets(phase) if phase in CAMPAIGN_PHASES else {}
        checkin_rows = [
            row for row in rows
            if any(value is not None for value in (row.trained, row.gym, row.jiujitsu, row.sober))
        ]
        weight_rows = [row for row in rows if row.weight_kg is not None]
        latest = checkin_rows[-1].local_date if checkin_rows else None
        # The nightly question runs at 21:00. Allow an hour for the reply before
        # considering today's entry missed; before then, yesterday is current.
        expected_checkin_date = today if current.hour >= 22 else today - timedelta(days=1)
        return WellbeingSummary(
            sober_days=sober_days,
            workouts_this_week=workouts,
            gym_this_week=gym,
            jiujitsu_this_week=jiujitsu,
            gym_weekly_goal=targets.get("strength") or settings.gym_weekly_goal,
            jiujitsu_weekly_goal=targets.get("bjj") or settings.jiujitsu_weekly_goal,
            week_start=week_start,
            latest_checkin_date=latest,
            checkin_stale=latest is None or latest < expected_checkin_date,
            current_weight_kg=weight_rows[-1].weight_kg if weight_rows else None,
            weight_goal_kg=settings.weight_goal_kg,
            latest_weight_date=weight_rows[-1].local_date if weight_rows else None,
            weight_7d_average_kg=average,
            weight_target_kg=round(sum(target) / 2, 1),
        )

    def _sober_streak(self, rows: list[DailyWellbeingCheckIn], today: date) -> int:
        """Count every day after the baseline. Only an explicit drink resets it."""
        drank = {
            row.local_date
            for row in rows
            if row.sober is False and self._baseline_date < row.local_date <= today
        }
        sober_days = self._baseline_days
        day = self._baseline_date + timedelta(days=1)
        while day <= today:
            sober_days = 0 if day in drank else sober_days + 1
            day += timedelta(days=1)
        return sober_days

    def sober_logged(self, local_date: date) -> bool:
        entry = self.entry(local_date)
        return bool(entry) and entry.get("sober") is not None

    def sober_nudges(self, now: datetime | None = None) -> list[SoberNudge]:
        current = self._as_utc(now or datetime.now(UTC)).astimezone(self._timezone)
        today = current.date()
        yesterday = today - timedelta(days=1)
        nudges: list[SoberNudge] = []
        if current.hour >= 21 and not self.sober_logged(today):
            nudges.append(self._sober_nudge(today, "ask"))
        return nudges

    def _sober_nudge(self, day: date, kind: Literal["ask", "followup"]) -> SoberNudge:
        message = telegram_message(
            "The streak keeps going. Open this only if you drank.",
            f"{settings.public_base_url()}/sober",
        )
        return SoberNudge(
            day=day,
            kind=kind,
            message=message,
            dedupe_key=f"sober:{kind}:{day.isoformat()}",
        )

    def _session_counts(self, week_start: date, today: date) -> tuple[int, int, int]:
        start = datetime.combine(week_start, time.min, self._timezone).astimezone(UTC)
        end = datetime.combine(today + timedelta(days=1), time.min, self._timezone).astimezone(UTC)
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(TrainingSession)
                .where(TrainingSession.start_at >= start)
                .where(TrainingSession.start_at < end)
                .where(TrainingSession.status.in_(COMPLETED_TRAINING))
            ).all())
        gym = sum(1 for row in rows if (row.planned_type or "").startswith("strength_"))
        jiujitsu = sum(
            1 for row in rows
            if (row.planned_type or "").startswith("bjj_") or row.planned_type == "competition"
        )
        extra = sum(1 for row in rows if row.planned_type in {"zone_2", "grip"})
        return gym + jiujitsu + extra, gym, jiujitsu

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
