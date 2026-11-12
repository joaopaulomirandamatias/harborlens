"""End-to-end synthetic evaluation harness (SPEC-003, issue #9, FR-013, FR-014, NFR-020, BR-012).

Pipeline, all in a temporary directory: a synthetic AIS file with fictional vessel
ids, ``harborlens``, ``harborlens-label-sample`` at a fixed seed, an adjudicated
sheet that contains no vessel id, then ``harborlens-evaluate --label-provenance synthetic``.

The counts, rates, Wilson intervals, timing errors and exclusion totals below are
computed in this file. This module does not import ``harborlens.evaluation`` and
does not call ``binary_metrics``, ``wilson``, ``evaluate`` or ``_timing``.
"""
from __future__ import annotations

import csv
import json
import math
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas" / "v1"
HEADER = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"]
DAY = datetime(2024, 1, 2)
SEED = 20241112
SYNTHETIC_CAVEAT = (
    "These labels are synthetic. They are not independent ground truth, "
    "and this report makes no accuracy claim."
)
UNSPECIFIED_CAVEAT = (
    "Label provenance is unspecified. These labels are not independent ground truth, "
    "and this report makes no accuracy claim."
)
ADJUDICATED_FIELDS = ["sample_id", "label", "evidence_level", "duration_judgement",
                      "true_start_utc", "true_end_utc", "adjudicator_id"]
STATIONARY = {"at_berth", "at_anchor", "other_stationary"}
MOVING = {"maneuvering", "transit"}
# Offsets applied to every true-positive bound: predicted start is 6 minutes
# later than the labeled start, predicted end is 3 minutes earlier.
START_BIAS_MINUTES = 6
END_BIAS_MINUTES = -3


def cli(module, function, argv):
    """Run one HarborLens console entry point in a child process."""
    code = (
        "import sys\n"
        f"from {module} import {function} as entry\n"
        "sys.argv = sys.argv[1:]\n"
        "entry()\n"
    )
    return subprocess.run(
        [sys.executable, "-c", code, *argv],
        capture_output=True, text=True, check=False,
    )


def synthetic_rows():
    """Eight fictional vessel ids. Each moves, stops, moves, and stops again.

    MMSIs are the 199020000-199020007 block already used as synthetic ids in
    this repository. Nothing here is read from a real AIS source.
    """
    rows = []
    vessel_ids = []
    for n in range(8):
        mmsi = f"19902000{n}"
        vessel_ids.append(mmsi)
        vtype = ("70", "80", "31", "60")[n % 4]
        moment = DAY + timedelta(minutes=5 + n)
        lat, lon = 29.4 + n * 0.01, -95.0
        for stop in (60 + 20 * n, 40):
            for i in range(0, 45, 3):
                lon += 0.002
                rows.append([mmsi, (moment + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
                             lat, lon, 8.0, vtype, "0"])
            moment += timedelta(minutes=45)
            for i in range(0, stop + 1, 5):
                rows.append([mmsi, (moment + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
                             lat, lon, 0.1, vtype, "1"])
            moment += timedelta(minutes=stop + 5)
    return vessel_ids, rows


def hand_wilson(successes, total):
    """Wilson score 95% interval. None when the denominator is 0.

    z is the 0.975 standard-normal quantile. The centre and half-width are the
    usual score-interval expressions, then rounded to 4 decimals and clipped
    to [0, 1].
    """
    if not total:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denom = 1 + z ** 2 / total
    centre = (proportion + z ** 2 / (2 * total)) / denom
    half = z * math.sqrt(proportion * (1 - proportion) / total + z ** 2 / (4 * total ** 2)) / denom
    return [round(max(0.0, centre - half), 4), round(min(1.0, centre + half), 4)]


def hand_rate(numerator, denominator):
    if not denominator:
        return None
    return round(numerator / denominator, 4)


def hand_f1(tp, fp, fn):
    """F1 from the unrounded ratios, then rounded to 4 decimals."""
    if not tp + fp or not tp + fn:
        return None
    precision = tp / (tp + fp)
    recall = tp / (tp + fn)
    if precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 4)


def shift(stamp, minutes):
    moment = datetime.fromisoformat(stamp.replace("Z", "+00:00")) + timedelta(minutes=minutes)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class SyntheticEvaluationHarnessTests(unittest.TestCase):
    def test_seeded_synthetic_pipeline_matches_the_hand_oracle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            vessel_ids, rows = synthetic_rows()
            self.assertEqual(len(vessel_ids), len(set(vessel_ids)))
            source = root / "synthetic.csv"
            with source.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADER)
                writer.writerows(rows)
            # The committed NOAA-style fixture is a different file. This run is generated here.
            self.assertNotEqual(source.resolve(), (ROOT / "tests" / "fixtures" / "synthetic_ais.csv").resolve())

            run_dir = root / "run"
            produced = cli("harborlens.cli", "main", [
                "harborlens", "--input", str(source), "--out", str(run_dir),
                "--window-start", "2024-01-02T00:00:00Z", "--window-end", "2024-01-02T12:00:00Z",
            ])
            self.assertEqual(produced.returncode, 0, produced.stderr)
            self.assertNotIn("Traceback", produced.stderr)

            sheet = root / "sheet.csv"
            sampled = cli("harborlens.labeling", "sample_main", [
                "harborlens-label-sample", "--run", str(run_dir), "--sheet", str(sheet),
                "--seed", str(SEED), "--candidates", "8", "--negatives", "4",
            ])
            self.assertEqual(sampled.returncode, 0, sampled.stderr)
            self.assertNotIn("Traceback", sampled.stderr)
            sampling = json.loads(sheet.with_name(sheet.name + ".sampling.json").read_text(encoding="utf-8"))
            self.assertEqual(sampling["seed"], SEED)
            with sheet.open(newline="", encoding="utf-8") as handle:
                sheet_rows = list(csv.DictReader(handle))
            sheet_ids = {row["mmsi"] for row in sheet_rows}
            self.assertTrue(sheet_ids)
            self.assertTrue(sheet_ids <= set(vessel_ids))

            geo = json.loads((run_dir / "stationary_candidates.geojson").read_text(encoding="utf-8"))
            candidates = {feature["properties"]["event_id"]: feature["properties"] for feature in geo["features"]}
            by_kind = {"candidate": [], "negative": []}
            for unit in sampling["key"]:
                by_kind[unit["kind"]].append(unit)
            for group in by_kind.values():
                group.sort(key=lambda unit: unit["sample_id"])
            self.assertGreaterEqual(len(by_kind["candidate"]), 4)
            self.assertGreaterEqual(len(by_kind["negative"]), 3)

            labels = {}
            # Candidates: one false positive, one unknown, one mixed, the rest true positives.
            labels[by_kind["candidate"][0]["sample_id"]] = ("transit", False)
            labels[by_kind["candidate"][1]["sample_id"]] = ("unknown", False)
            labels[by_kind["candidate"][2]["sample_id"]] = ("mixed", False)
            for unit in by_kind["candidate"][3:]:
                labels[unit["sample_id"]] = ("at_berth", True)
            # Negatives: one false negative, one unlabeled, the rest true negatives.
            labels[by_kind["negative"][0]["sample_id"]] = ("at_anchor", False)
            for unit in by_kind["negative"][2:]:
                labels[unit["sample_id"]] = ("maneuvering", False)

            adjudicated = root / "adjudicated.csv"
            with adjudicated.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=ADJUDICATED_FIELDS)
                writer.writeheader()
                for unit in sampling["key"]:
                    if unit["sample_id"] not in labels:
                        continue
                    label, timed = labels[unit["sample_id"]]
                    start = end = ""
                    if timed:
                        props = candidates[unit["event_id"]]
                        start = shift(props["start_utc"], -START_BIAS_MINUTES)
                        end = shift(props["end_utc"], -END_BIAS_MINUTES)
                    writer.writerow({
                        "sample_id": unit["sample_id"], "label": label, "evidence_level": "L2",
                        "duration_judgement": "assessable", "true_start_utc": start, "true_end_utc": end,
                        "adjudicator_id": "J1",
                    })
            adjudicated_text = adjudicated.read_text(encoding="utf-8")
            self.assertNotIn("mmsi", adjudicated_text.lower())
            for vessel_id in vessel_ids:
                self.assertNotIn(vessel_id, adjudicated_text)

            out = root / "evaluation.json"
            evaluated = cli("harborlens.evaluation", "main", [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sheet.with_name(sheet.name + ".sampling.json")),
                "--labels", str(adjudicated), "--out", str(out),
                "--label-provenance", "synthetic",
            ])
            self.assertEqual(evaluated.returncode, 0, evaluated.stderr)
            self.assertNotIn("Traceback", evaluated.stderr)
            report = json.loads(out.read_text(encoding="utf-8"))
            printed = json.loads(evaluated.stdout)
            self.assertEqual(printed["label_provenance"], "synthetic")
            self.assertEqual(printed["caveat"], SYNTHETIC_CAVEAT)

            tp = fp = fn = tn = 0
            excluded = {"mixed": 0, "unknown": 0, "unlabeled": 0}
            uncensored_true_positives = 0
            for unit in sampling["key"]:
                assigned = labels.get(unit["sample_id"])
                if assigned is None:
                    excluded["unlabeled"] += 1
                    continue
                label = assigned[0]
                if label in ("mixed", "unknown"):
                    excluded[label] += 1
                    continue
                predicted_stationary = unit["kind"] == "candidate"
                if predicted_stationary and label in STATIONARY:
                    tp += 1
                    props = candidates[unit["event_id"]]
                    if props["left_censoring"] == "not_censored" and props["right_censoring"] == "not_censored":
                        uncensored_true_positives += 1
                elif predicted_stationary and label in MOVING:
                    fp += 1
                elif label in STATIONARY:
                    fn += 1
                elif label in MOVING:
                    tn += 1
                else:
                    self.fail(label)

            self.assertGreaterEqual(tp, 1)
            self.assertEqual(fp, 1)
            self.assertEqual(fn, 1)
            self.assertGreaterEqual(tn, 1)
            self.assertEqual(excluded, {"mixed": 1, "unknown": 1, "unlabeled": 1})
            self.assertGreaterEqual(uncensored_true_positives, 1)

            precision = hand_rate(tp, tp + fp)
            recall = hand_rate(tp, tp + fn)
            specificity = hand_rate(tn, tn + fp)
            expected = {
                "tp": tp, "fp": fp, "fn": fn, "tn": tn, "n": tp + fp + fn + tn,
                "precision": precision,
                "precision_ci95": hand_wilson(tp, tp + fp),
                "recall": recall,
                "recall_ci95": hand_wilson(tp, tp + fn),
                "f1": hand_f1(tp, fp, fn),
                "specificity": specificity,
                "specificity_ci95": hand_wilson(tn, tn + fp),
                "false_positives": fp,
            }
            self.assertEqual(report["overall"], expected)
            self.assertEqual(report["coverage"]["sampled_units"], len(sampling["key"]))
            self.assertEqual(report["coverage"]["labeled_units"], len(labels))
            self.assertEqual(report["coverage"]["evaluated_units"], tp + fp + fn + tn)
            self.assertEqual(report["coverage"]["excluded"], excluded)
            self.assertEqual(
                report["coverage"]["sampled_units"],
                report["coverage"]["evaluated_units"] + sum(excluded.values()),
            )
            timing = report["boundary_error_minutes"]
            self.assertEqual(timing["start"]["n"], uncensored_true_positives)
            self.assertEqual(timing["end"]["n"], uncensored_true_positives)
            self.assertEqual(timing["duration"]["n"], uncensored_true_positives)
            self.assertEqual(timing["start"]["mae_minutes"], float(START_BIAS_MINUTES))
            self.assertEqual(timing["start"]["median_absolute_error_minutes"], float(START_BIAS_MINUTES))
            self.assertEqual(timing["end"]["mae_minutes"], float(abs(END_BIAS_MINUTES)))
            self.assertEqual(timing["end"]["median_absolute_error_minutes"], float(abs(END_BIAS_MINUTES)))
            # Duration error is the end error minus the start error: -3 - 6 = -9 minutes.
            self.assertEqual(timing["duration"]["mae_minutes"], 9.0)
            self.assertEqual(timing["duration"]["median_absolute_error_minutes"], 9.0)

            self.assertEqual(report["schema_version"], "evaluation-v0.2")
            self.assertEqual(report["validation_status"], "unvalidated")
            self.assertEqual(report["label_provenance"], "synthetic")
            self.assertEqual(report["caveat"], SYNTHETIC_CAVEAT)
            self.assertNotEqual(report["caveat"], UNSPECIFIED_CAVEAT)
            self.assertNotIn("Label provenance is unspecified", report["caveat"])
            self.assertEqual(
                report["warning"],
                "Metrics compare unvalidated stationary candidates with adjudicated labels from a stratified "
                "sample. Agreement with labels at any evidence level, including L3, is not validated performance "
                "while validation_status is unvalidated. Recall covers sampled movement intervals only, not stops "
                "the method never segmented.",
            )
            self.assertNotIn("accuracy", report["warning"])
            schema = json.loads((SCHEMAS / "evaluation-report.schema.json").read_text(encoding="utf-8"))
            Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)

            rejected = root / "rejected.json"
            denied = cli("harborlens.evaluation", "main", [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sheet.with_name(sheet.name + ".sampling.json")),
                "--labels", str(adjudicated), "--out", str(rejected),
                "--label-provenance", "ground_truth",
            ])
            self.assertEqual(denied.returncode, 2)
            self.assertNotIn("Traceback", denied.stderr)
            self.assertIn("label_provenance", denied.stderr)
            self.assertFalse(rejected.exists())
            self.assertFalse(Path(str(rejected) + ".partial").exists())


if __name__ == "__main__":
    unittest.main()
