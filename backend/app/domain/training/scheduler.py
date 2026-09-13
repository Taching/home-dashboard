from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.training.policy import (
    BJJ_TYPES,
    HARD_TYPES,
    PREFERRED_BJJ_GROUPS,
    assess_week_quality,
    weekly_targets,
)
from app.domain.training.templates import WORKOUT_TEMPLATES, reduced_template
from app.domain.training.types import (
    BjjCandidate,
    ExistingSession,
    ExercisePrescription,
    FatigueState,
    FixedBjjEvent,
    PlannedSession,
    ReadinessAssessment,
    ReadinessInput,
    ReadinessLevel,
    SessionStatus,
    TrainingPhase,
    WeatherHint,
    WeekPlan,
    WeekQuality,
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
    ) -> WeekPlan:
        del readiness
        if labeled_busy and not busy:
            busy = tuple((start, end) for start, end, _ in labeled_busy)
        week_end = week_start + timedelta(days=7)
        current = now.astimezone(self.timezone)
        tomorrow = current.date() + timedelta(days=1)
        future_days_remaining = sum(
            week_start + timedelta(days=offset) > current.date()
            for offset in range(7)
        )
        late_partial_week = week_start <= current.date() < week_end and future_days_remaining <= 2
        taper_week = any(
            phase_for_date(week_start + timedelta(days=offset)) in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2}
            for offset in range(7)
        )
        declined = set(declined_bjj)
        occupied_days = {
            item.start_at.astimezone(self.timezone).date()
            for item in existing
            if item.status in ACTIVE_STATUSES and item.type in {
                *BJJ_TYPES, WorkoutType.COMPETITION, WorkoutType.RECOVERY, WorkoutType.REST,
            }
        }
        planned: list[PlannedSession] = []

        for day_offset in range(7):
            day = week_start + timedelta(days=day_offset)
            phase = phase_for_date(day)
            if phase in {TrainingPhase.COMPETITION_1, TrainingPhase.COMPETITION_2}:
                planned.append(self._all_day(day, WorkoutType.COMPETITION, phase, "Competition day; performance and recovery override weekly counts."))
                occupied_days.add(day)
            elif phase == TrainingPhase.RECOVERY_1 and (
                day <= date(2026, 10, 13)
                or day != tomorrow
                or fatigue not in {FatigueState.NORMAL, FatigueState.TIRED}
            ):
                planned.append(self._all_day(day, WorkoutType.RECOVERY, phase, "Post-competition recovery is intentional training."))
                occupied_days.add(day)

        for event in fixed_bjj:
            day = event.start_at.astimezone(self.timezone).date()
            if day in occupied_days:
                continue
            workout_type = self._bjj_type(day)
            planned.append(self._bjj_session(day, workout_type, event.start_at, event.end_at, event.external_id, "calendar"))
            occupied_days.add(day)

        retained_bjj_days = {
            item.start_at.astimezone(self.timezone).date()
            for item in existing
            if item.type in BJJ_TYPES and item.status in ACTIVE_STATUSES
        }
        occupied_days.update(retained_bjj_days)

        confirmed_bjj = {
            item.start_at.astimezone(self.timezone).date()
            for item in planned if item.type in BJJ_TYPES
        } | retained_bjj_days
        target_bjj = weekly_targets(phase_for_date(week_start), bjj_count=len(confirmed_bjj))["bjj"]
        candidates = self._bjj_candidates(
            week_start, current.date(), confirmed_bjj, occupied_days, declined, busy, labeled_busy, target_bjj,
        )
        reserved_days = occupied_days | {item.day for item in candidates}

        four_bjj = len(confirmed_bjj) >= 4
        existing_strength_types = {
            item.suppresses_type or item.type for item in existing
            if (item.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}
                or item.suppresses_type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B})
            and item.status != SessionStatus.CANCELLED
        }
        completed_strength = len(existing_strength_types)
        strength_types: list[WorkoutType] = [
            item for item in (WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B)
            if item not in existing_strength_types
        ]
        if four_bjj:
            strength_types = [] if completed_strength else [WorkoutType.STRENGTH_B]
        if taper_week:
            strength_types = [WorkoutType.STRENGTH_B] if completed_strength == 0 else []
        if late_partial_week:
            strength_types = []

        hard_days = {
            item.start_at.astimezone(self.timezone).date()
            for item in planned if item.type in HARD_TYPES
        } | {
            item.start_at.astimezone(self.timezone).date()
            for item in existing
            if item.type in HARD_TYPES and item.status in ACTIVE_STATUSES
        }
        hard_bjj_days = {
            item.start_at.astimezone(self.timezone).date()
            for item in planned if item.type == WorkoutType.BJJ_HARD
        } | {
            item.start_at.astimezone(self.timezone).date()
            for item in existing
            if item.type == WorkoutType.BJJ_HARD and item.status in ACTIVE_STATUSES
        } | {item.day for item in candidates if item.suggested_type == WorkoutType.BJJ_HARD}
        hard_days |= {item.day for item in candidates if item.suggested_type in HARD_TYPES}

        last_strength_day: date | None = None
        for workout_type in strength_types:
            chosen = self._choose_day(
                week_start, current.date(), reserved_days, busy,
                duration=60 if workout_type == WorkoutType.STRENGTH_A else 55,
                reject=lambda day, selected=workout_type: (
                    (selected == WorkoutType.STRENGTH_A and any(0 <= (hard - day).days <= 1 for hard in hard_bjj_days))
                    or (selected == WorkoutType.STRENGTH_A and self._would_triple_hard(day, hard_days))
                    or (last_strength_day is not None and abs((day - last_strength_day).days) < 2)
                    or self._strength_too_late_for_taper(day)
                    or phase_for_date(day) == TrainingPhase.RECOVERY_1
                    or self._work_load(day, labeled_busy) == "heavy"
                    or (selected == WorkoutType.STRENGTH_A and self._work_load(day, labeled_busy) == "moderate")
                ),
            )
            if chosen is None:
                continue
            day, start, end = chosen
            session = self._template_session(workout_type, day, start, end, fatigue if day == tomorrow else FatigueState.NORMAL)
            planned.append(session)
            reserved_days.add(day)
            last_strength_day = day
            if workout_type in HARD_TYPES:
                hard_days.add(day)

        zone2_decided = any(
            (item.type == WorkoutType.ZONE_2 or item.suppresses_type == WorkoutType.ZONE_2)
            and item.status in {SessionStatus.COMPLETED, SessionStatus.PARTIAL, SessionStatus.IN_PROGRESS}
            for item in existing
        )
        zone2_skipped = any(
            (item.type == WorkoutType.ZONE_2 or item.suppresses_type == WorkoutType.ZONE_2)
            and item.status == SessionStatus.SKIPPED
            for item in existing
        )
        place_zone2 = not zone2_decided and not late_partial_week and not four_bjj
        if zone2_skipped:
            remaining_free = [
                week_start + timedelta(days=i) for i in range(7)
                if week_start + timedelta(days=i) > current.date()
                and week_start + timedelta(days=i) not in reserved_days
            ]
            place_zone2 = place_zone2 and len(remaining_free) >= 2
        chosen_zone2 = None if not place_zone2 else self._choose_day(
            week_start, current.date(), reserved_days, busy, duration=45,
            reject=lambda day: self._work_load(day, labeled_busy) == "heavy",
        )
        if chosen_zone2 is not None:
            day, start, end = chosen_zone2
            planned.append(self._template_session(
                WorkoutType.ZONE_2, day, start, end,
                fatigue if day == tomorrow else FatigueState.NORMAL,
                weather=next((item for item in weather if item.day == day), None),
            ))
            reserved_days.add(day)

        bjj_days = confirmed_bjj | {item.day for item in candidates}
        self._attach_grip(planned, bjj_days, fatigue, four_bjj=four_bjj, taper=taper_week)

        planned = [self._adapt_tomorrow(item, fatigue) if item.local_date == tomorrow else item for item in planned]
        if fatigue in {FatigueState.VERY_FATIGUED, FatigueState.PAIN}:
            leftover = [item for item in candidates if item.day != tomorrow]
            if len(leftover) != len(candidates):
                start = datetime.combine(tomorrow, time(7, 30), self.timezone)
                planned.append(self._recovery_session(tomorrow, start, fatigue))
                reserved_days.add(tomorrow)
            candidates = leftover

        free_days = [
            week_start + timedelta(days=i) for i in range(7)
            if week_start + timedelta(days=i) > current.date()
            and week_start + timedelta(days=i) not in reserved_days
        ]
        if free_days:
            day = free_days[-1]
            planned.append(self._all_day(day, WorkoutType.REST, phase_for_date(day), "A complete rest day protects BJJ quality and adaptation."))

        return WeekPlan(week_start, tuple(sorted(planned, key=lambda item: item.start_at)), tuple(candidates))

    def week_quality(self, plan: WeekPlan) -> WeekQuality:
        sessions = plan.sessions
        return assess_week_quality(
            bjj=sum(item.type in BJJ_TYPES for item in sessions) + len(plan.candidates),
            hard_bjj=any(item.type == WorkoutType.BJJ_HARD for item in sessions) or any(
                item.suggested_type == WorkoutType.BJJ_HARD for item in plan.candidates
            ),
            strength=sum(item.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B} for item in sessions),
            zone_2=sum(item.type == WorkoutType.ZONE_2 for item in sessions),
            intervals=sum(item.type == WorkoutType.STRENGTH_A for item in sessions),
            rest=any(item.type in {WorkoutType.REST, WorkoutType.RECOVERY} for item in sessions),
        )

    def _bjj_candidates(
        self,
        week_start: date,
        today: date,
        confirmed: set[date],
        occupied: set[date],
        declined: set[date],
        busy: tuple[tuple[datetime, datetime], ...],
        labeled_busy: tuple[tuple[datetime, datetime, str], ...],
        target: int,
    ) -> list[BjjCandidate]:
        needed = max(0, target - len(confirmed))
        if needed == 0:
            return []
        candidates: list[BjjCandidate] = []
        for group in PREFERRED_BJJ_GROUPS:
            if needed <= 0:
                break
            if any((week_start + timedelta(days=offset)) in confirmed for offset in group):
                continue
            for offset in group:
                day = week_start + timedelta(days=offset)
                if (
                    day <= today
                    or day in occupied
                    or day in declined
                    or phase_for_date(day) in {
                        TrainingPhase.COMPETITION_1, TrainingPhase.COMPETITION_2, TrainingPhase.RECOVERY_1,
                    }
                    or self._work_load(day, labeled_busy) == "heavy"
                ):
                    continue
                start_clock = time(10, 0) if offset == 5 else time(7, 30)
                if self._exact_slot(day, start_clock, 90, busy) is None:
                    continue
                workout_type = self._bjj_type(day)
                candidates.append(BjjCandidate(
                    day, workout_type,
                    "Candidate BJJ day. Confirm or add a calendar class before it becomes a timed session.",
                    start_clock,
                ))
                needed -= 1
                break
        return candidates

    def _bjj_type(self, day: date) -> WorkoutType:
        phase = phase_for_date(day)
        if phase in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2}:
            return WorkoutType.BJJ_NORMAL if day.weekday() <= 1 else WorkoutType.BJJ_TECHNICAL
        return WorkoutType.BJJ_HARD if day.weekday() == 5 else WorkoutType.BJJ_NORMAL

    def _bjj_session(
        self, day: date, workout_type: WorkoutType, start: datetime, end: datetime,
        external_id: str | None, source: str,
    ) -> PlannedSession:
        rounds, rest = bjj_round_target(day)
        focuses = (
            ("Guard retention: establish frames before strength against the knee cut.",)
            if day.weekday() in {0, 1}
            else (("Spider → De La Riva transition.",) if day.weekday() in {3, 4}
                  else ("DLR → X guard → sweep.", "Establish top pressure efficiently."))
        )
        if workout_type == WorkoutType.BJJ_TECHNICAL:
            rounds = min(rounds, 2)
        reason = "Known BJJ calendar event takes priority." if source == "calendar" else (
            "Saturday is the competition-specific session." if workout_type == WorkoutType.BJJ_HARD
            else "Confirmed BJJ session; gym work was placed around it."
        )
        return PlannedSession(
            workout_type, start.astimezone(self.timezone), end.astimezone(self.timezone),
            phase_for_date(day), reason,
            "hard" if workout_type == WorkoutType.BJJ_HARD else ("easy" if workout_type == WorkoutType.BJJ_TECHNICAL else "normal"),
            coach_focus=focuses[:2], preparation="Leave home 30 minutes before weekday class." if day.weekday() < 5 else None,
            target_rounds=rounds, round_length_seconds=300, rest_seconds=rest,
            source=source, pinned=source == "calendar", source_calendar_event_id=external_id,
        )

    def _template_session(
        self, workout_type: WorkoutType, day: date, start: datetime, end: datetime,
        fatigue: FatigueState,
        weather: WeatherHint | None = None,
    ) -> PlannedSession:
        phase = phase_for_date(day)
        taper = phase in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2}
        template = reduced_template(workout_type) if taper and workout_type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B} else WORKOUT_TEMPLATES[workout_type]
        reason = "Placed around BJJ with enough recovery before the hardest mat session."
        if fatigue in {FatigueState.PAIN, FatigueState.VERY_FATIGUED}:
            return self._recovery_session(day, start, fatigue)
        exercises = template.exercises
        intensity = template.intensity
        if fatigue == FatigueState.TIRED:
            reason = "Volume reduced because Toshi is tired; important BJJ stays."
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
            reason = "Zone 2 stays; weather only changes the indoor modality."
        return PlannedSession(
            workout_type, start, end, phase, reason, intensity, exercises=exercises,
            preparation="Hydrate and prepare training equipment the night before.",
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
    ) -> None:
        if fatigue in {FatigueState.VERY_FATIGUED, FatigueState.PAIN}:
            return
        grip = WORKOUT_TEMPLATES[WorkoutType.GRIP].exercises[0]
        limit = 1 if four_bjj or taper or fatigue == FatigueState.TIRED else 2
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
