from app.domain.training import strength_progress as sp
from app.domain.training.types import ExercisePrescription as E
from app.domain.training.types import WorkoutTemplate, WorkoutType

# Entries inside the strength templates that the progression engine never
# touches (warm-up and conditioning — no load/rep target to track).
STRENGTH_SKIP = {
    "Stationary bike warm-up", "Stationary bike intervals", "Easy cardio",
}

# October 2026 program (Heavy Strength A / Athletic Strength B). Loads are
# starting targets, not mandatory weights; the first logged actual load
# replaces them (TrainingService._advance_strength_progress).
_RESERVE = "RPE 7–8: stop with 2–3 good reps left. Never to failure."
_START = "Starting target — log the load you actually used."

WORKOUT_TEMPLATES: dict[WorkoutType, WorkoutTemplate] = {
    WorkoutType.STRENGTH_A: WorkoutTemplate(
        WorkoutType.STRENGTH_A,
        "Gym (Strength A)",
        55,
        "hard",
        (
            E("Stationary bike warm-up", duration_seconds=5 * 60, notes="Easy"),
            E("Trap-bar Deadlift", 125, "kg", 3, "3–4", notes=f"Heavy strength. {_RESERVE} Up to 130 kg on a good day."),
            E("Dumbbell Bench Press", 30, "kg/hand", 3, "6–8", notes=_RESERVE),
            E("Bulgarian Split Squat", 14, "kg/hand", 3, "6–8/leg", notes="Unilateral stability; control the descent."),
            E("Cable Row", None, "kg", 3, "8–10", notes=f"RPE 7–8. {_START}"),
            E("Pallof Press", None, "kg", 3, "10/side", notes=f"Moderate; no rotation. {_START}"),
            E("Cable Face Pull", None, "kg", 3, "12–15", notes=f"RPE 7, shoulder health. {_START}"),
            E("Easy cardio", duration_seconds=20 * 60, notes="Optional finisher for the cut: 20–30 min conversational pace. Counts as a weekly cardio session."),
        ),
        "Optional 20–30 minutes easy cardio after lifting; conversational pace, no intervals.",
    ),
    WorkoutType.STRENGTH_B: WorkoutTemplate(
        WorkoutType.STRENGTH_B,
        "Gym (Strength B)",
        50,
        "normal",
        (
            E("Stationary bike warm-up", duration_seconds=5 * 60, notes="Easy"),
            E("Kettlebell Swing", None, "kg", 3, "8", notes=f"Explosive hips, crisp reps; moderate bell. {_START}"),
            E("Front Squat", 90, "kg", 3, "4–5", notes=f"Work up to 90 kg. {_RESERVE}"),
            E("Military Press", 52, "kg", 3, "5", notes=f"Work up to 52 kg. {_RESERVE}"),
            E("Weighted Pull-up", 5, "kg added", 3, "5–6", notes="Bodyweight + 5 kg."),
            E("Romanian Deadlift", 100, "kg", 2, "6", notes="Work up to 100 kg."),
            E("Hanging Knee Raise", sets=3, reps="8–12", notes="Bodyweight. Or lying leg raise if hanging isn't practical."),
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
    WorkoutType.STRENGTH_A: {"Stationary bike warm-up", "Trap-bar Deadlift", "Dumbbell Bench Press", "Cable Row"},
    WorkoutType.STRENGTH_B: {"Stationary bike warm-up", "Front Squat", "Military Press", "Weighted Pull-up"},
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
