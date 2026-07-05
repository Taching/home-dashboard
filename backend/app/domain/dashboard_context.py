from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.core.settings import settings
from app.domain.calendar_bridge import CalendarEvent
from app.domain.lights import LightSnapshot
from app.domain.notion import NotionStatus, NotionTask
from app.domain.sensors import Reading


class WalkingPadContextService(Protocol):
    def context_lines(self, calendar_events: list[CalendarEvent], now: datetime | None = None) -> list[str]: ...


class SensorContextService(Protocol):
    def current(self) -> Reading | None: ...
    def status(self) -> str: ...


class LightContextService(Protocol):
    def snapshot(self) -> LightSnapshot: ...


class CalendarContextService(Protocol):
    def today(self) -> tuple[str, datetime | None, list[CalendarEvent]]: ...

    def upcoming(self, days: int) -> tuple[str, datetime | None, list[CalendarEvent]]: ...


class NotionContextService(Protocol):
    def today(self) -> tuple[NotionStatus, datetime | None, list[NotionTask]]: ...


class SpotifyContextService(Protocol):
    def now_playing(self) -> Mapping[str, object]: ...


class DashboardContextProvider:
    CALENDAR_LOOKAHEAD_DAYS = 14
    MAX_EVENTS_PER_DAY = 8

    def __init__(
        self,
        *,
        sensor_service: SensorContextService,
        light_service: LightContextService,
        calendar_service: CalendarContextService,
        notion_service: NotionContextService,
        spotify_service: SpotifyContextService,
        walkingpad_service: WalkingPadContextService | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._sensor_service = sensor_service
        self._light_service = light_service
        self._calendar_service = calendar_service
        self._notion_service = notion_service
        self._spotify_service = spotify_service
        self._walkingpad_service = walkingpad_service
        self._now = now or (lambda: datetime.now(UTC))

    def __call__(self) -> str:
        lines = [
            "Dashboard data snapshot:",
            f"- Snapshot time: {self._now().isoformat()}",
        ]
        lines.extend(self._sensor_lines())
        lines.extend(self._light_lines())
        lines.extend(self._calendar_lines())
        lines.extend(self._walking_lines())
        lines.extend(self._task_lines())
        lines.extend(self._spotify_lines())
        return "\n".join(lines)

    def _sensor_lines(self) -> list[str]:
        try:
            reading = self._sensor_service.current()
            status = self._sensor_service.status()
            if reading is None:
                return [f"- Temperature: unavailable; sensor status {status}."]
            return [
                (
                    f"- Temperature: {reading.temperature_c} C; humidity: "
                    f"{reading.humidity_percent}%; recorded at {reading.recorded_at.isoformat()}; "
                    f"sensor status {status}."
                )
            ]
        except Exception:
            return ["- Temperature: unavailable."]

    def _light_lines(self) -> list[str]:
        try:
            light = self._light_service.snapshot()
            updated = light.last_command_at.isoformat() if light.last_command_at else "unknown"
            available = "available" if light.available else "unavailable"
            return [
                (
                    f"- Light: last command {light.last_command_state}; "
                    f"last changed at {updated}; BroadLink {available}."
                )
            ]
        except Exception:
            return ["- Light: unavailable."]

    def _calendar_lines(self) -> list[str]:
        try:
            status, synced_at, events = self._calendar_service.upcoming(self.CALENDAR_LOOKAHEAD_DAYS)
            synced = synced_at.isoformat() if synced_at else "never"
            tz = ZoneInfo(settings.timezone)
            today = self._now().astimezone(tz).date()
            weekday = today.strftime("%A")
            lines = [
                (
                    f"- Calendar: {status}; synced at {synced}; local date today is "
                    f"{today.isoformat()} ({weekday}); {self.CALENDAR_LOOKAHEAD_DAYS}-day schedule:"
                ),
            ]
            grouped = self._group_events_by_local_date(events, tz)
            for offset in range(self.CALENDAR_LOOKAHEAD_DAYS):
                day = today + timedelta(days=offset)
                day_events = grouped.get(day, [])
                day_label = day.strftime("%A")
                lines.append(f"  - {day.isoformat()} ({day_label}): {len(day_events)} event(s).")
                for event in day_events[: self.MAX_EVENTS_PER_DAY]:
                    lines.append(f"    - {event.title}: {self._format_event_time(event, tz)}.")
                if len(day_events) > self.MAX_EVENTS_PER_DAY:
                    lines.append(f"    - {len(day_events) - self.MAX_EVENTS_PER_DAY} more on this day omitted.")
            return lines
        except Exception:
            return ["- Calendar: unavailable."]

    def _walking_lines(self) -> list[str]:
        if self._walkingpad_service is None:
            return ["- Walking: not configured."]
        try:
            _, _, events = self._calendar_service.today()
            return self._walkingpad_service.context_lines(events, self._now())
        except Exception:
            return ["- Walking: unavailable."]

    @staticmethod
    def _group_events_by_local_date(
        events: list[CalendarEvent],
        tz: ZoneInfo,
    ) -> dict[date, list[CalendarEvent]]:
        grouped: dict[date, list[CalendarEvent]] = {}
        for event in events:
            day = event.start_at.astimezone(tz).date()
            grouped.setdefault(day, []).append(event)
        for day_events in grouped.values():
            day_events.sort(key=lambda event: event.start_at)
        return grouped

    @staticmethod
    def _format_event_time(event: CalendarEvent, tz: ZoneInfo) -> str:
        if event.is_all_day:
            return "all day"
        start = event.start_at.astimezone(tz)
        end = event.end_at.astimezone(tz)
        return f"{start.strftime('%H:%M')}-{end.strftime('%H:%M')}"

    def _task_lines(self) -> list[str]:
        try:
            status, synced_at, tasks = self._notion_service.today()
            synced = synced_at.isoformat() if synced_at else "never"
            lines = [f"- Tasks: {status}; synced at {synced}; {len(tasks)} due or overdue task(s)."]
            for task in tasks[:8]:
                due = task.due_at.isoformat() if task.due_at else "no due date"
                overdue = "overdue" if task.is_overdue else "open"
                details = ", ".join(value for value in [task.status, task.priority, overdue, due] if value)
                lines.append(f"  - {task.title}: {details}.")
            if len(tasks) > 8:
                lines.append(f"  - {len(tasks) - 8} more task(s) omitted.")
            return lines
        except Exception:
            return ["- Tasks: unavailable."]

    def _spotify_lines(self) -> list[str]:
        try:
            playback = self._spotify_service.now_playing()
            status = playback.get("status", "unavailable")
            if not playback.get("track"):
                return [f"- Spotify: {status}; nothing playing."]
            state = "playing" if playback.get("is_playing") else "paused"
            device = playback.get("device_name") or "unknown device"
            return [
                (
                    f"- Spotify: {status}; {state}; {playback.get('track')} by "
                    f"{playback.get('artist') or 'unknown artist'} on {device}."
                )
            ]
        except Exception:
            return ["- Spotify: unavailable."]
