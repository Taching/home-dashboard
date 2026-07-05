import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.core.settings import settings
from app.domain.display import DisplayService

JST = ZoneInfo("Asia/Tokyo")


class DisplayServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tempdir.name) / "display-state.json"
        self.power_script = Path(self.tempdir.name) / "display-power.sh"
        self.power_script.write_text("#!/bin/sh\n")
        self.power_script.chmod(0o755)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def _service(self) -> DisplayService:
        return DisplayService(state_path=self.state_path, power_script=self.power_script)

    def test_scheduled_visible_between_on_and_off_hours(self) -> None:
        service = self._service()
        noon = datetime(2026, 7, 6, 12, 0, tzinfo=JST)
        with patch.object(settings, "screen_on_hour", 8), patch.object(settings, "screen_off_hour", 22):
            self.assertTrue(service._scheduled_visible(noon))

    def test_scheduled_hidden_outside_window(self) -> None:
        service = self._service()
        late = datetime(2026, 7, 6, 23, 0, tzinfo=JST)
        with patch.object(settings, "screen_on_hour", 8), patch.object(settings, "screen_off_hour", 22):
            self.assertFalse(service._scheduled_visible(late))

    def test_schedule_enabled_hides_outside_window(self) -> None:
        service = self._service()
        service._schedule_enabled = True
        late = datetime(2026, 7, 6, 23, 0, tzinfo=JST)
        with patch.object(settings, "screen_on_hour", 8), patch.object(settings, "screen_off_hour", 22):
            self.assertEqual(service.effective_state(late), "hidden")

    def test_manual_hide_overrides_schedule_until_boundary(self) -> None:
        service = self._service()
        service._schedule_enabled = True
        noon = datetime(2026, 7, 6, 12, 0, tzinfo=JST)
        with patch.object(settings, "screen_on_hour", 8), patch.object(settings, "screen_off_hour", 22):
            with patch.object(service, "_apply") as apply:
                service.hide("ui")
            self.assertEqual(service.effective_state(noon), "hidden")
            apply.assert_called_with("hidden")
            self.assertIsNotNone(service._manual_override_until)

    def test_disabling_schedule_keeps_current_state(self) -> None:
        service = self._service()
        service._state = "visible"
        service._schedule_enabled = True
        with patch.object(service, "_apply"):
            snapshot = service.set_schedule_enabled(False)
        self.assertFalse(snapshot.schedule_enabled)
        self.assertEqual(snapshot.state, "visible")

    def test_enabling_schedule_applies_window(self) -> None:
        service = self._service()
        service._state = "visible"
        service._schedule_enabled = False
        late = datetime(2026, 7, 6, 23, 0, tzinfo=JST)
        with patch.object(settings, "screen_on_hour", 8), patch.object(settings, "screen_off_hour", 22):
            with patch.object(service, "_now", return_value=late):
                with patch.object(service, "_apply") as apply:
                    snapshot = service.set_schedule_enabled(True)
        self.assertTrue(snapshot.schedule_enabled)
        self.assertEqual(snapshot.state, "hidden")
        apply.assert_called_with("hidden")

    def test_restore_persists_schedule_toggle(self) -> None:
        service = self._service()
        with patch.object(service, "_apply"):
            service.set_schedule_enabled(False)
        restored = self._service()
        with patch.object(restored, "_apply"):
            restored.restore()
        self.assertFalse(restored.snapshot().schedule_enabled)


if __name__ == "__main__":
    unittest.main()
