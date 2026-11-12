"""Labeling-pilot tooling (SPEC-003, issues #8 and #65): stratified sampling and agreement.

``harborlens-label-sample`` draws a seeded, stratified, blinded sample of
stationary candidates and negative (movement) intervals from one verified run.
Candidates are stratified by duration band, censoring, vessel group and AIS
transceiver class (A, B, or absent/unknown). Negatives are stratified by
vessel group and transceiver class. ``harborlens-label-agreement`` compares
two annotators' sheets.

Agreement between annotators is NOT accuracy of the method, and an L2 label is
expert review of AIS, not independent ground truth. Nothing here upgrades a
candidate to a berth, anchorage, wait or port call. See
docs/research/labeling-protocol.md.

Spreadsheet formula neutralization (SPEC-003, FR-013, NFR-006) uses
``harborlens.csv_safe``. The label sheet is the CSV this path writes. The
sampling key is JSON (``<sheet>.sampling.json``), not a CSV.
``harborlens-label-agreement`` reads sheets and writes JSON.
``harborlens-evaluate`` reads an adjudicated CSV and writes JSON; it does
not write a CSV. Cleaned AIS and stationary-candidate CSVs use the same
neutralizer.

A text cell is prefixed with one ASCII apostrophe (``'``) when it matches
``^'*<ignorable>*<trigger>``. Triggers are ``=``, ``+``, ``-``, ``@``, tab,
carriage return, and the fullwidth forms U+FF1D, U+FF0B, U+FF0D, and U+FF20.
Ignorable characters before the trigger are Unicode whitespace, U+FEFF, and
U+200B. A field that contains a comma, quote, carriage return, or line feed
is quoted, including on Python 3.10, whose ``csv.writer`` would otherwise
leave a carriage return bare when the row ends in ``\\n``.
``vessel_type_mode``, ``annotator_id``, ``evidence_sources``, ``notes``, and
``adjudicator_id`` are text. Contract columns are never prefixed:
``sample_id`` (``S`` and four digits), ``mmsi`` and ``observed_points``
(unsigned integers), ``centroid_lon`` and ``centroid_lat`` (finite decimals,
so ``-95.1`` is written unchanged), ``start_utc`` and ``end_utc`` (ISO-8601
with ``Z`` or ``±HH:MM``), censoring flags, the annotation enums, and
``true_start_utc`` / ``true_end_utc``. A contract value that fails its check
raises ``AISInputError`` before any sheet, ``.partial``, or sampling manifest
is created. The CLI exits 2.

On read, ``read_csv_cell`` removes exactly one leading apostrophe from a text
column, and only when the cell matches ``^'+<ignorable>*<trigger>``. A raw
value that already began with an apostrophe is written with one more
apostrophe, so the round trip keeps it. ``'abc`` is unchanged. The
``0.2.0.dev16`` ambiguity (a leading apostrophe plus a trigger was
indistinguishable from a neutralized cell) is resolved. A leading apostrophe
on a contract column raises ``AISInputError``. A contract column that comes
back carrying a trigger without that apostrophe, and that fails its contract,
also raises ``AISInputError`` (the case where a spreadsheet dropped the
prefix). The characters are not removed and the cell is not converted to a
number, timestamp, or enum. Edit the sheet with the column imported as text,
then re-validate it with this reader.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
import re
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from harborlens.ais import load_cleaned, parse_time, sha256
from harborlens.censoring import CENSORED, NOT_CENSORED, UNKNOWN, WindowCensoring
from harborlens.csv_safe import (
    matches_formula_pattern, neutralize_text_cell, quote_csv_field, recover_text_cell,
)
from harborlens.io_safe import AISInputError
from harborlens.provenance import digests_equal, verify_manifest
from harborlens.segmentation import SegmentationParams
from harborlens.timeparse import ExplicitOffsetRequired, parse_explicit_utc

SAMPLE_SCHEMA_V01 = "label-sample-v0.1"
SAMPLE_SCHEMA = "label-sample-v0.2"
AGREEMENT_SCHEMA = "label-agreement-v0.1"
# Closed stratum tokens. Anything other than A or B is absent_or_unknown and stays in the sample.
TRANSCEIVER_STRATA = ("A", "B", "absent_or_unknown")
# Canonical vessel groups returned by vessel_group(). The evaluator accepts only these.
VESSEL_GROUPS = ("cargo", "tanker", "passenger", "tug_or_service", "other_or_unknown")
LABELS = ("at_berth", "at_anchor", "other_stationary", "maneuvering", "transit", "mixed", "unknown")
COLLAPSED = {"at_berth": "stationary", "at_anchor": "stationary", "other_stationary": "stationary",
             "maneuvering": "moving", "transit": "moving", "mixed": "mixed", "unknown": "unknown"}
CONFIDENCE = ("high", "medium", "low")
EVIDENCE = ("L2", "L3")
FRAGMENT = ("true", "false", "unknown")
DURATION = ("assessable", "not_assessable")
UNIT_FIELDS = ["sample_id", "mmsi", "start_utc", "end_utc", "observed_points", "centroid_lon",
               "centroid_lat", "vessel_type_mode", "left_censoring", "right_censoring"]
ANNOTATION_FIELDS = ["annotator_id", "label", "confidence", "evidence_level", "evidence_sources",
                     "fragment_of_longer_stop", "duration_judgement", "notes"]
SHEET_FIELDS = UNIT_FIELDS + ANNOTATION_FIELDS
MAX_SAMPLE = 1000
WARNING = ("Blinded labeling sample of unvalidated AIS intervals. Keep sheets with MMSIs out of the public "
           "repository until data rights are reviewed. Labels are L2 expert review unless an independent "
           "operational record is cited (L3).")
# Free text. Neutralized on write. The reader may remove one neutralization prefix.
TEXT_COLUMNS = frozenset({
    "vessel_type_mode", "annotator_id", "evidence_sources", "notes", "adjudicator_id",
})
# Identifier, number, timestamp, or enum. Never neutralized. Never unquoted on read.
CONTRACT_COLUMNS = frozenset({
    "sample_id", "mmsi", "observed_points", "centroid_lon", "centroid_lat",
    "start_utc", "end_utc", "left_censoring", "right_censoring",
    "label", "confidence", "evidence_level", "fragment_of_longer_stop", "duration_judgement",
    "true_start_utc", "true_end_utc",
})
# Annotation enums are blank on the unlabeled sheet the sampler writes.
BLANK_ON_EXPORT = frozenset({
    "label", "confidence", "evidence_level", "fragment_of_longer_stop", "duration_judgement",
})
CENSORING_VALUES = frozenset({CENSORED, NOT_CENSORED, UNKNOWN})
ENUM_VALUES = {
    "left_censoring": CENSORING_VALUES,
    "right_censoring": CENSORING_VALUES,
    "label": frozenset(LABELS),
    "confidence": frozenset(CONFIDENCE),
    "evidence_level": frozenset(EVIDENCE),
    "fragment_of_longer_stop": frozenset(FRAGMENT),
    "duration_judgement": frozenset(DURATION),
}
_SAMPLE_ID = re.compile(r"^S[0-9]{4}$")
_UNSIGNED_INTEGER = re.compile(r"^[0-9]+$")
# Finite decimal as written. A leading minus or plus is part of the number.
# Leading whitespace is rejected so a numeric column cannot hide a formula trigger.
_FINITE_DECIMAL = re.compile(r"^[+-]?(?:[0-9]+\.[0-9]+|[0-9]+)(?:[eE][+-]?[0-9]+)?$")


def _cell_text(value):
    """Text csv.writer would emit for ``value``, without changing the value itself."""
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


def _contract_accepts(field, text):
    """True when ``text`` satisfies the column contract. A formula is not accepted."""
    try:
        _require_contract(field, text, allow_blank=False)
    except AISInputError:
        return False
    return True


def read_csv_cell(field, raw):
    """Logical value of one labeling or adjudicated CSV cell.

    Text columns use :func:`recover_text_cell`. Contract columns are returned
    unchanged when they satisfy their contract. A leading apostrophe on a
    contract column raises ``AISInputError`` and is not stripped, parsed, or
    converted. A contract cell that matches the writer trigger rule and fails
    its contract raises ``AISInputError`` as well. That is the spreadsheet
    case: the protective apostrophe was dropped and the cell came back as a
    formula. A signed coordinate such as ``-95.1`` matches the trigger
    character ``-`` and still satisfies the finite-decimal contract, so it is
    kept.
    """
    text = _cell_text(raw)
    if field in TEXT_COLUMNS:
        return recover_text_cell(text)
    if field not in CONTRACT_COLUMNS:
        raise AISInputError(f"{field} is not a label-sheet column")
    if text.startswith("'"):
        raise AISInputError(
            f"{field} {text!r} has a leading apostrophe. "
            "Contract columns are not unquoted and are not converted."
        )
    if matches_formula_pattern(text) and not _contract_accepts(field, text):
        raise AISInputError(
            f"{field} {text!r} carries a formula trigger without the neutralization apostrophe. "
            "Contract columns are not evaluated and are not converted."
        )
    return text


def _require_contract(field, value, allow_blank):
    """Raise ``AISInputError`` when ``value`` breaks the column contract.

    The returned object is ``value`` itself. The writer then serializes it
    the same way it did before neutralization existed.
    """
    text = _cell_text(value)
    if field == "sample_id":
        if _SAMPLE_ID.fullmatch(text) is None:
            raise AISInputError(f"sample_id {text!r} is not an S0000 identifier")
        return value
    if field in ("mmsi", "observed_points"):
        if _UNSIGNED_INTEGER.fullmatch(text) is None:
            raise AISInputError(f"{field} {text!r} is not an unsigned integer")
        return value
    if field in ("centroid_lon", "centroid_lat"):
        if _FINITE_DECIMAL.fullmatch(text) is None:
            raise AISInputError(f"{field} {text!r} is not a finite decimal number")
        number = float(text)
        if not math.isfinite(number):
            raise AISInputError(f"{field} {text!r} is not a finite decimal number")
        return value
    if field in ("start_utc", "end_utc", "true_start_utc", "true_end_utc"):
        if text == "" and field in ("true_start_utc", "true_end_utc"):
            return value
        try:
            parse_explicit_utc(text)
        except (TypeError, ValueError, ExplicitOffsetRequired) as exc:
            raise AISInputError(f"{field} {text!r} is not an ISO-8601 UTC timestamp") from exc
        return value
    if field in ENUM_VALUES:
        if text == "" and allow_blank and field in BLANK_ON_EXPORT:
            return value
        if text not in ENUM_VALUES[field]:
            raise AISInputError(f"{field} {text!r} is not an allowed value")
        return value
    raise AISInputError(f"{field} is not a contract column")


def prepare_sheet_row(row):
    """Validate one label-sheet row and neutralize its text cells.

    Contract columns are returned as the original objects so ``csv.writer``
    emits the same bytes it emitted before this check. Text columns are
    strings, with a leading apostrophe only when the trigger rule matches.
    """
    if not isinstance(row, dict):
        raise AISInputError("Label sheet row must be a mapping")
    prepared = {}
    for field in SHEET_FIELDS:
        value = row.get(field, "")
        if field in TEXT_COLUMNS:
            prepared[field] = neutralize_text_cell(value)
        else:
            prepared[field] = _require_contract(field, value, allow_blank=True)
    return prepared


def _quote_csv_field(value):
    """One CSV field, quoted when it contains a comma, quote, CR, or LF.

    ``csv.writer`` on Python 3.10 does not quote a carriage return when the
    line ending is ``\\n``. Python 3.12 does. A carriage return is also a
    formula trigger, so the sheet has to quote that field on both interpreters
    or the row splits. Cells with none of those characters stay unquoted, which
    is what the current synthetic sheet already does. The quoting rule lives
    in ``harborlens.csv_safe.quote_csv_field``.
    """
    return quote_csv_field(value)


def render_label_sheet(rows):
    """Return the label-sheet CSV. Raises ``AISInputError`` before any byte is useful.

    Callers write the returned text only after this function returns. A
    contract failure therefore creates no sheet, no ``.partial``, and no
    sampling manifest. Rows end in ``\\n``. A field that contains a comma,
    quote, carriage return, or line feed is quoted on Python 3.10 and 3.12.
    """
    prepared = [prepare_sheet_row(row) for row in rows]
    lines = [",".join(SHEET_FIELDS)]
    for row in prepared:
        lines.append(",".join(_quote_csv_field(row[field]) for field in SHEET_FIELDS))
    return "\n".join(lines) + "\n"


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def vessel_group(code):
    """Coarse AIS ship-type group used only for stratification.

    Every return value is a member of ``VESSEL_GROUPS``, which is the set the
    evaluator accepts.
    """
    try:
        value = int(float(code))
    except (TypeError, ValueError):
        return "other_or_unknown"
    if 70 <= value <= 79:
        return "cargo"
    if 80 <= value <= 89:
        return "tanker"
    if 60 <= value <= 69:
        return "passenger"
    if value in (21, 22, 31, 32, 33, 50, 51, 52, 53, 54, 55, 58):
        return "tug_or_service"
    return "other_or_unknown"


def transceiver_stratum(value):
    """Map a transmitted or stored AIS class to A, B, or absent_or_unknown.

    ``Class A`` / ``Class B`` normalize the same way as ingestion. Missing,
    blank and any other value (for example ``X``) become ``absent_or_unknown``.
    Callers keep the unit; this function never signals a drop.
    """
    text = str(value or "").strip().upper().replace("CLASS", "").strip()
    return text if text in ("A", "B") else "absent_or_unknown"


def parse_stratum(key, schema_version, sample_id=None):
    """Named components of a stratum key for an explicit sampling-manifest schema.

    ``label-sample-v0.2`` candidates are ``duration|censoring|vessel_group|transceiver_class``
    and negatives are ``negative|vessel_group|transceiver_class``. ``label-sample-v0.1``
    keys omit the class and are accepted only when ``schema_version`` is exactly that
    string. Field count is not used to guess the version. A damaged key raises
    ``AISInputError`` and names ``sample_id`` when one was supplied.
    """
    where = f"{sample_id}: " if sample_id else ""

    def reject(reason):
        raise AISInputError(f"{where}{reason}")

    if schema_version not in (SAMPLE_SCHEMA_V01, SAMPLE_SCHEMA):
        reject("sampling manifest schema_version "
               f"{schema_version!r} is missing or not a supported label-sample schema")
    if not isinstance(key, str) or not key or any(part == "" for part in key.split("|")):
        reject(f"stratum {key!r} is not a {schema_version} key")
    parts = key.split("|")
    negative = parts[0] == "negative"
    if schema_version == SAMPLE_SCHEMA:
        if negative:
            if len(parts) != 3:
                reject(f"stratum {key!r} is not a label-sample-v0.2 negative key "
                       "(negative|vessel_group|transceiver_class)")
            vessel, tclass = parts[1], parts[2]
            kind, duration, censoring = "negative", None, None
        else:
            if len(parts) != 4:
                reject(f"stratum {key!r} is not a label-sample-v0.2 candidate key "
                       "(duration|censoring|vessel_group|transceiver_class)")
            duration, censoring, vessel, tclass = parts
            kind = "candidate"
        if tclass not in TRANSCEIVER_STRATA:
            reject(f"transceiver_class {tclass!r} is not one of {', '.join(TRANSCEIVER_STRATA)}")
    else:
        if negative:
            if len(parts) != 2:
                reject(f"stratum {key!r} is not a label-sample-v0.1 negative key "
                       "(negative|vessel_group)")
            vessel, tclass = parts[1], None
            kind, duration, censoring = "negative", None, None
        else:
            if len(parts) != 3:
                reject(f"stratum {key!r} is not a label-sample-v0.1 candidate key "
                       "(duration|censoring|vessel_group)")
            duration, censoring, vessel = parts
            kind, tclass = "candidate", None
    if vessel not in VESSEL_GROUPS:
        reject(f"vessel_group {vessel!r} is not one of {', '.join(VESSEL_GROUPS)}")
    parsed = {"kind": kind, "vessel_group": vessel, "transceiver_class": tclass}
    if kind == "candidate":
        parsed["duration_band"] = duration
        parsed["censoring"] = censoring
    return parsed


def duration_band(minutes):
    return "lt_60" if minutes < 60 else ("60_180" if minutes <= 180 else "gt_180")


def censoring_status(left, right):
    if UNKNOWN in (left, right):
        return "unknown"
    return "censored" if CENSORED in (left, right) else "uncensored"


def _mode(values):
    counts = Counter(v for v in values if v)
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if counts else ""


def _window_from_manifest(manifest, tolerance):
    window = manifest.get("analysis_window") or {}
    if window.get("status") != "known":
        return WindowCensoring(None, tolerance)
    blocks = [{"start": parse_time(b["start_utc"]), "end": parse_time(b["end_utc"])} for b in window["blocks"]]
    return WindowCensoring(blocks, tolerance)


def _load_run(run_dir):
    run_dir = Path(run_dir)
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.is_file():
        raise AISInputError("Run directory has no manifest.json")
    check = verify_manifest(manifest_path)
    if not check["ok"]:
        raise AISInputError(f"Run artifacts fail integrity verification: {check['artifacts']}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    params = SegmentationParams.from_manifest(manifest.get("method_parameters"))
    geo = json.loads((run_dir / "stationary_candidates.geojson").read_text(encoding="utf-8"))
    candidates = []
    for feature in geo.get("features", []):
        props = feature["properties"]
        if not digests_equal(props.get("parameter_set"), params.parameter_set):
            raise AISInputError("Candidate parameter_set differs from the run manifest")
        candidates.append({**props, "lon": feature["geometry"]["coordinates"][0],
                           "lat": feature["geometry"]["coordinates"][1],
                           "start": parse_time(props["start_utc"]), "end": parse_time(props["end_utc"])})
    rows, unparsable = load_cleaned(run_dir / "houston_clean.csv")
    return manifest_path, manifest, params, candidates, rows, unparsable


def _negative_intervals(rows, params, candidates, min_minutes):
    """Maximal runs of moving observations (SOG above threshold, gaps within limit)."""
    busy = defaultdict(list)
    for c in candidates:
        busy[c["mmsi"]].append((c["start"], c["end"]))
    gap = timedelta(minutes=params.max_gap_minutes)
    intervals, current = [], []

    def close():
        if len(current) >= 2:
            start, end = current[0][1], current[-1][1]
            overlaps = any(a <= end and start <= b for a, b in busy[current[0][0]])
            if (end - start) >= timedelta(minutes=min_minutes) and not overlaps:
                intervals.append(list(current))

    for item in rows:
        mmsi, when, lat, lon, sog = item[:5]
        moving = sog > params.max_sog_knots
        if current and (not moving or mmsi != current[-1][0] or when - current[-1][1] > gap
                        or when <= current[-1][1]):
            close()
            current = []
        if moving:
            current.append(item)
    close()
    return intervals


def _interval_transceiver(run):
    """Most frequent A/B class in one movement interval; absent_or_unknown if neither occurs.

    Invalid and blank point values do not vote, so they cannot outvote a real class
    or create a stratum of their own. An interval with no A/B point is kept.
    """
    votes = []
    for row in run:
        raw = ""
        if len(row) > 7 and isinstance(row[7], dict):
            raw = row[7].get("transceiver_class") or ""
        bucket = transceiver_stratum(raw)
        if bucket in ("A", "B"):
            votes.append(bucket)
    if not votes:
        return "absent_or_unknown"
    return sorted(Counter(votes).items(), key=lambda kv: (-kv[1], kv[0]))[0][0]


def _allocate(strata, total, rng, cover=None):
    """At least one unit per non-empty stratum, remainder proportional (largest remainder).

    When fewer units are requested than there are non-empty strata, ``cover(key)``
    (the transceiver class) is drawn first: every covered value present in the frame
    gets one stratum when the request is at least that large, then a seeded sample
    fills any remainder. Empty strata are omitted. The proportional path does not
    consume ``cover`` and keeps the previous random sequence.
    """
    keys = sorted(k for k, members in strata.items() if members)
    total = min(total, sum(len(strata[k]) for k in keys))
    if total <= 0:
        return {}
    if total < len(keys):
        if cover is None:
            chosen = rng.sample(keys, total)
        else:
            by_value = defaultdict(list)
            for key in keys:
                by_value[cover(key)].append(key)
            values = sorted(by_value)
            if len(values) > total:
                values = sorted(rng.sample(values, total))
            chosen = [rng.choice(by_value[value]) for value in values]
            rest = [key for key in keys if key not in chosen]
            need = total - len(chosen)
            if need:
                chosen += rng.sample(rest, need)
        return {k: 1 for k in sorted(chosen)}
    allocation = {k: 1 for k in keys}
    spare = {k: len(strata[k]) - 1 for k in keys}
    remaining = total - len(keys)
    pool = sum(spare.values())
    if remaining and pool:
        shares = {k: remaining * spare[k] / pool for k in keys}
        for k in keys:
            allocation[k] += min(spare[k], math.floor(shares[k]))
        leftover = total - sum(allocation.values())
        for k in sorted(keys, key=lambda k: (-(shares[k] - math.floor(shares[k])), k)):
            if leftover <= 0:
                break
            if allocation[k] < len(strata[k]):
                allocation[k] += 1
                leftover -= 1
    return allocation


def _class_list(group, allocation, drawn_only):
    found = set()
    for key, members in group.items():
        if not members:
            continue
        if drawn_only and not allocation.get(key):
            continue
        found.add(parse_stratum(key, SAMPLE_SCHEMA)["transceiver_class"])
    return [name for name in TRANSCEIVER_STRATA if name in found]


def _stratification(strata, negative_strata, allocation):
    """Record whether the draw covered every non-empty stratum and every transceiver class."""
    non_empty = [key for group in (strata, negative_strata) for key, members in group.items() if members]
    return {
        "dimensions": {
            "candidates": ["duration_band", "censoring", "vessel_group", "transceiver_class"],
            "negatives": ["vessel_group", "transceiver_class"],
        },
        "all_non_empty_strata_drawn": all(allocation.get(key) for key in non_empty) if non_empty else True,
        "transceiver_classes": {
            "candidates": {"in_frame": _class_list(strata, allocation, False),
                           "drawn": _class_list(strata, allocation, True)},
            "negatives": {"in_frame": _class_list(negative_strata, allocation, False),
                          "drawn": _class_list(negative_strata, allocation, True)},
        },
    }


def draw_sample(run_dir, sheet, seed, candidates=70, negatives=30, min_negative_minutes=30):
    """Write a blinded labeling sheet and a sampling manifest holding the key.

    Text cells are neutralized and contract cells are validated before the
    sheet, its ``.partial`` file, or the sampling manifest is created.
    """
    sheet = Path(sheet)
    sampling = sheet.with_name(sheet.name + ".sampling.json")
    if sheet.suffix.lower() != ".csv" or sheet.exists() or sampling.exists():
        raise AISInputError("Sheet must be a new .csv path and its .sampling.json must not exist")
    if not (0 <= candidates <= MAX_SAMPLE and 0 <= negatives <= MAX_SAMPLE
            and candidates + negatives > 0 and min_negative_minutes > 0):
        raise AISInputError("Requested sample sizes are outside supported limits")
    manifest_path, manifest, params, stops, rows, unparsable = _load_run(run_dir)
    by_mmsi = defaultdict(list)
    for item in rows:
        by_mmsi[item[0]].append(item)
    rng = random.Random(seed)

    units = []
    strata = defaultdict(list)
    for c in sorted(stops, key=lambda c: c["event_id"]):
        types = [r[5] for r in by_mmsi[c["mmsi"]] if c["start"] <= r[1] <= c["end"]]
        mode = _mode(types)
        tclass = transceiver_stratum(c.get("transceiver_class"))
        key = "|".join((duration_band(c["duration_min"]),
                        censoring_status(c["left_censoring"], c["right_censoring"]),
                        vessel_group(mode), tclass))
        strata[key].append({"kind": "candidate", "event_id": c["event_id"], "stratum": key,
                            "transceiver_class": tclass,
                            "mmsi": c["mmsi"], "start": c["start"], "end": c["end"],
                            "points": c["point_count"], "lon": c["lon"], "lat": c["lat"], "type": mode,
                            "left": c["left_censoring"], "right": c["right_censoring"]})
    window = _window_from_manifest(manifest, params.max_gap_minutes)
    negative_strata = defaultdict(list)
    for run in _negative_intervals(rows, params, stops, min_negative_minutes):
        mode = _mode([r[5] for r in run])
        left, right = window.classify(run[0][1], run[-1][1])
        tclass = _interval_transceiver(run)
        key = "|".join(("negative", vessel_group(mode), tclass))
        negative_strata[key].append({
            "kind": "negative", "event_id": None, "stratum": key, "transceiver_class": tclass,
            "mmsi": run[0][0],
            "start": run[0][1], "end": run[-1][1], "points": len(run),
            "lon": round(sum(r[3] for r in run) / len(run), 6), "lat": round(sum(r[2] for r in run) / len(run), 6),
            "type": mode, "left": left, "right": right})

    allocation = {}
    for group, wanted in ((strata, candidates), (negative_strata, negatives)):
        plan = _allocate(group, wanted, rng,
                         cover=lambda key: parse_stratum(key, SAMPLE_SCHEMA)["transceiver_class"])
        allocation.update(plan)
        for key, count in plan.items():
            units.extend(rng.sample(group[key], count))
    if not units:
        raise AISInputError("The run has no candidates or negative intervals to sample")
    rng.shuffle(units)

    raw_rows = []
    key_rows = []
    for index, unit in enumerate(units, 1):
        sample_id = f"S{index:04d}"
        raw_rows.append({"sample_id": sample_id, "mmsi": unit["mmsi"], "start_utc": _iso(unit["start"]),
                         "end_utc": _iso(unit["end"]), "observed_points": unit["points"],
                         "centroid_lon": unit["lon"], "centroid_lat": unit["lat"],
                         "vessel_type_mode": unit["type"], "left_censoring": unit["left"],
                         "right_censoring": unit["right"]})
        key_rows.append({"sample_id": sample_id, "kind": unit["kind"], "event_id": unit["event_id"],
                         "stratum": unit["stratum"], "transceiver_class": unit["transceiver_class"]})
    # Validate and neutralize before creating the sheet, its .partial, or the manifest.
    rendered = render_label_sheet(raw_rows)
    sheet.parent.mkdir(parents=True, exist_ok=True)
    partial = sheet.with_name(sheet.name + ".partial")
    try:
        with partial.open("x", newline="", encoding="utf-8") as handle:
            handle.write(rendered)
        record = {
            "schema_version": SAMPLE_SCHEMA,
            "run_manifest_sha256": sha256(manifest_path),
            "run_id": manifest["run_id"],
            "method_version": params.manifest()["method_version"],
            "parameter_set": params.parameter_set,
            "seed": seed,
            "requested": {"candidates": candidates, "negatives": negatives,
                          "min_negative_minutes": min_negative_minutes},
            "frame": {"candidates": {k: len(v) for k, v in sorted(strata.items())},
                      "negatives": {k: len(v) for k, v in sorted(negative_strata.items())},
                      "unparsable_cleaned_rows": unparsable},
            "allocation": dict(sorted(allocation.items())),
            "stratification": _stratification(strata, negative_strata, allocation),
            "drawn": {"candidates": sum(1 for u in units if u["kind"] == "candidate"),
                      "negatives": sum(1 for u in units if u["kind"] == "negative")},
            "sheet_filename": sheet.name,
            "sheet_sha256": hashlib.sha256(partial.read_bytes()).hexdigest(),
            "key": key_rows,
            "rights_status": "review_required",
            "warning": WARNING,
        }
        with sampling.open("x", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2)
        os.replace(partial, sheet)
    except Exception:
        partial.unlink(missing_ok=True)
        if not sheet.exists():
            sampling.unlink(missing_ok=True)
        raise
    return record


def _read_sheet(path):
    """Read one annotator's completed sheet and validate every annotation field.

    Text columns are recovered with ``read_csv_cell``. A leading apostrophe
    on a contract column is an error and is not converted. A contract cell
    that carries a formula trigger without that apostrophe, and that fails
    its contract, is the same kind of error.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [f for f in ["sample_id", *ANNOTATION_FIELDS] if f not in (reader.fieldnames or [])]
        if missing:
            raise AISInputError(f"{path.name} lacks columns: {missing}")
        rows = list(reader)
    problems, labels, annotators = [], {}, set()
    allowed = {"label": LABELS, "confidence": CONFIDENCE, "evidence_level": EVIDENCE,
               "fragment_of_longer_stop": FRAGMENT, "duration_judgement": DURATION}
    for row in rows:
        try:
            sid = read_csv_cell("sample_id", row.get("sample_id"))
        except AISInputError as exc:
            problems.append(str(exc))
            continue
        row["sample_id"] = sid
        for field in SHEET_FIELDS:
            if field == "sample_id" or field not in row:
                continue
            try:
                row[field] = read_csv_cell(field, row[field])
            except AISInputError as exc:
                problems.append(f"{sid}: {exc}")
        if sid in labels:
            problems.append(f"{sid}: duplicated")
        for field, values in allowed.items():
            if row.get(field) not in values:
                problems.append(f"{sid}: {field}={row.get(field)!r}")
        if not (row.get("annotator_id") or "").strip():
            problems.append(f"{sid}: annotator_id missing")
        if not (row.get("evidence_sources") or "").strip():
            problems.append(f"{sid}: evidence_sources missing")
        elif row.get("evidence_level") == "L3" and "operational_record" not in row["evidence_sources"]:
            problems.append(f"{sid}: L3 requires an operational_record source")
        annotators.add(row.get("annotator_id"))
        labels[sid] = row
    if problems:
        raise AISInputError(f"{path.name} is not a complete, valid label sheet: " + "; ".join(problems[:20]))
    if len(annotators) != 1:
        raise AISInputError(f"{path.name} must contain exactly one annotator_id")
    return annotators.pop(), labels


def cohen_kappa(pairs):
    """Cohen's kappa for a list of (a, b) labels; None when chance agreement is 1."""
    n = len(pairs)
    if not n:
        return None
    observed = sum(a == b for a, b in pairs) / n
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(left[k] * right[k] for k in set(left) | set(right)) / (n * n)
    if expected >= 1:
        return None
    return round((observed - expected) / (1 - expected), 4)


def agreement(sheet_a, sheet_b, out, sampling=None):
    """Compare two annotators' sheets; write a JSON report. Agreement is not accuracy."""
    out = Path(out)
    if out.suffix.lower() != ".json" or out.exists():
        raise AISInputError("Output must be a new .json file")
    annotator_a, a = _read_sheet(sheet_a)
    annotator_b, b = _read_sheet(sheet_b)
    if annotator_a == annotator_b:
        raise AISInputError("The two sheets must come from different annotators")
    if set(a) != set(b):
        raise AISInputError("Both sheets must label exactly the same sample_ids")
    kinds = {}
    if sampling:
        record = json.loads(Path(sampling).read_text(encoding="utf-8"))
        kinds = {k["sample_id"]: k["kind"] for k in record.get("key", [])}
        if set(kinds) != set(a):
            raise AISInputError("Sampling manifest does not describe the labeled sample_ids")
    ids = sorted(a)
    pairs = [(a[i]["label"], b[i]["label"]) for i in ids]
    collapsed = [(COLLAPSED[x], COLLAPSED[y]) for x, y in pairs]
    confusion = {x: {y: 0 for y in LABELS} for x in LABELS}
    for x, y in pairs:
        confusion[x][y] += 1

    def summary(selected):
        sub = [(a[i]["label"], b[i]["label"]) for i in selected]
        col = [(COLLAPSED[x], COLLAPSED[y]) for x, y in sub]
        return {"units": len(sub),
                "raw_agreement": round(sum(x == y for x, y in sub) / len(sub), 4) if sub else None,
                "kappa_labels": cohen_kappa(sub), "kappa_collapsed": cohen_kappa(col)}

    report = {
        "schema_version": AGREEMENT_SCHEMA,
        "annotators": [annotator_a, annotator_b],
        "sheets_sha256": [sha256(Path(sheet_a)), sha256(Path(sheet_b))],
        **summary(ids),
        "collapsed_classes": sorted(set(COLLAPSED.values())),
        "confusion": confusion,
        "unknown_labels": {annotator_a: sum(a[i]["label"] == "unknown" for i in ids),
                           annotator_b: sum(b[i]["label"] == "unknown" for i in ids)},
        "evidence_levels": {annotator_a: dict(Counter(a[i]["evidence_level"] for i in ids)),
                            annotator_b: dict(Counter(b[i]["evidence_level"] for i in ids))},
        "by_kind": ({kind: summary([i for i in ids if kinds[i] == kind]) for kind in sorted(set(kinds.values()))}
                    if kinds else None),
        "disagreements": [{"sample_id": i, "labels": [a[i]["label"], b[i]["label"]],
                           "confidence": [a[i]["confidence"], b[i]["confidence"]]}
                          for i in ids if a[i]["label"] != b[i]["label"]],
        "warning": ("Inter-annotator agreement only. It is not precision, recall or accuracy of the method, "
                    "and L2 labels are not independent ground truth."),
    }
    if not collapsed:
        raise AISInputError("No labeled units")
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    try:
        with partial.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        os.replace(partial, out)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return report


def sample_main():
    parser = argparse.ArgumentParser(description="Blinded, stratified labeling sample of unvalidated AIS intervals")
    parser.add_argument("--run", type=Path, required=True, help="Run directory with manifest.json and outputs")
    parser.add_argument("--sheet", type=Path, required=True, help="New CSV labeling sheet")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--candidates", type=int, default=70)
    parser.add_argument("--negatives", type=int, default=30)
    parser.add_argument("--min-negative-minutes", type=float, default=30)
    args = parser.parse_args()
    try:
        record = draw_sample(args.run, args.sheet, args.seed, args.candidates, args.negatives,
                             args.min_negative_minutes)
    except AISInputError as exc:
        parser.error(str(exc))
    print(json.dumps({k: record[k] for k in ("parameter_set", "seed", "drawn", "allocation", "sheet_sha256")},
                     indent=2))


def agreement_main():
    parser = argparse.ArgumentParser(description="Inter-annotator agreement for two completed label sheets")
    parser.add_argument("--sheets", type=Path, nargs=2, required=True)
    parser.add_argument("--sampling", type=Path, default=None, help="Optional .sampling.json for by-kind results")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = agreement(args.sheets[0], args.sheets[1], args.out, args.sampling)
    except AISInputError as exc:
        parser.error(str(exc))
    print(json.dumps({k: report[k] for k in ("units", "raw_agreement", "kappa_labels", "kappa_collapsed")},
                     indent=2))
