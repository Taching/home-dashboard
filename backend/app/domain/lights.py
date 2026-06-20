from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import select

from app.database.models import LightCommand
from app.database.session import SessionLocal

LightCommandState = Literal["on", "off", "unknown"]


class LightAdapter(Protocol):
    @property
    def available(self) -> bool: ...

    def set_state(self, state: Literal["on", "off"]) -> None: ...


class UnavailableLightAdapter:
    """Safe default until the RM4 Mini and learned codes are configured."""

    @property
    def available(self) -> bool:
        return False

    def set_state(self, state: Literal["on", "off"]) -> None:
        raise RuntimeError("BroadLink light control is not configured")


@dataclass(frozen=True)
class LightSnapshot:
    last_command_state: LightCommandState
    last_command_at: datetime | None
    available: bool


@dataclass(frozen=True)
class LightCommandResult:
    status: Literal["success", "failed"]
    message: str
    light: LightSnapshot


class LightService:
    def __init__(self, adapter: LightAdapter | None = None) -> None:
        self._adapter = adapter or UnavailableLightAdapter()
        self._last_command_state: LightCommandState = "unknown"
        self._last_command_at: datetime | None = None

    def restore_latest(self) -> None:
        with SessionLocal() as session:
            command = session.scalar(
                select(LightCommand).order_by(LightCommand.occurred_at.desc()).limit(1)
            )
        if command is not None:
            self._last_command_state = command.state  # type: ignore[assignment]
            self._last_command_at = command.occurred_at

    def snapshot(self) -> LightSnapshot:
        return LightSnapshot(
            last_command_state=self._last_command_state,
            last_command_at=self._last_command_at,
            available=self._adapter.available,
        )

    def set_state(
        self, state: Literal["on", "off"], source: str
    ) -> LightCommandResult:
        if not self._adapter.available:
            return LightCommandResult(
                status="failed",
                message="BroadLink is unavailable.",
                light=self.snapshot(),
            )

        try:
            self._adapter.set_state(state)
        except Exception:
            return LightCommandResult(
                status="failed",
                message="The light command could not be sent.",
                light=self.snapshot(),
            )

        occurred_at = datetime.now(UTC)
        with SessionLocal.begin() as session:
            session.add(LightCommand(occurred_at=occurred_at, state=state, source=source))

        self._last_command_state = state
        self._last_command_at = occurred_at
        return LightCommandResult(
            status="success",
            message=f"Light set {state}.",
            light=self.snapshot(),
        )
