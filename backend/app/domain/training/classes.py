from datetime import time

from app.domain.training.types import ClassTemplate, ClassType

MITA_GYM_ID = "mita"

# Explicit recurring classes. Never inferred from weekday alone.
MITA_CLASS_TEMPLATE: tuple[ClassTemplate, ...] = (
    ClassTemplate(0, time(7, 30), ClassType.NORMAL, MITA_GYM_ID),
    ClassTemplate(1, time(7, 30), ClassType.NORMAL, MITA_GYM_ID),
    ClassTemplate(2, time(7, 30), ClassType.NORMAL, MITA_GYM_ID),
    ClassTemplate(3, time(7, 30), ClassType.NORMAL, MITA_GYM_ID),
    ClassTemplate(5, time(10, 0), ClassType.COMPETITION, MITA_GYM_ID),
)


def template_from_json(rows: list | None) -> tuple[ClassTemplate, ...]:
    if not rows:
        return MITA_CLASS_TEMPLATE
    parsed = []
    for item in rows:
        parsed.append(ClassTemplate(
            int(item["weekday"]),
            time.fromisoformat(item["start_time"]),
            ClassType(item["class_type"]),
            item.get("gym_id") or MITA_GYM_ID,
        ))
    return tuple(parsed)


def template_to_json(rows: tuple[ClassTemplate, ...] = MITA_CLASS_TEMPLATE) -> list[dict]:
    return [
        {
            "weekday": item.weekday,
            "start_time": item.start_time.strftime("%H:%M:%S"),
            "class_type": item.class_type.value,
            "gym_id": item.gym_id,
        }
        for item in rows
    ]
