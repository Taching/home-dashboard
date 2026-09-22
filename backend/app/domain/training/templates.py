from app.domain.training import strength_progress as sp
from app.domain.training.types import ExercisePrescription as E
from app.domain.training.types import WorkoutTemplate, WorkoutType

# Conditioning entries inside the strength templates that the progression
# engine never touches (no working load/rep target to track).
STRENGTH_SKIP = {"Stationary bike warm-up", "Stationary bike intervals"}


WORKOUT_TEMPLATES: dict[WorkoutType, WorkoutTemplate] = {
    WorkoutType.STRENGTH_A: WorkoutTemplate(
        WorkoutType.STRENGTH_A,
        "Gym (Strength A)",
        60,
        "hard",
        (
            E("Stationary bike warm-up", duration_seconds=8 * 60, notes="Easy"),
            E("Back Squat", 120, "kg", 3, "3"),
            E("Bench Press", 85, "kg", 3, "3"),
            E("Pull-ups", sets=3, reps="6–8", notes="Bodyweight"),
            E("Bulgarian Split Squat", 14, "kg/hand", 2, "6/leg"),
            E("Standing Landmine Rotation", 20, "kg", 3, "8/side"),
            E("Stationary bike intervals", sets=10, reps="30 sec hard / 30 sec easy", notes="Repeatable output; record every round"),
        ),
        "10 × 30 seconds hard / 30 seconds easy; do not sprint the first round.",
    ),
    WorkoutType.STRENGTH_B: WorkoutTemplate(
        WorkoutType.STRENGTH_B,
        "Gym (Strength B)",
        55,
        "normal",
        (
            E("Deadlift", 140, "kg", 3, "3", notes="RPE 7–8. Rest 3–4 minutes."),
            E("Military Press", 52, "kg", 3, "5–7", notes="RPE 7–8."),
            E("Weighted Dips", 20, "kg", 3, "6–8"),
            E("Bulgarian Split Squat", None, None, 3, "6–8/leg", notes="Stability and depth before load."),
            E("Leg Raise", None, None, 3, "6–10", notes="Progress reps, not added weight."),
            E("Seated Cable Row", 60, "kg", 3, "8–12", notes="Controlled eccentric, no torso swing."),
        ),
    ),
    WorkoutType.ZONE_2: WorkoutTemplate(
        WorkoutType.ZONE_2,
        "Zone 2",
        45,
        "easy",
        (E("Zone 2 cardio", duration_seconds=45 * 60, notes="Conversation pace; do not turn it into tempo"),),
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


def reduced_template(workout_type: WorkoutType) -> WorkoutTemplate:
    base = WORKOUT_TEMPLATES[workout_type]
    if workout_type == WorkoutType.STRENGTH_A:
        keep = {"Stationary bike warm-up", "Back Squat", "Bench Press", "Pull-ups", "Standing Landmine Rotation"}
    else:
        keep = {"Deadlift", "Military Press", "Weighted Dips"}
    exercises = tuple(
        E(
            item.name, item.load_value, item.load_unit,
            1 if item.name == "Deadlift" else min(item.sets or 2, 2),
            item.reps, item.duration_seconds, "Taper: leave substantial reserve",
        )
        for item in base.exercises if item.name in keep
    )
    return WorkoutTemplate(base.type, f"{base.title} · taper", 35, "normal", exercises)


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
