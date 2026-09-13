from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.domain.training.templates import WORKOUT_TEMPLATES, reduced_template
from app.domain.training.types import (
    ExistingSession,
    ExercisePrescription,
    FixedBjjEvent,
    PlannedSession,
    ReadinessAssessment,
    ReadinessInput,
    ReadinessLevel,
    SessionStatus,
    TrainingPhase,
    WeekPlan,
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
        fixed_bjj: tuple[FixedBjjEvent, ...] = (),
        existing: tuple[ExistingSession, ...] = (),
        readiness: ReadinessAssessment | None = None,
    ) -> WeekPlan:
        week_end = week_start + timedelta(days=7)
        current = now.astimezone(self.timezone)
        tomorrow = current.date() + timedelta(days=1)
        future_days_remaining = sum(
            week_start + timedelta(days=offset) > current.date()
            for offset in range(7)
        )
        late_partial_week = week_start <= current.date() < week_end and future_days_remaining <= 2
        occupied_days = {
            item.start_at.astimezone(self.timezone).date()
            for item in existing
            if item.status != SessionStatus.CANCELLED
        }
        fixed = [
            item for item in fixed_bjj
            if week_start <= item.start_at.astimezone(self.timezone).date() < week_end
        ]
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
                or readiness is None
                or readiness.level != ReadinessLevel.GREEN
            ):
                planned.append(self._all_day(day, WorkoutType.RECOVERY, phase, "Post-competition recovery is intentional training."))
                occupied_days.add(day)

        for event in fixed:
            day = event.start_at.astimezone(self.timezone).date()
            if day in occupied_days:
                continue
            workout_type = self._bjj_type(day)
            planned.append(self._bjj_session(day, workout_type, event.start_at, event.end_at, event.external_id, "calendar"))
            occupied_days.add(day)

        taper_week = any(
            phase_for_date(week_start + timedelta(days=offset)) in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2}
            for offset in range(7)
        )
        retained_bjj_count = sum(
            (item.type in {WorkoutType.BJJ_TECHNICAL, WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD}
             or item.suppresses_type in {WorkoutType.BJJ_TECHNICAL, WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD})
            and item.status not in {SessionStatus.SKIPPED, SessionStatus.CANCELLED}
            for item in existing
        )
        fixed_bjj_count = sum(1 for item in fixed if week_start <= item.start_at.astimezone(self.timezone).date() < week_end)
        generated_bjj_needed = max(0, (2 if taper_week else 3) - fixed_bjj_count - retained_bjj_count)
        groups = ((0, 1), (3, 4), (5,))
        for group in groups:
            if generated_bjj_needed <= 0:
                break
            if any((week_start + timedelta(days=offset)) in occupied_days for offset in group):
                continue
            for offset in group:
                day = week_start + timedelta(days=offset)
                # A same-day workout must have been committed by the prior evening
                # and will arrive through ``existing``. Do not surprise the athlete
                # with a newly generated session after the day has started.
                if day <= current.date() or phase_for_date(day) in {
                    TrainingPhase.COMPETITION_1, TrainingPhase.COMPETITION_2, TrainingPhase.RECOVERY_1,
                }:
                    continue
                start_clock = time(10, 0) if offset == 5 else time(7, 30)
                slot = self._exact_slot(day, start_clock, 90, busy)
                if slot is None:
                    continue
                workout_type = self._bjj_type(day)
                planned.append(self._bjj_session(day, workout_type, *slot, None, "scheduler"))
                occupied_days.add(day)
                generated_bjj_needed -= 1
                break

        if readiness and readiness.level != ReadinessLevel.UNKNOWN:
            planned = [
                self._adapt_bjj(item, readiness)
                if item.local_date == tomorrow and item.type in {
                    WorkoutType.BJJ_TECHNICAL, WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD,
                } else item
                for item in planned
            ]

        bjj_days = {
            item.start_at.astimezone(self.timezone).date()
            for item in planned if item.type in {WorkoutType.BJJ_TECHNICAL, WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD}
        } | {
            item.start_at.astimezone(self.timezone).date()
            for item in existing if item.type in {WorkoutType.BJJ_TECHNICAL, WorkoutType.BJJ_NORMAL, WorkoutType.BJJ_HARD}
            and item.status not in {SessionStatus.SKIPPED, SessionStatus.CANCELLED}
        }
        hard_bjj_days = {
            item.start_at.astimezone(self.timezone).date()
            for item in planned if item.type == WorkoutType.BJJ_HARD
        }
        four_bjj = len(bjj_days) >= 4
        existing_strength_types = {
            item.suppresses_type or item.type for item in existing
            if (item.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}
                or item.suppresses_type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B})
            and item.status not in {SessionStatus.SKIPPED, SessionStatus.CANCELLED}
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

        last_strength_day: date | None = None
        for workout_type in strength_types:
            chosen = self._choose_day(
                week_start, current.date(), occupied_days, busy,
                duration=60 if workout_type == WorkoutType.STRENGTH_A else 55,
                reject=lambda day: (
                    (workout_type == WorkoutType.STRENGTH_A and any(0 <= (hard - day).days <= 1 for hard in hard_bjj_days))
                    or (last_strength_day is not None and (day - last_strength_day).days < 2)
                    or self._strength_too_late_for_taper(day)
                    or phase_for_date(day) == TrainingPhase.RECOVERY_1
                ),
            )
            if chosen is None:
                continue
            day, start, end = chosen
            session = self._template_session(workout_type, day, start, end, readiness if day == tomorrow else None)
            planned.append(session)
            occupied_days.add(day)
            last_strength_day = day

        has_zone2 = any(
            (item.type == WorkoutType.ZONE_2 or item.suppresses_type == WorkoutType.ZONE_2)
            and item.status not in {SessionStatus.SKIPPED, SessionStatus.CANCELLED}
            for item in existing
        )
        chosen_zone2 = None if has_zone2 or late_partial_week else self._choose_day(
            week_start, current.date(), occupied_days, busy, duration=45, reject=lambda day: False,
        )
        if chosen_zone2 is not None:
            day, start, end = chosen_zone2
            planned.append(self._template_session(WorkoutType.ZONE_2, day, start, end, readiness if day == tomorrow else None))
            occupied_days.add(day)

        self._attach_grip(planned, bjj_days, readiness)

        free_days = [
            week_start + timedelta(days=i) for i in range(7)
            if week_start + timedelta(days=i) > current.date()
            and week_start + timedelta(days=i) not in occupied_days
        ]
        if free_days:
            day = free_days[-1]
            planned.append(self._all_day(day, WorkoutType.REST, phase_for_date(day), "A complete rest day protects BJJ quality and adaptation."))

        return WeekPlan(week_start, tuple(sorted(planned, key=lambda item: item.start_at)))

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
            else "Selected from the available weekday BJJ pair before placing gym work."
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
        readiness: ReadinessAssessment | None,
    ) -> PlannedSession:
        phase = phase_for_date(day)
        taper = phase in {TrainingPhase.TAPER_1, TrainingPhase.TAPER_2}
        template = reduced_template(workout_type) if taper and workout_type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B} else WORKOUT_TEMPLATES[workout_type]
        reason = "Placed around BJJ with enough recovery before the hardest mat session."
        if readiness and readiness.level in {ReadinessLevel.MANUAL_REVIEW, ReadinessLevel.RED}:
            return self._recovery_session(day, start, readiness)
        exercises = template.exercises
        intensity = template.intensity
        if readiness and readiness.level == ReadinessLevel.YELLOW:
            reason = f"Volume reduced because readiness has multiple warnings: {', '.join(readiness.alerts)}."
            intensity = "easy"
            exercises = tuple(
                ExercisePrescription(
                    item.name, item.load_value, item.load_unit,
                    max(1, round((item.sets or 1) * 0.67)) if item.sets else None,
                    item.reps, item.duration_seconds,
                    "Readiness-adjusted; finish with reserve.",
                )
                for item in exercises if item.name != "Stationary bike intervals"
            )
        return PlannedSession(
            workout_type, start, end, phase, reason, intensity, exercises=exercises,
            preparation="Hydrate and prepare training equipment the night before.",
        )

    def _recovery_session(self, day: date, start: datetime, readiness: ReadinessAssessment) -> PlannedSession:
        reason = "Manual review required because pain was reported." if readiness.level == ReadinessLevel.MANUAL_REVIEW else (
            f"Rest/recovery replaces hard work because of {', '.join(readiness.alerts)}."
        )
        end = start + timedelta(minutes=30)
        return PlannedSession(
            WorkoutType.RECOVERY, start, end, phase_for_date(day), reason, "easy",
            exercises=(ExercisePrescription("Easy mobility or walk", duration_seconds=20 * 60, notes="Stop if symptoms worsen"),),
        )

    def _adapt_bjj(self, item: PlannedSession, readiness: ReadinessAssessment) -> PlannedSession:
        if readiness.level in {ReadinessLevel.RED, ReadinessLevel.MANUAL_REVIEW}:
            return self._recovery_session(item.local_date, item.start_at, readiness)
        if readiness.level == ReadinessLevel.YELLOW and item.type == WorkoutType.BJJ_HARD:
            return PlannedSession(**{
                **item.__dict__,
                "type": WorkoutType.BJJ_NORMAL,
                "intensity": "normal",
                "target_rounds": min(item.target_rounds or 3, 3),
                "reason": f"Hard BJJ reduced because readiness has multiple warnings: {', '.join(readiness.alerts)}.",
            })
        return item

    def _attach_grip(
        self, planned: list[PlannedSession], bjj_days: set[date], readiness: ReadinessAssessment | None,
    ) -> None:
        if readiness and readiness.suppress_grip:
            return
        grip = WORKOUT_TEMPLATES[WorkoutType.GRIP].exercises[0]
        eligible: list[int] = []
        for index, item in enumerate(planned):
            if item.type not in {WorkoutType.ZONE_2, WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}:
                continue
            day = item.local_date
            if any(0 <= (bjj_day - day).days <= 1 for bjj_day in bjj_days):
                continue
            eligible.append(index)
        for index in eligible[:2]:
            item = planned[index]
            planned[index] = PlannedSession(**{**item.__dict__, "exercises": item.exercises + (grip,)})

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
