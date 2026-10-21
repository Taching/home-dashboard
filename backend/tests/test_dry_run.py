"""Tests proving dry-run guards block external side effects.

These tests verify that when CHILI_PRODUCTION_MODE is False (the default),
external writes to Telegram, Notion, devices, and LLM APIs are blocked.
"""

import unittest
from datetime import date
from unittest.mock import patch, MagicMock

from app.core.dry_run import is_dry_run, guard_external_call


class DryRunHelperTests(unittest.TestCase):
    def test_dry_run_true_when_production_mode_false(self):
        with patch("app.core.dry_run.settings") as mock_settings:
            mock_settings.production_mode = False
            self.assertTrue(is_dry_run())

    def test_dry_run_false_when_production_mode_true(self):
        with patch("app.core.dry_run.settings") as mock_settings:
            mock_settings.production_mode = True
            self.assertFalse(is_dry_run())


class TestEnvironmentIsDryRunTests(unittest.TestCase):
    def test_suite_never_runs_with_production_settings(self):
        # Guards against the Pi's production .env leaking into `make check`.
        from app.core.settings import settings
        self.assertFalse(settings.production_mode)
        self.assertIsNone(settings.openai_api_key)


class OpenClawDryRunTests(unittest.TestCase):
    @patch("app.domain.openclaw.settings")
    @patch("app.domain.openclaw.is_dry_run", return_value=True)
    def test_notify_user_blocked_in_dry_run(self, mock_dry_run, mock_settings):
        from app.domain.openclaw import OpenClawService

        mock_settings.openclaw_gateway_ws_url = "ws://test"
        mock_settings.openclaw_gateway_token = "token"
        mock_settings.openclaw_notify_channel = "telegram"
        mock_settings.openclaw_notify_target = "user"

        service = OpenClawService()
        result = service.notify_user("Hello world")

        self.assertEqual(result["delivery_status"], "dry_run")
        self.assertIsNone(result["reply"])

    @patch("app.domain.openclaw.settings")
    @patch("app.domain.openclaw.is_dry_run", return_value=True)
    def test_send_blocked_in_dry_run(self, mock_dry_run, mock_settings):
        from app.domain.openclaw import OpenClawService

        mock_settings.openclaw_gateway_ws_url = "ws://test"
        mock_settings.openclaw_gateway_token = "token"

        service = OpenClawService()
        result = service.send("Test message")

        self.assertEqual(result["delivery_status"], "dry_run")
        self.assertIsNone(result["reply"])


class LightsDryRunTests(unittest.TestCase):
    @patch("app.domain.lights.is_dry_run", return_value=True)
    def test_set_state_blocked_in_dry_run(self, mock_dry_run):
        from app.domain.lights import LightService

        service = LightService()
        result = service.set_state("on", source="test")

        self.assertEqual(result.status, "success")
        self.assertIn("DRY-RUN", result.message)


class WaterPumpDryRunTests(unittest.TestCase):
    @patch("app.domain.water_pump.is_dry_run", return_value=True)
    def test_start_pulse_blocked_in_dry_run(self, mock_dry_run):
        import asyncio
        from app.domain.water_pump import WaterPumpService

        service = WaterPumpService()
        result = asyncio.get_event_loop().run_until_complete(
            service.start_pulse(source="test")
        )

        self.assertEqual(result.status, "success")
        self.assertIn("DRY-RUN", result.message)

    @patch("app.domain.water_pump.is_dry_run", return_value=True)
    def test_run_pulse_blocked_in_dry_run(self, mock_dry_run):
        import asyncio
        from app.domain.water_pump import WaterPumpService

        service = WaterPumpService()
        result = asyncio.get_event_loop().run_until_complete(
            service.run_pulse(source="test")
        )

        self.assertEqual(result.status, "success")
        self.assertIn("DRY-RUN", result.message)


class DisplayDryRunTests(unittest.TestCase):
    @patch("app.domain.display.is_dry_run", return_value=True)
    @patch("app.domain.display.subprocess.run")
    def test_apply_blocked_in_dry_run(self, mock_subprocess, mock_dry_run):
        from app.domain.display import DisplayService
        import tempfile
        import os

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = os.path.join(tmpdir, "display-state.json")
            service = DisplayService(state_path=state_path, power_script="/bin/true")
            service._power_ready = True
            service._apply("hidden")

            mock_subprocess.assert_not_called()


class NotionDryRunTests(unittest.TestCase):
    @patch("app.domain.notion.settings")
    @patch("app.domain.notion.is_dry_run", return_value=True)
    def test_complete_blocked_in_dry_run(self, mock_dry_run, mock_settings):
        from app.domain.notion import NotionService

        mock_settings.notion_token = "test-token"
        mock_settings.notion_database_id = "test-db"
        mock_settings.notion_data_source_id = None
        mock_settings.notion_done_property = "Done"
        mock_settings.notion_status_property = "Status"
        mock_settings.notion_done_statuses = "Done"
        mock_settings.timezone = "Asia/Tokyo"

        service = NotionService()
        # Should not raise, should return silently
        service.complete("page-id")

    @patch("app.domain.notion.settings")
    @patch("app.domain.notion.is_dry_run", return_value=True)
    def test_publish_progress_blocked_in_dry_run(self, mock_dry_run, mock_settings):
        from app.domain.notion import NotionService
        from app.domain.progress_reports import ProgressReport
        from datetime import date

        mock_settings.notion_token = "test-token"
        mock_settings.notion_progress_data_source_id = "test-ds"
        mock_settings.timezone = "Asia/Tokyo"

        service = NotionService()
        report = ProgressReport(
            period="weekly",
            start=date(2026, 1, 1),
            end=date(2026, 1, 7),
            weight_kg=80.0,
            weight_change_kg=-0.5,
            sober_days=7,
            gym_sessions=3,
            jiujitsu_sessions=2,
            walk_minutes=120,
            walk_distance_km=5.0,
            steps=10000,
            strength_sessions=2,
            zone2_sessions=1,
            interval_sessions=0,
            grip_sessions=1,
            rest_days=2,
            sparring_rounds=10,
            skipped_workouts=0,
            skipped_reasons=(),
        )
        result = service.publish_progress(report)
        self.assertEqual(result, "dry-run-page-id")


class NotionSyncDryRunTests(unittest.TestCase):
    @patch("app.domain.training.notion_sync.settings")
    @patch("app.domain.training.notion_sync.is_dry_run", return_value=True)
    def test_sync_due_blocked_in_dry_run(self, mock_dry_run, mock_settings):
        from app.domain.training.notion_sync import TrainingNotionSync

        mock_settings.notion_token = "test-token"
        mock_settings.notion_training_data_source_id = "test-ds"
        mock_settings.timezone = "Asia/Tokyo"

        service = TrainingNotionSync()
        result = service.sync_due()
        self.assertEqual(result, 0)


class LLMDryRunTests(unittest.TestCase):
    @patch("app.domain.training.llm.settings")
    @patch("app.domain.training.llm.is_dry_run", return_value=True)
    def test_rerank_blocked_in_dry_run(self, mock_dry_run, mock_settings):
        from app.domain.training.llm import rerank_and_explain
        from app.domain.training.types import WorkoutType, SchedulerInput, AthleteState, FatigueLevel, SorenessLevel

        mock_settings.openai_api_key = "test-key"

        inp = SchedulerInput(
            today=date(2026, 9, 15),
            athlete_state=AthleteState(fatigue=FatigueLevel.NORMAL, soreness=SorenessLevel.LOW, injured=False),
            history=(),
            upcoming_hard_bjj=None,
        )

        result, reason = rerank_and_explain(
            close=(WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B),
            default=WorkoutType.STRENGTH_A,
            fallback_reason="Default choice",
            inp=inp,
            day=date(2026, 9, 15),
        )

        self.assertEqual(result, WorkoutType.STRENGTH_A)
        self.assertEqual(reason, "Default choice")


class AdjustDryRunTests(unittest.TestCase):
    @patch("app.domain.training.adjust.settings")
    @patch("app.domain.training.adjust.is_dry_run", return_value=True)
    def test_interpret_blocked_in_dry_run(self, mock_dry_run, mock_settings):
        from app.domain.training.adjust import CalendarAdjuster

        mock_settings.openai_api_key = "test-key"
        mock_settings.voice_command_model = "gpt-test"
        mock_settings.timezone = "Asia/Tokyo"

        adjuster = CalendarAdjuster()

        with self.assertRaises(ValueError) as ctx:
            adjuster.interpret(
                "something complex that needs GPT",
                context={},
                today=date(2026, 9, 15),
            )

        self.assertIn("dry-run", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()
