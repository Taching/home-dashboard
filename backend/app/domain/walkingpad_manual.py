from __future__ import annotations

import re
from dataclasses import dataclass

_WALK_KEYWORDS = re.compile(r"\b(?:walk(?:ed|ing)?|歩(?:いた|く))\b", re.I)
_MINUTES = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:min(?:ute)?s?|mins?|分)\b",
    re.I,
)
_DISTANCE_KM = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:km|kilometers?|kilometres?|キロ)\b",
    re.I,
)
_STEPS = re.compile(r"(\d+(?:,\d{3})*)\s*steps?\b", re.I)
_CALORIES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:k?cal(?:ories)?|カロリー)\b", re.I)


@dataclass(frozen=True)
class ParsedManualWalk:
    duration_minutes: float | None
    distance_km: float | None
    steps: int | None = None
    calories: float | None = None


def parse_manual_walk_message(text: str) -> ParsedManualWalk | None:
    """Parse phrases like "I walked 30 min and 2 km today"."""
    cleaned = text.strip()
    if not cleaned or not _WALK_KEYWORDS.search(cleaned):
        return None

    minutes_match = _MINUTES.search(cleaned)
    distance_match = _DISTANCE_KM.search(cleaned)
    steps_match = _STEPS.search(cleaned)
    calories_match = _CALORIES.search(cleaned)

    duration_minutes = float(minutes_match.group(1)) if minutes_match else None
    distance_km = float(distance_match.group(1)) if distance_match else None
    steps = int(steps_match.group(1).replace(",", "")) if steps_match else None
    calories = float(calories_match.group(1)) if calories_match else None

    if duration_minutes is None and distance_km is None:
        return None

    return ParsedManualWalk(
        duration_minutes=duration_minutes,
        distance_km=distance_km,
        steps=steps,
        calories=calories,
    )
