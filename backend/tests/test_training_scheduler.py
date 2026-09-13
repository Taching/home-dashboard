import unittest
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.training.scheduler import TrainingScheduler, assess_readiness, phase_for_date
from app.domain.training.types import (
    ExistingSession, FixedBjjEvent, ReadinessInput, ReadinessLevel, SessionStatus, TrainingPhase, WorkoutType,
)


TOKYO = ZoneInfo("Asia/Tokyo")


class TrainingSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = TrainingScheduler("Asia/Tokyo")
        self.now = datetime(2026, 9, 13, 20, tzinfo=TOKYO)

    def test_normal_week_prioritises_bjj_and_preserves_rest(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now)
        by_day = {item.local_date: item.type for item in plan.sessions}

        self.assertEqual(by_day[date(2026, 9, 14)], WorkoutType.BJJ_NORMAL)
        self.assertEqual(by_day[date(2026, 9, 15)], WorkoutType.STRENGTH_A)
        self.assertEqual(by_day[date(2026, 9, 17)], WorkoutType.BJJ_NORMAL)
        self.assertEqual(by_day[date(2026, 9, 18)], WorkoutType.STRENGTH_B)
        self.assertEqual(by_day[date(2026, 9, 19)], WorkoutType.BJJ_HARD)
        self.assertEqual(by_day[date(2026, 9, 20)], WorkoutType.REST)
        self.assertEqual(sum(item.type == WorkoutType.ZONE_2 for item in plan.sessions), 1)

    def test_busy_monday_moves_bjj_to_tuesday_without_double(self) -> None:
        busy = ((datetime(2026, 9, 14, 7, tzinfo=TOKYO), datetime(2026, 9, 14, 10, tzinfo=TOKYO)),)
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, busy=busy)
        days = [item.local_date for item in plan.sessions]

        self.assertIn(date(2026, 9, 15), [item.local_date for item in plan.sessions if item.type == WorkoutType.BJJ_NORMAL])
        self.assertEqual(len(days), len(set(days)))

    def test_four_bjj_sessions_reduce_strength_to_one(self) -> None:
        fixed = tuple(
            FixedBjjEvent(
                f"bjj-{index}", "BJJ",
                datetime(2026, 9, day, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, day, 9, tzinfo=TOKYO),
            )
            for index, day in enumerate((14, 15, 17, 19), 1)
        )
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, fixed_bjj=fixed)

        strength = [item for item in plan.sessions if item.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}]
        self.assertEqual([item.type for item in strength], [WorkoutType.STRENGTH_B])

    def test_red_readiness_replaces_tomorrow_with_recovery(self) -> None:
        readiness = assess_readiness(ReadinessInput(sleep_hours=5, fatigue=5, soreness=5, readiness=2))
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, readiness=readiness)
        tomorrow = next(item for item in plan.sessions if item.local_date == date(2026, 9, 14))

        self.assertEqual(readiness.level, ReadinessLevel.RED)
        self.assertEqual(tomorrow.type, WorkoutType.RECOVERY)

    def test_single_bad_metric_does_not_downgrade(self) -> None:
        assessment = assess_readiness(ReadinessInput(sleep_hours=5, fatigue=2, soreness=2, readiness=4))
        self.assertEqual(assessment.level, ReadinessLevel.GREEN)

    def test_pain_requires_manual_review(self) -> None:
        assessment = assess_readiness(ReadinessInput(pain=True, fatigue=1, soreness=1, readiness=5))
        self.assertEqual(assessment.level, ReadinessLevel.MANUAL_REVIEW)

    def test_phase_boundaries(self) -> None:
        cases = {
            date(2026, 10, 4): TrainingPhase.BUILD_1,
            date(2026, 10, 5): TrainingPhase.TAPER_1,
            date(2026, 10, 9): TrainingPhase.TAPER_1,
            date(2026, 10, 10): TrainingPhase.COMPETITION_1,
            date(2026, 10, 11): TrainingPhase.COMPETITION_1,
            date(2026, 10, 12): TrainingPhase.RECOVERY_1,
            date(2026, 10, 15): TrainingPhase.BUILD_2,
            date(2026, 11, 2): TrainingPhase.TAPER_2,
            date(2026, 11, 7): TrainingPhase.COMPETITION_2,
            date(2026, 11, 9): TrainingPhase.POST_COMPETITION,
        }
        for day, expected in cases.items():
            with self.subTest(day=day):
                self.assertEqual(phase_for_date(day), expected)

    def test_october_taper_does_not_invent_bjj_day_before_competition(self) -> None:
        now = datetime(2026, 10, 4, 20, tzinfo=TOKYO)
        plan = self.scheduler.plan_week(date(2026, 10, 5), now=now)
        bjj = [item for item in plan.sessions if item.type in {
            WorkoutType.BJJ_TECHNICAL, WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD,
        }]

        self.assertEqual(len(bjj), 2)
        self.assertFalse(any(item.local_date == date(2026, 10, 10) for item in bjj))
        self.assertFalse(any(item.type == WorkoutType.STRENGTH_A for item in plan.sessions))

    def test_tokyo_day_boundary_uses_local_tomorrow(self) -> None:
        now = datetime(2026, 9, 13, 15, 30, tzinfo=UTC)  # Monday 00:30 in Tokyo
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=now)
        self.assertFalse(any(item.local_date < date(2026, 9, 14) for item in plan.sessions))

    def test_late_partial_week_does_not_cram_missed_targets_into_sunday(self) -> None:
        now = datetime(2026, 9, 12, 12, tzinfo=TOKYO)
        plan = self.scheduler.plan_week(date(2026, 9, 7), now=now)

        self.assertEqual([(item.local_date, item.type) for item in plan.sessions], [
            (date(2026, 9, 13), WorkoutType.REST),
        ])


if __name__ == "__main__":
    unittest.main()
