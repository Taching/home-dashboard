from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time

from app.domain.training.types import (
    INJURY_EXCLUDED_DEFAULT,
    AthleteState,
    BjjClassAvailability,
    ClassTemplate,
    ClassType,
    FatigueLevel,
    GymAvailability,
    RecordStatus,
    SchedulerInput,
    SleepQuality,
    SorenessLevel,
    WeatherCondition,
    WorkoutType,
)

BJJ_TYPES = frozenset({
    WorkoutType.BJJ_TECHNICAL,
    WorkoutType.BJJ_NORMAL,
    WorkoutType.BJJ_HARD,
})
STRENGTH_TYPES = frozenset({WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B})
STORM_CODES = frozenset({"95", "96", "99"})
PRECIP_BLOCK_MM = 10.0
WIND_BLOCK_KPH = 50.0


@dataclass(frozen=True)
class DayAvailability:
    day: date
    user_available: bool
    gym_open: bool
    bjj_class: BjjClassAvailability | ClassTemplate | None
    travel_blocked: bool
    excluded: frozenset[WorkoutType]
    blocked: tuple[str, ...]

    def allows(self, session: WorkoutType) -> bool:
        if not self.user_available:
            return False
        if session in self.excluded:
            return False
        if session in BJJ_TYPES:
            if not self.gym_open:
                return False
            if self.bjj_class is None:
                return False
            if self.travel_blocked:
                return False
            if session == WorkoutType.BJJ_HARD:
                return _class_is_hard(self.bjj_class)
            return True
        return True


def travel_blocked(weather: WeatherCondition | None) -> bool:
    if weather is None:
        return False
    if weather.blocks_travel is not None:
        return weather.blocks_travel
    if weather.severe_weather:
        return True
    if weather.weather_code in STORM_CODES:
        return True
    if weather.precipitation_mm is not None and weather.precipitation_mm >= PRECIP_BLOCK_MM:
        return True
    if weather.wind_kph is not None and weather.wind_kph >= WIND_BLOCK_KPH:
        return True
    return False


def recovery_penalty(state: AthleteState, *, completed_hard_yesterday: bool = False) -> float:
    penalty = 0.0
    if state.fatigue == FatigueLevel.HIGH:
        penalty += 1
    if state.soreness == SorenessLevel.HIGH:
        penalty += 1
    if state.sleep_quality == SleepQuality.POOR:
        penalty += 1
    if state.injured:
        penalty += 1
    if completed_hard_yesterday and penalty > 0:
        penalty += 0.5
    return penalty


def needs_rest(state: AthleteState) -> bool:
    if state.injured:
        return True
    if state.fatigue == FatigueLevel.HIGH:
        return True
    if state.soreness == SorenessLevel.HIGH and state.sleep_quality == SleepQuality.POOR:
        return True
    return False


def excluded_types(state: AthleteState) -> frozenset[WorkoutType]:
    if state.exclude_types:
        return state.exclude_types
    if state.injured:
        return INJURY_EXCLUDED_DEFAULT
    return frozenset()


def gym_open(day: date, rows: tuple[GymAvailability, ...]) -> tuple[bool, str | None]:
    match = next((item for item in rows if item.date == day), None)
    if match is None:
        return True, None
    return match.is_open, match.reason


def class_for_day(day: date, inp: SchedulerInput) -> BjjClassAvailability | ClassTemplate | None:
    explicit = [item for item in inp.class_availability if item.date == day]
    if explicit:
        available = next((item for item in explicit if item.available), None)
        return available
    closed, reason = gym_open(day, inp.gym_availability)
    if not closed:
        return None
    if reason and "no class" in reason.lower():
        return None
    return next((item for item in inp.class_template if item.weekday == day.weekday()), None)


def availability_for(day: date, inp: SchedulerInput) -> DayAvailability:
    user_available = day not in inp.unavailability
    open_, gym_reason = gym_open(day, inp.gym_availability)
    weather = next((item for item in inp.weather if item.date == day), None)
    blocked_travel = travel_blocked(weather)
    bjj_class = class_for_day(day, inp) if open_ else None
    excluded = excluded_types(inp.athlete_state)
    catch_up_bjj = any(
        item.status == RecordStatus.MISSED and item.session in BJJ_TYPES
        for item in inp.history
    )
    pinned = {item[0]: item[1] for item in inp.pinned_bjj}
    if day in pinned and open_ and user_available and not _severe_travel(weather):
        class_type = ClassType.COMPETITION if pinned[day] == WorkoutType.BJJ_HARD else ClassType.NORMAL
        bjj_class = BjjClassAvailability(day, time(7, 30), class_type, True)
        blocked_travel = False
    elif catch_up_bjj and bjj_class is not None and not _severe_travel(weather):
        blocked_travel = False
    blocked: list[str] = []
    if not user_available:
        blocked.append("user unavailable")
    if not open_:
        blocked.append(gym_reason or "gym closed")
    if bjj_class is None:
        blocked.append("no BJJ class")
    if blocked_travel:
        blocked.append("travel blocked")
    if inp.athlete_state.injured:
        blocked.append("injury")
    return DayAvailability(
        day, user_available, open_, bjj_class, blocked_travel, excluded, tuple(blocked),
    )


def _severe_travel(weather: WeatherCondition | None) -> bool:
    if weather is None:
        return False
    if weather.severe_weather:
        return True
    if str(weather.weather_code or "") in STORM_CODES:
        return True
    if weather.wind_kph is not None and weather.wind_kph >= WIND_BLOCK_KPH:
        return True
    return False


def _class_is_hard(item: BjjClassAvailability | ClassTemplate) -> bool:
    return item.class_type in {ClassType.COMPETITION}
