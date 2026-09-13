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
        self.assertTrue(any("Open" in item for item in readiness["why"]))
        self.assertTrue(any("rest stays" in item for item in readiness["why"]))

    def test_places_missing_strength_b_on_open_tuesday_not_on_rest(self) -> None:
        today = date(2026, 9, 13)
        overview = {
            "week_quality": "acceptable",
            "bjj_candidates": [
                {"date": "2026-09-14", "suggested_type": "bjj_normal"},
                {"date": "2026-09-17", "suggested_type": "bjj_normal"},
                {"date": "2026-09-19", "suggested_type": "bjj_hard"},
            ],
            "week": [session("2026-09-13", "strength_a")],
            "upcoming": [
                session("2026-09-13", "strength_a"),
                session("2026-09-16", "rest"),
            ],
        }
        mutations = propose_evening_mutations(today, overview, [])
        self.assertTrue(mutations)
        self.assertEqual(mutations[0].op, "place_session")
        self.assertEqual(mutations[0].workout_type, "strength_b")
        self.assertEqual(mutations[0].date, date(2026, 9, 15))
        self.assertFalse(any(item.date == date(2026, 9, 16) for item in mutations))

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
