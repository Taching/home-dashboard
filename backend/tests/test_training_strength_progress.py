import unittest
from datetime import date

from app.domain.training import strength_progress as sp
from app.domain.training.types import WorkoutType


class ClassifyTests(unittest.TestCase):
    def test_easy_low_rpe_clean_technique(self) -> None:
        result = sp.classify(rpe=6, technique="clean", pain=False, sets_done=3, sets_prescribed=3)
        self.assertEqual(result, sp.Classification.EASY)

    def test_appropriate_mid_rpe(self) -> None:
        result = sp.classify(rpe=7.5, technique="clean", pain=False, sets_done=3, sets_prescribed=3)
        self.assertEqual(result, sp.Classification.APPROPRIATE)

    def test_hard_high_rpe(self) -> None:
        result = sp.classify(rpe=8.5, technique="clean", pain=False, sets_done=3, sets_prescribed=3)
        self.assertEqual(result, sp.Classification.HARD)

    def test_too_hard_on_pain(self) -> None:
        result = sp.classify(rpe=6, technique="clean", pain=True, sets_done=3, sets_prescribed=3)
        self.assertEqual(result, sp.Classification.TOO_HARD)

    def test_too_hard_on_missed_sets(self) -> None:
        result = sp.classify(rpe=8, technique="clean", pain=False, sets_done=2, sets_prescribed=3)
        self.assertEqual(result, sp.Classification.TOO_HARD)

    def test_too_hard_on_technique_breakdown(self) -> None:
        result = sp.classify(rpe=7, technique="breakdown", pain=False, sets_done=3, sets_prescribed=3)
        self.assertEqual(result, sp.Classification.TOO_HARD)

    def test_too_hard_on_rpe_nine_plus(self) -> None:
        result = sp.classify(rpe=9, technique="clean", pain=False, sets_done=3, sets_prescribed=3)
        self.assertEqual(result, sp.Classification.TOO_HARD)


class DecideTests(unittest.TestCase):
    def test_decisions_per_classification(self) -> None:
        self.assertEqual(sp.decide(sp.Classification.EASY), sp.Decision.PROGRESS)
        self.assertEqual(sp.decide(sp.Classification.APPROPRIATE), sp.Decision.REPEAT)
        self.assertEqual(sp.decide(sp.Classification.HARD), sp.Decision.REPEAT)
        self.assertEqual(sp.decide(sp.Classification.TOO_HARD), sp.Decision.REDUCE)


class ApplyDecisionLoadKindTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recipe = sp.recipe_for("Deadlift")
        self.state = sp.ExerciseState(
            workout_type="strength_b", exercise_name="Deadlift",
            load_value=140, load_unit="kg", sets=3, rep_target=None,
        )

    def test_progress_bumps_load_by_increment(self) -> None:
        result = sp.apply_decision(self.state, sp.Decision.PROGRESS, self.recipe)
        self.assertEqual(result.load_value, 142.5)
        self.assertEqual(result.sets, 3)

    def test_repeat_holds_load(self) -> None:
        result = sp.apply_decision(self.state, sp.Decision.REPEAT, self.recipe)
        self.assertEqual(result.load_value, 140)

    def test_reduce_cuts_load_and_drops_a_set(self) -> None:
        result = sp.apply_decision(self.state, sp.Decision.REDUCE, self.recipe)
        self.assertLess(result.load_value, 140)
        self.assertEqual(result.sets, 2)


class ApplyDecisionDoubleProgressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.recipe = sp.recipe_for("Military Press")
        self.state = sp.ExerciseState(
            workout_type="strength_b", exercise_name="Military Press",
            load_value=52, load_unit="kg", sets=3, rep_target=5,
        )

    def test_progress_climbs_reps_before_load(self) -> None:
        result = sp.apply_decision(self.state, sp.Decision.PROGRESS, self.recipe)
        self.assertEqual(result.rep_target, 6)
        self.assertEqual(result.load_value, 52)

    def test_progress_at_rep_max_bumps_load_and_resets_reps(self) -> None:
        at_max = sp.ExerciseState(**{**self.state.__dict__, "rep_target": 8})
        result = sp.apply_decision(at_max, sp.Decision.PROGRESS, self.recipe)
        self.assertEqual(result.rep_target, 6)
        self.assertEqual(result.load_value, 54.5)

    def test_repeat_at_rep_max_holds_load(self) -> None:
        at_max = sp.ExerciseState(**{**self.state.__dict__, "rep_target": 8})
        result = sp.apply_decision(at_max, sp.Decision.REPEAT, self.recipe)
        self.assertEqual(result.rep_target, 8)
        self.assertEqual(result.load_value, 52)

    def test_load_optional_recipe_never_touches_load(self) -> None:
        recipe = sp.recipe_for("Leg Raise")
        state = sp.ExerciseState(
            workout_type="strength_b", exercise_name="Leg Raise",
            load_value=None, load_unit=None, sets=3, rep_target=10,
        )
        result = sp.apply_decision(state, sp.Decision.PROGRESS, recipe)
        self.assertIsNone(result.load_value)
        self.assertEqual(result.rep_target, 6)


class DeloadPrescriptionTests(unittest.TestCase):
    def test_deload_cuts_sets_about_40_percent_at_the_same_load(self) -> None:
        recipe = sp.recipe_for("Trap-bar Deadlift")
        state = sp.ExerciseState(
            workout_type="strength_a", exercise_name="Trap-bar Deadlift",
            load_value=125, load_unit="kg", sets=3, rep_target=5,
        )
        result = sp.deload_prescription(state, recipe)
        self.assertEqual(result.sets, 2)
        self.assertEqual(result.load_value, 125)
        self.assertEqual(sp.deload_prescription(sp.ExerciseState(**{**state.__dict__, "sets": 2}), recipe).sets, 1)

    def test_deload_resets_rep_target_to_bottom_of_range(self) -> None:
        recipe = sp.recipe_for("Weighted Dips")
        state = sp.ExerciseState(
            workout_type="strength_b", exercise_name="Weighted Dips",
            load_value=20, load_unit="kg", sets=3, rep_target=8,
        )
        result = sp.deload_prescription(state, recipe)
        self.assertEqual(result.rep_target, 6)


class EvaluateDeloadTriggersTests(unittest.TestCase):
    def test_no_signals_does_not_force_deload(self) -> None:
        result = sp.evaluate_deload_triggers([], [])
        self.assertFalse(result["strength_a"])
        self.assertFalse(result["strength_b"])

    def test_two_signals_force_deload_for_both_tracks(self) -> None:
        sessions = [
            {"planned_type": "strength_b", "status": "completed", "result": {"session_rpe": 9}},
            {"planned_type": "strength_a", "status": "completed", "result": {"session_rpe": 9.5}},
            {"planned_type": "bjj_normal", "status": "completed", "result": {"grip_fatigue": "HIGH"}},
        ]
        result = sp.evaluate_deload_triggers(sessions, [])
        self.assertTrue(result["strength_a"])
        self.assertTrue(result["strength_b"])

    def test_single_signal_does_not_force_deload(self) -> None:
        sessions = [
            {"planned_type": "bjj_normal", "status": "completed", "result": {"grip_fatigue": "HIGH"}},
        ]
        result = sp.evaluate_deload_triggers(sessions, [7, 7.5, 8])
        self.assertFalse(result["strength_a"])

    def test_poor_sleep_counts_as_a_signal(self) -> None:
        sessions = [
            {"planned_type": "bjj_normal", "status": "completed", "result": {"grip_fatigue": "HIGH"}},
        ]
        result = sp.evaluate_deload_triggers(sessions, [5, 5.5, 4.5])
        self.assertTrue(result["strength_b"])


class EndToEndProgressionTests(unittest.TestCase):
    def _service(self):
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.database.session import Base
        from app.domain.training.service import TrainingService

        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        return TrainingService(factory, timezone_name="Asia/Tokyo")

    def test_easy_session_progresses_stored_deadlift_prescription(self) -> None:
        from datetime import UTC, datetime
        from app.database.models import TrainingExerciseProgress

        service = self._service()
        now = datetime(2026, 9, 13, 15, tzinfo=UTC)
        service.bootstrap(now)
        created = service.schedule_gym(date(2026, 9, 13), "strength_a", now=now)
        deadlift = next(item for item in created["exercises"] if item["name"] == "Trap-bar Deadlift")
        self.assertEqual(deadlift["load_value"], 125)
        self.assertEqual(deadlift["reps"], "4")
        service.log_session_result(
            created["id"], status="completed",
            exercises=[{
                "name": "Trap-bar Deadlift", "actual_load": 125, "actual_sets": 3, "actual_reps": "4,4,4",
                "rpe": 6, "technique": "clean", "pain": False, "completed": True, "done": True,
            }],
            now=now,
        )
        with service._session_factory() as session:
            row = session.get(TrainingExerciseProgress, ("strength_a", "Trap-bar Deadlift"))
            self.assertEqual(row.load_value, 125)
            self.assertEqual(row.rep_target, 5)
            self.assertEqual(row.last_classification, "easy")
            self.assertEqual(row.last_decision, "progress")
        # And the per-exercise builder used by manual placement picks it up.
        with service._session_factory() as session:
            exercises = service._strength_exercises_now(session, WorkoutType.STRENGTH_A)
        next_deadlift = next(item for item in exercises if item.name == "Trap-bar Deadlift")
        self.assertEqual(next_deadlift.reps, "5")

    def test_logged_actual_load_replaces_the_starting_estimate(self) -> None:
        from datetime import UTC, datetime
        from app.database.models import TrainingExerciseProgress

        service = self._service()
        now = datetime(2026, 9, 13, 15, tzinfo=UTC)
        service.bootstrap(now)
        created = service.schedule_gym(date(2026, 9, 13), "strength_b", now=now)
        service.log_session_result(
            created["id"], status="completed",
            exercises=[{
                "name": "Front Squat", "actual_load": 80, "actual_sets": 3, "actual_reps": "4,4,4",
                "rpe": 8, "technique": "clean", "pain": False, "completed": True, "done": True,
            }],
            now=now,
        )
        with service._session_factory() as session:
            row = session.get(TrainingExerciseProgress, ("strength_b", "Front Squat"))
            self.assertEqual(row.load_value, 80)
        logged = next(item for item in service.session(created["id"])["exercises"] if item["name"] == "Front Squat")
        self.assertEqual(logged["load_value"], 90)

    def test_too_hard_session_reduces_stored_deadlift_prescription(self) -> None:
        from datetime import UTC, datetime
        from app.database.models import TrainingExerciseProgress

        service = self._service()
        now = datetime(2026, 9, 13, 15, tzinfo=UTC)
        service.bootstrap(now)
        created = service.schedule_gym(date(2026, 9, 13), "strength_a", now=now)
        service.log_session_result(
            created["id"], status="completed",
            exercises=[{
                "name": "Trap-bar Deadlift", "actual_load": 125, "actual_sets": 3, "actual_reps": "4,4,3",
                "rpe": 9.5, "technique": "breakdown", "pain": False, "completed": True, "done": True,
            }],
            now=now,
        )
        with service._session_factory() as session:
            row = session.get(TrainingExerciseProgress, ("strength_a", "Trap-bar Deadlift"))
            self.assertLess(row.load_value, 125)
            self.assertEqual(row.sets, 2)
            self.assertEqual(row.last_classification, "too_hard")
            self.assertEqual(row.last_decision, "reduce")

    def test_interval_watts_are_stored_on_the_session(self) -> None:
        from datetime import UTC, datetime

        service = self._service()
        now = datetime(2026, 9, 13, 15, tzinfo=UTC)
        service.bootstrap(now)
        created = service.schedule_gym(date(2026, 9, 13), "strength_a", now=now)
        logged = service.log_session_result(
            created["id"], status="completed",
            exercises=[{"name": "Trap-bar Deadlift", "done": True, "completed": True, "rpe": 8, "actual_load": 125}],
            metrics=[
                {"metric_type": "bike_watts", "sequence": 1, "value": 220, "unit": "W"},
                {"metric_type": "bike_watts", "sequence": 2, "value": 200, "unit": "W"},
            ],
            now=now,
        )
        watts = [item for item in logged["metrics"] if item["metric_type"] == "bike_watts"]
        self.assertEqual([item["value"] for item in watts], [220, 200])

if __name__ == "__main__":
    unittest.main()
