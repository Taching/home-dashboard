import unittest

from app.domain.training.review import (
    exercise_done,
    kinds_match,
    local_workout_review,
    week_counters_text,
    workout_review_prompt,
)


class TrainingReviewTests(unittest.TestCase):
    def test_kinds_match_aliases(self):
        self.assertTrue(kinds_match("strength_a", "strength_a"))
        self.assertTrue(kinds_match("bjj_normal", "bjj"))
        self.assertTrue(kinds_match("zone_2", "zone2"))
        self.assertFalse(kinds_match("strength_a", "strength_b"))

    def test_exercise_names_tolerate_plan_titles(self):
        done = {
            "Warm-up": True,
            "Stationary Bike Intervals": True,
            "Back Squat": False,
        }
        self.assertTrue(exercise_done("Stationary bike warm-up", done))
        self.assertTrue(exercise_done("Stationary bike intervals", done))
        self.assertFalse(exercise_done("Back Squat", done))
        self.assertIsNone(exercise_done("Towel kettlebell hold", done))

    def test_local_review_covers_week_and_tomorrow(self):
        text = local_workout_review(
            session={"title": "Gym (Strength A)", "status": "completed"},
            kind="strength_a",
            note="all the workout is feel easy but the interval was hard",
            overview={
                "compliance": {
                    "bjj": {"completed": 0, "target": 3},
                    "strength": {"completed": 1, "target": 2},
                    "zone_2": {"completed": 0, "target": 1},
                    "grip": {"completed": 0, "target": 2},
                    "rest": {"completed": 0, "target": 1},
                },
                "tomorrow_prescription": {
                    "session": "bjj_normal",
                    "time": "07:30",
                    "why": "Selected from the weekday BJJ pair.",
                    "weekly_status": {
                        "bjj": {"completed": 0, "target": 3},
                        "strength": {"completed": 1, "target": 2},
                        "zone_2": {"completed": 0, "target": 1},
                        "grip": {"completed": 0, "target": 2},
                        "rest": {"completed": 0, "target": 1},
                    },
                },
            },
        )
        self.assertIn("Gym (Strength A) is in", text)
        self.assertIn("interval was hard", text)
        self.assertIn("Strength 1/2", text)
        self.assertIn("Tomorrow is bjj normal at 07:30", text)
        self.assertIn("Do not add extra gym", text)

    def test_prompt_asks_chili_for_a_week_read(self):
        prompt = workout_review_prompt(
            session={"title": "Gym (Strength A)", "status": "completed"},
            kind="strength_a",
            note="easy lifts",
            exercises=[{"name": "Back Squat", "done": True}],
            overview={"tomorrow_prescription": {"session": "rest", "why": "Protect recovery."}},
        )
        self.assertIn("easy lifts", prompt)
        self.assertIn("What is already done this week", prompt)
        self.assertIn("Do not invent extra training", prompt)

    def test_week_counters_skip_missing_keys(self):
        self.assertEqual(week_counters_text(None), "Weekly status unavailable.")
        self.assertIn("BJJ 1/3", week_counters_text({"bjj": {"completed": 1, "target": 3}}))


if __name__ == "__main__":
    unittest.main()
