import unittest

from repdown.errors import ParseError
from repdown.parser import parse_repdown
from repdown.serializer import serialize_repdown, to_csv


EXAMPLE = """# Push Day

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
"""


class ParserTests(unittest.TestCase):
    def test_parse_full_markdown_example(self):
        workout = parse_repdown(EXAMPLE)

        self.assertEqual(workout["title"], "Push Day")
        self.assertEqual(workout["date"], "2026-05-02")
        self.assertEqual(workout["unit"], "lb")
        self.assertEqual(workout["effort_type"], "RIR")
        self.assertEqual(workout["notes"], [])
        self.assertEqual(len(workout["blocks"]), 3)

        bench = workout["blocks"][0]
        self.assertEqual(bench["type"], "exercise")
        self.assertEqual(bench["name"], "Barbell Bench Press")
        self.assertEqual(bench["notes"], ["Shoulder felt off"])
        self.assertEqual(bench["sets"][0]["unit"], "lb")
        self.assertEqual(bench["sets"][1]["effort"], 1)

        squat = workout["blocks"][1]
        self.assertEqual([set_entry["reps"] for set_entry in squat["sets"]], [6, 6, 5.5])

        superset = workout["blocks"][2]
        self.assertEqual(superset["type"], "superset")
        self.assertEqual(superset["name"], "1")
        self.assertEqual(len(superset["exercises"]), 2)
        self.assertEqual(superset["exercises"][0]["name"], "Seated Dumbbell Hammer Curl")
        self.assertEqual(superset["exercises"][1]["sets"][2]["weight"], 55)

    def test_missing_title_is_valid(self):
        workout = parse_repdown(
            """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

## Deadlift

- 180 x 3 @8
"""
        )

        self.assertIsNone(workout["title"])
        self.assertEqual(workout["blocks"][0]["name"], "Deadlift")
        self.assertEqual(workout["blocks"][0]["sets"][0]["effort"], 8)

    def test_workout_notes_before_exercises_section(self):
        workout = parse_repdown(
            """# Pull Day

Date: 2026-05-02
Unit: kg
Effort: RPE

Notes: Slept poorly
Notes: Keep volume moderate

## Exercises

## Pull Up

- BW x 8
"""
        )

        self.assertEqual(workout["notes"], ["Slept poorly", "Keep volume moderate"])

    def test_explicit_unit_overrides_default_unit(self):
        workout = parse_repdown(
            """# Mixed Units

Date: 2026-05-02
Unit: lb
Effort: RPE

## Exercises

## Bench Press

- 185 x 5
- 100kg x 5
"""
        )

        first, second = workout["blocks"][0]["sets"]
        self.assertEqual(first["unit"], "lb")
        self.assertEqual(second["unit"], "kg")

        rendered = serialize_repdown(workout)
        self.assertIn("- 185 x 5", rendered)
        self.assertIn("- 100kg x 5", rendered)

    def test_bodyweight_and_loaded_bodyweight_sets(self):
        workout = parse_repdown(
            """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

## Dip

- BW x 10
- BW+20 x 5
"""
        )

        bodyweight, loaded = workout["blocks"][0]["sets"]
        self.assertTrue(bodyweight["bodyweight"])
        self.assertIsNone(bodyweight["weight"])
        self.assertIsNone(bodyweight["unit"])
        self.assertTrue(loaded["bodyweight"])
        self.assertEqual(loaded["weight"], 20)
        self.assertEqual(loaded["unit"], "kg")

    def test_all_modifiers_use_generic_effort(self):
        workout = parse_repdown(
            """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

## Squat

- 100 x 5 @8.5 r=120s t=3-1-1 warmup
"""
        )

        set_entry = workout["blocks"][0]["sets"][0]
        self.assertEqual(set_entry["effort"], 8.5)
        self.assertEqual(set_entry["rest_seconds"], 120)
        self.assertEqual(set_entry["tempo"], "3-1-1")
        self.assertEqual(set_entry["type"], "warmup")

    def test_multi_rep_modifiers_apply_to_each_expanded_set(self):
        workout = parse_repdown(
            """Date: 2026-05-02
Unit: kg
Effort: RIR

## Exercises

## Incline DB Press

- 30 x 10, 8.5 @2
"""
        )

        sets = workout["blocks"][0]["sets"]
        self.assertEqual([set_entry["reps"] for set_entry in sets], [10, 8.5])
        self.assertEqual([set_entry["effort"] for set_entry in sets], [2, 2])

    def test_superset_notes_attach_before_nested_exercises(self):
        workout = parse_repdown(
            """Date: 2026-05-02
Unit: lb
Effort: RPE

## Exercises

## Superset A

Notes: Rest 90 seconds after each round

### Pull Up

- BW x 8

### Dip

- BW x 10
"""
        )

        superset = workout["blocks"][0]
        self.assertEqual(superset["notes"], ["Rest 90 seconds after each round"])

    def test_serializer_round_trip(self):
        workout = parse_repdown(EXAMPLE)
        rendered = serialize_repdown(workout)
        reparsed = parse_repdown(rendered)

        self.assertEqual(reparsed, workout)
        self.assertIn("- 225 x 6, 6, 5.5", rendered)
        self.assertIn("## Superset 1", rendered)
        self.assertIn("### Seated Dumbbell Hammer Curl", rendered)

    def test_csv_export(self):
        workout = parse_repdown(EXAMPLE)
        csv_text = to_csv(workout)

        self.assertIn(
            "date,block_type,superset,exercise,set_index,weight,unit,reps,"
            "effort_type,effort,type\n",
            csv_text,
        )
        self.assertIn(
            "2026-05-02,exercise,,Barbell Bench Press,2,185,lb,5,RIR,1,\n",
            csv_text,
        )
        self.assertIn(
            "2026-05-02,superset,1,Seated Overhead Dumbbell Press,3,55,lb,6,RIR,,\n",
            csv_text,
        )

    def test_invalid_date_raises_line_number(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """# Push Day

Date: 2026-02-30
Unit: kg
Effort: RPE

## Exercises

## Squat

- 100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 3)
        self.assertIn("invalid calendar date", str(context.exception))

    def test_old_v1_syntax_is_rejected(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """2026-05-02
Push Day

unit: kg

Bench Press
100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 1)
        self.assertIn("expected 'Date: YYYY-MM-DD'", str(context.exception))

    def test_missing_required_metadata_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """Date: 2026-05-02
Effort: RPE

## Exercises

## Squat

- 100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 2)
        self.assertIn("expected 'Unit: <unit>'", str(context.exception))

    def test_missing_exercises_section_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """Date: 2026-05-02
Unit: kg
Effort: RPE

## Squat

- 100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 5)
        self.assertIn("expected '## Exercises'", str(context.exception))

    def test_malformed_heading_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

#### Squat

- 100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 7)
        self.assertIn("unexpected heading level", str(context.exception))

    def test_set_bullet_outside_exercise_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

- 100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 7)
        self.assertIn("set line must be inside an exercise", str(context.exception))

    def test_malformed_set_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

## Squat

- 100x5
"""
            )

        self.assertEqual(context.exception.line_number, 9)
        self.assertIn("invalid set line", str(context.exception))

    def test_unknown_modifier_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

## Squat

- 100 x 5 hard
"""
            )

        self.assertEqual(context.exception.line_number, 9)
        self.assertIn("unknown modifier 'hard'", str(context.exception))

    def test_duplicate_effort_modifier_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

## Squat

- 100 x 5 @8 @9
"""
            )

        self.assertEqual(context.exception.line_number, 9)
        self.assertIn("duplicate effort modifier", str(context.exception))

    def test_exercise_without_sets_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_repdown(
                """Date: 2026-05-02
Unit: kg
Effort: RPE

## Exercises

## Squat

Notes: skipped

## Bench Press

- 100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 7)
        self.assertIn("must contain at least one set", str(context.exception))


if __name__ == "__main__":
    unittest.main()
