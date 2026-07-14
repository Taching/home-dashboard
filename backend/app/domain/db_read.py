"""Date-scoped read-only export of dashboard SQLite data for OpenClaw/tools."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from app.core.settings import settings
from app.database.models import (
    CalendarBridgeEvent,
    ChiliNotifyDedupe,
    LightCommand,
    SensorReading,
    VoiceCommandLog,
    WalkingPadCollectorSync,
    WalkingPadSession,
    WaterPumpRun,
)
from app.database.session import SessionLocal


@dataclass(frozen=True)
class DbDayBounds:
    start: date
    end: date
    start_utc: datetime
    end_utc: datetime


class DbReadService:
    """Aggregate local-date slices of persisted dashboard tables.

    Secrets (Spotify OAuth tokens) are never included.
    """

    def __init__(self, session_factory=SessionLocal, timezone_name: str | None = None) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(timezone_name or settings.timezone)

    def snapshot_for_date(self, day: date) -> dict:
        return self.snapshot_for_range(day, day)

    def snapshot_for_range(self, start: date, end: date) -> dict:
        if end < start:
            raise ValueError("end date must be on or after start date")
        if (end - start).days > 62:
            raise ValueError("date range cannot exceed 62 days")

        bounds = self._bounds(start, end)
        with self._session_factory() as session:
            sensors = self._sensor_rows(session, bounds)
            walks = self._walk_rows(session, bounds)
            lights = self._light_rows(session, bounds)
            pumps = self._pump_rows(session, bounds)
            voice = self._voice_rows(session, bounds)
            calendar = self._calendar_rows(session, bounds)
            notifies = self._notify_rows(session, bounds)
            walk_sync = session.get(WalkingPadCollectorSync, "walkingpad")

        return {
            "timezone": str(self._timezone),
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "generated_at": datetime.now(UTC).isoformat(),
            "summary": {
                "sensor_reading_count": len(sensors),
                "sensor_avg_temperature_c": self._avg([row["temperature_c"] for row in sensors]),
                "sensor_avg_humidity_percent": self._avg([row["humidity_percent"] for row in sensors]),
                "walk_session_count": len(walks),
                "walk_total_minutes": round(sum(row["duration_seconds"] for row in walks) / 60, 1),
                "walk_total_distance_km": round(sum(row["distance_km"] for row in walks), 2),
                "walk_total_steps": sum(row["steps"] for row in walks),
                "walk_total_calories": round(sum(row["calories"] for row in walks), 1),
                "light_command_count": len(lights),
                "water_pump_run_count": len(pumps),
                "voice_command_count": len(voice),
                "calendar_event_count": len(calendar),
                "notify_dedupe_count": len(notifies),
            },
            "sensor_readings": sensors,
            "walkingpad_sessions": walks,
            "light_commands": lights,
            "water_pump_runs": pumps,
            "voice_command_logs": voice,
            "calendar_bridge_events": calendar,
            "chili_notify_dedupe": notifies,
            "meta": {
                "walkingpad_last_synced_at": (
                    self._iso(walk_sync.synced_at) if walk_sync is not None else None
                ),
                "excluded_tables": ["spotify_tokens", "spotify_devices"],
                "notes": (
                    "Dates are interpreted in the dashboard timezone. "
                    "Spotify OAuth tokens/devices are excluded."
                ),
            },
        }

    def _bounds(self, start: date, end: date) -> DbDayBounds:
        start_utc = datetime.combine(start, time.min, tzinfo=self._timezone).astimezone(UTC)
        end_utc = datetime.combine(end + timedelta(days=1), time.min, tzinfo=self._timezone).astimezone(UTC)
        return DbDayBounds(start=start, end=end, start_utc=start_utc, end_utc=end_utc)

    def _sensor_rows(self, session, bounds: DbDayBounds) -> list[dict]:
        rows = session.scalars(
            select(SensorReading)
            .where(SensorReading.recorded_at >= bounds.start_utc)
            .where(SensorReading.recorded_at < bounds.end_utc)
            .order_by(SensorReading.recorded_at)
        ).all()
        return [
            {
                "id": row.id,
                "recorded_at": self._iso(row.recorded_at),
                "temperature_c": row.temperature_c,
                "humidity_percent": row.humidity_percent,
            }
            for row in rows
        ]

    def _walk_rows(self, session, bounds: DbDayBounds) -> list[dict]:
        rows = session.scalars(
            select(WalkingPadSession)
            .where(WalkingPadSession.started_at < bounds.end_utc)
            .where(
                or_(
                    WalkingPadSession.ended_at.is_(None),
                    WalkingPadSession.ended_at > bounds.start_utc,
                )
            )
            .order_by(WalkingPadSession.started_at)
        ).all()
        return [
            {
                "id": row.id,
                "external_id": row.external_id,
                "started_at": self._iso(row.started_at),
                "ended_at": self._iso(row.ended_at) if row.ended_at else None,
                "duration_seconds": row.duration_seconds,
                "duration_minutes": round(row.duration_seconds / 60, 1),
                "distance_km": row.distance_km,
                "steps": row.steps,
                "calories": row.calories,
            }
            for row in rows
        ]

    def _light_rows(self, session, bounds: DbDayBounds) -> list[dict]:
        rows = session.scalars(
            select(LightCommand)
            .where(LightCommand.occurred_at >= bounds.start_utc)
            .where(LightCommand.occurred_at < bounds.end_utc)
            .order_by(LightCommand.occurred_at)
        ).all()
        return [
            {
                "id": row.id,
                "occurred_at": self._iso(row.occurred_at),
                "state": row.state,
                "source": row.source,
            }
            for row in rows
        ]

    def _pump_rows(self, session, bounds: DbDayBounds) -> list[dict]:
        rows = session.scalars(
            select(WaterPumpRun)
            .where(WaterPumpRun.occurred_at >= bounds.start_utc)
            .where(WaterPumpRun.occurred_at < bounds.end_utc)
            .order_by(WaterPumpRun.occurred_at)
        ).all()
        return [
            {
                "id": row.id,
                "occurred_at": self._iso(row.occurred_at),
                "source": row.source,
                "duration_seconds": row.duration_seconds,
                "result": row.result,
            }
            for row in rows
        ]

    def _voice_rows(self, session, bounds: DbDayBounds) -> list[dict]:
        rows = session.scalars(
            select(VoiceCommandLog)
            .where(VoiceCommandLog.occurred_at >= bounds.start_utc)
            .where(VoiceCommandLog.occurred_at < bounds.end_utc)
            .order_by(VoiceCommandLog.occurred_at)
        ).all()
        return [
            {
                "id": row.id,
                "occurred_at": self._iso(row.occurred_at),
                "transcript": row.transcript,
                "action": row.action,
                "status": row.status,
                "response_message": row.response_message,
                "wake_score": row.wake_score,
                "failure_stage": row.failure_stage,
            }
            for row in rows
        ]

    def _calendar_rows(self, session, bounds: DbDayBounds) -> list[dict]:
        rows = session.scalars(
            select(CalendarBridgeEvent)
            .where(CalendarBridgeEvent.start_at < bounds.end_utc)
            .where(CalendarBridgeEvent.end_at > bounds.start_utc)
            .order_by(CalendarBridgeEvent.start_at)
        ).all()
        return [
            {
                "id": row.id,
                "source": row.source,
                "external_id": row.external_id,
                "title": row.title,
                "start_at": self._iso(row.start_at),
                "end_at": self._iso(row.end_at),
                "is_all_day": row.is_all_day,
            }
            for row in rows
        ]

    def _notify_rows(self, session, bounds: DbDayBounds) -> list[dict]:
        rows = session.scalars(
            select(ChiliNotifyDedupe)
            .where(ChiliNotifyDedupe.sent_at >= bounds.start_utc)
            .where(ChiliNotifyDedupe.sent_at < bounds.end_utc)
            .order_by(ChiliNotifyDedupe.sent_at)
        ).all()
        return [
            {
                "dedupe_key": row.dedupe_key,
                "sent_at": self._iso(row.sent_at),
            }
            for row in rows
        ]

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()

    @staticmethod
    def _avg(values: list[float]) -> float | None:
        if not values:
            return None
        return round(sum(values) / len(values), 2)
