"""Vessel attributes and MMSI QA flags for stratified evaluation (SPEC-001, issue #39).

Transmitted static and voyage data (class A/B, dimensions, draft) and course
fields are kept for cohort analysis, with NOAA "not available" sentinels mapped
to empty values. MMSI categories follow the ITU-R M.585 numbering scheme; they
are QA flags only. No row is dropped because of its category, and MMSI is
never treated as a verified vessel identity (BR-008).
"""
from __future__ import annotations

import math
from collections import Counter

MMSI_CATEGORIES = (
    "ship", "group_of_ships", "coast_station", "sar_aircraft", "aid_to_navigation",
    "craft_associated_with_parent_ship", "handheld_vhf", "ais_sart", "mob_device", "epirb_ais",
    "placeholder", "leading_zero_ambiguous", "other",
)
PLACEHOLDERS = {"123456789", "987654321", "012345678"}
ATTRIBUTE_FIELDS = ("cog_deg", "heading_deg", "length_m", "width_m", "draft_m", "transceiver_class")


def mmsi_category(mmsi):
    """Classify a transmitted MMSI string (8 or 9 digits) by ITU-R M.585 prefix."""
    if len(set(mmsi)) == 1 or mmsi in PLACEHOLDERS:
        return "placeholder"
    if len(mmsi) == 8:
        # NOAA stores MMSI as a number, so a leading zero (group or coast station) is lost.
        return "leading_zero_ambiguous"
    if mmsi.startswith("00"):
        return "coast_station"
    if mmsi.startswith("0"):
        return "group_of_ships"
    if mmsi.startswith("111"):
        return "sar_aircraft"
    if mmsi.startswith("970"):
        return "ais_sart"
    if mmsi.startswith("972"):
        return "mob_device"
    if mmsi.startswith("974"):
        return "epirb_ais"
    if mmsi.startswith("98"):
        return "craft_associated_with_parent_ship"
    if mmsi.startswith("99"):
        return "aid_to_navigation"
    if mmsi[0] == "8":
        return "handheld_vhf"
    if mmsi[0] in "234567":
        return "ship"
    return "other"


def _number(value, low, high, missing=()):
    """Finite number within [low, high] and not a sentinel; otherwise None."""
    try:
        number = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number in missing or not low <= number <= high:
        return None
    return number


def normalize_attributes(cog=None, heading=None, length=None, width=None, draft=None, transceiver=None):
    """Canonical attributes with NOAA sentinels (COG 360, heading 511, 0 dimensions) as None."""
    tclass = str(transceiver or "").strip().upper().replace("CLASS", "").strip()
    return {
        "cog_deg": _number(cog, 0, 359.9999),
        "heading_deg": _number(heading, 0, 359, missing=(511,)),
        "length_m": _number(length, 0.1, 600),
        "width_m": _number(width, 0.1, 100),
        "draft_m": _number(draft, 0.1, 30),
        "transceiver_class": tclass if tclass in ("A", "B") else None,
    }


def csv_value(value):
    return "" if value is None else value


def parse_csv_attributes(row):
    """Attributes from a canonical cleaned CSV row (empty cells mean not available)."""
    out = {}
    for field in ATTRIBUTE_FIELDS:
        raw = (row.get(field) or "").strip()
        if field == "transceiver_class":
            out[field] = raw or None
        else:
            try:
                out[field] = float(raw) if raw else None
            except ValueError:
                out[field] = None
    return out


class AttributeSummary:
    """Dominant transmitted attributes of one candidate (most frequent non-empty value)."""

    def __init__(self):
        self.counters = {"transceiver_class": Counter(), "length_m": Counter(), "draft_m": Counter()}

    def add(self, attributes):
        if not attributes:
            return
        for field, counter in self.counters.items():
            value = attributes.get(field)
            if value not in (None, ""):
                counter[value] += 1

    def result(self):
        def mode(counter):
            if not counter:
                return None
            return sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0])))[0][0]
        return {field: mode(counter) for field, counter in self.counters.items()}
