from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
from bleak import BleakScanner
from walkingpad_controller import WalkingPadController
from walkingpad_controller.const import BeltState
from walkingpad_controller.models import TreadmillStatus

logger = logging.getLogger(__name__)

SESSION_IDLE_SECONDS = 120
HEARTBEAT_SECONDS = 30
SCAN_RETRY_SECONDS = 15


@dataclass
class SessionState:
    external_id: str
    started_at: datetime
    duration_seconds: int = 0
    distance_km: float = 0.0
    steps: int = 0
    calories: float = 0.0
    last_motion_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    in_progress: bool = True


class WalkingPadCollector:
    def __init__(self) -> None:
        self._device_name = os.environ.get("WALKINGPAD_BLE_NAME", "").strip()
        self._dashboard_url = os.environ.get("DASHBOARD_URL", "http://127.0.0.1:8080").rstrip("/")
        self._token = os.environ.get("WALKINGPAD_BRIDGE_TOKEN", "").strip()
        self._controller: WalkingPadController | None = None
        self._session: SessionState | None = None
        self._dirty = False
        self._last_post_at: datetime | None = None

    def configured(self) -> bool:
        return bool(self._device_name and self._token)

    async def run(self) -> None:
        if not self.configured():
            raise RuntimeError("WALKINGPAD_BLE_NAME and WALKINGPAD_BRIDGE_TOKEN are required.")
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
        logger.info("WalkingPad collector starting for %s", self._device_name)
        while True:
            try:
                await self._connect_loop()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Collector loop failed; retrying in %ss", SCAN_RETRY_SECONDS)
                await asyncio.sleep(SCAN_RETRY_SECONDS)

    async def _connect_loop(self) -> None:
        device = await BleakScanner.find_device_by_name(self._device_name, timeout=30.0)
        if device is None:
            logger.warning("WalkingPad %s not found; scanning again", self._device_name)
            await asyncio.sleep(SCAN_RETRY_SECONDS)
            return
        controller = WalkingPadController(ble_device=device)
        self._controller = controller
        controller.register_status_callback(self._on_status)
        controller.register_disconnect_callback(lambda: logger.warning("WalkingPad disconnected"))
        await controller.connect()
        logger.info("Connected to WalkingPad (%s)", controller.protocol)
        try:
            while controller.connected:
                await controller.update_state()
                await self._maybe_finalize_idle_session()
                await self._maybe_post_heartbeat()
                await asyncio.sleep(5)
        finally:
            await self._finalize_session()
            await controller.disconnect()
            self._controller = None

    def _on_status(self, status: TreadmillStatus) -> None:
        now = datetime.now(UTC)
        speed = float(status.speed or 0)
        belt_state = status.belt_state
        moving = speed > 0 or belt_state == BeltState.ACTIVE
        paused = belt_state == BeltState.PAUSED
        duration = int(status.duration or 0)
        distance_m = float(status.distance or 0)
        steps = int(status.steps or 0)
        calories = float(status.calories or 0)
        active = moving or paused or duration > 0 or distance_m > 0
        if not active:
            return
        if self._session is None:
            self._session = SessionState(external_id=str(uuid.uuid4()), started_at=now)
            logger.info(
                "Session started %s (speed=%.2f km/h, belt=%s)",
                self._session.external_id,
                speed,
                belt_state,
            )
        self._session.last_motion_at = now
        if duration <= 0 and moving:
            duration = int((now - self._session.started_at).total_seconds())
        self._session.duration_seconds = max(self._session.duration_seconds, duration)
        self._session.distance_km = max(self._session.distance_km, distance_m / 1000)
        self._session.steps = max(self._session.steps, steps)
        self._session.calories = max(self._session.calories, calories)
        self._dirty = True

    async def _maybe_finalize_idle_session(self) -> None:
        if self._session is None or not self._session.in_progress:
            return
        idle_for = datetime.now(UTC) - self._session.last_motion_at
        if idle_for >= timedelta(seconds=SESSION_IDLE_SECONDS):
            await self._finalize_session()

    async def _maybe_post_heartbeat(self) -> None:
        if self._session is None or not self._dirty:
            return
        now = datetime.now(UTC)
        if self._last_post_at and now - self._last_post_at < timedelta(seconds=HEARTBEAT_SECONDS):
            return
        await self._post_session(in_progress=True)
        self._dirty = False
        self._last_post_at = now

    async def _finalize_session(self) -> None:
        if self._session is None or not self._session.in_progress:
            return
        self._session.in_progress = False
        ended_at = datetime.now(UTC)
        logger.info(
            "Session complete %s (%ss, %.2f km)",
            self._session.external_id,
            self._session.duration_seconds,
            self._session.distance_km,
        )
        await self._post_session(in_progress=False, ended_at=ended_at)
        self._session = None
        self._dirty = False

    async def _post_session(self, *, in_progress: bool, ended_at: datetime | None = None) -> None:
        if self._session is None:
            return
        payload = {
            "synced_at": datetime.now(UTC).isoformat(),
            "session": {
                "external_id": self._session.external_id,
                "started_at": self._session.started_at.isoformat(),
                "ended_at": ended_at.isoformat() if ended_at else None,
                "duration_seconds": self._session.duration_seconds,
                "distance_km": self._session.distance_km,
                "steps": self._session.steps,
                "calories": self._session.calories,
                "in_progress": in_progress,
            },
        }
        url = f"{self._dashboard_url}/api/v1/walkingpad/sync"
        headers = {"X-Chili-Bridge-Token": self._token, "Content-Type": "application/json"}
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.post(url, json=payload, headers=headers)
                response.raise_for_status()
        except httpx.HTTPError:
            logger.exception("Failed to sync session %s to dashboard", self._session.external_id)
            self._dirty = True
            return
        logger.info(
            "Synced session %s (%ss, %.2f km, in_progress=%s)",
            self._session.external_id,
            self._session.duration_seconds,
            self._session.distance_km,
            in_progress,
        )


async def main() -> None:
    collector = WalkingPadCollector()
    await collector.run()


if __name__ == "__main__":
    asyncio.run(main())
