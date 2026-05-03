# Repdown

Repdown is a small, deterministic markup language for logging strength
training workouts. It is designed to be human-readable like Markdown, fast to
type on mobile, and straightforward to convert into JSON or CSV.

The core data model is:

```text
Workout -> Exercises -> Sets
```

## Design Goals

- Human-readable workout logs that remain pleasant to type by hand.
- Deterministic parsing with loud failures for invalid syntax.
- A compact syntax for common lifting data: weight, reps, RPE, rest, tempo, and
  set type.
- Lossless enough JSON output for storage and APIs.
- Simple CSV export for spreadsheets and analysis.
- No heavy runtime dependencies.

## Example

```repdown
2026-05-02
Push Day

unit: kg

Bench Press
100 x 5
100 x 5
100 x 5 @8

Incline DB Press
30 x 10, 10, 8

Lateral Raise
12 x 15 amrap

# left shoulder slightly off
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

This grammar is intentionally strict. Whitespace around `x`, between
modifiers, and after commas in rep lists is required exactly where shown.
Surrounding whitespace at the beginning and end of a line is ignored by the
parser. Inline comments are not supported.

```ebnf
workout        = date_line, newline,
                 [ title_line, newline ],
                 blank_lines,
                 metadata_lines,
                 blank_lines,
                 exercise_block, { blank_lines, exercise_block },
                 blank_lines ;

date_line      = iso_date ;
iso_date       = digit, digit, digit, digit, "-", digit, digit, "-", digit, digit ;

title_line     = text_line ;

metadata_lines = { metadata_line, newline, blank_lines } ;
metadata_line  = key, ": ", value ;
key            = alpha_or_underscore, { alpha_or_digit_or_underscore_or_dash } ;
value          = non_empty_text ;

exercise_block = exercise_name, newline, set_line, { newline, set_line } ;
exercise_name  = text_line ;

set_line       = weight, " x ", reps, [ " ", modifiers ] ;

weight         = numeric_weight | bodyweight | loaded_bodyweight ;
numeric_weight = number, [ unit ] ;
bodyweight     = "BW" ;
loaded_bodyweight = "BW+", number, unit ;

reps           = integer, { ", ", integer } ;

modifiers      = modifier, { " ", modifier } ;
modifier       = rpe | rest | tempo | set_type ;
rpe            = "@", number ;
rest           = "r=", integer, "s" ;
tempo          = "t=", integer, "-", integer, "-", integer ;
set_type       = "warmup" | "drop" | "amrap" ;

unit           = alpha, { alpha } ;
number         = integer, [ ".", digit, { digit } ] ;
integer        = "0" | nonzero_digit, { digit } ;

blank_lines    = { blank_line, newline } ;
blank_line     = "" ;
comment_line   = "#", any_text ;
```

Comment lines begin with `#` in column 1 and are ignored before parsing.

### Header Rules

- The first non-comment content line must be an ISO date: `YYYY-MM-DD`.
- The title is optional.
- If the title is omitted and the first exercise comes immediately after the
  date, the parser uses lookahead: a line followed by a valid set line is an
  exercise name, not a title.
- A metadata line immediately after the date is metadata, not a title.

### Metadata Rules

Metadata uses `key: value` and must appear before the first exercise.

```repdown
unit: kg
location: garage
```

Metadata keys may contain letters, digits, underscores, and dashes, but must
start with a letter or underscore.

### Set Rules

Valid set lines:

```repdown
100kg x 5
225lb x 3 @9
BW x 10
BW+20kg x 5
30 x 10, 10, 8
100 x 5 @8 r=120s t=3-1-1 warmup
```

Invalid set lines:

```repdown
100x5          # missing spaces around x
100 kg x 5     # unit must be attached to the number
BW+20 x 5      # loaded bodyweight requires a unit
100 x 5 # note  # inline comments are not supported
100 x 5 hard   # unknown modifier
```

### Multi-Rep Shorthand

Rep lists expand to multiple sets because each JSON set has one numeric `reps`
field.

```repdown
30 x 10, 10, 8
```

maps to three sets: `30 x 10`, `30 x 10`, and `30 x 8`.

Modifiers on a multi-rep line apply to every expanded set:

```repdown
30 x 10, 8 @8
```

maps to two sets, both with `rpe: 8`.

## JSON Mapping

Parser output is a plain Python dictionary that is directly JSON-serializable:

```json
{
  "date": "2026-05-02",
  "title": "Push Day",
  "metadata": {
    "unit": "kg"
  },
  "exercises": [
    {
      "name": "Bench Press",
      "sets": [
        {
          "weight": 100,
          "unit": null,
          "bodyweight": false,
          "reps": 5,
          "rpe": null,
          "rest_seconds": null,
          "tempo": null,
          "type": null
        },
        {
          "weight": 100,
          "unit": null,
          "bodyweight": false,
          "reps": 5,
          "rpe": 8,
          "rest_seconds": null,
          "tempo": null,
          "type": null
        }
      ]
    }
  ]
}
```

### Weight Mapping

| Repdown | JSON `weight` | JSON `unit` | JSON `bodyweight` |
| --- | ---: | --- | --- |
| `100 x 5` | `100` | `null` | `false` |
| `100kg x 5` | `100` | `"kg"` | `false` |
| `BW x 10` | `null` | `null` | `true` |
| `BW+20kg x 5` | `20` | `"kg"` | `true` |

## CSV Mapping

CSV export flattens the workout into one row per set with these columns:

```text
date,exercise,set_index,weight,reps,rpe,type
```

- `set_index` is 1-based within each exercise.
- `weight` is emitted as a readable Repdown weight token such as `100`,
  `100kg`, `BW`, or `BW+20kg`.
- Empty optional fields are emitted as empty CSV cells.

Example:

```csv
date,exercise,set_index,weight,reps,rpe,type
2026-05-02,Bench Press,1,100,5,,
2026-05-02,Bench Press,2,100,5,8,
2026-05-02,Lateral Raise,1,12,15,,amrap
```

## Python Usage

```python
from repdown.parser import parse_repdown
from repdown.serializer import serialize_repdown, to_csv

source = """2026-05-02
Push Day

unit: kg

Bench Press
100 x 5
100 x 5 @8
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
- Comments are ignored only when `#` is the first character on the line.
- Inline comments are invalid.
- Metadata after the first exercise is invalid.
- Exercise names must not be valid set lines or metadata lines.
- Each exercise must have at least one set.
- Duplicate modifiers on a set line are invalid.
- More than one set type on a set line is invalid.
- `BW+<number><unit>` requires a unit.
- Rep lists expand into multiple JSON set objects.
- Serialization may group consecutive compatible sets back into rep-list
  shorthand for readability.

## Stretch Goal Status

Superset syntax such as `[Superset A]` is not implemented in this version. The
current parser rejects it so the base grammar remains strict and deterministic.
