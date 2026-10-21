import unittest
from datetime import UTC, datetime
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.router import api_router
from app.domain.lights import LightCommandResult, LightSnapshot


class AutomationLightApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.lights = Mock()
        self.snapshot = LightSnapshot(
            last_command_state="on",
            last_command_at=datetime(2026, 8, 30, tzinfo=UTC),
            available=True,
        )
        self.lights.snapshot.return_value = self.snapshot
        self.lights.set_state.return_value = LightCommandResult(
            status="success",
            message="Light set off.",
            light=LightSnapshot(
                last_command_state="off",
                last_command_at=datetime(2026, 8, 30, tzinfo=UTC),
                available=True,
            ),
        )
        self.app.state.light_service = self.lights
        self.app.state.activity_feed_service = Mock()
        self.client = TestClient(self.app)

    def test_requires_automation_token(self) -> None:
        response = self.client.post("/api/v1/automation/lights", json={"action": "off"})
        self.assertEqual(response.status_code, 401)

    def test_turns_lights_off_as_openclaw(self) -> None:
        with patch("app.api.router.settings") as mocked_settings:
            mocked_settings.dashboard_automation_token = "secret"
            response = self.client.post(
                "/api/v1/automation/lights",
                headers={"Authorization": "Bearer secret"},
                json={"action": "off"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["light"]["last_command_state"], "off")
        self.lights.set_state.assert_called_once_with("off", "openclaw")

    def test_reads_last_command_without_changing_lights(self) -> None:
        with patch("app.api.router.settings") as mocked_settings:
            mocked_settings.dashboard_automation_token = "secret"
            response = self.client.post(
                "/api/v1/automation/lights",
                headers={"Authorization": "Bearer secret"},
                json={"action": "status"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["message"], "The last light command was on.")
        self.lights.snapshot.assert_called_once_with()
        self.lights.set_state.assert_not_called()


if __name__ == "__main__":
    unittest.main()
