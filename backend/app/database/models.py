from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
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


class VoiceCommandLog(Base):
    __tablename__ = "voice_command_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    transcript: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action: Mapped[str | None] = mapped_column(String(64), nullable=True)
    interpret_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    artist: Mapped[str | None] = mapped_column(String(200), nullable=True)
    volume_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intent_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(16))
    response_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    audio_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    wake_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)


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
