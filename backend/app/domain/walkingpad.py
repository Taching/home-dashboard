from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import WalkingPadCollectorSync, WalkingPadSession
from app.database.session import SessionLocal
from app.domain.calendar_bridge import CalendarEvent

WALKINGPAD_SOURCE = "walkingpad"
STALE_AFTER = timedelta(minutes=15)
WalkingPadStatus = Literal["not_configured", "ready", "unavailable", "walking"]


@dataclass(frozen=True)
class WalkingPadActiveSession:
    external_id: str
    started_at: datetime
    duration_seconds: int
    distance_km: float
    steps: int
    calories: float


@dataclass(frozen=True)
class WalkingPadTodaySnapshot:
    status: WalkingPadStatus
    synced_at: datetime | None
    total_minutes: float
    total_distance_km: float
    total_steps: int
    total_calories: float
    goal_minutes: int
    goal_distance_km: float
    session_count: int
    active_session: WalkingPadActiveSession | None
    goal_met: bool


@dataclass(frozen=True)
class WalkReminder:
    active: bool
    message: str
    dedupe_key: str


class WalkingPadService:
    def __init__(self, session_factory=SessionLocal, bridge_token: str | None = None) -> None:
        self._session_factory = session_factory
        self._bridge_token = bridge_token
        self._timezone = ZoneInfo(settings.timezone)

    def configured(self) -> bool:
        token = self._bridge_token if self._bridge_token is not None else settings.walkingpad_bridge_token
        return bool(token)

    def sync_session(
        self,
        *,
        external_id: str,
        started_at: datetime,
        ended_at: datetime | None,
        duration_seconds: int,
        distance_km: float,
        steps: int,
        calories: float,
        synced_at: datetime,
    ) -> None:
        started_at = self._as_utc(started_at)
        ended_at = self._as_utc(ended_at) if ended_at is not None else None
        synced_at = self._as_utc(synced_at)
        with self._session_factory() as session:
            row = session.scalar(
                select(WalkingPadSession).where(WalkingPadSession.external_id == external_id)
            )
            if row is None:
                session.add(
                    WalkingPadSession(
                        external_id=external_id,
                        started_at=started_at,
                        ended_at=ended_at,
                        duration_seconds=duration_seconds,
                        distance_km=distance_km,
                        steps=steps,
                        calories=calories,
                    )
                )
            else:
                row.started_at = started_at
                row.ended_at = ended_at
                row.duration_seconds = duration_seconds
                row.distance_km = distance_km
                row.steps = steps
                row.calories = calories
            sync = session.get(WalkingPadCollectorSync, WALKINGPAD_SOURCE)
            if sync is None:
                session.add(WalkingPadCollectorSync(source=WALKINGPAD_SOURCE, synced_at=synced_at))
            else:
                sync.synced_at = synced_at
            session.commit()

    def today(self, now: datetime | None = None) -> WalkingPadTodaySnapshot:
        current = self._as_utc(now or datetime.now(UTC))
        if not self.configured():
            return self._empty_snapshot("not_configured")
        synced_at = self._last_synced_at()
        sessions = self._sessions_for_local_date(current)
        active = next((session for session in sessions if session.ended_at is None), None)
        completed = [session for session in sessions if session.ended_at is not None]
        total_seconds = sum(session.duration_seconds for session in sessions)
        total_distance = sum(session.distance_km for session in sessions)
        total_steps = sum(session.steps for session in sessions)
        total_calories = sum(session.calories for session in sessions)
        goal_minutes = settings.walkingpad_goal_minutes
        goal_distance = settings.walkingpad_goal_distance_km
        goal_met = (total_seconds / 60) >= goal_minutes and total_distance >= goal_distance
        status = self._resolve_status(synced_at, active is not None, current)
        active_session = None
        if active is not None:
            active_session = WalkingPadActiveSession(
                external_id=active.external_id,
                started_at=active.started_at,
                duration_seconds=active.duration_seconds,
                distance_km=active.distance_km,
                steps=active.steps,
                calories=active.calories,
            )
        return WalkingPadTodaySnapshot(
            status=status,
            synced_at=synced_at,
            total_minutes=round(total_seconds / 60, 1),
            total_distance_km=round(total_distance, 2),
            total_steps=total_steps,
            total_calories=round(total_calories, 1),
            goal_minutes=goal_minutes,
            goal_distance_km=goal_distance,
            session_count=len(completed) + (1 if active else 0),
            active_session=active_session,
            goal_met=goal_met,
        )

    def reminder(
        self,
        calendar_events: list[CalendarEvent],
        now: datetime | None = None,
    ) -> WalkReminder:
        current = self._as_utc(now or datetime.now(UTC))
        inactive = WalkReminder(active=False, message="", dedupe_key="")
        if not self.configured():
            return inactive
        snapshot = self.today(current)
        if snapshot.goal_met:
            return inactive
        local_now = current.astimezone(self._timezone)
        if not settings.walkingpad_reminder_start_hour <= local_now.hour < settings.walkingpad_reminder_end_hour:
            return inactive
        next_event = self._next_timed_event(calendar_events, current)
        minutes_until = self._minutes_until_next_event(local_now, next_event)
        if minutes_until < settings.walkingpad_min_gap_before_meeting_min:
            return inactive
        if minutes_until < settings.walkingpad_min_session_minutes:
            return inactive
        local_date = local_now.date().isoformat()
        next_key = next_event.external_id if next_event else "end-of-day"
        dedupe_key = f"walk:window:{local_date}:{next_key}"
        walked_min = int(snapshot.total_minutes)
        goal_min = snapshot.goal_minutes
        if next_event is not None:
            title = next_event.title
            message = (
                f"You've walked {walked_min} of {goal_min} minutes today. "
                f"You have about {minutes_until} minutes before {title} — good time for a walk."
            )
        else:
            message = (
                f"You've walked {walked_min} of {goal_min} minutes today. "
                f"You have {minutes_until} minutes left in your walk window today."
            )
        return WalkReminder(active=True, message=message, dedupe_key=dedupe_key)

    def context_lines(
        self,
        calendar_events: list[CalendarEvent],
        now: datetime | None = None,
    ) -> list[str]:
        current = self._as_utc(now or datetime.now(UTC))
        snapshot = self.today(current)
        if snapshot.status == "not_configured":
            return ["- Walking: not configured."]
        synced = snapshot.synced_at.isoformat() if snapshot.synced_at else "never"
        activity = "walking now" if snapshot.active_session else "idle"
        lines = [
            (
                f"- Walking: {snapshot.status}; synced at {synced}; "
                f"today {snapshot.total_minutes}/{snapshot.goal_minutes} min and "
                f"{snapshot.total_distance_km}/{snapshot.goal_distance_km} km; "
                f"{snapshot.session_count} session(s); {activity}."
            ),
            f"- Walking goal: {'met' if snapshot.goal_met else 'not yet met'}.",
        ]
        reminder = self.reminder(calendar_events, current)
        if reminder.active:
            lines.append(f"- Walk reminder: {reminder.message}")
        next_event = self._next_timed_event(calendar_events, current)
        if next_event is not None:
            local_start = next_event.start_at.astimezone(self._timezone)
            minutes_until = max(0, int((next_event.start_at - current).total_seconds() // 60))
            lines.append(
                f"- Next meeting: {next_event.title} at {local_start.strftime('%H:%M')}; "
                f"{minutes_until} min away."
            )
        return lines

    def _empty_snapshot(self, status: WalkingPadStatus) -> WalkingPadTodaySnapshot:
        return WalkingPadTodaySnapshot(
            status=status,
            synced_at=None,
            total_minutes=0.0,
            total_distance_km=0.0,
            total_steps=0,
            total_calories=0.0,
            goal_minutes=settings.walkingpad_goal_minutes,
            goal_distance_km=settings.walkingpad_goal_distance_km,
            session_count=0,
            active_session=None,
            goal_met=False,
        )

    def _resolve_status(
        self,
        synced_at: datetime | None,
        has_active: bool,
        now: datetime,
    ) -> WalkingPadStatus:
        if has_active:
            return "walking"
        if synced_at is None:
            return "ready"
        if now - synced_at > STALE_AFTER:
            return "unavailable"
        return "ready"

    def _last_synced_at(self) -> datetime | None:
        with self._session_factory() as session:
            row = session.get(WalkingPadCollectorSync, WALKINGPAD_SOURCE)
            if row is None:
                return None
            return self._as_utc(row.synced_at)

    def _sessions_for_local_date(self, now: datetime) -> list[WalkingPadSession]:
        local_date = now.astimezone(self._timezone).date()
        start, end = self._local_day_bounds(local_date)
        with self._session_factory() as session:
            rows = session.scalars(
                select(WalkingPadSession)
                .where(WalkingPadSession.started_at < end)
                .where(
                    (WalkingPadSession.ended_at.is_(None))
                    | (WalkingPadSession.ended_at > start)
                )
                .order_by(WalkingPadSession.started_at)
            ).all()
            return list(rows)

    def _local_day_bounds(self, local_date: date) -> tuple[datetime, datetime]:
        start = datetime.combine(local_date, time.min, tzinfo=self._timezone).astimezone(UTC)
        end = datetime.combine(local_date, time.max, tzinfo=self._timezone).astimezone(UTC)
        return start, end

    @staticmethod
    def _next_timed_event(events: list[CalendarEvent], now: datetime) -> CalendarEvent | None:
        upcoming = [
            event for event in events
            if not event.is_all_day and event.start_at > now
        ]
        upcoming.sort(key=lambda event: event.start_at)
        return upcoming[0] if upcoming else None

    def _minutes_until_next_event(
        self,
        local_now: datetime,
        next_event: CalendarEvent | None,
    ) -> int:
        if next_event is not None:
            delta = next_event.start_at.astimezone(self._timezone) - local_now
            return max(0, int(delta.total_seconds() // 60))
        end = datetime.combine(
            local_now.date(),
            time(hour=settings.walkingpad_reminder_end_hour),
            tzinfo=self._timezone,
        )
        if local_now >= end:
            return 0
        return max(0, int((end - local_now).total_seconds() // 60))

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
