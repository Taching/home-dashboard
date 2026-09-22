from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.training.policy import (
    BJJ_TYPES,
    COMPLETED_STATUSES,
)
from app.domain.training.rebuild import rebuild_schedule
from app.domain.training.strength_progress import ExerciseState
from app.domain.training.templates import (
    WORKOUT_TEMPLATES,
    apply_adaptation,
    build_strength_exercises,
    reduced_template,
)
from app.domain.training.types import (
    AthleteState,
    ExistingSession,
    ExercisePrescription,
    FatigueLevel,
    FatigueState,
    FixedBjjEvent,
    GymAvailability,
    PlannedSession,
    ReadinessAssessment,
    ReadinessInput,
    ReadinessLevel,
    RecordStatus,
    SchedulerInput,
    SessionStatus,
    SleepQuality,
    SorenessLevel,
    TrainingPhase,
    TrainingRecord,
    WeatherCondition,
    WeatherHint,
    WeekAdaptation,
    WeekPlan,
    WeekQuality,
    WorkoutTemplate,
    WorkoutType,
)

OCTOBER_COMPETITION_START = date(2026, 10, 10)
OCTOBER_COMPETITION_END = date(2026, 10, 11)
NOVEMBER_COMPETITION_START = date(2026, 11, 7)
NOVEMBER_COMPETITION_END = date(2026, 11, 8)


def phase_for_date(day: date) -> TrainingPhase:
    if day <= date(2026, 10, 4):
        return TrainingPhase.BUILD_1
    if day < OCTOBER_COMPETITION_START:
        return TrainingPhase.TAPER_1
    if day <= OCTOBER_COMPETITION_END:
        return TrainingPhase.COMPETITION_1
    if day <= date(2026, 10, 14):
        return TrainingPhase.RECOVERY_1
    if day <= date(2026, 11, 1):
        return TrainingPhase.BUILD_2
    if day <= date(2026, 11, 6):
        return TrainingPhase.TAPER_2
    if day <= NOVEMBER_COMPETITION_END:
        return TrainingPhase.COMPETITION_2
    return TrainingPhase.POST_COMPETITION


def assess_readiness(value: ReadinessInput | None) -> ReadinessAssessment:
    if value is None:
        return ReadinessAssessment(ReadinessLevel.UNKNOWN, ())
    if value.pain is True:
        return ReadinessAssessment(ReadinessLevel.MANUAL_REVIEW, ("pain or injury reported",), True)
    alerts: list[str] = []
    if (value.sleep_hours is not None and value.sleep_hours < 6.5) or (
        value.sleep_quality is not None and value.sleep_quality <= 2
    ):
        alerts.append("poor sleep")
    if value.fatigue is not None and value.fatigue >= 4:
        alerts.append("high fatigue")
    if value.soreness is not None and value.soreness >= 4:
        alerts.append("high soreness")
    if value.readiness is not None and value.readiness <= 2:
        alerts.append("low readiness")
    if value.prior_hard_bjj and any(item in alerts for item in ("high fatigue", "high soreness")):
        alerts.append("high-load BJJ yesterday")
    level = ReadinessLevel.RED if len(alerts) >= 3 else (
        ReadinessLevel.YELLOW if len(alerts) >= 2 else ReadinessLevel.GREEN
    )
    return ReadinessAssessment(
        level,
        tuple(alerts),
        suppress_grip=value.grip_fatigue is not None and value.grip_fatigue >= 4,
    )


def bjj_round_target(day: date) -> tuple[int, int]:
    if day <= date(2026, 9, 20):
        return 3, 120
    if day <= date(2026, 9, 27):
        return 4, 120
    if day <= date(2026, 10, 4):
        return 5, 90
    if day <= date(2026, 10, 10):
        return 3, 120
    if day <= date(2026, 10, 18):
        return 3, 120
    if day <= date(2026, 10, 25):
        return 4, 120
    if day <= date(2026, 11, 1):
        return 5, 90
    return 3, 120


TRAVEL_MARKERS = ("flight", "travel", "airport", "shinkansen", "train to")
DINNER_MARKERS = ("dinner", "izakaya")
ACTIVE_STATUSES = {
    SessionStatus.PLANNED, SessionStatus.IN_PROGRESS, SessionStatus.COMPLETED,
    SessionStatus.PARTIAL, SessionStatus.RECOVERY, SessionStatus.COMPETITION,
}


class TrainingScheduler:
    """Pure, deterministic weekly planner. Persistence and prose generation live elsewhere."""

    def __init__(self, timezone_name: str = "Asia/Tokyo") -> None:
        self.timezone = ZoneInfo(timezone_name)

    def plan_week(
        self,
        week_start: date,
        *,
        now: datetime,
        busy: tuple[tuple[datetime, datetime], ...] = (),
        labeled_busy: tuple[tuple[datetime, datetime, str], ...] = (),
        fixed_bjj: tuple[FixedBjjEvent, ...] = (),
        existing: tuple[ExistingSession, ...] = (),
        fatigue: FatigueState = FatigueState.NORMAL,
        weather: tuple[WeatherHint, ...] = (),
        declined_bjj: tuple[date, ...] = (),
        readiness: ReadinessAssessment | None = None,
        class_template: tuple = (),
        class_availability: tuple = (),
        gym_availability: tuple[GymAvailability, ...] = (),
        unavailability: tuple[date, ...] = (),
        weather_conditions: tuple[WeatherCondition, ...] = (),
        adaptation: WeekAdaptation | None = None,
        upcoming_hard_bjj: date | None = None,
        tournament_date: date | None = None,
        strength_progress: dict[str, dict[str, ExerciseState]] | None = None,
        strength_deload: dict[str, bool] | None = None,
        use_llm: bool = False,
    ) -> WeekPlan:
        if labeled_busy and not busy:
            busy = tuple((start, end) for start, end, _ in labeled_busy)
        current = now.astimezone(self.timezone)
        today = current.date()
        history: list[TrainingRecord] = []
        for item in existing:
            day = item.start_at.astimezone(self.timezone).date()
            session_type = item.type if item.type not in {WorkoutType.GRIP} or item.suppresses_type is None else (item.suppresses_type or item.type)
            if item.status in COMPLETED_STATUSES:
                history.append(TrainingRecord(day, item.type, RecordStatus.COMPLETED))
            elif item.status == SessionStatus.SKIPPED or (
                item.status == SessionStatus.PLANNED and item.type in BJJ_TYPES and item.end_at <= current
            ):
                history.append(TrainingRecord(day, session_type, RecordStatus.MISSED))
        pinned = tuple(
            (
                event.start_at.astimezone(self.timezone).date(),
                WorkoutType.BJJ_HARD if event.start_at.astimezone(self.timezone).date().weekday() == 5 else WorkoutType.BJJ_NORMAL,
            )
            for event in fixed_bjj
            if event.end_at > current
        )
        locked = tuple(
            (item.start_at.astimezone(self.timezone).date(), item.type)
            for item in existing
            if item.status in {SessionStatus.PLANNED, SessionStatus.IN_PROGRESS, SessionStatus.RECOVERY, SessionStatus.COMPETITION}
            and (item.pinned or item.source in {"calendar", "manual"})
            and item.start_at.astimezone(self.timezone).date() >= today
        )
        if upcoming_hard_bjj is None:
            upcoming_hard_bjj = next((day for day, kind in pinned if kind == WorkoutType.BJJ_HARD and day >= today), None)
        athlete = _athlete_from_fatigue(fatigue, readiness)
        conditions = weather_conditions or tuple(
            WeatherCondition(item.day, blocks_travel=False)
            for item in weather
        )
        result = rebuild_schedule(SchedulerInput(
            today=today,
            history=tuple(history),
            gym_availability=gym_availability,
            weather=conditions,
            athlete_state=athlete,
            class_availability=class_availability,
            class_template=class_template,
            unavailability=tuple(set(unavailability) | set(declined_bjj)),
            upcoming_hard_bjj=upcoming_hard_bjj,
            tournament_date=tournament_date,
            adaptation=adaptation,
            pinned_bjj=pinned,
            locked_sessions=locked,
            horizon_days=max(7, (week_start + timedelta(days=13) - today).days + 1),
            as_of=current,
        ), use_llm=use_llm)
        planned: list[PlannedSession] = []
        by_event = {event.start_at.astimezone(self.timezone).date(): event for event in fixed_bjj if event.end_at > current}
        for day, plan in sorted(result.items()):
            if day < today or plan.status != "planned" or plan.session is None:
                continue
            if week_start <= day < week_start + timedelta(days=7) and phase_for_date(day) in {
                TrainingPhase.COMPETITION_1, TrainingPhase.COMPETITION_2,
            }:
                planned.append(self._all_day(day, WorkoutType.COMPETITION, phase_for_date(day), plan.reason))
                continue
            event = by_event.get(day) if plan.session in BJJ_TYPES else None
            if event is not None:
                if event.end_at <= current:
                    continue
                planned.append(self._bjj_session(
                    day, plan.session, event.start_at, event.end_at, event.external_id, "calendar",
                    reason=plan.reason, adaptation=adaptation,
                ))
                continue
            start, end = self._slot_for(day, plan.session, busy)
            if start is None:
                start = datetime.combine(day, time(7, 30), self.timezone)
                end = start + timedelta(minutes=60)
            all_day = plan.session in {WorkoutType.REST, WorkoutType.COMPETITION} and fatigue not in {
                FatigueState.PAIN, FatigueState.VERY_FATIGUED,
            }
            if not all_day and end <= current:
                continue
            if plan.session in BJJ_TYPES:
                planned.append(self._bjj_session(
                    day, plan.session, start, end, None, "scheduler",
                    reason=plan.reason, adaptation=adaptation,
                ))
            elif plan.session == WorkoutType.RECOVERY or (
                plan.session == WorkoutType.REST and fatigue in {FatigueState.PAIN, FatigueState.VERY_FATIGUED}
            ):
                recovery = self._recovery_session(day, start, fatigue)
                planned.append(PlannedSession(**{**recovery.__dict__, "reason": plan.reason}))
            elif plan.session in {WorkoutType.REST, WorkoutType.COMPETITION}:
                planned.append(self._all_day(day, plan.session, phase_for_date(day), plan.reason))
            elif plan.session in WORKOUT_TEMPLATES:
                hint = next((item for item in weather if item.day == day), None)
                session = self._template_session(
                    plan.session, day, start, end,
                    fatigue if day == today + timedelta(days=1) else FatigueState.NORMAL,
                    weather=hint, adaptation=adaptation, reason=plan.reason,
                    strength_progress=strength_progress, strength_deload=strength_deload,
                )
                planned.append(session)
        return WeekPlan(week_start, tuple(sorted(planned, key=lambda item: item.start_at)), ())

    def week_quality(self, plan: WeekPlan) -> WeekQuality:
        from app.domain.training.policy import assess_week_quality
        sessions = plan.sessions
        return assess_week_quality(
            bjj=sum(item.type in BJJ_TYPES for item in sessions),
            hard_bjj=any(item.type == WorkoutType.BJJ_HARD for item in sessions),
            strength=sum(item.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B} for item in sessions),
            zone_2=sum(item.type == WorkoutType.ZONE_2 for item in sessions),
            intervals=sum(item.type == WorkoutType.STRENGTH_A for item in sessions),
            rest=any(item.type in {WorkoutType.REST, WorkoutType.RECOVERY} for item in sessions),
        )

    def _slot_for(self, day: date, workout_type: WorkoutType, busy: tuple[tuple[datetime, datetime], ...]):
        duration = {WorkoutType.STRENGTH_A: 60, WorkoutType.STRENGTH_B: 55, WorkoutType.ZONE_2: 45, WorkoutType.GRIP: 15}.get(workout_type, 90)
        clock = time(10, 0) if day.weekday() == 5 and workout_type in BJJ_TYPES else time(7, 30)
        exact = self._exact_slot(day, clock, duration, busy)
        if exact is not None:
            return exact
        return self._flexible_slot(day, duration, busy) or (None, None)

    def _bjj_type(self, day: date) -> WorkoutType:
        phase = phase_for_date(day)
        if phase in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2}:
            return WorkoutType.BJJ_NORMAL if day.weekday() <= 1 else WorkoutType.BJJ_TECHNICAL
        return WorkoutType.BJJ_HARD if day.weekday() == 5 else WorkoutType.BJJ_NORMAL

    def _bjj_session(
        self, day: date, workout_type: WorkoutType, start: datetime, end: datetime,
        external_id: str | None, source: str,
        reason: str | None = None, adaptation: WeekAdaptation | None = None,
    ) -> PlannedSession:
        rounds, rest = bjj_round_target(day)
        if adaptation is not None:
            rounds = max(2, rounds + adaptation.bjj_rounds_delta)
        focuses = (
            ("Guard retention: establish frames before strength against the knee cut.",)
            if day.weekday() in {0, 1}
            else (("Spider → De La Riva transition.",) if day.weekday() in {3, 4}
                  else ("DLR → X guard → sweep.", "Establish top pressure efficiently."))
        )
        if workout_type == WorkoutType.BJJ_TECHNICAL:
            rounds = min(rounds, 2)
        text = reason or (
            "Known BJJ calendar event takes priority." if source == "calendar" else (
                "Saturday is the competition-specific session." if workout_type == WorkoutType.BJJ_HARD
                else "Confirmed BJJ session; gym work was placed around it."
            )
        )
        return PlannedSession(
            workout_type, start.astimezone(self.timezone), end.astimezone(self.timezone),
            phase_for_date(day), text,
            "hard" if workout_type == WorkoutType.BJJ_HARD else ("easy" if workout_type == WorkoutType.BJJ_TECHNICAL else "normal"),
            coach_focus=focuses[:2], preparation="Leave home 30 minutes before weekday class." if day.weekday() < 5 else None,
            target_rounds=rounds, round_length_seconds=300, rest_seconds=rest,
            source=source, pinned=source == "calendar", source_calendar_event_id=external_id,
        )

    def _template_session(
        self, workout_type: WorkoutType, day: date, start: datetime, end: datetime,
        fatigue: FatigueState,
        weather: WeatherHint | None = None,
        adaptation: WeekAdaptation | None = None,
        reason: str | None = None,
        strength_progress: dict[str, dict[str, ExerciseState]] | None = None,
        strength_deload: dict[str, bool] | None = None,
    ) -> PlannedSession:
        phase = phase_for_date(day)
        taper = phase in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2}
        is_strength = workout_type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}
        is_deload = False
        if is_strength and not taper:
            is_deload = bool((strength_deload or {}).get(workout_type.value))
            progress_map = (strength_progress or {}).get(workout_type.value, {})
            exercises = build_strength_exercises(workout_type, progress_map, deload=is_deload)
            template = WorkoutTemplate(
                workout_type, WORKOUT_TEMPLATES[workout_type].title,
                WORKOUT_TEMPLATES[workout_type].estimated_minutes, WORKOUT_TEMPLATES[workout_type].intensity,
                exercises, WORKOUT_TEMPLATES[workout_type].conditioning,
            )
        else:
            template = reduced_template(workout_type) if taper and is_strength else WORKOUT_TEMPLATES[workout_type]
            template = apply_adaptation(template, adaptation)
        text = reason or "Placed around BJJ with enough recovery before the hardest mat session."
        if fatigue in {FatigueState.PAIN, FatigueState.VERY_FATIGUED}:
            return self._recovery_session(day, start, fatigue)
        exercises = template.exercises
        intensity = template.intensity
        if fatigue == FatigueState.TIRED:
            text = "Volume reduced because Toshi is tired; important BJJ stays."
            intensity = "easy"
            exercises = self._tired_exercises(exercises)
        if workout_type == WorkoutType.ZONE_2 and weather and weather.outdoor_impractical:
            indoor = "Indoor equivalent: stationary bike, treadmill, or incline walking."
            if weather.condition:
                indoor = f"{weather.condition}: {indoor}"
            exercises = tuple(
                ExercisePrescription(
                    item.name, item.load_value, item.load_unit, item.sets, item.reps,
                    item.duration_seconds, indoor,
                )
                for item in exercises
            )
            text = "Zone 2 stays; weather only changes the indoor modality."
        if is_deload:
            text = f"{text} Deload week: lighter load, one fewer set per lift."
        return PlannedSession(
            workout_type, start, end, phase, text, intensity, exercises=exercises,
            preparation="Hydrate and prepare training equipment the night before.",
            deload=is_deload,
        )

    @staticmethod
    def _tired_exercises(exercises: tuple[ExercisePrescription, ...]) -> tuple[ExercisePrescription, ...]:
        shortened: list[ExercisePrescription] = []
        for item in exercises:
            if item.name == "Stationary bike intervals":
                continue
            duration = item.duration_seconds
            if duration and item.name.startswith("Zone 2"):
                duration = max(20 * 60, round(duration * 0.75))
            shortened.append(ExercisePrescription(
                item.name, item.load_value, item.load_unit,
                max(1, (item.sets or 1) - 1) if item.sets and item.sets > 1 else item.sets,
                item.reps, duration, "Tired: keep the important work, drop extra volume.",
            ))
        return tuple(shortened)

    def _recovery_session(self, day: date, start: datetime, fatigue: FatigueState) -> PlannedSession:
        if fatigue == FatigueState.PAIN:
            reason = "Pain overrides weekly targets; hard training needs a manual decision."
        else:
            reason = "Very fatigued: rest or easy movement instead of chasing the schedule."
        end = start + timedelta(minutes=30)
        return PlannedSession(
            WorkoutType.RECOVERY, start, end, phase_for_date(day), reason, "easy",
            exercises=(ExercisePrescription("Easy mobility or walk", duration_seconds=20 * 60, notes="Stop if symptoms worsen"),),
        )

    def _adapt_tomorrow(self, item: PlannedSession, fatigue: FatigueState) -> PlannedSession:
        if fatigue == FatigueState.NORMAL:
            return item
        if fatigue == FatigueState.PAIN:
            return self._recovery_session(item.local_date, item.start_at, fatigue)
        if fatigue == FatigueState.VERY_FATIGUED:
            if item.type in {WorkoutType.REST, WorkoutType.RECOVERY}:
                return item
            return self._recovery_session(item.local_date, item.start_at, fatigue)
        if fatigue == FatigueState.TIRED and item.type == WorkoutType.BJJ_HARD:
            return PlannedSession(**{
                **item.__dict__,
                "type": WorkoutType.BJJ_NORMAL,
                "intensity": "normal",
                "target_rounds": min(item.target_rounds or 3, 3),
                "reason": "Hard BJJ reduced because Toshi is tired; the class still happens.",
            })
        if fatigue == FatigueState.TIRED and item.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B, WorkoutType.ZONE_2}:
            return self._template_session(item.type, item.local_date, item.start_at, item.end_at, fatigue)
        return item

    def _attach_grip(
        self,
        planned: list[PlannedSession],
        bjj_days: set[date],
        fatigue: FatigueState,
        *,
        four_bjj: bool,
        taper: bool,
        already_decided: int = 0,
        hunting_bjj: bool = False,
    ) -> None:
        if fatigue in {FatigueState.VERY_FATIGUED, FatigueState.PAIN} or hunting_bjj:
            return
        grip = WORKOUT_TEMPLATES[WorkoutType.GRIP].exercises[0]
        target = 1 if four_bjj or taper or fatigue == FatigueState.TIRED else 2
        limit = max(0, target - already_decided)
        eligible: list[int] = []
        for index, item in enumerate(planned):
            if item.type not in {WorkoutType.ZONE_2, WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}:
                continue
            day = item.local_date
            if any(0 <= (bjj_day - day).days <= 1 for bjj_day in bjj_days):
                continue
            eligible.append(index)
        for index in eligible[:limit]:
            item = planned[index]
            planned[index] = PlannedSession(**{**item.__dict__, "exercises": item.exercises + (grip,)})

    @staticmethod
    def _would_triple_hard(day: date, hard_days: set[date]) -> bool:
        proposed = hard_days | {day}
        for start in (-2, -1, 0):
            window = {day + timedelta(days=start + offset) for offset in range(3)}
            if window <= proposed:
                return True
        return False

    def _choose_day(
        self, week_start: date, today: date, occupied_days: set[date],
        busy: tuple[tuple[datetime, datetime], ...], duration: int, reject,
    ) -> tuple[date, datetime, datetime] | None:
        for offset in range(7):
            day = week_start + timedelta(days=offset)
            if day <= today or day in occupied_days or reject(day):
                continue
            slot = self._flexible_slot(day, duration, busy)
            if slot is not None:
                return day, *slot
        return None

    def _exact_slot(
        self, day: date, start_clock: time, duration: int,
        busy: tuple[tuple[datetime, datetime], ...],
    ) -> tuple[datetime, datetime] | None:
        start = datetime.combine(day, start_clock, self.timezone)
        end = start + timedelta(minutes=duration)
        return None if self._overlaps(start, end, busy) else (start, end)

    def _travel_day(self, day: date, labeled_busy: tuple[tuple[datetime, datetime, str], ...]) -> bool:
        day_start = datetime.combine(day, time.min, self.timezone)
        day_end = day_start + timedelta(days=1)
        titles = []
        for start, end, title in labeled_busy:
            clipped_start = max(start.astimezone(self.timezone), day_start)
            clipped_end = min(end.astimezone(self.timezone), day_end)
            if clipped_end > clipped_start:
                titles.append(title.lower())
        blob = " ".join(titles)
        return any(marker in blob for marker in TRAVEL_MARKERS)

    def _work_load(self, day: date, labeled_busy: tuple[tuple[datetime, datetime, str], ...]) -> str:
        day_start = datetime.combine(day, time.min, self.timezone)
        day_end = day_start + timedelta(days=1)
        hours = 0.0
        last_end: datetime | None = None
        titles: list[str] = []
        for start, end, title in labeled_busy:
            clipped_start = max(start.astimezone(self.timezone), day_start)
            clipped_end = min(end.astimezone(self.timezone), day_end)
            if clipped_end <= clipped_start:
                continue
            hours += (clipped_end - clipped_start).total_seconds() / 3600
            last_end = clipped_end if last_end is None or clipped_end > last_end else last_end
            titles.append(title.lower())
        blob = " ".join(titles)
        if any(marker in blob for marker in TRAVEL_MARKERS + DINNER_MARKERS):
            return "heavy"
        if hours >= 6 or (last_end is not None and last_end.time() >= time(18, 0) and hours >= 2):
            return "heavy"
        if hours >= 3 or (last_end is not None and last_end.time() >= time(17, 0)):
            return "moderate"
        return "light"

    def _flexible_slot(
        self, day: date, duration: int, busy: tuple[tuple[datetime, datetime], ...],
    ) -> tuple[datetime, datetime] | None:
        preferred = datetime.combine(day, time(7, 30), self.timezone)
        offsets = [0]
        for value in range(30, 450, 30):
            offsets.extend((-value, value))
        for offset in offsets:
            start = preferred + timedelta(minutes=offset)
            if start.time() < time(6) or start.time() > time(14):
                continue
            end = start + timedelta(minutes=duration)
            if not self._overlaps(start, end, busy):
                return start, end
        return None

    @staticmethod
    def _overlaps(start: datetime, end: datetime, busy: tuple[tuple[datetime, datetime], ...]) -> bool:
        return any(start < busy_end and end > busy_start for busy_start, busy_end in busy)

    @staticmethod
    def _strength_too_late_for_taper(day: date) -> bool:
        phase = phase_for_date(day)
        return phase in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2} and day.weekday() > 1

    def _all_day(self, day: date, workout_type: WorkoutType, phase: TrainingPhase, reason: str) -> PlannedSession:
        start = datetime.combine(day, time.min, self.timezone)
        return PlannedSession(workout_type, start, start + timedelta(days=1), phase, reason, "easy", is_all_day=True)

    def _is_live(self, item: ExistingSession, now: datetime) -> bool:
        if item.status in COMPLETED_STATUSES:
            return True
        if item.status in {SessionStatus.RECOVERY, SessionStatus.COMPETITION}:
            return True
        if item.status != SessionStatus.PLANNED:
            return False
        if item.type in {WorkoutType.REST, WorkoutType.RECOVERY, WorkoutType.COMPETITION}:
            return item.start_at.astimezone(self.timezone).date() >= now.astimezone(self.timezone).date()
        return item.end_at > now


def _athlete_from_fatigue(fatigue: FatigueState, readiness: ReadinessAssessment | None) -> AthleteState:
    injured = fatigue == FatigueState.PAIN or (readiness is not None and readiness.level == ReadinessLevel.MANUAL_REVIEW)
    if fatigue in {FatigueState.VERY_FATIGUED, FatigueState.PAIN}:
        level = FatigueLevel.HIGH
    elif fatigue == FatigueState.TIRED:
        level = FatigueLevel.NORMAL
    else:
        level = FatigueLevel.LOW if fatigue == FatigueState.NORMAL else FatigueLevel.NORMAL
    sleep = SleepQuality.POOR if readiness is not None and "poor sleep" in readiness.alerts else None
    soreness = SorenessLevel.HIGH if readiness is not None and "high soreness" in readiness.alerts else SorenessLevel.NORMAL
    if fatigue == FatigueState.VERY_FATIGUED:
        level = FatigueLevel.HIGH
    return AthleteState(fatigue=level, soreness=soreness, injured=injured, sleep_quality=sleep)
