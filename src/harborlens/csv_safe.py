"""Shared CSV formula neutralization (SPEC-001, SPEC-003, NFR-006).

Spreadsheet applications evaluate a cell whose first significant character is
``=``, ``+``, ``-``, ``@``, tab, carriage return, or the fullwidth forms
``＝`` ``＋`` ``－`` ``＠`` (U+FF1D, U+FF0B, U+FF0D, U+FF20). One ASCII
apostrophe forces the cell to be text.

Characters that may sit between a leading apostrophe and that trigger, and
that are ignored, are the fixed code points in ``IGNORABLE``. That set is the
whitespace characters this module used to accept, written out one by one, plus
U+FEFF, U+200B, and the other invisible format characters named below. The
module does not consult the Unicode character database at runtime, so Python
3.10 and 3.12 write the same bytes. Tab and carriage return are both ignorable
and triggers. The match is the pattern ``^'*<ignorable>*<trigger>``: the first
character that is a trigger ends the scan, so a leading tab is a trigger.

Writer. Prepend one apostrophe when the value matches
``^'*<ignorable>*<trigger>`` (zero or more leading apostrophes, then
ignorables, then a trigger).

Reader. Remove exactly one leading apostrophe when the value matches
``^'+<ignorable>*<trigger>`` (one or more leading apostrophes, then
ignorables, then a trigger), and never otherwise.

A raw value that already starts with an apostrophe therefore survives a
round trip. ``'=x`` is written ``''=x`` and read back ``'=x``. ``'abc``
matches neither pattern and is unchanged on disk and on read. Package
``0.2.0.dev16`` treated a leading apostrophe followed by a trigger as
indistinguishable from a neutralized cell. That ambiguity is resolved here.

Numeric columns and contract identifiers are not passed to the writer.
``-95.1`` stays ``-95.1``. GeoJSON is out of scope: a JSON string is not a
spreadsheet formula.
"""
from __future__ import annotations

# ASCII apostrophe. A spreadsheet treats a cell that begins with this as text.
NEUTRALIZATION_PREFIX = "'"
# First significant character that a spreadsheet may evaluate.
FORMULA_TRIGGERS = frozenset("=+-@\t\r\uff1d\uff0b\uff0d\uff20")
# One fixed set. Membership is a table lookup. Do not derive it from
# ``unicodedata.category`` or ``str.isspace``: those tables are not the same
# on every supported interpreter.
IGNORABLE = frozenset(
    # Whitespace this module treated as ignorable, enumerated so the main
    # fixture stays byte-identical. The same 29 characters are whitespace on
    # Python 3.10 (Unicode 13.0) and Python 3.12 (Unicode 15.0).
    "\t\n\v\f\r"
    "\u001c\u001d\u001e\u001f"
    "\u0085"
    " \u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029"
    "\u202f\u205f\u3000"
    # Invisible format characters that can sit in front of a trigger.
    "\ufeff\u200b\u200c\u200d\u200e\u200f"
    "\u2060\u2061\u2062\u2063\u2064"
    "\u206a\u206b\u206c\u206d\u206e\u206f"
    "\u00ad\u180e"
    # Other Cf characters judged ignorable. One reason each.
    "\u061c"  # Arabic letter mark: invisible bidi mark, same role as LRM/RLM.
    "\u202a"  # Left-to-right embedding: invisible bidi control.
    "\u202b"  # Right-to-left embedding: invisible bidi control.
    "\u202c"  # Pop directional formatting: invisible bidi control.
    "\u202d"  # Left-to-right override: invisible bidi control.
    "\u202e"  # Right-to-left override: invisible bidi control.
    "\u2066"  # Left-to-right isolate: invisible bidi control.
    "\u2067"  # Right-to-left isolate: invisible bidi control.
    "\u2068"  # First strong isolate: invisible bidi control.
    "\u2069"  # Pop directional isolate: invisible bidi control.
)


def cell_text(value):
    """Text a CSV field would carry, without adding a neutralization prefix."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, bool):
        return "True" if value else "False"
    return str(value)


def _ignorable(character):
    return character in IGNORABLE


def matches_formula_pattern(value, *, min_apostrophes=0):
    """True when ``value`` matches ``^'*`` or ``^'+`` then ignorables then a trigger.

    ``min_apostrophes`` is 0 for the writer and 1 for the reader. A character
    that is both ignorable and a trigger (tab, carriage return) is the trigger.
    """
    text = cell_text(value)
    index = 0
    size = len(text)
    apostrophes = 0
    while index < size and text[index] == NEUTRALIZATION_PREFIX:
        apostrophes += 1
        index += 1
    if apostrophes < min_apostrophes:
        return False
    while index < size:
        if text[index] in FORMULA_TRIGGERS:
            return True
        if _ignorable(text[index]):
            index += 1
            continue
        return False
    return False


def neutralize_text_cell(value):
    """Prefix one ASCII apostrophe when ``value`` matches the writer rule.

    Do not pass numeric columns or contract identifiers. An empty cell and a
    cell that does not match are returned unchanged. ``'abc`` is unchanged.
    ``'=x`` becomes ``''=x``.
    """
    text = cell_text(value)
    if matches_formula_pattern(text, min_apostrophes=0):
        return NEUTRALIZATION_PREFIX + text
    return text


def recover_text_cell(value):
    """Remove one leading apostrophe when ``value`` matches the reader rule.

    ``''=x`` becomes ``'=x``. ``'=x`` becomes ``=x``. ``'abc`` is unchanged.
    A value with no leading apostrophe is unchanged, including ``=x``.
    """
    text = cell_text(value)
    if matches_formula_pattern(text, min_apostrophes=1):
        return text[1:]
    return text


def quote_csv_field(value):
    """Quote a field that contains a comma, quote, carriage return, or line feed.

    Python 3.10's ``csv.writer`` leaves a carriage return bare when the line
    ending is ``\\n``. Python 3.12 quotes it. Quoting here makes both
    interpreters write the same bytes. A field with none of those characters
    stays unquoted.
    """
    text = cell_text(value)
    if any(character in text for character in ",\"\r\n"):
        return '"' + text.replace('"', '""') + '"'
    return text


class CsvDictWriter:
    """Stream CSV rows with stable quoting on Python 3.10 and 3.12.

    Fields that do not need quotes are written the same way ``csv.DictWriter``
    writes them, including ``\\r\\n`` when that is the line ending. A field
    that contains a carriage return is quoted on both interpreters.
    """

    def __init__(self, stream, fieldnames, lineterminator="\r\n"):
        self.stream = stream
        self.fieldnames = list(fieldnames)
        self.lineterminator = lineterminator
        self.stream.write(",".join(self.fieldnames) + lineterminator)

    def writerow(self, row):
        if not isinstance(row, dict):
            raise ValueError("CSV row must be a mapping")
        extra = set(row) - set(self.fieldnames)
        if extra:
            raise ValueError("dict contains fields not in fieldnames: " + ", ".join(sorted(extra)))
        rendered = ",".join(quote_csv_field(row.get(field, "")) for field in self.fieldnames)
        self.stream.write(rendered + self.lineterminator)
