import unittest
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.domain.training.policy import assess_week_quality
from app.domain.training.scheduler import TrainingScheduler, assess_readiness, phase_for_date
from app.domain.training.types import (
    ClassTemplate, ClassType, ExistingSession, FatigueState, FixedBjjEvent, ReadinessInput,
    ReadinessLevel, SessionStatus, TrainingPhase, WeatherHint, WeekQuality, WorkoutType,
)

TOKYO = ZoneInfo("Asia/Tokyo")
MITA_WEEK = (
    ClassTemplate(0, __import__("datetime").time(7, 30), ClassType.NORMAL),
    ClassTemplate(1, __import__("datetime").time(7, 30), ClassType.NORMAL),
    ClassTemplate(2, __import__("datetime").time(7, 30), ClassType.NORMAL),
    ClassTemplate(3, __import__("datetime").time(7, 30), ClassType.NORMAL),
    ClassTemplate(5, __import__("datetime").time(10, 0), ClassType.COMPETITION),
)


class TrainingSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = TrainingScheduler("Asia/Tokyo")
        self.now = datetime(2026, 9, 13, 20, tzinfo=TOKYO)

    def test_class_template_schedules_bjj_as_a_real_session(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, class_template=MITA_WEEK)
        by_day = {item.local_date: item.type for item in plan.sessions}
        self.assertEqual(by_day.get(date(2026, 9, 14)), WorkoutType.BJJ_NORMAL)
        self.assertEqual(by_day.get(date(2026, 9, 19)), WorkoutType.BJJ_HARD)
        self.assertEqual(plan.candidates, ())

    def test_without_template_does_not_invent_bjj(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now)
        self.assertFalse(any(item.type.value.startswith("bjj_") for item in plan.sessions))

    def test_calendar_bjj_is_timed_and_pins_the_day(self) -> None:
        fixed = (
            FixedBjjEvent(
                "tue", "BJJ",
                datetime(2026, 9, 15, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 15, 9, tzinfo=TOKYO),
            ),
        )
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, fixed_bjj=fixed)
        tuesday = [item for item in plan.sessions if item.local_date == date(2026, 9, 15)]
        self.assertEqual([item.type for item in tuesday], [WorkoutType.BJJ_NORMAL])

    def test_very_fatigued_replaces_tomorrow_with_recovery(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, fatigue=FatigueState.VERY_FATIGUED)
        tomorrow = next(item for item in plan.sessions if item.local_date == date(2026, 9, 14))
        self.assertEqual(tomorrow.type, WorkoutType.RECOVERY)

    def test_pain_requires_recovery(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, fatigue=FatigueState.PAIN)
        tomorrow = next(item for item in plan.sessions if item.local_date == date(2026, 9, 14))
        self.assertEqual(tomorrow.type, WorkoutType.RECOVERY)

    def test_skipped_strength_does_not_advance_ab_sequence(self) -> None:
        existing = (
            ExistingSession(
                "sa", WorkoutType.STRENGTH_A,
                datetime(2026, 9, 15, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 15, 8, 30, tzinfo=TOKYO),
                SessionStatus.SKIPPED,
            ),
        )
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, existing=existing)
        self.assertTrue(any(item.type == WorkoutType.STRENGTH_A for item in plan.sessions))

    def test_completed_strength_a_is_followed_by_b(self) -> None:
        existing = (
            ExistingSession(
                "sun-strength", WorkoutType.STRENGTH_A,
                datetime(2026, 9, 13, 14, 0, tzinfo=TOKYO),
                datetime(2026, 9, 13, 15, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
        )
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, existing=existing)
        self.assertTrue(any(item.type == WorkoutType.STRENGTH_B for item in plan.sessions))
        self.assertFalse(any(item.type == WorkoutType.STRENGTH_A for item in plan.sessions))

    def test_does_not_force_sunday_rest_quota(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now)
        self.assertFalse(any(item.type == WorkoutType.REST and item.local_date == date(2026, 9, 20) for item in plan.sessions))

    def test_protects_day_before_hard_bjj(self) -> None:
        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=datetime(2026, 9, 17, 20, tzinfo=TOKYO),
            class_template=MITA_WEEK, upcoming_hard_bjj=date(2026, 9, 19),
        )
        friday = next((item for item in plan.sessions if item.local_date == date(2026, 9, 18)), None)
        if friday is not None:
            self.assertNotIn(friday.type, {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B})

    def test_rain_keeps_zone2_as_indoor(self) -> None:
        existing = (
            ExistingSession(
                "sb", WorkoutType.STRENGTH_B,
                datetime(2026, 9, 16, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 16, 8, 25, tzinfo=TOKYO),
                SessionStatus.PLANNED,
                True, None, None, "manual",
            ),
        )
        plan = self.scheduler.plan_week(
            date(2026, 9, 14),
            now=datetime(2026, 9, 14, 6, tzinfo=TOKYO),
            weather=(WeatherHint(date(2026, 9, 14), True, "Rain"),),
            existing=existing,
        )
        zone2 = next(item for item in plan.sessions if item.local_date == date(2026, 9, 14))
        self.assertEqual(zone2.type, WorkoutType.ZONE_2)
        self.assertTrue(any("Indoor" in (exercise.notes or "") for exercise in zone2.exercises))

    def test_readiness_helpers_still_map_legacy_fields(self) -> None:
        assessment = assess_readiness(ReadinessInput(sleep_hours=5, fatigue=2, soreness=2, readiness=4))
        self.assertEqual(assessment.level, ReadinessLevel.GREEN)
        self.assertEqual(assess_readiness(ReadinessInput(pain=True)).level, ReadinessLevel.MANUAL_REVIEW)

    def test_phase_boundaries(self) -> None:
        cases = {
            date(2026, 10, 4): TrainingPhase.BUILD_1,
            date(2026, 10, 5): TrainingPhase.TAPER_1,
            date(2026, 10, 10): TrainingPhase.COMPETITION_1,
            date(2026, 10, 12): TrainingPhase.RECOVERY_1,
            date(2026, 10, 15): TrainingPhase.BUILD_2,
            date(2026, 11, 7): TrainingPhase.COMPETITION_2,
            date(2026, 11, 9): TrainingPhase.POST_COMPETITION,
        }
        for day, expected in cases.items():
            with self.subTest(day=day):
                self.assertEqual(phase_for_date(day), expected)

    def test_tokyo_day_boundary_uses_local_tomorrow(self) -> None:
        now = datetime(2026, 9, 13, 15, 30, tzinfo=UTC)
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=now)
        self.assertFalse(any(item.local_date < date(2026, 9, 14) for item in plan.sessions))

    def test_week_quality_does_not_require_rest(self) -> None:
        self.assertEqual(assess_week_quality(bjj=3, hard_bjj=True, strength=2, zone_2=1, intervals=1, rest=False), WeekQuality.EXCELLENT)
        self.assertEqual(assess_week_quality(bjj=2, hard_bjj=False, strength=1, zone_2=1, intervals=0, rest=False), WeekQuality.ACCEPTABLE)


if __name__ == "__main__":
    unittest.main()
