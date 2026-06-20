import unittest

from app.core.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_dashboard_operational_defaults_are_centralized(self) -> None:
        settings = Settings()

        self.assertEqual(settings.sensor_stale_after_seconds, 900)
        self.assertEqual(settings.dashboard_refresh_interval_seconds, 60)
        self.assertEqual(settings.openclaw_refresh_interval_seconds, 10)
        self.assertEqual(settings.readings_history_hours, 24)
        self.assertEqual(settings.calendar_range_days, 30)
        self.assertEqual(settings.openclaw_message_max_length, 3000)

