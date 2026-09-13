from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import DailyWellbeingCheckIn, TrainingMetric, TrainingSession, WalkingPadSession
from app.database.session import SessionLocal


@dataclass(frozen=True)
class ProgressReport:
    period: str
    start: date
    end: date
    weight_kg: float | None
    weight_change_kg: float | None
    sober_days: int
    gym_sessions: int
    jiujitsu_sessions: int
    walk_minutes: float
    walk_distance_km: float
    steps: int
    strength_sessions: int = 0
    zone2_sessions: int = 0
    interval_sessions: int = 0
    grip_sessions: int = 0
    rest_days: int = 0
    sparring_rounds: int = 0
    average_sleep: float | None = None
    average_weight: float | None = None
    average_readiness: float | None = None
    skipped_workouts: int = 0
    skipped_reasons: tuple[str, ...] = ()
    conditioning_decay_percent: float | None = None

    @property
    def key(self) -> str:
        return f"{self.period.lower()}:{self.start.isoformat()}"

    @property
    def title(self) -> str:
        return f"{self.period} progress · {self.start.isoformat()} to {self.end.isoformat()}"


class ProgressReportService:
    def __init__(self, session_factory=SessionLocal, *, timezone_name: str | None = None) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(timezone_name or settings.timezone)

    def report(self, period: str, start: date, end: date) -> ProgressReport:
        start_utc = datetime.combine(start, time.min, self._timezone).astimezone(UTC)
        end_utc = datetime.combine(end + timedelta(days=1), time.min, self._timezone).astimezone(UTC)
        with self._session_factory() as session:
            wellbeing = list(session.scalars(
                select(DailyWellbeingCheckIn)
                .where(DailyWellbeingCheckIn.local_date <= end)
                .order_by(DailyWellbeingCheckIn.local_date)
            ).all())
            walks = list(session.scalars(
                select(WalkingPadSession)
                .where(WalkingPadSession.started_at >= start_utc)
                .where(WalkingPadSession.started_at < end_utc)
            ).all())
            training = list(session.scalars(
                select(TrainingSession)
                .where(TrainingSession.start_at >= start_utc)
                .where(TrainingSession.start_at < end_utc)
            ).all())
            training_ids = [row.id for row in training]
            metrics = list(session.scalars(
                select(TrainingMetric).where(TrainingMetric.session_id.in_(training_ids or [""]))
            ).all())

        in_period = [row for row in wellbeing if start <= row.local_date <= end]
        weights_through_end = [row for row in wellbeing if row.weight_kg is not None]
        weights_before = [row for row in wellbeing if row.local_date < start and row.weight_kg is not None]
        end_weight = weights_through_end[-1].weight_kg if weights_through_end else None
        start_weight = weights_before[-1].weight_kg if weights_before else (
            next((row.weight_kg for row in in_period if row.weight_kg is not None), None)
        )
        change = None if end_weight is None or start_weight is None else round(end_weight - start_weight, 1)
        completed = [row for row in training if row.status in {"completed", "partial", "competition", "recovery"}]
        sleeps = [row.sleep_hours for row in in_period if row.sleep_hours is not None]
        readiness = [row.readiness for row in in_period if row.readiness is not None]
        weights = [row.weight_kg for row in in_period if row.weight_kg is not None]
        metric_by_session: dict[str, list[TrainingMetric]] = {}
        for metric in metrics:
            if metric.metric_type.startswith("bike_") and metric.sequence is not None:
                metric_by_session.setdefault(metric.session_id, []).append(metric)
        decays: list[float] = []
        for values in metric_by_session.values():
            ordered = sorted(values, key=lambda item: item.sequence or 0)
            if len(ordered) >= 2 and ordered[0].value:
                decays.append((ordered[0].value - ordered[-1].value) / ordered[0].value * 100)
        return ProgressReport(
            period=period,
            start=start,
            end=end,
            weight_kg=end_weight,
            weight_change_kg=change,
            sober_days=sum(row.sober is True for row in in_period),
            gym_sessions=sum(row.planned_type.startswith("strength_") for row in completed),
            jiujitsu_sessions=sum(
                row.planned_type.startswith("bjj_") or row.planned_type == "competition"
                for row in completed
            ),
            walk_minutes=round(sum(row.duration_seconds for row in walks) / 60, 1),
            walk_distance_km=round(sum(row.distance_km for row in walks), 2),
            steps=sum(row.steps for row in walks),
            strength_sessions=sum(row.planned_type.startswith("strength_") for row in completed),
            zone2_sessions=sum(row.planned_type == "zone_2" for row in completed),
            interval_sessions=sum(row.planned_type == "strength_a" for row in completed),
            grip_sessions=sum(
                1 for row in completed
                if any(metric.metric_type == "grip_hold_seconds" and metric.session_id == row.id for metric in metrics)
            ),
            rest_days=sum(row.planned_type in {"rest", "recovery"} for row in completed),
            sparring_rounds=int(sum(metric.value for metric in metrics if metric.metric_type == "bjj_rounds")),
            average_sleep=round(sum(sleeps) / len(sleeps), 1) if sleeps else None,
            average_weight=round(sum(weights) / len(weights), 1) if weights else None,
            average_readiness=round(sum(readiness) / len(readiness), 1) if readiness else None,
            skipped_workouts=sum(row.status == "skipped" for row in training),
            skipped_reasons=tuple(row.notes for row in training if row.status == "skipped" and row.notes),
            conditioning_decay_percent=round(sum(decays) / len(decays), 1) if decays else None,
        )

    def completed_periods(self, today: date) -> list[ProgressReport]:
        this_week = today - timedelta(days=today.weekday())
        week_end = this_week - timedelta(days=1)
        week_start = week_end - timedelta(days=6)
        first_this_month = today.replace(day=1)
        month_end = first_this_month - timedelta(days=1)
        month_start = month_end.replace(day=1)
        return [
            self.report("Weekly", week_start, week_end),
            self.report("Monthly", month_start, month_end),
        ]
