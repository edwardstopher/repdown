"""Serialization and CSV export for Repdown workouts."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any, Iterable


def serialize_repdown(workout: dict[str, Any]) -> str:
    """Serialize a workout dictionary to readable Repdown text."""

    _require_keys(workout, ["date", "title", "metadata", "exercises"], "workout")

    lines: list[str] = [str(workout["date"])]
    title = workout.get("title")
    if title is not None:
        lines.append(str(title))
    lines.append("")

    metadata = workout.get("metadata") or {}
    for key, value in metadata.items():
        lines.append(f"{key}: {value}")
    if metadata:
        lines.append("")

    exercises = workout.get("exercises") or []
    for exercise_index, exercise in enumerate(exercises):
        _require_keys(exercise, ["name", "sets"], "exercise")
        if exercise_index > 0:
            lines.append("")
        lines.append(str(exercise["name"]))
        for group in _group_sets(exercise.get("sets") or []):
            lines.append(_serialize_set_group(group))

    return "\n".join(lines).rstrip() + "\n"


def to_csv(workout: dict[str, Any]) -> str:
    """Export a workout dictionary as CSV text."""

    output = StringIO()
    fieldnames = ["date", "exercise", "set_index", "weight", "reps", "rpe", "type"]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    workout_date = workout.get("date", "")
    for exercise in workout.get("exercises", []):
        exercise_name = exercise.get("name", "")
        for index, set_entry in enumerate(exercise.get("sets", []), start=1):
            writer.writerow(
                {
                    "date": workout_date,
                    "exercise": exercise_name,
                    "set_index": index,
                    "weight": _weight_token(set_entry),
                    "reps": set_entry.get("reps", ""),
                    "rpe": _blank_if_none(set_entry.get("rpe")),
                    "type": _blank_if_none(set_entry.get("type")),
                }
            )

    return output.getvalue()


def _group_sets(sets: Iterable[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    groups: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_key: tuple[Any, ...] | None = None

    for set_entry in sets:
        key = _group_key(set_entry)
        if current and key != current_key:
            groups.append(current)
            current = []
        current.append(set_entry)
        current_key = key

    if current:
        groups.append(current)

    return groups


def _group_key(set_entry: dict[str, Any]) -> tuple[Any, ...]:
    return (
        set_entry.get("weight"),
        set_entry.get("unit"),
        set_entry.get("bodyweight"),
        set_entry.get("rpe"),
        set_entry.get("rest_seconds"),
        set_entry.get("tempo"),
        set_entry.get("type"),
    )


def _serialize_set_group(group: list[dict[str, Any]]) -> str:
    first = group[0]
    reps = ", ".join(_format_number(set_entry["reps"]) for set_entry in group)
    parts = [_weight_token(first), "x", reps]

    rpe = first.get("rpe")
    if rpe is not None:
        parts.append(f"@{_format_number(rpe)}")

    rest_seconds = first.get("rest_seconds")
    if rest_seconds is not None:
        parts.append(f"r={rest_seconds}s")

    tempo = first.get("tempo")
    if tempo is not None:
        parts.append(f"t={tempo}")

    set_type = first.get("type")
    if set_type is not None:
        parts.append(str(set_type))

    return " ".join(parts)


def _weight_token(set_entry: dict[str, Any]) -> str:
    bodyweight = bool(set_entry.get("bodyweight"))
    weight = set_entry.get("weight")
    unit = set_entry.get("unit")

    if bodyweight:
        if weight is None:
            return "BW"
        if not unit:
            raise ValueError("loaded bodyweight sets require a unit")
        return f"BW+{_format_number(weight)}{unit}"

    if weight is None:
        raise ValueError("non-bodyweight sets require a weight")

    suffix = unit or ""
    return f"{_format_number(weight)}{suffix}"


def _format_number(value: Any) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def _blank_if_none(value: Any) -> Any:
    return "" if value is None else value


def _require_keys(value: dict[str, Any], keys: list[str], name: str) -> None:
    missing = [key for key in keys if key not in value]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"{name} is missing required key(s): {joined}")
