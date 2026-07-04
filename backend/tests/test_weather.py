import unittest

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


if __name__ == "__main__":
    unittest.main()
