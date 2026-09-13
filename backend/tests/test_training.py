import unittest
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.domain.calendar_bridge import CalendarEvent
from app.domain.training_logs import ExerciseDone, TrainingService
from app.domain.training_plans import suggested_kinds_for
from app.domain.weekly import WeeklyService


def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class TrainingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        factory = test_session_factory()
        self.service = TrainingService(session_factory=factory)
        self.weekly = WeeklyService(session_factory=factory)
        self.tokyo = ZoneInfo("Asia/Tokyo")

    def test_weekday_fallback_matches_program(self) -> None:
        monday = date(2026, 9, 14)
        self.assertEqual(suggested_kinds_for(monday), ("bjj",))
        snapshot = self.service.today(now=datetime(2026, 9, 14, 9, tzinfo=self.tokyo))
        self.assertEqual(snapshot.suggested, ("bjj",))
        self.assertEqual(snapshot.suggested_source, "week")

    def test_calendar_titles_override_weekday(self) -> None:
        day = datetime(2026, 9, 14, 9, tzinfo=self.tokyo)
        events = [
            CalendarEvent(
                "strength",
                "Strength A",
                day.replace(hour=18),
                day.replace(hour=19),
            )
        ]
        snapshot = self.service.today(now=day, calendar_events=events)
        self.assertEqual(snapshot.suggested, ("strength_a",))
        self.assertEqual(snapshot.suggested_source, "calendar")

    def test_log_sober_and_gym(self) -> None:
        now = datetime(2026, 9, 12, 12, tzinfo=self.tokyo)
        gym = self.service.log(kind="grip", completed="yes", feeling="normal", source="ui", now=now)
        sober = self.service.log(kind="sober", completed="yes", source="ui", now=now + timedelta(minutes=1))
        snapshot = self.service.today(now=now)
        self.assertEqual(gym.completed, "yes")
        self.assertEqual(snapshot.sober.id, sober.id)
        self.assertEqual(len(snapshot.logs), 2)

    def test_workout_checkboxes_set_partial(self) -> None:
        now = datetime(2026, 9, 15, 12, tzinfo=self.tokyo)
        record = self.service.log_workout(
            kind="strength_a",
            exercises=[
                ExerciseDone("Back Squat", True),
                ExerciseDone("Bench Press", False),
            ],
            note="squat felt heavy",
            now=now,
        )
        self.assertEqual(record.completed, "partial")
        self.assertEqual(record.note, "squat felt heavy")
        self.assertEqual([item.done for item in record.exercises], [True, False])
        again = self.service.log_workout(
            kind="strength_a",
            exercises=[
                ExerciseDone("Back Squat", True),
                ExerciseDone("Bench Press", True),
            ],
            note="finished the bench",
            now=now + timedelta(minutes=10),
        )
        self.assertEqual(again.id, record.id)
        self.assertEqual(again.completed, "yes")
        self.assertEqual(len(self.service.logs_for(now.date())), 1)

    def test_sober_is_separate_from_workout(self) -> None:
        now = datetime(2026, 9, 15, 21, tzinfo=self.tokyo)
        with self.assertRaises(ValueError):
            self.service.log_workout(kind="sober", exercises=[], now=now)
        record = self.service.log_sober(sober=True, note="stayed in", now=now)
        self.assertEqual(record.kind, "sober")
        self.assertEqual(record.completed, "yes")

    def test_sunday_weight_compares_with_last_week(self) -> None:
        previous = date(2026, 9, 6)
        sunday = date(2026, 9, 13)
        self.weekly.save_sunday(
            previous,
            self.service,
            weight_kg=82.8,
            now=datetime(2026, 9, 6, 10, tzinfo=self.tokyo),
        )
        self.service.log_workout(
            kind="bjj",
            exercises=[ExerciseDone("Class", True)],
            note="normal class",
            now=datetime(2026, 9, 7, 21, tzinfo=self.tokyo),
        )
        saved = self.weekly.save_sunday(
            sunday,
            self.service,
            weight_kg=82.4,
            note="maybe drop Friday if BJJ is 4x",
            now=datetime(2026, 9, 13, 10, tzinfo=self.tokyo),
        )
        self.assertEqual(saved.check_in.previous_weight_kg, 82.8)
        self.assertEqual(saved.check_in.delta_kg, -0.4)
        self.assertIn("down 0.4 kg", saved.notify_message)
        self.assertNotIn("This week:", saved.notify_message)
        self.assertIn("BJJ", saved.review_prompt)
        self.assertIn("maybe drop Friday", saved.review_prompt)
        self.assertIn("3–6 short lines", saved.review_prompt)

    def test_nudge_messages_are_short_with_one_link(self) -> None:
        daily = self.service.nudge_message(date(2026, 9, 13))
        gym = self.service.nudge_message(date(2026, 9, 15))
        self.assertIn("/daily/2026-09-13", daily)
        self.assertTrue(daily.startswith("http"))
        self.assertNotIn("tick", daily.lower())
        self.assertLess(len(daily.splitlines()), 6)
        self.assertIn("Today: Strength A", gym)
        self.assertIn("/workout/strength_a", gym)
        self.assertTrue(gym.startswith("http"))
        self.assertNotIn("tick", gym.lower())

    def test_sunday_rejected_on_weekday(self) -> None:
        with self.assertRaises(ValueError):
            self.weekly.save_sunday(
                date(2026, 9, 14),
                self.service,
                weight_kg=82.0,
                now=datetime(2026, 9, 14, 10, tzinfo=self.tokyo),
            )

    def test_sunday_reminder_only_at_10(self) -> None:
        sunday_morning = datetime(2026, 9, 13, 10, 3, tzinfo=self.tokyo)
        saturday = datetime(2026, 9, 12, 10, 3, tzinfo=self.tokyo)
        self.assertEqual(self.weekly.reminder_due(sunday_morning), date(2026, 9, 13))
        self.assertIsNone(self.weekly.reminder_due(saturday))
        self.assertIsNone(self.weekly.reminder_due(sunday_morning.replace(hour=18)))

    def test_managed_calendar_plan_uses_same_program(self) -> None:
        plan = self.service.managed_calendar_plan(now=datetime(2026, 9, 14, 9, tzinfo=self.tokyo), days=1)
        self.assertEqual(plan["calendar_name"], "Chili Training")
        self.assertEqual(plan["events"][0]["title"], "BJJ")
        self.assertIn("chili-training:bjj-2026-09-14", plan["events"][0]["notes"])
        self.assertIn("/workout/bjj", plan["events"][0]["notes"])


if __name__ == "__main__":
    unittest.main()
