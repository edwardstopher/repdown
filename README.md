# Repdown

Repdown is a small, deterministic Markdown subset for logging strength
training workouts. A Repdown file renders cleanly in Markdown editors while
remaining strict enough to parse into structured JSON or CSV.

Repdown v2 is a breaking format change. It no longer parses the original
date-first v1 syntax.

The core data model is:

```text
Workout -> Blocks -> Exercise | Superset -> Exercises -> Sets
```

## Design Goals

- Valid Markdown that remains readable in ordinary editors and renderers.
- Deterministic parsing with loud failures for invalid syntax.
- A compact syntax for common lifting data: weight, reps, effort, rest, tempo,
  and set type.
- Structured output that preserves exercise and superset ordering.
- Simple CSV export for spreadsheets and analysis.
- No heavy runtime dependencies.

## Example

```markdown
# Push Day

Date: 2026-05-02
Unit: lb
Effort: RIR

## Exercises

## Barbell Bench Press

- 185 x 5
- 185 x 5 @1

Notes: Shoulder felt off

## Barbell Back Squat

- 225 x 6
- 225 x 6
- 225 x 5.5

## Superset 1

### Seated Dumbbell Hammer Curl

- 30 x 10
- 30 x 10
- 30 x 10

### Seated Overhead Dumbbell Press

- 55 x 6
- 55 x 6
- 55 x 6
```

## File Structure

```text
/repdown
  parser.py
  serializer.py
  models.py
  errors.py
/tests
  test_parser.py
README.md
```

## Grammar

Repdown is intentionally a narrow Markdown subset. Arbitrary Markdown prose,
unexpected heading levels, set bullets outside exercises, and malformed set
lines are rejected.

Trailing Markdown hard-break spaces after `Date:` and `Unit:` are emitted by
the serializer but are not required by the parser.

```ebnf
document          = [ title, blank_lines ],
                    date_line, blank_lines,
                    unit_line, blank_lines,
                    effort_line, blank_lines,
                    { note_line, blank_lines },
                    exercises_section,
                    block, { blank_lines, block } ;

title             = "# ", text ;
date_line         = "Date: ", iso_date ;
unit_line         = "Unit: ", unit ;
effort_line       = "Effort: ", effort_type ;
effort_type       = "RPE" | "RIR" ;
exercises_section = "## Exercises" ;

block             = exercise_block | superset_block ;

exercise_block    = "## ", exercise_name, blank_lines,
                    set_or_note, { blank_lines, set_or_note } ;

superset_block    = "## Superset ", name, blank_lines,
                    { note_line, blank_lines },
                    nested_exercise, { blank_lines, nested_exercise } ;

nested_exercise   = "### ", exercise_name, blank_lines,
                    set_or_note, { blank_lines, set_or_note } ;

set_or_note       = set_line | note_line ;
note_line         = "Notes: ", text ;

set_line          = "- ", weight, " x ", reps, [ " ", modifiers ] ;

weight            = numeric_weight | bodyweight | loaded_bodyweight ;
numeric_weight    = number, [ unit ] ;
bodyweight        = "BW" ;
loaded_bodyweight = "BW+", number, [ unit ] ;

reps              = number, { ", ", number } ;

modifiers         = modifier, { " ", modifier } ;
modifier          = effort | rest | tempo | set_type ;
effort            = "@", number ;
rest              = "r=", integer, "s" ;
tempo             = "t=", integer, "-", integer, "-", integer ;
set_type          = "warmup" | "drop" | "amrap" ;

unit              = alpha, { alpha } ;
number            = integer, [ ".", digit, { digit } ] ;
integer           = "0" | nonzero_digit, { digit } ;
```

## Header Rules

- `# <title>` is optional.
- `Date: YYYY-MM-DD`, `Unit: <unit>`, and `Effort: RPE|RIR` are required.
- `## Exercises` is required and marks the start of workout content.
- Workout-level `Notes:` lines may appear between the effort line and
  `## Exercises`.

## Unit and Effort Rules

Numeric weights without an attached unit inherit the workout `Unit:`.

```markdown
Unit: lb

- 185 x 5
- 100kg x 5
```

The first set parses as `185 lb`. The second set uses an explicit `kg`
override.

The `Effort:` header determines how `@<number>` should be interpreted.

```markdown
Effort: RIR

- 185 x 5 @1
```

The set above parses as `effort: 1` with workout-level
`effort_type: "RIR"`.

## Set Rules

Valid set lines:

```markdown
- 100 x 5
- 225lb x 3 @9
- 225 x 5.5
- BW x 10
- BW+20 x 5
- BW+20kg x 5
- 30 x 10, 10, 8.5
- 100 x 5 @8 r=120s t=3-1-1 warmup
```

Invalid set lines:

```markdown
- 100x5          # missing spaces around x
- 100 kg x 5     # unit must be attached to the number
- 100 x 5 hard   # unknown modifier
100 x 5          # missing Markdown bullet
```

### Multi-Rep Shorthand

Rep lists expand to multiple sets because each JSON set has one numeric `reps`
field.

```markdown
- 30 x 10, 10, 8.5
```

maps to three sets: `30 x 10`, `30 x 10`, and `30 x 8.5`.

Modifiers on a multi-rep line apply to every expanded set:

```markdown
- 30 x 10, 8 @2
```

maps to two sets, both with `effort: 2`.

## Supersets

A superset is an ordered block with nested exercises.

```markdown
## Superset 1

Notes: Rest 90 seconds after each round

### Pull Up

- BW x 8

### Dip

- BW x 10
```

`Notes:` lines before the first nested exercise attach to the superset.
`Notes:` lines inside a nested exercise attach to that exercise.

## JSON Mapping

Parser output is a plain Python dictionary that is directly JSON-serializable:

```json
{
  "date": "2026-05-02",
  "title": "Push Day",
  "unit": "lb",
  "effort_type": "RIR",
  "notes": [],
  "blocks": [
    {
      "type": "exercise",
      "name": "Barbell Bench Press",
      "sets": [
        {
          "weight": 185,
          "unit": "lb",
          "bodyweight": false,
          "reps": 5,
          "effort": null,
          "rest_seconds": null,
          "tempo": null,
          "type": null
        },
        {
          "weight": 185,
          "unit": "lb",
          "bodyweight": false,
          "reps": 5,
          "effort": 1,
          "rest_seconds": null,
          "tempo": null,
          "type": null
        }
      ],
      "notes": ["Shoulder felt off"]
    }
  ]
}
```

Superset blocks use this shape:

```json
{
  "type": "superset",
  "name": "1",
  "exercises": [
    {
      "name": "Pull Up",
      "sets": [
        {
          "weight": null,
          "unit": null,
          "bodyweight": true,
          "reps": 8,
          "effort": null,
          "rest_seconds": null,
          "tempo": null,
          "type": null
        }
      ],
      "notes": []
    }
  ],
  "notes": []
}
```

## CSV Mapping

CSV export flattens the workout into one row per set with these columns:

```text
date,block_type,superset,exercise,set_index,weight,unit,reps,effort_type,effort,type
```

- `block_type` is `exercise` or `superset`.
- `superset` is empty for normal exercise blocks.
- `set_index` is 1-based within each exercise.
- `weight` is numeric for loaded sets, `BW` for bodyweight sets, and `BW+N`
  for loaded bodyweight sets.
- `unit` is emitted separately for structured analysis.

Example:

```csv
date,block_type,superset,exercise,set_index,weight,unit,reps,effort_type,effort,type
2026-05-02,exercise,,Barbell Bench Press,1,185,lb,5,RIR,,
2026-05-02,exercise,,Barbell Bench Press,2,185,lb,5,RIR,1,
```

## Python Usage

```python
from repdown.parser import parse_repdown
from repdown.serializer import serialize_repdown, to_csv

source = """# Push Day

Date: 2026-05-02
Unit: lb
Effort: RIR

## Exercises

## Barbell Bench Press

- 185 x 5
- 185 x 5 @1
"""

workout = parse_repdown(source)
text = serialize_repdown(workout)
csv_text = to_csv(workout)
```

## Running Tests

No third-party dependencies are required.

```bash
python3 -m unittest discover -s tests
```

## Edge Cases

- Missing title is valid.
- Old v1 Repdown syntax is invalid.
- Header metadata is required before `## Exercises`.
- `## Exercises` is required and may appear only once.
- Normal exercises use `## <exercise>`.
- Superset exercises use `### <exercise>` inside a `## Superset <name>` block.
- Each exercise must have at least one set.
- Duplicate effort, rest, tempo, or set type modifiers are invalid.
- More than one set type on a set line is invalid.
- Rep lists expand into multiple JSON set objects.
- Serialization may group consecutive compatible sets back into rep-list
  shorthand for readability.
