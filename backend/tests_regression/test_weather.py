import unittest
from datetime import date

from app.domain.weather import wmo_to_icon


class WeatherIconTests(unittest.TestCase):
    def test_clear_day_is_sunny(self):
        self.assertEqual(wmo_to_icon(0, is_day=True), ("sunny", "Clear"))

    def test_clear_night_is_evening(self):
        self.assertEqual(wmo_to_icon(0, is_day=False), ("evening", "Clear night"))

    def test_rain_codes(self):
        self.assertEqual(wmo_to_icon(61, is_day=True)[0], "rain")
        self.assertEqual(wmo_to_icon(55, is_day=False)[0], "rain")

    def test_thunderstorm(self):
        self.assertEqual(wmo_to_icon(95, is_day=True)[0], "storm")

    def test_travel_blocks_storms_and_heavy_rain_not_probability(self):
        from app.domain.weather import TravelDay
        light = TravelDay(date=date(2026, 9, 16), weather_code=61, precipitation_mm=2, precipitation_probability=80)
        heavy = TravelDay(date=date(2026, 9, 16), weather_code=63, precipitation_mm=12, precipitation_probability=40)
        storm = TravelDay(date=date(2026, 9, 16), weather_code=95, precipitation_mm=1, severe_weather=True)
        self.assertFalse(light.blocks_travel)
        self.assertTrue(heavy.blocks_travel)
        self.assertTrue(storm.blocks_travel)


if __name__ == "__main__":
    unittest.main()
