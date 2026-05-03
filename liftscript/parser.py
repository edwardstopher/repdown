"""Parser for LiftScript workout logs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Any

from .errors import ParseError
from .models import Exercise, SetEntry, Workout

NUMBER_RE = r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?"
INTEGER_RE = r"(?:0|[1-9][0-9]*)"
UNIT_RE = r"[A-Za-z]+"

DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
METADATA_RE = re.compile(
    r"^(?P<key>[A-Za-z_][A-Za-z0-9_-]*): (?P<value>.+)$"
)
SET_RE = re.compile(
    rf"^(?P<weight>BW(?:\+(?:{NUMBER_RE})(?:{UNIT_RE}))?|"
    rf"(?:{NUMBER_RE})(?:{UNIT_RE})?)"
    rf" x "
    rf"(?P<reps>{INTEGER_RE}(?:, {INTEGER_RE})*)"
    rf"(?P<modifiers>(?: [^ ]+)*)$"
)
NUMERIC_WEIGHT_RE = re.compile(rf"^(?P<value>{NUMBER_RE})(?P<unit>{UNIT_RE})?$")
LOADED_BODYWEIGHT_RE = re.compile(
    rf"^BW\+(?P<value>{NUMBER_RE})(?P<unit>{UNIT_RE})$"
)
RPE_RE = re.compile(rf"^@(?P<value>{NUMBER_RE})$")
REST_RE = re.compile(rf"^r=(?P<seconds>{INTEGER_RE})s$")
TEMPO_RE = re.compile(rf"^t={INTEGER_RE}-{INTEGER_RE}-{INTEGER_RE}$")
SET_TYPES = {"warmup", "drop", "amrap"}


@dataclass(frozen=True)
class _Line:
    number: int
    text: str


def parse_liftscript(source: str) -> dict[str, Any]:
    """Parse a LiftScript string into a JSON-serializable dictionary."""

    parser = _Parser(source)
    return parser.parse().to_dict()


class _Parser:
    def __init__(self, source: str) -> None:
        self.lines = _logical_lines(source)
        self.position = 0

    def parse(self) -> Workout:
        if not self.lines:
            raise ParseError(1, "expected ISO date")

        first = self._current()
        if first.text == "":
            raise ParseError(first.number, "expected ISO date, found blank line")
        workout_date = self._parse_date(first)
        self.position += 1

        title = self._parse_optional_title()
        self._skip_blank_lines()
        metadata = self._parse_metadata()
        self._skip_blank_lines()
        exercises = self._parse_exercises()

        return Workout(
            date=workout_date,
            title=title,
            metadata=metadata,
            exercises=exercises,
        )

    def _parse_date(self, line: _Line) -> str:
        if not DATE_RE.match(line.text):
            raise ParseError(line.number, "expected ISO date in YYYY-MM-DD format")
        try:
            date.fromisoformat(line.text)
        except ValueError as exc:
            raise ParseError(line.number, "invalid calendar date") from exc
        return line.text

    def _parse_optional_title(self) -> str | None:
        if self._at_end():
            return None

        line = self._current()
        if line.text == "" or _is_metadata_line(line.text):
            return None

        next_content = self._next_nonblank(self.position + 1)
        if next_content is not None and _is_set_line(next_content.text):
            return None

        self.position += 1
        return line.text

    def _parse_metadata(self) -> dict[str, str]:
        metadata: dict[str, str] = {}

        while not self._at_end():
            line = self._current()
            if line.text == "":
                self._skip_blank_lines()
                continue

            match = METADATA_RE.match(line.text)
            if not match:
                break

            key = match.group("key")
            if key in metadata:
                raise ParseError(line.number, f"duplicate metadata key '{key}'")
            metadata[key] = match.group("value")
            self.position += 1

        return metadata

    def _parse_exercises(self) -> list[Exercise]:
        exercises: list[Exercise] = []

        while not self._at_end():
            self._skip_blank_lines()
            if self._at_end():
                break

            name_line = self._current()
            if name_line.text.startswith("["):
                raise ParseError(
                    name_line.number,
                    "superset blocks are not supported by this parser",
                )
            if _is_set_line(name_line.text):
                raise ParseError(name_line.number, "expected exercise name, found set line")
            if _is_metadata_line(name_line.text):
                raise ParseError(
                    name_line.number,
                    "metadata must appear before the first exercise",
                )

            exercise_name = name_line.text
            self.position += 1

            sets: list[SetEntry] = []
            while not self._at_end():
                line = self._current()
                if line.text == "":
                    break
                if _is_metadata_line(line.text):
                    raise ParseError(
                        line.number,
                        "metadata must appear before the first exercise",
                    )
                if not _is_set_line(line.text):
                    raise ParseError(line.number, "expected set line")
                sets.extend(_parse_set_line(line))
                self.position += 1

            if not sets:
                raise ParseError(
                    name_line.number,
                    f"exercise '{exercise_name}' must contain at least one set",
                )

            exercises.append(Exercise(name=exercise_name, sets=sets))

        if not exercises:
            last_line = self.lines[-1] if self.lines else _Line(1, "")
            raise ParseError(last_line.number, "expected at least one exercise")

        return exercises

    def _skip_blank_lines(self) -> None:
        while not self._at_end() and self._current().text == "":
            self.position += 1

    def _next_nonblank(self, start: int) -> _Line | None:
        for index in range(start, len(self.lines)):
            if self.lines[index].text != "":
                return self.lines[index]
        return None

    def _current(self) -> _Line:
        return self.lines[self.position]

    def _at_end(self) -> bool:
        return self.position >= len(self.lines)


def _logical_lines(source: str) -> list[_Line]:
    lines: list[_Line] = []
    for index, raw_line in enumerate(source.splitlines(), start=1):
        if raw_line.startswith("#"):
            continue
        lines.append(_Line(number=index, text=raw_line.strip()))
    return lines


def _is_metadata_line(text: str) -> bool:
    return METADATA_RE.match(text) is not None


def _is_set_line(text: str) -> bool:
    return SET_RE.match(text) is not None


def _parse_set_line(line: _Line) -> list[SetEntry]:
    match = SET_RE.match(line.text)
    if not match:
        raise ParseError(line.number, "invalid set line")

    weight, unit, bodyweight = _parse_weight(match.group("weight"), line.number)
    reps = [int(rep) for rep in match.group("reps").split(", ")]
    modifiers = _parse_modifiers(match.group("modifiers").strip(), line.number)

    return [
        SetEntry(
            weight=weight,
            unit=unit,
            bodyweight=bodyweight,
            reps=rep,
            rpe=modifiers["rpe"],
            rest_seconds=modifiers["rest_seconds"],
            tempo=modifiers["tempo"],
            type=modifiers["type"],
        )
        for rep in reps
    ]


def _parse_weight(token: str, line_number: int) -> tuple[int | float | None, str | None, bool]:
    if token == "BW":
        return None, None, True

    loaded_bodyweight = LOADED_BODYWEIGHT_RE.match(token)
    if loaded_bodyweight:
        return (
            _parse_number(loaded_bodyweight.group("value")),
            loaded_bodyweight.group("unit"),
            True,
        )

    numeric = NUMERIC_WEIGHT_RE.match(token)
    if numeric:
        return _parse_number(numeric.group("value")), numeric.group("unit"), False

    raise ParseError(line_number, "invalid weight")


def _parse_modifiers(text: str, line_number: int) -> dict[str, int | float | str | None]:
    modifiers: dict[str, int | float | str | None] = {
        "rpe": None,
        "rest_seconds": None,
        "tempo": None,
        "type": None,
    }
    if not text:
        return modifiers

    for token in text.split(" "):
        rpe = RPE_RE.match(token)
        if rpe:
            if modifiers["rpe"] is not None:
                raise ParseError(line_number, "duplicate RPE modifier")
            modifiers["rpe"] = _parse_number(rpe.group("value"))
            continue

        rest = REST_RE.match(token)
        if rest:
            if modifiers["rest_seconds"] is not None:
                raise ParseError(line_number, "duplicate rest modifier")
            modifiers["rest_seconds"] = int(rest.group("seconds"))
            continue

        if TEMPO_RE.match(token):
            if modifiers["tempo"] is not None:
                raise ParseError(line_number, "duplicate tempo modifier")
            modifiers["tempo"] = token.removeprefix("t=")
            continue

        if token in SET_TYPES:
            if modifiers["type"] is not None:
                raise ParseError(line_number, "duplicate set type modifier")
            modifiers["type"] = token
            continue

        raise ParseError(line_number, f"unknown modifier '{token}'")

    return modifiers


def _parse_number(value: str) -> int | float:
    if "." in value:
        return float(value)
    return int(value)
