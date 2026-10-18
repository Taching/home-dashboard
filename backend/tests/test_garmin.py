import asyncio
import unittest
from types import SimpleNamespace
from datetime import UTC, date, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import models  # noqa: F401
from app.database.session import Base
from app.api.training import _morning_message
from app.domain.garmin import GarminService, parse_day, recovery_hint, watch_line
from app.domain.wellbeing import WellbeingService


class FakeGarmin:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def get_user_summary(self, cdate: str) -> dict:
        self.calls.append(cdate)
        return {
            "totalSteps": 9123, "restingHeartRate": 52, "bodyBatteryHighestValue": 88,
            "bodyBatteryLowestValue": 21, "bodyBatteryMostRecentValue": 40, "averageStressLevel": -1,
        }

    def get_sleep_data(self, cdate: str) -> dict:
        return {"dailySleepDTO": {"sleepTimeSeconds": 7 * 3600 + 1800, "sleepScores": {"overall": {"value": 81}}}}

    def get_hrv_data(self, cdate: str) -> dict:
        return {"hrvSummary": {"lastNightAvg": 58, "status": "BALANCED"}}

    def get_activities_by_date(self, start: str, end: str) -> list:
        return [{
            "activityName": "Mita BJJ", "activityType": {"typeKey": "other"},
            "startTimeLocal": f"{start} 07:31:00", "duration": 5460.0, "averageHR": 142.0, "distance": 0,
        }]


def _factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class GarminTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = _factory()
        self.wellbeing = WellbeingService(session_factory=self.factory)
        self.fake = FakeGarmin()
        self.garmin = GarminService(self.factory, client_factory=lambda: self.fake, wellbeing=self.wellbeing)

    def test_parse_day_normalises_garmin_payloads(self) -> None:
        values = parse_day(
            self.fake.get_user_summary("2026-10-19"), self.fake.get_sleep_data("2026-10-19"),
            self.fake.get_hrv_data("2026-10-19"), self.fake.get_activities_by_date("2026-10-19", "2026-10-19"),
        )
        self.assertEqual(values["steps"], 9123)
        self.assertEqual(values["sleep_score"], 81)
        self.assertEqual(values["hrv_status"], "balanced")
        self.assertIsNone(values["stress_avg"])
        self.assertEqual(values["activities"][0]["duration_min"], 91)
        self.assertIsNone(values["activities"][0]["distance_km"])

    def test_parse_day_tolerates_missing_data(self) -> None:
        values = parse_day({}, None, None, None)
        self.assertIsNone(values["steps"])
        self.assertEqual(values["activities"], [])

    def test_sync_recent_stores_today_and_yesterday(self) -> None:
        now = datetime(2026, 10, 19, 1, tzinfo=UTC)
        self.assertEqual(self.garmin.sync_recent(now), 2)
        self.assertEqual(self.fake.calls, ["2026-10-18", "2026-10-19"])
        snap = self.garmin.snapshot(date(2026, 10, 19))
        self.assertEqual(snap["resting_hr"], 52)
        self.assertEqual(snap["sleep_hours"], 7.5)
        self.assertEqual(self.garmin.steps_for(date(2026, 10, 19)), 9123)

    def test_watch_fills_sleep_only_when_empty(self) -> None:
        self.wellbeing.record(date(2026, 10, 18), sleep_hours=6.0, source="daily-page")
        self.garmin.sync_recent(datetime(2026, 10, 19, 1, tzinfo=UTC))
        self.assertEqual(self.wellbeing.entry(date(2026, 10, 18))["sleep_hours"], 6.0)
        self.assertEqual(self.wellbeing.entry(date(2026, 10, 19))["sleep_hours"], 7.5)

    def test_week_summary_averages(self) -> None:
        self.garmin.sync_recent(datetime(2026, 10, 19, 1, tzinfo=UTC))
        summary = self.garmin.week_summary(date(2026, 10, 13), date(2026, 10, 19))
        self.assertEqual(summary["days"], 2)
        self.assertEqual(summary["resting_hr"], 52)
        self.assertEqual(summary["steps"], 9123)

    def test_auth_failure_drops_the_cached_client(self) -> None:
        class GarminConnectAuthenticationError(Exception):
            pass

        class Broken(FakeGarmin):
            def get_user_summary(self, cdate: str) -> dict:
                raise GarminConnectAuthenticationError("expired")

        garmin = GarminService(self.factory, client_factory=Broken, wellbeing=self.wellbeing)
        with self.assertRaises(GarminConnectAuthenticationError):
            garmin.sync_day(date(2026, 10, 19))
        self.assertIn("expired", garmin.last_error)
        self.assertIsNone(garmin._client)

    def test_watch_steps_count_toward_the_walk_goal(self) -> None:
        from app.domain.walkingpad import WalkingPadService

        self.garmin.sync_recent(datetime(2026, 10, 19, 1, tzinfo=UTC))
        pad = WalkingPadService(session_factory=self.factory, bridge_token="token")
        pad.use_watch_steps(self.garmin.steps_for)
        snapshot = pad.today(datetime(2026, 10, 19, 3, tzinfo=UTC))
        self.assertEqual(snapshot.watch_steps, 9123)
        self.assertEqual(snapshot.day_steps, 9123)
        self.assertTrue(snapshot.goal_met)


if __name__ == "__main__":
    unittest.main()


class MorningReportTests(unittest.TestCase):
    ROUGH = {"sleep_hours": 5.9, "sleep_score": 71, "resting_hr": 54, "hrv_last_night": 48,
             "hrv_status": "unbalanced", "body_battery_high": 27}

    def test_watch_line_waits_for_sleep(self) -> None:
        self.assertIsNone(watch_line(None))
        self.assertIsNone(watch_line({"steps": 300, "sleep_hours": None}))
        self.assertEqual(
            watch_line(self.ROUGH),
            "Watch: 5.9 h sleep (71) · RHR 54 · HRV 48 unbalanced · Body Battery 27",
        )

    def test_recovery_hint_only_on_a_rough_night(self) -> None:
        good = {"sleep_hours": 7.5, "hrv_status": "balanced", "body_battery_high": 80}
        self.assertIsNone(recovery_hint(good, rest_day=False))
        hint = recovery_hint(self.ROUGH, rest_day=False)
        self.assertTrue(hint.startswith("Short night, Body Battery only 27, HRV unbalanced"))
        self.assertIn("stays as planned", hint)
        self.assertIn("rest", recovery_hint(self.ROUGH, rest_day=True))

    def test_morning_message_pulls_fresh_watch_data(self) -> None:
        factory = _factory()
        garmin = GarminService(factory, client_factory=FakeGarmin)
        training = SimpleNamespace(for_date=lambda day: {"planned_type": "bjj_gi", "title": "BJJ"})
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
            garmin_service=garmin, training_service=training,
        )))
        message = asyncio.run(_morning_message(request, date(2026, 10, 19)))
        self.assertIn("/daily/2026-10-19", message)
        self.assertIn("Watch: 7.5 h sleep (81) · RHR 52 · HRV 58 balanced · Body Battery 88", message)
        self.assertNotIn("stays as planned", message)

    def test_morning_message_without_watch_is_unchanged(self) -> None:
        training = SimpleNamespace(for_date=lambda day: None)
        request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(training_service=training)))
        message = asyncio.run(_morning_message(request, date(2026, 10, 19)))
        self.assertTrue(message.startswith("Today's briefing is ready.\n"))
        self.assertIn("/daily/2026-10-19", message)
