import unittest

from liftscript.errors import ParseError
from liftscript.parser import parse_liftscript
from liftscript.serializer import serialize_liftscript, to_csv


EXAMPLE = """2026-05-02
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
"""


class ParserTests(unittest.TestCase):
    def test_parse_full_example(self):
        workout = parse_liftscript(EXAMPLE)

        self.assertEqual(workout["date"], "2026-05-02")
        self.assertEqual(workout["title"], "Push Day")
        self.assertEqual(workout["metadata"], {"unit": "kg"})
        self.assertEqual(len(workout["exercises"]), 3)
        self.assertEqual(len(workout["exercises"][0]["sets"]), 3)
        self.assertEqual(workout["exercises"][0]["sets"][2]["rpe"], 8)
        self.assertEqual(len(workout["exercises"][1]["sets"]), 3)
        self.assertEqual(workout["exercises"][1]["sets"][2]["reps"], 8)
        self.assertEqual(workout["exercises"][2]["sets"][0]["type"], "amrap")

    def test_missing_title_with_blank_line(self):
        workout = parse_liftscript(
            """2026-05-02

unit: kg

Squat
140 x 5
"""
        )

        self.assertIsNone(workout["title"])
        self.assertEqual(workout["metadata"], {"unit": "kg"})
        self.assertEqual(workout["exercises"][0]["name"], "Squat")

    def test_missing_title_with_immediate_exercise_uses_lookahead(self):
        workout = parse_liftscript(
            """2026-05-02
Deadlift
180 x 3
"""
        )

        self.assertIsNone(workout["title"])
        self.assertEqual(workout["exercises"][0]["name"], "Deadlift")

    def test_bodyweight_set(self):
        workout = parse_liftscript(
            """2026-05-02

Pull Up
BW x 10
"""
        )

        set_entry = workout["exercises"][0]["sets"][0]
        self.assertTrue(set_entry["bodyweight"])
        self.assertIsNone(set_entry["weight"])
        self.assertIsNone(set_entry["unit"])

    def test_loaded_bodyweight_set(self):
        workout = parse_liftscript(
            """2026-05-02

Dip
BW+20kg x 5
"""
        )

        set_entry = workout["exercises"][0]["sets"][0]
        self.assertTrue(set_entry["bodyweight"])
        self.assertEqual(set_entry["weight"], 20)
        self.assertEqual(set_entry["unit"], "kg")

    def test_weight_unit_and_decimal_weight(self):
        workout = parse_liftscript(
            """2026-05-02

Bench Press
225lb x 3
102.5kg x 2
"""
        )

        first, second = workout["exercises"][0]["sets"]
        self.assertEqual(first["weight"], 225)
        self.assertEqual(first["unit"], "lb")
        self.assertEqual(second["weight"], 102.5)
        self.assertEqual(second["unit"], "kg")

    def test_all_modifiers(self):
        workout = parse_liftscript(
            """2026-05-02

Squat
100 x 5 @8.5 r=120s t=3-1-1 warmup
"""
        )

        set_entry = workout["exercises"][0]["sets"][0]
        self.assertEqual(set_entry["rpe"], 8.5)
        self.assertEqual(set_entry["rest_seconds"], 120)
        self.assertEqual(set_entry["tempo"], "3-1-1")
        self.assertEqual(set_entry["type"], "warmup")

    def test_multi_rep_modifiers_apply_to_each_expanded_set(self):
        workout = parse_liftscript(
            """2026-05-02

Incline DB Press
30 x 10, 8 @8
"""
        )

        sets = workout["exercises"][0]["sets"]
        self.assertEqual([set_entry["reps"] for set_entry in sets], [10, 8])
        self.assertEqual([set_entry["rpe"] for set_entry in sets], [8, 8])

    def test_serializer_round_trip(self):
        workout = parse_liftscript(EXAMPLE)
        rendered = serialize_liftscript(workout)
        reparsed = parse_liftscript(rendered)

        self.assertEqual(reparsed, workout)
        self.assertIn("30 x 10, 10, 8", rendered)

    def test_csv_export(self):
        workout = parse_liftscript(EXAMPLE)
        csv_text = to_csv(workout)

        self.assertIn("date,exercise,set_index,weight,reps,rpe,type\n", csv_text)
        self.assertIn("2026-05-02,Bench Press,3,100,5,8,\n", csv_text)
        self.assertIn("2026-05-02,Lateral Raise,1,12,15,,amrap\n", csv_text)

    def test_invalid_date_raises_line_number(self):
        with self.assertRaises(ParseError) as context:
            parse_liftscript(
                """2026-02-30

Squat
100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 1)
        self.assertIn("invalid calendar date", str(context.exception))

    def test_malformed_set_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_liftscript(
                """2026-05-02

Squat
100x5
"""
            )

        self.assertEqual(context.exception.line_number, 4)
        self.assertIn("expected set line", str(context.exception))

    def test_unknown_modifier_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_liftscript(
                """2026-05-02

Squat
100 x 5 hard
"""
            )

        self.assertEqual(context.exception.line_number, 4)
        self.assertIn("unknown modifier 'hard'", str(context.exception))

    def test_duplicate_modifier_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_liftscript(
                """2026-05-02

Squat
100 x 5 @8 @9
"""
            )

        self.assertEqual(context.exception.line_number, 4)
        self.assertIn("duplicate RPE modifier", str(context.exception))

    def test_exercise_without_sets_raises(self):
        with self.assertRaises(ParseError) as context:
            parse_liftscript(
                """2026-05-02

Squat

Bench Press
100 x 5
"""
            )

        self.assertEqual(context.exception.line_number, 3)
        self.assertIn("must contain at least one set", str(context.exception))


if __name__ == "__main__":
    unittest.main()
