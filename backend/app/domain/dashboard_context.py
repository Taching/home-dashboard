from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any


class DashboardContextProvider:
    def __init__(
        self,
        *,
        sensor_service: Any,
        light_service: Any,
        calendar_service: Any,
        notion_service: Any,
        spotify_service: Any,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._sensor_service = sensor_service
        self._light_service = light_service
        self._calendar_service = calendar_service
        self._notion_service = notion_service
        self._spotify_service = spotify_service
        self._now = now or (lambda: datetime.now(UTC))

    def __call__(self) -> str:
        lines = [
            "Dashboard data snapshot:",
            f"- Snapshot time: {self._now().isoformat()}",
        ]
        lines.extend(self._sensor_lines())
        lines.extend(self._light_lines())
        lines.extend(self._calendar_lines())
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
            status, synced_at, events = self._calendar_service.today()
            synced = synced_at.isoformat() if synced_at else "never"
            lines = [f"- Calendar: {status}; synced at {synced}; {len(events)} event(s) today."]
            for event in events[:8]:
                label = "all day" if event.is_all_day else f"{event.start_at.isoformat()} to {event.end_at.isoformat()}"
                lines.append(f"  - {event.title}: {label}.")
            if len(events) > 8:
                lines.append(f"  - {len(events) - 8} more event(s) omitted.")
            return lines
        except Exception:
            return ["- Calendar: unavailable."]

    def _task_lines(self) -> list[str]:
        try:
            status, synced_at, tasks = self._notion_service.today()
            synced = synced_at.isoformat() if synced_at else "never"
            lines = [f"- Tasks: {status}; synced at {synced}; {len(tasks)} due or overdue task(s)."]
            for task in tasks[:8]:
                due = task.due_at.isoformat() if task.due_at else "no due date"
                overdue = "overdue" if task.is_overdue else "due today"
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
