"""Labeling-pilot tooling (SPEC-003, issue #8): stratified sampling and agreement.

``harborlens-label-sample`` draws a seeded, stratified, blinded sample of
stationary candidates and negative (movement) intervals from one verified run.
``harborlens-label-agreement`` compares two annotators' sheets.

Agreement between annotators is NOT accuracy of the method, and an L2 label is
expert review of AIS, not independent ground truth. Nothing here upgrades a
candidate to a berth, anchorage, wait or port call. See
docs/research/labeling-protocol.md.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict
from datetime import timedelta
from pathlib import Path

from harborlens.ais import load_cleaned, parse_time, sha256
from harborlens.censoring import CENSORED, UNKNOWN, WindowCensoring
from harborlens.io_safe import AISInputError
from harborlens.provenance import verify_manifest
from harborlens.segmentation import SegmentationParams

SAMPLE_SCHEMA = "label-sample-v0.1"
AGREEMENT_SCHEMA = "label-agreement-v0.1"
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


def _iso(value):
    return value.isoformat().replace("+00:00", "Z")


def vessel_group(code):
    """Coarse AIS ship-type group used only for stratification."""
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
        if props.get("parameter_set") != params.parameter_set:
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


def _allocate(strata, total, rng):
    """At least one unit per non-empty stratum, remainder proportional (largest remainder)."""
    keys = sorted(k for k, members in strata.items() if members)
    total = min(total, sum(len(strata[k]) for k in keys))
    if total <= 0:
        return {}
    if total < len(keys):
        return {k: 1 for k in sorted(rng.sample(keys, total))}
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


def draw_sample(run_dir, sheet, seed, candidates=70, negatives=30, min_negative_minutes=30):
    """Write a blinded labeling sheet and a sampling manifest holding the key."""
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
        key = "|".join((duration_band(c["duration_min"]),
                        censoring_status(c["left_censoring"], c["right_censoring"]), vessel_group(mode)))
        strata[key].append({"kind": "candidate", "event_id": c["event_id"], "stratum": key,
                            "mmsi": c["mmsi"], "start": c["start"], "end": c["end"],
                            "points": c["point_count"], "lon": c["lon"], "lat": c["lat"], "type": mode,
                            "left": c["left_censoring"], "right": c["right_censoring"]})
    window = _window_from_manifest(manifest, params.max_gap_minutes)
    negative_strata = defaultdict(list)
    for run in _negative_intervals(rows, params, stops, min_negative_minutes):
        mode = _mode([r[5] for r in run])
        left, right = window.classify(run[0][1], run[-1][1])
        key = "negative|" + vessel_group(mode)
        negative_strata[key].append({
            "kind": "negative", "event_id": None, "stratum": key, "mmsi": run[0][0],
            "start": run[0][1], "end": run[-1][1], "points": len(run),
            "lon": round(sum(r[3] for r in run) / len(run), 6), "lat": round(sum(r[2] for r in run) / len(run), 6),
            "type": mode, "left": left, "right": right})

    allocation = {}
    for group, wanted in ((strata, candidates), (negative_strata, negatives)):
        plan = _allocate(group, wanted, rng)
        allocation.update(plan)
        for key, count in plan.items():
            units.extend(rng.sample(group[key], count))
    if not units:
        raise AISInputError("The run has no candidates or negative intervals to sample")
    rng.shuffle(units)

    sheet.parent.mkdir(parents=True, exist_ok=True)
    partial = sheet.with_name(sheet.name + ".partial")
    key_rows = []
    try:
        with partial.open("x", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS, lineterminator="\n")
            writer.writeheader()
            for index, unit in enumerate(units, 1):
                sample_id = f"S{index:04d}"
                writer.writerow({"sample_id": sample_id, "mmsi": unit["mmsi"], "start_utc": _iso(unit["start"]),
                                 "end_utc": _iso(unit["end"]), "observed_points": unit["points"],
                                 "centroid_lon": unit["lon"], "centroid_lat": unit["lat"],
                                 "vessel_type_mode": unit["type"], "left_censoring": unit["left"],
                                 "right_censoring": unit["right"]})
                key_rows.append({"sample_id": sample_id, "kind": unit["kind"], "event_id": unit["event_id"],
                                 "stratum": unit["stratum"]})
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
    """Read one annotator's completed sheet and validate every annotation field."""
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
        sid = row["sample_id"]
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
    record = draw_sample(args.run, args.sheet, args.seed, args.candidates, args.negatives,
                         args.min_negative_minutes)
    print(json.dumps({k: record[k] for k in ("parameter_set", "seed", "drawn", "allocation", "sheet_sha256")},
                     indent=2))


def agreement_main():
    parser = argparse.ArgumentParser(description="Inter-annotator agreement for two completed label sheets")
    parser.add_argument("--sheets", type=Path, nargs=2, required=True)
    parser.add_argument("--sampling", type=Path, default=None, help="Optional .sampling.json for by-kind results")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = agreement(args.sheets[0], args.sheets[1], args.out, args.sampling)
    print(json.dumps({k: report[k] for k in ("units", "raw_agreement", "kappa_labels", "kappa_collapsed")},
                     indent=2))
