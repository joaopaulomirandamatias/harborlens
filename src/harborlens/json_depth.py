"""Container depth of a JSON text, counted before ``json.loads``.

One forward pass. A top-level ``{`` or ``[`` is depth 1. Each nested
object or array adds one. Characters inside a JSON string do not count,
including a brace after an escaped quote. The scan does not call itself
and does not parse the document.

``MAX_JSON_NESTING`` is 512. A GeoJSON coordinate list is only a few
containers deep, and a schema-valid rights register stops at 4. 512 is
above those documents and below the point where CPython 3.10 raises
``RecursionError`` while parsing (about 993 nested containers). CPython
3.12 still parses about 9995 levels. Rejecting above 512 makes 3.10,
3.12, and 3.14 agree, including a runner whose C stack lets 3.14 parse
a 100000-array document. The rights register uses a tighter limit of 4.
"""
from __future__ import annotations

MAX_JSON_NESTING = 512


def max_container_depth(text, *, limit=None):
    """Return the deepest object or array nesting in ``text``.

    When ``limit`` is set, return as soon as the depth passes it. The
    value is then ``limit + 1``, which is enough for a ``> limit`` check
    and does not walk the rest of a very deep document.
    """
    depth = 0
    maximum = 0
    in_string = False
    escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
            continue
        if character == '"':
            in_string = True
        elif character in "{[":
            depth += 1
            if depth > maximum:
                maximum = depth
            if limit is not None and depth > limit:
                return depth
        elif character in "}]" and depth:
            depth -= 1
    return maximum
