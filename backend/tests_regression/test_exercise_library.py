"""Tests for the exercise library and alternatives engine.

Tests spec sections 5, 6, 7, 8 (Milestone 1).
"""

import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database.session import Base
from app.domain.exercise_library import (
    AlternativesRequest,
    ExerciseLibraryService,
    EXERCISE_SEED,
    BJJ_FAILURE_SEED,
    get_filter_options,
)


def test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


class ExerciseLibrarySeedTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = test_session_factory()
        self.service = ExerciseLibraryService(session_factory=self.factory)

    def test_seed_populates_exercises(self) -> None:
        count = self.service.seed_if_empty()
        self.assertEqual(count, len(EXERCISE_SEED))
        exercises = self.service.list_exercises()
        self.assertEqual(len(exercises), len(EXERCISE_SEED))

    def test_seed_populates_bjj_failure_types(self) -> None:
        self.service.seed_if_empty()
        failures = self.service.get_bjj_failure_types()
        self.assertEqual(len(failures), len(BJJ_FAILURE_SEED))
        codes = {f["code"] for f in failures}
        self.assertIn("grip_lost", codes)
        self.assertIn("frame_late", codes)
        self.assertIn("other", codes)

    def test_seed_is_idempotent(self) -> None:
        first = self.service.seed_if_empty()
        second = self.service.seed_if_empty()
        self.assertEqual(first, len(EXERCISE_SEED))
        self.assertEqual(second, 0)


class ExerciseSearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = test_session_factory()
        self.service = ExerciseLibraryService(session_factory=self.factory)
        self.service.seed_if_empty()

    def test_search_by_name(self) -> None:
        results = self.service.list_exercises(search="bench press")
        self.assertTrue(len(results) > 0)
        self.assertTrue(any("bench" in r["name"].lower() for r in results))

    def test_search_by_alias_grappler_twist(self) -> None:
        results = self.service.list_exercises(search="grappler twist")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["slug"], "landmine-180")

    def test_search_by_alias_full_contact_twist(self) -> None:
        results = self.service.list_exercises(search="full-contact twist")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["slug"], "landmine-180")

    def test_search_by_alias_barbell_rotation(self) -> None:
        results = self.service.list_exercises(search="barbell rotation")
        self.assertTrue(len(results) >= 1)
        slugs = [r["slug"] for r in results]
        self.assertIn("landmine-180", slugs)

    def test_filter_by_movement_pattern(self) -> None:
        results = self.service.list_exercises(pattern="horizontal_push")
        self.assertTrue(len(results) > 0)
        self.assertTrue(all(r["movement_pattern"] == "horizontal_push" for r in results))

    def test_filter_by_region(self) -> None:
        results = self.service.list_exercises(region="lower")
        self.assertTrue(len(results) > 0)
        self.assertTrue(all(r["primary_region"] == "lower" for r in results))

    def test_filter_by_category(self) -> None:
        results = self.service.list_exercises(category="power")
        self.assertTrue(len(results) > 0)
        self.assertTrue(all(r["category"] == "power" for r in results))

    def test_filter_by_bjj_tag(self) -> None:
        results = self.service.list_exercises(bjj_tag="grip")
        self.assertTrue(len(results) > 0)
        self.assertTrue(all(any("grip" in tag.lower() for tag in r["bjj_tags"]) for r in results))


class ExerciseClassificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = test_session_factory()
        self.service = ExerciseLibraryService(session_factory=self.factory)
        self.service.seed_if_empty()

    def test_bench_press_is_horizontal_push(self) -> None:
        exercise = self.service.get_exercise("barbell-bench-press")
        self.assertIsNotNone(exercise)
        self.assertEqual(exercise["movement_pattern"], "horizontal_push")

    def test_squat_is_squat_not_vertical_push(self) -> None:
        exercise = self.service.get_exercise("back-squat")
        self.assertIsNotNone(exercise)
        self.assertEqual(exercise["movement_pattern"], "squat")
        self.assertNotEqual(exercise["movement_pattern"], "vertical_push")

    def test_deadlift_is_hinge_not_vertical_push(self) -> None:
        exercise = self.service.get_exercise("conventional-deadlift")
        self.assertIsNotNone(exercise)
        self.assertEqual(exercise["movement_pattern"], "hinge")
        self.assertNotEqual(exercise["movement_pattern"], "vertical_push")

    def test_overhead_press_is_vertical_push(self) -> None:
        exercise = self.service.get_exercise("barbell-overhead-press")
        self.assertIsNotNone(exercise)
        self.assertEqual(exercise["movement_pattern"], "vertical_push")

    def test_kb_swing_clean_snatch_getup_windmill_halo_press_exists(self) -> None:
        kb_exercises = [
            "two-hand-kettlebell-swing",
            "kettlebell-clean",
            "kettlebell-snatch",
            "turkish-get-up",
            "kettlebell-windmill",
            "kettlebell-halo",
            "kettlebell-strict-press",
        ]
        for slug in kb_exercises:
            exercise = self.service.get_exercise(slug)
            self.assertIsNotNone(exercise, f"Expected exercise {slug} not found")

    def test_rotational_sled_sprawl_grip_neck_work_exists(self) -> None:
        exercises = [
            "landmine-180",
            "medicine-ball-rotational-throw",
            "sled-push",
            "backward-sled-drag",
            "sprawl",
            "penetration-step",
            "towel-dead-hang",
            "four-way-neck-isometric",
            "wrestler-bridge",
        ]
        for slug in exercises:
            exercise = self.service.get_exercise(slug)
            self.assertIsNotNone(exercise, f"Expected exercise {slug} not found")

    def test_advanced_exercises_show_risk_notes(self) -> None:
        wrestler_bridge = self.service.get_exercise("wrestler-bridge")
        self.assertIsNotNone(wrestler_bridge)
        self.assertEqual(wrestler_bridge["difficulty"], "advanced")
        self.assertIsNotNone(wrestler_bridge["risk_notes"])


class AlternativesEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = test_session_factory()
        self.service = ExerciseLibraryService(session_factory=self.factory)
        self.service.seed_if_empty()

    def test_bench_press_alternatives_include_db_bench(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"dumbbell", "bench"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertIn("dumbbell-bench-press", slugs)

    def test_bench_press_alternatives_include_weighted_push_up(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"bodyweight", "plate"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertIn("weighted-push-up", slugs)

    def test_bench_press_alternatives_include_floor_press(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"dumbbell"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertIn("dumbbell-floor-press", slugs)

    def test_bench_press_alternatives_exclude_overhead_press(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"barbell", "bench", "dumbbell"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("barbell-overhead-press", slugs)
        self.assertNotIn("dumbbell-overhead-press", slugs)

    def test_bench_press_alternatives_exclude_rows(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"barbell", "bench", "dumbbell", "cable"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("seated-cable-row", slugs)
        self.assertNotIn("chest-supported-dumbbell-row", slugs)

    def test_front_squat_alternatives_include_bilateral_squats(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="front-squat",
            available_equipment=frozenset({"barbell", "rack", "kettlebell"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertIn("back-squat", slugs)
        self.assertIn("goblet-squat", slugs)

    def test_front_squat_alternatives_exclude_deadlift(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="front-squat",
            available_equipment=frozenset({"barbell", "rack", "trap_bar"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("conventional-deadlift", slugs)
        self.assertNotIn("trap-bar-deadlift", slugs)

    def test_front_squat_alternatives_exclude_kb_swing(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="front-squat",
            available_equipment=frozenset({"barbell", "rack", "kettlebell"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("two-hand-kettlebell-swing", slugs)

    def test_deadlift_alternatives_include_trap_bar_sumo(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="conventional-deadlift",
            available_equipment=frozenset({"barbell", "trap_bar"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertIn("trap-bar-deadlift", slugs)
        self.assertIn("sumo-deadlift", slugs)

    def test_deadlift_alternatives_exclude_kb_swing(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="conventional-deadlift",
            available_equipment=frozenset({"barbell", "kettlebell"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("two-hand-kettlebell-swing", slugs)

    def test_landmine_180_excludes_pallof_press(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="landmine-180",
            available_equipment=frozenset({"barbell", "landmine", "cable", "resistance_band"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("pallof-press", slugs)

    def test_pull_up_alternatives_include_chin_up_lat_pulldown(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="pull-up",
            available_equipment=frozenset({"pull_up_bar", "bodyweight", "cable"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertIn("chin-up", slugs)
        self.assertIn("lat-pulldown", slugs)

    def test_pull_up_alternatives_exclude_seated_cable_row(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="pull-up",
            available_equipment=frozenset({"pull_up_bar", "bodyweight", "cable"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("seated-cable-row", slugs)

    def test_goblet_squat_with_kettlebell_only(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="front-squat",
            available_equipment=frozenset({"kettlebell"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertIn("goblet-squat", slugs)
        goblet = next(a for a in result.alternatives if a.slug == "goblet-squat")
        self.assertIsNotNone(goblet.tradeoff)

    def test_equipment_matching_requires_full_setup(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="back-squat",
            available_equipment=frozenset({"barbell"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("front-squat", slugs)

    def test_alternatives_include_why_reasons(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"dumbbell", "bench"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        self.assertTrue(len(result.alternatives) > 0)
        self.assertTrue(len(result.alternatives[0].why) > 0)


class OverrideTests(unittest.TestCase):
    def setUp(self) -> None:
        self.factory = test_session_factory()
        self.service = ExerciseLibraryService(session_factory=self.factory)
        self.service.seed_if_empty()

    def test_user_exclude_respected(self) -> None:
        self.service.set_override("barbell-bench-press", "dumbbell-bench-press", "exclude")
        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"dumbbell", "bench"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertNotIn("dumbbell-bench-press", slugs)

    def test_user_prefer_boosts_score(self) -> None:
        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"dumbbell", "bench", "bodyweight", "plate"}),
            allow_advanced=True,
        )
        result_before = self.service.find_alternatives(request)
        before_scores = {a.slug: a.score for a in result_before.alternatives}

        self.service.set_override("barbell-bench-press", "weighted-push-up", "prefer")

        result_after = self.service.find_alternatives(request)
        after_scores = {a.slug: a.score for a in result_after.alternatives}

        self.assertGreater(after_scores.get("weighted-push-up", 0), before_scores.get("weighted-push-up", 0))

    def test_delete_override(self) -> None:
        self.service.set_override("barbell-bench-press", "dumbbell-bench-press", "exclude")
        deleted = self.service.delete_override("barbell-bench-press", "dumbbell-bench-press")
        self.assertTrue(deleted)

        request = AlternativesRequest(
            source_exercise_slug="barbell-bench-press",
            available_equipment=frozenset({"dumbbell", "bench"}),
            allow_advanced=True,
        )
        result = self.service.find_alternatives(request)
        slugs = [a.slug for a in result.alternatives]
        self.assertIn("dumbbell-bench-press", slugs)


class FilterOptionsTests(unittest.TestCase):
    def test_filter_options_returns_all_categories(self) -> None:
        options = get_filter_options()
        self.assertIn("categories", options)
        self.assertIn("strength", options["categories"])
        self.assertIn("power", options["categories"])
        self.assertIn("conditioning", options["categories"])

    def test_filter_options_includes_extended_equipment_tokens(self) -> None:
        options = get_filter_options()
        self.assertIn("bar", options["equipment_tokens"])
        self.assertIn("hands", options["equipment_tokens"])


if __name__ == "__main__":
    unittest.main()
