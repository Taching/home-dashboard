"""Exercise library and deterministic alternatives engine.

Implements spec sections 5, 6, 7, and 8 (Milestone 1 scope).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import BjjFailureType, Exercise, ExerciseSubstitutionOverride

CATEGORIES = frozenset({"strength", "power", "conditioning", "mobility", "skill"})

MOVEMENT_PATTERNS = frozenset({
    "horizontal_push", "vertical_push", "horizontal_pull", "vertical_pull",
    "squat", "hinge", "lunge", "carry", "rotation", "anti_rotation",
    "trunk_stability", "trunk_flexion", "locomotion", "neck", "grip", "cyclical",
})

PLANES = frozenset({"sagittal", "frontal", "transverse", "multiplanar"})

TRAINING_INTENTS = frozenset({
    "strength", "hypertrophy", "power", "conditioning", "stability", "skill", "mobility",
})

PRIMARY_REGIONS = frozenset({"upper", "lower", "core", "full_body", "neck"})

MOVEMENT_SPEEDS = frozenset({"controlled", "ballistic", "isometric", "cyclical"})

LATERALITIES = frozenset({"bilateral", "unilateral", "alternating", "not_applicable"})

DIFFICULTIES = frozenset({"beginner", "intermediate", "advanced"})

CANONICAL_EQUIPMENT_TOKENS = frozenset({
    "barbell", "bench", "dumbbell", "bodyweight", "plate", "weight_vest",
    "kettlebell", "landmine", "cable", "resistance_band", "pull_up_bar",
    "rack", "trap_bar", "box", "sandbag", "sled", "rope", "towel", "gi",
    "medicine_ball", "wall", "mat", "stationary_bike", "rowing_machine",
    "bar", "hands",
})

PROGRESSION_PROFILES = frozenset({
    "lower_barbell", "upper_barbell", "weighted_pull", "dumbbell_pair",
    "cable_stack", "kettlebell_jump", "reps_only", "hold",
})


@dataclass(frozen=True)
class ExerciseData:
    slug: str
    name: str
    aliases: tuple[str, ...] = ()
    category: str = "strength"
    movement_pattern: str = "horizontal_push"
    plane: str = "sagittal"
    training_intent: str = "strength"
    primary_region: str = "upper"
    primary_muscles: tuple[str, ...] = ()
    equipment: tuple[str, ...] = ()
    substitution_group: str = "horizontal_press"
    movement_speed: str = "controlled"
    laterality: str = "bilateral"
    difficulty: str = "intermediate"
    bjj_tags: tuple[str, ...] = ()
    risk_notes: str | None = None


@dataclass(frozen=True)
class BjjFailureTypeData:
    code: str
    label: str
    description: str


@dataclass(frozen=True)
class AlternativeResult:
    slug: str
    name: str
    score: int
    why: tuple[str, ...]
    tradeoff: str | None = None


@dataclass(frozen=True)
class AlternativesResponse:
    source: str
    alternatives: tuple[AlternativeResult, ...]


EXERCISE_SEED: tuple[ExerciseData, ...] = (
    ExerciseData(
        "barbell-bench-press", "Barbell Bench Press", ("bench press",),
        "strength", "horizontal_push", "sagittal", "strength", "upper",
        ("chest", "triceps", "front delts"), ("barbell+bench",),
        "horizontal_press", "controlled", "bilateral", "intermediate",
        ("upper-body pushing",), None,
    ),
    ExerciseData(
        "dumbbell-bench-press", "Dumbbell Bench Press", ("DB bench",),
        "strength", "horizontal_push", "sagittal", "strength", "upper",
        ("chest", "triceps", "front delts"), ("dumbbell+bench",),
        "horizontal_press", "controlled", "bilateral", "beginner",
        ("upper-body pushing",), None,
    ),
    ExerciseData(
        "weighted-push-up", "Weighted Push-Up", ("loaded push-up",),
        "strength", "horizontal_push", "sagittal", "strength", "upper",
        ("chest", "triceps", "front delts"), ("bodyweight+plate", "bodyweight+weight_vest"),
        "horizontal_press", "controlled", "bilateral", "intermediate",
        ("upper-body pushing", "trunk stiffness"), None,
    ),
    ExerciseData(
        "push-up", "Push-Up", (),
        "strength", "horizontal_push", "sagittal", "hypertrophy", "upper",
        ("chest", "triceps", "front delts"), ("bodyweight",),
        "horizontal_press", "controlled", "bilateral", "beginner",
        ("upper-body pushing", "trunk stiffness"), None,
    ),
    ExerciseData(
        "dumbbell-floor-press", "Dumbbell Floor Press", ("DB floor press",),
        "strength", "horizontal_push", "sagittal", "strength", "upper",
        ("chest", "triceps"), ("dumbbell",),
        "horizontal_press", "controlled", "bilateral", "beginner",
        ("upper-body pushing",), "Shorter range of motion than bench pressing.",
    ),
    ExerciseData(
        "barbell-overhead-press", "Barbell Overhead Press", ("military press",),
        "strength", "vertical_push", "sagittal", "strength", "upper",
        ("delts", "triceps"), ("barbell",),
        "vertical_press", "controlled", "bilateral", "intermediate",
        ("posting strength",), None,
    ),
    ExerciseData(
        "dumbbell-overhead-press", "Dumbbell Overhead Press", ("DB shoulder press",),
        "strength", "vertical_push", "sagittal", "strength", "upper",
        ("delts", "triceps"), ("dumbbell",),
        "vertical_press", "controlled", "bilateral", "beginner",
        ("posting strength",), None,
    ),
    ExerciseData(
        "half-kneeling-landmine-press", "Half-Kneeling Landmine Press", ("landmine press",),
        "strength", "vertical_push", "sagittal", "strength", "upper",
        ("delts", "triceps", "serratus"), ("barbell+landmine",),
        "vertical_press", "controlled", "unilateral", "beginner",
        ("posting strength", "anti-rotation"), None,
    ),
    ExerciseData(
        "kettlebell-strict-press", "Kettlebell Strict Press", ("KB press",),
        "strength", "vertical_push", "sagittal", "strength", "upper",
        ("delts", "triceps"), ("kettlebell",),
        "vertical_press", "controlled", "unilateral", "intermediate",
        ("posting strength", "shoulder stability"), None,
    ),
    ExerciseData(
        "bottoms-up-kettlebell-press", "Bottoms-Up Kettlebell Press", ("bottoms-up press",),
        "skill", "vertical_push", "sagittal", "stability", "upper",
        ("delts", "triceps", "forearms"), ("kettlebell",),
        "shoulder_stability_press", "controlled", "unilateral", "advanced",
        ("grip", "shoulder stability"), "Use light loads; this is not a direct heavy press substitute.",
    ),
    ExerciseData(
        "chest-supported-dumbbell-row", "Chest-Supported Dumbbell Row", ("chest-supported row",),
        "strength", "horizontal_pull", "sagittal", "strength", "upper",
        ("lats", "upper back", "biceps"), ("dumbbell+bench",),
        "horizontal_row", "controlled", "bilateral", "beginner",
        ("pulling strength", "posture"), None,
    ),
    ExerciseData(
        "one-arm-dumbbell-row", "One-Arm Dumbbell Row", ("single-arm DB row",),
        "strength", "horizontal_pull", "sagittal", "strength", "upper",
        ("lats", "upper back", "biceps"), ("dumbbell+bench",),
        "horizontal_row", "controlled", "unilateral", "beginner",
        ("pulling strength", "anti-rotation"), None,
    ),
    ExerciseData(
        "seated-cable-row", "Seated Cable Row", (),
        "strength", "horizontal_pull", "sagittal", "strength", "upper",
        ("lats", "upper back", "biceps"), ("cable",),
        "horizontal_row", "controlled", "bilateral", "beginner",
        ("pulling strength", "posture"), None,
    ),
    ExerciseData(
        "inverted-row", "Inverted Row", ("body row",),
        "strength", "horizontal_pull", "sagittal", "hypertrophy", "upper",
        ("lats", "upper back", "biceps"), ("bar+bodyweight",),
        "horizontal_row", "controlled", "bilateral", "beginner",
        ("pulling strength", "trunk stiffness"), None,
    ),
    ExerciseData(
        "cable-face-pull", "Cable Face Pull", ("face pull",),
        "strength", "horizontal_pull", "sagittal", "hypertrophy", "upper",
        ("rear delts", "upper back", "rotator cuff"), ("cable",),
        "rear_shoulder_pull", "controlled", "bilateral", "beginner",
        ("shoulder health", "posture"), None,
    ),
    ExerciseData(
        "pull-up", "Pull-Up", (),
        "strength", "vertical_pull", "sagittal", "strength", "upper",
        ("lats", "biceps", "upper back"), ("pull_up_bar+bodyweight",),
        "vertical_pull", "controlled", "bilateral", "intermediate",
        ("grip", "pulling strength"), None,
    ),
    ExerciseData(
        "weighted-pull-up", "Weighted Pull-Up", ("loaded pull-up",),
        "strength", "vertical_pull", "sagittal", "strength", "upper",
        ("lats", "biceps", "upper back"), ("pull_up_bar+bodyweight+plate", "pull_up_bar+bodyweight+weight_vest"),
        "vertical_pull", "controlled", "bilateral", "advanced",
        ("grip", "pulling strength"), None,
    ),
    ExerciseData(
        "chin-up", "Chin-Up", (),
        "strength", "vertical_pull", "sagittal", "strength", "upper",
        ("lats", "biceps", "upper back"), ("pull_up_bar+bodyweight",),
        "vertical_pull", "controlled", "bilateral", "intermediate",
        ("grip", "pulling strength"), None,
    ),
    ExerciseData(
        "lat-pulldown", "Lat Pulldown", (),
        "strength", "vertical_pull", "sagittal", "strength", "upper",
        ("lats", "biceps", "upper back"), ("cable",),
        "vertical_pull", "controlled", "bilateral", "beginner",
        ("pulling strength",), None,
    ),
    ExerciseData(
        "towel-pull-up", "Towel Pull-Up", ("gi pull-up",),
        "strength", "vertical_pull", "sagittal", "strength", "upper",
        ("lats", "biceps", "forearms"), ("pull_up_bar+towel", "pull_up_bar+gi"),
        "grip_vertical_pull", "controlled", "bilateral", "advanced",
        ("gi grip", "pulling strength"), "Progress grip exposure gradually.",
    ),
    ExerciseData(
        "rope-climb", "Rope Climb", (),
        "skill", "vertical_pull", "sagittal", "strength", "full_body",
        ("lats", "biceps", "forearms"), ("rope",),
        "grip_vertical_pull", "controlled", "bilateral", "advanced",
        ("grip", "pulling strength", "conditioning"), "Requires a safe rope setup and controlled descent.",
    ),
    ExerciseData(
        "back-squat", "Back Squat", ("barbell back squat",),
        "strength", "squat", "sagittal", "strength", "lower",
        ("quads", "glutes", "adductors"), ("barbell+rack",),
        "bilateral_squat", "controlled", "bilateral", "intermediate",
        ("base strength",), None,
    ),
    ExerciseData(
        "front-squat", "Front Squat", ("barbell front squat",),
        "strength", "squat", "sagittal", "strength", "lower",
        ("quads", "glutes", "upper back"), ("barbell+rack",),
        "bilateral_squat", "controlled", "bilateral", "intermediate",
        ("base strength", "posture"), None,
    ),
    ExerciseData(
        "goblet-squat", "Goblet Squat", (),
        "strength", "squat", "sagittal", "strength", "lower",
        ("quads", "glutes"), ("kettlebell", "dumbbell"),
        "bilateral_squat", "controlled", "bilateral", "beginner",
        ("base strength", "posture"), "Loading may become limited by how much weight can be held.",
    ),
    ExerciseData(
        "zercher-squat", "Zercher Squat", (),
        "strength", "squat", "sagittal", "strength", "full_body",
        ("quads", "glutes", "upper back"), ("barbell+rack",),
        "bilateral_squat", "controlled", "bilateral", "advanced",
        ("clinch posture", "base strength"), "Use appropriate elbow padding and conservative loading.",
    ),
    ExerciseData(
        "bulgarian-split-squat", "Bulgarian Split Squat", ("rear-foot-elevated split squat",),
        "strength", "lunge", "sagittal", "strength", "lower",
        ("quads", "glutes"), ("bench+bodyweight", "bench+dumbbell", "bench+barbell"),
        "unilateral_squat", "controlled", "unilateral", "intermediate",
        ("single-leg strength", "base"), None,
    ),
    ExerciseData(
        "reverse-lunge", "Reverse Lunge", (),
        "strength", "lunge", "sagittal", "strength", "lower",
        ("quads", "glutes"), ("bodyweight", "dumbbell"),
        "unilateral_squat", "controlled", "alternating", "beginner",
        ("single-leg strength", "base"), None,
    ),
    ExerciseData(
        "step-up", "Step-Up", (),
        "strength", "lunge", "sagittal", "strength", "lower",
        ("quads", "glutes"), ("box", "box+dumbbell"),
        "unilateral_squat", "controlled", "unilateral", "beginner",
        ("single-leg strength", "base"), None,
    ),
    ExerciseData(
        "conventional-deadlift", "Conventional Deadlift", ("deadlift",),
        "strength", "hinge", "sagittal", "strength", "full_body",
        ("glutes", "hamstrings", "back"), ("barbell",),
        "heavy_hinge", "controlled", "bilateral", "intermediate",
        ("base strength", "grip"), None,
    ),
    ExerciseData(
        "trap-bar-deadlift", "Trap-Bar Deadlift", ("hex-bar deadlift",),
        "strength", "hinge", "sagittal", "strength", "full_body",
        ("glutes", "quads", "hamstrings", "back"), ("trap_bar",),
        "heavy_hinge", "controlled", "bilateral", "beginner",
        ("base strength", "grip"), None,
    ),
    ExerciseData(
        "sumo-deadlift", "Sumo Deadlift", (),
        "strength", "hinge", "sagittal", "strength", "full_body",
        ("glutes", "adductors", "quads", "back"), ("barbell",),
        "heavy_hinge", "controlled", "bilateral", "intermediate",
        ("base strength", "grip"), None,
    ),
    ExerciseData(
        "romanian-deadlift", "Romanian Deadlift", ("RDL",),
        "strength", "hinge", "sagittal", "hypertrophy", "lower",
        ("hamstrings", "glutes", "back"), ("barbell", "dumbbell"),
        "accessory_hinge", "controlled", "bilateral", "beginner",
        ("posterior chain",), None,
    ),
    ExerciseData(
        "single-leg-romanian-deadlift", "Single-Leg Romanian Deadlift", ("single-leg RDL",),
        "strength", "hinge", "sagittal", "stability", "lower",
        ("hamstrings", "glutes"), ("kettlebell", "dumbbell"),
        "accessory_hinge", "controlled", "unilateral", "intermediate",
        ("single-leg strength", "balance"), None,
    ),
    ExerciseData(
        "kettlebell-deadlift", "Kettlebell Deadlift", ("KB deadlift",),
        "strength", "hinge", "sagittal", "strength", "lower",
        ("glutes", "hamstrings", "back"), ("kettlebell",),
        "accessory_hinge", "controlled", "bilateral", "beginner",
        ("hinge skill", "base strength"), "Loading may be insufficient for a trained athlete.",
    ),
    ExerciseData(
        "barbell-hip-thrust", "Barbell Hip Thrust", ("hip thrust",),
        "strength", "hinge", "sagittal", "strength", "lower",
        ("glutes", "hamstrings"), ("barbell+bench",),
        "hip_extension", "controlled", "bilateral", "beginner",
        ("hip extension",), None,
    ),
    ExerciseData(
        "two-hand-kettlebell-swing", "Two-Hand Kettlebell Swing", ("KB swing",),
        "power", "hinge", "sagittal", "power", "full_body",
        ("glutes", "hamstrings", "back"), ("kettlebell",),
        "ballistic_hinge", "ballistic", "bilateral", "intermediate",
        ("hip power", "conditioning"), "Do not substitute automatically for a heavy or controlled hinge.",
    ),
    ExerciseData(
        "one-hand-kettlebell-swing", "One-Hand Kettlebell Swing", ("single-arm KB swing",),
        "power", "hinge", "sagittal", "power", "full_body",
        ("glutes", "hamstrings", "back", "forearms"), ("kettlebell",),
        "ballistic_hinge", "ballistic", "unilateral", "intermediate",
        ("hip power", "grip", "anti-rotation"), "Do not substitute automatically for a heavy or controlled hinge.",
    ),
    ExerciseData(
        "kettlebell-clean", "Kettlebell Clean", ("KB clean",),
        "power", "hinge", "sagittal", "power", "full_body",
        ("glutes", "hamstrings", "upper back"), ("kettlebell",),
        "kettlebell_ballistic_pull", "ballistic", "unilateral", "intermediate",
        ("hip power", "grip"), None,
    ),
    ExerciseData(
        "kettlebell-snatch", "Kettlebell Snatch", ("KB snatch",),
        "power", "hinge", "sagittal", "power", "full_body",
        ("glutes", "hamstrings", "upper back", "delts"), ("kettlebell",),
        "kettlebell_ballistic_pull", "ballistic", "unilateral", "advanced",
        ("hip power", "grip", "conditioning"), "Requires competent swing and clean mechanics.",
    ),
    ExerciseData(
        "turkish-get-up", "Turkish Get-Up", ("TGU",),
        "skill", "trunk_stability", "multiplanar", "stability", "full_body",
        ("shoulders", "core", "hips"), ("kettlebell",),
        "ground_to_stand_stability", "controlled", "unilateral", "advanced",
        ("shoulder stability", "ground movement", "base"), "Treat as a skill/stability drill, not a maximal lift.",
    ),
    ExerciseData(
        "kettlebell-windmill", "Kettlebell Windmill", ("KB windmill",),
        "skill", "trunk_stability", "multiplanar", "mobility", "full_body",
        ("obliques", "shoulders", "hamstrings"), ("kettlebell",),
        "loaded_mobility", "controlled", "unilateral", "advanced",
        ("shoulder stability", "hip mobility"), "Requires adequate shoulder and hip mobility.",
    ),
    ExerciseData(
        "kettlebell-halo", "Kettlebell Halo", ("KB halo",),
        "mobility", "trunk_stability", "multiplanar", "mobility", "upper",
        ("shoulders", "upper back", "core"), ("kettlebell",),
        "shoulder_mobility", "controlled", "alternating", "beginner",
        ("shoulder mobility",), None,
    ),
    ExerciseData(
        "landmine-180", "Landmine 180", ("barbell rotation", "full-contact twist", "grappler twist", "landmine rainbow"),
        "power", "rotation", "transverse", "power", "full_body",
        ("obliques", "hips", "shoulders"), ("barbell+landmine",),
        "rotation_power", "ballistic", "alternating", "intermediate",
        ("rotational power", "hand fighting"), "Rotate through the hips and trunk; do not force lumbar range.",
    ),
    ExerciseData(
        "half-kneeling-landmine-rotation", "Half-Kneeling Landmine Rotation", ("half-kneeling barbell rotation",),
        "strength", "rotation", "transverse", "strength", "core",
        ("obliques", "hips", "shoulders"), ("barbell+landmine",),
        "rotation_strength", "controlled", "unilateral", "intermediate",
        ("rotational strength", "base"), "Control the range; avoid twisting only through the low back.",
    ),
    ExerciseData(
        "rotational-landmine-press", "Rotational Landmine Press", ("landmine rotational press",),
        "power", "rotation", "transverse", "power", "full_body",
        ("hips", "obliques", "delts", "triceps"), ("barbell+landmine",),
        "rotational_press", "ballistic", "unilateral", "intermediate",
        ("rotational power", "posting strength"), None,
    ),
    ExerciseData(
        "cable-woodchop", "Cable Woodchop", ("cable chop",),
        "strength", "rotation", "transverse", "strength", "core",
        ("obliques", "hips"), ("cable",),
        "rotation_strength", "controlled", "unilateral", "beginner",
        ("rotational strength",), None,
    ),
    ExerciseData(
        "band-rotation", "Band Rotation", ("banded rotation",),
        "strength", "rotation", "transverse", "strength", "core",
        ("obliques", "hips"), ("resistance_band",),
        "rotation_strength", "controlled", "unilateral", "beginner",
        ("rotational strength",), None,
    ),
    ExerciseData(
        "medicine-ball-rotational-throw", "Medicine-Ball Rotational Throw", ("rotational wall throw",),
        "power", "rotation", "transverse", "power", "full_body",
        ("hips", "obliques", "shoulders"), ("medicine_ball+wall",),
        "rotation_power", "ballistic", "unilateral", "intermediate",
        ("rotational power",), "Requires a safe wall and non-bouncing throwing area.",
    ),
    ExerciseData(
        "pallof-press", "Pallof Press", (),
        "strength", "anti_rotation", "transverse", "stability", "core",
        ("obliques", "deep core"), ("cable", "resistance_band"),
        "anti_rotation", "isometric", "unilateral", "beginner",
        ("base", "posture"), None,
    ),
    ExerciseData(
        "side-plank", "Side Plank", (),
        "strength", "trunk_stability", "frontal", "stability", "core",
        ("obliques", "glute medius"), ("bodyweight",),
        "lateral_trunk_stability", "isometric", "unilateral", "beginner",
        ("base", "posture"), None,
    ),
    ExerciseData(
        "dead-bug", "Dead Bug", (),
        "strength", "trunk_stability", "sagittal", "stability", "core",
        ("deep core", "hip flexors"), ("bodyweight",),
        "anterior_trunk_stability", "controlled", "alternating", "beginner",
        ("base", "posture"), None,
    ),
    ExerciseData(
        "hanging-knee-raise", "Hanging Knee Raise", (),
        "strength", "trunk_flexion", "sagittal", "hypertrophy", "core",
        ("abs", "hip flexors"), ("pull_up_bar+bodyweight",),
        "hip_flexion_core", "controlled", "bilateral", "intermediate",
        ("trunk control", "grip"), None,
    ),
    ExerciseData(
        "lying-leg-raise", "Lying Leg Raise", (),
        "strength", "trunk_flexion", "sagittal", "hypertrophy", "core",
        ("abs", "hip flexors"), ("bodyweight",),
        "hip_flexion_core", "controlled", "bilateral", "beginner",
        ("trunk control",), None,
    ),
    ExerciseData(
        "farmer-carry", "Farmer Carry", ("farmers walk",),
        "strength", "carry", "sagittal", "strength", "full_body",
        ("forearms", "traps", "core"), ("dumbbell", "kettlebell"),
        "bilateral_carry", "controlled", "bilateral", "beginner",
        ("grip", "posture", "conditioning"), None,
    ),
    ExerciseData(
        "suitcase-carry", "Suitcase Carry", (),
        "strength", "carry", "sagittal", "stability", "full_body",
        ("forearms", "obliques", "traps"), ("dumbbell", "kettlebell"),
        "unilateral_carry", "controlled", "unilateral", "beginner",
        ("grip", "anti-lateral-flexion", "base"), None,
    ),
    ExerciseData(
        "front-rack-kettlebell-carry", "Front-Rack Kettlebell Carry", ("KB rack carry",),
        "strength", "carry", "sagittal", "stability", "full_body",
        ("core", "upper back", "forearms"), ("kettlebell",),
        "front_loaded_carry", "controlled", "unilateral", "intermediate",
        ("posture", "grip", "base"), None,
    ),
    ExerciseData(
        "bottoms-up-kettlebell-carry", "Bottoms-Up Kettlebell Carry", ("bottoms-up carry",),
        "skill", "carry", "sagittal", "stability", "upper",
        ("forearms", "shoulders", "core"), ("kettlebell",),
        "shoulder_stability_carry", "controlled", "unilateral", "advanced",
        ("grip", "shoulder stability"), "Use light loads and stop before grip failure.",
    ),
    ExerciseData(
        "sandbag-bear-hug-carry", "Sandbag Bear-Hug Carry", ("bear-hug carry",),
        "strength", "carry", "sagittal", "strength", "full_body",
        ("upper back", "arms", "core", "legs"), ("sandbag",),
        "front_loaded_carry", "controlled", "bilateral", "beginner",
        ("clinch", "posture", "conditioning"), None,
    ),
    ExerciseData(
        "zercher-carry", "Zercher Carry", (),
        "strength", "carry", "sagittal", "strength", "full_body",
        ("upper back", "arms", "core", "legs"), ("barbell",),
        "front_loaded_carry", "controlled", "bilateral", "advanced",
        ("clinch", "posture"), "Use conservative loads and protect the elbow crease.",
    ),
    ExerciseData(
        "sled-push", "Sled Push", ("prowler push",),
        "conditioning", "locomotion", "sagittal", "conditioning", "full_body",
        ("quads", "glutes", "calves"), ("sled",),
        "sled_drive", "controlled", "bilateral", "beginner",
        ("drive", "conditioning", "base"), None,
    ),
    ExerciseData(
        "backward-sled-drag", "Backward Sled Drag", ("reverse sled drag",),
        "conditioning", "locomotion", "sagittal", "conditioning", "lower",
        ("quads", "calves"), ("sled",),
        "sled_drive", "controlled", "bilateral", "beginner",
        ("drive", "conditioning", "knee capacity"), None,
    ),
    ExerciseData(
        "bear-crawl", "Bear Crawl", (),
        "conditioning", "locomotion", "multiplanar", "conditioning", "full_body",
        ("shoulders", "core", "hips"), ("bodyweight",),
        "ground_locomotion", "controlled", "alternating", "beginner",
        ("ground movement", "shoulder endurance"), None,
    ),
    ExerciseData(
        "sprawl", "Sprawl", ("wrestling sprawl",),
        "skill", "locomotion", "sagittal", "skill", "full_body",
        ("hips", "chest", "legs"), ("bodyweight",),
        "wrestling_movement", "ballistic", "bilateral", "intermediate",
        ("takedown defense", "conditioning"), "Use an appropriate surface and progress volume gradually.",
    ),
    ExerciseData(
        "penetration-step", "Penetration Step", ("wrestling shot entry",),
        "skill", "locomotion", "sagittal", "skill", "lower",
        ("quads", "glutes", "hips"), ("bodyweight",),
        "wrestling_movement", "controlled", "alternating", "intermediate",
        ("takedown entry", "level change"), "Use knee-friendly flooring and sound technique.",
    ),
    ExerciseData(
        "towel-dead-hang", "Towel Dead Hang", ("gi dead hang",),
        "strength", "grip", "sagittal", "strength", "upper",
        ("forearms", "hands", "lats"), ("pull_up_bar+towel", "pull_up_bar+gi"),
        "grip_isometric", "isometric", "bilateral", "intermediate",
        ("gi grip",), "Progress duration gradually; stop for elbow or finger pain.",
    ),
    ExerciseData(
        "four-way-neck-isometric", "Four-Way Neck Isometric", ("neck isometric holds",),
        "strength", "neck", "multiplanar", "stability", "neck",
        ("neck flexors", "neck extensors", "lateral neck"), ("hands", "resistance_band"),
        "neck_isometric", "isometric", "not_applicable", "beginner",
        ("neck strength",), "Use gentle progressive resistance; stop for neurological symptoms.",
    ),
    ExerciseData(
        "wrestler-bridge", "Wrestler Bridge", ("neck bridge",),
        "skill", "neck", "sagittal", "strength", "neck",
        ("neck extensors", "upper back"), ("bodyweight+mat",),
        "neck_dynamic", "controlled", "bilateral", "advanced",
        ("wrestling",), "Never auto-program. Requires coaching and an appropriate neck-training history.",
    ),
    ExerciseData(
        "stationary-bike-zone-2", "Stationary Bike Zone 2", ("easy bike",),
        "conditioning", "cyclical", "sagittal", "conditioning", "lower",
        ("quads", "glutes"), ("stationary_bike",),
        "low_impact_aerobic", "cyclical", "bilateral", "beginner",
        ("aerobic base", "recovery"), None,
    ),
    ExerciseData(
        "stationary-bike-intervals", "Stationary Bike Intervals", ("bike sprints",),
        "conditioning", "cyclical", "sagittal", "conditioning", "lower",
        ("quads", "glutes"), ("stationary_bike",),
        "low_impact_intervals", "cyclical", "bilateral", "intermediate",
        ("repeat effort", "conditioning"), None,
    ),
    ExerciseData(
        "rower-zone-2", "Rower Zone 2", ("easy row",),
        "conditioning", "cyclical", "sagittal", "conditioning", "full_body",
        ("legs", "back", "arms"), ("rowing_machine",),
        "low_impact_aerobic", "cyclical", "bilateral", "beginner",
        ("aerobic base",), None,
    ),
    ExerciseData(
        "rower-intervals", "Rower Intervals", (),
        "conditioning", "cyclical", "sagittal", "conditioning", "full_body",
        ("legs", "back", "arms"), ("rowing_machine",),
        "low_impact_intervals", "cyclical", "bilateral", "intermediate",
        ("repeat effort", "conditioning"), None,
    ),
)

BJJ_FAILURE_SEED: tuple[BjjFailureTypeData, ...] = (
    BjjFailureTypeData("grip_lost", "Grip lost", "Required grip was lost before the action could continue."),
    BjjFailureTypeData("frame_late", "Frame late", "Frame was established after pressure or control was already secured."),
    BjjFailureTypeData("posture_broken", "Posture broken", "Opponent controlled or collapsed posture."),
    BjjFailureTypeData("bad_angle", "Bad angle", "Body alignment or angle prevented the technique from working."),
    BjjFailureTypeData("off_balance_failed", "Could not off-balance", "Kuzushi or weight shift was insufficient."),
    BjjFailureTypeData("technique_forgotten", "Technique forgotten", "The next technical step was not recalled."),
    BjjFailureTypeData("poor_decision", "Poor decision", "A known but inappropriate option was selected."),
    BjjFailureTypeData("strength_limited", "Strength limited", "Required force could not be produced despite sound position."),
    BjjFailureTypeData("cardio_limited", "Cardio limited", "General fatigue caused a clear performance drop."),
    BjjFailureTypeData("grip_fatigue", "Grip fatigue", "Forearm or hand fatigue caused repeated grip failure."),
    BjjFailureTypeData("opponent_skill", "Opponent technically better", "Opponent consistently won the exchange through superior technique."),
    BjjFailureTypeData("other", "Other", "Failure does not fit an existing category; note is required."),
)


def _equipment_matches(required: str, available: frozenset[str]) -> bool:
    """Check if a single equipment setup (e.g. 'barbell+bench') is satisfied.
    
    Treats 'bodyweight' as always available.
    """
    parts = required.split("+")
    for part in parts:
        if part == "bodyweight":
            continue
        if part not in available:
            return False
    return True


def _any_equipment_matches(setups: tuple[str, ...], available: frozenset[str]) -> bool:
    """Check if any equipment setup from the list is available."""
    if not setups:
        return True
    return any(_equipment_matches(setup, available) for setup in setups)


@dataclass
class AlternativesRequest:
    source_exercise_slug: str
    available_equipment: frozenset[str] = field(default_factory=frozenset)
    excluded_exercises: frozenset[str] = field(default_factory=frozenset)
    limitations: frozenset[str] = field(default_factory=frozenset)
    max_results: int = 5
    allow_advanced: bool = False


class ExerciseLibraryService:
    """Service for exercise library operations and alternatives engine."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def seed_if_empty(self) -> int:
        """Seed the exercise library if empty. Returns count of exercises seeded."""
        with self._session_factory() as session:
            existing = session.scalar(select(Exercise).limit(1))
            if existing is not None:
                return 0
            return self._seed(session)

    def _seed(self, session: Session) -> int:
        now = datetime.now(UTC)
        for data in EXERCISE_SEED:
            exercise = Exercise(
                slug=data.slug,
                name=data.name,
                aliases=list(data.aliases),
                category=data.category,
                movement_pattern=data.movement_pattern,
                plane=data.plane,
                training_intent=data.training_intent,
                primary_region=data.primary_region,
                primary_muscles=list(data.primary_muscles),
                equipment=list(data.equipment),
                substitution_group=data.substitution_group,
                movement_speed=data.movement_speed,
                laterality=data.laterality,
                difficulty=data.difficulty,
                bjj_tags=list(data.bjj_tags),
                risk_notes=data.risk_notes,
                is_active=True,
                created_at=now,
                updated_at=now,
            )
            session.add(exercise)

        for failure in BJJ_FAILURE_SEED:
            session.add(BjjFailureType(
                code=failure.code,
                label=failure.label,
                description=failure.description,
            ))

        session.commit()
        return len(EXERCISE_SEED)

    def list_exercises(
        self,
        *,
        search: str | None = None,
        pattern: str | None = None,
        intent: str | None = None,
        region: str | None = None,
        equipment: str | None = None,
        bjj_tag: str | None = None,
        substitution_group: str | None = None,
        category: str | None = None,
        active_only: bool = True,
    ) -> list[dict]:
        """List and filter exercises."""
        with self._session_factory() as session:
            query = select(Exercise)
            if active_only:
                query = query.where(Exercise.is_active == True)
            if pattern:
                query = query.where(Exercise.movement_pattern == pattern)
            if intent:
                query = query.where(Exercise.training_intent == intent)
            if region:
                query = query.where(Exercise.primary_region == region)
            if substitution_group:
                query = query.where(Exercise.substitution_group == substitution_group)
            if category:
                query = query.where(Exercise.category == category)

            exercises = list(session.scalars(query).all())

        if equipment:
            exercises = [e for e in exercises if equipment in " ".join(e.equipment)]
        if bjj_tag:
            exercises = [e for e in exercises if bjj_tag.lower() in " ".join(e.bjj_tags).lower()]
        if search:
            search_lower = search.lower()
            exercises = [
                e for e in exercises
                if search_lower in e.name.lower()
                or search_lower in e.slug.lower()
                or any(search_lower in alias.lower() for alias in e.aliases)
            ]

        return [self._exercise_to_dict(e) for e in exercises]

    def get_exercise(self, slug: str) -> dict | None:
        """Get a single exercise by slug."""
        with self._session_factory() as session:
            exercise = session.get(Exercise, slug)
            if exercise is None:
                return None
            return self._exercise_to_dict(exercise)

    def get_bjj_failure_types(self) -> list[dict]:
        """Get all BJJ failure types."""
        with self._session_factory() as session:
            failures = session.scalars(select(BjjFailureType)).all()
            return [
                {"code": f.code, "label": f.label, "description": f.description}
                for f in failures
            ]

    def find_alternatives(self, request: AlternativesRequest) -> AlternativesResponse:
        """Find alternative exercises using the deterministic algorithm from spec section 8."""
        with self._session_factory() as session:
            source = session.get(Exercise, request.source_exercise_slug)
            if source is None:
                return AlternativesResponse(source=request.source_exercise_slug, alternatives=())

            overrides = self._get_overrides(session, request.source_exercise_slug)
            candidates = list(session.scalars(
                select(Exercise).where(Exercise.is_active == True)
            ).all())

        eligible = []
        for candidate in candidates:
            rejection = self._check_eligibility(
                source, candidate, request, overrides
            )
            if rejection is None:
                eligible.append(candidate)

        scored = []
        for candidate in eligible:
            score, reasons = self._score_alternative(source, candidate, overrides)
            tradeoff = candidate.risk_notes
            if candidate.difficulty == "advanced" and source.difficulty != "advanced":
                tradeoff = tradeoff or "This is an advanced exercise."
            if source.movement_speed == "controlled" and candidate.movement_speed == "ballistic":
                tradeoff = "Ballistic; not a direct substitute for controlled strength work."
            if self._is_loading_limited(candidate):
                tradeoff = tradeoff or "Loading may become the limiting factor."
            scored.append(AlternativeResult(
                slug=candidate.slug,
                name=candidate.name,
                score=score,
                why=tuple(reasons),
                tradeoff=tradeoff,
            ))

        scored.sort(key=lambda x: (-x.score, x.name))
        top = scored[:request.max_results]

        return AlternativesResponse(source=source.slug, alternatives=tuple(top))

    def _check_eligibility(
        self,
        source: Exercise,
        candidate: Exercise,
        request: AlternativesRequest,
        overrides: dict[str, str],
    ) -> str | None:
        """Return rejection reason or None if eligible. Implements spec 8.2."""
        if not candidate.is_active:
            return "inactive"
        if candidate.slug == source.slug:
            return "same_exercise"
        if not _any_equipment_matches(tuple(candidate.equipment), request.available_equipment):
            return "equipment_unavailable"
        if overrides.get(candidate.slug) == "exclude":
            return "user_excluded"
        if candidate.slug in request.excluded_exercises:
            return "explicitly_excluded"

        for limit in request.limitations:
            if limit == "no_overhead" and candidate.movement_pattern == "vertical_push":
                return "limitation_no_overhead"
            if limit == "no_high_impact" and candidate.movement_speed == "ballistic":
                return "limitation_no_high_impact"
            if limit == candidate.slug:
                return "limitation_blocked_exercise"

        same_group = candidate.substitution_group == source.substitution_group
        same_pattern = candidate.movement_pattern == source.movement_pattern
        if not same_group and not same_pattern:
            return "no_group_or_pattern_match"

        if source.training_intent == "strength" and source.movement_speed == "controlled":
            if candidate.movement_speed == "ballistic" and candidate.training_intent == "power":
                return "controlled_to_ballistic_power"

        if source.training_intent == "power" and candidate.movement_speed == "isometric":
            return "power_to_isometric"

        if source.movement_pattern == "rotation" and candidate.movement_pattern == "anti_rotation":
            return "rotation_to_anti_rotation"
        if source.movement_pattern == "anti_rotation" and candidate.movement_pattern == "rotation":
            return "anti_rotation_to_rotation"

        if candidate.difficulty == "advanced" and not request.allow_advanced:
            return "advanced_not_enabled"

        return None

    def _score_alternative(
        self,
        source: Exercise,
        candidate: Exercise,
        overrides: dict[str, str],
    ) -> tuple[int, list[str]]:
        """Score an eligible alternative. Implements spec 8.3."""
        score = 0
        reasons = []

        if candidate.substitution_group == source.substitution_group:
            score += 50
            reasons.append(f"same {source.substitution_group} substitution group")
        if candidate.movement_pattern == source.movement_pattern:
            score += 25
            reasons.append(f"same {source.movement_pattern} pattern")
        if candidate.training_intent == source.training_intent:
            score += 10
            reasons.append(f"same {source.training_intent} intent")
        if candidate.primary_region == source.primary_region:
            score += 5
            reasons.append(f"same {source.primary_region} region")
        if candidate.laterality == source.laterality:
            score += 5
            reasons.append(f"same {source.laterality} laterality")
        if overrides.get(candidate.slug) == "prefer":
            score += 5
            reasons.append("user preference")

        if candidate.movement_speed != source.movement_speed:
            score -= 15
        if candidate.training_intent != source.training_intent:
            score -= 10

        return score, reasons

    def _get_overrides(self, session: Session, source_slug: str) -> dict[str, str]:
        """Get user overrides for a source exercise."""
        query = select(ExerciseSubstitutionOverride).where(
            ExerciseSubstitutionOverride.source_exercise_slug == source_slug
        )
        overrides = session.scalars(query).all()
        return {o.target_exercise_slug: o.decision for o in overrides}

    def _is_loading_limited(self, exercise: Exercise) -> bool:
        """Check if exercise has loading limitations."""
        limited_slugs = {"goblet-squat", "kettlebell-deadlift"}
        return exercise.slug in limited_slugs

    def set_override(
        self,
        source_slug: str,
        target_slug: str,
        decision: Literal["prefer", "allow", "exclude"],
        reason: str | None = None,
    ) -> dict:
        """Set or update a user override for exercise substitution."""
        if source_slug == target_slug:
            raise ValueError("Source and target exercise cannot be the same.")
        if decision not in ("prefer", "allow", "exclude"):
            raise ValueError(f"Invalid decision: {decision}")

        with self._session_factory() as session:
            source = session.get(Exercise, source_slug)
            if source is None:
                raise KeyError(f"Source exercise not found: {source_slug}")
            target = session.get(Exercise, target_slug)
            if target is None:
                raise KeyError(f"Target exercise not found: {target_slug}")

            existing = session.scalar(
                select(ExerciseSubstitutionOverride).where(
                    ExerciseSubstitutionOverride.source_exercise_slug == source_slug,
                    ExerciseSubstitutionOverride.target_exercise_slug == target_slug,
                )
            )

            now = datetime.now(UTC)
            if existing:
                existing.decision = decision
                existing.reason = reason
            else:
                override = ExerciseSubstitutionOverride(
                    source_exercise_slug=source_slug,
                    target_exercise_slug=target_slug,
                    decision=decision,
                    reason=reason,
                    created_at=now,
                )
                session.add(override)

            session.commit()

            return {
                "source": source_slug,
                "target": target_slug,
                "decision": decision,
                "reason": reason,
            }

    def delete_override(self, source_slug: str, target_slug: str) -> bool:
        """Delete a user override. Returns True if deleted, False if not found."""
        with self._session_factory() as session:
            existing = session.scalar(
                select(ExerciseSubstitutionOverride).where(
                    ExerciseSubstitutionOverride.source_exercise_slug == source_slug,
                    ExerciseSubstitutionOverride.target_exercise_slug == target_slug,
                )
            )
            if existing is None:
                return False
            session.delete(existing)
            session.commit()
            return True

    def get_overrides(self, source_slug: str | None = None) -> list[dict]:
        """Get user overrides, optionally filtered by source exercise."""
        with self._session_factory() as session:
            query = select(ExerciseSubstitutionOverride)
            if source_slug:
                query = query.where(
                    ExerciseSubstitutionOverride.source_exercise_slug == source_slug
                )
            overrides = session.scalars(query).all()
            return [
                {
                    "source": o.source_exercise_slug,
                    "target": o.target_exercise_slug,
                    "decision": o.decision,
                    "reason": o.reason,
                }
                for o in overrides
            ]

    def _exercise_to_dict(self, exercise: Exercise) -> dict:
        return {
            "slug": exercise.slug,
            "name": exercise.name,
            "aliases": list(exercise.aliases),
            "category": exercise.category,
            "movement_pattern": exercise.movement_pattern,
            "plane": exercise.plane,
            "training_intent": exercise.training_intent,
            "primary_region": exercise.primary_region,
            "primary_muscles": list(exercise.primary_muscles),
            "equipment": list(exercise.equipment),
            "substitution_group": exercise.substitution_group,
            "movement_speed": exercise.movement_speed,
            "laterality": exercise.laterality,
            "difficulty": exercise.difficulty,
            "bjj_tags": list(exercise.bjj_tags),
            "risk_notes": exercise.risk_notes,
            "is_active": exercise.is_active,
        }


def get_filter_options() -> dict:
    """Get all valid filter option values for the exercise library."""
    return {
        "categories": sorted(CATEGORIES),
        "movement_patterns": sorted(MOVEMENT_PATTERNS),
        "planes": sorted(PLANES),
        "training_intents": sorted(TRAINING_INTENTS),
        "primary_regions": sorted(PRIMARY_REGIONS),
        "movement_speeds": sorted(MOVEMENT_SPEEDS),
        "lateralities": sorted(LATERALITIES),
        "difficulties": sorted(DIFFICULTIES),
        "equipment_tokens": sorted(CANONICAL_EQUIPMENT_TOKENS),
    }
