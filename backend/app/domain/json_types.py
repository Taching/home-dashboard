from __future__ import annotations

from typing import TypeAlias

JsonValue: TypeAlias = "None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]"
JsonDict: TypeAlias = dict[str, JsonValue]


def as_dict(value: JsonValue | None) -> JsonDict:
    return value if isinstance(value, dict) else {}


def as_list(value: JsonValue | None) -> list[JsonValue]:
    return value if isinstance(value, list) else []
