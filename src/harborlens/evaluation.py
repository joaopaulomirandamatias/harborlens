"""Evaluation of stationary candidates against adjudicated labels (SPEC-003, issue #9).

Inputs are one verified run, the sampling manifest written by
``harborlens-label-sample`` and an adjudicated label CSV. A candidate is the
method's "stationary" prediction; a sampled negative (movement) interval is its
"moving" prediction. Labels ``at_berth``/``at_anchor``/``other_stationary`` are
true stationary, ``maneuvering``/``transit`` are true moving. ``mixed``,
``unknown`` and unlabeled units are reported separately and are never counted
as correct.

Metrics against L2 labels measure agreement with expert review of AIS, not
independent ground truth; only L3 labels support real-world accuracy claims.
Nothing here upgrades a candidate to a verified berth, anchorage, wait or port
call.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import os
import statistics
from collections import Counter
from pathlib import Path

from harborlens.ais import parse_time, sha256
from harborlens.io_safe import AISInputError
from harborlens.labeling import COLLAPSED, LABELS, censoring_status, parse_stratum
from harborlens.provenance import verify_manifest
from harborlens.segmentation import SegmentationParams

SCHEMA_VERSION = "evaluation-v0.1"
ADJUDICATED_FIELDS = ["sample_id", "label", "evidence_level", "duration_judgement",
                      "true_start_utc", "true_end_utc", "adjudicator_id"]
Z95 = 1.959963984540054
WARNING = ("Metrics compare unvalidated stationary candidates with adjudicated labels from a stratified "
           "sample. Against L2 labels they measure agreement with expert review of AIS, not independent "
           "ground truth; only the L3 cohort supports real-world accuracy statements. Recall covers sampled "
           "movement intervals only, not stops the method never segmented.")


def wilson(successes, total):
    """95% Wilson score interval; None when there is no denominator."""
    if not total:
        return None
    p = successes / total
    denom = 1 + Z95 ** 2 / total
    centre = (p + Z95 ** 2 / (2 * total)) / denom
    half = Z95 * math.sqrt(p * (1 - p) / total + Z95 ** 2 / (4 * total ** 2)) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def binary_metrics(tp, fp, fn, tn):
    """Confusion counts with precision, recall, F1, specificity and Wilson intervals."""
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (2 * precision * recall / (precision + recall)
          if precision is not None and recall is not None and precision + recall else None)
    specificity = tn / (tn + fp) if tn + fp else None
    rnd = lambda v: None if v is None else round(v, 4)  # noqa: E731
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": tp + fp + fn + tn,
            "precision": rnd(precision), "precision_ci95": wilson(tp, tp + fp),
            "recall": rnd(recall), "recall_ci95": wilson(tp, tp + fn),
            "f1": rnd(f1), "specificity": rnd(specificity), "specificity_ci95": wilson(tn, tn + fp),
            "false_positives": fp}


def _read_labels(path, known_ids):
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [f for f in ADJUDICATED_FIELDS if f not in (reader.fieldnames or [])]
        if missing:
            raise AISInputError(f"{path.name} lacks columns: {missing}")
        rows = list(reader)
    labels, problems = {}, []
    for row in rows:
        sid = row["sample_id"]
        if sid not in known_ids:
            problems.append(f"{sid}: not in the sampling manifest")
        if sid in labels:
            problems.append(f"{sid}: duplicated")
        if row["label"] not in LABELS:
            problems.append(f"{sid}: label={row['label']!r}")
        if row["evidence_level"] not in ("L2", "L3"):
            problems.append(f"{sid}: evidence_level={row['evidence_level']!r}")
        if row["duration_judgement"] not in ("assessable", "not_assessable"):
            problems.append(f"{sid}: duration_judgement={row['duration_judgement']!r}")
        if not (row.get("adjudicator_id") or "").strip():
            problems.append(f"{sid}: adjudicator_id missing")
        bounds = (row["true_start_utc"].strip(), row["true_end_utc"].strip())
        if any(bounds) and not all(bounds):
            problems.append(f"{sid}: give both true_start_utc and true_end_utc or neither")
        if all(bounds):
            try:
                if not parse_time(bounds[0]) < parse_time(bounds[1]):
                    problems.append(f"{sid}: true_start_utc must precede true_end_utc")
            except ValueError:
                problems.append(f"{sid}: invalid true_* timestamp")
        labels[sid] = row
    if problems:
        raise AISInputError(f"{path.name} is not a valid adjudicated label file: " + "; ".join(problems[:20]))
    return labels


def _timing(errors):
    if not errors:
        return {"n": 0, "mae_minutes": None, "median_absolute_error_minutes": None}
    absolute = [abs(e) for e in errors]
    return {"n": len(errors), "mae_minutes": round(sum(absolute) / len(absolute), 2),
            "median_absolute_error_minutes": round(statistics.median(absolute), 2)}


def evaluate(run_dir, sampling, labels_path, out):
    """Write an evaluation report for one run, its sampling manifest and adjudicated labels."""
    run_dir, sampling, out = Path(run_dir), Path(sampling), Path(out)
    if out.suffix.lower() != ".json" or out.exists():
        raise AISInputError("Output must be a new .json file")
    manifest_path = run_dir / "manifest.json"
    check = verify_manifest(manifest_path)
    if not check["ok"]:
        raise AISInputError(f"Run artifacts fail integrity verification: {check['artifacts']}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    params = SegmentationParams.from_manifest(manifest.get("method_parameters"))
    plan = json.loads(sampling.read_text(encoding="utf-8"))
    if plan.get("run_manifest_sha256") != sha256(manifest_path) or plan.get("parameter_set") != params.parameter_set:
        raise AISInputError("Sampling manifest was not drawn from this run")
    key = {k["sample_id"]: k for k in plan["key"]}
    labels = _read_labels(labels_path, set(key))
    geo = json.loads((run_dir / "stationary_candidates.geojson").read_text(encoding="utf-8"))
    candidates = {f["properties"]["event_id"]: f["properties"] for f in geo["features"]}

    excluded = Counter()
    rows = []
    for sid, unit in sorted(key.items()):
        row = labels.get(sid)
        if row is None:
            excluded["unlabeled"] += 1
            continue
        truth = COLLAPSED[row["label"]]
        if truth in ("mixed", "unknown"):
            excluded[truth] += 1
            continue
        predicted = "stationary" if unit["kind"] == "candidate" else "moving"
        outcome = {("stationary", "stationary"): "tp", ("stationary", "moving"): "fp",
                   ("moving", "stationary"): "fn", ("moving", "moving"): "tn"}[(predicted, truth)]
        stratum = unit["stratum"]
        if unit["kind"] == "candidate":
            props = candidates.get(unit["event_id"])
            if props is None:
                raise AISInputError(f"{sid}: candidate {unit['event_id']} is not in the run")
            censoring = censoring_status(props["left_censoring"], props["right_censoring"])
        else:
            props, censoring = None, None
        rows.append({"sample_id": sid, "kind": unit["kind"], "stratum": stratum, "outcome": outcome,
                     "label": row["label"], "evidence_level": row["evidence_level"], "props": props,
                     "censoring": censoring,
                     "vessel_group": parse_stratum(stratum)["vessel_group"], "label_row": row})

    def metrics(selected):
        counts = Counter(r["outcome"] for r in selected)
        return binary_metrics(counts["tp"], counts["fp"], counts["fn"], counts["tn"])

    cohorts = {
        "evidence_level": {lvl: metrics([r for r in rows if r["evidence_level"] == lvl])
                           for lvl in sorted({r["evidence_level"] for r in rows})},
        "vessel_group": {g: metrics([r for r in rows if r["vessel_group"] == g])
                         for g in sorted({r["vessel_group"] for r in rows})},
        "candidate_censoring": {c: metrics([r for r in rows if r["censoring"] == c])
                                for c in sorted({r["censoring"] for r in rows if r["censoring"]})},
    }

    # Design-weighted precision: each candidate stratum stands for its whole frame.
    frame = plan["frame"]["candidates"]
    weighted_tp = weighted_all = 0.0
    for stratum, size in frame.items():
        judged = [r for r in rows if r["kind"] == "candidate" and r["stratum"] == stratum]
        if judged:
            weight = size / len(judged)
            weighted_tp += weight * sum(r["outcome"] == "tp" for r in judged)
            weighted_all += weight * len(judged)
    covered = sum(size for stratum, size in frame.items()
                  if any(r["kind"] == "candidate" and r["stratum"] == stratum for r in rows))

    # Boundary errors: true positives with uncensored candidates, assessable duration and given bounds.
    start_err, end_err, dur_err = [], [], []
    for r in rows:
        lab = r["label_row"]
        if (r["outcome"] == "tp" and r["censoring"] == "uncensored"
                and lab["duration_judgement"] == "assessable" and lab["true_start_utc"].strip()):
            p = r["props"]
            ps, pe = parse_time(p["start_utc"]), parse_time(p["end_utc"])
            ts, te = parse_time(lab["true_start_utc"]), parse_time(lab["true_end_utc"])
            start_err.append((ps - ts).total_seconds() / 60)
            end_err.append((pe - te).total_seconds() / 60)
            dur_err.append(((pe - ps) - (te - ts)).total_seconds() / 60)

    composition = Counter(r["label"] for r in rows if r["kind"] == "candidate")
    composition.update({k: 0 for k in LABELS})
    for sid, unit in key.items():
        lab = labels.get(sid)
        if unit["kind"] == "candidate" and lab and COLLAPSED[lab["label"]] in ("mixed", "unknown"):
            composition[lab["label"]] += 1

    report = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "method_version": params.manifest()["method_version"],
        "parameter_set": params.parameter_set,
        "sampling_sha256": sha256(sampling),
        "labels_sha256": sha256(Path(labels_path)),
        "coverage": {"sampled_units": len(key), "labeled_units": len(labels),
                     "evaluated_units": len(rows), "excluded": {k: excluded[k] for k in ("mixed", "unknown", "unlabeled")},
                     "candidate_frame_units": sum(frame.values()), "candidate_frame_units_in_judged_strata": covered},
        "overall": metrics(rows),
        "design_weighted_precision": (round(weighted_tp / weighted_all, 4) if weighted_all else None),
        "cohorts": cohorts,
        "candidate_label_composition": dict(sorted(composition.items())),
        "boundary_error_minutes": {"definition": "predicted minus labeled; true positives with uncensored "
                                                 "candidates and assessable duration only",
                                   "start": _timing(start_err), "end": _timing(end_err),
                                   "duration": _timing(dur_err)},
        "evidence_basis": ("L3_only" if rows and all(r["evidence_level"] == "L3" for r in rows)
                           else "includes_L2_expert_review"),
        "warning": WARNING,
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
    parser = argparse.ArgumentParser(description="Evaluate unvalidated stationary candidates against adjudicated labels")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--sampling", type=Path, required=True, help="<sheet>.sampling.json from harborlens-label-sample")
    parser.add_argument("--labels", type=Path, required=True, help="Adjudicated label CSV")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    report = evaluate(args.run, args.sampling, args.labels, args.out)
    print(json.dumps({"overall": report["overall"], "coverage": report["coverage"],
                      "evidence_basis": report["evidence_basis"]}, indent=2))


if __name__ == "__main__":
    main()
