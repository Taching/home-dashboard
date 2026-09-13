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
from app.domain.training.scheduler import TrainingScheduler, assess_readiness, phase_for_date
from app.domain.training.templates import WORKOUT_TEMPLATES
from app.domain.training.types import ExistingSession, FixedBjjEvent, ReadinessInput, SessionStatus, WorkoutType


class TrainingService:
    def __init__(self, session_factory=SessionLocal, *, timezone_name: str | None = None) -> None:
        self._session_factory = session_factory
        self._timezone = ZoneInfo(timezone_name or settings.timezone)
        self._scheduler = TrainingScheduler(self._timezone.key)

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
        self.reconcile(current)

    def reconcile(self, now: datetime | None = None) -> None:
        current = self._as_utc(now or datetime.now(UTC))
        local_day = current.astimezone(self._timezone).date()
        week_start = local_day - timedelta(days=local_day.weekday())
        self._reconcile_week(week_start, current)
        self._reconcile_week(week_start + timedelta(days=7), current)

    def _reconcile_week(self, week_start: date, now: datetime) -> None:
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
            busy = tuple(
                (self._as_utc(row.start_at).astimezone(self._timezone), self._as_utc(row.end_at).astimezone(self._timezone))
                for row in calendar_rows if not row.is_all_day and row.managed_session_id is None
            )
            existing = tuple(self._existing(row) for row in retained)
            readiness = self._latest_readiness(session, now)
            plan = self._scheduler.plan_week(
                week_start, now=now, busy=busy, fixed_bjj=fixed_bjj,
                existing=existing, readiness=readiness,
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
                .where(TrainingSession.start_at >= window_start)
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
        today_sessions = [item for item in serialized if self._local_date(item["start_at"]) == local_day]
        tomorrow = local_day + timedelta(days=1)
        tomorrow_sessions = [item for item in serialized if self._local_date(item["start_at"]) == tomorrow]
        current_week = [item for item in serialized if week_start <= self._local_date(item["start_at"]) < week_start + timedelta(days=7)]
        upcoming = [
            item for item in serialized
            if local_day <= self._local_date(item["start_at"]) < local_day + timedelta(days=7)
        ]
        return {
            "generated_at": current.isoformat(),
            "timezone": self._timezone.key,
            "phase": phase_for_date(local_day).value,
            "today": today_sessions[0] if today_sessions else None,
            "tomorrow": tomorrow_sessions[0] if tomorrow_sessions else None,
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
        }

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
        start = datetime.combine(local_date, time.min, self._timezone).astimezone(UTC)
        end = start + timedelta(days=1)
        with self._session_factory() as session:
            row = session.scalar(
                select(TrainingSession)
                .where(TrainingSession.start_at < end)
                .where(TrainingSession.end_at > start)
                .where(TrainingSession.status != SessionStatus.CANCELLED.value)
                .order_by(TrainingSession.start_at)
                .limit(1)
            )
            if row is None:
                return None
            exercises = list(session.scalars(
                select(TrainingExercise)
                .where(TrainingExercise.session_id == row.id)
                .order_by(TrainingExercise.position)
            ).all())
            return self._session_dict(row, [self._exercise_dict(item) for item in exercises])

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
                if item.name in done_by_name:
                    item.done = done_by_name[item.name]
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

    def _latest_readiness(self, session, now: datetime):
        local_day = now.astimezone(self._timezone).date()
        row = session.scalar(
            select(DailyWellbeingCheckIn)
            .where(DailyWellbeingCheckIn.local_date <= local_day)
            .order_by(DailyWellbeingCheckIn.local_date.desc())
            .limit(1)
        )
        if row is None:
            return assess_readiness(None)
        yesterday_start = datetime.combine(local_day - timedelta(days=1), time.min, self._timezone).astimezone(UTC)
        yesterday_end = yesterday_start + timedelta(days=1)
        prior_hard = session.scalar(
            select(TrainingSession.id)
            .where(TrainingSession.start_at >= yesterday_start)
            .where(TrainingSession.start_at < yesterday_end)
            .where(TrainingSession.planned_type.like("bjj_%"))
            .where(TrainingSession.session_rpe >= 8)
            .limit(1)
        ) is not None
        return assess_readiness(ReadinessInput(
            sleep_hours=row.sleep_hours, sleep_quality=row.sleep_quality, fatigue=row.fatigue,
            soreness=row.soreness, grip_fatigue=row.grip_fatigue, pain=row.pain,
            readiness=row.readiness, prior_hard_bjj=prior_hard,
        ))

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
            "strength_a": "Strength A + Intervals", "strength_b": "Strength B", "zone_2": "Zone 2",
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
        taper = phase.value.startswith("taper")
        targets = {"bjj": 2 if taper else 3, "strength": 1 if taper else 2, "zone_2": 1, "intervals": 0 if taper else 1, "grip": 1 if taper else 2, "rest": 2 if taper else 1}
        return {key: {"completed": completed[key], "target": targets[key]} for key in targets}

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
        return {"date": row.local_date.isoformat(), "level": assessment.level.value, "alerts": list(assessment.alerts), "sleep_hours": row.sleep_hours, "sleep_quality": row.sleep_quality, "fatigue": row.fatigue, "soreness": row.soreness, "grip_fatigue": row.grip_fatigue, "pain": row.pain, "pain_notes": row.pain_notes, "motivation": row.readiness, "weight_kg": row.weight_kg}

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
