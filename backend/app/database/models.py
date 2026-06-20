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
