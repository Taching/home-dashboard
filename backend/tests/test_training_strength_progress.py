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
        self.recipe = sp.recipe_for("Dumbbell Bench Press")
        self.state = sp.ExerciseState(
            workout_type="strength_a", exercise_name="Dumbbell Bench Press",
            load_value=30, load_unit="kg/hand", sets=3, rep_target=6,
        )

    def test_progress_climbs_reps_before_load(self) -> None:
        result = sp.apply_decision(self.state, sp.Decision.PROGRESS, self.recipe, rpe=7.5)
        self.assertEqual(result.rep_target, 7)
        self.assertEqual(result.load_value, 30)

    def test_progress_at_rep_max_bumps_load_and_resets_reps(self) -> None:
        at_max = sp.ExerciseState(**{**self.state.__dict__, "rep_target": 8})
        result = sp.apply_decision(at_max, sp.Decision.PROGRESS, self.recipe, rpe=8)
        self.assertEqual(result.rep_target, 6)
        self.assertEqual(result.load_value, 32)

    def test_repeat_at_rep_max_holds_load(self) -> None:
        at_max = sp.ExerciseState(**{**self.state.__dict__, "rep_target": 8})
        result = sp.apply_decision(at_max, sp.Decision.REPEAT, self.recipe)
        self.assertEqual(result.rep_target, 8)
        self.assertEqual(result.load_value, 30)

    def test_load_optional_recipe_stays_at_the_top_of_the_range(self) -> None:
        recipe = sp.recipe_for("Hanging Knee Raise")
        state = sp.ExerciseState(
            workout_type="strength_b", exercise_name="Hanging Knee Raise",
            load_value=None, load_unit=None, sets=3, rep_target=12,
        )
        result = sp.apply_decision(state, sp.Decision.PROGRESS, recipe, rpe=6)
        self.assertIsNone(result.load_value)
        self.assertEqual(result.rep_target, 12)

    def test_cable_without_a_logged_load_waits_at_the_top(self) -> None:
        recipe = sp.recipe_for("Cable Row")
        state = sp.ExerciseState(
            workout_type="strength_a", exercise_name="Cable Row",
            load_value=None, load_unit="kg", sets=3, rep_target=10,
        )
        self.assertEqual(sp.apply_decision(state, sp.Decision.PROGRESS, recipe, rpe=7).rep_target, 10)


class ProgressionStepTests(unittest.TestCase):
    def _deadlift(self, load: float = 125, reps: int = 4) -> sp.ExerciseState:
        return sp.ExerciseState(
            workout_type="strength_a", exercise_name="Trap-bar Deadlift",
            load_value=load, load_unit="kg", sets=3, rep_target=reps,
        )

    def test_big_lift_adds_5_kg_when_easy_and_2_5_when_comfortable(self) -> None:
        recipe = sp.recipe_for("Trap-bar Deadlift")
        self.assertEqual(sp.apply_decision(self._deadlift(), sp.Decision.PROGRESS, recipe, rpe=7).load_value, 130)
        self.assertEqual(sp.apply_decision(self._deadlift(), sp.Decision.PROGRESS, recipe, rpe=8).load_value, 127.5)

    def test_press_and_pull_up_use_small_steps(self) -> None:
        press = sp.ExerciseState(
            workout_type="strength_b", exercise_name="Military Press",
            load_value=52, load_unit="kg", sets=3, rep_target=None,
        )
        recipe = sp.recipe_for("Military Press")
        self.assertEqual(sp.apply_decision(press, sp.Decision.PROGRESS, recipe, rpe=8).load_value, 53)
        self.assertEqual(sp.apply_decision(press, sp.Decision.PROGRESS, recipe, rpe=6.5).load_value, 54.5)

    def test_weight_goes_up_only_with_a_comfortable_logged_rpe(self) -> None:
        ok = sp.Classification.APPROPRIATE
        self.assertEqual(sp.decide(ok, rpe=8), sp.Decision.PROGRESS)
        self.assertEqual(sp.decide(ok, rpe=None), sp.Decision.REPEAT)
        self.assertEqual(sp.decide(sp.Classification.HARD, rpe=8.5), sp.Decision.REPEAT)
        self.assertEqual(sp.decide(sp.Classification.TOO_HARD, rpe=9), sp.Decision.REDUCE)


class DeloadPrescriptionTests(unittest.TestCase):
    def test_deload_halves_sets_and_drops_load_10_to_15_percent(self) -> None:
        recipe = sp.recipe_for("Trap-bar Deadlift")
        state = sp.ExerciseState(
            workout_type="strength_a", exercise_name="Trap-bar Deadlift",
            load_value=125, load_unit="kg", sets=3, rep_target=4,
        )
        result = sp.deload_prescription(state, recipe)
        self.assertEqual(result.sets, 2)
        self.assertEqual(result.load_value, 110)  # 12.5% lighter, nearest 2.5 kg
        self.assertEqual(result.rep_target, 3)
        self.assertEqual(sp.deload_prescription(sp.ExerciseState(**{**state.__dict__, "sets": 2}), recipe).sets, 1)

    def test_deload_rounds_to_real_dumbbell_steps(self) -> None:
        recipe = sp.recipe_for("Dumbbell Bench Press")
        state = sp.ExerciseState(
            workout_type="strength_a", exercise_name="Dumbbell Bench Press",
            load_value=30, load_unit="kg/hand", sets=3, rep_target=8,
        )
        result = sp.deload_prescription(state, recipe)
        self.assertEqual(result.load_value, 26)
        self.assertEqual(result.rep_target, 6)

    def test_bodyweight_deload_keeps_no_load(self) -> None:
        recipe = sp.recipe_for("Hanging Knee Raise")
        state = sp.ExerciseState(
            workout_type="strength_b", exercise_name="Hanging Knee Raise",
            load_value=None, load_unit=None, sets=3, rep_target=10,
        )
        result = sp.deload_prescription(state, recipe)
        self.assertIsNone(result.load_value)
        self.assertEqual(result.sets, 2)


class DeloadCalendarTests(unittest.TestCase):
    def test_every_fourth_week_from_the_program_start(self) -> None:
        self.assertFalse(sp.is_deload_week(date(2026, 10, 20)))
        self.assertTrue(sp.is_deload_week(date(2026, 11, 9)))
        self.assertTrue(sp.is_deload_week(date(2026, 11, 14)))
        self.assertFalse(sp.is_deload_week(date(2026, 11, 16)))
        self.assertTrue(sp.is_deload_week(date(2026, 12, 7)))
        self.assertEqual(sp.next_deload_week(date(2026, 10, 20)), date(2026, 11, 9))

    def test_sunday_belongs_to_the_next_training_week(self) -> None:
        self.assertTrue(sp.is_deload_week(date(2026, 11, 8)))
        self.assertFalse(sp.is_deload_week(date(2026, 11, 15)))
        self.assertEqual(sp.block_week(date(2026, 10, 18)), 1)
        self.assertEqual(sp.block_week(date(2026, 11, 7)), 3)

    def test_nothing_before_the_program(self) -> None:
        self.assertFalse(sp.is_deload_week(date(2026, 10, 12)))
        self.assertIsNone(sp.block_week(date(2026, 10, 17)))


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
        now = datetime(2026, 10, 21, 15, tzinfo=UTC)
        service.bootstrap(now)
        created = service.schedule_gym(date(2026, 10, 22), "strength_a", now=now)
        deadlift = next(item for item in created["exercises"] if item["name"] == "Trap-bar Deadlift")
        self.assertEqual(deadlift["load_value"], 125)
        self.assertEqual(deadlift["reps"], "3")
        service.log_session_result(
            created["id"], status="completed",
            exercises=[{
                "name": "Trap-bar Deadlift", "actual_load": 125, "actual_sets": 3, "actual_reps": "3,3,3",
                "rpe": 6, "technique": "clean", "pain": False, "completed": True, "done": True,
            }],
            now=now,
        )
        with service._session_factory() as session:
            row = session.get(TrainingExerciseProgress, ("strength_a", "Trap-bar Deadlift"))
            self.assertEqual(row.load_value, 125)
            self.assertEqual(row.rep_target, 4)
            self.assertEqual(row.last_classification, "easy")
            self.assertEqual(row.last_decision, "progress")
        # And the per-exercise builder used by manual placement picks it up.
        with service._session_factory() as session:
            exercises = service._strength_exercises_now(session, WorkoutType.STRENGTH_A, date(2026, 10, 24))
        next_deadlift = next(item for item in exercises if item.name == "Trap-bar Deadlift")
        self.assertEqual(next_deadlift.reps, "4")
        # In the deload week the same lift is lighter with fewer sets.
        with service._session_factory() as session:
            deload = service._strength_exercises_now(session, WorkoutType.STRENGTH_A, date(2026, 11, 10))
        deload_deadlift = next(item for item in deload if item.name == "Trap-bar Deadlift")
        self.assertEqual((deload_deadlift.load_value, deload_deadlift.sets), (110, 2))

    def test_progress_from_the_old_program_is_ignored(self) -> None:
        from datetime import UTC, datetime
        from app.database.models import TrainingExerciseProgress

        service = self._service()
        with service._session_factory() as session:
            session.add(TrainingExerciseProgress(
                workout_type="strength_a", exercise_name="Bulgarian Split Squat",
                load_value=14, load_unit="kg/hand", sets=2, rep_target=7,
                updated_at=datetime(2026, 9, 24, tzinfo=UTC),
            ))
            session.commit()
            exercises = service._strength_exercises_now(session, WorkoutType.STRENGTH_A, date(2026, 10, 24))
        split = next(item for item in exercises if item.name == "Bulgarian Split Squat")
        self.assertEqual((split.sets, split.reps), (3, "6/leg"))

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
