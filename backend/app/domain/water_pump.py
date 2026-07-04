from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import WaterPumpRun
from app.database.session import SessionLocal
from app.domain.switchbot import SwitchBotClient, SwitchBotError

WaterPumpState = Literal["idle", "running"]
RunStatus = Literal["success", "skipped", "failed"]


class WaterPumpAdapter(Protocol):
    @property
    def available(self) -> bool: ...

    def set_power(self, on: bool) -> None: ...


class SwitchBotPlugAdapter:
    def __init__(self, client: SwitchBotClient | None = None) -> None:
        self._client = client or SwitchBotClient()

    @property
    def available(self) -> bool:
        return self._client.configured

    def set_power(self, on: bool) -> None:
        self._client.set_power(on)


@dataclass(frozen=True)
class WaterPumpSnapshot:
    state: WaterPumpState
    last_run_at: datetime | None
    last_run_status: str | None
    available: bool


@dataclass(frozen=True)
class WaterPumpRunResult:
    status: RunStatus
    message: str
    water_pump: WaterPumpSnapshot


class WaterPumpService:
    MAX_DURATION_SECONDS = 120

    def __init__(self, adapter: WaterPumpAdapter | None = None) -> None:
        self._adapter = adapter or SwitchBotPlugAdapter()
        self._lock = asyncio.Lock()
        self._state: WaterPumpState = "idle"
        self._cancel = False
        self._task: asyncio.Task[None] | None = None
        self._last_run_at: datetime | None = None
        self._last_run_status: str | None = None

    def restore_latest(self) -> None:
        with SessionLocal() as session:
            run = session.scalar(
                select(WaterPumpRun).order_by(WaterPumpRun.occurred_at.desc()).limit(1)
            )
        if run is not None:
            self._last_run_at = run.occurred_at
            self._last_run_status = run.result

    def snapshot(self) -> WaterPumpSnapshot:
        return WaterPumpSnapshot(
            state=self._state,
            last_run_at=self._last_run_at,
            last_run_status=self._last_run_status,
            available=self._adapter.available,
        )

    async def start_pulse(self, source: str) -> WaterPumpRunResult:
        if not self._adapter.available:
            return WaterPumpRunResult(
                status="failed",
                message="Plant pump is unavailable.",
                water_pump=self.snapshot(),
            )

        async with self._lock:
            if self._state == "running":
                return WaterPumpRunResult(
                    status="skipped",
                    message="Plant pump is already running.",
                    water_pump=self.snapshot(),
                )
            self._state = "running"
            self._cancel = False
            self._task = asyncio.create_task(self._pulse(source))

        duration = self._duration_seconds()
        return WaterPumpRunResult(
            status="success",
            message=f"Plant pump started for {duration} seconds.",
            water_pump=self.snapshot(),
        )

    async def run_pulse(self, source: str) -> WaterPumpRunResult:
        if not self._adapter.available:
            return WaterPumpRunResult(
                status="failed",
                message="Plant pump is unavailable.",
                water_pump=self.snapshot(),
            )

        async with self._lock:
            if self._state == "running":
                return WaterPumpRunResult(
                    status="skipped",
                    message="Plant pump is already running.",
                    water_pump=self.snapshot(),
                )
            self._state = "running"
            self._cancel = False

        await self._pulse(source)
        status: RunStatus = (
            "failed" if (self._last_run_status or "").startswith("failed") else "success"
        )
        message = (
            f"Plant pump ran for {self._duration_seconds()} seconds."
            if status == "success"
            else (self._last_run_status or "Plant pump failed.")
        )
        return WaterPumpRunResult(status=status, message=message, water_pump=self.snapshot())

    async def stop(self, source: str) -> WaterPumpRunResult:
        if self._state != "running":
            return WaterPumpRunResult(
                status="skipped",
                message="Plant pump is idle.",
                water_pump=self.snapshot(),
            )

        self._cancel = True
        if self._task is not None:
            try:
                await self._task
            except Exception:
                pass

        return WaterPumpRunResult(
            status="success",
            message="Plant pump stopped.",
            water_pump=self.snapshot(),
        )

    async def _pulse(self, source: str) -> None:
        duration = self._duration_seconds()
        result = "success"
        try:
            await asyncio.to_thread(self._adapter.set_power, True)
            for _ in range(duration):
                if self._cancel:
                    result = "stopped"
                    break
                await asyncio.sleep(1)
        except SwitchBotError as error:
            result = f"failed: {error}"
        except Exception:
            result = "failed"
        finally:
            try:
                await asyncio.to_thread(self._adapter.set_power, False)
            except Exception:
                if result == "success":
                    result = "failed: could not turn off"
            self._state = "idle"
            self._task = None
            self._record(source, result, duration)

    def _record(self, source: str, result: str, duration_seconds: int) -> None:
        occurred_at = datetime.now(UTC)
        with SessionLocal.begin() as session:
            session.add(
                WaterPumpRun(
                    occurred_at=occurred_at,
                    source=source,
                    duration_seconds=duration_seconds,
                    result=result,
                )
            )
        self._last_run_at = occurred_at
        self._last_run_status = result

    @staticmethod
    def _duration_seconds() -> int:
        return max(1, min(settings.water_pump_duration_seconds, WaterPumpService.MAX_DURATION_SECONDS))
