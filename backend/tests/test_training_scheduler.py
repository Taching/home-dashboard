import unittest
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.domain.training.policy import assess_week_quality
from app.domain.training.scheduler import TrainingScheduler, assess_readiness, phase_for_date
from app.domain.training.types import (
    ExistingSession, FatigueState, FixedBjjEvent, ReadinessInput, ReadinessLevel,
    SessionStatus, TrainingPhase, WeatherHint, WeekQuality, WorkoutType,
)


TOKYO = ZoneInfo("Asia/Tokyo")


class TrainingSchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = TrainingScheduler("Asia/Tokyo")
        self.now = datetime(2026, 9, 13, 20, tzinfo=TOKYO)

    def test_normal_week_proposes_bjj_and_places_gym_around_it(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now)
        by_day = {item.local_date: item.type for item in plan.sessions}
        candidate_days = {item.day for item in plan.candidates}

        self.assertEqual(candidate_days, {date(2026, 9, 14), date(2026, 9, 17), date(2026, 9, 19)})
        self.assertFalse(any(item.type in {WorkoutType.BJJ_TECHNICAL, WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD} for item in plan.sessions))
        self.assertEqual(by_day[date(2026, 9, 15)], WorkoutType.STRENGTH_A)
        self.assertEqual(by_day[date(2026, 9, 17)] if date(2026, 9, 17) in by_day else None, None)
        self.assertEqual(by_day[date(2026, 9, 18)], WorkoutType.STRENGTH_B)
        self.assertEqual(by_day[date(2026, 9, 20)], WorkoutType.REST)
        self.assertEqual(sum(item.type == WorkoutType.ZONE_2 for item in plan.sessions), 1)

    def test_busy_monday_proposes_tuesday_instead_of_inventing_a_class(self) -> None:
        busy = ((datetime(2026, 9, 14, 7, tzinfo=TOKYO), datetime(2026, 9, 14, 10, tzinfo=TOKYO)),)
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, busy=busy)
        candidate_days = {item.day for item in plan.candidates}

        self.assertIn(date(2026, 9, 15), candidate_days)
        self.assertNotIn(date(2026, 9, 14), candidate_days)
        self.assertFalse(any(item.type.value.startswith("bjj_") for item in plan.sessions))

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
        self.assertFalse(any(item.type == WorkoutType.ZONE_2 for item in plan.sessions))

    def test_very_fatigued_replaces_tomorrow_with_recovery(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, fatigue=FatigueState.VERY_FATIGUED)
        tomorrow = next(item for item in plan.sessions if item.local_date == date(2026, 9, 14))

        self.assertEqual(tomorrow.type, WorkoutType.RECOVERY)
        self.assertFalse(any(item.day == date(2026, 9, 14) for item in plan.candidates))

    def test_tired_keeps_bjj_and_strips_intervals(self) -> None:
        monday_bjj = (
            FixedBjjEvent(
                "bjj-mon", "BJJ",
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, tzinfo=TOKYO),
            ),
        )
        kept = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, fixed_bjj=monday_bjj, fatigue=FatigueState.TIRED)
        monday = next(item for item in kept.sessions if item.local_date == date(2026, 9, 14))
        self.assertEqual(monday.type, WorkoutType.BJJ_NORMAL)

        later = datetime(2026, 9, 15, 20, tzinfo=TOKYO)
        existing = (
            ExistingSession(
                "mon", WorkoutType.BJJ_NORMAL,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
        )
        fixed = (
            FixedBjjEvent("thu", "BJJ", datetime(2026, 9, 17, 7, 30, tzinfo=TOKYO), datetime(2026, 9, 17, 9, tzinfo=TOKYO)),
            FixedBjjEvent("sat", "BJJ", datetime(2026, 9, 19, 10, 0, tzinfo=TOKYO), datetime(2026, 9, 19, 11, 30, tzinfo=TOKYO)),
        )
        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=later, fixed_bjj=fixed, existing=existing, fatigue=FatigueState.TIRED,
        )
        strength = next(item for item in plan.sessions if item.local_date == date(2026, 9, 16))
        self.assertEqual(strength.type, WorkoutType.STRENGTH_A)
        self.assertFalse(any(exercise.name == "Stationary bike intervals" for exercise in strength.exercises))

    def test_pain_requires_recovery(self) -> None:
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, fatigue=FatigueState.PAIN)
        tomorrow = next(item for item in plan.sessions if item.local_date == date(2026, 9, 14))
        self.assertEqual(tomorrow.type, WorkoutType.RECOVERY)
        self.assertIn("Pain", tomorrow.reason)

    def test_skipped_strength_a_is_not_moved_forward(self) -> None:
        existing = (
            ExistingSession(
                "sa", WorkoutType.STRENGTH_A,
                datetime(2026, 9, 15, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 15, 8, 30, tzinfo=TOKYO),
                SessionStatus.SKIPPED,
            ),
        )
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, existing=existing)
        self.assertFalse(any(item.type == WorkoutType.STRENGTH_A for item in plan.sessions))

    def test_monday_skip_uses_tuesday_class_without_stacking_gym(self) -> None:
        existing = (
            ExistingSession(
                "mon", WorkoutType.BJJ_NORMAL,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
                SessionStatus.SKIPPED,
            ),
        )
        fixed = (
            FixedBjjEvent(
                "tue", "BJJ",
                datetime(2026, 9, 15, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 15, 9, 0, tzinfo=TOKYO),
            ),
        )
        now = datetime(2026, 9, 14, 20, tzinfo=TOKYO)
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=now, fixed_bjj=fixed, existing=existing)
        tuesday = [item for item in plan.sessions if item.local_date == date(2026, 9, 15)]

        self.assertEqual([item.type for item in tuesday], [WorkoutType.BJJ_NORMAL])
        self.assertTrue(any(item.type == WorkoutType.STRENGTH_A and item.local_date > date(2026, 9, 15) for item in plan.sessions))

    def test_example_24_missed_monday_bjj_after_sunday_strength_a(self) -> None:
        existing = (
            ExistingSession(
                "sun-strength", WorkoutType.STRENGTH_A,
                datetime(2026, 9, 13, 14, 0, tzinfo=TOKYO),
                datetime(2026, 9, 13, 15, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
            ExistingSession(
                "mon-bjj", WorkoutType.BJJ_NORMAL,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
                SessionStatus.SKIPPED,
            ),
        )
        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=datetime(2026, 9, 14, 9, 32, tzinfo=TOKYO),
            existing=existing,
        )
        by_day = {item.local_date: item.type for item in plan.sessions}

        self.assertEqual([item.day for item in plan.candidates], [
            date(2026, 9, 15), date(2026, 9, 17), date(2026, 9, 19),
        ])
        self.assertNotIn(date(2026, 9, 15), by_day)
        self.assertFalse(any(item.type == WorkoutType.STRENGTH_A for item in plan.sessions))
        self.assertEqual(by_day.get(date(2026, 9, 16)), WorkoutType.STRENGTH_B)
        self.assertFalse(any(
            exercise.name == "Towel kettlebell hold" for item in plan.sessions for exercise in item.exercises
        ))
        self.assertEqual(by_day.get(date(2026, 9, 20)), WorkoutType.REST)
        self.assertIn("Replacement BJJ", plan.candidates[0].reason)

    def test_evening_work_does_not_block_replacement_bjj(self) -> None:
        existing = (
            ExistingSession(
                "sun-strength", WorkoutType.STRENGTH_A,
                datetime(2026, 9, 13, 14, 0, tzinfo=TOKYO),
                datetime(2026, 9, 13, 15, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
            ExistingSession(
                "mon-bjj", WorkoutType.BJJ_NORMAL,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
                SessionStatus.SKIPPED,
            ),
        )
        labeled = (
            (datetime(2026, 9, 15, 9, tzinfo=TOKYO), datetime(2026, 9, 15, 10, tzinfo=TOKYO), "Mango Standup"),
            (datetime(2026, 9, 15, 19, tzinfo=TOKYO), datetime(2026, 9, 15, 20, tzinfo=TOKYO), "特許選手権_壁打ち会"),
        )
        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=datetime(2026, 9, 14, 9, 32, tzinfo=TOKYO),
            existing=existing, labeled_busy=labeled,
        )

        self.assertEqual(plan.candidates[0].day, date(2026, 9, 15))
        self.assertFalse(any(
            item.type == WorkoutType.STRENGTH_B and item.local_date == date(2026, 9, 15)
            for item in plan.sessions
        ))

    def test_past_due_planned_bjj_is_treated_as_a_miss(self) -> None:
        existing = (
            ExistingSession(
                "sun-strength", WorkoutType.STRENGTH_A,
                datetime(2026, 9, 13, 14, 0, tzinfo=TOKYO),
                datetime(2026, 9, 13, 15, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
            ExistingSession(
                "mon-bjj", WorkoutType.BJJ_NORMAL,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
                SessionStatus.PLANNED,
            ),
        )
        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=datetime(2026, 9, 14, 9, 32, tzinfo=TOKYO),
            existing=existing,
        )

        self.assertEqual(plan.candidates[0].day, date(2026, 9, 15))
        self.assertFalse(any(
            item.type == WorkoutType.STRENGTH_B and item.local_date == date(2026, 9, 15)
            for item in plan.sessions
        ))

    def test_missed_bjj_searches_next_viable_window_before_lower_priority_work(self) -> None:
        existing = (
            ExistingSession(
                "sun-strength", WorkoutType.STRENGTH_A,
                datetime(2026, 9, 13, 14, 0, tzinfo=TOKYO),
                datetime(2026, 9, 13, 15, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
            ExistingSession(
                "mon-bjj", WorkoutType.BJJ_NORMAL,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
                SessionStatus.SKIPPED,
            ),
        )
        fixed = (
            FixedBjjEvent(
                "wed-bjj", "BJJ",
                datetime(2026, 9, 16, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 16, 9, 0, tzinfo=TOKYO),
            ),
            FixedBjjEvent(
                "sat-bjj", "BJJ",
                datetime(2026, 9, 19, 10, 0, tzinfo=TOKYO),
                datetime(2026, 9, 19, 11, 30, tzinfo=TOKYO),
            ),
        )

        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=datetime(2026, 9, 14, 20, tzinfo=TOKYO),
            fixed_bjj=fixed, existing=existing,
        )

        self.assertEqual([item.day for item in plan.candidates], [date(2026, 9, 15)])
        self.assertFalse(any(
            item.type in {WorkoutType.BJJ_TECHNICAL, WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD}
            and item.local_date == date(2026, 9, 15)
            for item in plan.sessions
        ))
        self.assertFalse(any(item.type == WorkoutType.STRENGTH_A for item in plan.sessions))
        self.assertEqual(sum(item.type == WorkoutType.STRENGTH_B for item in plan.sessions), 1)
        self.assertEqual(sum(item.type == WorkoutType.ZONE_2 for item in plan.sessions), 1)
        saturday = [item.type for item in plan.sessions if item.local_date == date(2026, 9, 19)]
        self.assertEqual(saturday, [WorkoutType.BJJ_HARD])

    def test_skipped_replacement_still_searches_for_bjj_before_lower_priority_work(self) -> None:
        existing = (
            ExistingSession(
                "replaced-bjj", WorkoutType.GRIP,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 7, 40, tzinfo=TOKYO),
                SessionStatus.SKIPPED,
                suppresses_type=WorkoutType.BJJ_NORMAL,
            ),
        )
        fixed = (
            FixedBjjEvent(
                "thu-bjj", "BJJ",
                datetime(2026, 9, 17, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 17, 9, 0, tzinfo=TOKYO),
            ),
            FixedBjjEvent(
                "sat-bjj", "BJJ",
                datetime(2026, 9, 19, 10, 0, tzinfo=TOKYO),
                datetime(2026, 9, 19, 11, 30, tzinfo=TOKYO),
            ),
        )

        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
            fixed_bjj=fixed, existing=existing,
        )

        self.assertEqual([item.day for item in plan.candidates], [date(2026, 9, 15)])

    def test_completed_hard_bjj_prevents_a_second_hard_bjj_target(self) -> None:
        existing = (
            ExistingSession(
                "hard-done", WorkoutType.BJJ_HARD,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
        )
        fixed = (
            FixedBjjEvent(
                "sat-bjj", "BJJ",
                datetime(2026, 9, 19, 10, 0, tzinfo=TOKYO),
                datetime(2026, 9, 19, 11, 30, tzinfo=TOKYO),
            ),
        )

        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=datetime(2026, 9, 15, 20, tzinfo=TOKYO),
            fixed_bjj=fixed, existing=existing,
        )

        saturday = next(item for item in plan.sessions if item.local_date == date(2026, 9, 19))
        self.assertEqual(saturday.type, WorkoutType.BJJ_NORMAL)

    def test_decided_zone2_and_rest_are_not_duplicated(self) -> None:
        existing = (
            ExistingSession(
                "zone", WorkoutType.ZONE_2,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 8, 15, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
            ExistingSession(
                "rest", WorkoutType.REST,
                datetime(2026, 9, 15, 0, 0, tzinfo=TOKYO),
                datetime(2026, 9, 16, 0, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
        )

        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=datetime(2026, 9, 15, 20, tzinfo=TOKYO),
            existing=existing,
        )

        self.assertFalse(any(item.type == WorkoutType.ZONE_2 for item in plan.sessions))
        self.assertFalse(any(item.type == WorkoutType.REST for item in plan.sessions))

    def test_three_consecutive_hard_days_are_rejected(self) -> None:
        existing = (
            ExistingSession(
                "mon", WorkoutType.BJJ_HARD,
                datetime(2026, 9, 14, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 14, 9, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
            ExistingSession(
                "tue", WorkoutType.BJJ_HARD,
                datetime(2026, 9, 15, 7, 30, tzinfo=TOKYO),
                datetime(2026, 9, 15, 9, 0, tzinfo=TOKYO),
                SessionStatus.COMPLETED,
            ),
        )
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, existing=existing)
        self.assertFalse(any(item.type == WorkoutType.STRENGTH_A and item.local_date == date(2026, 9, 16) for item in plan.sessions))

    def test_rain_keeps_zone2_as_indoor(self) -> None:
        plan = self.scheduler.plan_week(
            date(2026, 9, 14), now=self.now,
            weather=(WeatherHint(date(2026, 9, 16), True, "Rain"),),
        )
        zone2 = next(item for item in plan.sessions if item.type == WorkoutType.ZONE_2)
        self.assertEqual(zone2.local_date, date(2026, 9, 16))
        self.assertTrue(any("Indoor" in (exercise.notes or "") for exercise in zone2.exercises))

    def test_readiness_helpers_still_map_legacy_fields(self) -> None:
        assessment = assess_readiness(ReadinessInput(sleep_hours=5, fatigue=2, soreness=2, readiness=4))
        self.assertEqual(assessment.level, ReadinessLevel.GREEN)
        self.assertEqual(assess_readiness(ReadinessInput(pain=True)).level, ReadinessLevel.MANUAL_REVIEW)

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

        self.assertEqual(bjj, [])
        self.assertFalse(any(item.day == date(2026, 10, 10) for item in plan.candidates))
        self.assertFalse(any(item.type == WorkoutType.STRENGTH_A for item in plan.sessions))

    def test_tokyo_day_boundary_uses_local_tomorrow(self) -> None:
        now = datetime(2026, 9, 13, 15, 30, tzinfo=UTC)
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=now)
        self.assertFalse(any(item.local_date < date(2026, 9, 14) for item in plan.sessions))

    def test_late_partial_week_does_not_cram_missed_targets_into_sunday(self) -> None:
        now = datetime(2026, 9, 12, 12, tzinfo=TOKYO)
        plan = self.scheduler.plan_week(date(2026, 9, 7), now=now)

        self.assertEqual([(item.local_date, item.type) for item in plan.sessions], [
            (date(2026, 9, 13), WorkoutType.REST),
        ])
        self.assertEqual(plan.candidates, ())

    def test_heavy_workday_skips_extra_gym_even_if_morning_is_free(self) -> None:
        labeled = (
            (datetime(2026, 9, 15, 9, tzinfo=TOKYO), datetime(2026, 9, 15, 18, tzinfo=TOKYO), "LCA meetings"),
        )
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, labeled_busy=labeled)
        tuesday = [item for item in plan.sessions if item.local_date == date(2026, 9, 15)]
        self.assertFalse(any(item.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B, WorkoutType.ZONE_2} for item in tuesday))

    def test_dinner_or_travel_marks_the_day_too_loaded_for_gym(self) -> None:
        labeled = (
            (datetime(2026, 9, 18, 19, tzinfo=TOKYO), datetime(2026, 9, 18, 21, tzinfo=TOKYO), "Dinner with team"),
        )
        plan = self.scheduler.plan_week(date(2026, 9, 14), now=self.now, labeled_busy=labeled)
        friday = [item for item in plan.sessions if item.local_date == date(2026, 9, 18)]
        self.assertFalse(any(item.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B} for item in friday))

    def test_week_quality_bands(self) -> None:
        self.assertEqual(assess_week_quality(bjj=3, hard_bjj=True, strength=2, zone_2=1, intervals=1, rest=True), WeekQuality.EXCELLENT)
        self.assertEqual(assess_week_quality(bjj=2, hard_bjj=False, strength=1, zone_2=1, intervals=0, rest=True), WeekQuality.ACCEPTABLE)
        self.assertEqual(assess_week_quality(bjj=2, hard_bjj=False, strength=3, zone_2=0, intervals=2, rest=False), WeekQuality.BAD_PLANNING)


if __name__ == "__main__":
    unittest.main()
