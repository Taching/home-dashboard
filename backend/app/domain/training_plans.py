from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal

TrainingKind = Literal[
    "strength_a",
    "strength_b",
    "zone2",
    "grip",
    "bjj",
    "bjj_hard",
    "sober",
    "rest",
]

TRAINING_KINDS: tuple[TrainingKind, ...] = (
    "strength_a",
    "strength_b",
    "zone2",
    "grip",
    "bjj",
    "bjj_hard",
    "sober",
    "rest",
)


@dataclass(frozen=True)
class TrainingBlock:
    title: str
    prescription: str | None
    details: tuple[str, ...]


@dataclass(frozen=True)
class TrainingPlan:
    slug: str
    kind: TrainingKind
    name: str
    duration: str
    category: Literal["strength", "cardio", "grip", "bjj", "rest", "checkin"]
    summary: str
    blocks: tuple[TrainingBlock, ...]
    notes: tuple[str, ...]


# Fallback labels only when no competition-plan session exists.
# The scheduler does not preserve this weekday layout.
WEEKDAY_SUGGESTIONS: tuple[tuple[TrainingKind, ...], ...] = (
    ("bjj",),
    ("strength_a",),
    ("zone2", "grip"),
    ("bjj",),
    ("strength_b",),
    ("bjj_hard",),
    ("rest",),
)


def suggested_kinds_for(day: date) -> tuple[TrainingKind, ...]:
    return WEEKDAY_SUGGESTIONS[day.weekday()]


PLANS: dict[str, TrainingPlan] = {
    "strength_a": TrainingPlan(
        slug="strength_a",
        kind="strength_a",
        name="Strength A",
        duration="55–65 minutes",
        category="strength",
        summary="Squat and bench day, then bike intervals. Strength maintenance, not max attempts.",
        blocks=(
            TrainingBlock(
                "Warm-up",
                "7–10 min easy",
                ("Stationary bike, easy pace.",),
            ),
            TrainingBlock(
                "Back Squat",
                "120 kg · 3×3",
                ("Rest about 3 minutes.",),
            ),
            TrainingBlock(
                "Bench Press",
                "85 kg · 3×3",
                ("Rest 2–3 minutes.",),
            ),
            TrainingBlock(
                "Pull-ups",
                "Bodyweight · 6–8×3",
                (),
            ),
            TrainingBlock(
                "Bulgarian Split Squat",
                "12–16 kg each hand · 6/leg × 2",
                (),
            ),
            TrainingBlock(
                "Standing Landmine Rotation",
                "20 kg · 8/side × 3",
                ("Use the normal setup.",),
            ),
            TrainingBlock(
                "Stationary Bike Intervals",
                "10 rounds · 30s hard / 30s easy",
                (
                    "Hard is about 9/10 and repeatable. Do not sprint maximally on round 1.",
                    "Record RPM, watts, distance, or calories when available.",
                    "Goal: hold output across all 10 rounds.",
                ),
            ),
        ),
        notes=(
            "Avoid max-effort squat or bench attempts.",
            "Do not put hard bike intervals within ~24 hours of important BJJ sparring.",
        ),
    ),
    "strength_b": TrainingPlan(
        slug="strength_b",
        kind="strength_b",
        name="Strength B",
        duration="45–55 minutes",
        category="strength",
        summary="Deadlift and press day. Finish with something left in the tank.",
        blocks=(
            TrainingBlock("Deadlift", "120 kg · 3×2", ()),
            TrainingBlock("Military Press", "40 kg · 5×3", ()),
            TrainingBlock("Pull-ups", "Bodyweight · 6–8×3", ()),
            TrainingBlock("Weighted Dips", "+10 kg · 8×2", ()),
            TrainingBlock("Copenhagen Plank", "20–30s/side × 3", ()),
            TrainingBlock(
                "Suitcase Carry",
                "Heavy DB or KB · 30–45s/side × 3",
                (),
            ),
        ),
        notes=(
            "No hard bike intervals after Strength B.",
            "Finish feeling like more work would still be possible.",
            "Avoid max-effort deadlift attempts.",
        ),
    ),
    "zone2": TrainingPlan(
        slug="zone2",
        kind="zone2",
        name="Zone 2 Cardio",
        duration="40–45 minutes",
        category="cardio",
        summary="One easy aerobic session. Conversational pace only.",
        blocks=(
            TrainingBlock(
                "Easy cardio",
                "40–45 min",
                (
                    "Running, stationary bike, treadmill, or incline walking.",
                    "Comfortable conversational pace. Do not turn this into a hard workout.",
                ),
            ),
        ),
        notes=(
            "Record duration, average HR, max HR, distance, or pace when possible.",
            "If BJJ was unexpectedly hard, prefer this over extra intensity.",
        ),
    ),
    "grip": TrainingPlan(
        slug="grip",
        kind="grip",
        name="Grip",
        duration="About 15 minutes",
        category="grip",
        summary="Short home grip work. Two sessions a week.",
        blocks=(
            TrainingBlock(
                "Towel Kettlebell Hold",
                "25 lb · 30s/hand × 3",
                (
                    "Rest about 45–90 seconds.",
                    "Progress toward 45 lb when 25 lb is comfortable for 30–45 seconds.",
                ),
            ),
        ),
        notes=(
            "Can be done at home with a towel and 25/45 lb kettlebells.",
            "Avoid hard grip work immediately before Gi BJJ.",
        ),
    ),
    "bjj": TrainingPlan(
        slug="bjj",
        kind="bjj",
        name="BJJ",
        duration="About 90 minutes",
        category="bjj",
        summary="Technique, positional work, and normal sparring. Primary training.",
        blocks=(
            TrainingBlock(
                "Class",
                "~90 minutes",
                ("Technique, positional work, and sparring.",),
            ),
            TrainingBlock(
                "Sparring capacity",
                "2–3 × 5-minute rounds",
                (
                    "Typical competition round is 5 minutes.",
                    "Conditioning goal: progress toward 4–5 × 5 minutes with 1–2 minutes rest.",
                ),
            ),
            TrainingBlock(
                "Technical focus",
                "Pick 1–2 things",
                (
                    "Guard retention, bottom movement, knee-cut defense, grip efficiency.",
                    "Preferred chain: Spider → De La Riva → X Guard → Sweep → Top pressure.",
                    "Start some rounds from open/bottom guard instead of always using strength.",
                ),
            ),
        ),
        notes=(
            "Do not make every BJJ session a hard competition session.",
            "If this class is unexpectedly very hard, reduce tomorrow's gym or conditioning.",
        ),
    ),
    "bjj_hard": TrainingPlan(
        slug="bjj_hard",
        kind="bjj_hard",
        name="BJJ Hard",
        duration="Competition practice",
        category="bjj",
        summary="One harder sparring day. Build rounds gradually.",
        blocks=(
            TrainingBlock(
                "Hard rounds",
                "Start 3 × 5 minutes",
                (
                    "If recovery is good, optional 4th round.",
                    "Progress toward 4 × 5, then 5 × 5.",
                    "Rest about 1–2 minutes between rounds.",
                ),
            ),
            TrainingBlock(
                "Technical focus",
                "Still only 1–2 things",
                ("Same focus list as regular BJJ. Quality over extra volume.",),
            ),
        ),
        notes=(
            "Preferably once per week.",
            "Do not stack this with heavy lower body or hard bike intervals the day before.",
        ),
    ),
    "rest": TrainingPlan(
        slug="rest",
        kind="rest",
        name="Full Rest",
        duration="Off",
        category="rest",
        summary="At least one full rest day. Do not add missed workouts on top of other hard sessions.",
        blocks=(),
        notes=(
            "BJJ scheduling takes priority. Move gym or cardio around it.",
            "If BJJ hits 4 sessions this week, drop a strength session rather than recovery.",
        ),
    ),
    "sober": TrainingPlan(
        slug="sober",
        kind="sober",
        name="Sober check-in",
        duration="Daily",
        category="checkin",
        summary="Same daily question OpenClaw asks.",
        blocks=(),
        notes=("Log whether you stayed sober and any note you want to keep.",),
    ),
}


def plan_for(slug: str) -> TrainingPlan | None:
    return PLANS.get(slug)


def all_plans() -> list[TrainingPlan]:
    return [PLANS[kind] for kind in TRAINING_KINDS]
