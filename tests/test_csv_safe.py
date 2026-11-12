"""Shared CSV formula neutralizer (SPEC-001, SPEC-003, NFR-006).

Synthetic values only. A stationary candidate is not a berth, anchorage,
wait, or port call. These tests fail if a fullwidth trigger is dropped from
the trigger set or if the apostrophe rule returns to the previous ambiguity.
"""
import unittest

from harborlens.csv_safe import (
    FORMULA_TRIGGERS,
    matches_formula_pattern,
    neutralize_text_cell,
    recover_text_cell,
)


ROUND_TRIPS = (
    ("plain apostrophe", "'abc", "'abc"),
    ("apostrophe then trigger", "'=x", "''=x"),
    ("two apostrophes then trigger", "''=x", "'''=x"),
    ("equals", "=x", "'=x"),
    ("plus", "+x", "'+x"),
    ("minus", "-x", "'-x"),
    ("at", "@SUM", "'@SUM"),
    ("tab", "\tcmd", "'\tcmd"),
    ("carriage return", "\rcmd", "'\rcmd"),
    ("leading spaces", "  =cmd", "'  =cmd"),
    ("bom then equals", "\ufeff=1+1", "'\ufeff=1+1"),
    ("zwsp then at", "\u200b@SUM", "'\u200b@SUM"),
    ("fullwidth equals", "\uff1dcmd", "'\uff1dcmd"),
    ("fullwidth plus", "\uff0bcmd", "'\uff0bcmd"),
    ("fullwidth minus", "\uff0dcmd", "'\uff0dcmd"),
    ("fullwidth at", "\uff20cmd", "'\uff20cmd"),
    ("nbsp then plus", "\u00a0+1", "'\u00a0+1"),
    ("ordinary", "70", "70"),
    ("negative number is a trigger when passed here", "-95.1", "'-95.1"),
)


class FormulaRuleTests(unittest.TestCase):
    def test_trigger_set_contains_ascii_and_fullwidth(self):
        """Dropping a fullwidth code point fails this test before any round trip."""
        for character in "=+-@\t\r\uff1d\uff0b\uff0d\uff20":
            self.assertIn(character, FORMULA_TRIGGERS)
        self.assertNotIn("'", FORMULA_TRIGGERS)
        self.assertNotIn("\ufeff", FORMULA_TRIGGERS)
        self.assertNotIn("\u200b", FORMULA_TRIGGERS)
        self.assertNotIn("\u00a0", FORMULA_TRIGGERS)

    def test_writer_and_reader_are_inverses_for_the_required_cases(self):
        for name, logical, disk in ROUND_TRIPS:
            with self.subTest(case=name):
                self.assertEqual(neutralize_text_cell(logical), disk)
                self.assertEqual(recover_text_cell(disk), logical)
                self.assertEqual(recover_text_cell(neutralize_text_cell(logical)), logical)

    def test_apostrophe_rule_is_not_the_previous_ambiguity(self):
        """0.2.0.dev16 kept '=x on disk and read it back as =x.

        The writer now emits ''=x, and the reader removes exactly one
        apostrophe, so the raw apostrophe survives.
        """
        self.assertTrue(matches_formula_pattern("'=x", min_apostrophes=0))
        self.assertTrue(matches_formula_pattern("''=x", min_apostrophes=1))
        self.assertFalse(matches_formula_pattern("'abc", min_apostrophes=0))
        self.assertFalse(matches_formula_pattern("'abc", min_apostrophes=1))
        self.assertEqual(neutralize_text_cell("'=x"), "''=x")
        self.assertNotEqual(neutralize_text_cell("'=x"), "'=x")
        self.assertEqual(recover_text_cell("''=x"), "'=x")
        self.assertEqual(recover_text_cell("'abc"), "'abc")
        # A single apostrophe on disk is the neutralized form of a bare trigger.
        self.assertEqual(recover_text_cell("'=x"), "=x")

    def test_reader_does_not_strip_without_a_trigger(self):
        self.assertEqual(recover_text_cell("abc"), "abc")
        self.assertEqual(recover_text_cell("'abc"), "'abc")
        self.assertEqual(recover_text_cell(""), "")
        self.assertEqual(neutralize_text_cell(""), "")
        self.assertEqual(neutralize_text_cell(None), "")


if __name__ == "__main__":
    unittest.main()
