from app.domain.training.types import ExercisePrescription as E
from app.domain.training.types import WorkoutTemplate, WorkoutType


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
            E("Deadlift", 120, "kg", 2, "3"),
            E("Military Press", 40, "kg", 3, "5"),
            E("Pull-ups", sets=3, reps="6–8", notes="Bodyweight"),
            E("Weighted Dips", 10, "kg", 2, "8"),
            E("Copenhagen Plank", sets=3, reps="20–30 sec/side"),
            E("Suitcase Carry", sets=3, reps="30–45 sec/side", notes="Heavy DB/KB"),
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
}


def reduced_template(workout_type: WorkoutType) -> WorkoutTemplate:
    base = WORKOUT_TEMPLATES[workout_type]
    if workout_type == WorkoutType.STRENGTH_A:
        keep = {"Stationary bike warm-up", "Back Squat", "Bench Press", "Pull-ups", "Standing Landmine Rotation"}
    else:
        keep = {"Deadlift", "Military Press", "Pull-ups", "Copenhagen Plank"}
    exercises = tuple(
        E(
            item.name, item.load_value, item.load_unit,
            1 if item.name == "Deadlift" else min(item.sets or 2, 2),
            item.reps, item.duration_seconds, "Taper: leave substantial reserve",
        )
        for item in base.exercises if item.name in keep
    )
    return WorkoutTemplate(base.type, f"{base.title} · taper", 35, "normal", exercises)
