"""Serialization and CSV export for Repdown workouts."""

from __future__ import annotations

import csv
from io import StringIO
from typing import Any, Iterable


def serialize_repdown(workout: dict[str, Any]) -> str:
    """Serialize a workout dictionary to Markdown-compatible Repdown text."""

    _require_keys(workout, ["date", "unit", "effort_type", "blocks"], "workout")

    default_unit = str(workout["unit"])
    effort_type = str(workout["effort_type"]).upper()
    lines: list[str] = []

    title = workout.get("title")
    if title:
        lines.append(f"# {title}")
        lines.append("")

    lines.append(f"Date: {workout['date']}  ")
    lines.append(f"Unit: {default_unit}  ")
    lines.append(f"Effort: {effort_type}")

    workout_notes = workout.get("notes") or []
    if workout_notes:
        lines.append("")
        _append_notes(lines, workout_notes)

    lines.append("")
    lines.append("## Exercises")

    blocks = workout.get("blocks") or []
    if not blocks:
        raise ValueError("workout must contain at least one block")

    for block in blocks:
        _append_block(lines, block, default_unit)

    return "\n".join(lines).rstrip() + "\n"


def to_csv(workout: dict[str, Any]) -> str:
    """Export a workout dictionary as CSV text."""

    output = StringIO()
    fieldnames = [
        "date",
        "block_type",
        "superset",
        "exercise",
        "set_index",
        "weight",
        "unit",
        "reps",
        "effort_type",
        "effort",
        "type",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()

    workout_date = workout.get("date", "")
    effort_type = workout.get("effort_type", "")
    for block in workout.get("blocks", []):
        block_type = block.get("type")
        if block_type == "exercise":
            _write_exercise_rows(
                writer,
                workout_date,
                effort_type,
                "exercise",
                "",
                block,
            )
            continue

        if block_type == "superset":
            superset_name = block.get("name", "")
            for exercise in block.get("exercises", []):
                _write_exercise_rows(
                    writer,
                    workout_date,
                    effort_type,
                    "superset",
                    superset_name,
                    exercise,
                )
            continue

        raise ValueError(f"unknown block type: {block_type}")

    return output.getvalue()


def _append_block(lines: list[str], block: dict[str, Any], default_unit: str) -> None:
    block_type = block.get("type")
    if block_type == "exercise":
        _require_keys(block, ["name", "sets"], "exercise block")
        lines.append("")
        lines.append(f"## {block['name']}")
        _append_sets_and_notes(
            lines,
            block.get("sets") or [],
            block.get("notes") or [],
            default_unit,
        )
        return

    if block_type == "superset":
        _require_keys(block, ["name", "exercises"], "superset block")
        lines.append("")
        lines.append(f"## Superset {block['name']}")
        superset_notes = block.get("notes") or []
        if superset_notes:
            lines.append("")
            _append_notes(lines, superset_notes)

        exercises = block.get("exercises") or []
        if not exercises:
            raise ValueError("superset block must contain at least one exercise")

        for exercise in exercises:
            _require_keys(exercise, ["name", "sets"], "superset exercise")
            lines.append("")
            lines.append(f"### {exercise['name']}")
            _append_sets_and_notes(
                lines,
                exercise.get("sets") or [],
                exercise.get("notes") or [],
                default_unit,
            )
        return

    raise ValueError(f"unknown block type: {block_type}")


def _append_sets_and_notes(
    lines: list[str],
    sets: list[dict[str, Any]],
    notes: list[str],
    default_unit: str,
) -> None:
    if not sets:
        raise ValueError("exercise must contain at least one set")

    lines.append("")
    for group in _group_sets(sets):
        lines.append(f"- {_serialize_set_group(group, default_unit)}")

    if notes:
        lines.append("")
        _append_notes(lines, notes)


def _append_notes(lines: list[str], notes: Iterable[Any]) -> None:
    for note in notes:
        lines.append(f"Notes: {note}")


def _write_exercise_rows(
    writer: csv.DictWriter,
    workout_date: Any,
    effort_type: Any,
    block_type: str,
    superset_name: Any,
    exercise: dict[str, Any],
) -> None:
    exercise_name = exercise.get("name", "")
    for index, set_entry in enumerate(exercise.get("sets", []), start=1):
        writer.writerow(
            {
                "date": workout_date,
                "block_type": block_type,
                "superset": superset_name,
                "exercise": exercise_name,
                "set_index": index,
                "weight": _csv_weight_value(set_entry),
                "unit": _blank_if_none(set_entry.get("unit")),
                "reps": set_entry.get("reps", ""),
                "effort_type": effort_type,
                "effort": _blank_if_none(set_entry.get("effort")),
                "type": _blank_if_none(set_entry.get("type")),
            }
        )


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
        set_entry.get("effort"),
        set_entry.get("rest_seconds"),
        set_entry.get("tempo"),
        set_entry.get("type"),
    )


def _serialize_set_group(group: list[dict[str, Any]], default_unit: str) -> str:
    first = group[0]
    reps = ", ".join(_format_number(set_entry["reps"]) for set_entry in group)
    parts = [_weight_token(first, default_unit), "x", reps]

    effort = first.get("effort")
    if effort is not None:
        parts.append(f"@{_format_number(effort)}")

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


def _weight_token(set_entry: dict[str, Any], default_unit: str) -> str:
    bodyweight = bool(set_entry.get("bodyweight"))
    weight = set_entry.get("weight")
    unit = set_entry.get("unit")

    if bodyweight:
        if weight is None:
            return "BW"
        suffix = "" if unit == default_unit else unit or ""
        return f"BW+{_format_number(weight)}{suffix}"

    if weight is None:
        raise ValueError("non-bodyweight sets require a weight")

    suffix = "" if unit == default_unit else unit or ""
    return f"{_format_number(weight)}{suffix}"


def _csv_weight_value(set_entry: dict[str, Any]) -> Any:
    bodyweight = bool(set_entry.get("bodyweight"))
    weight = set_entry.get("weight")

    if bodyweight:
        if weight is None:
            return "BW"
        return f"BW+{_format_number(weight)}"

    return _blank_if_none(weight)


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
