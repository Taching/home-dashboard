import unittest
from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.core.settings import settings
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
    def __init__(self) -> None:
        self.planned_type = "strength_a"
        self.status = "planned"
        self.logged: list[tuple[str, list | None, str | None]] = []

    def for_date(self, day):
        rest = self.planned_type == "rest"
        return {
            "id": "session-1",
            "title": "Rest" if rest else "Strength A + Intervals",
            "reason": "Build.",
            "coach_focus": [],
            "exercises": [{"name": "Back Squat", "done": False}],
            "estimated_minutes": 60,
            "intensity": "normal",
            "planned_type": self.planned_type,
            "status": "planned" if rest else self.status,
            "notes": None,
        }

    def log_workout_check(self, session_id, *, exercises=None, note=None):
        self.logged.append((session_id, exercises, note))
        self.status = "completed"
        return {
            "id": session_id,
            "title": "Strength A + Intervals",
            "status": "completed",
            "planned_type": self.planned_type,
            "notes": note,
        }

    def log_session_result(self, session_id, **kwargs):
        self.last_result = kwargs
        self.logged.append((session_id, kwargs.get("exercises"), kwargs.get("notes")))
        self.status = kwargs.get("status") or "completed"
        return {
            "id": session_id,
            "title": "BJJ Normal" if str(self.planned_type).startswith("bjj_") else "Strength A + Intervals",
            "status": self.status,
            "planned_type": self.planned_type,
            "notes": kwargs.get("notes"),
            "result": {
                "bjj_rounds": kwargs.get("bjj_rounds"),
                "perceived_intensity": kwargs.get("perceived_intensity"),
            },
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
        self.assertTrue(workout.json()["briefing"]["answers"]["all_answered"])
        self.assertEqual(len(self.app.state.openclaw_service.sent), 1)
        self.assertGreaterEqual(len(self.app.state.openclaw_service.notified), 1)
        notify = self.app.state.openclaw_service.notified[0]
        self.assertIn(f"{settings.public_base_url()}/daily/2026-09-15", notify)
        self.assertFalse(notify.startswith("http"))
        sober = self.client.post(
            "/api/v1/daily/2026-09-15/sober",
            json={"sober": True, "note": "evening"},
        )
        self.assertEqual(sober.status_code, 200)
        self.assertEqual(sober.json()["status"], "logged")
        self.assertEqual(sober.json()["briefing"]["sobriety"]["answered"], "yes")
        self.assertTrue(sober.json()["briefing"]["answers"]["all_answered"])
        self.assertEqual(len(self.app.state.openclaw_service.sent), 1)
        self.assertIn("finished every answer", self.app.state.openclaw_service.sent[0])
        self.assertEqual(len(self.app.state.openclaw_service.notified), 2)
        self.assertTrue(sober.json()["briefing"]["chili_reply"])
        again = self.client.post("/api/v1/daily/2026-09-15/close")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(len(self.app.state.openclaw_service.sent), 1)
        daily = self.client.get("/api/v1/daily/2026-09-13").json()
        self.assertIsNone(daily["sleep"]["hours"])
        self.assertIsNone(daily["weekly"])
        monday = self.client.get("/api/v1/daily/2026-09-14").json()
        self.assertIsNotNone(monday["weekly"])
        self.assertEqual(monday["weekly"]["week_ending"], "2026-09-13")

    def test_daily_sleep_is_optional_and_never_closes_the_day(self) -> None:
        sleep = self.client.post(
            "/api/v1/daily/2026-09-16/sleep",
            json={"hours": 6.5},
        )
        self.assertEqual(sleep.status_code, 200)
        self.assertEqual(sleep.json()["status"], "logged")
        self.assertEqual(sleep.json()["briefing"]["sleep"]["hours"], 6.5)
        # Logging sleep alone must not ask Chili anything or close the day —
        # it is optional context, not a readiness form.
        self.assertEqual(self.app.state.openclaw_service.sent, [])
        self.assertEqual(self.app.state.openclaw_service.notified, [])
        daily = self.client.get("/api/v1/daily/2026-09-16").json()
        self.assertEqual(daily["sleep"]["hours"], 6.5)

    def test_daily_weight_is_optional_and_never_closes_the_day(self) -> None:
        response = self.client.post("/api/v1/daily/2026-09-16/weight", json={"weight_kg": 83.64})
        self.assertEqual(response.status_code, 200)
        cut = response.json()["briefing"]["cut"]
        self.assertEqual(cut["today_kg"], 83.6)
        self.assertEqual(cut["seven_day_average_kg"], 83.6)
        self.assertIn(cut["nutrition"]["kcal"], {2000, 2300})
        self.assertEqual(self.app.state.openclaw_service.sent, [])
        self.assertEqual(self.app.state.openclaw_service.notified, [])
        self.assertEqual(self.client.post("/api/v1/daily/2026-09-16/weight", json={"weight_kg": 10}).status_code, 422)

    def test_monday_check_in_compares_seven_day_averages(self) -> None:
        for offset in range(14):
            day = date(2026, 8, 31) + timedelta(days=offset)
            weight = 82.8 if offset < 7 else 82.4
            self.assertEqual(self.client.post(f"/api/v1/daily/{day.isoformat()}/weight", json={"weight_kg": weight}).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/daily/2026-09-13/weekly", json={"energy": 3, "hunger": 3, "bjj_performance": 3}).status_code, 400)
        response = self.client.post(
            "/api/v1/daily/2026-09-14/weekly",
            json={"energy": 4, "hunger": 3, "bjj_performance": 4, "waist_cm": 88, "note": "keep the week as-is"},
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["weekly"]["previous_weight_kg"], 82.8)
        self.assertEqual(body["weekly"]["delta_kg"], -0.4)
        self.assertEqual(body["weekly"]["waist_cm"], 88)
        self.assertIn("down 0.4 kg", body["message"])
        # One weekly-training-review agent turn per submission.
        self.assertEqual(len(self.app.state.openclaw_service.sent), 1)
        self.assertIn("Monday check-in", self.app.state.openclaw_service.sent[-1])
        self.assertIsNotNone(body["weekly"]["coach_review"])
        self.assertTrue(any(f"{settings.public_base_url()}/daily/2026-09-14" in item for item in self.app.state.openclaw_service.notified))
        self.assertTrue(any(item.startswith("Monday check-in saved.") for item in self.app.state.openclaw_service.notified))
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

    def test_rest_day_close_asks_chili_without_a_sober_answer(self) -> None:
        self.app.state.training_service.planned_type = "rest"
        closed = self.client.post("/api/v1/daily/2026-09-15/close")
        self.assertEqual(closed.status_code, 200)
        self.assertTrue(closed.json()["answers"]["all_answered"])
        self.assertTrue(closed.json()["chili_reply"])
        self.assertEqual(len(self.app.state.openclaw_service.sent), 1)

    def test_daily_bjj_report_saves_rounds(self) -> None:
        self.app.state.training_service.planned_type = "bjj_normal"
        response = self.client.post(
            "/api/v1/daily/2026-09-15/workout",
            json={
                "kind": "bjj_normal",
                "status": "completed",
                "bjj_rounds": 5,
                "perceived_intensity": "hard",
                "note": "grip was fried",
                "exercises": [{"name": "Live rounds", "done": True}],
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "logged")
        self.assertEqual(body["workout"]["status"], "completed")
        self.assertEqual(body["workout"]["result"]["bjj_rounds"], 5)
        self.assertEqual(body["workout"]["result"]["perceived_intensity"], "hard")
        self.assertEqual(self.app.state.training_service.logged[0][2], "grip was fried")

    def test_daily_strength_report_saves_load_rpe_and_intervals(self) -> None:
        response = self.client.post(
            "/api/v1/daily/2026-09-15/workout",
            json={
                "kind": "strength_a",
                "status": "completed",
                "exercises": [
                    {"name": "Back Squat", "done": True, "actual_load": 125, "rpe": 8},
                    {"name": "Bench Press", "done": False, "actual_load": 90, "rpe": 9},
                ],
                "interval_watts": [{"round": 1, "watts": 220}, {"round": 2, "watts": 200}],
            },
        )
        self.assertEqual(response.status_code, 200)
        kwargs = self.app.state.training_service.last_result
        squat = next(item for item in kwargs["exercises"] if item["name"] == "Back Squat")
        bench = next(item for item in kwargs["exercises"] if item["name"] == "Bench Press")
        self.assertEqual(squat["actual_load"], 125)
        self.assertEqual(squat["rpe"], 8)
        self.assertEqual(squat["status"], "completed")
        self.assertNotIn("actual_load", bench)
        self.assertEqual(bench["status"], "skipped")
        self.assertEqual(kwargs["session_rpe"], 8)
        self.assertEqual(kwargs["metrics"], [
            {"metric_type": "bike_watts", "sequence": 1, "value": 220, "unit": "W"},
            {"metric_type": "bike_watts", "sequence": 2, "value": 200, "unit": "W"},
        ])

    def test_daily_workout_rejects_mismatched_kind(self) -> None:
        response = self.client.post(
            "/api/v1/daily/2026-09-15/workout",
            json={
                "kind": "strength_b",
                "exercises": [{"name": "Warm-up", "done": True}],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not today's session", response.json()["detail"])
        self.assertEqual(self.app.state.training_service.logged, [])

    def test_daily_workout_rejects_rest_day(self) -> None:
        self.app.state.training_service.planned_type = "rest"
        response = self.client.post(
            "/api/v1/daily/2026-09-15/workout",
            json={
                "kind": "rest",
                "exercises": [{"name": "Full rest", "done": True}],
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("no workout to log", response.json()["detail"])
        self.assertEqual(self.app.state.training_service.logged, [])


if __name__ == "__main__":
    unittest.main()
