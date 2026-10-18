import unittest
from datetime import date, timedelta

from app.domain import cut_plan as cut


def _series(start: date, values: list[float]) -> dict[date, float]:
    return {start + timedelta(days=offset): value for offset, value in enumerate(values)}


class TargetTests(unittest.TestCase):
    def test_checkpoints_are_hit_exactly(self) -> None:
        self.assertEqual(cut.target_for(date(2026, 11, 2)), (83.0, 83.0))
        self.assertEqual(cut.target_for(date(2026, 12, 7)), (80.5, 81.0))
        self.assertEqual(cut.target_for(date(2027, 3, 1)), (74.0, 74.5))

    def test_target_interpolates_and_clamps(self) -> None:
        low, high = cut.target_for(date(2026, 10, 26))
        self.assertAlmostEqual(low, 83.5)
        self.assertEqual(cut.target_for(date(2026, 10, 1)), (84.0, 84.0))
        self.assertEqual(cut.target_for(date(2027, 3, 6)), (74.0, 74.5))


class AverageTests(unittest.TestCase):
    def test_seven_day_average_uses_only_logged_days(self) -> None:
        weights = {date(2026, 10, 19): 84.0, date(2026, 10, 21): 83.0}
        self.assertEqual(cut.seven_day_average(weights, date(2026, 10, 25)), (83.5, 2))
        self.assertEqual(cut.seven_day_average(weights, date(2026, 10, 28)), (None, 0))

    def test_weekly_change_needs_three_weigh_ins_each_side(self) -> None:
        weights = _series(date(2026, 10, 19), [84.0] * 7 + [83.5] * 7)
        self.assertEqual(cut.weekly_change(weights, date(2026, 11, 1)), -0.5)
        self.assertIsNone(cut.weekly_change({date(2026, 11, 1): 83.0}, date(2026, 11, 1)))

    def test_trend_status(self) -> None:
        self.assertEqual(cut.trend_status(83.2, (83.0, 83.0)), "on_trend")
        self.assertEqual(cut.trend_status(83.6, (83.0, 83.0)), "above")
        self.assertEqual(cut.trend_status(None, (83.0, 83.0)), "unknown")


class NutritionTests(unittest.TestCase):
    def test_training_and_rest_day_targets(self) -> None:
        self.assertEqual(cut.nutrition_for("bjj_hard")["kcal"], 2300)
        self.assertEqual(cut.nutrition_for("strength_a")["kind"], "training")
        self.assertEqual(cut.nutrition_for("zone_2")["kcal"], 2000)
        self.assertEqual(cut.nutrition_for(None)["kind"], "rest")
        self.assertEqual(cut.nutrition_for("rest", adjustment_kcal=-150)["kcal"], 1850)
        self.assertEqual(cut.nutrition_for("bjj_normal")["protein_g"], [165, 175])


class AdjustmentTests(unittest.TestCase):
    def test_trial_holds_steady(self) -> None:
        self.assertEqual(cut.intake_adjustment(date(2026, 10, 26), [-0.1, -0.1])[0], 0)

    def test_two_slow_weeks_cut_150(self) -> None:
        self.assertEqual(cut.intake_adjustment(date(2026, 11, 9), [-0.1, -0.2])[0], -150)

    def test_one_slow_week_holds(self) -> None:
        self.assertEqual(cut.intake_adjustment(date(2026, 11, 9), [-0.1, -0.5])[0], 0)

    def test_fast_loss_adds_150(self) -> None:
        self.assertEqual(cut.intake_adjustment(date(2026, 11, 9), [-0.9, -0.5])[0], 150)

    def test_worse_performance_adds_150(self) -> None:
        self.assertEqual(cut.intake_adjustment(date(2026, 11, 9), [-0.5, -0.5], performance_worse=True)[0], 150)

    def test_recent_adjustment_holds_for_14_days(self) -> None:
        result = cut.intake_adjustment(date(2026, 11, 16), [-0.1, -0.1], last_adjustment_on=date(2026, 11, 9))
        self.assertEqual(result[0], 0)


class DivisionTests(unittest.TestCase):
    def test_before_decision_date_stays_provisional(self) -> None:
        result = cut.division_status(date(2026, 12, 1), 80.0)
        self.assertEqual(result["division"], "lightweight")
        self.assertFalse(result["decided"])

    def test_decision_rules(self) -> None:
        day = cut.DIVISION_DECISION_DATE
        self.assertEqual(cut.division_status(day, 77.8, performance_ok=True)["division"], "lightweight")
        self.assertTrue(cut.division_status(day, 77.8, performance_ok=True)["decided"])
        self.assertEqual(cut.division_status(day, 79.4)["division"], "middleweight")
        self.assertEqual(cut.division_status(day, 77.8, performance_ok=False)["division"], "middleweight")
        self.assertFalse(cut.division_status(day, 78.5)["decided"])


if __name__ == "__main__":
    unittest.main()
