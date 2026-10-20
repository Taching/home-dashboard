"""Tests for deterministic weekly analyzer (spec sections 10–12, 19–20)."""

from __future__ import annotations

import tempfile
import unittest
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database.models import (
    BjjFailureType,
    BjjSessionAnalysis,
    BjjSessionFailure,
    DailyWellbeingCheckIn,
    TrainingSession,
    TrainingSessionExerciseLog,
    TrainingSessionResult,
    TrainingWeeklyAnalysis,
)
from app.database.session import Base
from app.domain.exercise_library import BJJ_FAILURE_SEED
from app.domain.weekly_analyzer import WeeklyAnalyzerService
from app.domain.weekly_coach import ask_coach, validate_coach_report


TZ = ZoneInfo("Asia/Tokyo")


class WeeklyAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self._tmpdir.name) / "test.db"
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=engine)
        self.Session = sessionmaker(bind=engine, expire_on_commit=False)
        with self.Session() as session:
            for failure in BJJ_FAILURE_SEED:
                session.add(BjjFailureType(
                    code=failure.code,
                    label=failure.label,
                    description=failure.description,
                ))
            session.commit()
        self.service = WeeklyAnalyzerService(session_factory=self.Session, timezone_name="Asia/Tokyo")
        # Monday of a fixed test week (2026-10-12 is a Monday)
        self.week_start = date(2026, 10, 12)
        self.week_end = date(2026, 10, 18)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _add_session(
        self,
        *,
        day: date,
        planned_type: str,
        status: str = "completed",
        requires_travel: bool = False,
        cancellation_reason: str | None = None,
        deload: bool = False,
        bjj_rounds: int | None = None,
    ) -> str:
        session_id = str(uuid4())
        start = datetime.combine(day, time(19, 0), TZ).astimezone(UTC)
        with self.Session() as session:
            session.add(TrainingSession(
                id=session_id,
                planned_type=planned_type,
                status=status,
                phase="general",
                planned_week_start=self.week_start,
                start_at=start,
                end_at=start + timedelta(hours=1),
                is_all_day=False,
                estimated_minutes=60,
                intensity="normal",
                reason="test",
                coach_focus=[],
                source="test",
                requires_travel=requires_travel,
                cancellation_reason=cancellation_reason,
                deload=deload,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ))
            if bjj_rounds is not None or status in {"completed", "partial", "skipped"}:
                session.add(TrainingSessionResult(
                    session_id=session_id,
                    status=status,
                    bjj_rounds=bjj_rounds,
                    updated_at=datetime.now(UTC),
                ))
            session.commit()
        return session_id

    def _add_exercise_log(
        self,
        session_id: str,
        *,
        name: str,
        sort_order: int = 0,
        load_kg: float | None = 100,
        reps: list[int] | None = None,
        rpe: float | None = 8,
        slug: str | None = None,
        status: str = "completed",
        planned_sets: int = 3,
    ) -> None:
        with self.Session() as session:
            session.add(TrainingSessionExerciseLog(
                id=str(uuid4()),
                training_session_id=session_id,
                sort_order=sort_order,
                planned_exercise_name=name,
                performed_exercise_name=name,
                planned_exercise_slug=slug,
                performed_exercise_slug=slug,
                planned_sets=planned_sets,
                reps_per_set=reps or [5, 5, 5],
                load_kg=load_kg,
                rpe=rpe,
                technique_quality="good",
                pain_flag=False,
                status=status,
                created_at=datetime.now(UTC),
            ))
            session.commit()

    def test_recompute_is_idempotent(self) -> None:
        self._add_session(day=self.week_start, planned_type="strength_a")
        first = self.service.recompute(self.week_start)
        second = self.service.recompute(self.week_start)
        self.assertEqual(first["id"], second["id"])
        with self.Session() as session:
            count = len(list(session.scalars(select(TrainingWeeklyAnalysis)).all()))
        self.assertEqual(count, 1)

    def test_execution_failure_scenario(self) -> None:
        # Spec scenario 1: half strength + 1 of 3 BJJ → execution, not program rewrite
        sid = self._add_session(day=self.week_start, planned_type="strength_a", status="partial")
        self._add_exercise_log(sid, name="Trap-bar Deadlift", sort_order=0, status="completed", slug="trap-bar-deadlift")
        self._add_exercise_log(sid, name="Dumbbell Bench Press", sort_order=1, status="skipped", slug="dumbbell-bench-press")
        self._add_exercise_log(sid, name="Bulgarian Split Squat", sort_order=2, status="skipped", slug="bulgarian-split-squat")
        self._add_exercise_log(sid, name="Cable Row", sort_order=3, status="skipped", slug="seated-cable-row")
        self._add_session(day=self.week_start + timedelta(days=1), planned_type="bjj_normal", status="completed", requires_travel=True, bjj_rounds=4)
        self._add_session(day=self.week_start + timedelta(days=3), planned_type="bjj_normal", status="skipped", requires_travel=True)
        self._add_session(day=self.week_start + timedelta(days=5), planned_type="bjj_hard", status="skipped", requires_travel=True)

        payload = self.service.recompute(self.week_start)
        report = payload["deterministic_report"]
        self.assertEqual(report["main_bottleneck"]["cause_code"], "execution")
        self.assertTrue(report["main_bottleneck"]["evidence_keys"])
        self.assertNotEqual(report["main_bottleneck"]["cause_code"], "possible_program_issue")

    def test_rain_blocked_not_execution(self) -> None:
        # Spec scenario 14
        self._add_session(
            day=self.week_start, planned_type="bjj_normal", status="skipped",
            requires_travel=True, cancellation_reason="weather_blocked",
        )
        self._add_session(
            day=self.week_start + timedelta(days=2), planned_type="bjj_normal",
            status="completed", requires_travel=True, bjj_rounds=5,
        )
        self._add_session(
            day=self.week_start + timedelta(days=4), planned_type="bjj_hard",
            status="completed", requires_travel=True, bjj_rounds=4,
        )
        payload = self.service.recompute(self.week_start)
        facts = payload["facts"]
        self.assertTrue(facts["adherence"]["has_weather_blocks"])
        self.assertEqual(facts["adherence"]["targets"]["bjj"]["weather_blocked"], 1)
        self.assertEqual(facts["adherence"]["targets"]["bjj"]["completed"], 2)
        codes = [item["cause_code"] for item in payload["deterministic_report"]["rule_findings"]]
        self.assertIn("weather_constraint", codes)
        # Controllable adherence should be high (2/2 non-weather)
        self.assertGreaterEqual(facts["adherence"]["controllable_adherence_pct"], 99)

    def test_technical_recurrence(self) -> None:
        # Spec scenario 3: frame_late in 3 sessions
        ids = []
        for offset in (0, 2, 4):
            sid = self._add_session(
                day=self.week_start + timedelta(days=offset),
                planned_type="bjj_normal",
                status="completed",
                requires_travel=True,
                bjj_rounds=4,
            )
            ids.append(sid)
            with self.Session() as session:
                session.add(BjjSessionAnalysis(
                    training_session_id=sid,
                    main_focus="half guard",
                    problem_position="bottom half guard",
                    updated_at=datetime.now(UTC),
                ))
                session.add(BjjSessionFailure(
                    training_session_id=sid,
                    failure_code="frame_late",
                    is_primary=True,
                ))
                session.commit()

        payload = self.service.recompute(self.week_start)
        recurring = payload["facts"]["bjj"]["recurring_problems"]
        self.assertTrue(any(item["code"] == "frame_late" for item in recurring))
        codes = [item["cause_code"] for item in payload["deterministic_report"]["rule_findings"]]
        self.assertIn("technical_recurrence", codes)
        self.assertIsNotNone(payload["deterministic_report"]["recurring_problem"])

    def test_one_poor_exposure_is_not_plateau(self) -> None:
        # Spec scenario 4
        sid = self._add_session(day=self.week_start, planned_type="strength_a")
        self._add_exercise_log(
            sid, name="Trap-bar Deadlift", load_kg=130, reps=[3, 3, 2],
            slug="trap-bar-deadlift", rpe=9,
        )
        payload = self.service.recompute(self.week_start)
        codes = [item["cause_code"] for item in payload["deterministic_report"]["rule_findings"]]
        self.assertNotIn("possible_program_issue", codes)

    def test_e1rm_same_slug_only(self) -> None:
        sid = self._add_session(day=self.week_start, planned_type="strength_a")
        self._add_exercise_log(
            sid, name="Trap-bar Deadlift", load_kg=130, reps=[4, 4, 4],
            slug="trap-bar-deadlift",
        )
        payload = self.service.recompute(self.week_start)
        strength = payload["facts"]["strength"]["exercises"]
        self.assertIn("trap-bar-deadlift", strength)
        best = strength["trap-bar-deadlift"]["weekly_best_e1rm"]
        # 130 * (1 + 4/30) = 130 * 1.1333...
        self.assertAlmostEqual(best, 130 * (1 + 4 / 30), places=1)

    def test_optional_cardio_does_not_reduce_adherence(self) -> None:
        sid = self._add_session(day=self.week_start, planned_type="strength_a")
        self._add_exercise_log(sid, name="Trap-bar Deadlift", sort_order=0, slug="trap-bar-deadlift")
        self._add_exercise_log(sid, name="Easy cardio", sort_order=1, status="skipped", load_kg=None, reps=[])
        payload = self.service.recompute(self.week_start)
        adherence = payload["facts"]["adherence"]
        self.assertEqual(adherence["prescribed_exercises"], 1)
        self.assertEqual(adherence["completed_or_partial_exercises"], 1)

    def test_low_confidence_insufficient_data(self) -> None:
        # Marked completed with no compact logs → low confidence strength conclusions
        self._add_session(day=self.week_start, planned_type="strength_a", status="completed")
        self._add_session(
            day=self.week_start + timedelta(days=1),
            planned_type="bjj_normal",
            status="completed",
            requires_travel=True,
            bjj_rounds=3,
        )
        payload = self.service.recompute(self.week_start)
        # May be medium or low depending on coverage; claims must still have evidence
        report = payload["deterministic_report"]
        self.assertTrue(report["main_bottleneck"]["evidence_keys"])
        if payload["data_confidence"] == "low":
            codes = [item["cause_code"] for item in report["rule_findings"]]
            self.assertIn("insufficient_data", codes)

    def test_recovery_context(self) -> None:
        self._add_session(day=self.week_start, planned_type="strength_a")
        self._add_session(
            day=self.week_start + timedelta(days=1),
            planned_type="bjj_normal",
            status="completed",
            requires_travel=True,
            bjj_rounds=4,
        )
        with self.Session() as session:
            for offset in range(5):
                session.add(DailyWellbeingCheckIn(
                    local_date=self.week_start + timedelta(days=offset),
                    sleep_hours=5.5,
                    fatigue_state="very fatigued",
                    updated_at=datetime.now(UTC),
                    source="test",
                ))
            session.commit()
        payload = self.service.recompute(self.week_start)
        codes = [item["cause_code"] for item in payload["deterministic_report"]["rule_findings"]]
        self.assertIn("recovery", codes)

    def test_schedule_change_prefill_present(self) -> None:
        self._add_session(day=self.week_start, planned_type="strength_a", status="skipped")
        payload = self.service.recompute(self.week_start)
        self.assertIn("From weekly review", payload.get("schedule_change_prefill") or "")

    def test_rejects_non_monday(self) -> None:
        with self.assertRaises(ValueError):
            self.service.recompute(date(2026, 10, 13))  # Tuesday

    def test_ask_coach_dry_run(self) -> None:
        self._add_session(day=self.week_start, planned_type="strength_a")
        analysis = self.service.recompute(self.week_start)
        report, status = ask_coach(analysis)
        self.assertEqual(status, "dry_run")
        self.assertIsNotNone(report)
        assert report is not None
        validate_coach_report({k: v for k, v in report.items() if k not in {"dry_run", "prompt_version"}})
        saved = self.service.save_coach_report(self.week_start, report, model_name="dry-run:test")
        self.assertIsNotNone(saved["coach_report"])

    def test_validate_coach_rejects_bad_cause(self) -> None:
        with self.assertRaises(ValueError):
            validate_coach_report({
                "verdict": "x",
                "confidence": "high",
                "main_bottleneck": {"cause_code": "laziness", "statement": "x", "evidence_keys": ["a"]},
                "improved": [],
                "regressed": [],
                "recurring_problem": None,
                "next_week_actions": [],
                "tests": [],
                "missing_data": [],
            })

    def test_at_most_three_actions_and_tests(self) -> None:
        with self.assertRaises(ValueError):
            validate_coach_report({
                "verdict": "x",
                "confidence": "high",
                "main_bottleneck": {
                    "cause_code": "execution",
                    "statement": "x",
                    "evidence_keys": ["adherence.session_adherence"],
                },
                "improved": [],
                "regressed": [],
                "recurring_problem": None,
                "next_week_actions": [
                    {"area": "a", "action": "1", "reason": "r", "requires_user_approval": False},
                    {"area": "a", "action": "2", "reason": "r", "requires_user_approval": False},
                    {"area": "a", "action": "3", "reason": "r", "requires_user_approval": False},
                    {"area": "a", "action": "4", "reason": "r", "requires_user_approval": False},
                ],
                "tests": [],
                "missing_data": [],
            })


if __name__ == "__main__":
    unittest.main()
