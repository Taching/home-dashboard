from __future__ import annotations

from datetime import date
import json
import logging

import httpx

from app.core.settings import settings
from app.domain.training.types import SchedulerInput, WorkoutType

logger = logging.getLogger(__name__)

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "pick": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["pick", "reason"],
}


def rerank_and_explain(
    close: tuple[WorkoutType, ...],
    default: WorkoutType | None,
    fallback_reason: str,
    inp: SchedulerInput,
    day: date,
) -> tuple[WorkoutType | None, str]:
    if default is None or not close:
        return default, fallback_reason
    api_key = settings.openai_api_key
    if not api_key:
        return default, fallback_reason
    allowed = {item.value for item in close}
    payload = {
        "day": day.isoformat(),
        "default": default.value,
        "close_set": [item.value for item in close],
        "fatigue": inp.athlete_state.fatigue.value,
        "soreness": inp.athlete_state.soreness.value,
        "injured": inp.athlete_state.injured,
        "hard_bjj": inp.upcoming_hard_bjj.isoformat() if inp.upcoming_hard_bjj else None,
        "history": [
            {"date": item.date.isoformat(), "session": item.session.value, "status": item.status.value}
            for item in inp.history[-8:]
        ],
        "fallback_reason": fallback_reason,
    }
    try:
        response = httpx.post(
            "https://api.openai.com/v1/responses",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": settings.voice_command_model,
                "store": False,
                "input": [
                    {
                        "role": "system",
                        "content": (
                            "You are a BJJ strength coach. Pick only from close_set or keep the default. "
                            "Write one short coaching sentence. Never invent a session type."
                        ),
                    },
                    {"role": "user", "content": json.dumps(payload)},
                ],
                "text": {"format": {"type": "json_schema", "name": "session_pick", "strict": True, "schema": _SCHEMA}},
            },
            timeout=12,
        )
        response.raise_for_status()
        body = response.json()
        raw = body.get("output_text") or _output_text(body)
        parsed = json.loads(raw)
        pick = str(parsed.get("pick") or "")
        reason = str(parsed.get("reason") or "").strip()
        if pick not in allowed:
            logger.info("llm pick %s discarded; keeping %s", pick, default.value)
            return default, fallback_reason
        chosen = next(item for item in close if item.value == pick)
        return chosen, reason or fallback_reason
    except Exception as error:
        logger.info("llm rerank failed: %s", error)
        return default, fallback_reason


def _output_text(payload: dict) -> str:
    chunks = []
    for item in payload.get("output") or []:
        for content in item.get("content") or []:
            text = content.get("text")
            if text:
                chunks.append(text)
    return "".join(chunks)
