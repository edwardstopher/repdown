"""Parser for Markdown-compatible Repdown workout logs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import re
from typing import Any

from .errors import ParseError
from .models import Exercise, ExerciseBlock, SetEntry, SupersetBlock, Workout

NUMBER_RE = r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?"
DATE_VALUE_RE = r"[0-9]{4}-[0-9]{2}-[0-9]{2}"
UNIT_RE = r"[A-Za-z]+"

TITLE_RE = re.compile(r"^# (?P<title>.+)$")
DATE_RE = re.compile(rf"^Date: (?P<value>{DATE_VALUE_RE})$")
UNIT_LINE_RE = re.compile(rf"^Unit: (?P<value>{UNIT_RE})$")
EFFORT_LINE_RE = re.compile(r"^Effort: (?P<value>RPE|RIR)$", re.IGNORECASE)
EXERCISES_SECTION = "## Exercises"
SUPERSET_HEADING_RE = re.compile(r"^## Superset (?P<name>.+)$")
EXERCISE_HEADING_RE = re.compile(r"^## (?P<name>.+)$")
NESTED_EXERCISE_HEADING_RE = re.compile(r"^### (?P<name>.+)$")
ANY_HEADING_RE = re.compile(r"^#{1,6} .+$")
NOTES_RE = re.compile(r"^Notes: (?P<value>.+)$")
BULLET_SET_RE = re.compile(r"^- (?P<set>.+)$")

SET_RE = re.compile(
    rf"^(?P<weight>BW(?:\+(?:{NUMBER_RE})(?:{UNIT_RE})?)?|"
    rf"(?:{NUMBER_RE})(?:{UNIT_RE})?)"
    rf" x "
    rf"(?P<reps>{NUMBER_RE}(?:, {NUMBER_RE})*)"
    rf"(?P<modifiers>(?: [^ ]+)*)$"
)
NUMERIC_WEIGHT_RE = re.compile(rf"^(?P<value>{NUMBER_RE})(?P<unit>{UNIT_RE})?$")
LOADED_BODYWEIGHT_RE = re.compile(
    rf"^BW\+(?P<value>{NUMBER_RE})(?P<unit>{UNIT_RE})?$"
)
EFFORT_RE = re.compile(rf"^@(?P<value>{NUMBER_RE})$")
REST_RE = re.compile(r"^(?:r=)(?P<seconds>(?:0|[1-9][0-9]*))s$")
TEMPO_RE = re.compile(r"^t=(?:0|[1-9][0-9]*)-(?:0|[1-9][0-9]*)-(?:0|[1-9][0-9]*)$")
SET_TYPES = {"warmup", "drop", "amrap"}


@dataclass(frozen=True)
class _Line:
    number: int
    text: str


def parse_repdown(source: str) -> dict[str, Any]:
    """Parse a Markdown-compatible Repdown string into a dictionary."""

    parser = _Parser(source)
    return parser.parse().to_dict()


class _Parser:
    def __init__(self, source: str) -> None:
        self.lines = _logical_lines(source)
        self.position = 0

    def parse(self) -> Workout:
        self._skip_blank_lines()
        if self._at_end():
            raise ParseError(1, "expected 'Date: YYYY-MM-DD'")

        title = self._parse_optional_title()
        self._skip_blank_lines()
        workout_date = self._parse_required_date()
        self._skip_blank_lines()
        unit = self._parse_required_unit()
        self._skip_blank_lines()
        effort_type = self._parse_required_effort_type()
        notes = self._parse_workout_notes()
        self._skip_blank_lines()
        self._parse_exercises_section()

        blocks = self._parse_blocks(unit)
        return Workout(
            date=workout_date,
            title=title,
            unit=unit,
            effort_type=effort_type,
            notes=notes,
            blocks=blocks,
        )

    def _parse_optional_title(self) -> str | None:
        if self._at_end():
            return None

        line = self._current()
        match = TITLE_RE.match(line.text)
        if not match:
            if line.text.startswith("#"):
                raise ParseError(line.number, "title must use '# <title>'")
            return None

        self.position += 1
        return match.group("title")

    def _parse_required_date(self) -> str:
        line = self._expect_current("expected 'Date: YYYY-MM-DD'")
        match = DATE_RE.match(line.text)
        if not match:
            raise ParseError(line.number, "expected 'Date: YYYY-MM-DD'")

        value = match.group("value")
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ParseError(line.number, "invalid calendar date") from exc

        self.position += 1
        return value

    def _parse_required_unit(self) -> str:
        line = self._expect_current("expected 'Unit: <unit>'")
        match = UNIT_LINE_RE.match(line.text)
        if not match:
            raise ParseError(line.number, "expected 'Unit: <unit>'")

        self.position += 1
        return match.group("value")

    def _parse_required_effort_type(self) -> str:
        line = self._expect_current("expected 'Effort: RPE' or 'Effort: RIR'")
        match = EFFORT_LINE_RE.match(line.text)
        if not match:
            raise ParseError(line.number, "expected 'Effort: RPE' or 'Effort: RIR'")

        self.position += 1
        return match.group("value").upper()

    def _parse_workout_notes(self) -> list[str]:
        notes: list[str] = []
        while not self._at_end():
            self._skip_blank_lines()
            if self._at_end() or self._current().text == EXERCISES_SECTION:
                break

            line = self._current()
            if ANY_HEADING_RE.match(line.text):
                raise ParseError(line.number, "expected '## Exercises'")

            note = _parse_notes_line(line)
            if note is None:
                raise ParseError(line.number, "expected 'Notes: <text>' or '## Exercises'")
            notes.append(note)
            self.position += 1

        return notes

    def _parse_exercises_section(self) -> None:
        line = self._expect_current("expected '## Exercises'")
        if line.text != EXERCISES_SECTION:
            raise ParseError(line.number, "expected '## Exercises'")
        self.position += 1

    def _parse_blocks(self, default_unit: str) -> list[ExerciseBlock | SupersetBlock]:
        blocks: list[ExerciseBlock | SupersetBlock] = []

        while not self._at_end():
            self._skip_blank_lines()
            if self._at_end():
                break

            line = self._current()
            if _is_bullet_line(line.text):
                raise ParseError(line.number, "set line must be inside an exercise")
            if NESTED_EXERCISE_HEADING_RE.match(line.text):
                raise ParseError(
                    line.number,
                    "nested exercise headings are only valid inside supersets",
                )
            if SUPERSET_HEADING_RE.match(line.text):
                blocks.append(self._parse_superset_block(default_unit))
                continue
            if EXERCISE_HEADING_RE.match(line.text):
                blocks.append(self._parse_exercise_block(default_unit))
                continue
            if ANY_HEADING_RE.match(line.text):
                raise ParseError(line.number, "unexpected heading level")

            raise ParseError(line.number, "expected exercise or superset heading")

        if not blocks:
            line_number = self.lines[-1].number if self.lines else 1
            raise ParseError(line_number, "expected at least one workout block")

        return blocks

    def _parse_exercise_block(self, default_unit: str) -> ExerciseBlock:
        line = self._current()
        match = EXERCISE_HEADING_RE.match(line.text)
        if not match:
            raise ParseError(line.number, "expected exercise heading")

        name = match.group("name")
        if name == "Exercises":
            raise ParseError(line.number, "'## Exercises' may only appear once")
        if name.startswith("Superset"):
            raise ParseError(
                line.number,
                "superset headings must use '## Superset <name>'",
            )

        self.position += 1
        sets, notes = self._parse_exercise_contents(name, line.number, default_unit)
        return ExerciseBlock(name=name, sets=sets, notes=notes)

    def _parse_superset_block(self, default_unit: str) -> SupersetBlock:
        line = self._current()
        match = SUPERSET_HEADING_RE.match(line.text)
        if not match:
            raise ParseError(line.number, "expected superset heading")

        name = match.group("name")
        self.position += 1
        notes: list[str] = []
        exercises: list[Exercise] = []

        while not self._at_end():
            self._skip_blank_lines()
            if self._at_end() or _is_top_level_heading(self._current().text):
                break

            line = self._current()
            if NESTED_EXERCISE_HEADING_RE.match(line.text):
                exercises.append(self._parse_nested_exercise(default_unit))
                continue

            note = _parse_notes_line(line)
            if note is not None:
                if exercises:
                    raise ParseError(
                        line.number,
                        "superset notes must appear before nested exercises",
                    )
                notes.append(note)
                self.position += 1
                continue

            if _is_bullet_line(line.text):
                raise ParseError(
                    line.number,
                    "set line must be inside a superset exercise",
                )
            if ANY_HEADING_RE.match(line.text):
                raise ParseError(line.number, "unexpected heading level")

            raise ParseError(line.number, "expected nested exercise heading or notes")

        if not exercises:
            raise ParseError(
                line.number,
                f"superset '{name}' must contain at least one exercise",
            )

        return SupersetBlock(name=name, exercises=exercises, notes=notes)

    def _parse_nested_exercise(self, default_unit: str) -> Exercise:
        line = self._current()
        match = NESTED_EXERCISE_HEADING_RE.match(line.text)
        if not match:
            raise ParseError(line.number, "expected nested exercise heading")

        name = match.group("name")
        self.position += 1
        sets, notes = self._parse_exercise_contents(
            name,
            line.number,
            default_unit,
            nested=True,
        )
        return Exercise(name=name, sets=sets, notes=notes)

    def _parse_exercise_contents(
        self,
        name: str,
        heading_line_number: int,
        default_unit: str,
        *,
        nested: bool = False,
    ) -> tuple[list[SetEntry], list[str]]:
        sets: list[SetEntry] = []
        notes: list[str] = []

        while not self._at_end():
            self._skip_blank_lines()
            if self._at_end():
                break

            line = self._current()
            if _is_top_level_heading(line.text):
                break
            if nested and NESTED_EXERCISE_HEADING_RE.match(line.text):
                break
            if not nested and NESTED_EXERCISE_HEADING_RE.match(line.text):
                raise ParseError(
                    line.number,
                    "nested exercise headings are only valid inside supersets",
                )

            note = _parse_notes_line(line)
            if note is not None:
                notes.append(note)
                self.position += 1
                continue

            bullet = BULLET_SET_RE.match(line.text)
            if bullet:
                sets.extend(
                    _parse_set_text(bullet.group("set"), line.number, default_unit)
                )
                self.position += 1
                continue

            if ANY_HEADING_RE.match(line.text):
                raise ParseError(line.number, "unexpected heading level")

            raise ParseError(line.number, "expected set line or notes")

        if not sets:
            raise ParseError(
                heading_line_number,
                f"exercise '{name}' must contain at least one set",
            )

        return sets, notes

    def _skip_blank_lines(self) -> None:
        while not self._at_end() and self._current().text == "":
            self.position += 1

    def _expect_current(self, message: str) -> _Line:
        if self._at_end():
            line_number = self.lines[-1].number if self.lines else 1
            raise ParseError(line_number, message)
        return self._current()

    def _current(self) -> _Line:
        return self.lines[self.position]

    def _at_end(self) -> bool:
        return self.position >= len(self.lines)


def _logical_lines(source: str) -> list[_Line]:
    return [
        _Line(number=index, text=raw_line.strip())
        for index, raw_line in enumerate(source.splitlines(), start=1)
    ]


def _is_top_level_heading(text: str) -> bool:
    return text.startswith("## ")


def _is_bullet_line(text: str) -> bool:
    return text.startswith("- ")


def _parse_notes_line(line: _Line) -> str | None:
    match = NOTES_RE.match(line.text)
    if not match:
        return None
    return match.group("value")


def _parse_set_text(text: str, line_number: int, default_unit: str) -> list[SetEntry]:
    match = SET_RE.match(text)
    if not match:
        raise ParseError(line_number, "invalid set line")

    weight, unit, bodyweight = _parse_weight(
        match.group("weight"),
        default_unit,
        line_number,
    )
    reps = [_parse_number(rep) for rep in match.group("reps").split(", ")]
    modifiers = _parse_modifiers(match.group("modifiers").strip(), line_number)

    return [
        SetEntry(
            weight=weight,
            unit=unit,
            bodyweight=bodyweight,
            reps=rep,
            effort=modifiers["effort"],
            rest_seconds=modifiers["rest_seconds"],
            tempo=modifiers["tempo"],
            type=modifiers["type"],
        )
        for rep in reps
    ]


def _parse_weight(
    token: str,
    default_unit: str,
    line_number: int,
) -> tuple[int | float | None, str | None, bool]:
    if token == "BW":
        return None, None, True

    loaded_bodyweight = LOADED_BODYWEIGHT_RE.match(token)
    if loaded_bodyweight:
        return (
            _parse_number(loaded_bodyweight.group("value")),
            loaded_bodyweight.group("unit") or default_unit,
            True,
        )

    numeric = NUMERIC_WEIGHT_RE.match(token)
    if numeric:
        return (
            _parse_number(numeric.group("value")),
            numeric.group("unit") or default_unit,
            False,
        )

    raise ParseError(line_number, "invalid weight")


def _parse_modifiers(text: str, line_number: int) -> dict[str, int | float | str | None]:
    modifiers: dict[str, int | float | str | None] = {
        "effort": None,
        "rest_seconds": None,
        "tempo": None,
        "type": None,
    }
    if not text:
        return modifiers

    for token in text.split(" "):
        effort = EFFORT_RE.match(token)
        if effort:
            if modifiers["effort"] is not None:
                raise ParseError(line_number, "duplicate effort modifier")
            modifiers["effort"] = _parse_number(effort.group("value"))
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
