from datetime import date, time
import unittest

from app.domain.training.rebuild import rebuild_schedule
from app.domain.training.types import (
    AthleteState,
    BjjClassAvailability,
    ClassType,
    FatigueLevel,
    GymAvailability,
    MissReason,
    RecordStatus,
    SchedulerInput,
    SleepQuality,
    SorenessLevel,
    TrainingRecord,
    WeatherCondition,
    WorkoutType,
)


def _athlete(**overrides) -> AthleteState:
    values = dict(fatigue=FatigueLevel.NORMAL, soreness=SorenessLevel.LOW, injured=False)
    values.update(overrides)
    return AthleteState(**values)


def _class(day: date, class_type: ClassType = ClassType.NORMAL) -> BjjClassAvailability:
    return BjjClassAvailability(day, time(7, 30), class_type, True)


def test_prioritizes_bjj_after_bjj_was_missed_for_non_fatigue_reasons() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
            TrainingRecord(date(2026, 9, 14), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.OVERSLEPT),
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.WEATHER),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(WeatherCondition(date(2026, 9, 16), precipitation_probability=20, blocks_travel=False),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
        upcoming_hard_bjj=date(2026, 9, 19),
    ))
    assert result["2026-09-16"].session == WorkoutType.BJJ_NORMAL


def test_does_not_force_rest_just_because_weekly_rest_quota_is_incomplete() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
            TrainingRecord(date(2026, 9, 14), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.OVERSLEPT),
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.WEATHER),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    assert result["2026-09-16"].session != WorkoutType.REST


def test_does_not_treat_logistical_missed_sessions_as_training_fatigue() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 14), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.OVERSLEPT),
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.WEATHER),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(),
        athlete_state=_athlete(),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    assert result["2026-09-16"].recovery_penalty == 0


def test_fatigue_miss_does_not_add_penalty_when_athlete_is_normal() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.FATIGUE),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        athlete_state=_athlete(),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    assert result["2026-09-16"].recovery_penalty == 0
    assert result["2026-09-16"].session != WorkoutType.REST


def test_alternates_strength_a_to_strength_b() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
        ),
        gym_availability=(),
        weather=(),
        athlete_state=_athlete(),
    ))
    next_strength = next(
        (
            plan.session for day, plan in result.items()
            if day >= date(2026, 9, 16) and plan.session in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}
        ),
        None,
    )
    assert next_strength == WorkoutType.STRENGTH_B


def test_never_schedules_bjj_when_gym_is_manually_marked_closed() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(),
        gym_availability=(GymAvailability(date(2026, 9, 16), False, reason="Gym holiday"),),
        weather=(WeatherCondition(date(2026, 9, 16), precipitation_probability=0, blocks_travel=False),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    session = result["2026-09-16"].session
    assert session is None or not session.value.startswith("bjj")


def test_bjj_gym_holiday_still_allows_fitness_gym_and_home_work() -> None:
    closed_days = tuple(
        GymAvailability(date(2026, 9, day), False, reason="BJJ gym holiday")
        for day in (21, 22, 23)
    )
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 21),
        history=(
            TrainingRecord(date(2026, 9, 20), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
        ),
        gym_availability=closed_days,
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=tuple(_class(date(2026, 9, day)) for day in (21, 22, 23)),
    ))

    holiday_sessions = {
        result[f"2026-09-{day}"].session
        for day in (21, 22, 23)
        if result[f"2026-09-{day}"].session is not None
    }
    assert not any(session in {WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD, WorkoutType.BJJ_TECHNICAL} for session in holiday_sessions)
    assert holiday_sessions == {
        WorkoutType.STRENGTH_B,
        WorkoutType.ZONE_2,
        WorkoutType.GRIP,
    }


def test_moves_bjj_to_nearest_available_day_when_gym_is_closed() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.WEATHER),
        ),
        gym_availability=(
            GymAvailability(date(2026, 9, 16), False, reason="Gym holiday"),
            GymAvailability(date(2026, 9, 17), True),
        ),
        weather=(),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 17)),),
    ))
    session = result["2026-09-16"].session
    assert session is None or not session.value.startswith("bjj")
    assert result["2026-09-17"].session == WorkoutType.BJJ_NORMAL


def test_blocks_bjj_when_weather_makes_travel_unsafe() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(WeatherCondition(
            date(2026, 9, 16), precipitation_probability=100, precipitation_mm=25, blocks_travel=True,
        ),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    session = result["2026-09-16"].session
    assert session is None or not session.value.startswith("bjj")


def test_missed_bjj_still_takes_next_class_in_rain() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.USER_CANCELLED),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(WeatherCondition(
            date(2026, 9, 16), precipitation_probability=100, precipitation_mm=40, blocks_travel=True,
        ),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
        upcoming_hard_bjj=date(2026, 9, 19),
    ))
    assert result["2026-09-16"].session == WorkoutType.BJJ_NORMAL


def test_storm_still_blocks_catch_up_bjj() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.USER_CANCELLED),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(WeatherCondition(
            date(2026, 9, 16), precipitation_mm=40, weather_code="95", severe_weather=True, blocks_travel=True,
        ),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    session = result["2026-09-16"].session
    assert session is None or not session.value.startswith("bjj")


def test_does_not_cancel_bjj_merely_because_some_rain_is_forecast() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(WeatherCondition(
            date(2026, 9, 16), precipitation_probability=60, precipitation_mm=1, blocks_travel=False,
        ),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    assert result["2026-09-16"].session == WorkoutType.BJJ_NORMAL


def test_uses_rest_when_fatigue_is_actually_high() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_HARD, RecordStatus.COMPLETED),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(),
        athlete_state=_athlete(
            fatigue=FatigueLevel.HIGH, soreness=SorenessLevel.HIGH, sleep_quality=SleepQuality.POOR,
        ),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    assert result["2026-09-16"].session == WorkoutType.REST


def test_does_not_compress_grip_and_zone2_into_remaining_days() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 17),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
            TrainingRecord(date(2026, 9, 14), WorkoutType.GRIP, RecordStatus.MISSED, MissReason.SCHEDULE_CONFLICT),
            TrainingRecord(date(2026, 9, 15), WorkoutType.ZONE_2, RecordStatus.MISSED, MissReason.SCHEDULE_CONFLICT),
        ),
        gym_availability=(),
        weather=(),
        athlete_state=_athlete(),
        upcoming_hard_bjj=date(2026, 9, 19),
        class_availability=(_class(date(2026, 9, 19), ClassType.COMPETITION),),
    ))
    assert len(result["2026-09-18"].sessions or (result["2026-09-18"].session,)) <= 1


def test_protects_saturday_hard_bjj_from_unnecessary_friday_fatigue() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 17),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 19), True),),
        weather=(),
        athlete_state=_athlete(),
        upcoming_hard_bjj=date(2026, 9, 19),
        class_availability=(_class(date(2026, 9, 19), ClassType.COMPETITION),),
    ))
    assert result["2026-09-19"].session == WorkoutType.BJJ_HARD
    assert result["2026-09-18"].session != WorkoutType.STRENGTH_B


def test_weather_fallback_picks_strength_b_instead_of_rest() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(WeatherCondition(date(2026, 9, 16), precipitation_probability=100, precipitation_mm=20, blocks_travel=True),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
    ))
    assert result["2026-09-16"].session == WorkoutType.STRENGTH_B


def test_no_class_does_not_schedule_bjj() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        weather=(),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(),
        class_template=(),
    ))
    session = result["2026-09-16"].session
    assert session is None or not session.value.startswith("bjj")
    assert session != WorkoutType.BJJ_NORMAL


def test_weekday_is_not_inferred_as_bjj_without_template() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
    ))
    session = result["2026-09-16"].session
    assert session is None or not str(session.value).startswith("bjj")


def test_completed_session_cannot_move() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 15), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
        ),
        gym_availability=(),
        weather=(),
        athlete_state=_athlete(),
    ))
    assert result["2026-09-15"].session == WorkoutType.STRENGTH_A
    assert result["2026-09-15"].status == "completed"
    assert not any(
        day != date(2026, 9, 15) and plan.session == WorkoutType.STRENGTH_A
        for day, plan in result.items()
    )


def test_user_unavailability_has_no_workout() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(),
        gym_availability=(GymAvailability(date(2026, 9, 17), True),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 17)),),
        unavailability=(date(2026, 9, 17),),
        horizon_days=3,
    ))
    assert result["2026-09-17"].session is None or result["2026-09-17"].session == WorkoutType.REST
    assert result["2026-09-17"].session not in {
        WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD, WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B,
        WorkoutType.ZONE_2, WorkoutType.GRIP,
    }


def test_injury_excludes_bjj_and_strength_without_makeup_volume() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        athlete_state=_athlete(injured=True, fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)), _class(date(2026, 9, 17))),
        horizon_days=3,
    ))
    future = [plan.session for day, plan in result.items() if day >= date(2026, 9, 16)]
    assert WorkoutType.BJJ_NORMAL not in future
    assert WorkoutType.BJJ_HARD not in future
    assert WorkoutType.STRENGTH_A not in future
    assert WorkoutType.STRENGTH_B not in future
    assert sum(session in {WorkoutType.ZONE_2, WorkoutType.GRIP} for session in future) <= 1


def test_rebuild_is_idempotent() -> None:
    inp = SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
            TrainingRecord(date(2026, 9, 14), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.OVERSLEPT),
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.WEATHER),
        ),
        gym_availability=(
            GymAvailability(date(2026, 9, 16), True),
            GymAvailability(date(2026, 9, 19), True),
        ),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(
            _class(date(2026, 9, 16)),
            _class(date(2026, 9, 19), ClassType.COMPETITION),
        ),
        upcoming_hard_bjj=date(2026, 9, 19),
    )
    first = rebuild_schedule(inp)
    second = rebuild_schedule(inp)
    planned = tuple(
        TrainingRecord(day, plan.session, RecordStatus.PLANNED)
        for day, plan in first.items()
        if day >= inp.today and plan.session is not None
    )
    third = rebuild_schedule(SchedulerInput(
        **{**inp.__dict__, "planned_future": planned},
    ))
    assert first.future_sessions(inp.today) == second.future_sessions(inp.today)
    assert first.future_sessions(inp.today) == third.future_sessions(inp.today)


def test_constraint_change_rebuilds_from_current_truth() -> None:
    inp = SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
            TrainingRecord(date(2026, 9, 14), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.OVERSLEPT),
        ),
        gym_availability=(GymAvailability(date(2026, 9, 16), True),),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(_class(date(2026, 9, 16)),),
    )
    first = rebuild_schedule(inp)
    assert first["2026-09-16"].session == WorkoutType.BJJ_NORMAL
    planned = tuple(
        TrainingRecord(day, plan.session, RecordStatus.PLANNED)
        for day, plan in first.items()
        if day >= inp.today and plan.session is not None
    )
    closed = rebuild_schedule(SchedulerInput(
        today=inp.today,
        history=inp.history,
        gym_availability=(GymAvailability(date(2026, 9, 16), False, reason="Gym holiday"),),
        athlete_state=inp.athlete_state,
        class_availability=inp.class_availability,
        planned_future=planned,
    ))
    session = closed["2026-09-16"].session
    assert session is None or not session.value.startswith("bjj")


def test_wednesday_scenario_prefers_bjj_not_rest() -> None:
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(
            TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),
            TrainingRecord(date(2026, 9, 14), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.OVERSLEPT),
            TrainingRecord(date(2026, 9, 15), WorkoutType.BJJ_NORMAL, RecordStatus.MISSED, MissReason.WEATHER),
        ),
        gym_availability=(
            GymAvailability(date(2026, 9, 16), True),
            GymAvailability(date(2026, 9, 19), True),
        ),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        class_availability=(
            _class(date(2026, 9, 16)),
            _class(date(2026, 9, 19), ClassType.COMPETITION),
        ),
        upcoming_hard_bjj=date(2026, 9, 19),
    ))
    assert result["2026-09-16"].session == WorkoutType.BJJ_NORMAL
    assert result["2026-09-18"].session != WorkoutType.STRENGTH_B
    assert result["2026-09-19"].session == WorkoutType.BJJ_HARD
    assert "0/1" not in result["2026-09-16"].reason
    assert result["2026-09-13"].session == WorkoutType.STRENGTH_A


def test_adaptation_extra_rest_when_no_class_two_days_before_hard() -> None:
    from app.domain.training.classes import MITA_CLASS_TEMPLATE
    from app.domain.training.types import WeekAdaptation
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),),
        class_template=tuple(item for item in MITA_CLASS_TEMPLATE if item.weekday != 3),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        upcoming_hard_bjj=date(2026, 9, 19),
        adaptation=WeekAdaptation(extra_rest_before_hard_bjj=True),
        horizon_days=7,
    ))
    assert result["2026-09-17"].session == WorkoutType.REST
    assert result["2026-09-19"].session == WorkoutType.BJJ_HARD


def test_adaptation_reduces_preceding_strength() -> None:
    from app.domain.training.classes import MITA_CLASS_TEMPLATE
    from app.domain.training.types import WeekAdaptation
    result = rebuild_schedule(SchedulerInput(
        today=date(2026, 9, 16),
        history=(TrainingRecord(date(2026, 9, 13), WorkoutType.STRENGTH_A, RecordStatus.COMPLETED),),
        class_template=tuple(item for item in MITA_CLASS_TEMPLATE if item.weekday != 3),
        athlete_state=_athlete(fatigue=FatigueLevel.LOW),
        upcoming_hard_bjj=date(2026, 9, 19),
        adaptation=WeekAdaptation(reduce_preceding_strength=True),
        horizon_days=7,
    ))
    assert result["2026-09-17"].session not in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}
    assert result["2026-09-18"].session not in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}


def load_tests(loader, tests, pattern):
    suite = unittest.TestSuite()
    for name, value in list(globals().items()):
        if name.startswith("test_") and callable(value):
            suite.addTest(unittest.FunctionTestCase(value))
    return suite


if __name__ == "__main__":
    unittest.main()
