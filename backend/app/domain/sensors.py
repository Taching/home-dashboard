import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import SensorReading
from app.database.session import SessionLocal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reading:
    recorded_at: datetime
    temperature_c: float
    humidity_percent: float


class SHT31Sensor:
    """Lazy I2C adapter so development machines can run without Pi hardware."""

    def __init__(self) -> None:
        self._sensor = None

    def read(self) -> Reading:
        if self._sensor is None:
            import adafruit_sht31d
            import board

            self._sensor = adafruit_sht31d.SHT31D(
                board.I2C(), address=settings.sensor_i2c_address
            )

        return Reading(
            recorded_at=datetime.now(UTC),
            temperature_c=round(float(self._sensor.temperature), 1),
            humidity_percent=round(float(self._sensor.relative_humidity), 1),
        )


class SensorService:
    def __init__(self, sensor: SHT31Sensor | None = None) -> None:
        self._sensor = sensor or SHT31Sensor()
        self._latest: Reading | None = None
        self._status = "pending"
        self._error: str | None = None
        self._lock = Lock()

    def restore_latest(self) -> None:
        with SessionLocal() as session:
            row = session.scalar(
                select(SensorReading).order_by(SensorReading.recorded_at.desc()).limit(1)
            )
        if row is None:
            return
        self._set_latest(
            Reading(row.recorded_at, row.temperature_c, row.humidity_percent), "ready"
        )

    def poll(self) -> Reading | None:
        if not settings.sensor_enabled:
            self._set_status("disabled", None)
            return None

        try:
            reading = self._sensor.read()
            with SessionLocal.begin() as session:
                session.add(
                    SensorReading(
                        recorded_at=reading.recorded_at,
                        temperature_c=reading.temperature_c,
                        humidity_percent=reading.humidity_percent,
                    )
                )
            self._set_latest(reading, "ready")
            return reading
        except Exception as error:  # Hardware failures must not stop the API.
            logger.warning("SHT31 read failed: %s", error)
            self._set_status("unavailable", type(error).__name__)
            return None

    def current(self) -> Reading | None:
        with self._lock:
            return self._latest

    def status(self) -> str:
        with self._lock:
            return self._status

    def history(self, hours: int = 24) -> list[Reading]:
        start = datetime.now(UTC) - timedelta(hours=hours)
        with SessionLocal() as session:
            rows = session.scalars(
                select(SensorReading)
                .where(SensorReading.recorded_at >= start)
                .order_by(SensorReading.recorded_at)
            ).all()
        return [Reading(row.recorded_at, row.temperature_c, row.humidity_percent) for row in rows]

    def _set_latest(self, reading: Reading, status: str) -> None:
        with self._lock:
            self._latest = reading
            self._status = status
            self._error = None

    def _set_status(self, status: str, error: str | None) -> None:
        with self._lock:
            self._status = status
            self._error = error
