"""Shared CSV formula neutralizer (SPEC-001, SPEC-003, NFR-006).

Synthetic values only. A stationary candidate is not a berth, anchorage,
wait, or port call. These tests fail if a fullwidth trigger is dropped from
the trigger set or if the apostrophe rule returns to the previous ambiguity.

The ignorable set is a fixed table. A Cf character that appears on this
interpreter and is neither in that table nor in ``EXCLUDED_CF`` fails the
drift guard, so a Unicode update cannot silently change the written bytes.
"""
import inspect
import unittest
import unicodedata

from harborlens.csv_safe import (
    FORMULA_TRIGGERS,
    IGNORABLE,
    _ignorable,
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


# Whitespace whose category is not Cf or Zs. These are the characters
# ``str.isspace`` accepts on Python 3.10 and 3.12 besides Zs. Cc is the
# category of the ASCII and C1 controls. U+2028 is Zl (line separator) and
# U+2029 is Zp (paragraph separator); both are whitespace and neither is Cc.
ENUMERATED_WHITESPACE = {
    0x0009: "Cc",
    0x000A: "Cc",
    0x000B: "Cc",
    0x000C: "Cc",
    0x000D: "Cc",
    0x001C: "Cc",
    0x001D: "Cc",
    0x001E: "Cc",
    0x001F: "Cc",
    0x0085: "Cc",
    0x2028: "Zl",
    0x2029: "Zp",
}

# Invisible characters the writer must skip before a trigger. This is the
# QA list plus the extra Cf characters judged ignorable in csv_safe.py.
LISTED_INVISIBLE = (
    "\ufeff\u200b\u200c\u200d\u200e\u200f"
    "\u2060\u2061\u2062\u2063\u2064"
    "\u206a\u206b\u206c\u206d\u206e\u206f"
    "\u00ad\u180e"
    "\u061c"
    "\u202a\u202b\u202c\u202d\u202e"
    "\u2066\u2067\u2068\u2069"
)

# Cf characters that are not ignorable. A new Cf on either interpreter must
# be added here with a concrete reason, or added to IGNORABLE, or this test
# fails and names the code point.
EXCLUDED_CF = {
    0x0600: "Arabic number sign: visible prefix, not ignorable",
    0x0601: "Arabic sign sanah: visible prefix, not ignorable",
    0x0602: "Arabic footnote marker: visible mark, not ignorable",
    0x0603: "Arabic sign safha: visible prefix, not ignorable",
    0x0604: "Arabic sign samvat: visible prefix, not ignorable",
    0x0605: "Arabic number mark above: visible mark, not ignorable",
    0x06DD: "Arabic end of ayah: visible enclosing mark, not ignorable",
    0x070F: "Syriac abbreviation mark: visible abbreviation line, not ignorable",
    0x0890: "Arabic pound mark above: visible mark, not ignorable",
    0x0891: "Arabic piastre mark above: visible mark, not ignorable",
    0x08E2: "Arabic disputed end of ayah: visible enclosing mark, not ignorable",
    0x110BD: "Kaithi number sign: visible prefix, not ignorable",
    0x110CD: "Kaithi number sign above: visible mark, not ignorable",
    0xFFF9: "interlinear annotation anchor: annotation control, not ignorable",
    0xFFFA: "interlinear annotation separator: annotation control, not ignorable",
    0xFFFB: "interlinear annotation terminator: annotation control, not ignorable",
}
EXCLUDED_CF.update({
    cp: "Egyptian hieroglyph format control: structures a sign cluster, not an ignorable prefix"
    for cp in range(0x13430, 0x13440)
})
EXCLUDED_CF.update({
    cp: "shorthand format control: structures overlap, not an ignorable prefix"
    for cp in range(0x1BCA0, 0x1BCA4)
})
EXCLUDED_CF.update({
    cp: "musical symbol format control: structures notation, not an ignorable prefix"
    for cp in range(0x1D173, 0x1D17B)
})
EXCLUDED_CF.update({0xE0001: "tag character: language tag, not ignorable"})
EXCLUDED_CF.update({
    cp: "tag character: deprecated tag, not ignorable"
    for cp in range(0xE0020, 0xE0080)
})

TRIGGERS = "=+-@\t\r\uff1d\uff0b\uff0d\uff20"


class IgnorableSetTests(unittest.TestCase):
    def test_every_member_is_cf_zs_or_enumerated_whitespace(self):
        """U+180E may be Cf or Zs. Enumerated whitespace may be Cc, Zl, or Zp."""
        for character in IGNORABLE:
            code = ord(character)
            category = unicodedata.category(character)
            with self.subTest(code=f"U+{code:04X}", category=category):
                if code == 0x180E:
                    self.assertIn(category, {"Cf", "Zs"})
                    continue
                if category in {"Cf", "Zs"}:
                    continue
                expected = ENUMERATED_WHITESPACE.get(code)
                self.assertIsNotNone(
                    expected,
                    f"U+{code:04X} is {category}, not Cf or Zs, and is not enumerated whitespace",
                )
                self.assertEqual(category, expected)
                self.assertIn(category, {"Cc", "Zl", "Zp"})
        for code, expected in ENUMERATED_WHITESPACE.items():
            self.assertIn(chr(code), IGNORABLE)
            self.assertEqual(unicodedata.category(chr(code)), expected)

    def test_runtime_lookup_does_not_consult_unicode_tables(self):
        source = inspect.getsource(_ignorable) + inspect.getsource(matches_formula_pattern)
        self.assertNotIn("isspace", source)
        self.assertNotIn("unicodedata", source)
        self.assertNotIn("category", source)
        self.assertTrue(_ignorable("\u200c"))
        self.assertFalse(_ignorable("A"))

    def test_every_cf_is_ignorable_or_explicitly_excluded(self):
        """A Cf added by a newer Unicode table fails here and is listed."""
        missing = []
        for code in range(0x110000):
            if unicodedata.category(chr(code)) != "Cf":
                continue
            if chr(code) in IGNORABLE or code in EXCLUDED_CF:
                continue
            missing.append(f"U+{code:04X} {unicodedata.name(chr(code), 'UNNAMED')}")
        if missing:
            self.fail(
                "New Cf code points are not in IGNORABLE or EXCLUDED_CF:\n" + "\n".join(missing)
            )
        overlap = [f"U+{code:04X}" for code in EXCLUDED_CF if chr(code) in IGNORABLE]
        self.assertEqual(overlap, [])
        for code, reason in EXCLUDED_CF.items():
            self.assertIsInstance(reason, str)
            self.assertTrue(reason.strip(), f"U+{code:04X} has an empty reason")
            self.assertNotIn("todo", reason.casefold())

    def test_each_listed_character_before_each_trigger_is_neutralized(self):
        self.assertEqual(set(TRIGGERS), set(FORMULA_TRIGGERS))
        combinations = (
            "\u200c\u200d",
            "\u00ad\u180e",
            "\u200e\u200f\u2060",
            " \u200c",
            "\u00a0\u2063",
            "\ufeff\u200b\u200c",
            "\u202e\u2066\u061c",
            LISTED_INVISIBLE,
        )
        cases = [(character, character) for character in LISTED_INVISIBLE]
        cases.extend((combo, combo) for combo in combinations)
        for prefix, label in cases:
            for trigger in TRIGGERS:
                logical = prefix + trigger + "x"
                with self.subTest(prefix=label, trigger=hex(ord(trigger))):
                    self.assertTrue(matches_formula_pattern(logical, min_apostrophes=0))
                    written = neutralize_text_cell(logical)
                    self.assertEqual(written, "'" + logical)
                    self.assertEqual(recover_text_cell(written), logical)
                    quoted = "'" + logical
                    self.assertEqual(neutralize_text_cell(quoted), "'" + quoted)
                    self.assertEqual(recover_text_cell("'" + quoted), quoted)

    def test_ignorable_in_the_middle_or_at_the_end_does_not_trigger(self):
        self.assertEqual(neutralize_text_cell("'abc"), "'abc")
        self.assertEqual(recover_text_cell("'abc"), "'abc")
        for character in LISTED_INVISIBLE:
            middle = "ab" + character + "=x"
            end = "abc" + character
            with self.subTest(code=f"U+{ord(character):04X}"):
                self.assertFalse(matches_formula_pattern(middle, min_apostrophes=0))
                self.assertEqual(neutralize_text_cell(middle), middle)
                self.assertEqual(recover_text_cell(middle), middle)
                self.assertEqual(neutralize_text_cell(end), end)
                self.assertEqual(recover_text_cell(end), end)
                self.assertEqual(neutralize_text_cell("'" + end), "'" + end)

    def test_boundaries_empty_ignorables_and_apostrophe_forms(self):
        only = "\u200c\u200d\u00ad\u180e \ufeff\u2060"
        self.assertEqual(neutralize_text_cell(only), only)
        self.assertEqual(recover_text_cell(only), only)
        self.assertEqual(neutralize_text_cell(""), "")
        self.assertEqual(recover_text_cell(""), "")
        self.assertEqual(neutralize_text_cell("'abc"), "'abc")
        self.assertEqual(recover_text_cell("'abc"), "'abc")
        self.assertEqual(neutralize_text_cell("'=x"), "''=x")
        self.assertEqual(recover_text_cell("''=x"), "'=x")
        self.assertEqual(recover_text_cell(neutralize_text_cell("'=x")), "'=x")
        self.assertEqual(neutralize_text_cell("''=x"), "'''=x")
        self.assertEqual(recover_text_cell("'''=x"), "''=x")
        self.assertEqual(recover_text_cell(neutralize_text_cell("''=x")), "''=x")
        # A visible Cf prefix is not ignorable, so the cell is left as text.
        visible = "\u0600=cmd"
        self.assertEqual(neutralize_text_cell(visible), visible)
        self.assertEqual(recover_text_cell(visible), visible)


if __name__ == "__main__":
    unittest.main()
