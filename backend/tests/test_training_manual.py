import unittest

from app.domain.training_manual import parse_training_message
from app.domain.walkingpad_manual import parse_manual_walk_message


class TrainingManualParseTests(unittest.TestCase):
    def test_parses_strength_check_in(self) -> None:
        parsed = parse_training_message("did Strength A, felt tired")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.kind, "strength_a")
        self.assertEqual(parsed.completed, "yes")
        self.assertEqual(parsed.feeling, "tired")

    def test_parses_bjj_rounds(self) -> None:
        parsed = parse_training_message("did BJJ 3x5, note: guard retention")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.kind, "bjj")
        self.assertEqual(parsed.rounds, "3x5")
        self.assertEqual(parsed.note, "guard retention")

    def test_parses_sober_no(self) -> None:
        parsed = parse_training_message("not sober, drank")
        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.kind, "sober")
        self.assertEqual(parsed.completed, "no")

    def test_walk_messages_stay_on_walkingpad_parser(self) -> None:
        text = "I walked 20 min and 1.5 km today"
        self.assertIsNotNone(parse_manual_walk_message(text))
        self.assertIsNone(parse_training_message(text))


if __name__ == "__main__":
    unittest.main()
