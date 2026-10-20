"""Deterministic weekly training analyzer (spec sections 10–12, Milestone 3).

Builds a facts snapshot + rule-based report with no AI call. Ask coach (M4)
explains the same saved facts on demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.core.settings import settings
from app.database.models import (
    BjjSessionAnalysis,
    BjjSessionFailure,
    DailyWellbeingCheckIn,
    GarminDailySnapshot,
    TrainingSession,
    TrainingSessionExerciseLog,
    TrainingSessionResult,
    TrainingWeeklyAnalysis,
    WeeklyReview,
)
from app.database.session import SessionLocal
from app.domain.rain_handling import calculate_controllable_adherence, is_session_weather_blocked

RULE_VERSION = "v1.2"
COACH_PROMPT_VERSION = "v1.2-ruthless"

CAUSE_CODES = frozenset({
    "insufficient_data",
    "weather_constraint",
    "execution",
    "recovery",
    "specificity",
    "technical_recurrence",
    "possible_program_issue",
    "progressing_as_expected",
})

# Chili template display names → exercise library slugs (spec 7.3 / templates.py).
TEMPLATE_NAME_TO_SLUG: dict[str, str] = {
    "Trap-bar Deadlift": "trap-bar-deadlift",
    "Dumbbell Bench Press": "dumbbell-bench-press",
    "Bulgarian Split Squat": "bulgarian-split-squat",
    "Cable Row": "seated-cable-row",
    "Pallof Press": "pallof-press",
    "Cable Face Pull": "cable-face-pull",
    "Kettlebell Swing": "two-hand-kettlebell-swing",
    "Front Squat": "front-squat",
    "Military Press": "barbell-overhead-press",
    "Weighted Pull-up": "weighted-pull-up",
    "Romanian Deadlift": "romanian-deadlift",
    "Hanging Knee Raise": "hanging-knee-raise",
}

OPTIONAL_EXERCISE_NAMES = frozenset({
    "Easy cardio",
    "Stationary bike warm-up",
    "Zone 2 cardio",
})


@dataclass
class WeeklyAnalyzerService:
    """Compute and persist deterministic weekly training analysis."""

    session_factory: Any = SessionLocal
    timezone_name: str = field(default_factory=lambda: settings.timezone)

    @property
    def _tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone_name)

    def latest(self) -> dict | None:
        with self.session_factory() as session:
            row = session.scalars(
                select(TrainingWeeklyAnalysis).order_by(TrainingWeeklyAnalysis.week_start.desc())
            ).first()
            return None if row is None else self._row_payload(row)

    def get(self, week_start: date) -> dict | None:
        with self.session_factory() as session:
            row = session.scalars(
                select(TrainingWeeklyAnalysis).where(TrainingWeeklyAnalysis.week_start == week_start)
            ).first()
            return None if row is None else self._row_payload(row)

    def recompute(self, week_start: date) -> dict:
        """Idempotent recompute for Mon–Sun week starting at week_start."""
        if week_start.weekday() != 0:
            raise ValueError("week_start must be a Monday")
        week_end = week_start + timedelta(days=6)
        facts = self._build_facts(week_start, week_end)
        report = self._build_report(facts)
        now = datetime.now(UTC)
        with self.session_factory() as session:
            row = session.scalars(
                select(TrainingWeeklyAnalysis).where(TrainingWeeklyAnalysis.week_start == week_start)
            ).first()
            if row is None:
                row = TrainingWeeklyAnalysis(
                    id=str(uuid4()),
                    week_start=week_start,
                    week_end=week_end,
                    status="ready",
                    data_confidence=report["confidence"],
                    facts_snapshot=facts,
                    deterministic_report_json=report,
                    rule_version=RULE_VERSION,
                    created_at=now,
                    updated_at=now,
                )
                session.add(row)
            else:
                row.week_end = week_end
                row.status = "ready"
                row.data_confidence = report["confidence"]
                row.facts_snapshot = facts
                row.deterministic_report_json = report
                row.rule_version = RULE_VERSION
                row.updated_at = now
                # Keep prior coach output; it stays tied to older facts until Ask coach runs again.
            session.commit()
            session.refresh(row)
            return self._row_payload(row)

    def save_coach_report(
        self,
        week_start: date,
        coach_report: dict,
        *,
        model_name: str,
    ) -> dict:
        with self.session_factory() as session:
            row = session.scalars(
                select(TrainingWeeklyAnalysis).where(TrainingWeeklyAnalysis.week_start == week_start)
            ).first()
            if row is None:
                raise KeyError(week_start.isoformat())
            row.coach_report_json = coach_report
            row.coach_model_name = model_name
            row.coach_prompt_version = COACH_PROMPT_VERSION
            row.coach_generated_at = datetime.now(UTC)
            row.updated_at = datetime.now(UTC)
            session.commit()
            session.refresh(row)
            return self._row_payload(row)

    # --- facts -----------------------------------------------------------------

    def _build_facts(self, week_start: date, week_end: date) -> dict:
        window_start = datetime.combine(week_start, time.min, self._tz).astimezone(UTC)
        window_end = datetime.combine(week_end + timedelta(days=1), time.min, self._tz).astimezone(UTC)
        lookback_start = week_start - timedelta(days=21)

        with self.session_factory() as session:
            sessions = list(session.scalars(
                select(TrainingSession)
                .where(TrainingSession.start_at >= window_start)
                .where(TrainingSession.start_at < window_end)
                .where(TrainingSession.status != "cancelled")
                .order_by(TrainingSession.start_at)
            ).all())
            session_ids = [row.id for row in sessions]
            results = {
                item.session_id: item
                for item in session.scalars(select(TrainingSessionResult)).all()
                if item.session_id in session_ids
            }
            logs = list(session.scalars(
                select(TrainingSessionExerciseLog)
                .where(TrainingSessionExerciseLog.training_session_id.in_(session_ids or [""]))
                .order_by(TrainingSessionExerciseLog.sort_order)
            ).all()) if session_ids else []
            bjj_analyses = {
                item.training_session_id: item
                for item in session.scalars(
                    select(BjjSessionAnalysis).where(
                        BjjSessionAnalysis.training_session_id.in_(session_ids or [""])
                    )
                ).all()
            } if session_ids else {}
            bjj_failures = list(session.scalars(
                select(BjjSessionFailure).where(
                    BjjSessionFailure.training_session_id.in_(session_ids or [""])
                )
            ).all()) if session_ids else []

            # 4-week lookback for recurrence
            lookback_window_start = datetime.combine(lookback_start, time.min, self._tz).astimezone(UTC)
            lookback_sessions = list(session.scalars(
                select(TrainingSession)
                .where(TrainingSession.start_at >= lookback_window_start)
                .where(TrainingSession.start_at < window_end)
                .where(TrainingSession.planned_type.like("bjj_%"))
            ).all())
            lookback_ids = [row.id for row in lookback_sessions]
            lookback_failures = list(session.scalars(
                select(BjjSessionFailure).where(
                    BjjSessionFailure.training_session_id.in_(lookback_ids or [""])
                )
            ).all()) if lookback_ids else []
            lookback_analyses = {
                item.training_session_id: item
                for item in session.scalars(
                    select(BjjSessionAnalysis).where(
                        BjjSessionAnalysis.training_session_id.in_(lookback_ids or [""])
                    )
                ).all()
            } if lookback_ids else {}

            wellbeing = list(session.scalars(
                select(DailyWellbeingCheckIn)
                .where(DailyWellbeingCheckIn.local_date >= week_start)
                .where(DailyWellbeingCheckIn.local_date <= week_end)
            ).all())
            garmin = list(session.scalars(
                select(GarminDailySnapshot)
                .where(GarminDailySnapshot.local_date >= week_start)
                .where(GarminDailySnapshot.local_date <= week_end)
            ).all())
            monday_review = session.scalars(
                select(WeeklyReview).where(WeeklyReview.week_ending == week_end)
            ).first()

        session_payloads = []
        for row in sessions:
            recorded = results.get(row.id)
            session_payloads.append({
                "id": row.id,
                "planned_type": row.planned_type,
                "status": row.status,
                "miss_reason": row.miss_reason,
                "cancellation_reason": row.cancellation_reason,
                "requires_travel": bool(row.requires_travel),
                "deload": bool(row.deload),
                "start_at": row.start_at.isoformat() if row.start_at else None,
                "result": None if recorded is None else {
                    "bjj_rounds": recorded.bjj_rounds,
                    "session_rpe": recorded.session_rpe,
                    "fatigue": recorded.fatigue,
                    "soreness": recorded.soreness,
                    "pain": recorded.pain,
                },
            })

        logs_by_session: dict[str, list] = {}
        for log in logs:
            logs_by_session.setdefault(log.training_session_id, []).append(log)

        adherence = self._adherence_facts(session_payloads, logs_by_session)
        strength = self._strength_facts(logs, session_payloads)
        bjj = self._bjj_facts(
            session_payloads, results, bjj_analyses, bjj_failures,
            lookback_failures, lookback_analyses, lookback_sessions,
        )
        recovery = self._recovery_facts(wellbeing, garmin, monday_review, session_payloads)
        body_trend = self._body_trend_facts(wellbeing, monday_review)
        conditioning = self._conditioning_facts(session_payloads)

        required_present, required_total = self._data_coverage(
            adherence, strength, bjj, recovery, session_payloads, logs_by_session
        )
        confidence = self._confidence(required_present, required_total)

        return {
            "week": {
                "start": week_start.isoformat(),
                "end": week_end.isoformat(),
                "timezone": self.timezone_name,
            },
            "adherence": adherence,
            "strength": strength,
            "bjj": bjj,
            "conditioning": conditioning,
            "recovery": recovery,
            "body_trend": body_trend,
            "sessions": session_payloads,
            "data_coverage": {
                "required_present": required_present,
                "required_total": required_total,
                "ratio": round(required_present / required_total, 3) if required_total else 1.0,
            },
            "confidence": confidence,
            "rule_findings": [],  # filled by _build_report
        }

    def _adherence_facts(self, sessions: list[dict], logs_by_session: dict) -> dict:
        planned = [s for s in sessions if s["planned_type"] != "rest"]
        completed = [s for s in planned if s["status"] in {"completed", "partial"}]
        weather_blocked = [s for s in planned if is_session_weather_blocked(s)]
        controllable = calculate_controllable_adherence(
            total_sessions=len(planned),
            completed_sessions=len(completed),
            weather_blocked_sessions=len(weather_blocked),
        )

        prescribed_exercises = 0
        completed_exercises = 0
        planned_sets = 0
        completed_rep_entries = 0
        for session in planned:
            if not session["planned_type"].startswith("strength_"):
                continue
            logs = logs_by_session.get(session["id"], [])
            for log in logs:
                if log.planned_exercise_name in OPTIONAL_EXERCISE_NAMES:
                    continue
                prescribed_exercises += 1
                if log.status in {"completed", "partial"}:
                    completed_exercises += 1
                sets = log.planned_sets or 0
                planned_sets += sets
                reps = list(log.reps_per_set or [])
                completed_rep_entries += min(len(reps), sets) if sets else len(reps)

        bjj_planned = sum(1 for s in planned if s["planned_type"].startswith("bjj_") or s["planned_type"] == "competition")
        bjj_done = sum(
            1 for s in planned
            if (s["planned_type"].startswith("bjj_") or s["planned_type"] == "competition")
            and s["status"] in {"completed", "partial"}
            and not is_session_weather_blocked(s)
        )
        bjj_weather = sum(
            1 for s in weather_blocked
            if s["planned_type"].startswith("bjj_") or s["planned_type"] == "competition"
        )
        strength_planned = sum(1 for s in planned if s["planned_type"].startswith("strength_"))
        strength_done = sum(
            1 for s in planned
            if s["planned_type"].startswith("strength_") and s["status"] in {"completed", "partial"}
        )
        cardio_planned = sum(1 for s in planned if s["planned_type"] in {"zone_2", "grip"})
        cardio_done = sum(
            1 for s in planned
            if s["planned_type"] in {"zone_2", "grip"} and s["status"] in {"completed", "partial"}
        )
        rest_days = sum(1 for s in sessions if s["planned_type"] == "rest")

        session_adherence = (len(completed) / len(planned)) if planned else 1.0
        exercise_adherence = (completed_exercises / prescribed_exercises) if prescribed_exercises else None
        work_set_adherence = (completed_rep_entries / planned_sets) if planned_sets else None

        return {
            "planned_sessions": len(planned),
            "completed_or_partial_sessions": len(completed),
            "weather_blocked_sessions": len(weather_blocked),
            "session_adherence": round(session_adherence, 3),
            "exercise_adherence": None if exercise_adherence is None else round(exercise_adherence, 3),
            "work_set_adherence": None if work_set_adherence is None else round(work_set_adherence, 3),
            "prescribed_exercises": prescribed_exercises,
            "completed_or_partial_exercises": completed_exercises,
            "planned_working_sets": planned_sets,
            "completed_rep_entries": completed_rep_entries,
            "ordinary_adherence_pct": controllable["ordinary_adherence"],
            "controllable_adherence_pct": controllable["controllable_adherence"],
            "has_weather_blocks": controllable["has_weather_blocks"],
            "targets": {
                "bjj": {"planned": bjj_planned, "completed": bjj_done, "weather_blocked": bjj_weather, "target": 3},
                "strength": {"planned": strength_planned, "completed": strength_done, "target": 2},
                "easy_cardio": {"planned": cardio_planned, "completed": cardio_done, "target_min": 1, "target_max": 2},
                "rest_days": {"count": rest_days, "target_min": 1},
            },
        }

    def _strength_facts(self, logs: list, sessions: list[dict]) -> dict:
        deload_ids = {s["id"] for s in sessions if s.get("deload")}
        by_slug: dict[str, list[dict]] = {}
        for log in logs:
            if log.status == "skipped":
                continue
            slug = log.performed_exercise_slug or log.planned_exercise_slug
            if not slug:
                slug = TEMPLATE_NAME_TO_SLUG.get(log.performed_exercise_name or "")
                slug = slug or TEMPLATE_NAME_TO_SLUG.get(log.planned_exercise_name or "")
            if not slug or log.load_kg is None:
                continue
            if log.training_session_id in deload_ids:
                continue  # do not compare deload e1RM/volume to normal weeks
            reps = [int(r) for r in (log.reps_per_set or []) if isinstance(r, (int, float)) and 1 <= int(r) <= 10]
            if not reps:
                continue
            highest = max(reps)
            e1rm = float(log.load_kg) * (1 + highest / 30)
            volume = float(log.load_kg) * sum(int(r) for r in (log.reps_per_set or []) if isinstance(r, (int, float)))
            by_slug.setdefault(slug, []).append({
                "session_id": log.training_session_id,
                "load_kg": float(log.load_kg),
                "reps_per_set": list(log.reps_per_set or []),
                "highest_reps": highest,
                "estimated_1rm": round(e1rm, 2),
                "volume_load": round(volume, 2),
                "rpe": log.rpe,
                "technique_quality": log.technique_quality,
                "pain_flag": bool(log.pain_flag),
                "status": log.status,
            })

        exercises = {}
        for slug, exposures in by_slug.items():
            best = max(item["estimated_1rm"] for item in exposures)
            exercises[slug] = {
                "exposures": exposures,
                "weekly_best_e1rm": best,
                "exposure_count": len(exposures),
            }
        return {"exercises": exercises}

    def _bjj_facts(
        self,
        sessions: list[dict],
        results: dict,
        analyses: dict,
        failures: list,
        lookback_failures: list,
        lookback_analyses: dict,
        lookback_sessions: list,
    ) -> dict:
        bjj_sessions = [
            s for s in sessions
            if s["planned_type"].startswith("bjj_") or s["planned_type"] == "competition"
        ]
        completed = [s for s in bjj_sessions if s["status"] in {"completed", "partial"} and not is_session_weather_blocked(s)]
        weather_blocked = [s for s in bjj_sessions if is_session_weather_blocked(s)]
        total_rounds = 0
        for s in completed:
            recorded = results.get(s["id"])
            if recorded and recorded.bjj_rounds is not None:
                total_rounds += int(recorded.bjj_rounds)

        primary_this_week: dict[str, list[str]] = {}
        positions_this_week: dict[str, list[str]] = {}
        for failure in failures:
            if not failure.is_primary:
                continue
            primary_this_week.setdefault(failure.failure_code, []).append(failure.training_session_id)
        for analysis in analyses.values():
            if analysis.problem_position:
                positions_this_week.setdefault(analysis.problem_position, []).append(analysis.training_session_id)

        # Recurrence: same primary failure or position in ≥2 sessions this week,
        # or ≥3 distinct sessions in last 4 weeks.
        recurring = []
        for code, ids in primary_this_week.items():
            distinct = sorted(set(ids))
            if len(distinct) >= 2:
                recurring.append({
                    "kind": "failure",
                    "code": code,
                    "session_ids": distinct,
                    "window": "this_week",
                })
        for position, ids in positions_this_week.items():
            distinct = sorted(set(ids))
            if len(distinct) >= 2:
                recurring.append({
                    "kind": "position",
                    "code": position,
                    "session_ids": distinct,
                    "window": "this_week",
                })

        lookback_primary: dict[str, set[str]] = {}
        for failure in lookback_failures:
            if failure.is_primary:
                lookback_primary.setdefault(failure.failure_code, set()).add(failure.training_session_id)
        for code, ids in lookback_primary.items():
            if len(ids) >= 3 and not any(r["kind"] == "failure" and r["code"] == code for r in recurring):
                recurring.append({
                    "kind": "failure",
                    "code": code,
                    "session_ids": sorted(ids),
                    "window": "last_4_weeks",
                })

        lookback_positions: dict[str, set[str]] = {}
        for analysis in lookback_analyses.values():
            if analysis.problem_position:
                lookback_positions.setdefault(analysis.problem_position, set()).add(analysis.training_session_id)
        for position, ids in lookback_positions.items():
            if len(ids) >= 3 and not any(r["kind"] == "position" and r["code"] == position for r in recurring):
                recurring.append({
                    "kind": "position",
                    "code": position,
                    "session_ids": sorted(ids),
                    "window": "last_4_weeks",
                })

        success_rates = []
        for analysis in analyses.values():
            if analysis.success_count is not None and analysis.attempt_count:
                success_rates.append({
                    "session_id": analysis.training_session_id,
                    "focus": analysis.main_focus,
                    "success_count": analysis.success_count,
                    "attempt_count": analysis.attempt_count,
                    "rate": round(analysis.success_count / analysis.attempt_count, 3),
                })

        return {
            "planned_sessions": len(bjj_sessions),
            "completed_sessions": len(completed),
            "weather_blocked_sessions": len(weather_blocked),
            "total_rounds": total_rounds,
            "primary_failure_distribution": {
                code: len(set(ids)) for code, ids in primary_this_week.items()
            },
            "problem_positions": {
                pos: len(set(ids)) for pos, ids in positions_this_week.items()
            },
            "recurring_problems": recurring,
            "success_rates": success_rates,
            "lookback_bjj_sessions": len(lookback_sessions),
        }

    def _recovery_facts(
        self,
        wellbeing: list,
        garmin: list,
        monday_review: WeeklyReview | None,
        sessions: list[dict],
    ) -> dict:
        sleep_hours = []
        for row in wellbeing:
            if row.sleep_hours is not None:
                sleep_hours.append(float(row.sleep_hours))
        garmin_by_day = {row.local_date: row for row in garmin}
        for row in wellbeing:
            if row.sleep_hours is None and row.local_date in garmin_by_day:
                snap = garmin_by_day[row.local_date]
                if snap.sleep_seconds:
                    sleep_hours.append(snap.sleep_seconds / 3600)

        fatigue_counts = {"normal": 0, "tired": 0, "very_fatigued": 0, "pain": 0}
        for row in wellbeing:
            state = (row.fatigue_state or "").lower().replace(" ", "_")
            if state in fatigue_counts:
                fatigue_counts[state] += 1
            elif row.pain:
                fatigue_counts["pain"] += 1

        exercise_pain = sum(
            1 for s in sessions
            if (s.get("result") or {}).get("pain") is True
        )
        monday_pain = bool(monday_review and monday_review.pain_note)

        hrv = [row.hrv_last_night for row in garmin if row.hrv_last_night is not None]
        rhr = [row.resting_hr for row in garmin if row.resting_hr is not None]
        body_battery = [row.body_battery_latest for row in garmin if row.body_battery_latest is not None]
        stress = [row.stress_avg for row in garmin if row.stress_avg is not None]

        rough_nights = sum(1 for h in sleep_hours if h < 6.5)

        return {
            "average_sleep_hours": round(sum(sleep_hours) / len(sleep_hours), 2) if sleep_hours else None,
            "sleep_samples": len(sleep_hours),
            "rough_nights": rough_nights,
            "fatigue_counts": fatigue_counts,
            "exercise_pain_flags": exercise_pain,
            "monday_pain_note": monday_review.pain_note if monday_review else None,
            "has_pain_flag": exercise_pain > 0 or monday_pain,
            "garmin": {
                "hrv_avg": round(sum(hrv) / len(hrv), 1) if hrv else None,
                "resting_hr_avg": round(sum(rhr) / len(rhr), 1) if rhr else None,
                "body_battery_avg": round(sum(body_battery) / len(body_battery), 1) if body_battery else None,
                "stress_avg": round(sum(stress) / len(stress), 1) if stress else None,
                "days_with_data": len(garmin),
            },
            "monday": None if monday_review is None else {
                "energy": monday_review.energy,
                "hunger": monday_review.hunger,
                "bjj_performance": monday_review.bjj_performance,
                "waist_cm": monday_review.waist_cm,
            },
        }

    def _body_trend_facts(self, wellbeing: list, monday_review: WeeklyReview | None) -> dict:
        weights = [float(row.weight_kg) for row in wellbeing if row.weight_kg is not None]
        average = round(sum(weights) / len(weights), 2) if len(weights) >= 4 else None
        return {
            "weight_samples": len(weights),
            "seven_day_average_kg": average if average is not None else (
                monday_review.weight_kg if monday_review and monday_review.weight_kg is not None else None
            ),
            "requires_four_measurements": len(weights) < 4 and (
                monday_review is None or monday_review.weight_kg is None
            ),
            "waist_cm": monday_review.waist_cm if monday_review else None,
            "kcal_adjustment": monday_review.kcal_adjustment if monday_review else None,
            "kcal_reason": monday_review.kcal_reason if monday_review else None,
        }

    def _conditioning_facts(self, sessions: list[dict]) -> dict:
        cardio = [s for s in sessions if s["planned_type"] in {"zone_2", "grip"}]
        return {
            "planned": len(cardio),
            "completed": sum(1 for s in cardio if s["status"] in {"completed", "partial"}),
        }

    def _data_coverage(
        self,
        adherence: dict,
        strength: dict,
        bjj: dict,
        recovery: dict,
        sessions: list[dict],
        logs_by_session: dict,
    ) -> tuple[int, int]:
        """Count required fields present for the claims we can make."""
        present = 0
        total = 0

        # Session outcomes always required for adherence
        planned = [s for s in sessions if s["planned_type"] != "rest"]
        total += max(len(planned), 1)
        present += sum(1 for s in planned if s["status"] in {"completed", "partial", "skipped"})

        # Strength logs when strength was planned
        strength_sessions = [s for s in planned if s["planned_type"].startswith("strength_")]
        for s in strength_sessions:
            logs = logs_by_session.get(s["id"], [])
            total += 1
            if logs:
                present += 1
            for log in logs:
                if log.planned_exercise_name in OPTIONAL_EXERCISE_NAMES:
                    continue
                total += 2  # reps + rpe for progression claims
                if log.reps_per_set:
                    present += 1
                if log.rpe is not None:
                    present += 1

        # BJJ optional analysis — only required when claiming technical conclusions
        if bjj["completed_sessions"] > 0:
            total += bjj["completed_sessions"]
            # Count sessions that have any analysis as present for technical claims
            present += min(bjj["completed_sessions"], len(bjj["primary_failure_distribution"]) + len(bjj["problem_positions"]))

        # Sleep samples for recovery claims
        total += 3
        if recovery["average_sleep_hours"] is not None:
            present += 1
        if recovery["sleep_samples"] >= 3:
            present += 1
        if sum(recovery["fatigue_counts"].values()) > 0:
            present += 1

        return present, total

    @staticmethod
    def _confidence(present: int, total: int) -> str:
        if total <= 0:
            return "high"
        ratio = present / total
        if ratio >= 0.8:
            return "high"
        if ratio >= 0.5:
            return "medium"
        return "low"

    # --- report / diagnosis ----------------------------------------------------

    def _build_report(self, facts: dict) -> dict:
        findings = self._diagnose(facts)
        facts["rule_findings"] = findings
        confidence = facts["confidence"]
        bottleneck = findings[0] if findings else {
            "cause_code": "progressing_as_expected",
            "statement": "No blocking pattern this week.",
            "evidence_keys": ["adherence.session_adherence"],
        }

        improved = []
        regressed = []
        for slug, data in (facts.get("strength") or {}).get("exercises", {}).items():
            exposures = data.get("exposures") or []
            if len(exposures) >= 2:
                delta = exposures[-1]["estimated_1rm"] - exposures[0]["estimated_1rm"]
                key = f"strength.{slug}"
                if delta > 0:
                    improved.append({
                        "statement": f"{slug} e1RM up {delta:.1f} kg this week",
                        "evidence_keys": [key],
                    })
                elif delta < -1:
                    regressed.append({
                        "statement": f"{slug} e1RM down {abs(delta):.1f} kg this week",
                        "evidence_keys": [key],
                    })

        recurring = None
        recurring_list = (facts.get("bjj") or {}).get("recurring_problems") or []
        if recurring_list:
            item = recurring_list[0]
            recurring = {
                "statement": (
                    f"Recurring {item['kind']} `{item['code']}` across "
                    f"{len(item['session_ids'])} sessions ({item['window']})"
                ),
                "evidence_keys": [f"bjj.recurring.{item['kind']}.{item['code']}"],
            }

        missing = []
        coverage = facts.get("data_coverage") or {}
        if coverage.get("ratio", 1) < 0.8:
            missing.append("Compact strength reps/RPE and/or BJJ failure tags are incomplete.")
        if (facts.get("recovery") or {}).get("average_sleep_hours") is None:
            missing.append("Sleep hours missing for recovery conclusions.")
        if (facts.get("body_trend") or {}).get("requires_four_measurements"):
            missing.append("Fewer than 4 morning weights; 7-day average not claimed from daily logs.")

        suggestions = self._suggestions(bottleneck, facts)
        tests = self._tests(bottleneck, facts, recurring)

        summary = bottleneck["statement"]
        if facts["adherence"].get("has_weather_blocks"):
            targets = facts["adherence"]["targets"]["bjj"]
            summary = (
                f"{targets['completed']}/{targets['planned']} BJJ completed; "
                f"{targets['weather_blocked']} weather-blocked. {summary}"
            )

        return {
            "summary_line": summary,
            "confidence": confidence,
            "main_bottleneck": bottleneck,
            "improved": improved[:5],
            "regressed": regressed[:5],
            "recurring_problem": recurring,
            "progression_decisions": [],
            "next_week_suggestions": suggestions[:3],
            "tests": tests[:3],
            "missing_data": missing,
            "rule_findings": findings,
        }

    def _diagnose(self, facts: dict) -> list[dict]:
        findings: list[dict] = []
        confidence = facts["confidence"]
        adherence = facts["adherence"]
        recovery = facts["recovery"]
        bjj = facts["bjj"]
        strength = facts["strength"]

        # 1. Data sufficiency
        if confidence == "low":
            findings.append({
                "cause_code": "insufficient_data",
                "statement": "Insufficient data for strong conclusions this week.",
                "evidence_keys": ["data_coverage.ratio"],
            })

        # 2. Pain / safety
        if recovery.get("has_pain_flag"):
            findings.append({
                "cause_code": "recovery",
                "statement": "Pain was flagged; do not add intensity or volume.",
                "evidence_keys": ["recovery.has_pain_flag"],
            })

        # 3. External constraint (rain)
        if adherence.get("has_weather_blocks"):
            findings.append({
                "cause_code": "weather_constraint",
                "statement": (
                    f"{adherence['weather_blocked_sessions']} leave-home session(s) were "
                    "weather-blocked; missing live exposure remains visible but is not an execution miss."
                ),
                "evidence_keys": ["adherence.weather_blocked_sessions", "adherence.controllable_adherence_pct"],
            })

        # 4. Execution (controllable)
        controllable = adherence.get("controllable_adherence_pct")
        ordinary = adherence.get("ordinary_adherence_pct")
        exercise_adh = adherence.get("exercise_adherence")
        if controllable is not None and controllable < 70:
            findings.append({
                "cause_code": "execution",
                "statement": (
                    f"Controllable adherence was {controllable:.0f}% "
                    f"(ordinary {ordinary:.0f}%). Finish the planned work before changing the program."
                ),
                "evidence_keys": ["adherence.controllable_adherence_pct", "adherence.session_adherence"],
            })
        elif exercise_adh is not None and exercise_adh < 0.7:
            findings.append({
                "cause_code": "execution",
                "statement": (
                    f"Only {adherence['completed_or_partial_exercises']}/"
                    f"{adherence['prescribed_exercises']} prescribed strength exercises were logged."
                ),
                "evidence_keys": ["adherence.exercise_adherence"],
            })

        # 5. Recovery
        avg_sleep = recovery.get("average_sleep_hours")
        very_fatigued = recovery.get("fatigue_counts", {}).get("very_fatigued", 0)
        if avg_sleep is not None and avg_sleep < 6.0:
            findings.append({
                "cause_code": "recovery",
                "statement": f"Average sleep was {avg_sleep:.1f} h; recovery is the constraint.",
                "evidence_keys": ["recovery.average_sleep_hours"],
            })
        elif very_fatigued >= 2 or recovery.get("rough_nights", 0) >= 3:
            findings.append({
                "cause_code": "recovery",
                "statement": "Repeated rough nights / very fatigued states limit adaptation.",
                "evidence_keys": ["recovery.rough_nights", "recovery.fatigue_counts"],
            })

        # 6–7. Technical recurrence
        for item in bjj.get("recurring_problems") or []:
            findings.append({
                "cause_code": "technical_recurrence",
                "statement": (
                    f"Repeated {item['kind']} `{item['code']}` across "
                    f"{len(item['session_ids'])} sessions ({item['window']})."
                ),
                "evidence_keys": [f"bjj.recurring.{item['kind']}.{item['code']}"],
            })

        # 8. Possible program issue — only after high adherence + stable recovery
        if (
            confidence != "low"
            and (controllable is None or controllable >= 80)
            and not recovery.get("has_pain_flag")
            and (avg_sleep is None or avg_sleep >= 6.5)
            and very_fatigued == 0
        ):
            for slug, data in (strength.get("exercises") or {}).items():
                # Need comparable exposures; single-week analysis can only flag within-week stalls
                # as noise. Cross-week stall detection needs prior saved facts — mark possible
                # only when ≥3 exposures this week with tiny e1RM range (unusual but tested).
                exposures = data.get("exposures") or []
                if len(exposures) >= 3:
                    values = [e["estimated_1rm"] for e in exposures]
                    mid = sum(values) / len(values)
                    if mid and all(abs(v - mid) / mid <= 0.02 for v in values):
                        findings.append({
                            "cause_code": "possible_program_issue",
                            "statement": (
                                f"{slug} showed no meaningful e1RM change across "
                                f"{len(exposures)} comparable exposures this week."
                            ),
                            "evidence_keys": [f"strength.{slug}"],
                        })

        if not findings:
            findings.append({
                "cause_code": "progressing_as_expected",
                "statement": "Adherence and recovery support the current plan.",
                "evidence_keys": ["adherence.session_adherence"],
            })

        # Prefer non-progressing findings first; keep diagnosis order from spec.
        priority = {
            "insufficient_data": 0,
            "recovery": 1,  # pain first among recovery
            "weather_constraint": 2,
            "execution": 3,
            "specificity": 4,
            "technical_recurrence": 5,
            "possible_program_issue": 6,
            "progressing_as_expected": 9,
        }
        # Re-rank pain recovery above other recovery: already encoded by insertion order.
        findings.sort(key=lambda item: priority.get(item["cause_code"], 8))
        return findings

    def _suggestions(self, bottleneck: dict, facts: dict) -> list[dict]:
        code = bottleneck["cause_code"]
        if code == "execution":
            return [{
                "area": "execution",
                "action": "Protect the next planned strength and BJJ sessions; do not rewrite the program yet.",
                "reason": "Low controllable adherence explains the lack of progress.",
                "requires_user_approval": False,
            }]
        if code == "weather_constraint":
            return [{
                "area": "bjj",
                "action": "Keep academy BJJ when weather allows; do not treat solo drills as live rounds.",
                "reason": "Weather blocked leave-home sessions; exposure is still missing.",
                "requires_user_approval": False,
            }]
        if code == "recovery":
            return [{
                "area": "recovery",
                "action": "Hold load/volume and prioritize sleep before adding intensity.",
                "reason": bottleneck["statement"],
                "requires_user_approval": False,
            }]
        if code == "technical_recurrence":
            return [{
                "area": "bjj",
                "action": "Drill the recurring problem position with a measurable success/attempt target.",
                "reason": bottleneck["statement"],
                "requires_user_approval": True,
            }]
        if code == "possible_program_issue":
            return [{
                "area": "strength",
                "action": "Change only one variable (load, reps, or exercise) for the stalled lift.",
                "reason": bottleneck["statement"],
                "requires_user_approval": True,
            }]
        if code == "insufficient_data":
            return [{
                "area": "logging",
                "action": "Log compact reps/RPE on strength and one BJJ failure tag when relevant.",
                "reason": "Missing fields block stronger conclusions.",
                "requires_user_approval": False,
            }]
        return [{
            "area": "plan",
            "action": "Keep the current weekly targets; no schedule change required.",
            "reason": "Nothing in the facts requires a program rewrite.",
            "requires_user_approval": False,
        }]

    def _tests(self, bottleneck: dict, facts: dict, recurring: dict | None) -> list[dict]:
        tests = []
        if recurring:
            tests.append({
                "metric": "Recurring BJJ problem under comparable practice",
                "target": "Fewer primary tags for the same failure/position next week, or a confirmed success ratio.",
            })
        if bottleneck["cause_code"] == "execution":
            tests.append({
                "metric": "Controllable session adherence",
                "target": "≥80% of non-weather-blocked planned sessions completed or partial.",
            })
        if bottleneck["cause_code"] == "recovery":
            tests.append({
                "metric": "Average sleep",
                "target": "≥6.5 h average across the next week.",
            })
        if bottleneck["cause_code"] == "possible_program_issue":
            tests.append({
                "metric": "Stalled lift weekly-best e1RM",
                "target": "Any increase after a single approved load/rep/exercise change.",
            })
        if not tests:
            tests.append({
                "metric": "Weekly controllable adherence",
                "target": "Hold ≥80% while keeping at least one full rest day.",
            })
        return tests

    @staticmethod
    def _row_payload(row: TrainingWeeklyAnalysis) -> dict:
        return {
            "id": row.id,
            "week_start": row.week_start.isoformat(),
            "week_end": row.week_end.isoformat(),
            "status": row.status,
            "data_confidence": row.data_confidence,
            "facts": row.facts_snapshot or {},
            "deterministic_report": row.deterministic_report_json or {},
            "rule_version": row.rule_version,
            "coach_report": row.coach_report_json,
            "coach_model_name": row.coach_model_name,
            "coach_prompt_version": row.coach_prompt_version,
            "coach_generated_at": row.coach_generated_at.isoformat() if row.coach_generated_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "schedule_change_prefill": _schedule_change_prefill(row.deterministic_report_json or {}),
        }


def _schedule_change_prefill(report: dict) -> str:
    """Plain-language prefill for /schedule-change — never auto-submits."""
    suggestions = report.get("next_week_suggestions") or []
    if not suggestions:
        return ""
    lines = ["From weekly review:"]
    for item in suggestions[:3]:
        action = item.get("action") or ""
        reason = item.get("reason") or ""
        lines.append(f"- {action}" + (f" ({reason})" if reason else ""))
    return "\n".join(lines)


def slug_for_exercise_name(name: str) -> str | None:
    return TEMPLATE_NAME_TO_SLUG.get(name)
