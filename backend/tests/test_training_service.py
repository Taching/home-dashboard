import unittest
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.models import TrainingReminder, TrainingSession
from app.database.session import Base
from app.domain.training.service import TrainingService


def factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class TrainingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = factory()
        self.service = TrainingService(self.factory, timezone_name="Asia/Tokyo")
        self.now = datetime(2026, 9, 13, 15, tzinfo=UTC)  # Monday 00:00 JST
        self.service.bootstrap(self.now)

    def test_reconcile_keeps_future_planned_sessions(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        start = datetime(2026, 9, 14, 7, 30, tzinfo=tokyo)
        session_id = "future-bjj-must-survive"
        with self.factory() as session:
            session.add(TrainingSession(
                id=session_id,
                planned_type="bjj_normal",
                status="planned",
                phase="build_october",
                planned_week_start=date(2026, 9, 14),
                start_at=start.astimezone(UTC),
                end_at=start.astimezone(UTC) + timedelta(minutes=90),
                estimated_minutes=90,
                intensity="normal",
                reason="Weekday BJJ",
                source="scheduler",
                pinned=False,
                created_at=self.now,
                updated_at=self.now,
            ))
            session.commit()

        self.service.bootstrap(self.now)
        kept = self.service.session(session_id)
        self.assertIsNotNone(kept)
        self.assertEqual(kept["status"], "planned")
        self.assertEqual(kept["planned_type"], "bjj_normal")

    def test_reconcile_is_idempotent(self) -> None:
        with self.factory() as session:
            before = [(row.id, row.revision) for row in session.scalars(select(TrainingSession)).all()]
            reminder_count = len(session.scalars(select(TrainingReminder)).all())

        self.service.reconcile(self.now)

        with self.factory() as session:
            after = [(row.id, row.revision) for row in session.scalars(select(TrainingSession)).all()]
            self.assertEqual(before, after)
            self.assertEqual(reminder_count, len(session.scalars(select(TrainingReminder)).all()))

    def test_overview_exposes_rolling_seven_day_plan(self) -> None:
        saturday = datetime(2026, 9, 12, 8, tzinfo=UTC)  # Saturday 17:00 JST
        service = TrainingService(self.factory, timezone_name="Asia/Tokyo")
        service.bootstrap(saturday)

        overview = service.overview(saturday)
        upcoming_dates = {
            datetime.fromisoformat(item["start_at"]).astimezone(service._timezone).date()
            for item in overview["upcoming"]
        }

        self.assertTrue(upcoming_dates)
        self.assertTrue(all(date(2026, 9, 12) <= item < date(2026, 9, 19) for item in upcoming_dates))
        self.assertTrue(any(item >= date(2026, 9, 14) for item in upcoming_dates))

    def test_moving_strength_does_not_recreate_original(self) -> None:
        overview = self.service.overview(self.now)
        strength_a = next(item for item in overview["week"] if item["planned_type"] == "strength_a")
        moved = datetime.fromisoformat(strength_a["start_at"]) + timedelta(days=1)

        self.service.update_session(strength_a["id"], start_at=moved, now=self.now)
        overview = self.service.overview(self.now)

        self.assertEqual(sum(item["planned_type"] == "strength_a" for item in overview["week"]), 1)

    def test_skipped_strength_a_is_not_automatically_made_up(self) -> None:
        overview = self.service.overview(self.now)
        strength_a = next(item for item in overview["week"] if item["planned_type"] == "strength_a")

        self.service.update_session(strength_a["id"], status="skipped", notes="work conflict", now=self.now)
        overview = self.service.overview(self.now)

        self.assertFalse(any(item["planned_type"] == "strength_a" and item["status"] == "planned" for item in overview["week"]))
        self.assertTrue(overview["tomorrow_prescription"])
        self.assertIn(overview["week_quality"], {"excellent", "good", "acceptable", "bad_planning"})

    def test_confirm_bjj_creates_a_timed_session_and_replans(self) -> None:
        day = date(2026, 9, 15)
        if not any(item["date"] == day.isoformat() for item in self.service.overview(self.now)["bjj_candidates"]):
            day = date.fromisoformat(self.service.overview(self.now)["bjj_candidates"][0]["date"])

        created = self.service.confirm_bjj(day, now=self.now)
        overview = self.service.overview(self.now)

        self.assertTrue(created["planned_type"].startswith("bjj_"))
        self.assertTrue(any(
            item["planned_type"].startswith("bjj_") and self.service._local_date(item["start_at"]) == day
            for item in overview["week"]
        ))
        self.assertFalse(any(item["date"] == day.isoformat() for item in overview["bjj_candidates"]))

    def test_sunday_gym_counts_as_coming_week_strength_a(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        sunday = datetime(2026, 9, 13, 12, tzinfo=tokyo)
        created = self.service.schedule_gym(date(2026, 9, 13), "strength_a", now=sunday)
        self.assertEqual(created["title"], "Gym (Strength A)")
        monday = datetime(2026, 9, 14, 8, tzinfo=tokyo)
        overview = self.service.overview(monday)
        planned_a = [
            item for item in overview["week"]
            if item["planned_type"] == "strength_a" and item["status"] == "planned"
        ]
        self.assertEqual(planned_a, [])

    def test_legacy_completed_sunday_strength_counts_for_the_new_week(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        sunday_start = datetime(2026, 9, 13, 14, 0, tzinfo=tokyo)
        with self.factory() as session:
            session.add(TrainingSession(
                id="legacy-sunday-strength",
                planned_type="strength_a",
                status="completed",
                phase="build_october",
                planned_week_start=date(2026, 9, 7),
                start_at=sunday_start.astimezone(UTC),
                end_at=(sunday_start + timedelta(minutes=60)).astimezone(UTC),
                estimated_minutes=60,
                intensity="hard",
                reason="Completed before Sunday carry-over was normalized.",
                source="scheduler",
                pinned=True,
                original_planned_type="rest",
                created_at=self.now,
                updated_at=self.now,
            ))
            session.commit()

        self.service.reconcile(self.now)
        overview = self.service.overview(self.now)

        self.assertFalse(any(
            item["planned_type"] == "strength_a" and item["status"] == "planned"
            for item in overview["week"]
        ))
        self.assertEqual(overview["compliance"]["strength"]["completed"], 1)

    def test_retained_zone2_day_is_not_stacked_with_strength(self) -> None:
        wednesday = date(2026, 9, 16)
        self.service.place_session(wednesday, "zone_2", now=self.now, pinned=True)

        wednesday_sessions = self.service.sessions_on(wednesday)

        self.assertEqual([item["planned_type"] for item in wednesday_sessions], ["zone_2"])

    def test_skipped_history_does_not_replace_active_today_session(self) -> None:
        today = date(2026, 9, 14)
        zone2 = self.service.place_session(today, "zone_2", now=self.now)
        start = datetime(2026, 9, 14, 7, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        with self.factory() as session:
            session.add(TrainingSession(
                id="skipped-grip-history",
                planned_type="grip",
                status="skipped",
                phase="build_october",
                planned_week_start=today,
                start_at=start.astimezone(UTC),
                end_at=(start + timedelta(minutes=10)).astimezone(UTC),
                estimated_minutes=10,
                intensity="easy",
                reason="Historical replacement",
                source="manual",
                pinned=True,
                created_at=self.now,
                updated_at=self.now,
            ))
            session.commit()

        overview = self.service.overview(self.now)

        self.assertEqual(overview["today"]["id"], zone2["id"])
        self.assertEqual(self.service.for_date(today)["id"], zone2["id"])
        self.assertFalse(any(item["id"] == "skipped-grip-history" for item in overview["upcoming"]))

    def test_recovery_replacement_suppresses_original_workout(self) -> None:
        overview = self.service.overview(self.now)
        strength_a = next(item for item in overview["week"] if item["planned_type"] == "strength_a")

        self.service.replace_session(strength_a["id"], "recovery", now=self.now)
        overview = self.service.overview(self.now)

        self.assertFalse(any(item["planned_type"] == "strength_a" for item in overview["week"]))

    def test_past_due_monday_bjj_replans_tuesday_as_bjj_not_strength(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        sunday = datetime(2026, 9, 13, 12, tzinfo=tokyo)
        strength = self.service.schedule_gym(date(2026, 9, 13), "strength_a", now=sunday)
        self.service.update_session(strength["id"], status="completed", now=sunday)
        morning = datetime(2026, 9, 14, 0, 30, tzinfo=tokyo)
        monday_bjj = self.service.add_bjj(datetime(2026, 9, 14, 7, 30, tzinfo=tokyo), now=morning)
        later = datetime(2026, 9, 14, 9, 32, tzinfo=tokyo)
        self.service.reconcile(later)
        overview = self.service.overview(later)
        tuesday = date(2026, 9, 15)
        tuesday_types = [
            item["planned_type"] for item in overview["week"]
            if self.service._local_date(item["start_at"]) == tuesday
            and item["status"] not in {"skipped", "cancelled"}
        ]

        self.assertEqual(self.service.session(monday_bjj["id"])["status"], "skipped")
        self.assertEqual(tuesday_types, [])
        self.assertTrue(any(item["date"] == tuesday.isoformat() for item in overview["bjj_candidates"]))
        self.assertEqual(overview["tomorrow_prescription"]["session"], "bjj_normal")
        self.assertTrue(overview["tomorrow_prescription"].get("candidate"))
        self.assertFalse(any(
            item["planned_type"] == "strength_b"
            and item["status"] == "planned"
            and self.service._local_date(item["start_at"]) == tuesday
            for item in overview["week"]
        ))

    def test_skipped_monday_bjj_does_not_stack_tuesday_gym(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        monday = self.service.add_bjj(datetime(2026, 9, 14, 7, 30, tzinfo=tokyo), now=self.now)
        self.service.add_bjj(datetime(2026, 9, 15, 7, 30, tzinfo=tokyo), now=self.now)
        evening = datetime(2026, 9, 14, 12, tzinfo=UTC)
        self.service.update_session(monday["id"], status="skipped", notes="missed class", now=evening)
        overview = self.service.overview(evening)
        tuesday = [
            item for item in overview["week"]
            if self.service._local_date(item["start_at"]) == date(2026, 9, 15)
        ]
        self.assertEqual([item["planned_type"] for item in tuesday], ["bjj_normal"])

    def test_confirmed_hard_bjj_cancels_strength_a_collision(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        saturday = date(2026, 9, 19)
        strength = self.service.schedule_gym(saturday, "strength_a", now=self.now)

        hard_bjj = self.service.add_bjj(
            datetime(2026, 9, 19, 10, 0, tzinfo=tokyo), hard=True, now=self.now,
        )

        self.assertEqual(self.service.session(hard_bjj["id"])["status"], "planned")
        self.assertEqual(self.service.session(strength["id"])["status"], "cancelled")

    def test_confirmed_normal_bjj_displaces_and_replans_strength_b(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        tuesday = date(2026, 9, 15)
        strength = self.service.schedule_gym(tuesday, "strength_b", now=self.now)

        bjj = self.service.add_bjj(
            datetime(2026, 9, 15, 7, 30, tzinfo=tokyo), now=self.now,
        )
        overview = self.service.overview(self.now)
        tuesday_types = [
            item["planned_type"] for item in overview["week"]
            if self.service._local_date(item["start_at"]) == tuesday
        ]

        self.assertEqual(self.service.session(bjj["id"])["status"], "planned")
        self.assertEqual(self.service.session(strength["id"])["status"], "cancelled")
        self.assertEqual(tuesday_types, ["bjj_normal"])
        self.assertTrue(any(
            item["planned_type"] == "strength_b"
            and item["status"] == "planned"
            and self.service._local_date(item["start_at"]) != tuesday
            for item in overview["week"]
        ))

    def test_confirmed_bjj_never_rewrites_completed_strength(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        tuesday = date(2026, 9, 15)
        strength = self.service.schedule_gym(tuesday, "strength_b", now=self.now)
        self.service.update_session(strength["id"], status="completed", now=self.now)

        self.service.add_bjj(
            datetime(2026, 9, 15, 7, 30, tzinfo=tokyo), now=self.now,
        )

        self.assertEqual(self.service.session(strength["id"])["status"], "completed")

    def test_strength_a_is_rejected_when_hard_bjj_is_already_confirmed(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        saturday = date(2026, 9, 19)
        self.service.add_bjj(
            datetime(2026, 9, 19, 10, 0, tzinfo=tokyo), hard=True, now=self.now,
        )

        with self.assertRaisesRegex(ValueError, "Hard BJJ"):
            self.service.schedule_gym(saturday, "strength_a", now=self.now)

    def test_log_matching_workout_marks_strength_complete(self) -> None:
        tokyo = ZoneInfo("Asia/Tokyo")
        sunday = datetime(2026, 9, 13, 12, tzinfo=tokyo)
        created = self.service.schedule_gym(date(2026, 9, 13), "strength_a", now=sunday)

        updated = self.service.log_matching_workout(
            date(2026, 9, 13),
            kind="strength_a",
            exercises=[
                {"name": "Warm-up", "done": True},
                {"name": "Back Squat", "done": True},
                {"name": "Bench Press", "done": True},
                {"name": "Pull-ups", "done": True},
                {"name": "Bulgarian Split Squat", "done": True},
                {"name": "Standing Landmine Rotation", "done": True},
                {"name": "Stationary Bike Intervals", "done": True},
            ],
            note="easy lifts, hard intervals",
            now=sunday,
        )

        self.assertEqual(updated["id"], created["id"])
        self.assertEqual(updated["status"], "completed")
        self.assertEqual(updated["notes"], "easy lifts, hard intervals")
        self.assertTrue(all(item["done"] for item in updated["exercises"]))

    def test_bjj_capacity_uses_actual_round_metric(self) -> None:
        bjj = self.service.add_bjj(datetime(2026, 9, 15, 7, 30, tzinfo=ZoneInfo("Asia/Tokyo")), now=self.now)

        self.service.update_session(
            bjj["id"], status="completed", final_round_quality=3,
            metrics=[{"metric_type": "bjj_rounds", "sequence": None, "value": 4, "unit": "rounds"}],
            now=self.now,
        )
        trend = self.service.overview(self.now)["trends"]["bjj_capacity"][-1]

        self.assertEqual(trend["rounds"], 4)
        self.assertEqual(trend["final_quality"], 3)


if __name__ == "__main__":
    unittest.main()
