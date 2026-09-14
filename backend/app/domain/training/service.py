from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import delete, or_, select

from app.core.settings import settings
from app.database.models import (
    CalendarBridgeEvent,
    Competition,
    DailyWellbeingCheckIn,
    TrainingExercise,
    TrainingMetric,
    TrainingPlannerSetting,
    TrainingReminder,
    TrainingSession,
)
from app.database.session import SessionLocal
from app.domain.training.policy import (
    BJJ_DISPLACEABLE_TYPES,
    BJJ_TYPES,
    assess_week_quality,
    weekly_targets,
)
from app.domain.training.scheduler import TrainingScheduler, assess_readiness, phase_for_date
from app.domain.training.review import exercise_done, kinds_match
from app.domain.training.templates import WORKOUT_TEMPLATES
from app.domain.training.types import (
    ExistingSession,
    FatigueState,
    FixedBjjEvent,
    ReadinessInput,
    SessionStatus,
    WeatherHint,
    WorkoutType,
)


class TrainingService:
    def __init__(self, session_factory=SessionLocal, *, timezone_name: str | None = None, weather_service=None) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(timezone_name or settings.timezone)
        self._scheduler = TrainingScheduler(self._timezone.key)
        self._weather_service = weather_service

    def bootstrap(self, now: datetime | None = None) -> None:
        current = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            if session.get(TrainingPlannerSetting, 1) is None:
                session.add(TrainingPlannerSetting(
                    id=1,
                    enabled=settings.training_enabled,
                    timezone=self._timezone.key,
                    morning_checkin_time=settings.training_morning_checkin_time,
                    evening_plan_time=settings.training_evening_plan_time,
                    pre_reminder_minutes=settings.training_pre_reminder_minutes,
                    post_check_minutes=settings.training_post_check_minutes,
                    calendar_name=settings.training_calendar_name,
                ))
            for competition in (
                Competition(id="oct-2026", name="9th All Japan Jiu-Jitsu Championship", start_date=date(2026, 10, 10), end_date=date(2026, 10, 11), taper_start=date(2026, 10, 5), recovery_days=2),
                Competition(id="nov-2026", name="ASJJF Asian Open Jiu-Jitsu Championship 2026", start_date=date(2026, 11, 7), end_date=date(2026, 11, 8), taper_start=date(2026, 11, 2), recovery_days=2),
            ):
                session.merge(competition)
            session.commit()
        self.reconcile(current, cancel_missing=False)

    def reconcile(self, now: datetime | None = None, *, cancel_missing: bool = True) -> None:
        current = self._as_utc(now or datetime.now(UTC))
        local_day = current.astimezone(self._timezone).date()
        week_start = local_day - timedelta(days=local_day.weekday())
        self._reconcile_week(week_start, current, cancel_missing=cancel_missing)
        self._reconcile_week(week_start + timedelta(days=7), current, cancel_missing=cancel_missing)

    def _reconcile_week(self, week_start: date, now: datetime, *, cancel_missing: bool = True) -> None:
        start = datetime.combine(week_start, time.min, self._timezone).astimezone(UTC)
        end = start + timedelta(days=7)
        with self._session_factory() as session:
            planner_settings = session.get(TrainingPlannerSetting, 1)
            if planner_settings is not None and not planner_settings.enabled:
                return
            calendar_rows = list(session.scalars(
                select(CalendarBridgeEvent)
                .where(CalendarBridgeEvent.start_at < end)
                .where(CalendarBridgeEvent.end_at > start)
            ).all())
            all_sessions = list(session.scalars(
                select(TrainingSession)
                .where(or_(
                    (TrainingSession.start_at < end) & (TrainingSession.end_at > start),
                    TrainingSession.planned_week_start == week_start,
                    (
                        (TrainingSession.start_at >= start - timedelta(days=1))
                        & (TrainingSession.start_at < start)
                        & TrainingSession.planned_type.in_([
                            WorkoutType.STRENGTH_A.value, WorkoutType.STRENGTH_B.value,
                        ])
                        & TrainingSession.status.in_([
                            SessionStatus.COMPLETED.value, SessionStatus.PARTIAL.value,
                            SessionStatus.IN_PROGRESS.value,
                        ])
                    ),
                ))
            ).all())
            retained = [row for row in all_sessions if self._retained(row, now)]
            keywords = tuple((planner_settings.bjj_title_keywords if planner_settings else []) or ["bjj", "jiu jitsu", "jiujitsu", "open mat"])
            fixed_bjj = tuple(
                FixedBjjEvent(
                    row.external_id, row.title,
                    self._as_utc(row.start_at).astimezone(self._timezone),
                    self._as_utc(row.end_at).astimezone(self._timezone),
                )
                for row in calendar_rows
                if row.managed_session_id is None and any(keyword.lower() in row.title.lower() for keyword in keywords)
            )
            confirmed_bjj_days = {
                item.start_at.astimezone(self._timezone).date()
                for item in fixed_bjj
            } | {
                self._as_utc(row.start_at).astimezone(self._timezone).date()
                for row in retained
                if WorkoutType(row.planned_type) in BJJ_TYPES
                and row.status in {
                    SessionStatus.PLANNED.value, SessionStatus.IN_PROGRESS.value,
                    SessionStatus.COMPLETED.value, SessionStatus.PARTIAL.value,
                }
            }
            self._skip_past_due(retained, now)
            displaced_ids = {
                row.id for row in retained
                if WorkoutType(row.planned_type) in BJJ_DISPLACEABLE_TYPES
                and row.status == SessionStatus.PLANNED.value
                and self._as_utc(row.start_at).astimezone(self._timezone).date() in confirmed_bjj_days
            }
            # Confirmed BJJ owns its day. Cancel the future lower-priority slot
            # before planning so it can be placed elsewhere only if recovery
            # and the remaining week safely allow it. Completed/active work is
            # never rewritten here.
            self._cancel_displaced(session, retained, displaced_ids, now, "confirmed BJJ")
            retained = [row for row in retained if row.id not in displaced_ids]
            labeled_busy = tuple(
                (
                    self._as_utc(row.start_at).astimezone(self._timezone),
                    self._as_utc(row.end_at).astimezone(self._timezone),
                    row.title or "",
                )
                for row in calendar_rows if not row.is_all_day and row.managed_session_id is None
            )
            busy = tuple((start, end) for start, end, _ in labeled_busy)
            existing = tuple(self._existing(row) for row in retained)
            fatigue = self._latest_fatigue(session, now)
            declined = self._declined_dates(planner_settings, week_start)
            plan = self._scheduler.plan_week(
                week_start, now=now, busy=busy, labeled_busy=labeled_busy, fixed_bjj=fixed_bjj,
                existing=existing, fatigue=fatigue, weather=self._weather_hints(), declined_bjj=declined,
            )
            candidate_days = {item.day for item in plan.candidates}
            candidate_displaced_ids = {
                row.id for row in retained
                if WorkoutType(row.planned_type) in BJJ_DISPLACEABLE_TYPES
                and row.status == SessionStatus.PLANNED.value
                and self._as_utc(row.start_at).astimezone(self._timezone).date() in candidate_days
                and not (row.pinned and row.source == "manual")
            }
            if candidate_displaced_ids:
                self._cancel_displaced(
                    session, retained, candidate_displaced_ids, now,
                    "a replacement BJJ opportunity",
                )
                retained = [row for row in retained if row.id not in candidate_displaced_ids]
                plan = self._scheduler.plan_week(
                    week_start, now=now, busy=busy, labeled_busy=labeled_busy, fixed_bjj=fixed_bjj,
                    existing=tuple(self._existing(row) for row in retained),
                    fatigue=fatigue, weather=self._weather_hints(), declined_bjj=declined,
                )
            desired_ids: set[str] = set()
            for item in plan.sessions:
                stable_key = item.source_calendar_event_id or f"{item.local_date.isoformat()}:{item.type.value}:{item.source}"
                session_id = str(uuid5(NAMESPACE_URL, f"chili-training:{stable_key}"))
                desired_ids.add(session_id)
                row = session.get(TrainingSession, session_id)
                if row is None:
                    row = TrainingSession(id=session_id, created_at=now, revision=1)
                    session.add(row)
                changed = self._apply_plan(row, item, now)
                if changed and row.created_at != now:
                    row.revision += 1
                self._replace_exercises(session, row.id, item.exercises)
                self._ensure_reminders(session, row, planner_settings, now)
            for row in retained:
                self._ensure_reminders(session, row, planner_settings, now)
            existing_planned_bjj = any(
                row.status == SessionStatus.PLANNED.value and (row.planned_type or "").startswith("bjj_")
                for row in all_sessions
            )
            kept_or_planned_bjj = any(item.type.value.startswith("bjj_") for item in plan.sessions) or any(
                (row.planned_type or "").startswith("bjj_")
                for row in retained
                if row.status != SessionStatus.CANCELLED.value
            )
            should_cancel = cancel_missing and (kept_or_planned_bjj or not existing_planned_bjj)
            if should_cancel:
                for row in all_sessions:
                    if row.id in desired_ids or self._retained(row, now):
                        continue
                    if row.status == SessionStatus.PLANNED.value:
                        row.status = SessionStatus.CANCELLED.value
                        row.revision += 1
                        row.updated_at = now
                        for reminder in session.scalars(select(TrainingReminder).where(TrainingReminder.session_id == row.id)):
                            if reminder.status == "pending":
                                reminder.status = "cancelled"
            session.commit()

    def overview(self, now: datetime | None = None) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        local_day = current.astimezone(self._timezone).date()
        week_start = local_day - timedelta(days=local_day.weekday())
        window_start = datetime.combine(week_start, time.min, self._timezone).astimezone(UTC)
        window_end = window_start + timedelta(days=14)
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(TrainingSession)
                .where(or_(
                    TrainingSession.start_at >= window_start,
                    (
                        (TrainingSession.start_at >= window_start - timedelta(days=1))
                        & TrainingSession.planned_type.in_([
                            WorkoutType.STRENGTH_A.value, WorkoutType.STRENGTH_B.value,
                        ])
                        & TrainingSession.status.in_([
                            SessionStatus.COMPLETED.value, SessionStatus.PARTIAL.value,
                            SessionStatus.IN_PROGRESS.value,
                        ])
                    ),
                ))
                .where(TrainingSession.start_at < window_end)
                .where(TrainingSession.status != SessionStatus.CANCELLED.value)
                .order_by(TrainingSession.start_at)
            ).all())
            exercises = list(session.scalars(
                select(TrainingExercise).where(TrainingExercise.session_id.in_([row.id for row in rows] or [""]))
                .order_by(TrainingExercise.session_id, TrainingExercise.position)
            ).all())
            metrics = list(session.scalars(select(TrainingMetric).order_by(TrainingMetric.recorded_at)).all())
            wellbeing = list(session.scalars(
                select(DailyWellbeingCheckIn)
                .where(DailyWellbeingCheckIn.local_date >= local_day - timedelta(days=42))
                .order_by(DailyWellbeingCheckIn.local_date)
            ).all())
            competitions = list(session.scalars(select(Competition).order_by(Competition.start_date)).all())
        exercise_map: dict[str, list[dict]] = {}
        for item in exercises:
            exercise_map.setdefault(item.session_id, []).append(self._exercise_dict(item))
        serialized = [self._session_dict(row, exercise_map.get(row.id, [])) for row in rows]
        visible = [item for item in serialized if item["status"] != SessionStatus.SKIPPED.value]
        today_sessions = [item for item in visible if self._local_date(item["start_at"]) == local_day]
        tomorrow = local_day + timedelta(days=1)
        tomorrow_sessions = [item for item in visible if self._local_date(item["start_at"]) == tomorrow]
        current_week = [
            item for item in serialized
            if week_start <= self._local_date(item["start_at"]) < week_start + timedelta(days=7)
            or (
                self._local_date(item["start_at"]) == week_start - timedelta(days=1)
                and item["planned_type"] in {WorkoutType.STRENGTH_A.value, WorkoutType.STRENGTH_B.value}
                and item["status"] in {
                    SessionStatus.COMPLETED.value, SessionStatus.PARTIAL.value,
                    SessionStatus.IN_PROGRESS.value,
                }
            )
        ]
        upcoming = [
            item for item in visible
            if local_day <= self._local_date(item["start_at"]) < local_day + timedelta(days=7)
        ]
        candidates = self._candidate_dicts(week_start, current)
        tomorrow_session = tomorrow_sessions[0] if tomorrow_sessions else None
        return {
            "generated_at": current.isoformat(),
            "timezone": self._timezone.key,
            "phase": phase_for_date(local_day).value,
            "today": today_sessions[0] if today_sessions else None,
            "tomorrow": tomorrow_session,
            "week_start": week_start.isoformat(),
            "week": current_week,
            "upcoming": upcoming,
            "countdowns": [
                {"id": item.id, "name": item.name, "start_date": item.start_date.isoformat(), "end_date": item.end_date.isoformat(), "days_remaining": max(0, (item.start_date - local_day).days)}
                for item in competitions if item.end_date >= local_day
            ],
            "compliance": self._compliance(current_week, phase_for_date(local_day)),
            "trends": self._trends(rows, metrics, wellbeing, local_day),
            "readiness": self._readiness_dict(wellbeing[-1] if wellbeing else None),
            "bjj_candidates": candidates,
            "week_quality": self._week_quality(current_week, candidates),
            "tomorrow_prescription": self._tomorrow_prescription(
                tomorrow_session,
                current_week,
                phase_for_date(local_day),
                tomorrow=tomorrow,
                candidates=candidates,
            ),
            "last_adjustment": self.last_adjustment(),
        }

    def last_adjustment(self) -> dict | None:
        with self._session_factory() as session:
            row = session.get(TrainingPlannerSetting, 1)
            payload = getattr(row, "last_adjustment", None) if row is not None else None
        return payload if isinstance(payload, dict) and payload else None

    def store_last_adjustment(self, payload: dict) -> None:
        with self._session_factory() as session:
            row = session.get(TrainingPlannerSetting, 1)
            if row is None:
                return
            row.last_adjustment = payload
            session.commit()

    def session(self, session_id: str) -> dict | None:
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is None:
                return None
            exercises = list(session.scalars(
                select(TrainingExercise).where(TrainingExercise.session_id == session_id).order_by(TrainingExercise.position)
            ).all())
            metrics = list(session.scalars(
                select(TrainingMetric).where(TrainingMetric.session_id == session_id).order_by(TrainingMetric.metric_type, TrainingMetric.sequence)
            ).all())
            result = self._session_dict(row, [self._exercise_dict(item) for item in exercises])
            result["metrics"] = [self._metric_dict(item) for item in metrics]
            return result

    def for_date(self, local_date: date) -> dict | None:
        sessions = self.sessions_on(local_date)
        active = [
            item for item in sessions
            if item["status"] not in {SessionStatus.SKIPPED.value, SessionStatus.CANCELLED.value}
        ]
        return (active or sessions)[0] if sessions else None

    def sessions_on(self, local_date: date) -> list[dict]:
        start = datetime.combine(local_date, time.min, self._timezone).astimezone(UTC)
        end = start + timedelta(days=1)
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(TrainingSession)
                .where(TrainingSession.start_at < end)
                .where(TrainingSession.end_at > start)
                .where(TrainingSession.status != SessionStatus.CANCELLED.value)
                .order_by(TrainingSession.start_at)
            ).all())
            result = []
            for row in rows:
                exercises = list(session.scalars(
                    select(TrainingExercise)
                    .where(TrainingExercise.session_id == row.id)
                    .order_by(TrainingExercise.position)
                ).all())
                result.append(self._session_dict(row, [self._exercise_dict(item) for item in exercises]))
            return result

    def log_matching_workout(
        self,
        local_date: date,
        *,
        kind: str | None = None,
        exercises: list[dict] | None = None,
        note: str | None = None,
        now: datetime | None = None,
    ) -> dict | None:
        sessions = self.sessions_on(local_date)
        chosen = next((item for item in sessions if kinds_match(item.get("planned_type"), kind)), None)
        if chosen is None and not kind and sessions:
            chosen = sessions[0]
        if chosen is None:
            return None
        return self.log_workout_check(chosen["id"], exercises=exercises, note=note, now=now)

    def record_readiness(self, day: date, values: dict, *, now: datetime | None = None) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            row = session.get(DailyWellbeingCheckIn, day)
            if row is None:
                row = DailyWellbeingCheckIn(local_date=day, updated_at=current, source="openclaw-training")
                session.add(row)
            for key, value in values.items():
                if value is not None and hasattr(row, key):
                    setattr(row, key, value)
            row.updated_at = current
            row.source = "openclaw-training"
            session.commit()
        self.reconcile(current)
        return self.overview(current)["readiness"]

    def record_fatigue(self, day: date, state: str, *, now: datetime | None = None) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        parsed = FatigueState(state)
        with self._session_factory() as session:
            row = session.get(DailyWellbeingCheckIn, day)
            if row is None:
                row = DailyWellbeingCheckIn(local_date=day, updated_at=current, source="openclaw-training")
                session.add(row)
            row.fatigue_state = parsed.value
            if parsed == FatigueState.PAIN:
                row.pain = True
            row.updated_at = current
            row.source = "openclaw-training"
            session.commit()
        self.reconcile(current)
        return self.overview(current)

    def confirm_bjj(self, day: date, *, hard: bool | None = None, now: datetime | None = None) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        self._set_declined(day, False)
        week_start = day - timedelta(days=day.weekday())
        candidate = next((item for item in self._candidate_dicts(week_start, current) if item["date"] == day.isoformat()), None)
        clock = time(10, 0) if day.weekday() == 5 else time(7, 30)
        if candidate and candidate.get("preferred_clock"):
            hour, minute = (int(part) for part in str(candidate["preferred_clock"]).split(":")[:2])
            clock = time(hour, minute)
        is_hard = day.weekday() == 5 if hard is None else hard
        if candidate and hard is None:
            is_hard = candidate.get("suggested_type") == WorkoutType.BJJ_HARD.value
        start = datetime.combine(day, clock, self._timezone)
        return self.add_bjj(start, hard=is_hard, now=current)

    def decline_bjj(self, day: date, *, now: datetime | None = None) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        self._set_declined(day, True)
        self.reconcile(current)
        return {"day": day.isoformat(), "status": "declined", **self.overview(current)}

    def schedule_gym(self, day: date, workout_type: str, *, now: datetime | None = None) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        target = WorkoutType(workout_type)
        if target not in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}:
            raise ValueError("Gym day must be strength_a or strength_b.")
        if target == WorkoutType.STRENGTH_A and any(
            item.get("planned_type") == WorkoutType.BJJ_HARD.value
            and item.get("status") not in {SessionStatus.SKIPPED.value, SessionStatus.CANCELLED.value}
            for item in self.sessions_on(day)
        ):
            raise ValueError("Strength A cannot be scheduled on a Hard BJJ day.")
        existing = self.for_date(day)
        if existing is not None:
            updated = self.replace_session(existing["id"], target.value, now=current)
            self._assign_gym_week(updated["id"], day, current)
            self.reconcile(current)
            return self.session(updated["id"]) or updated
        template = WORKOUT_TEMPLATES[target]
        start = datetime.combine(day, time(14, 0), self._timezone)
        session_id = str(uuid5(NAMESPACE_URL, f"chili-training:gym:{day.isoformat()}:{target.value}"))
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is None:
                row = TrainingSession(
                    id=session_id, planned_type=target.value, status=SessionStatus.PLANNED.value,
                    phase=phase_for_date(day).value, planned_week_start=self._training_week_start(day),
                    start_at=start.astimezone(UTC), end_at=(start + timedelta(minutes=template.estimated_minutes)).astimezone(UTC),
                    is_all_day=False, estimated_minutes=template.estimated_minutes, intensity=template.intensity,
                    reason="Gym chosen explicitly; the remaining week was rebuilt around it.",
                    coach_focus=["Strength maintenance, not a PR day."],
                    source="manual", pinned=True, revision=1, created_at=current, updated_at=current,
                )
                session.add(row)
                self._replace_exercises(session, row.id, template.exercises)
            session.commit()
        self.reconcile(current)
        result = self.session(session_id)
        assert result is not None
        return result

    def place_session(self, day: date, workout_type: str, *, now: datetime | None = None, pinned: bool = False) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        target = WorkoutType(workout_type)
        if target in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B}:
            if pinned:
                return self.schedule_gym(day, target.value, now=current)
            return self._place_template(day, target, now=current, pinned=False, source="scheduler")
        if target == WorkoutType.REST:
            existing = self.for_date(day)
            if existing is None:
                raise KeyError("No training session to rest.")
            return self.replace_session(existing["id"], "rest", now=current)
        if target not in WORKOUT_TEMPLATES:
            raise ValueError(f"Cannot place {workout_type}.")
        existing = self.for_date(day)
        if existing is not None:
            return self.replace_session(existing["id"], target.value, now=current)
        return self._place_template(day, target, now=current, pinned=pinned, source="manual" if pinned else "scheduler")

    def _place_template(
        self, day: date, target: WorkoutType, *, now: datetime, pinned: bool, source: str,
    ) -> dict:
        template = WORKOUT_TEMPLATES[target]
        start = datetime.combine(day, time(14, 0), self._timezone)
        session_id = str(uuid5(NAMESPACE_URL, f"chili-training:place:{day.isoformat()}:{target.value}"))
        reason = (
            "Gym chosen explicitly; the remaining week was rebuilt around it."
            if pinned else
            "Placed around BJJ only if the remaining week still had a safe open day."
        )
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is None:
                row = TrainingSession(
                    id=session_id, planned_type=target.value, status=SessionStatus.PLANNED.value,
                    phase=phase_for_date(day).value, planned_week_start=self._training_week_start(day),
                    start_at=start.astimezone(UTC), end_at=(start + timedelta(minutes=template.estimated_minutes)).astimezone(UTC),
                    is_all_day=False, estimated_minutes=template.estimated_minutes, intensity=template.intensity,
                    reason=reason,
                    coach_focus=["Keep this repeatable. Do not turn an Open day into junk volume."],
                    source=source, pinned=pinned, revision=1, created_at=now, updated_at=now,
                )
                session.add(row)
                self._replace_exercises(session, row.id, template.exercises)
            session.commit()
        self.reconcile(now)
        result = self.session(session_id)
        assert result is not None
        return result

    @staticmethod
    def _training_week_start(day: date) -> date:
        if day.weekday() == 6:
            return day + timedelta(days=1)
        return day - timedelta(days=day.weekday())

    def _assign_gym_week(self, session_id: str, day: date, now: datetime) -> None:
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is None:
                return
            row.planned_week_start = self._training_week_start(day)
            row.pinned = True
            row.source = "manual"
            row.is_all_day = False
            if row.planned_type in WORKOUT_TEMPLATES:
                template = WORKOUT_TEMPLATES[WorkoutType(row.planned_type)]
                start = datetime.combine(day, time(14, 0), self._timezone)
                row.start_at = start.astimezone(UTC)
                row.end_at = (start + timedelta(minutes=template.estimated_minutes)).astimezone(UTC)
                row.estimated_minutes = template.estimated_minutes
            row.reason = "Gym chosen explicitly; the remaining week was rebuilt around it."
            row.updated_at = now
            session.commit()

    def update_session(
        self, session_id: str, *, status: str | None = None, actual_type: str | None = None,
        start_at: datetime | None = None, notes: str | None = None,
        session_rpe: float | None = None, final_round_quality: int | None = None,
        metrics: list[dict] | None = None, now: datetime | None = None,
    ) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is None:
                raise KeyError(session_id)
            if status is not None:
                row.status = SessionStatus(status).value
            if actual_type is not None:
                row.actual_type = WorkoutType(actual_type).value
            if start_at is not None:
                duration = row.end_at - row.start_at
                row.start_at = self._as_utc(start_at)
                row.end_at = row.start_at + duration
                row.pinned = True
            if notes is not None:
                row.notes = notes
            if session_rpe is not None:
                row.session_rpe = session_rpe
            if final_round_quality is not None:
                row.final_round_quality = final_round_quality
            row.revision += 1
            row.updated_at = current
            if metrics is not None:
                session.execute(delete(TrainingMetric).where(TrainingMetric.session_id == row.id))
                for item in metrics:
                    session.add(TrainingMetric(
                        session_id=row.id, metric_type=item["metric_type"], sequence=item.get("sequence"),
                        value=item["value"], unit=item["unit"], recorded_at=current,
                    ))
            if row.status in {SessionStatus.COMPLETED.value, SessionStatus.PARTIAL.value}:
                local_date = self._as_utc(row.start_at).astimezone(self._timezone).date()
                if row.planned_type in {WorkoutType.STRENGTH_A.value, WorkoutType.STRENGTH_B.value}:
                    row.planned_week_start = self._training_week_start(local_date)
                wellbeing = session.get(DailyWellbeingCheckIn, local_date)
                if wellbeing is None:
                    wellbeing = DailyWellbeingCheckIn(local_date=local_date, updated_at=current, source="training")
                    session.add(wellbeing)
                wellbeing.trained = True
                if row.planned_type.startswith("bjj_"):
                    wellbeing.jiujitsu = True
                if row.planned_type.startswith("strength_"):
                    wellbeing.gym = True
                wellbeing.updated_at = current
            session.commit()
        self.reconcile(current)
        result = self.session(session_id)
        assert result is not None
        return result

    def log_workout_check(
        self,
        session_id: str,
        *,
        exercises: list[dict] | None = None,
        note: str | None = None,
        now: datetime | None = None,
    ) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is None:
                raise KeyError(session_id)
            items = list(session.scalars(
                select(TrainingExercise)
                .where(TrainingExercise.session_id == session_id)
                .order_by(TrainingExercise.position)
            ).all())
            done_by_name = {
                str(item.get("name")): bool(item.get("done"))
                for item in (exercises or [])
                if item.get("name")
            }
            for item in items:
                matched = exercise_done(item.name, done_by_name)
                if matched is not None:
                    item.done = matched
            if items:
                done_count = sum(1 for item in items if item.done)
                if done_count == 0:
                    status = SessionStatus.SKIPPED
                elif done_count == len(items):
                    status = SessionStatus.COMPLETED
                else:
                    status = SessionStatus.PARTIAL
            else:
                status = SessionStatus.COMPLETED
            row.status = status.value
            if note is not None:
                row.notes = note
            row.revision += 1
            row.updated_at = current
            if row.status in {SessionStatus.COMPLETED.value, SessionStatus.PARTIAL.value}:
                local_date = self._as_utc(row.start_at).astimezone(self._timezone).date()
                if row.planned_type in {WorkoutType.STRENGTH_A.value, WorkoutType.STRENGTH_B.value}:
                    row.planned_week_start = self._training_week_start(local_date)
                wellbeing = session.get(DailyWellbeingCheckIn, local_date)
                if wellbeing is None:
                    wellbeing = DailyWellbeingCheckIn(
                        local_date=local_date, updated_at=current, source="training",
                    )
                    session.add(wellbeing)
                wellbeing.trained = True
                if row.planned_type.startswith("bjj_"):
                    wellbeing.jiujitsu = True
                if row.planned_type.startswith("strength_"):
                    wellbeing.gym = True
                wellbeing.updated_at = current
            session.commit()
        result = self.session(session_id)
        assert result is not None
        return result

    def replace_session(self, session_id: str, workout_type: str, *, now: datetime | None = None) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        target = WorkoutType(workout_type)
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is None:
                raise KeyError(session_id)
            if row.status not in {SessionStatus.PLANNED.value, SessionStatus.IN_PROGRESS.value}:
                raise ValueError("Only an upcoming or active session can be replaced.")
            if target in WORKOUT_TEMPLATES:
                template = WORKOUT_TEMPLATES[target]
                row.estimated_minutes = template.estimated_minutes
                row.end_at = row.start_at + timedelta(minutes=template.estimated_minutes)
                row.intensity = template.intensity
                self._replace_exercises(session, row.id, template.exercises)
            elif target in {WorkoutType.RECOVERY, WorkoutType.REST}:
                row.estimated_minutes = 30 if target == WorkoutType.RECOVERY else 0
                row.end_at = row.start_at + timedelta(minutes=max(15, row.estimated_minutes))
                row.intensity = "easy"
                self._replace_exercises(session, row.id, ())
            else:
                row.estimated_minutes = 90
                row.end_at = row.start_at + timedelta(minutes=90)
                row.intensity = "hard" if target == WorkoutType.BJJ_HARD else "normal"
                self._replace_exercises(session, row.id, ())
            if row.original_planned_type is None:
                row.original_planned_type = row.planned_type
            row.planned_type = target.value
            row.reason = "Replacement selected through OpenClaw; the rest of the week was recalculated."
            row.pinned = True
            row.revision += 1
            row.updated_at = current
            session.commit()
        self.reconcile(current)
        result = self.session(session_id)
        assert result is not None
        return result

    def add_bjj(self, start_at: datetime, *, hard: bool = False, now: datetime | None = None) -> dict:
        current = self._as_utc(now or datetime.now(UTC))
        start = self._as_utc(start_at)
        workout_type = WorkoutType.BJJ_HARD if hard else WorkoutType.BJJ_NORMAL
        session_id = str(uuid5(NAMESPACE_URL, f"chili-training:manual:{start.isoformat()}:{workout_type.value}"))
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is None:
                row = TrainingSession(
                    id=session_id, planned_type=workout_type.value, status=SessionStatus.PLANNED.value,
                    phase=phase_for_date(start.astimezone(self._timezone).date()).value,
                    planned_week_start=start.astimezone(self._timezone).date() - timedelta(days=start.astimezone(self._timezone).date().weekday()),
                    start_at=start, end_at=start + timedelta(minutes=90), is_all_day=False,
                    estimated_minutes=90, intensity="hard" if hard else "normal",
                    reason="BJJ session added through OpenClaw; the remaining week was rebalanced.",
                    coach_focus=["Guard retention: establish frames before strength against the knee cut."],
                    source="manual", pinned=True, revision=1, created_at=current, updated_at=current,
                    target_rounds=3, round_length_seconds=300, rest_seconds=120,
                )
                session.add(row)
                session.commit()
        self.reconcile(current)
        result = self.session(session_id)
        assert result is not None
        return result

    def calendar_plan(self, now: datetime | None = None, days: int = 30) -> list[dict]:
        current = self._as_utc(now or datetime.now(UTC))
        end = current + timedelta(days=days)
        with self._session_factory() as session:
            rows = list(session.scalars(
                select(TrainingSession)
                .where(TrainingSession.start_at >= current - timedelta(days=1))
                .where(TrainingSession.start_at < end)
                .where(TrainingSession.status.not_in([SessionStatus.CANCELLED.value, SessionStatus.SKIPPED.value]))
                .where(TrainingSession.source != "calendar")
                .order_by(TrainingSession.start_at)
            ).all())
        return [
            {
                "session_id": row.id,
                "title": self._title(row.planned_type),
                "start_at": self._as_utc(row.start_at).isoformat(),
                "end_at": self._as_utc(row.end_at).isoformat(),
                "is_all_day": row.is_all_day,
                "notes": f"Managed by Chili Training\nchili-training:{row.id}\n{row.reason}",
            }
            for row in rows
        ]

    def link_calendar_event(self, session_id: str, apple_event_id: str) -> None:
        with self._session_factory() as session:
            row = session.get(TrainingSession, session_id)
            if row is not None and row.apple_event_id != apple_event_id:
                row.apple_event_id = apple_event_id
                session.commit()

    def due_reminders(self, now: datetime | None = None) -> list[tuple[TrainingReminder, dict]]:
        current = self._as_utc(now or datetime.now(UTC))
        with self._session_factory() as session:
            reminders = list(session.scalars(
                select(TrainingReminder)
                .where(TrainingReminder.status == "pending")
                .where(TrainingReminder.scheduled_for <= current)
                .order_by(TrainingReminder.scheduled_for)
            ).all())
            result = []
            for reminder in reminders:
                if reminder.session_id is None:
                    continue
                row = session.get(TrainingSession, reminder.session_id)
                if row is None or row.revision != reminder.session_revision or row.status != SessionStatus.PLANNED.value:
                    reminder.status = "cancelled"
                    continue
                exercises = list(session.scalars(
                    select(TrainingExercise)
                    .where(TrainingExercise.session_id == row.id)
                    .order_by(TrainingExercise.position)
                ).all())
                result.append((reminder, self._session_dict(row, [self._exercise_dict(item) for item in exercises])))
            session.commit()
            return result

    def mark_reminder_sent(self, reminder_id: int, now: datetime | None = None) -> None:
        with self._session_factory() as session:
            row = session.get(TrainingReminder, reminder_id)
            if row is not None and row.status == "pending":
                row.status = "sent"
                row.sent_at = self._as_utc(now or datetime.now(UTC))
                session.commit()

    def _latest_fatigue(self, session, now: datetime) -> FatigueState:
        local_day = now.astimezone(self._timezone).date()
        row = session.scalar(
            select(DailyWellbeingCheckIn)
            .where(DailyWellbeingCheckIn.local_date <= local_day)
            .where(DailyWellbeingCheckIn.local_date >= local_day - timedelta(days=1))
            .order_by(DailyWellbeingCheckIn.local_date.desc())
            .limit(1)
        )
        if row is None or not getattr(row, "fatigue_state", None):
            return FatigueState.NORMAL
        try:
            return FatigueState(row.fatigue_state)
        except ValueError:
            return FatigueState.NORMAL

    def _weather_hints(self) -> tuple[WeatherHint, ...]:
        service = self._weather_service
        if service is None:
            return ()
        try:
            forecast = service.forecast()
        except Exception:
            return ()
        hints = []
        for day in (getattr(forecast, "today", None), getattr(forecast, "tomorrow", None)):
            if day is None:
                continue
            hints.append(WeatherHint(
                day.date,
                outdoor_impractical=getattr(day, "icon", "") in {"rain", "storm", "snow"},
                condition=getattr(day, "condition", "") or "",
            ))
        return tuple(hints)

    def _declined_dates(self, planner_settings, week_start: date) -> tuple[date, ...]:
        raw = getattr(planner_settings, "declined_bjj_dates", None) or []
        days: list[date] = []
        for item in raw:
            try:
                day = date.fromisoformat(str(item))
            except ValueError:
                continue
            if day >= week_start - timedelta(days=14):
                days.append(day)
        return tuple(days)

    def _set_declined(self, day: date, declined: bool) -> None:
        with self._session_factory() as session:
            settings_row = session.get(TrainingPlannerSetting, 1)
            if settings_row is None:
                return
            raw = [str(item) for item in (settings_row.declined_bjj_dates or [])]
            key = day.isoformat()
            if declined and key not in raw:
                raw.append(key)
            if not declined:
                raw = [item for item in raw if item != key]
            cutoff = (day - timedelta(days=21)).isoformat()
            settings_row.declined_bjj_dates = [item for item in raw if item >= cutoff]
            session.commit()

    def _candidate_dicts(self, week_start: date, now: datetime) -> list[dict]:
        start = datetime.combine(week_start, time.min, self._timezone).astimezone(UTC)
        end = start + timedelta(days=7)
        with self._session_factory() as session:
            planner_settings = session.get(TrainingPlannerSetting, 1)
            calendar_rows = list(session.scalars(
                select(CalendarBridgeEvent)
                .where(CalendarBridgeEvent.start_at < end)
                .where(CalendarBridgeEvent.end_at > start)
            ).all())
            all_sessions = list(session.scalars(
                select(TrainingSession)
                .where(or_(
                    (TrainingSession.start_at < end) & (TrainingSession.end_at > start),
                    TrainingSession.planned_week_start == week_start,
                ))
            ).all())
            retained = [row for row in all_sessions if self._retained(row, now)]
            keywords = tuple((planner_settings.bjj_title_keywords if planner_settings else []) or ["bjj", "jiu jitsu", "jiujitsu", "open mat"])
            fixed_bjj = tuple(
                FixedBjjEvent(
                    row.external_id, row.title,
                    self._as_utc(row.start_at).astimezone(self._timezone),
                    self._as_utc(row.end_at).astimezone(self._timezone),
                )
                for row in calendar_rows
                if row.managed_session_id is None and any(keyword.lower() in row.title.lower() for keyword in keywords)
            )
            labeled_busy = tuple(
                (
                    self._as_utc(row.start_at).astimezone(self._timezone),
                    self._as_utc(row.end_at).astimezone(self._timezone),
                    row.title or "",
                )
                for row in calendar_rows if not row.is_all_day and row.managed_session_id is None
            )
            busy = tuple((start_at, end_at) for start_at, end_at, _ in labeled_busy)
            plan = self._scheduler.plan_week(
                week_start, now=now, busy=busy, labeled_busy=labeled_busy, fixed_bjj=fixed_bjj,
                existing=tuple(self._existing(row) for row in retained),
                fatigue=self._latest_fatigue(session, now),
                weather=self._weather_hints(),
                declined_bjj=self._declined_dates(planner_settings, week_start),
            )
        return [
            {
                "date": item.day.isoformat(),
                "suggested_type": item.suggested_type.value,
                "reason": item.reason,
                "preferred_clock": item.preferred_clock.strftime("%H:%M") if item.preferred_clock else None,
            }
            for item in plan.candidates
        ]

    def _skip_past_due(self, rows: list[TrainingSession], now: datetime) -> None:
        for row in rows:
            if row.status != SessionStatus.PLANNED.value or row.is_all_day:
                continue
            if row.planned_type in {WorkoutType.REST.value, WorkoutType.RECOVERY.value, WorkoutType.COMPETITION.value}:
                continue
            if self._as_utc(row.end_at) > now:
                continue
            row.status = SessionStatus.SKIPPED.value
            if not row.notes:
                row.notes = "Missed. Remaining week replanned from completed training."
            row.revision += 1
            row.updated_at = now

    def _cancel_displaced(
        self, session, rows: list[TrainingSession], displaced_ids: set[str], now: datetime, reason: str,
    ) -> None:
        for row in rows:
            if row.id not in displaced_ids:
                continue
            row.status = SessionStatus.CANCELLED.value
            row.notes = f"Displaced by {reason}; lower-priority work was replanned from the remaining week."
            row.revision += 1
            row.updated_at = now
            for reminder in session.scalars(select(TrainingReminder).where(TrainingReminder.session_id == row.id)):
                if reminder.status == "pending":
                    reminder.status = "cancelled"

    def _retained(self, row: TrainingSession, now: datetime) -> bool:
        start = self._as_utc(row.start_at)
        end = self._as_utc(row.end_at)
        created = self._as_utc(row.created_at)
        # A scheduler row first created after its slot had already ended is a
        # stale bootstrap artifact, not a workout the athlete skipped.
        if row.source == "scheduler" and row.status == SessionStatus.PLANNED.value and created >= end:
            return False
        if start.astimezone(self._timezone).date() == now.astimezone(self._timezone).date():
            return True
        return (
            row.pinned or row.source == "manual" or start <= now
            or row.status in {SessionStatus.COMPLETED.value, SessionStatus.PARTIAL.value, SessionStatus.IN_PROGRESS.value, SessionStatus.SKIPPED.value}
        )

    def _existing(self, row: TrainingSession) -> ExistingSession:
        return ExistingSession(
            row.id, WorkoutType(row.planned_type), self._as_utc(row.start_at).astimezone(self._timezone),
            self._as_utc(row.end_at).astimezone(self._timezone), SessionStatus(row.status), row.pinned,
            row.source_calendar_event_id,
            WorkoutType(row.original_planned_type) if row.original_planned_type else None,
            row.source or "scheduler",
        )

    def _apply_plan(self, row: TrainingSession, item, now: datetime) -> bool:
        values = {
            "planned_type": item.type.value, "status": SessionStatus.PLANNED.value,
            "phase": item.phase.value, "start_at": item.start_at.astimezone(UTC), "end_at": item.end_at.astimezone(UTC),
            "planned_week_start": item.local_date - timedelta(days=item.local_date.weekday()),
            "is_all_day": item.is_all_day, "estimated_minutes": round((item.end_at - item.start_at).total_seconds() / 60),
            "intensity": item.intensity, "reason": item.reason, "coach_focus": list(item.coach_focus),
            "preparation": item.preparation, "target_rounds": item.target_rounds,
            "round_length_seconds": item.round_length_seconds, "rest_seconds": item.rest_seconds,
            "source": item.source, "pinned": item.pinned, "source_calendar_event_id": item.source_calendar_event_id,
        }
        changed = any(
            self._as_utc(getattr(row, key)) != value
            if key in {"start_at", "end_at"} and getattr(row, key, None) is not None
            else getattr(row, key, None) != value
            for key, value in values.items()
        )
        for key, value in values.items():
            setattr(row, key, value)
        row.updated_at = now
        return changed

    @staticmethod
    def _replace_exercises(session, session_id: str, exercises) -> None:
        session.execute(delete(TrainingExercise).where(TrainingExercise.session_id == session_id))
        for position, item in enumerate(exercises):
            session.add(TrainingExercise(
                session_id=session_id, position=position, name=item.name, load_value=item.load_value,
                load_unit=item.load_unit, sets=item.sets, reps=item.reps,
                duration_seconds=item.duration_seconds, notes=item.notes,
            ))

    def _ensure_reminders(self, session, row: TrainingSession, planner_settings, now: datetime) -> None:
        for reminder in session.scalars(select(TrainingReminder).where(TrainingReminder.session_id == row.id)):
            if reminder.session_revision != row.revision and reminder.status == "pending":
                reminder.status = "cancelled"
        if row.is_all_day or row.status != SessionStatus.PLANNED.value or self._as_utc(row.end_at) <= now:
            return
        pre_minutes = planner_settings.pre_reminder_minutes if planner_settings else 60
        post_minutes = planner_settings.post_check_minutes if planner_settings else 30
        for kind, scheduled in (("pre_workout", row.start_at - timedelta(minutes=pre_minutes)), ("post_workout", row.end_at + timedelta(minutes=post_minutes))):
            dedupe = f"training:{kind}:{row.id}:r{row.revision}"
            existing = session.scalar(select(TrainingReminder).where(TrainingReminder.dedupe_key == dedupe))
            if existing is None:
                session.add(TrainingReminder(
                    session_id=row.id, kind=kind, session_revision=row.revision,
                    scheduled_for=scheduled, status="pending", dedupe_key=dedupe,
                ))

    def _session_dict(self, row: TrainingSession, exercises: list[dict]) -> dict:
        return {
            "id": row.id, "planned_type": row.planned_type, "actual_type": row.actual_type,
            "original_planned_type": row.original_planned_type,
            "title": self._title(row.planned_type), "status": row.status, "phase": row.phase,
            "start_at": self._as_utc(row.start_at).isoformat(), "end_at": self._as_utc(row.end_at).isoformat(),
            "is_all_day": row.is_all_day, "estimated_minutes": row.estimated_minutes,
            "intensity": row.intensity, "reason": row.reason, "coach_focus": row.coach_focus or [],
            "preparation": row.preparation, "target_rounds": row.target_rounds,
            "round_length_seconds": row.round_length_seconds, "rest_seconds": row.rest_seconds,
            "revision": row.revision, "exercises": exercises, "session_rpe": row.session_rpe,
            "final_round_quality": row.final_round_quality, "notes": row.notes,
            "calendar_event_id": row.apple_event_id or row.source_calendar_event_id,
        }

    @staticmethod
    def _exercise_dict(item: TrainingExercise) -> dict:
        return {
            "name": item.name,
            "load_value": item.load_value,
            "load_unit": item.load_unit,
            "sets": item.sets,
            "reps": item.reps,
            "duration_seconds": item.duration_seconds,
            "notes": item.notes,
            "done": bool(getattr(item, "done", False)),
        }

    @staticmethod
    def _metric_dict(item: TrainingMetric) -> dict:
        return {"metric_type": item.metric_type, "sequence": item.sequence, "value": item.value, "unit": item.unit, "recorded_at": item.recorded_at.isoformat()}

    @staticmethod
    def _title(workout_type: str) -> str:
        return {
            "bjj_technical": "BJJ Technical", "bjj_normal": "BJJ Normal", "bjj_hard": "BJJ Competition / Hard",
            "strength_a": "Gym (Strength A)", "strength_b": "Gym (Strength B)", "zone_2": "Zone 2",
            "grip": "Grip", "recovery": "Recovery Day", "rest": "Rest", "competition": "Gi BJJ Competition",
        }.get(workout_type, workout_type.replace("_", " ").title())

    def _local_date(self, value: str) -> date:
        return datetime.fromisoformat(value).astimezone(self._timezone).date()

    @staticmethod
    def _compliance(week: list[dict], phase) -> dict:
        completed = {key: 0 for key in ("bjj", "strength", "zone_2", "intervals", "grip", "rest")}
        for item in week:
            if item["status"] not in {"completed", "partial", "recovery", "competition"}:
                continue
            workout_type = item["planned_type"]
            if workout_type.startswith("bjj_"):
                completed["bjj"] += 1
            elif workout_type.startswith("strength_"):
                completed["strength"] += 1
                completed["intervals"] += workout_type == "strength_a"
            elif workout_type == "zone_2":
                completed["zone_2"] += 1
            elif workout_type in {"rest", "recovery"}:
                completed["rest"] += 1
            completed["grip"] += any(exercise["name"] == "Towel kettlebell hold" for exercise in item["exercises"])
        bjj_count = sum(item["planned_type"].startswith("bjj_") for item in week if item["status"] not in {"skipped", "cancelled"})
        targets = weekly_targets(phase, bjj_count=bjj_count)
        return {key: {"completed": completed[key], "target": targets[key]} for key in targets}

    def _week_quality(self, week: list[dict], candidates: list[dict]) -> str:
        active = [item for item in week if item["status"] not in {"skipped", "cancelled"}]
        return assess_week_quality(
            bjj=sum(item["planned_type"].startswith("bjj_") for item in active) + len(candidates),
            hard_bjj=any(item["planned_type"] == "bjj_hard" for item in active) or any(
                item.get("suggested_type") == "bjj_hard" for item in candidates
            ),
            strength=sum(item["planned_type"].startswith("strength_") for item in active),
            zone_2=sum(item["planned_type"] == "zone_2" for item in active),
            intervals=sum(item["planned_type"] == "strength_a" for item in active),
            rest=any(item["planned_type"] in {"rest", "recovery"} for item in active),
        ).value

    def _tomorrow_prescription(
        self, session: dict | None, week: list[dict], phase, *,
        tomorrow: date | None = None, candidates: list[dict] | None = None,
    ) -> dict:
        candidate = next(
            (
                item for item in (candidates or [])
                if tomorrow and item.get("date") == tomorrow.isoformat()
            ),
            None,
        )
        if session is None and candidate is not None:
            status = self._status_after(week, {
                "planned_type": candidate.get("suggested_type"),
                "status": "planned",
                "exercises": [],
            }, phase)
            clock = candidate.get("preferred_clock")
            return {
                "session": candidate.get("suggested_type") or "bjj_normal",
                "time": clock,
                "work": "Confirm this BJJ class. It is the replacement for a missed or open mat window.",
                "focus": "Show up ready",
                "why": candidate.get("reason") or "BJJ has priority over gym quotas.",
                "weekly_status": status,
                "candidate": True,
            }
        status = self._status_after(week, session, phase)
        if session is None:
            return {
                "session": "rest",
                "time": None,
                "work": "No training is prescribed.",
                "focus": "Protect recovery",
                "why": "An empty slot is not an invitation to add fatigue.",
                "weekly_status": status,
            }
        start = session.get("start_at")
        clock = None
        if start and not session.get("is_all_day"):
            clock = datetime.fromisoformat(start).astimezone(self._timezone).strftime("%H:%M")
        focus = (session.get("coach_focus") or ["Show up ready"])[0]
        why = str(session.get("reason") or "Selected because it best protects the next tournament.").split(".")[0] + "."
        return {
            "session": session.get("planned_type") or "rest",
            "time": clock,
            "work": self._work_text(session),
            "focus": str(focus).split(".")[0],
            "why": why,
            "weekly_status": status,
        }

    def _status_after(self, week: list[dict], session: dict | None, phase) -> dict:
        counts = self._compliance(week, phase)
        if session and session.get("status") == "planned":
            kind = session.get("planned_type") or ""
            key = None
            if kind.startswith("bjj_"):
                key = "bjj"
            elif kind.startswith("strength_"):
                key = "strength"
            elif kind == "zone_2":
                key = "zone_2"
            elif kind in {"rest", "recovery"}:
                key = "rest"
            if key:
                counts[key] = {**counts[key], "completed": counts[key]["completed"] + 1}
            if kind == "strength_a":
                counts["intervals"] = {**counts["intervals"], "completed": counts["intervals"]["completed"] + 1}
            if any(exercise.get("name") == "Towel kettlebell hold" for exercise in session.get("exercises") or []):
                counts["grip"] = {**counts["grip"], "completed": counts["grip"]["completed"] + 1}
        return counts

    @staticmethod
    def _work_text(session: dict) -> str:
        if str(session.get("planned_type", "")).startswith("bjj_") and session.get("target_rounds"):
            rest = int((session.get("rest_seconds") or 120) / 60)
            return f"{session['target_rounds']} × 5-minute rounds, about {rest} minutes rest."
        if session.get("planned_type") in {"rest", "recovery"}:
            return "Complete rest. Do not add training."
        parts: list[str] = []
        for item in session.get("exercises") or []:
            detail: list[str] = []
            if item.get("load_value") is not None:
                detail.append(f"{item['load_value']} {item.get('load_unit') or ''}".strip())
            if item.get("sets") is not None:
                reps = item.get("reps") or ""
                detail.append(f"{item['sets']}×{reps}".rstrip("×"))
            if item.get("duration_seconds"):
                detail.append(f"{int(item['duration_seconds'] / 60)} min")
            parts.append(item["name"] + (f" — {' '.join(detail)}" if detail else ""))
        return "; ".join(parts) if parts else (session.get("title") or "Open")

    def _trends(self, sessions, metrics, wellbeing, local_day: date) -> dict:
        weights = [row.weight_kg for row in wellbeing if row.weight_kg is not None and row.local_date >= local_day - timedelta(days=6)]
        by_session: dict[str, list[TrainingMetric]] = {}
        actual_rounds: dict[str, int] = {}
        for item in metrics:
            if item.metric_type in {"bike_watts", "bike_rpm", "bike_distance", "bike_calories"}:
                by_session.setdefault(item.session_id, []).append(item)
            elif item.metric_type == "bjj_rounds":
                actual_rounds[item.session_id] = int(item.value)
        decay = []
        for session_id, values in by_session.items():
            ordered = sorted((item for item in values if item.sequence is not None), key=lambda item: item.sequence or 0)
            if len(ordered) >= 2 and ordered[0].value:
                decay.append({"session_id": session_id, "decay_percent": round((ordered[0].value - ordered[-1].value) / ordered[0].value * 100, 1)})
        bjj = [
            {
                "date": self._as_utc(row.start_at).astimezone(self._timezone).date().isoformat(),
                "rounds": actual_rounds.get(row.id, row.target_rounds or 0),
                "final_quality": row.final_round_quality,
            }
            for row in sessions if row.planned_type.startswith("bjj_") and row.status in {"completed", "partial"}
        ]
        return {"bike_decay": decay[-8:], "bjj_capacity": bjj[-8:], "weight_7d_average": round(sum(weights) / len(weights), 1) if weights else None}

    @staticmethod
    def _readiness_dict(row: DailyWellbeingCheckIn | None) -> dict | None:
        if row is None:
            return None
        assessment = assess_readiness(ReadinessInput(
            sleep_hours=row.sleep_hours, sleep_quality=row.sleep_quality, fatigue=row.fatigue,
            soreness=row.soreness, grip_fatigue=row.grip_fatigue, pain=row.pain, readiness=row.readiness,
        ))
        return {
            "date": row.local_date.isoformat(),
            "level": assessment.level.value,
            "fatigue_state": getattr(row, "fatigue_state", None) or FatigueState.NORMAL.value,
            "alerts": list(assessment.alerts),
            "sleep_hours": row.sleep_hours,
            "sleep_quality": row.sleep_quality,
            "fatigue": row.fatigue,
            "soreness": row.soreness,
            "grip_fatigue": row.grip_fatigue,
            "pain": row.pain,
            "pain_notes": row.pain_notes,
            "motivation": row.readiness,
            "weight_kg": row.weight_kg,
        }

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
