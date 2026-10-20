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
        name="Strength A — Heavy Strength",
        duration="50–60 minutes (+ optional 20–30 min easy cardio)",
        category="strength",
        summary="Maximum strength, unilateral leg stability, upper-back strength, shoulder health and core stability. RPE 7–8.",
        blocks=(
            TrainingBlock("Warm-up", "5 min easy", ("Stationary bike, easy pace.",)),
            TrainingBlock("Trap-bar Deadlift", "3 × 3–4", ("Start 125–130 kg.", "Rest about 3 minutes.")),
            TrainingBlock("Dumbbell Bench Press", "3 × 6–8", ("Start 30 kg/hand.",)),
            TrainingBlock("Bulgarian Split Squat", "3 × 6–8/leg", ("Start 14 kg/hand.",)),
            TrainingBlock("Cable Row", "3 × 8–10", ("RPE 7–8.",)),
            TrainingBlock("Pallof Press", "3 × 10/side", ("Moderate.",)),
            TrainingBlock("Cable Face Pull", "3 × 12–15", ("RPE 7.",)),
            TrainingBlock(
                "Easy cardio",
                "20–30 min, optional",
                ("Incline walk, bike, row, or swim at conversational pace.", "Counts toward the cut's weekly cardio."),
            ),
        ),
        notes=(
            "Use 2–3 reps in reserve on most working sets; never to failure.",
            "Reps first: reach the top of the range, then add weight (deadlift +2.5–5 kg, bench +2 kg/hand).",
            "Weight goes up only after a logged RPE of 8 or less.",
            "Every fourth week is a deload: about half the sets, 10–15% lighter.",
        ),
    ),
    "strength_b": TrainingPlan(
        slug="strength_b",
        kind="strength_b",
        name="Strength B — Athletic Strength",
        duration="45–55 minutes",
        category="strength",
        summary="Explosive hip power, leg strength, overhead strength, pulling strength and core control. RPE 7–8.",
        blocks=(
            TrainingBlock("Warm-up", "5 min easy", ("Stationary bike, easy pace.",)),
            TrainingBlock("Kettlebell Swing", "3 × 8", ("Moderate bell, crisp reps.",)),
            TrainingBlock("Front Squat", "3 × 4–5", ("Up to 90 kg.",)),
            TrainingBlock("Military Press", "3 × 5", ("Up to 52 kg.",)),
            TrainingBlock("Weighted Pull-up", "3 × 5–6", ("Bodyweight + 5 kg.",)),
            TrainingBlock("Romanian Deadlift", "2 × 6", ("Up to 100 kg.",)),
            TrainingBlock("Hanging Knee Raise", "3 × 8–12", ("Bodyweight. Or lying leg raise.",)),
        ),
        notes=(
            "Use 2–3 reps in reserve on most working sets; never to failure.",
            "Squat/RDL +2.5–5 kg, press and weighted pull-up +1–2.5 kg once the reps feel comfortable.",
            "Every fourth week is a deload: about half the sets, 10–15% lighter.",
            "Final six weeks: same weight, two working sets on most lifts.",
        ),
    ),
    "zone2": TrainingPlan(
        slug="zone2",
        kind="zone2",
        name="Zone 2 Cardio",
        duration="30–40 minutes",
        category="cardio",
        summary="Easy aerobic session. Conversational pace only.",
        blocks=(
            TrainingBlock(
                "Easy cardio",
                "30–40 min",
                (
                    "Incline walking, cycling, rowing, or swimming.",
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
