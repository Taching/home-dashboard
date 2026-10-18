"""Garmin Connect (Fenix 8 Pro) sync.

Uses the unofficial `garminconnect` library — Garmin's official API does not
accept personal apps. Tokens come from a one-time interactive login
(`python -m app.jobs.garmin_login`, handles MFA) and are refreshed by the
library. Everything here is read-only context for the daily page and the
Monday check-in; it never gates the scheduler (no readiness form, see
docs/agent-handoff-chili.md).
"""
from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import GarminDailySnapshot
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)


def _default_client_factory():
    from garminconnect import Garmin

    client = Garmin(settings.garmin_email, settings.garmin_password)
    client.login(tokenstore=settings.garmin_token_dir)
    return client


def _int(value) -> int | None:
    try:
        return None if value is None else int(round(float(value)))
    except (TypeError, ValueError):
        return None


def parse_day(summary: dict | None, sleep: dict | None, hrv: dict | None, activities: list | None) -> dict:
    summary = summary or {}
    sleep_dto = (sleep or {}).get("dailySleepDTO") or {}
    hrv_summary = (hrv or {}).get("hrvSummary") or {}
    return {
        "steps": _int(summary.get("totalSteps")),
        "resting_hr": _int(summary.get("restingHeartRate")),
        "body_battery_high": _int(summary.get("bodyBatteryHighestValue")),
        "body_battery_low": _int(summary.get("bodyBatteryLowestValue")),
        "body_battery_latest": _int(summary.get("bodyBatteryMostRecentValue")),
        "stress_avg": _int(summary.get("averageStressLevel")) if (summary.get("averageStressLevel") or 0) >= 0 else None,
        "sleep_seconds": _int(sleep_dto.get("sleepTimeSeconds")),
        "sleep_score": _int(((sleep_dto.get("sleepScores") or {}).get("overall") or {}).get("value")),
        "hrv_last_night": _int(hrv_summary.get("lastNightAvg")),
        "hrv_status": (str(hrv_summary["status"]).lower() if hrv_summary.get("status") else None),
        "activities": [
            {
                "name": item.get("activityName") or "Activity",
                "type": ((item.get("activityType") or {}).get("typeKey") or "other"),
                "start_local": item.get("startTimeLocal"),
                "duration_min": round(float(item.get("duration") or 0) / 60),
                "avg_hr": _int(item.get("averageHR")),
                "distance_km": round(float(item.get("distance") or 0) / 1000, 2) or None,
            }
            for item in (activities or [])
        ],
    }


LOW_HRV_STATUSES = {"low", "unbalanced", "poor"}
SHORT_SLEEP_HOURS = 6.0
LOW_BODY_BATTERY = 30


def watch_line(snapshot: dict | None) -> str | None:
    """One-line morning summary, or None until last night's sleep has synced."""
    if not snapshot or snapshot.get("sleep_hours") is None:
        return None
    sleep = f"{snapshot['sleep_hours']:.1f} h sleep"
    if snapshot.get("sleep_score") is not None:
        sleep += f" ({snapshot['sleep_score']})"
    parts = [sleep]
    if snapshot.get("resting_hr") is not None:
        parts.append(f"RHR {snapshot['resting_hr']}")
    if snapshot.get("hrv_last_night") is not None:
        hrv = f"HRV {snapshot['hrv_last_night']}"
        parts.append(f"{hrv} {snapshot['hrv_status']}" if snapshot.get("hrv_status") else hrv)
    if snapshot.get("body_battery_high") is not None:
        parts.append(f"Body Battery {snapshot['body_battery_high']}")
    return "Watch: " + " · ".join(parts)


def recovery_hint(snapshot: dict | None, *, rest_day: bool) -> str | None:
    """One gentle sentence when the night looks rough. Words only: the plan
    never changes because of the watch."""
    if not snapshot:
        return None
    flags: list[str] = []
    sleep = snapshot.get("sleep_hours")
    if sleep is not None and sleep < SHORT_SLEEP_HOURS:
        flags.append("short night")
    battery = snapshot.get("body_battery_high")
    if battery is not None and battery < LOW_BODY_BATTERY:
        flags.append(f"Body Battery only {battery}")
    if snapshot.get("hrv_status") in LOW_HRV_STATUSES:
        flags.append(f"HRV {snapshot['hrv_status']}")
    if not flags:
        return None
    lead = ", ".join(flags)
    lead = lead[0].upper() + lead[1:]
    if rest_day:
        return f"{lead} — good day for the rest. Get the walk in and aim for an early night."
    return f"{lead} — warm up longer and do not chase extra volume. The session stays as planned."


class GarminService:
    def __init__(
        self,
        session_factory=SessionLocal,
        *,
        client_factory: Callable[[], object] | None = None,
        wellbeing=None,
    ) -> None:
        self._session_factory = session_factory
        self._client_factory = client_factory or _default_client_factory
        self._client = None
        self._wellbeing = wellbeing
        self._timezone = ZoneInfo(settings.timezone)
        self.last_error: str | None = None

    def configured(self) -> bool:
        if self._client_factory is not _default_client_factory:
            return True
        token_dir = Path(settings.garmin_token_dir)
        has_tokens = token_dir.is_dir() and any(token_dir.iterdir())
        return has_tokens or bool(settings.garmin_email and settings.garmin_password)

    def sync_recent(self, now: datetime | None = None) -> int:
        """Today and yesterday: last night's sleep/HRV land on today, and
        yesterday's final step count settles after midnight."""
        if not self.configured():
            return 0
        today = self._local_today(now)
        synced = 0
        for day in (today - timedelta(days=1), today):
            self.sync_day(day, now=now)
            synced += 1
        return synced

    def sync_day(self, day: date, *, now: datetime | None = None) -> dict:
        client = self._connect()
        cdate = day.isoformat()
        try:
            values = parse_day(
                client.get_user_summary(cdate),
                client.get_sleep_data(cdate),
                client.get_hrv_data(cdate),
                client.get_activities_by_date(cdate, cdate),
            )
        except Exception as error:
            self.last_error = f"{type(error).__name__}: {error}"[:300]
            if "auth" in type(error).__name__.lower():
                self._client = None
            raise
        self.last_error = None
        stamped = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            row = session.get(GarminDailySnapshot, day)
            if row is None:
                row = GarminDailySnapshot(local_date=day, synced_at=stamped)
                session.add(row)
            for key, value in values.items():
                setattr(row, key, value)
            row.synced_at = stamped
            session.commit()
        self._fill_sleep(day, values.get("sleep_seconds"))
        self._persist_tokens(client)
        return values

    def snapshot(self, day: date) -> dict | None:
        with self._session_factory() as session:
            row = session.get(GarminDailySnapshot, day)
            if row is None:
                return None
            return self._as_dict(row)

    def steps_for(self, day: date) -> int | None:
        snap = self.snapshot(day)
        return None if snap is None else snap.get("steps")

    def week_summary(self, start: date, end: date) -> dict | None:
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(GarminDailySnapshot)
                .where(GarminDailySnapshot.local_date >= start)
                .where(GarminDailySnapshot.local_date <= end)
            ).all())
        if not rows:
            return None

        def avg(values: list) -> float | None:
            present = [value for value in values if value is not None]
            return round(mean(present), 1) if present else None

        steps = [row.steps for row in rows if row.steps is not None]
        return {
            "days": len(rows),
            "resting_hr": avg([row.resting_hr for row in rows]),
            "hrv": avg([row.hrv_last_night for row in rows]),
            "sleep_score": avg([row.sleep_score for row in rows]),
            "sleep_hours": avg([row.sleep_seconds / 3600 if row.sleep_seconds else None for row in rows]),
            "body_battery_high": avg([row.body_battery_high for row in rows]),
            "steps": round(mean(steps)) if steps else None,
        }

    def _connect(self):
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    def _fill_sleep(self, day: date, sleep_seconds: int | None) -> None:
        # The watch fills the daily page's sleep field only when it is empty;
        # a number Toshi typed in himself always wins.
        if not sleep_seconds or self._wellbeing is None:
            return
        entry = self._wellbeing.entry(day) or {}
        if entry.get("sleep_hours") is not None:
            return
        self._wellbeing.record(day, sleep_hours=round(sleep_seconds / 3600, 1), source="garmin")

    @staticmethod
    def _persist_tokens(client) -> None:
        inner = getattr(client, "client", None)
        if inner is None or not hasattr(inner, "dump"):
            return
        with contextlib.suppress(Exception):
            inner.dump(settings.garmin_token_dir)

    @staticmethod
    def _as_dict(row: GarminDailySnapshot) -> dict:
        return {
            "date": row.local_date.isoformat(),
            "synced_at": GarminService._as_utc(row.synced_at).isoformat(),
            "steps": row.steps,
            "sleep_hours": round(row.sleep_seconds / 3600, 1) if row.sleep_seconds else None,
            "sleep_score": row.sleep_score,
            "resting_hr": row.resting_hr,
            "hrv_last_night": row.hrv_last_night,
            "hrv_status": row.hrv_status,
            "body_battery_high": row.body_battery_high,
            "body_battery_low": row.body_battery_low,
            "body_battery_latest": row.body_battery_latest,
            "stress_avg": row.stress_avg,
            "activities": row.activities or [],
        }

    def _local_today(self, now: datetime | None) -> date:
        return self._as_utc(now or datetime.now(UTC)).astimezone(self._timezone).date()

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
