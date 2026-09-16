import unittest
from datetime import date

from app.domain.training.coach import evening_readiness, propose_evening_mutations


def session(day: str, planned_type: str, status: str = "planned") -> dict:
    return {
        "id": f"{planned_type}-{day}",
        "planned_type": planned_type,
        "status": status,
        "title": planned_type,
        "start_at": f"{day}T05:00:00+00:00",
    }


class EveningCoachRuleTests(unittest.TestCase):
    def test_open_tuesday_and_wednesday_rest_are_legal_when_targets_are_met(self) -> None:
        today = date(2026, 9, 13)
        overview = {
            "week_quality": "good",
            "phase": "build_october",
            "countdowns": [{"id": "oct-2026", "days_remaining": 27}],
            "bjj_candidates": [
                {"date": "2026-09-14", "suggested_type": "bjj_normal"},
                {"date": "2026-09-17", "suggested_type": "bjj_normal"},
                {"date": "2026-09-19", "suggested_type": "bjj_hard"},
            ],
            "week": [session("2026-09-13", "strength_a")],
            "upcoming": [
                session("2026-09-13", "strength_a"),
                session("2026-09-16", "rest"),
                session("2026-09-18", "strength_b"),
                session("2026-09-20", "zone_2"),
            ],
        }
        mutations = propose_evening_mutations(today, overview, [])
        self.assertEqual(mutations, [])
        readiness = evening_readiness(today, overview, [])
        self.assertTrue(any("Open" in item or "rest" in item.lower() for item in readiness["why"]))

    def test_does_not_fill_missing_strength_as_a_quota(self) -> None:
        today = date(2026, 9, 13)
        overview = {
            "week_quality": "acceptable",
            "bjj_candidates": [
                {"date": "2026-09-14", "suggested_type": "bjj_normal"},
            ],
            "week": [session("2026-09-13", "strength_a")],
            "upcoming": [
                session("2026-09-13", "strength_a"),
                session("2026-09-16", "rest"),
            ],
        }
        mutations = propose_evening_mutations(today, overview, [])
        self.assertFalse(any(item.op == "place_session" for item in mutations))
        self.assertFalse(any(item.op == "rest_today" for item in mutations))

    def test_does_not_place_strength_on_replacement_bjj_tuesday(self) -> None:
        today = date(2026, 9, 14)
        overview = {
            "week_quality": "acceptable",
            "bjj_candidates": [
                {"date": "2026-09-15", "suggested_type": "bjj_normal"},
                {"date": "2026-09-17", "suggested_type": "bjj_normal"},
                {"date": "2026-09-19", "suggested_type": "bjj_hard"},
            ],
            "week": [
                session("2026-09-13", "strength_a", "completed"),
                session("2026-09-14", "bjj_normal", "skipped"),
            ],
            "upcoming": [],
        }
        mutations = propose_evening_mutations(today, overview, [])
        self.assertFalse(any(
            item.op == "place_session" and item.date == date(2026, 9, 15)
            for item in mutations
        ))
        strength = next((item for item in mutations if item.op == "place_session" and item.workout_type == "strength_b"), None)
        if strength is not None:
            self.assertNotEqual(strength.date, date(2026, 9, 15))

    def test_moves_tomorrow_gym_off_a_heavy_workday(self) -> None:
        today = date(2026, 9, 14)
        overview = {
            "week_quality": "acceptable",
            "bjj_candidates": [{"date": "2026-09-19", "suggested_type": "bjj_hard"}],
            "week": [
                session("2026-09-15", "strength_b"),
                session("2026-09-16", "rest"),
                session("2026-09-17", "zone_2"),
            ],
            "upcoming": [
                session("2026-09-15", "strength_b"),
                session("2026-09-16", "rest"),
                session("2026-09-17", "zone_2"),
            ],
        }
        meetings = [{
            "title": "Flight to Osaka",
            "start_at": __import__("datetime").datetime(2026, 9, 15, 8, 0, tzinfo=__import__("datetime").timezone.utc),
            "end_at": __import__("datetime").datetime(2026, 9, 15, 12, 0, tzinfo=__import__("datetime").timezone.utc),
            "is_all_day": False,
        }]
        mutations = propose_evening_mutations(today, overview, meetings)
        self.assertTrue(any(item.op == "move_gym" for item in mutations))
