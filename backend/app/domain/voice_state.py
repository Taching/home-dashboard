from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Literal

VoiceState = Literal["offline", "idle", "listening", "thinking", "complete", "error"]


@dataclass(frozen=True)
class VoiceStateSnapshot:
    state: VoiceState
    updated_at: datetime | None
    transcript: str | None
    message: str | None


class VoiceStateService:
    """Ephemeral status shared by the local voice worker and dashboard UI."""

    _display_durations = {
        "listening": timedelta(seconds=10),
        "thinking": timedelta(seconds=45),
        "complete": timedelta(seconds=4),
        "error": timedelta(seconds=5),
    }

    def __init__(self) -> None:
        self._state: VoiceState = "offline"
        self._updated_at: datetime | None = None
        self._transcript: str | None = None
        self._message: str | None = None
        self._lock = Lock()

    def set_state(
        self,
        state: VoiceState,
        transcript: str | None = None,
        message: str | None = None,
    ) -> None:
        with self._lock:
            self._state = state
            self._updated_at = datetime.now(UTC)
            self._transcript = transcript if state != "idle" else None
            self._message = message if state != "idle" else None

    def current(self) -> VoiceStateSnapshot:
        with self._lock:
            if self._updated_at is None:
                return VoiceStateSnapshot("offline", None, None, None)
            duration = self._display_durations.get(self._state)
            if duration and datetime.now(UTC) - self._updated_at > duration:
                return VoiceStateSnapshot("idle", self._updated_at, None, None)
            return VoiceStateSnapshot(self._state, self._updated_at, self._transcript, self._message)
