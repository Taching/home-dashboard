from __future__ import annotations

import re
from dataclasses import dataclass

from app.domain.training_plans import TrainingKind

_KIND_PATTERNS: tuple[tuple[re.Pattern[str], TrainingKind], ...] = (
    (re.compile(r"\b(?:strength[\s_-]*a|workout[\s_-]*a)\b", re.I), "strength_a"),
    (re.compile(r"\b(?:strength[\s_-]*b|workout[\s_-]*b)\b", re.I), "strength_b"),
    (re.compile(r"\b(?:zone[\s_-]*2|z2|easy cardio)\b", re.I), "zone2"),
    (re.compile(r"\bgrip\b", re.I), "grip"),
    (re.compile(r"\b(?:bjj[\s_-]*hard|hard[\s_-]*bjj|competition practice)\b", re.I), "bjj_hard"),
    (re.compile(r"\b(?:bjj|jiu[\s-]*jitsu|jiujitsu)\b", re.I), "bjj"),
    (re.compile(r"\b(?:sober|stayed sober|drank|relapse(?:d)?)\b", re.I), "sober"),
    (re.compile(r"\b(?:full rest|rest day)\b", re.I), "rest"),
)

_YES = re.compile(r"\b(?:did|done|completed|finished|logged|yes|stayed sober)\b", re.I)
_PARTIAL = re.compile(r"\b(?:partial|halfway|cut(?:ting)? short)\b", re.I)
_SKIPPED = re.compile(r"\b(?:skip(?:ped)?|missed|no show)\b", re.I)
_SOBER_NO = re.compile(r"\b(?:drank|relapse(?:d)?|not sober)\b", re.I)

_FEELING = (
    (re.compile(r"\b(?:wrecked|destroyed|fried|dead)\b", re.I), "wrecked"),
    (re.compile(r"\b(?:tired|heavy|wiped)\b", re.I), "tired"),
    (re.compile(r"\b(?:fresh|easy|great|good)\b", re.I), "fresh"),
    (re.compile(r"\b(?:normal|okay|ok|fine)\b", re.I), "normal"),
)

_ROUNDS = re.compile(r"(\d+)\s*[x×]\s*(\d+)", re.I)
_ROUNDS_WORD = re.compile(r"(\d+)\s*rounds?\b", re.I)
_MINUTES = re.compile(r"(\d+(?:\.\d+)?)\s*(?:min(?:ute)?s?|mins?)\b", re.I)
_HR_AVG = re.compile(r"(?:avg(?:erage)?\s*)?hr\s*(\d{2,3})\b", re.I)
_HR_MAX = re.compile(r"max(?:imum)?\s*hr\s*(\d{2,3})\b", re.I)
_DISTANCE = re.compile(r"(\d+(?:\.\d+)?)\s*(?:km|kilometers?|kilometres?)\b", re.I)
_NOTE = re.compile(r"(?:note|felt|because)[:\s]+(.+)$", re.I)

TrainingCompleted = str
TrainingFeeling = str


@dataclass(frozen=True)
class ParsedTrainingLog:
    kind: TrainingKind
    completed: TrainingCompleted
    feeling: TrainingFeeling | None = None
    note: str | None = None
    rounds: str | None = None
    duration_minutes: float | None = None
    avg_hr: int | None = None
    max_hr: int | None = None
    distance_km: float | None = None


def parse_training_message(text: str) -> ParsedTrainingLog | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    kind = _match_kind(cleaned)
    if kind is None:
        return None

    completed = _match_completed(cleaned, kind)
    feeling = _match_feeling(cleaned)
    rounds = _match_rounds(cleaned)
    minutes = _MINUTES.search(cleaned)
    avg_hr = _HR_AVG.search(cleaned)
    max_hr = _HR_MAX.search(cleaned)
    distance = _DISTANCE.search(cleaned)
    note_match = _NOTE.search(cleaned)
    note = note_match.group(1).strip() if note_match else None

    return ParsedTrainingLog(
        kind=kind,
        completed=completed,
        feeling=feeling,
        note=note,
        rounds=rounds,
        duration_minutes=float(minutes.group(1)) if minutes else None,
        avg_hr=int(avg_hr.group(1)) if avg_hr else None,
        max_hr=int(max_hr.group(1)) if max_hr else None,
        distance_km=float(distance.group(1)) if distance else None,
    )


def _match_kind(text: str) -> TrainingKind | None:
    for pattern, kind in _KIND_PATTERNS:
        if pattern.search(text):
            return kind
    return None


def _match_completed(text: str, kind: TrainingKind) -> TrainingCompleted:
    if kind == "sober":
        if _SOBER_NO.search(text):
            return "no"
        return "yes"
    if _PARTIAL.search(text):
        return "partial"
    if _SKIPPED.search(text):
        return "skipped"
    if _YES.search(text):
        return "yes"
    return "yes"


def _match_feeling(text: str) -> TrainingFeeling | None:
    for pattern, feeling in _FEELING:
        if pattern.search(text):
            return feeling
    return None


def _match_rounds(text: str) -> str | None:
    match = _ROUNDS.search(text)
    if match:
        return f"{match.group(1)}x{match.group(2)}"
    word = _ROUNDS_WORD.search(text)
    if word:
        return f"{word.group(1)}x5"
    return None
