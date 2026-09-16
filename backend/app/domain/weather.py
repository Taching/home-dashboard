from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

import httpx

from app.core.settings import settings

WeatherStatus = Literal["not_configured", "ready", "unavailable"]
WeatherIcon = Literal["sunny", "evening", "cloudy", "fog", "rain", "snow", "storm"]


@dataclass(frozen=True)
class WeatherDay:
    date: date
    label: str
    high_c: float
    low_c: float
    condition: str
    icon: WeatherIcon
    current_c: float | None = None


@dataclass(frozen=True)
class TravelDay:
    date: date
    weather_code: int = 0
    precipitation_mm: float = 0
    precipitation_probability: float = 0
    wind_kph: float | None = None
    severe_weather: bool = False

    @property
    def blocks_travel(self) -> bool:
        if self.severe_weather or self.weather_code in {95, 96, 99}:
            return True
        if self.precipitation_mm >= 10:
            return True
        if self.wind_kph is not None and self.wind_kph >= 50:
            return True
        return False


@dataclass(frozen=True)
class WeatherForecast:
    status: WeatherStatus
    location: str
    synced_at: datetime | None
    today: WeatherDay | None
    tomorrow: WeatherDay | None


def wmo_to_icon(code: int, *, is_day: bool | None) -> tuple[WeatherIcon, str]:
    if code == 0:
        if is_day is False:
            return "evening", "Clear night"
        return "sunny", "Clear"
    if code in {1, 2}:
        if is_day is False:
            return "evening", "Partly cloudy"
        return "sunny", "Mostly sunny"
    if code == 3:
        if is_day is False:
            return "evening", "Overcast"
        return "cloudy", "Overcast"
    if code in {45, 48}:
        return "fog", "Foggy"
    if code in {51, 53, 55, 56, 57}:
        return "rain", "Drizzle"
    if code in {61, 63, 65, 66, 67, 80, 81, 82}:
        return "rain", "Rain"
    if code in {71, 73, 75, 77, 85, 86}:
        return "snow", "Snow"
    if code in {95, 96, 99}:
        return "storm", "Thunderstorm"
    return "cloudy", "Cloudy"


class WeatherService:
    _cache_ttl = timedelta(minutes=20)

    def __init__(self) -> None:
        self._cached: WeatherForecast | None = None
        self._cached_travel: tuple[TravelDay, ...] = ()
        self._cached_at: datetime | None = None

    def configured(self) -> bool:
        return settings.weather_latitude is not None and settings.weather_longitude is not None

    def forecast(self) -> WeatherForecast:
        self._refresh()
        if self._cached is not None:
            return self._cached
        if not self.configured():
            return WeatherForecast("not_configured", settings.weather_location_name, None, None, None)
        return WeatherForecast("unavailable", settings.weather_location_name, None, None, None)

    def travel_conditions(self) -> tuple[TravelDay, ...]:
        self._refresh()
        return self._cached_travel

    def _refresh(self) -> None:
        if not self.configured():
            self._cached = WeatherForecast("not_configured", settings.weather_location_name, None, None, None)
            self._cached_travel = ()
            return
        now = datetime.now(UTC)
        if self._cached and self._cached_at and now - self._cached_at < self._cache_ttl:
            return
        try:
            payload = self._fetch()
            self._cached = self._parse(payload)
            self._cached_travel = self._parse_travel(payload)
            self._cached_at = now
        except httpx.HTTPError:
            if self._cached is None:
                self._cached = WeatherForecast(
                    "unavailable", settings.weather_location_name, None, None, None,
                )

    def _fetch(self) -> dict:
        assert settings.weather_latitude is not None
        assert settings.weather_longitude is not None
        params = {
            "latitude": settings.weather_latitude,
            "longitude": settings.weather_longitude,
            "current": "temperature_2m,weather_code,is_day",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max",
            "timezone": settings.timezone,
            "forecast_days": 8,
        }
        with httpx.Client(timeout=12) as client:
            response = client.get("https://api.open-meteo.com/v1/forecast", params=params)
        response.raise_for_status()
        return response.json()

    def _parse(self, payload: dict) -> WeatherForecast:
        tz = ZoneInfo(settings.timezone)
        today_local = datetime.now(tz).date()
        tomorrow_local = today_local + timedelta(days=1)
        daily = payload.get("daily", {})
        dates = [date.fromisoformat(value) for value in daily.get("time", [])]
        codes = daily.get("weather_code", [])
        highs = daily.get("temperature_2m_max", [])
        lows = daily.get("temperature_2m_min", [])

        by_date: dict[date, WeatherDay] = {}
        for index, day in enumerate(dates):
            code = int(codes[index]) if index < len(codes) else 3
            is_day = None
            icon, condition = wmo_to_icon(code, is_day=is_day)
            by_date[day] = WeatherDay(
                date=day,
                label="Today" if day == today_local else "Tomorrow" if day == tomorrow_local else day.strftime("%a"),
                high_c=float(highs[index]),
                low_c=float(lows[index]),
                condition=condition,
                icon=icon,
            )

        current = payload.get("current", {})
        today = by_date.get(today_local)
        if today and current:
            current_code = int(current.get("weather_code", 0))
            is_day = bool(current.get("is_day", 1))
            icon, condition = wmo_to_icon(current_code, is_day=is_day)
            today = WeatherDay(
                date=today.date,
                label="Today",
                high_c=today.high_c,
                low_c=today.low_c,
                condition=condition,
                icon=icon,
                current_c=float(current["temperature_2m"]) if current.get("temperature_2m") is not None else None,
            )

        return WeatherForecast(
            status="ready",
            location=settings.weather_location_name,
            synced_at=datetime.now(UTC),
            today=today,
            tomorrow=by_date.get(tomorrow_local),
        )

    def _parse_travel(self, payload: dict) -> tuple[TravelDay, ...]:
        daily = payload.get("daily", {})
        dates = [date.fromisoformat(value) for value in daily.get("time", [])]
        codes = daily.get("weather_code", [])
        rain = daily.get("precipitation_sum", [])
        chance = daily.get("precipitation_probability_max", [])
        wind = daily.get("wind_speed_10m_max", [])
        days: list[TravelDay] = []
        for index, day in enumerate(dates):
            code = int(codes[index]) if index < len(codes) else 0
            mm = float(rain[index]) if index < len(rain) and rain[index] is not None else 0.0
            probability = float(chance[index]) if index < len(chance) and chance[index] is not None else 0.0
            wind_kph = float(wind[index]) if index < len(wind) and wind[index] is not None else None
            days.append(TravelDay(
                date=day,
                weather_code=code,
                precipitation_mm=mm,
                precipitation_probability=probability,
                wind_kph=wind_kph,
                severe_weather=code in {95, 96, 99},
            ))
        return tuple(days)
