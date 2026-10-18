"""March 2027 campaign: per-week quotas from the competition plan (rebuild._assign_campaign)."""
import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.training.classes import MITA_CLASS_TEMPLATE
from app.domain.training.policy import weekly_targets
from app.domain.training.scheduler import TrainingScheduler
from app.domain.training.types import (
    ExistingSession, FatigueState, FixedBjjEvent, SessionStatus, TrainingPhase, WorkoutType,
)

TOKYO = ZoneInfo("Asia/Tokyo")
BUILD_WEEK = date(2026, 10, 19)


def _week(plan, week_start: date) -> dict[date, WorkoutType]:
    return {
        item.local_date: item.type
        for item in plan.sessions
        if week_start <= item.local_date < week_start + timedelta(days=7)
    }


class CampaignWeekTests(unittest.TestCase):
    def setUp(self) -> None:
        self.scheduler = TrainingScheduler("Asia/Tokyo")

    def plan(self, week_start: date, *, now: datetime | None = None, **kwargs):
        now = now or datetime.combine(week_start - timedelta(days=1), time(20), TOKYO)
        return self.scheduler.plan_week(week_start, now=now, class_template=MITA_CLASS_TEMPLATE, **kwargs)

    def test_build_week_matches_the_example_week(self) -> None:
        week = _week(self.plan(BUILD_WEEK), BUILD_WEEK)
        expected = [
            WorkoutType.BJJ_NORMAL, WorkoutType.STRENGTH_A, WorkoutType.BJJ_NORMAL,
            WorkoutType.STRENGTH_B, WorkoutType.REST, WorkoutType.BJJ_HARD, WorkoutType.ZONE_2,
        ]
        self.assertEqual([week.get(BUILD_WEEK + timedelta(days=offset)) for offset in range(7)], expected)

    def test_build_week_has_no_intervals_or_grip(self) -> None:
        plan = self.plan(BUILD_WEEK)
        names = {exercise.name for item in plan.sessions for exercise in item.exercises}
        self.assertNotIn("Stationary bike intervals", names)
        self.assertNotIn("Towel kettlebell hold", names)
        self.assertIn("Easy cardio", names)
        self.assertNotIn(WorkoutType.GRIP, {item.type for item in plan.sessions})

    def test_peak_week_has_four_bjj_and_two_set_strength(self) -> None:
        week_start = date(2027, 1, 25)
        plan = self.plan(week_start)
        week = _week(plan, week_start)
        self.assertEqual(sum(kind.value.startswith("bjj_") for kind in week.values()), 4)
        self.assertEqual(sum(kind.value.startswith("strength_") for kind in week.values()), 2)
        lifts = [
            exercise for item in plan.sessions if item.local_date in week and item.type == WorkoutType.STRENGTH_A
            for exercise in item.exercises if exercise.name == "Trap-bar Deadlift"
        ]
        self.assertTrue(lifts)
        self.assertTrue(all(exercise.sets == 2 for exercise in lifts))

    def test_competition_week_tapers_and_rests_the_day_before(self) -> None:
        week_start = date(2027, 3, 1)
        week = _week(self.plan(week_start), week_start)
        self.assertEqual(week.get(date(2027, 3, 4)), WorkoutType.REST)
        for day in (date(2027, 3, 5), date(2027, 3, 6), date(2027, 3, 7)):
            self.assertEqual(week.get(day), WorkoutType.COMPETITION)
        self.assertEqual(sum(kind.value.startswith("bjj_") for kind in week.values()), 2)
        self.assertEqual(sum(kind.value.startswith("strength_") for kind in week.values()), 1)

    def test_last_hard_simulation_is_about_a_week_out(self) -> None:
        week_start = date(2027, 2, 22)
        week = _week(self.plan(week_start), week_start)
        self.assertEqual(week.get(date(2027, 2, 27)), WorkoutType.BJJ_HARD)

    def test_every_campaign_week_keeps_a_full_rest_day(self) -> None:
        week_start = BUILD_WEEK
        while week_start < date(2027, 3, 1):
            with self.subTest(week=week_start):
                week = _week(self.plan(week_start), week_start)
                free = [
                    week_start + timedelta(days=offset) for offset in range(7)
                    if week.get(week_start + timedelta(days=offset)) in {None, WorkoutType.REST}
                ]
                self.assertGreaterEqual(len(free), 1)
            week_start += timedelta(days=7)

    def test_strength_is_never_on_back_to_back_days_or_before_hard_bjj(self) -> None:
        week_start = BUILD_WEEK
        while week_start < date(2027, 3, 1):
            week = _week(self.plan(week_start), week_start)
            for day, kind in week.items():
                if not kind.value.startswith("strength_"):
                    continue
                with self.subTest(day=day):
                    self.assertFalse(str(week.get(day + timedelta(days=1), "")).startswith("strength_"))
                    self.assertNotEqual(week.get(day + timedelta(days=1)), WorkoutType.BJJ_HARD)
            week_start += timedelta(days=7)

    def test_calendar_bjj_counts_toward_the_week_and_strength_moves(self) -> None:
        fixed = (FixedBjjEvent(
            "tue", "BJJ",
            datetime(2026, 10, 20, 7, 30, tzinfo=TOKYO), datetime(2026, 10, 20, 9, tzinfo=TOKYO),
        ),)
        week = _week(self.plan(BUILD_WEEK, fixed_bjj=fixed), BUILD_WEEK)
        self.assertTrue(week[date(2026, 10, 20)].value.startswith("bjj_"))
        self.assertEqual(sum(kind.value.startswith("bjj_") for kind in week.values()), 3)
        self.assertEqual(sum(kind.value.startswith("strength_") for kind in week.values()), 2)

    def test_missed_monday_bjj_is_replaced_on_a_later_class_day(self) -> None:
        missed = ExistingSession(
            "mon", WorkoutType.BJJ_NORMAL,
            datetime(2026, 10, 19, 7, 30, tzinfo=TOKYO), datetime(2026, 10, 19, 9, tzinfo=TOKYO),
            SessionStatus.SKIPPED,
        )
        now = datetime(2026, 10, 19, 20, tzinfo=TOKYO)
        week = _week(self.plan(BUILD_WEEK, now=now, existing=(missed,)), BUILD_WEEK)
        upcoming_bjj = [day for day, kind in week.items() if kind.value.startswith("bjj_") and day > date(2026, 10, 19)]
        self.assertEqual(len(upcoming_bjj), 3)

    def test_skipped_lift_counts_as_decided_for_the_week(self) -> None:
        skipped = ExistingSession(
            "tue-a", WorkoutType.STRENGTH_A,
            datetime(2026, 10, 20, 7, 30, tzinfo=TOKYO), datetime(2026, 10, 20, 8, 45, tzinfo=TOKYO),
            SessionStatus.SKIPPED,
        )
        now = datetime(2026, 10, 20, 20, tzinfo=TOKYO)
        week = _week(self.plan(BUILD_WEEK, now=now, existing=(skipped,)), BUILD_WEEK)
        later_strength = [day for day, kind in week.items() if kind.value.startswith("strength_") and day > date(2026, 10, 20)]
        self.assertEqual(len(later_strength), 1)

    def test_very_fatigued_rests_today_and_tomorrow(self) -> None:
        now = datetime(2026, 10, 19, 6, tzinfo=TOKYO)
        plan = self.plan(BUILD_WEEK, now=now, fatigue=FatigueState.VERY_FATIGUED)
        week = _week(plan, BUILD_WEEK)
        for day in (date(2026, 10, 19), date(2026, 10, 20)):
            self.assertIn(week.get(day), {WorkoutType.REST, WorkoutType.RECOVERY, None})

    def test_targets_drop_second_cardio_for_a_fourth_bjj(self) -> None:
        self.assertEqual(weekly_targets(TrainingPhase.BUILD_3)["zone_2"], 1)
        self.assertEqual(weekly_targets(TrainingPhase.BUILD_3, bjj_count=4)["zone_2"], 0)
        self.assertEqual(weekly_targets(TrainingPhase.BUILD_3)["intervals"], 0)


if __name__ == "__main__":
    unittest.main()
