import unittest
from dataclasses import dataclass
from datetime import UTC, datetime

from app.domain.dashboard_context import DashboardContextProvider


@dataclass(frozen=True)
class FakeReading:
    recorded_at: datetime
    temperature_c: float
    humidity_percent: float


@dataclass(frozen=True)
class FakeLight:
    last_command_state: str
    last_command_at: datetime | None
    available: bool


@dataclass(frozen=True)
class FakeEvent:
    title: str
    start_at: datetime
    end_at: datetime
    is_all_day: bool = False


@dataclass(frozen=True)
class FakeTask:
    title: str
    due_at: datetime | None
    is_overdue: bool
    status: str | None = None
    priority: str | None = None


class FakeSensor:
    def current(self):
        return FakeReading(datetime(2026, 7, 4, 1, 0, tzinfo=UTC), 24.3, 61.0)

    def status(self):
        return "ready"


class FakeLightService:
    def snapshot(self):
        return FakeLight("on", datetime(2026, 7, 4, 0, 55, tzinfo=UTC), True)


class FakeCalendar:
    def today(self):
        return self.upcoming(1)

    def upcoming(self, days: int):
        _ = days
        return "ready", datetime(2026, 7, 4, 0, 50, tzinfo=UTC), [
            FakeEvent("Lunch", datetime(2026, 7, 4, 3, 0, tzinfo=UTC), datetime(2026, 7, 4, 4, 0, tzinfo=UTC)),
        ]


class FakeNotion:
    def today(self):
        return "ready", datetime(2026, 7, 4, 0, 45, tzinfo=UTC), [
            FakeTask("Water plants", datetime(2026, 7, 4, 12, 0, tzinfo=UTC), False, "Next", "High"),
        ]


class FakeSpotify:
    def now_playing(self):
        return {
            "status": "ready",
            "track": "Summer Song",
            "artist": "The Band",
            "device_name": "Chili Dashboard",
            "is_playing": True,
        }


class FakeWalkingPad:
    def context_lines(self, calendar_events, now=None):
        _ = calendar_events, now
        return [
            "- Walking: ready; today 18/45 min and 0.9/3.0 km; 1 session(s); idle.",
            "- Walking goal: not yet met.",
        ]


class DashboardContextProviderTests(unittest.TestCase):
    def test_snapshot_includes_dashboard_data_for_openclaw(self):
        provider = DashboardContextProvider(
            sensor_service=FakeSensor(),
            light_service=FakeLightService(),
            calendar_service=FakeCalendar(),
            notion_service=FakeNotion(),
            spotify_service=FakeSpotify(),
            walkingpad_service=FakeWalkingPad(),
            now=lambda: datetime(2026, 7, 4, 1, 5, tzinfo=UTC),
        )

        context = provider()

        self.assertIn("Temperature: 24.3 C", context)
        self.assertIn("Light: last command on", context)
        self.assertIn("Calendar: ready", context)
        self.assertIn("2026-07-04 (Saturday): 1 event(s)", context)
        self.assertIn("Lunch", context)
        self.assertIn("Walking: ready", context)
        self.assertIn("Tasks: ready", context)
        self.assertIn("Water plants", context)
        self.assertIn("Spotify: ready; playing; Summer Song by The Band", context)


if __name__ == "__main__":
    unittest.main()
