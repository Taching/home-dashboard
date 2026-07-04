import asyncio
import unittest
from unittest.mock import patch

from app.domain.water_pump import SwitchBotPlugAdapter, WaterPumpService


class FakeAdapter:
    def __init__(self, available: bool = True) -> None:
        self.available = available
        self.power: bool | None = None
        self.calls: list[bool] = []

    def set_power(self, on: bool) -> None:
        self.power = on
        self.calls.append(on)


class WaterPumpServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_run_pulse_turns_on_then_off(self):
        adapter = FakeAdapter()
        service = WaterPumpService(adapter=adapter)

        with patch.object(service, "_duration_seconds", return_value=2):
            result = await service.run_pulse("test")

        self.assertEqual(result.status, "success")
        self.assertEqual(adapter.calls, [True, False])
        self.assertEqual(service.snapshot().state, "idle")

    async def test_start_pulse_skips_when_already_running(self):
        adapter = FakeAdapter()
        service = WaterPumpService(adapter=adapter)
        service._state = "running"

        result = await service.start_pulse("ui")

        self.assertEqual(result.status, "skipped")
        self.assertEqual(adapter.calls, [])

    async def test_stop_cancels_running_pulse(self):
        adapter = FakeAdapter()
        service = WaterPumpService(adapter=adapter)

        with patch.object(service, "_duration_seconds", return_value=5):
            start = await service.start_pulse("ui")
            self.assertEqual(start.status, "success")
            await asyncio.sleep(0.05)
            stop = await service.stop("ui")
            await asyncio.sleep(0.05)

        self.assertEqual(stop.status, "success")
        self.assertFalse(adapter.power)
        self.assertEqual(service.snapshot().state, "idle")

    async def test_unavailable_when_not_configured(self):
        service = WaterPumpService(adapter=FakeAdapter(available=False))
        result = await service.run_pulse("ui")
        self.assertEqual(result.status, "failed")


class SwitchBotPlugAdapterTests(unittest.TestCase):
    def test_available_requires_device_id(self):
        with patch("app.domain.switchbot.SwitchBotClient") as client_cls:
            client_cls.return_value.configured = False
            adapter = SwitchBotPlugAdapter()
            self.assertFalse(adapter.available)


if __name__ == "__main__":
    unittest.main()
