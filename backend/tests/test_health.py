import unittest
from datetime import UTC, datetime, timedelta

from app.domain.health import dashboard_health_details


class DashboardHealthTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 8, 1, 3, 0, tzinfo=UTC)

    def details(self, **overrides):
        values = {
            "calendar_status": "ready",
            "calendar_synced_at": self.now,
            "walkingpad_status": "ready",
            "walkingpad_synced_at": self.now,
            "now": self.now,
        }
        values.update(overrides)
        return {item.id: item for item in dashboard_health_details(**values)}

    def test_stale_calendar_needs_attention(self):
        details = self.details(
            calendar_status="stale",
        )

        self.assertTrue(details["calendar"].needs_attention)

    def test_inactive_walkingpad_is_informational(self):
        details = self.details(
            walkingpad_status="unavailable",
            walkingpad_synced_at=self.now - timedelta(days=1),
        )

        self.assertFalse(details["walkingpad"].needs_attention)
        self.assertEqual(details["walkingpad"].severity, "info")
        self.assertIn("normal when unused", details["walkingpad"].reason)

    def test_optional_unconfigured_services_are_not_faults(self):
        details = self.details(
            calendar_status="not_configured",
            walkingpad_status="not_configured",
        )

        self.assertFalse(details["calendar"].needs_attention)
        self.assertFalse(details["walkingpad"].needs_attention)


if __name__ == "__main__":
    unittest.main()
