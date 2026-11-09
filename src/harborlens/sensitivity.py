"""Descriptive threshold-sensitivity runs over one cleaned AIS file (SPEC-002, #37).

Re-runs the shared segmentation engine for a bounded grid of thresholds and
reports how candidate counts, discard reasons, splits and durations change.
This describes the method's sensitivity only. It does NOT select or tune
thresholds: that requires independent labels (SPEC-003, issues #8 and #9).
No network access; no candidate is upgraded beyond ``unvalidated``.
"""
from __future__ import annotations

import argparse
import itertools
import json
import os
from pathlib import Path

from harborlens.ais import load_cleaned, segment_rows, sha256
from harborlens.censoring import CENSORED, WindowCensoring, declared_window
from harborlens.io_safe import AISInputError
from harborlens.segmentation import METHOD_VERSION, SegmentationParams

SCHEMA_VERSION = "sensitivity-v0.1"
MAX_SETTINGS = 64
MAX_ROWS = 1_500_000
WARNING = ("Descriptive sensitivity of unvalidated stationary candidates. Do not select thresholds "
           "from these counts without independent labels; candidates are not berths, anchorages, "
           "waits or port calls.")
GRID_FIELDS = ("max_sog_knots", "min_duration_minutes", "max_gap_minutes",
               "max_radius_m", "min_points", "max_jump_knots")


def _quantile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * q
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 2)


def _durations(events):
    values = [e["duration_min"] for e in events]
    return {"count": len(values), "min": min(values, default=None), "median": _quantile(values, 0.5),
            "p90": _quantile(values, 0.9), "max": max(values, default=None)}


def run_sensitivity(cleaned, out, grid, window_start=None, window_end=None):
    """Evaluate every combination in ``grid`` (field -> list of values) on one cleaned CSV."""
    cleaned, out = Path(cleaned), Path(out)
    if out.suffix.lower() != ".json" or out.exists() or out.resolve() == cleaned.resolve():
        raise AISInputError("Output must be a new .json file different from the input")
    unknown = set(grid) - set(GRID_FIELDS)
    if unknown:
        raise AISInputError(f"Unknown grid fields: {sorted(unknown)}")
    axes = {name: sorted(set(grid.get(name) or [getattr(SegmentationParams(), name)]))
            for name in GRID_FIELDS}
    combos = list(itertools.product(*(axes[name] for name in GRID_FIELDS)))
    if not 1 <= len(combos) <= MAX_SETTINGS:
        raise AISInputError(f"Grid must contain 1..{MAX_SETTINGS} settings, got {len(combos)}")
    settings = [SegmentationParams(**dict(zip(GRID_FIELDS, values))) for values in combos]
    window = declared_window(window_start, window_end)
    rows, unparsable = load_cleaned(cleaned)
    if len(rows) > MAX_ROWS:
        raise AISInputError("Cleaned AIS exceeds the sensitivity row cap; refusing a partial result")
    results = []
    for params in settings:
        censoring = WindowCensoring([window] if window else None, params.max_gap_minutes)
        if window and rows:
            censoring.check_observed(min(r[1] for r in rows), max(r[1] for r in rows))
        events, stats = segment_rows(rows, params, censoring, unparsable)
        uncensored = [e for e in events
                      if CENSORED not in (e["left_censoring"], e["right_censoring"])
                      and "unknown" not in (e["left_censoring"], e["right_censoring"])]
        results.append({
            "parameters": params.manifest(),
            "stationary_candidates": stats["stationary_candidates"],
            "discarded_by_reason": stats["discarded_by_reason"],
            "splits": {k: stats[k] for k in ("timestamp_conflicts", "gap_splits", "identity_conflicts",
                                              "implausible_jumps", "spatial_splits")},
            "moving_points": stats["moving_points"],
            "candidates_per_mmsi": stats["candidates_per_mmsi"],
            "censoring": stats["censoring"],
            "duration_minutes_all": _durations(events),
            "duration_minutes_uncensored": _durations(uncensored) if window else None,
        })
    report = {
        "schema_version": SCHEMA_VERSION, "method_version": METHOD_VERSION,
        "input_filename": cleaned.name, "input_sha256": sha256(cleaned),
        "rows": len(rows), "unparsable_rows": unparsable,
        "analysis_window": ({"start_utc": window_start, "end_utc": window_end} if window else None),
        "grid": axes, "settings": results, "warning": WARNING,
    }
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


def main():
    parser = argparse.ArgumentParser(
        description="Descriptive threshold sensitivity for unvalidated stationary candidates; NOT FOR NAVIGATION")
    parser.add_argument("--cleaned", type=Path, required=True, help="Canonical cleaned AIS CSV (houston_clean.csv)")
    parser.add_argument("--out", type=Path, required=True, help="New JSON report path")
    parser.add_argument("--window-start", default=None, help="Optional analysis window start (ISO 8601 with Z)")
    parser.add_argument("--window-end", default=None)
    for name in GRID_FIELDS:
        kind = int if name == "min_points" else float
        parser.add_argument("--" + name.replace("_", "-"), type=kind, nargs="+", default=None,
                            help="One or more values; default is the BR-003 value")
    args = parser.parse_args()
    grid = {name: getattr(args, name) for name in GRID_FIELDS if getattr(args, name)}
    report = run_sensitivity(args.cleaned, args.out, grid, args.window_start, args.window_end)
    summary = [{"parameter_set": s["parameters"]["parameter_set"],
                **{k: s["parameters"][k] for k in GRID_FIELDS},
                "stationary_candidates": s["stationary_candidates"]} for s in report["settings"]]
    print(json.dumps({"out": str(args.out), "settings": summary}, indent=2))


if __name__ == "__main__":
    main()
