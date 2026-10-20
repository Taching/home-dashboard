"""On-demand Ask coach for the weekly analyzer (spec section 12, Milestone 4).

AI explains already-saved facts only. It never invents metrics or mutates the planner.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.core.dry_run import guard_external_call, is_dry_run
from app.core.settings import settings
from app.domain.weekly_analyzer import CAUSE_CODES, COACH_PROMPT_VERSION

logger = logging.getLogger(__name__)

RUTHLESS_SYSTEM_PROMPT = """You are a direct BJJ and strength performance reviewer.
Use only the supplied facts. Separate effort from results.
Call out missed work, repeated mistakes, weak explanations, and unrealistic expectations.
Do not use praise unless a supplied metric improved.
Do not insult, shame, diagnose, or invent motives.
Do not call one noisy result a trend.
If evidence is missing, say exactly what cannot be concluded.
Return only the required JSON."""

_COACH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "verdict": {"type": "string"},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "main_bottleneck": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "cause_code": {"type": "string"},
                "statement": {"type": "string"},
                "evidence_keys": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["cause_code", "statement", "evidence_keys"],
        },
        "improved": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "statement": {"type": "string"},
                    "evidence_keys": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["statement", "evidence_keys"],
            },
        },
        "regressed": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "statement": {"type": "string"},
                    "evidence_keys": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["statement", "evidence_keys"],
            },
        },
        "recurring_problem": {
            "type": ["object", "null"],
            "additionalProperties": False,
            "properties": {
                "statement": {"type": "string"},
                "evidence_keys": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["statement", "evidence_keys"],
        },
        "next_week_actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "area": {"type": "string"},
                    "action": {"type": "string"},
                    "reason": {"type": "string"},
                    "requires_user_approval": {"type": "boolean"},
                },
                "required": ["area", "action", "reason", "requires_user_approval"],
            },
        },
        "tests": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "metric": {"type": "string"},
                    "target": {"type": "string"},
                },
                "required": ["metric", "target"],
            },
        },
        "missing_data": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "verdict",
        "confidence",
        "main_bottleneck",
        "improved",
        "regressed",
        "recurring_problem",
        "next_week_actions",
        "tests",
        "missing_data",
    ],
}


def validate_coach_report(payload: dict) -> dict:
    """Validate Ask coach JSON before saving. Raises ValueError on failure."""
    if not isinstance(payload, dict):
        raise ValueError("Coach report must be an object")
    for key in _COACH_SCHEMA["required"]:
        if key not in payload:
            raise ValueError(f"Missing field: {key}")
    confidence = payload["confidence"]
    if confidence not in {"low", "medium", "high"}:
        raise ValueError("Invalid confidence")
    bottleneck = payload["main_bottleneck"]
    if not isinstance(bottleneck, dict):
        raise ValueError("main_bottleneck must be an object")
    if bottleneck.get("cause_code") not in CAUSE_CODES:
        raise ValueError(f"Invalid cause_code: {bottleneck.get('cause_code')}")
    if not bottleneck.get("evidence_keys"):
        raise ValueError("main_bottleneck requires evidence_keys")
    actions = payload.get("next_week_actions") or []
    tests = payload.get("tests") or []
    if len(actions) > 3:
        raise ValueError("At most 3 next_week_actions")
    if len(tests) > 3:
        raise ValueError("At most 3 tests")
    for claim in list(payload.get("improved") or []) + list(payload.get("regressed") or []):
        if not claim.get("evidence_keys"):
            raise ValueError("Every performance claim needs evidence_keys")
    recurring = payload.get("recurring_problem")
    if recurring is not None and not isinstance(recurring, dict):
        raise ValueError("recurring_problem must be object or null")
    return payload


def build_coach_input(analysis: dict) -> dict:
    facts = analysis.get("facts") or {}
    week = facts.get("week") or {
        "start": analysis.get("week_start"),
        "end": analysis.get("week_end"),
        "timezone": settings.timezone,
    }
    return {
        "week": week,
        "goal": "March 2027 BJJ competition preparation",
        "coach_style": "ruthless",
        "confidence": analysis.get("data_confidence") or facts.get("confidence") or "low",
        "facts": {
            "adherence": facts.get("adherence") or {},
            "bjj": facts.get("bjj") or {},
            "strength": facts.get("strength") or {},
            "conditioning": facts.get("conditioning") or {},
            "recovery": facts.get("recovery") or {},
            "body_trend": facts.get("body_trend") or {},
            "rule_findings": (analysis.get("deterministic_report") or {}).get("rule_findings")
            or facts.get("rule_findings")
            or [],
        },
        "deterministic_report": analysis.get("deterministic_report") or {},
    }


def ask_coach(analysis: dict, *, model_name: str | None = None) -> tuple[dict | None, str]:
    """Call OpenAI once (with one retry on invalid JSON). Returns (report, status).

    status: ok | dry_run | unavailable | validation_failed
    """
    model = model_name or settings.voice_command_model or "gpt-4.1-mini"
    payload = build_coach_input(analysis)

    if is_dry_run():
        guard_external_call("OpenAI", f"weekly ask_coach(week={payload['week'].get('start')})")
        # Deterministic dry-run payload mirrors the saved report so UI can still demo.
        report = _dry_run_report(analysis)
        return report, "dry_run"

    api_key = settings.openai_api_key
    if not api_key:
        return None, "unavailable"

    last_error: Exception | None = None
    for _attempt in range(2):
        try:
            raw = _call_openai(api_key, model, payload)
            parsed = json.loads(raw)
            return validate_coach_report(parsed), "ok"
        except Exception as error:  # noqa: BLE001 — retry then fall back
            last_error = error
            logger.info("weekly ask_coach attempt failed: %s", error)
    logger.info("weekly ask_coach unavailable after retry: %s", last_error)
    return None, "validation_failed"


def _dry_run_report(analysis: dict) -> dict:
    report = analysis.get("deterministic_report") or {}
    bottleneck = report.get("main_bottleneck") or {
        "cause_code": "insufficient_data",
        "statement": "Dry-run: no external coach call.",
        "evidence_keys": ["data_coverage.ratio"],
    }
    return {
        "verdict": (
            "[dry-run] " + str(report.get("summary_line") or bottleneck.get("statement") or "")
        ).strip(),
        "confidence": report.get("confidence") or analysis.get("data_confidence") or "low",
        "main_bottleneck": bottleneck,
        "improved": report.get("improved") or [],
        "regressed": report.get("regressed") or [],
        "recurring_problem": report.get("recurring_problem"),
        "next_week_actions": [
            {
                "area": item.get("area") or "plan",
                "action": item.get("action") or "",
                "reason": item.get("reason") or "",
                "requires_user_approval": bool(item.get("requires_user_approval")),
            }
            for item in (report.get("next_week_suggestions") or [])[:3]
        ],
        "tests": report.get("tests") or [],
        "missing_data": report.get("missing_data") or [],
        "dry_run": True,
        "prompt_version": COACH_PROMPT_VERSION,
    }


def _call_openai(api_key: str, model: str, payload: dict) -> str:
    response = httpx.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "store": False,
            "input": [
                {"role": "system", "content": RUTHLESS_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload)},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "weekly_coach_report",
                    "strict": True,
                    "schema": _COACH_SCHEMA,
                }
            },
        },
        timeout=30,
    )
    response.raise_for_status()
    body = response.json()
    raw = body.get("output_text") or _output_text(body)
    if not raw:
        raise ValueError("Empty OpenAI response")
    return raw


def _output_text(payload: dict) -> str:
    chunks = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if text:
                chunks.append(text)
    return "".join(chunks)
