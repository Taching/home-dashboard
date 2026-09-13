import unittest
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
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
            "week": [dict(self.session)],
            "week_quality": "good",
            "bjj_candidates": [],
            "tomorrow_prescription": {
                "session": self.session["planned_type"],
                "time": "07:30",
                "work": "Squat, bench, then bike intervals.",
                "focus": "Leave two reps in reserve",
                "why": "Placed around BJJ.",
                "weekly_status": {"bjj": {"completed": 0, "target": 3}},
            },
        }

    def record_fatigue(self, day, state):
        return {"fatigue_state": state}

    def confirm_bjj(self, day, hard=None):
        return {"planned_type": "bjj_normal", "day": day.isoformat()}

    def decline_bjj(self, day):
        return {"status": "declined", "day": day.isoformat()}

    def schedule_gym(self, day, workout_type):
        return {"planned_type": workout_type, "title": f"Gym ({workout_type})", "day": day.isoformat()}

    def reconcile(self):
        self.reconciled += 1


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
