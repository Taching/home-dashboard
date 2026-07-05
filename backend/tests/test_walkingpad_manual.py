import unittest

from app.domain.walkingpad_manual import parse_manual_walk_message


class WalkingPadManualParseTests(unittest.TestCase):
    def test_parses_minutes_and_distance(self) -> None:
        parsed = parse_manual_walk_message("I walked 30 min and 2 km today")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.duration_minutes, 30.0)
        self.assertEqual(parsed.distance_km, 2.0)

    def test_parses_compact_units(self) -> None:
        parsed = parse_manual_walk_message("walk today 45min 3.5km")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.duration_minutes, 45.0)
        self.assertEqual(parsed.distance_km, 3.5)

    def test_ignores_non_walk_messages(self) -> None:
        self.assertIsNone(parse_manual_walk_message("What's on my calendar?"))
        self.assertIsNone(parse_manual_walk_message("walk later maybe"))

    def test_parses_minutes_only(self) -> None:
        parsed = parse_manual_walk_message("I walked 20 minutes today")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.duration_minutes, 20.0)
        self.assertIsNone(parsed.distance_km)


if __name__ == "__main__":
    unittest.main()
