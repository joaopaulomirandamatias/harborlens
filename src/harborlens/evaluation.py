"""Comparison of stationary candidates with adjudicated labels (SPEC-003, issue #9).

Inputs are one verified run, the sampling manifest written by
``harborlens-label-sample`` and an adjudicated label CSV. A candidate is the
method's "stationary" prediction; a sampled negative (movement) interval is its
"moving" prediction. Labels ``at_berth``/``at_anchor``/``other_stationary`` are
true stationary, ``maneuvering``/``transit`` are true moving. ``mixed``,
``unknown`` and unlabeled units are reported separately and are never counted
as correct.

This is a reproducibility harness. The report is ``evaluation-v0.2``.
``validation_status`` is ``unvalidated``. ``label_provenance`` is ``synthetic``
only when the caller says so, and ``unspecified`` otherwise. The ``caveat``
states that the labels are not independent ground truth and that the report
makes no accuracy claim. ``warning`` says that agreement with labels at any
evidence level, including L3, is not validated performance while
``validation_status`` is ``unvalidated``. ``read_evaluation_report`` refuses an
``evaluation-v0.1`` file with ``EvaluationReportError``. No ``evaluation-v0.1``
reader is maintained.

The adjudicated label file is an input CSV. This module does not write a CSV.
Text column ``adjudicator_id`` is read with ``read_csv_cell``, which removes a
neutralization apostrophe only when the remainder is a formula trigger.
``sample_id``, ``label``, ``evidence_level``, ``duration_judgement``,
``true_start_utc`` and ``true_end_utc`` are contract columns: a leading
apostrophe is rejected and is not converted. See ``harborlens.labeling``.

Nothing here upgrades a candidate to a berth, anchorage, wait or port call.
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
from harborlens.labeling import COLLAPSED, LABELS, censoring_status, parse_stratum, read_csv_cell
from harborlens.provenance import digests_equal, verify_manifest
from harborlens.segmentation import SegmentationParams

SCHEMA_VERSION = "evaluation-v0.2"
# evaluation-v0.1 reports are not readable. read_evaluation_report names that version and raises.
PREVIOUS_SCHEMA_VERSION = "evaluation-v0.1"
VALIDATION_STATUS = "unvalidated"
LABEL_PROVENANCE_VALUES = ("synthetic", "unspecified")
CAVEAT_SYNTHETIC = (
    "These labels are synthetic. They are not independent ground truth, "
    "and this report makes no accuracy claim."
)
CAVEAT_UNSPECIFIED = (
    "Label provenance is unspecified. These labels are not independent ground truth, "
    "and this report makes no accuracy claim."
)
CAVEATS = {"synthetic": CAVEAT_SYNTHETIC, "unspecified": CAVEAT_UNSPECIFIED}
ADJUDICATED_FIELDS = ["sample_id", "label", "evidence_level", "duration_judgement",
                      "true_start_utc", "true_end_utc", "adjudicator_id"]
Z95 = 1.959963984540054
WARNING = ("Metrics compare unvalidated stationary candidates with adjudicated labels from a stratified "
           "sample. Agreement with labels at any evidence level, including L3, is not validated performance "
           "while validation_status is unvalidated. Recall covers sampled movement intervals only, not stops "
           "the method never segmented.")


class EvaluationReportError(AISInputError):
    """An evaluation report is outside the evaluation-v0.2 contract."""


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
        try:
            sid = read_csv_cell("sample_id", row.get("sample_id"))
        except AISInputError as exc:
            problems.append(str(exc))
            continue
        row["sample_id"] = sid
        for field in ADJUDICATED_FIELDS:
            if field == "sample_id" or field not in row:
                continue
            try:
                row[field] = read_csv_cell(field, row[field])
            except AISInputError as exc:
                problems.append(f"{sid}: {exc}")
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


def evaluate(run_dir, sampling, labels_path, out, label_provenance="unspecified"):
    """Write an evaluation report for one run, its sampling manifest and adjudicated labels.

    ``label_provenance`` defaults to ``unspecified``. ``synthetic`` is only for a
    synthetic fixture. Any other value raises ``AISInputError`` before a file is written.
    """
    if label_provenance not in CAVEATS:
        raise AISInputError("label_provenance must be synthetic or unspecified")
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
    if (not digests_equal(plan.get("run_manifest_sha256"), sha256(manifest_path))
            or not digests_equal(plan.get("parameter_set"), params.parameter_set)):
        raise AISInputError("Sampling manifest was not drawn from this run")
    key = {k["sample_id"]: k for k in plan["key"]}
    schema_version = plan.get("schema_version")
    labels = _read_labels(labels_path, set(key))
    geo = json.loads((run_dir / "stationary_candidates.geojson").read_text(encoding="utf-8"))
    candidates = {f["properties"]["event_id"]: f["properties"] for f in geo["features"]}

    excluded = Counter()
    rows = []
    for sid, unit in sorted(key.items()):
        # Parse before exclusion so a damaged key cannot become a vessel-group cohort.
        parsed = parse_stratum(unit.get("stratum"), schema_version, sid)
        if unit.get("kind") != parsed["kind"]:
            raise AISInputError(f"{sid}: kind {unit.get('kind')!r} does not match stratum kind {parsed['kind']!r}")
        row = labels.get(sid)
        if row is None:
            excluded["unlabeled"] += 1
            continue
        truth = COLLAPSED[row["label"]]
        if truth in ("mixed", "unknown"):
            excluded[truth] += 1
            continue
        predicted = "stationary" if parsed["kind"] == "candidate" else "moving"
        outcome = {("stationary", "stationary"): "tp", ("stationary", "moving"): "fp",
                   ("moving", "stationary"): "fn", ("moving", "moving"): "tn"}[(predicted, truth)]
        stratum = unit["stratum"]
        if parsed["kind"] == "candidate":
            props = candidates.get(unit["event_id"])
            if props is None:
                raise AISInputError(f"{sid}: candidate {unit['event_id']} is not in the run")
            censoring = censoring_status(props["left_censoring"], props["right_censoring"])
        else:
            props, censoring = None, None
        rows.append({"sample_id": sid, "kind": parsed["kind"], "stratum": stratum, "outcome": outcome,
                     "label": row["label"], "evidence_level": row["evidence_level"], "props": props,
                     "censoring": censoring,
                     "vessel_group": parsed["vessel_group"], "label_row": row})

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
        "validation_status": VALIDATION_STATUS,
        "label_provenance": label_provenance,
        "caveat": CAVEATS[label_provenance],
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


def read_evaluation_report(path):
    """Read one ``evaluation-v0.2`` report.

    An ``evaluation-v0.1`` file, or any other ``schema_version``, raises
    ``EvaluationReportError``. The message names the version that was found.
    This function does not upgrade the file and does not write a replacement.
    """
    path = Path(path)
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvaluationReportError(f"{path.name} is not a readable evaluation report") from exc
    if not isinstance(body, dict):
        raise EvaluationReportError(f"{path.name} is not an evaluation report object")
    version = body.get("schema_version")
    if version != SCHEMA_VERSION:
        found = version if isinstance(version, str) else type(version).__name__
        note = " It is not upgraded." if version == PREVIOUS_SCHEMA_VERSION else ""
        raise EvaluationReportError(
            f"{path.name} schema_version {found!r} is not readable.{note} "
            f"This reader accepts only {SCHEMA_VERSION}."
        )
    if body.get("validation_status") != VALIDATION_STATUS:
        raise EvaluationReportError(
            f"{path.name} validation_status must be {VALIDATION_STATUS!r}"
        )
    provenance = body.get("label_provenance")
    if provenance not in CAVEATS:
        raise EvaluationReportError(
            f"{path.name} label_provenance {provenance!r} is not one of "
            f"{', '.join(LABEL_PROVENANCE_VALUES)}"
        )
    if body.get("caveat") != CAVEATS[provenance]:
        raise EvaluationReportError(
            f"{path.name} caveat does not match label_provenance {provenance!r}"
        )
    return body


def main():
    parser = argparse.ArgumentParser(
        description="Compare unvalidated stationary candidates with adjudicated labels. "
                    "The report makes no accuracy claim.")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--sampling", type=Path, required=True, help="<sheet>.sampling.json from harborlens-label-sample")
    parser.add_argument("--labels", type=Path, required=True, help="Adjudicated label CSV")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--label-provenance", default="unspecified",
                        help="synthetic or unspecified. Default: unspecified. Any other value is rejected.")
    args = parser.parse_args()
    if args.label_provenance not in CAVEATS:
        parser.error("label_provenance must be synthetic or unspecified")
    try:
        report = evaluate(args.run, args.sampling, args.labels, args.out,
                          label_provenance=args.label_provenance)
    except AISInputError as exc:
        parser.error(str(exc))
    print(json.dumps({"validation_status": report["validation_status"],
                      "label_provenance": report["label_provenance"],
                      "caveat": report["caveat"],
                      "overall": report["overall"], "coverage": report["coverage"],
                      "evidence_basis": report["evidence_basis"]}, indent=2))


if __name__ == "__main__":
    main()
