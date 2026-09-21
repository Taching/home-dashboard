from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database.session import Base


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    temperature_c: Mapped[float] = mapped_column(Float)
    humidity_percent: Mapped[float] = mapped_column(Float)


class LightCommand(Base):
    __tablename__ = "light_commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32))


class WaterPumpRun(Base):
    __tablename__ = "water_pump_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(32))
    duration_seconds: Mapped[int] = mapped_column(Integer)
    result: Mapped[str] = mapped_column(String(64))


class SpotifyToken(Base):
    __tablename__ = "spotify_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    encrypted_access_token: Mapped[str] = mapped_column(String)
    encrypted_refresh_token: Mapped[str] = mapped_column(String)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class SpotifyDevice(Base):
    __tablename__ = "spotify_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    spotify_device_id: Mapped[str] = mapped_column(String, unique=True)


class CalendarBridgeSync(Base):
    __tablename__ = "calendar_bridge_syncs"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class CalendarBridgeEvent(Base):
    __tablename__ = "calendar_bridge_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), index=True)
    external_id: Mapped[str] = mapped_column(String(512), index=True)
    title: Mapped[str] = mapped_column(String(512))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    calendar_title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    managed_session_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)


class ChiliNotifyDedupe(Base):
    __tablename__ = "chili_notify_dedupe"

    dedupe_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class WalkingPadSession(Base):
    __tablename__ = "walkingpad_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    distance_km: Mapped[float] = mapped_column(Float, default=0.0)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    calories: Mapped[float] = mapped_column(Float, default=0.0)


class WalkingPadCollectorSync(Base):
    __tablename__ = "walkingpad_collector_syncs"

    source: Mapped[str] = mapped_column(String(32), primary_key=True)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TrainingLog(Base):
    __tablename__ = "training_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    completed: Mapped[str] = mapped_column(String(16))
    feeling: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rounds: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    avg_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[int | None] = mapped_column(Integer, nullable=True)
    distance_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    exercises: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String(16))


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    weight_kg: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16))


class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    week_ending: Mapped[date] = mapped_column(Date, unique=True, index=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    previous_weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    summary: Mapped[str | None] = mapped_column(String, nullable=True)
    source: Mapped[str] = mapped_column(String(16))


class DailyWellbeingCheckIn(Base):
    __tablename__ = "daily_wellbeing_checkins"

    local_date: Mapped[date] = mapped_column(Date, primary_key=True)
    trained: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    gym: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    jiujitsu: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sober: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    weight_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fatigue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    soreness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grip_fatigue: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pain: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    pain_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    readiness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fatigue_state: Mapped[str | None] = mapped_column(String(32), nullable=True)
    daily_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    advice: Mapped[str | None] = mapped_column(Text, nullable=True)
    chili_reply: Mapped[str | None] = mapped_column(Text, nullable=True)
    chili_delivery: Mapped[str | None] = mapped_column(String(32), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    source: Mapped[str] = mapped_column(String(32), default="openclaw")


class ProgressReportPublication(Base):
    __tablename__ = "progress_report_publications"

    period_key: Mapped[str] = mapped_column(String(32), primary_key=True)
    notion_page_id: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class Competition(Base):
    __tablename__ = "competitions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    discipline: Mapped[str] = mapped_column(String(32), default="Gi BJJ")
    start_date: Mapped[date] = mapped_column(Date, index=True)
    end_date: Mapped[date] = mapped_column(Date)
    taper_start: Mapped[date] = mapped_column(Date)
    recovery_days: Mapped[int] = mapped_column(Integer, default=2)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tokyo")


class TrainingPlannerSetting(Base):
    __tablename__ = "training_planner_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Tokyo")
    morning_checkin_time: Mapped[str] = mapped_column(String(5), default="06:00")
    evening_plan_time: Mapped[str] = mapped_column(String(5), default="20:00")
    preferred_training_time: Mapped[str] = mapped_column(String(5), default="07:30")
    saturday_bjj_time: Mapped[str] = mapped_column(String(5), default="10:00")
    pre_reminder_minutes: Mapped[int] = mapped_column(Integer, default=60)
    post_check_minutes: Mapped[int] = mapped_column(Integer, default=30)
    departure_buffer_minutes: Mapped[int] = mapped_column(Integer, default=30)
    calendar_name: Mapped[str] = mapped_column(String(255), default="Chili Training")
    bjj_title_keywords: Mapped[list[str]] = mapped_column(
        JSON, default=lambda: ["bjj", "jiu jitsu", "jiujitsu", "open mat"]
    )
    declined_bjj_dates: Mapped[list[str]] = mapped_column(JSON, default=list)
    last_adjustment: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    class_template: Mapped[list] = mapped_column(JSON, default=list)
    gym_id: Mapped[str] = mapped_column(String(40), default="mita")


class TrainingPreference(Base):
    __tablename__ = "training_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TrainingSession(Base):
    __tablename__ = "training_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    planned_type: Mapped[str] = mapped_column(String(40), index=True)
    actual_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    original_planned_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="planned")
    phase: Mapped[str] = mapped_column(String(32), index=True)
    planned_week_start: Mapped[date] = mapped_column(Date, index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer)
    intensity: Mapped[str] = mapped_column(String(16), default="normal")
    reason: Mapped[str] = mapped_column(Text)
    coach_focus: Mapped[list[str]] = mapped_column(JSON, default=list)
    preparation: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    round_length_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rest_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(24), default="scheduler")
    pinned: Mapped[bool] = mapped_column(Boolean, default=False)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    rescheduled_from_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("training_sessions.id"), nullable=True)
    source_calendar_event_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    apple_event_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notion_page_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    notion_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    session_rpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    final_round_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    miss_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TrainingExercise(Base):
    __tablename__ = "training_exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("training_sessions.id"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(120))
    load_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    load_unit: Mapped[str | None] = mapped_column(String(16), nullable=True)
    sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reps: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    done: Mapped[bool] = mapped_column(Boolean, default=False)


class TrainingMetric(Base):
    __tablename__ = "training_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("training_sessions.id"), index=True)
    metric_type: Mapped[str] = mapped_column(String(40), index=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True)
    value: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(20))
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TrainingReminder(Base):
    __tablename__ = "training_reminders"
    __table_args__ = (UniqueConstraint("session_id", "kind", "session_revision"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("training_sessions.id"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), index=True)
    session_revision: Mapped[int] = mapped_column(Integer, default=1)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TrainingSummaryPublication(Base):
    __tablename__ = "training_summary_publications"

    week_key: Mapped[str] = mapped_column(String(16), primary_key=True)
    notion_page_id: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class TrainingGymClosure(Base):
    __tablename__ = "training_gym_closures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, index=True)
    gym_id: Mapped[str] = mapped_column(String(40), default="mita")
    closure_type: Mapped[str] = mapped_column(String(32), default="HOLIDAY")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class TrainingUnavailability(Base):
    __tablename__ = "training_unavailability"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    local_date: Mapped[date] = mapped_column(Date, index=True, unique=True)
    reason: Mapped[str] = mapped_column(String(32), default="USER_CANCELLED")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class TrainingSessionResult(Base):
    __tablename__ = "training_session_results"

    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("training_sessions.id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(20))
    miss_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    session_rpe: Mapped[float | None] = mapped_column(Float, nullable=True)
    difficulty: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fatigue: Mapped[str | None] = mapped_column(String(16), nullable=True)
    pain: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    soreness: Mapped[str | None] = mapped_column(String(16), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    bjj_rounds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    perceived_intensity: Mapped[str | None] = mapped_column(String(24), nullable=True)
    cardio: Mapped[str | None] = mapped_column(String(24), nullable=True)
    grip_fatigue: Mapped[str | None] = mapped_column(String(16), nullable=True)
    technical_performance: Mapped[str | None] = mapped_column(String(24), nullable=True)
    recovery_activity: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TrainingExerciseResult(Base):
    __tablename__ = "training_exercise_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exercise_id: Mapped[int] = mapped_column(Integer, ForeignKey("training_exercises.id"), index=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("training_sessions.id"), index=True)
    actual_load: Mapped[float | None] = mapped_column(Float, nullable=True)
    actual_sets: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_reps: Mapped[str | None] = mapped_column(String(32), nullable=True)
    actual_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)


class TrainingWeekAdaptation(Base):
    __tablename__ = "training_week_adaptations"

    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
