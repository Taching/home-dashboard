from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

from app.core.settings import settings

logger = logging.getLogger(__name__)

DisplayState = Literal["visible", "hidden"]


@dataclass(frozen=True)
class DisplaySnapshot:
    state: DisplayState
    schedule_enabled: bool
    schedule_on_hour: int
    schedule_off_hour: int
    power_available: bool
    manual_override: bool


class DisplayService:
    """Controls dashboard visibility on a daily schedule with manual overrides."""

    def __init__(
        self,
        *,
        state_path: str | Path | None = None,
        power_script: str | Path | None = None,
    ) -> None:
        self._state_path = Path(state_path or "/data/display-state.json")
        self._power_script = Path(power_script or settings.display_power_script)
        self._timezone = ZoneInfo(settings.timezone)
        self._state: DisplayState = "visible"
        self._schedule_enabled = settings.display_schedule_enabled
        self._manual_override_until: datetime | None = None
        self._applied_state: DisplayState | None = None

    def restore(self) -> None:
        if not self._state_path.exists():
            self.sync(self._now())
            return
        try:
            payload = json.loads(self._state_path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            logger.warning("Could not read display state: %s", error)
            self.sync(self._now())
            return

        raw_state = payload.get("state", "visible")
        self._state = "visible" if raw_state == "visible" else "hidden"
        if "schedule_enabled" in payload:
            self._schedule_enabled = bool(payload["schedule_enabled"])
        override = payload.get("manual_override_until")
        self._manual_override_until = self._parse_timestamp(override)
        self.sync(self._now())

    def snapshot(self) -> DisplaySnapshot:
        now = self._now()
        return DisplaySnapshot(
            state=self.effective_state(now),
            schedule_enabled=self._schedule_enabled,
            schedule_on_hour=settings.screen_on_hour,
            schedule_off_hour=settings.screen_off_hour,
            power_available=self._power_available(),
            manual_override=self._manual_override_active(now),
        )

    def effective_state(self, now: datetime | None = None) -> DisplayState:
        current = now or self._now()
        if self._manual_override_active(current):
            return self._state
        if self._schedule_enabled:
            return "visible" if self._scheduled_visible(current) else "hidden"
        return self._state

    def sync(self, now: datetime | None = None) -> bool:
        current = now or self._now()
        changed = False

        if self._manual_override_until and current >= self._manual_override_until:
            self._manual_override_until = None
            self._persist()
            changed = True

        target = self.effective_state(current)
        if target != self._applied_state:
            self._apply(target)
            changed = True
        return changed

    def show(self, source: str) -> DisplaySnapshot:
        del source
        return self._set_manual("visible")

    def hide(self, source: str) -> DisplaySnapshot:
        del source
        return self._set_manual("hidden")

    def set_schedule_enabled(self, enabled: bool) -> DisplaySnapshot:
        self._schedule_enabled = enabled
        self._manual_override_until = None
        if enabled:
            self._state = self.effective_state(self._now())
        self._apply(self.effective_state(self._now()))
        self._persist()
        return self.snapshot()

    def _set_manual(self, state: DisplayState) -> DisplaySnapshot:
        now = self._now()
        self._state = state
        self._manual_override_until = self._next_boundary(now)
        self._apply(state)
        self._persist()
        return self.snapshot()

    def _scheduled_visible(self, now: datetime) -> bool:
        local = now.astimezone(self._timezone)
        hour = local.hour
        on_hour = settings.screen_on_hour
        off_hour = settings.screen_off_hour
        if on_hour == off_hour:
            return True
        if on_hour < off_hour:
            return on_hour <= hour < off_hour
        return hour >= on_hour or hour < off_hour

    def _next_boundary(self, now: datetime) -> datetime:
        local = now.astimezone(self._timezone)
        on_hour = settings.screen_on_hour
        off_hour = settings.screen_off_hour
        candidates: list[datetime] = []
        for hour in (on_hour, off_hour):
            boundary = local.replace(hour=hour, minute=0, second=0, microsecond=0)
            if boundary <= local:
                boundary += timedelta(days=1)
            candidates.append(boundary)
        return min(candidates).astimezone(UTC)

    def _manual_override_active(self, now: datetime) -> bool:
        return self._manual_override_until is not None and now < self._manual_override_until

    def _apply(self, state: DisplayState) -> None:
        self._applied_state = state
        if not self._power_available():
            return
        action = "on" if state == "visible" else "off"
        try:
            subprocess.run(
                [str(self._power_script), action],
                check=True,
                capture_output=True,
                text=True,
                timeout=5,
                env=self._power_env(),
            )
        except (OSError, subprocess.SubprocessError) as error:
            logger.warning("Display power command failed (%s): %s", action, error)

    def _power_available(self) -> bool:
        return os.access(self._power_script, os.X_OK)

    def _power_env(self) -> dict[str, str]:
        env = os.environ.copy()
        env.setdefault("DISPLAY", settings.display_x_display)
        if settings.display_xauthority:
            env.setdefault("XAUTHORITY", settings.display_xauthority)
        return env

    def _persist(self) -> None:
        payload = {
            "state": self._state,
            "schedule_enabled": self._schedule_enabled,
            "manual_override_until": (
                self._manual_override_until.isoformat() if self._manual_override_until else None
            ),
        }
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            self._state_path.write_text(json.dumps(payload, indent=2) + "\n")
        except OSError as error:
            logger.warning("Could not persist display state: %s", error)

    def _now(self) -> datetime:
        return datetime.now(UTC)

    @staticmethod
    def _parse_timestamp(value: object) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)
