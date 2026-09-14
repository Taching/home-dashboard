import unittest
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import patch
from zoneinfo import ZoneInfo
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.router import api_router
from app.database.session import Base
from app.domain.daily_plan import DailyPlanService, advice_window_name, compose_today_advice
from app.domain.wellbeing import WellbeingService


def test_session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class FakeCalendar:
    def events_for_range(self, day, days):
        start = datetime(day.year, day.month, day.day, 1, tzinfo=UTC)
        return "ready", start, [
            SimpleNamespace(
                external_id="meeting-1", title="LCA standup", start_at=start,
                end_at=start + timedelta(hours=1), is_all_day=False, source="apple_calendar",
            ),
        ]

    def reschedule_event(self, event_id, start_at, end_at=None):
        end = end_at or start_at + timedelta(hours=1)
        return SimpleNamespace(
            external_id=event_id, title="LCA standup", start_at=start_at, end_at=end,
        )


class FakeTraining:
    def __init__(self):
        self.replaced = []
        self.updated = []
        self.scheduled = []
        self.reconciled = 0
        self.session = {
            "id": "session-1", "title": "Strength A + Intervals", "planned_type": "strength_a",
            "status": "planned", "estimated_minutes": 60, "intensity": "normal",
            "start_at": "2026-09-14T07:30:00+09:00", "is_all_day": False,
            "coach_focus": ["Leave two reps in reserve."], "reason": "Build.",
        }

    def for_date(self, day):
        return dict(self.session)

    def replace_session(self, session_id, workout_type):
        self.replaced.append((session_id, workout_type))
        self.session = {**self.session, "planned_type": workout_type, "title": "Rest"}
        return self.session

    def update_session(self, session_id, **values):
        self.updated.append((session_id, values))
        return self.session

    def overview(self, now=None):
        return {
            "generated_at": "2026-09-14T07:00:00+09:00",
            "phase": "build_october",
            "week_start": "2026-09-14",
            "week": [dict(self.session)],
            "upcoming": [dict(self.session)],
            "countdowns": [{
                "id": "oct", "name": "All Japan", "start_date": "2026-10-10",
                "end_date": "2026-10-11", "days_remaining": 26,
            }],
            "compliance": {"bjj": {"completed": 0, "target": 3}},
            "week_quality": "good",
            "bjj_candidates": [],
            "trends": {"bike_decay": [], "bjj_capacity": [], "weight_7d_average": 81.4},
            "readiness": {"date": "2026-09-14", "level": "normal", "weight_kg": 81.2},
            "tomorrow_prescription": {
                "session": self.session["planned_type"],
                "time": "07:30",
                "work": "Squat, bench, then bike intervals.",
                "focus": "Leave two reps in reserve",
                "why": "Placed around BJJ.",
                "weekly_status": {"bjj": {"completed": 0, "target": 3}},
            },
        }

    def record_fatigue(self, day, state, now=None):
        return {"fatigue_state": state}

    def confirm_bjj(self, day, hard=None, now=None):
        return {"planned_type": "bjj_normal", "day": day.isoformat()}

    def decline_bjj(self, day, now=None):
        return {"status": "declined", "day": day.isoformat()}

    def schedule_gym(self, day, workout_type, now=None):
        self.scheduled.append((day, workout_type))
        self.session = {**self.session, "planned_type": workout_type, "title": f"Gym ({workout_type})"}
        return {**self.session, "day": day.isoformat()}

    def place_session(self, day, workout_type, now=None):
        return self.schedule_gym(day, workout_type, now=now)

    def calendar_plan(self, now=None, days=30):
        return []

    def reconcile(self, now=None):
        self.reconciled += 1


class FakeWalking:
    def today(self, now=None):
        return SimpleNamespace(goal_met=False, total_steps=2500, goal_steps=10000)

    def reminder(self, events, now=None, snapshot=None):
        self.snapshot = snapshot
        return SimpleNamespace(
            active=True,
            message="You've walked 2,500 of 10,000 steps today.",
            dedupe_key="walk:window:2026-09-14:meeting-1",
        )


class FakeNotion:
    def __init__(self):
        self.completed = []
        self.task = SimpleNamespace(
            id="task-1", title="Prepare HMO deck", due_at=None, is_overdue=False,
            priority="High", task_type="Work", status="To do",
        )

    def today(self):
        return "ready", datetime.now(UTC), [self.task]

    def complete(self, page_id):
        self.completed.append(page_id)


class DailyPlanTests(unittest.TestCase):
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
        self.app.state.notion_service = FakeNotion()
        self.app.state.weekly_service = SimpleNamespace(sunday_check_in=lambda day, training: None)
        self.app.state.walkingpad_service = FakeWalking()
        self.client = TestClient(self.app)
        self.service = DailyPlanService("Asia/Tokyo")

    def test_plan_endpoint_matches_daily_shape(self):
        daily = self.client.get(f"/api/v1/daily/{self.day.isoformat()}").json()
        plan = self.client.get(f"/api/v1/plan/{self.day.isoformat()}").json()
        self.assertEqual(daily["today"]["headline"], plan["today"]["headline"])
        self.assertEqual(plan["today"]["tasks"][0]["title"], "Prepare HMO deck")
        self.assertIn("LCA", plan["tomorrow"]["preparation"])
        self.assertEqual(plan["tomorrow"]["prescription"]["session"], "strength_a")
        self.assertEqual(plan["tomorrow"]["week_quality"], "good")
        self.assertIn(plan["advice_window"], {"morning", "lunch", "evening"})
        self.assertEqual(daily["advice_window"], plan["advice_window"])
        self.assertEqual(plan["phase"], "build_october")
        self.assertEqual(plan["week_start"], "2026-09-14")
        self.assertEqual(plan["week"][0]["planned_type"], "strength_a")
        self.assertEqual(plan["upcoming"][0]["title"], "Strength A + Intervals")
        self.assertEqual(plan["countdowns"][0]["id"], "oct")
        self.assertEqual(plan["trends"]["weight_7d_average"], 81.4)
        self.assertEqual(plan["readiness"]["weight_kg"], 81.2)
        self.assertEqual(plan["walk_reminder"]["dedupe_key"], "walk:window:2026-09-14:meeting-1")
        self.assertTrue(plan["walk_reminder"]["active"])
        self.assertEqual(self.app.state.walkingpad_service.snapshot.total_steps, 2500)
        self.assertEqual(plan["notion"]["status"], "ready")
        self.assertEqual(plan["notion"]["tasks"][0]["title"], "Prepare HMO deck")
        self.assertIsNotNone(plan["notion"]["synced_at"])

    def test_rest_today_replaces_and_returns_plan(self):
        result = self.service.rest_today(self.app.state.training_service, self.day)
        self.assertEqual(result["planned_type"], "rest")
        self.assertEqual(self.app.state.training_service.replaced, [("session-1", "rest")])

    def test_complete_task_by_title(self):
        result = self.service.complete_task(self.app.state.notion_service, title="HMO")
        self.assertEqual(result["id"], "task-1")
        self.assertEqual(self.app.state.notion_service.completed, ["task-1"])

    def _rest_advice(self, hour: int, minute: int = 0, **overrides):
        tokyo = ZoneInfo("Asia/Tokyo")
        now = datetime(2026, 9, 13, hour, minute, tzinfo=tokyo)
        payload = dict(
            stored="Today is Rest. A complete rest day protects BJJ quality and adaptation.",
            training={"planned_type": "rest", "title": "Rest", "is_all_day": True},
            meetings=[],
            tasks=[{"title": "Evaluation update", "is_overdue": True}],
            reminders=[{"kind": "walk", "title": "10,000 steps left"}],
            tomorrow_training={
                "planned_type": "bjj_normal",
                "title": "BJJ Normal",
                "start_at": "2026-09-14T07:30:00+09:00",
                "is_all_day": False,
            },
            timezone=tokyo,
            now=now,
        )
        payload.update(overrides)
        return compose_today_advice(**payload), advice_window_name(now, tokyo)

    def test_morning_advice_covers_the_open_day(self):
        advice, window = self._rest_advice(6)
        self.assertEqual(window, "morning")
        self.assertIn("Sunday is rest — keep the morning light", advice)
        self.assertIn("10,000 steps", advice)
        self.assertIn("Evaluation update", advice)
        self.assertNotIn("Today is Rest", advice)
        self.assertNotIn("07:30 BJJ Normal", advice)
        self.assertNotIn("Payroll", advice)

    def test_lunch_advice_covers_what_is_left(self):
        advice, window = self._rest_advice(12)
        self.assertEqual(window, "lunch")
        self.assertIn("Midday check", advice)
        self.assertIn("10,000 steps", advice)
        self.assertIn("Evaluation update", advice)
        self.assertIn("07:30 BJJ Normal", advice)
        self.assertNotIn("Today is Rest", advice)

    def test_evening_advice_closes_the_day(self):
        advice, window = self._rest_advice(19)
        self.assertEqual(window, "evening")
        self.assertIn("Evening", advice)
        self.assertIn("10,000 steps", advice)
        self.assertIn("Evaluation update", advice)
        self.assertIn("07:30 BJJ Normal", advice)
        self.assertIn("Keep tonight easy", advice)
        self.assertNotIn("Today is Rest", advice)

    def test_late_night_stays_evening_until_six(self):
        evening, evening_window = self._rest_advice(5, 30)
        morning, morning_window = self._rest_advice(6)
        self.assertEqual(evening_window, "evening")
        self.assertEqual(morning_window, "morning")
        self.assertIn("Evening", evening)
        self.assertIn("Sunday is rest", morning)

    def test_move_meeting_replans(self):
        start = datetime(2026, 9, 14, 11, tzinfo=UTC)
        result = self.service.move_meeting(
            self.app.state.calendar_bridge_service,
            self.app.state.training_service,
            "meeting-1",
            start,
        )
        self.assertEqual(result["id"], "meeting-1")
        self.assertEqual(self.app.state.training_service.reconciled, 1)

    def test_fatigue_and_bjj_candidate_verbs(self):
        self.assertEqual(self.service.set_fatigue(self.app.state.training_service, self.day, "tired")["fatigue_state"], "tired")
        self.assertEqual(self.service.confirm_bjj(self.app.state.training_service, self.day)["planned_type"], "bjj_normal")
        self.assertEqual(self.service.decline_bjj(self.app.state.training_service, self.day)["status"], "declined")
        self.assertEqual(self.service.gym_today(self.app.state.training_service, self.day, "strength_a")["planned_type"], "strength_a")

    @patch("app.api.daily.settings")
    def test_adjust_calendar_action(self, settings):
        from app.domain.training.adjust import CalendarAdjuster

        settings.dashboard_automation_token = "automation-token"
        settings.chili_public_url = "http://127.0.0.1:8080"
        settings.daily_briefing_base_url = "http://127.0.0.1:8080"
        settings.timezone = "Asia/Tokyo"
        self.app.state.calendar_adjuster = CalendarAdjuster(timezone_name="Asia/Tokyo", api_key="")
        response = self.client.post(
            "/api/v1/automation/plan",
            headers={"Authorization": "Bearer automation-token"},
            json={"action": "adjust_calendar", "instruction": "I want Strength A today"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["action"], "adjust_calendar")
        self.assertEqual(body["result"]["analysis"]["mutations"][0]["op"], "gym_today")
        self.assertEqual(self.app.state.training_service.scheduled[0][1], "strength_a")
