import logging
import time
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
    """SHT31 adapter that talks to the Pi's Linux I²C device directly."""

    def __init__(self) -> None:
        self._bus = None

    def read(self) -> Reading:
        if self._bus is None:
            from smbus2 import SMBus

            self._bus = SMBus(1)

        # Single shot, high-repeatability measurement without clock stretching.
        # The SHT31 needs up to 15 ms before its six-byte result is ready.
        self._bus.write_i2c_block_data(settings.sensor_i2c_address, 0x24, [0x00])
        time.sleep(0.015)
        payload = self._bus.read_i2c_block_data(settings.sensor_i2c_address, 0x00, 6)
        if not (_valid_crc(payload[:2], payload[2]) and _valid_crc(payload[3:5], payload[5])):
            raise RuntimeError("SHT31 returned a reading with an invalid CRC")

        raw_temperature = (payload[0] << 8) | payload[1]
        raw_humidity = (payload[3] << 8) | payload[4]

        return Reading(
            recorded_at=datetime.now(UTC),
            temperature_c=round(-45 + 175 * raw_temperature / 65535, 1),
            humidity_percent=round(100 * raw_humidity / 65535, 1),
        )


def _valid_crc(data: list[int], expected: int) -> bool:
    crc = 0xFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            crc = ((crc << 1) ^ 0x131) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc == expected


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
