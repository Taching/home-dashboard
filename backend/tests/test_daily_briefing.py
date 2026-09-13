import unittest
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.session import Base
from app.domain.wellbeing import WellbeingService


def test_session_factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class FakeCalendar:
    def events_for_range(self, day, days):
        start = datetime(day.year, day.month, day.day, 1, tzinfo=UTC)
        return "ready", start, [
            SimpleNamespace(
                external_id="meeting-1", title="Standup", start_at=start,
                end_at=start + timedelta(hours=1), is_all_day=False, source="apple_calendar",
            ),
            SimpleNamespace(
                external_id="training-1", title="Strength A", start_at=start,
                end_at=start + timedelta(hours=1), is_all_day=False, source="training",
            ),
        ]


class FakeTraining:
    def __init__(self):
        self.reconciled = 0
        self.updated = []
        self.status = "planned"

    def for_date(self, day):
        return {
            "id": "session-1", "title": "Strength A + Intervals", "reason": "Build strength safely.",
            "coach_focus": ["Leave two reps in reserve."], "exercises": [],
            "estimated_minutes": 60, "intensity": "normal", "planned_type": "strength_a",
            "status": self.status,
        }

    def reconcile(self):
        self.reconciled += 1

    def update_session(self, session_id, **values):
        self.updated.append((session_id, values))
        self.status = values.get("status", self.status)


class FakeOpenClaw:
    def __init__(self, configured=True):
        self.configured_flag = configured
        self.sent = []

    def configured(self):
        return self.configured_flag

    def send(self, message, *, deliver=True):
        self.sent.append((message, deliver))
        return {"delivery_status": "completed", "reply": "Train steadily, then protect recovery."}


class DailyBriefingApiTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 9, 14)
        self.factory = test_session_factory()
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.wellbeing_service = WellbeingService(
            self.factory, timezone_name="Asia/Tokyo",
            sober_baseline_date=self.day - timedelta(days=1), sober_baseline_days=7,
        )
        self.app.state.calendar_bridge_service = FakeCalendar()
        self.app.state.training_service = FakeTraining()
        self.app.state.weekly_service = SimpleNamespace(sunday_check_in=lambda day, training: None)
        self.app.state.openclaw_service = FakeOpenClaw()
        self.client = TestClient(self.app)

    def test_daily_page_combines_workout_meetings_and_sobriety(self):
        response = self.client.get(f"/api/v1/daily/{self.day.isoformat()}")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["workout"]["title"], "Strength A + Intervals")
        self.assertEqual([item["title"] for item in payload["calendar"]["meetings"]], ["Standup"])
        self.assertEqual(payload["sobriety"]["days"], 7)
        self.assertFalse(payload["preview"])
        self.assertFalse(payload["check_in_status"]["morning_complete"])
        self.assertIn("today", payload)
        self.assertIn("tomorrow", payload)
        self.assertEqual(payload["today"]["meetings"][0]["title"], "Standup")
        self.assertTrue(payload["tomorrow"]["headline"].startswith("Tomorrow:"))

    def test_strength_preview_does_not_change_the_saved_plan(self):
        response = self.client.get(
            f"/api/v1/daily/{self.day.isoformat()}?preview=strength_a",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["preview"])
        self.assertEqual(payload["workout"]["planned_type"], "strength_a")
        self.assertEqual(payload["workout"]["status"], "preview")
        self.assertEqual(self.app.state.training_service.updated, [])

    def test_submission_updates_one_daily_row_and_returns_openclaw_advice(self):
        response = self.client.post(
            f"/api/v1/daily/{self.day.isoformat()}/check-in",
            json={
                "sleep_hours": 7.5, "sleep_quality": 4, "fatigue": 2,
                "soreness": 2, "grip_fatigue": 3, "pain": False,
                "readiness": 4, "workout_status": "completed", "sober": True,
                "notes": "Busy afternoon.",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["check_in"]["sober"])
        self.assertEqual(payload["check_in"]["daily_notes"], "Busy afternoon.")
        self.assertIsNotNone(payload["check_in_status"]["last_saved_at"])
        self.assertFalse(payload["check_in_status"]["morning_complete"])
        self.assertTrue(payload["check_in_status"]["end_of_day_complete"])
        self.assertEqual(self.app.state.training_service.reconciled, 1)
        self.assertEqual(
            self.app.state.training_service.updated,
            [("session-1", {"status": "completed"})],
        )
        self.assertEqual(self.app.state.openclaw_service.sent, [])

        correction = self.client.post(
            f"/api/v1/daily/{self.day.isoformat()}/check-in", json={"readiness": 3},
        )
        self.assertEqual(correction.status_code, 200)
        self.assertEqual(correction.json()["check_in"]["sleep_hours"], 7.5)
        self.assertEqual(correction.json()["check_in"]["readiness"], 3)

    def test_empty_submission_is_rejected(self):
        response = self.client.post(
            f"/api/v1/daily/{self.day.isoformat()}/check-in", json={},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
