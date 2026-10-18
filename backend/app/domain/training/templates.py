from app.domain.training import strength_progress as sp
from app.domain.training.types import ExercisePrescription as E
from app.domain.training.types import WorkoutTemplate, WorkoutType

# Entries inside the strength templates that the progression engine never
# touches (conditioning, carries, isometrics — no load/rep target to track).
STRENGTH_SKIP = {
    "Stationary bike warm-up", "Stationary bike intervals", "Easy cardio",
    "Suitcase Carry", "Farmer Carry", "Neck Isometric Holds", "Side Plank",
}

# March 2027 plan. Starting loads are estimates from the last logged lifts
# (deadlift 142.5×3, back squat 122.5×3, bench 87.5×3, row 60×9); the first
# logged actual load replaces them (TrainingService._advance_strength_progress).
_ESTIMATE = "Starting estimate — log the load you actually used."
_RESERVE = "Stop with about two good reps left. Never to failure."

WORKOUT_TEMPLATES: dict[WorkoutType, WorkoutTemplate] = {
    WorkoutType.STRENGTH_A: WorkoutTemplate(
        WorkoutType.STRENGTH_A,
        "Gym (Strength A)",
        75,
        "hard",
        (
            E("Stationary bike warm-up", duration_seconds=6 * 60, notes="Easy"),
            E("Trap-bar Deadlift", 125, "kg", 3, "4–6", notes=f"{_RESERVE} {_ESTIMATE}"),
            E("Dumbbell Bench Press", 30, "kg/hand", 3, "6–8", notes=f"Or weighted push-up. {_ESTIMATE}"),
            E("Bulgarian Split Squat", 14, "kg/hand", 2, "6–8/leg"),
            E("Chest-Supported Row", 24, "kg/hand", 3, "6–10", notes=_ESTIMATE),
            E("Suitcase Carry", 28, "kg", 2, "30–40 m/side", notes="Stay tall; no lean toward the bell."),
            E("Neck Isometric Holds", sets=2, reps="15–20 s each direction", notes="Front, back, both sides. Gentle pressure."),
            E("Easy cardio", duration_seconds=25 * 60, notes="20–30 min conversational pace: incline walk, bike, row, or swim. No sprints."),
        ),
        "20–30 minutes easy cardio after lifting; conversational pace, no intervals.",
    ),
    WorkoutType.STRENGTH_B: WorkoutTemplate(
        WorkoutType.STRENGTH_B,
        "Gym (Strength B)",
        55,
        "normal",
        (
            E("Stationary bike warm-up", duration_seconds=6 * 60, notes="Easy"),
            E("Front Squat", 90, "kg", 3, "4–6", notes=f"Or goblet squat. {_RESERVE} {_ESTIMATE}"),
            E("Romanian Deadlift", 100, "kg", 3, "6–8", notes=_ESTIMATE),
            E("Military Press", 52, "kg", 3, "6–8", notes="Or landmine press."),
            E("Pull-ups", sets=3, reps="6–10", notes="Bodyweight, or lat pulldown."),
            E("Farmer Carry", 32, "kg/hand", 3, "30–40 m"),
            E("Side Plank", sets=2, reps="30 s/side", notes="Or Pallof press, 2 × 10/side."),
        ),
    ),
    WorkoutType.ZONE_2: WorkoutTemplate(
        WorkoutType.ZONE_2,
        "Easy cardio (Zone 2)",
        35,
        "easy",
        (E("Zone 2 cardio", duration_seconds=35 * 60, notes="30–40 min conversational pace: incline walk, bike, row, or swim. Do not turn it into tempo."),),
    ),
    WorkoutType.GRIP: WorkoutTemplate(
        WorkoutType.GRIP,
        "Grip",
        10,
        "easy",
        (E("Towel kettlebell hold", 25, "lb", 3, "30 sec/hand", notes="Progress to 45 lb only when easy"),),
    ),
    WorkoutType.BJJ_NORMAL: WorkoutTemplate(
        WorkoutType.BJJ_NORMAL,
        "BJJ Normal",
        90,
        "normal",
        (
            E("Technical drilling", duration_seconds=20 * 60, notes="Class instruction"),
            E("Positional sparring", duration_seconds=20 * 60),
            E("Live rounds", sets=3, reps="5 min", notes="Record rounds, intensity, grip, and cardio"),
        ),
    ),
    WorkoutType.BJJ_HARD: WorkoutTemplate(
        WorkoutType.BJJ_HARD,
        "BJJ Competition / Hard",
        90,
        "hard",
        (
            E("Specific sparring", duration_seconds=20 * 60, notes="Competition positions"),
            E("Hard rounds", sets=5, reps="5 min", notes="Match pace; leave a round in the tank if quality drops"),
        ),
    ),
    WorkoutType.BJJ_TECHNICAL: WorkoutTemplate(
        WorkoutType.BJJ_TECHNICAL,
        "BJJ Technical",
        75,
        "easy",
        (
            E("Technique", duration_seconds=30 * 60),
            E("Light positional work", sets=2, reps="5 min"),
        ),
    ),
    WorkoutType.RECOVERY: WorkoutTemplate(
        WorkoutType.RECOVERY,
        "Recovery",
        30,
        "easy",
        (E("Easy mobility or walk", duration_seconds=20 * 60, notes="Stop if symptoms worsen"),),
    ),
}


def apply_adaptation(template: WorkoutTemplate, adaptation) -> WorkoutTemplate:
    if adaptation is None:
        return template
    exercises = []
    for item in template.exercises:
        load = item.load_value
        sets = item.sets
        duration = item.duration_seconds
        if template.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B} and load is not None:
            load = round(load * (1 + adaptation.strength_load_delta) * 2) / 2
        if template.type in {WorkoutType.STRENGTH_A, WorkoutType.STRENGTH_B} and sets is not None and adaptation.strength_volume_delta:
            sets = max(1, sets + (1 if adaptation.strength_volume_delta > 0 else -1 if adaptation.strength_volume_delta < 0 else 0))
        if template.type == WorkoutType.ZONE_2 and duration is not None:
            duration = max(20 * 60, duration + adaptation.zone2_minutes_delta * 60)
        if template.type == WorkoutType.GRIP and sets is not None:
            sets = max(1, sets + adaptation.grip_sets_delta)
        exercises.append(E(
            item.name, load, item.load_unit, sets, item.reps, duration, item.notes,
        ))
    return WorkoutTemplate(template.type, template.title, template.estimated_minutes, template.intensity, tuple(exercises), template.conditioning)


# Taper keeps the main lifts moderately heavy at low volume; accessories,
# carries and the cardio finisher drop out.
TAPER_KEEP = {
    WorkoutType.STRENGTH_A: {"Stationary bike warm-up", "Trap-bar Deadlift", "Dumbbell Bench Press", "Chest-Supported Row"},
    WorkoutType.STRENGTH_B: {"Stationary bike warm-up", "Front Squat", "Military Press", "Pull-ups"},
}


def taper_strength(workout_type: WorkoutType, exercises: tuple[E, ...]) -> WorkoutTemplate:
    base = WORKOUT_TEMPLATES[workout_type]
    keep = TAPER_KEEP[workout_type]
    reduced = tuple(
        item if item.name in STRENGTH_SKIP else E(
            item.name, item.load_value, item.load_unit,
            min(item.sets or 2, 2), item.reps, item.duration_seconds,
            "Taper: same load, short and sharp, leave substantial reserve",
        )
        for item in exercises if item.name in keep
    )
    return WorkoutTemplate(base.type, f"{base.title} · taper", 35, "normal", reduced)


def peak_strength(exercises: tuple[E, ...]) -> tuple[E, ...]:
    """Final six weeks: keep the weight moderately heavy, two working sets."""
    return tuple(
        item if item.name in STRENGTH_SKIP or item.sets is None else E(
            item.name, item.load_value, item.load_unit, min(item.sets, 2),
            item.reps, item.duration_seconds, item.notes,
        )
        for item in exercises
    )


def build_strength_exercises(
    workout_type: WorkoutType,
    progress: dict[str, sp.ExerciseState],
    *,
    deload: bool,
) -> tuple[E, ...]:
    """Per-exercise version of apply_adaptation for Strength A/B: each exercise
    renders from its own stored TrainingExerciseProgress state (or the template
    default the first time it's ever scheduled) instead of one blanket weekly
    delta applied to every exercise alike."""
    template = WORKOUT_TEMPLATES[workout_type]
    exercises: list[E] = []
    for item in template.exercises:
        if item.name in STRENGTH_SKIP:
            exercises.append(item)
            continue
        recipe = sp.recipe_for(item.name)
        state = progress.get(item.name) or sp.seed_state(
            workout_type.value, name=item.name, load_value=item.load_value,
            load_unit=item.load_unit, sets=item.sets, recipe=recipe,
        )
        if deload:
            state = sp.deload_prescription(state, recipe)
        exercises.append(E(
            state.exercise_name, state.load_value, state.load_unit, state.sets,
            sp.render_reps(state, recipe), item.duration_seconds, item.notes,
        ))
    return tuple(exercises)
