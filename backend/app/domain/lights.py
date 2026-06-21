import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol

from sqlalchemy import select

from app.database.models import LightCommand
from app.database.session import SessionLocal
from app.core.settings import settings

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


class BroadlinkRM4MiniAdapter:
    """RM4 Mini adapter using locally learned, base64-encoded IR packets.

    The BroadLink package is imported only when the device is used, so local
    development remains possible without Pi hardware or the native network
    environment it needs.
    """

    def __init__(
        self,
        host: str | None = None,
        mac: str | None = None,
        device_type: int | None = None,
        codes_path: str | Path | None = None,
    ) -> None:
        self._host = host if host is not None else settings.broadlink_host
        self._mac = mac if mac is not None else settings.broadlink_mac
        self._device_type = device_type if device_type is not None else settings.broadlink_device_type
        self._codes_path = Path(codes_path or settings.broadlink_codes_path)
        self._device = None

    @property
    def available(self) -> bool:
        return bool(
            self._host
            and self._mac
            and self._device_type is not None
            and self._load_codes() is not None
        )

    def set_state(self, state: Literal["on", "off"]) -> None:
        codes = self._load_codes()
        if not self.available or codes is None:
            raise RuntimeError("Configure the RM4 Mini and learn light IR codes first")
        packet = codes.get(state)
        if packet is None:
            raise RuntimeError(f"No learned IR code for light {state}")
        self._connect().send_data(packet)

    def _connect(self):
        if self._device is not None:
            return self._device

        import broadlink

        assert self._host is not None
        assert self._mac is not None
        assert self._device_type is not None
        mac = bytes.fromhex(self._mac.replace(":", "").replace("-", ""))
        if len(mac) != 6:
            raise ValueError("BROADLINK_MAC must contain six hexadecimal bytes")
        device = broadlink.gendevice(self._device_type, (self._host, 80), mac)
        if not device.auth():
            raise RuntimeError("RM4 Mini authentication failed")
        self._device = device
        return device

    def _load_codes(self) -> dict[str, bytes] | None:
        try:
            payload = json.loads(self._codes_path.read_text())
            return {
                state: base64.b64decode(payload[state], validate=True)
                for state in ("on", "off")
            }
        except (KeyError, OSError, ValueError, json.JSONDecodeError):
            return None


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
        self._adapter = adapter or BroadlinkRM4MiniAdapter()
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
