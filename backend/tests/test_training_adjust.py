import json
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
from app.domain.training.adjust import CalendarAdjuster, match_calendar_adjust_fast_path
from app.domain.training.service import TrainingService


def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class CalendarAdjustFastPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.today = date(2026, 9, 13)

    def test_strength_a_today_and_skip_tomorrow(self) -> None:
        analysis = match_calendar_adjust_fast_path(
            "I want Strength A today, can't make tomorrow morning",
            self.today,
        )
        self.assertIsNotNone(analysis)
        assert analysis is not None
        self.assertEqual([item.op for item in analysis.mutations], ["gym_today", "decline_bjj"])
        self.assertEqual(analysis.mutations[0].date, self.today)
        self.assertEqual(analysis.mutations[0].workout_type, "strength_a")
        self.assertEqual(analysis.mutations[1].date, date(2026, 9, 14))

    def test_strength_b_on_named_day(self) -> None:
        analysis = match_calendar_adjust_fast_path("put Strength B on Tuesday", self.today)
        self.assertIsNotNone(analysis)
        assert analysis is not None
        self.assertEqual(analysis.mutations[0].op, "gym_today")
        self.assertEqual(analysis.mutations[0].workout_type, "strength_b")
        self.assertEqual(analysis.mutations[0].date, date(2026, 9, 15))

    def test_rest_today_and_move_gym(self) -> None:
        rest = match_calendar_adjust_fast_path("rest today", self.today)
        move = match_calendar_adjust_fast_path("move gym to Friday", self.today)
        self.assertEqual(rest.mutations[0].op, "rest_today")
        self.assertEqual(move.mutations[0].op, "move_gym")
        self.assertEqual(move.mutations[0].to_date, date(2026, 9, 18))

    def test_unknown_instruction_is_none(self) -> None:
        self.assertIsNone(match_calendar_adjust_fast_path("what is on the wall?", self.today))

    def test_missed_bjj_did_grip_instead(self) -> None:
        analysis = match_calendar_adjust_fast_path(
            "I didn't do jiu-jitsu this morning, instead I did grip training",
            date(2026, 9, 15),
        )
        self.assertIsNotNone(analysis)
        assert analysis is not None
        self.assertEqual(analysis.mutations[0].op, "did_instead")
        self.assertEqual(analysis.mutations[0].workout_type, "grip")
        self.assertEqual(analysis.mutations[0].date, date(2026, 9, 15))


class CalendarAdjusterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = factory()
        self.now = datetime(2026, 9, 13, 3, tzinfo=UTC)  # Sunday 12:00 JST
        self.training = TrainingService(self.factory, timezone_name="Asia/Tokyo")
        self.training.bootstrap(self.now)
        self.adjuster = CalendarAdjuster(timezone_name="Asia/Tokyo", api_key="")

    def test_strength_a_today_updates_plan_and_calendar(self) -> None:
        result = self.adjuster.adjust(
            "I want Strength A today, can't make tomorrow morning",
            training=self.training,
            notion_sync=type("Sync", (), {"sync_due": lambda inner_self, limit=25: 2})(),
            now=self.now,
        )
        overview = result["overview"]
        today = overview["today"]
        self.assertEqual(result["analysis"]["source"], "fast_path")
        self.assertEqual(today["planned_type"], "strength_a")
        self.assertEqual(today["title"], "Gym (Strength A)")
        self.assertFalse(today["is_all_day"])
        coming_strength = [
            item for item in overview["upcoming"]
            if item["planned_type"] == "strength_a" and item["status"] == "planned"
        ]
        self.assertEqual(len(coming_strength), 1)
        self.assertEqual(coming_strength[0]["id"], today["id"])
        monday_sessions = [
            item for item in overview["upcoming"]
            if self.training._local_date(item["start_at"]) == date(2026, 9, 14)
        ]
        self.assertFalse(any(str(item["planned_type"]).startswith("bjj_") for item in monday_sessions))
        self.assertEqual(result["notion_synced"], 2)
        self.assertTrue(any(event["session_id"] == today["id"] for event in result["calendar_events"]))
        decision = result["decision"]
        self.assertTrue(any("Gym (Strength A)" in item for item in decision["how"]))
        self.assertTrue(any("BJJ is off" in item for item in decision["how"]))
        self.assertTrue(any("coming week" in item for item in decision["why"]))
        self.assertIn("How", result["notification"])
        self.assertIn("Why", result["notification"])
        self.assertEqual(result["overview"]["last_adjustment"]["id"], decision["id"])

    def test_unclear_instruction_without_openai_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            self.adjuster.adjust("hmm maybe later", training=self.training, now=self.now)

    @patch("app.domain.training.adjust.httpx.post")
    def test_gpt_path_rests_today(self, post) -> None:
        post.return_value.raise_for_status = lambda: None
        post.return_value.json.return_value = {
            "output_text": json.dumps({
                "summary": "Make Sunday rest.",
                "mutations": [{
                    "op": "rest_today",
                    "date": "2026-09-13",
                    "to_date": None,
                    "workout_type": None,
                    "session_id": None,
                    "start_at": None,
                    "end_at": None,
                    "fatigue_state": None,
                    "task_id": None,
                    "task_title": None,
                    "event_id": None,
                    "hard": None,
                }],
            }),
        }
        adjuster = CalendarAdjuster(timezone_name="Asia/Tokyo", api_key="sk-test")
        existing = self.training.for_date(date(2026, 9, 13))
        if existing is None:
            self.training.schedule_gym(date(2026, 9, 13), "strength_a", now=self.now)
        result = adjuster.adjust("make Sunday a rest day please", training=self.training, now=self.now)
        self.assertEqual(result["analysis"]["source"], "gpt")
        self.assertEqual(result["overview"]["today"]["planned_type"], "rest")


class CalendarAdjustApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = factory()
        self.now = datetime(2026, 9, 13, 3, tzinfo=UTC)
        self.app = FastAPI()
        self.app.include_router(api_router, prefix="/api/v1")
        self.app.state.training_service = TrainingService(self.factory, timezone_name="Asia/Tokyo")
        self.app.state.training_service.bootstrap(self.now)
        self.app.state.calendar_adjuster = CalendarAdjuster(timezone_name="Asia/Tokyo", api_key="")
        self.app.state.training_notion_sync = type("Sync", (), {"sync_due": lambda self, limit=25: 1})()
        self.app.state.calendar_bridge_service = type("Cal", (), {"configured": lambda self: False})()
        self.client = TestClient(self.app)

    @patch("app.api.training.settings")
    def test_training_adjust_endpoint(self, settings) -> None:
        settings.dashboard_automation_token = "automation-token"
        response = self.client.post(
            "/api/v1/automation/training/adjust",
            headers={"Authorization": "Bearer automation-token"},
            json={"instruction": "I want Strength A today"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertEqual(body["analysis"]["mutations"][0]["op"], "gym_today")
        self.assertEqual(body["analysis"]["mutations"][0]["workout_type"], "strength_a")
        self.assertIn("How", body["notification"])
        self.assertEqual(body["notify"]["status"], "not_configured")
