"""Data models for Repdown workouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

Number = Union[int, float]


@dataclass(frozen=True)
class SetEntry:
    weight: Number | None
    unit: str | None
    bodyweight: bool
    reps: Number
    effort: Number | None = None
    rest_seconds: int | None = None
    tempo: str | None = None
    type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "weight": self.weight,
            "unit": self.unit,
            "bodyweight": self.bodyweight,
            "reps": self.reps,
            "effort": self.effort,
            "rest_seconds": self.rest_seconds,
            "tempo": self.tempo,
            "type": self.type,
        }


@dataclass(frozen=True)
class Exercise:
    name: str
    sets: list[SetEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sets": [set_entry.to_dict() for set_entry in self.sets],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class ExerciseBlock:
    name: str
    sets: list[SetEntry] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "exercise",
            "name": self.name,
            "sets": [set_entry.to_dict() for set_entry in self.sets],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class SupersetBlock:
    name: str
    exercises: list[Exercise] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "superset",
            "name": self.name,
            "exercises": [exercise.to_dict() for exercise in self.exercises],
            "notes": list(self.notes),
        }


Block = Union[ExerciseBlock, SupersetBlock]


@dataclass(frozen=True)
class Workout:
    date: str
    title: str | None
    unit: str
    effort_type: str
    notes: list[str] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "title": self.title,
            "unit": self.unit,
            "effort_type": self.effort_type,
            "notes": list(self.notes),
            "blocks": [block.to_dict() for block in self.blocks],
        }
