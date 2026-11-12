"""Fixed 1:1 map from legacy synthetic MMSIs onto unassigned MID 199.

Every image matches ``1990xxxxx`` (nine digits, MID 199, fourth digit 0).
Rules are closed integer ranges. ``new = new_start + (legacy - legacy_start)``.
The legacy ranges do not overlap, and the images do not overlap.

MID 199 is outside the assigned MID block 201-775. ``mmsi_category`` returns
``other`` when the first digit is ``1`` and ``ship`` when the first digit is
``2`` through ``7``, so a vessel id that moves from MID 367 to MID 199 changes
category from ``ship`` to ``other``. This module does not change that classifier.

These strings are synthetic test identifiers. They are not vessel identities
and they are not AIS observations.
"""
from __future__ import annotations

# (legacy_start, legacy_end inclusive, new_start)
SYNTHETIC_ID_RULES = (
    # tools/benchmark_multiday.py used f"3670{n:05d}" for n in range(800).
    (367000000, 367000799, 199000000),
    # Labeling fixtures: 367100001-367100044.
    (367100000, 367100099, 199010000),
    # f"36711{index:04d}" for index 0..16, plus the 367110009 literal.
    (367110000, 367110016, 199011000),
    # Category-table probe. It was asserted as ship under MID 367.
    (367123450, 367123450, 199012345),
    # Evaluation harness and evaluator: f"36720000{n}" for n in 0..7.
    (367200000, 367200007, 199020000),
    (367300001, 367300001, 199030001),
    # tests/fixtures/synthetic_ais.csv and `367800001 + i` for i in 0..11.
    (367800001, 367800012, 199080001),
    # Category-table probe. It was asserted as ship under MID 538.
    (538001234, 538001234, 199090001),
)


def expand_rules(rules=SYNTHETIC_ID_RULES):
    """Expand range rules to a legacy-string → new-string map."""
    mapping = {}
    images = {}
    for start, end, new_start in rules:
        if end < start:
            raise ValueError(f"inverted range {start}..{end}")
        width = end - start
        for offset in range(width + 1):
            legacy = str(start + offset)
            modern = str(new_start + offset)
            if len(legacy) != 9 or len(modern) != 9:
                raise ValueError(f"non 9-digit pair {legacy} -> {modern}")
            if not modern.startswith("1990"):
                raise ValueError(f"image is not 1990xxxxx: {modern}")
            if legacy in mapping or modern in images:
                raise ValueError(f"collision {legacy} -> {modern}")
            mapping[legacy] = modern
            images[modern] = legacy
    return mapping


SYNTHETIC_ID_MAP = expand_rules()


def map_synthetic_mmsi(legacy):
    """Return the MID 199 id for one legacy synthetic id."""
    try:
        return SYNTHETIC_ID_MAP[str(legacy)]
    except KeyError as exc:
        raise KeyError(f"no synthetic mapping for {legacy}") from exc
