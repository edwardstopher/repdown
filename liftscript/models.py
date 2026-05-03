"""Data models for LiftScript workouts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Union

Number = Union[int, float]


@dataclass(frozen=True)
class SetEntry:
    weight: Number | None
    unit: str | None
    bodyweight: bool
    reps: int
    rpe: Number | None = None
    rest_seconds: int | None = None
    tempo: str | None = None
    type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "weight": self.weight,
            "unit": self.unit,
            "bodyweight": self.bodyweight,
            "reps": self.reps,
            "rpe": self.rpe,
            "rest_seconds": self.rest_seconds,
            "tempo": self.tempo,
            "type": self.type,
        }


@dataclass(frozen=True)
class Exercise:
    name: str
    sets: list[SetEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sets": [set_entry.to_dict() for set_entry in self.sets],
        }


@dataclass(frozen=True)
class Workout:
    date: str
    title: str | None
    metadata: dict[str, str] = field(default_factory=dict)
    exercises: list[Exercise] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "date": self.date,
            "title": self.title,
            "metadata": dict(self.metadata),
            "exercises": [exercise.to_dict() for exercise in self.exercises],
        }
