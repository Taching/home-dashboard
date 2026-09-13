from __future__ import annotations

from app.domain.training_plans import TrainingKind

QUESTIONS: dict[TrainingKind, tuple[str, ...]] = {
    "strength_a": (
        "Check each exercise you did on the workout page",
        "Optional note if it felt easy or hard",
    ),
    "strength_b": (
        "Check each exercise you did on the workout page",
        "Optional note if it felt easy or hard",
    ),
    "zone2": (
        "Check the Zone 2 session if you did it",
        "Optional note if it felt easy or hard",
    ),
    "grip": (
        "Check grip if you did it",
        "Optional note if it felt easy or hard",
    ),
    "bjj": (
        "Check each BJJ block you did",
        "Optional note if it felt easy or hard",
    ),
    "bjj_hard": (
        "Check each hard BJJ block you did",
        "Optional note if it felt easy or hard",
    ),
    "sober": (
        "Evening only. Did you stay sober today? yes / no",
        "Optional note",
    ),
    "rest": (
        "Check if today was full rest",
        "Optional note",
    ),
}


def questions_for(kind: TrainingKind) -> tuple[str, ...]:
    return QUESTIONS[kind]


def context_question_lines() -> list[str]:
    lines = ["- Training check-in questions (ask exactly these; do not invent extra ones):"]
    labels = {
        "strength_a": "Strength A",
        "strength_b": "Strength B",
        "zone2": "Zone 2",
        "grip": "Grip",
        "bjj": "BJJ",
        "bjj_hard": "BJJ Hard",
        "sober": "Sober",
        "rest": "Rest",
    }
    for kind, label in labels.items():
        joined = " · ".join(QUESTIONS[kind])
        lines.append(f"  - {label}: {joined}")
    return lines
