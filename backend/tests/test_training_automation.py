import unittest
from datetime import UTC, date, datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.session import Base
from app.database import models  # noqa: F401
from app.domain.activity_feed import ActivityFeedService
from app.domain.calendar_bridge import CalendarBridgeService, CalendarEvent
from app.domain.chili_notify import ChiliNotifyService
from app.domain.training_logs import TrainingService
from app.domain.walkingpad import WalkingPadService
from app.domain.weekly import WeeklyService
from app.domain.wellbeing import WellbeingService


def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class FakePlanner:
    def for_date(self, day):
        return {
            "id": "session-1",
            "title": "Strength A + Intervals",
            "reason": "Build.",
            "coach_focus": [],
            "exercises": [{"name": "Back Squat", "done": False}],
            "estimated_minutes": 60,
            "intensity": "normal",
            "planned_type": "strength_a",
            "status": "planned",
            "notes": None,
        }

    def log_workout_check(self, session_id, *, exercises=None, note=None):
        return {
            "id": session_id,
            "title": "Strength A + Intervals",
            "status": "completed",
            "planned_type": "strength_a",
            "notes": note,
        }

    def overview(self, now=None):
        return {"week": [], "phase": "build_october"}

    def calendar_plan(self, now=None, days=30):
        stamp = datetime.now(UTC)
        return [{
            "session_id": "session-1",
            "title": "Gym (Strength A)",
            "start_at": stamp.isoformat(),
            "end_at": stamp.isoformat(),
            "is_all_day": False,
            "notes": "Managed by Chili Training\nchili-training:session-1",
        }]

    def reconcile(self):
        return None


class FakeOpenClaw:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.notified: list[str] = []

    def configured(self) -> bool:
        return True

    def send(self, message: str) -> dict[str, str | None]:
        self.sent.append(message)
        return {"delivery_status": "started", "reply": f"forwarded:{message}"}

    def notify_user(self, message: str) -> dict[str, str | None]:
        self.notified.append(message)
        return {"delivery_status": "sent", "reply": None}


class TrainingAutomationApiTests(unittest.TestCase):
    def setUp(self) -> None:
        factory = test_session_factory()
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.activity_feed_service = ActivityFeedService()
        self.app.state.training_log_service = TrainingService(session_factory=factory)
        self.app.state.training_service = FakePlanner()
        self.app.state.wellbeing_service = WellbeingService(
            factory, timezone_name="Asia/Tokyo",
            sober_baseline_date=date(2026, 8, 22), sober_baseline_days=7,
        )
        self.app.state.weekly_service = WeeklyService(session_factory=factory)
        self.app.state.walkingpad_service = WalkingPadService(
            session_factory=factory,
            bridge_token="bridge-token",
        )
        self.app.state.calendar_bridge_service = CalendarBridgeService(
            session_factory=factory,
            bridge_token="calendar-token",
        )
        self.app.state.openclaw_service = FakeOpenClaw()
        self.app.state.chili_notify_service = ChiliNotifyService(factory)
        self.client = TestClient(self.app)
        self.token = "automation-token"

    def test_lists_plans_and_today(self) -> None:
        plans = self.client.get("/api/v1/training/plans")
        self.assertEqual(plans.status_code, 200)
        slugs = [plan["slug"] for plan in plans.json()["plans"]]
        self.assertIn("strength_a", slugs)
        self.assertIn("sober", slugs)
        today = self.client.get("/api/v1/training/today")
        self.assertEqual(today.status_code, 200)
        self.assertIn(today.json()["suggested_source"], {"calendar", "week"})

    @patch("app.api.router.settings")
    def test_browser_and_automation_log(self, settings) -> None:
        settings.dashboard_automation_token = self.token
        ui = self.client.post(
            "/api/v1/training/log",
            json={"kind": "grip", "completed": "yes", "feeling": "normal"},
        )
        self.assertEqual(ui.status_code, 200)
        self.assertEqual(ui.json()["status"], "logged")
        automation = self.client.post(
            "/api/v1/automation/training/log",
            headers={"Authorization": f"Bearer {self.token}"},
            json={"message": "did Strength B, felt fresh"},
        )
        self.assertEqual(automation.status_code, 200)
        self.assertEqual(automation.json()["log"]["kind"], "strength_b")
        self.assertEqual(automation.json()["log"]["source"], "automation")

    @patch("app.api.router.settings")
    def test_openclaw_chat_logs_training_without_sending(self, settings) -> None:
        settings.dashboard_automation_token = self.token
        response = self.client.post(
            "/api/v1/openclaw/messages",
            json={"message": "did BJJ 3x5, felt tired"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertIn("Logged bjj", response.json()["reply"] or "")
        today = self.client.get("/api/v1/training/today").json()
        self.assertEqual(today["logs"][0]["kind"], "bjj")

    @patch("app.api.router.settings")
    def test_walk_messages_still_use_walkingpad(self, settings) -> None:
        settings.dashboard_automation_token = self.token
        response = self.client.post(
            "/api/v1/openclaw/messages",
            json={"message": "I walked 20 min and 1.5 km today"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Logged walk", response.json()["reply"] or "")
        today = self.client.get("/api/v1/training/today").json()
        self.assertEqual(today["logs"], [])

    @patch("app.api.router.settings")
    def test_training_plan_uses_same_program_for_calendar(self, settings) -> None:
        settings.apple_calendar_bridge_token = "calendar-token"
        settings.training_calendar_name = "Chili Training"
        response = self.client.get(
            "/api/v1/calendar/apple/training-plan",
            headers={"X-Chili-Bridge-Token": "calendar-token"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["calendar_name"], "Chili Training")
        self.assertTrue(body["events"])
        self.assertIn("chili-training:", body["events"][0]["notes"])

    def test_today_prefers_calendar_titles(self) -> None:
        now = datetime.now(UTC)
        self.app.state.calendar_bridge_service.replace_snapshot(
            [
                CalendarEvent(
                    "grip-today",
                    "Grip",
                    now,
                    now.replace(hour=min(now.hour + 1, 23)),
                )
            ],
            now,
        )
        today = self.client.get("/api/v1/training/today").json()
        self.assertEqual(today["suggested_source"], "calendar")
        self.assertEqual(today["suggested"][0]["slug"], "grip")

    def test_daily_workout_and_sober_are_separate_posts(self) -> None:
        workout = self.client.post(
            "/api/v1/daily/2026-09-15/workout",
            json={
                "kind": "strength_a",
                "exercises": [
                    {"name": "Back Squat", "done": True},
                    {"name": "Bench Press", "done": True},
                ],
                "note": "felt hard",
            },
        )
        self.assertEqual(workout.status_code, 200)
        self.assertEqual(workout.json()["status"], "logged")
        self.assertIn("Strength A", workout.json()["message"])
        advice = workout.json()["advice"]
        self.assertTrue(advice)
        self.assertNotIn("/daily/", advice)
        self.assertEqual(self.app.state.openclaw_service.sent, [])
        self.assertEqual(len(self.app.state.openclaw_service.notified), 1)
        notify = self.app.state.openclaw_service.notified[0]
        self.assertTrue(notify.startswith("http://127.0.0.1:8080/daily/2026-09-15\n\n"))
        self.assertIn(advice, notify)
        sober = self.client.post(
            "/api/v1/daily/2026-09-15/sober",
            json={"sober": True, "note": "evening"},
        )
        self.assertEqual(sober.status_code, 200)
        self.assertEqual(sober.json()["status"], "logged")
        self.assertEqual(sober.json()["briefing"]["sobriety"]["answered"], "yes")
        daily = self.client.get("/api/v1/daily/2026-09-13").json()
        self.assertIsNone(daily["sleep"])
        self.assertIsNotNone(daily["sunday"])
        self.assertEqual(daily["sunday"]["week_ending"], "2026-09-13")

    def test_sunday_review_compares_weight(self) -> None:
        first = self.client.post(
            "/api/v1/daily/2026-09-06/sunday",
            json={"weight_kg": 82.8},
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            "/api/v1/daily/2026-09-13/sunday",
            json={"weight_kg": 82.4, "note": "keep the week as-is"},
        )
        self.assertEqual(second.status_code, 200)
        body = second.json()
        self.assertEqual(body["sunday"]["previous_weight_kg"], 82.8)
        self.assertEqual(body["sunday"]["delta_kg"], -0.4)
        self.assertIn("down 0.4 kg", body["message"])
        self.assertEqual(self.app.state.openclaw_service.sent, [])
        self.assertTrue(any(item.startswith("http://127.0.0.1:8080/daily/2026-09-13") for item in self.app.state.openclaw_service.notified))
        self.assertNotEqual(body["advice"], body["message"])
        self.assertNotIn("/daily/", body["advice"] or "")

    def test_workout_page_log_completes_planner_and_returns_advice(self) -> None:
        response = self.client.post(
            "/api/v1/training/workout",
            json={
                "kind": "strength_a",
                "exercises": [
                    {"name": "Warm-up", "done": True},
                    {"name": "Back Squat", "done": True},
                ],
                "note": "felt easy except the bike",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "logged")
        self.assertTrue(body["advice"])
        self.assertIn("felt easy except the bike", body["advice"])
        today = self.client.get("/api/v1/training/today").json()
        self.assertEqual(today["logs"][0]["kind"], "strength_a")
        self.assertTrue(today["advice"])


if __name__ == "__main__":
    unittest.main()
