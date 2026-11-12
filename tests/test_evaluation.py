"""Evaluator tests (SPEC-003, issue #9). Synthetic AIS and synthetic labels only."""
import contextlib
import csv
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

from jsonschema.exceptions import ValidationError

from harborlens.ais import run
from harborlens.evaluation import (
    ADJUDICATED_FIELDS, CAVEAT_SYNTHETIC, CAVEAT_UNSPECIFIED, SCHEMA_VERSION, VALIDATION_STATUS,
    WARNING, binary_metrics, evaluate, main, read_evaluation_report, wilson,
)
from harborlens.evaluation import EvaluationReportError
from harborlens.io_safe import AISInputError
from harborlens.labeling import draw_sample

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"
HEADER = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"]
DAY = datetime(2024, 1, 2)


def fixture_rows():
    """Eight vessels, each: 42 min moving, a stop, 42 min moving, a second stop."""
    out = []
    for n in range(8):
        mmsi, vtype = f"36720000{n}", ("70", "80", "31", "60")[n % 4]
        t, lat, lon = DAY + timedelta(minutes=5 + n), 29.4 + n * 0.01, -95.0
        for stop in (60 + 20 * n, 40):
            for i in range(0, 45, 3):
                lon += 0.002
                out.append([mmsi, (t + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"), lat, lon, 8.0, vtype, "0"])
            t += timedelta(minutes=45)
            for i in range(0, stop + 1, 5):
                out.append([mmsi, (t + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"), lat, lon, 0.1, vtype, "1"])
            t += timedelta(minutes=stop + 5)
    return out


class EvaluatorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        src = self.root / "in.csv"
        with src.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            writer.writerows(fixture_rows())
        self.run_dir = self.root / "run"
        run(src, self.run_dir, window_start="2024-01-02T00:00:00Z", window_end="2024-01-02T12:00:00Z")
        self.plan = draw_sample(self.run_dir, self.root / "sheet.csv", 11, candidates=10, negatives=6)
        self.sampling = self.root / "sheet.csv.sampling.json"
        geo = json.loads((self.run_dir / "stationary_candidates.geojson").read_text())
        self.candidates = {f["properties"]["event_id"]: f["properties"] for f in geo["features"]}

    def tearDown(self):
        self.tmp.cleanup()

    def write_labels(self, assign, name="adjudicated.csv"):
        path = self.root / name
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ADJUDICATED_FIELDS)
            writer.writeheader()
            for unit in self.plan["key"]:
                row = assign(unit)
                if row is not None:
                    writer.writerow({"sample_id": unit["sample_id"], "evidence_level": "L2",
                                     "duration_judgement": "assessable", "true_start_utc": "",
                                     "true_end_utc": "", "adjudicator_id": "J1", **row})
        return path

    def test_confusion_counts_match_the_constructed_truth(self):
        candidates = [u for u in self.plan["key"] if u["kind"] == "candidate"]
        negatives = [u for u in self.plan["key"] if u["kind"] == "negative"]
        fp_ids = {u["sample_id"] for u in candidates[:2]}           # 2 candidates actually moving
        fn_ids = {u["sample_id"] for u in negatives[:1]}            # 1 negative actually anchored
        unknown_ids = {candidates[2]["sample_id"], negatives[1]["sample_id"]}

        def assign(unit):
            sid = unit["sample_id"]
            if sid in unknown_ids:
                return {"label": "unknown"}
            if sid in fp_ids:
                return {"label": "transit"}
            if sid in fn_ids:
                return {"label": "at_anchor"}
            return {"label": "at_berth" if unit["kind"] == "candidate" else "maneuvering"}

        report = evaluate(self.run_dir, self.sampling, self.write_labels(assign), self.root / "eval.json")
        tp = len(candidates) - 2 - 1
        tn = len(negatives) - 1 - 1
        overall = report["overall"]
        self.assertEqual((overall["tp"], overall["fp"], overall["fn"], overall["tn"]), (tp, 2, 1, tn))
        self.assertEqual(overall["precision"], round(tp / (tp + 2), 4))
        self.assertEqual(overall["recall"], round(tp / (tp + 1), 4))
        # Unknowns are excluded and reported, never counted as correct negatives.
        self.assertEqual(report["coverage"]["excluded"], {"mixed": 0, "unknown": 2, "unlabeled": 0})
        self.assertEqual(report["coverage"]["evaluated_units"], len(self.plan["key"]) - 2)
        self.assertEqual(report["candidate_label_composition"]["unknown"], 1)
        self.assertEqual(report["evidence_basis"], "includes_L2_expert_review")
        # v0.2 stratum keys end in the transceiver class. Vessel group stays the group, not the class.
        groups = set(report["cohorts"]["vessel_group"])
        self.assertTrue(groups)
        self.assertTrue(groups <= {"cargo", "tanker", "passenger", "tug_or_service", "other_or_unknown"})
        self.assertTrue(groups.isdisjoint({"A", "B", "absent_or_unknown"}))
        schema = json.loads((SCHEMAS / "evaluation-report.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)

    def test_unlabeled_units_are_counted_not_dropped(self):
        first = self.plan["key"][0]["sample_id"]
        path = self.write_labels(lambda u: None if u["sample_id"] == first else {"label": "unknown"})
        report = evaluate(self.run_dir, self.sampling, path, self.root / "eval.json")
        self.assertEqual(report["coverage"]["excluded"]["unlabeled"], 1)
        self.assertEqual(report["overall"]["n"], 0)
        self.assertIsNone(report["overall"]["precision"])

    def test_boundary_errors_use_only_uncensored_true_positives(self):
        def assign(unit):
            if unit["kind"] != "candidate":
                return {"label": "transit"}
            props = self.candidates[unit["event_id"]]
            start = datetime.fromisoformat(props["start_utc"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(props["end_utc"].replace("Z", "+00:00"))
            return {"label": "at_anchor",
                    "true_start_utc": (start - timedelta(minutes=4)).isoformat().replace("+00:00", "Z"),
                    "true_end_utc": (end + timedelta(minutes=2)).isoformat().replace("+00:00", "Z")}

        report = evaluate(self.run_dir, self.sampling, self.write_labels(assign), self.root / "eval.json")
        uncensored = sum(1 for u in self.plan["key"] if u["kind"] == "candidate"
                         and "censored" not in (self.candidates[u["event_id"]]["left_censoring"],
                                                self.candidates[u["event_id"]]["right_censoring"]))
        timing = report["boundary_error_minutes"]
        self.assertEqual(timing["start"]["n"], uncensored)
        if uncensored:
            self.assertEqual(timing["start"]["mae_minutes"], 4.0)
            self.assertEqual(timing["end"]["mae_minutes"], 2.0)
            self.assertEqual(timing["duration"]["median_absolute_error_minutes"], 6.0)

    def test_design_weighted_precision_and_l3_basis(self):
        def assign(unit):
            return {"label": "at_berth" if unit["kind"] == "candidate" else "transit",
                    "evidence_level": "L3"}
        path = self.root / "l3.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ADJUDICATED_FIELDS)
            writer.writeheader()
            for unit in self.plan["key"]:
                writer.writerow({"sample_id": unit["sample_id"], "duration_judgement": "assessable",
                                 "true_start_utc": "", "true_end_utc": "", "adjudicator_id": "J1",
                                 **assign(unit)})
        report = evaluate(self.run_dir, self.sampling, path, self.root / "eval.json")
        self.assertEqual(report["design_weighted_precision"], 1.0)
        self.assertEqual(report["evidence_basis"], "L3_only")
        self.assertEqual(set(report["cohorts"]["evidence_level"]), {"L3"})

    def test_lineage_and_input_validation(self):
        good = self.write_labels(lambda u: {"label": "unknown"})
        other = draw_sample(self.run_dir, self.root / "other.csv", 99, candidates=2, negatives=0)
        other_path = self.root / "other.csv.sampling.json"
        tampered = json.loads(other_path.read_text())
        tampered["parameter_set"] = "0" * 12
        other_path.write_text(json.dumps(tampered))
        with self.assertRaisesRegex(AISInputError, "not drawn from this run"):
            evaluate(self.run_dir, other_path, good, self.root / "a.json")
        bad_label = self.write_labels(lambda u: {"label": "anchored"}, "bad.csv")
        with self.assertRaises(AISInputError):
            evaluate(self.run_dir, self.sampling, bad_label, self.root / "b.json")
        half = self.write_labels(lambda u: {"label": "at_berth", "true_start_utc": "2024-01-02T01:00:00Z"}, "half.csv")
        with self.assertRaisesRegex(AISInputError, "both true_start_utc"):
            evaluate(self.run_dir, self.sampling, half, self.root / "c.json")
        (self.root / "exists.json").write_text("{}")
        with self.assertRaises(AISInputError):
            evaluate(self.run_dir, self.sampling, good, self.root / "exists.json")
        self.assertIsNotNone(other)

    def test_damaged_v02_key_is_not_reported_as_a_vessel_group(self):
        plan = json.loads(self.sampling.read_text())
        unit = next(item for item in plan["key"] if item["kind"] == "candidate")
        unit["stratum"] = "lt_60|uncensored|A"
        damaged = self.root / "damaged.sampling.json"
        damaged.write_text(json.dumps(plan))
        labels = self.write_labels(lambda item: {"label": "at_berth"} if item["kind"] == "candidate" else {"label": "transit"},
                                   name="damaged-labels.csv")
        with self.assertRaises(AISInputError) as caught:
            evaluate(self.run_dir, damaged, labels, self.root / "damaged-eval.json")
        self.assertIn(unit["sample_id"], str(caught.exception))
        self.assertFalse((self.root / "damaged-eval.json").exists())

    def test_kind_must_match_the_stratum(self):
        labels = self.write_labels(
            lambda item: {"label": "at_berth"} if item["kind"] == "candidate" else {"label": "transit"},
            name="kind-labels.csv")
        candidate = next(item for item in self.plan["key"] if item["kind"] == "candidate")
        negative = next(item for item in self.plan["key"] if item["kind"] == "negative")

        def reject(name, sample_id, mutate):
            body = json.loads(self.sampling.read_text())
            mutate(next(item for item in body["key"] if item["sample_id"] == sample_id))
            path = self.root / f"{name}.sampling.json"
            path.write_text(json.dumps(body))
            out = self.root / f"{name}.json"
            with self.subTest(name=name), self.assertRaises(AISInputError) as caught:
                evaluate(self.run_dir, path, labels, out)
            message = str(caught.exception)
            self.assertIn(sample_id, message)
            self.assertIn("kind", message)
            self.assertNotIn("not in the run", message)
            self.assertFalse(out.exists())

        reject("candidate-as-negative", candidate["sample_id"], lambda unit: unit.update(kind="negative"))
        reject("negative-as-candidate", negative["sample_id"], lambda unit: unit.update(kind="candidate"))
        reject("missing-kind", candidate["sample_id"], lambda unit: unit.pop("kind"))

    def test_cli_reports_input_error_without_a_traceback(self):
        body = json.loads(self.sampling.read_text())
        unit = next(item for item in body["key"] if item["kind"] == "candidate")
        unit.pop("kind")
        sampling = self.root / "cli-missing-kind.sampling.json"
        sampling.write_text(json.dumps(body))
        labels = self.write_labels(lambda item: {"label": "unknown"}, name="cli-labels.csv")
        out = self.root / "cli-eval.json"
        stderr = io.StringIO()
        argv = ["harborlens-evaluate", "--run", str(self.run_dir), "--sampling", str(sampling),
                "--labels", str(labels), "--out", str(out)]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 2)
        text = stderr.getvalue()
        self.assertNotIn("Traceback", text)
        self.assertIn(unit["sample_id"], text)
        self.assertIn("kind", text)
        self.assertFalse(out.exists())

    def test_adjudicated_rows_satisfy_schema(self):
        path = self.write_labels(lambda u: {"label": "unknown"})
        validator = Draft202012Validator(json.loads((SCHEMAS / "adjudicated-label.schema.json").read_text()),
                                         format_checker=FormatChecker())
        with path.open(newline="") as handle:
            for row in csv.DictReader(handle):
                validator.validate(row)


class ReportContractTests(unittest.TestCase):
    """evaluation-v0.2 status, provenance, caveat, and the v0.1 reader (SPEC-003, FR-014, NFR-020)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        src = self.root / "in.csv"
        with src.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            writer.writerows(fixture_rows())
        self.run_dir = self.root / "run"
        run(src, self.run_dir, window_start="2024-01-02T00:00:00Z", window_end="2024-01-02T12:00:00Z")
        self.plan = draw_sample(self.run_dir, self.root / "sheet.csv", 11, candidates=10, negatives=6)
        self.sampling = self.root / "sheet.csv.sampling.json"

    def tearDown(self):
        self.tmp.cleanup()

    def write_labels(self, assign, name="adjudicated.csv"):
        path = self.root / name
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ADJUDICATED_FIELDS)
            writer.writeheader()
            for unit in self.plan["key"]:
                row = assign(unit)
                if row is not None:
                    writer.writerow({"sample_id": unit["sample_id"], "evidence_level": "L2",
                                     "duration_judgement": "assessable", "true_start_utc": "",
                                     "true_end_utc": "", "adjudicator_id": "J1", **row})
        return path

    def _report(self, name="eval.json"):
        path = self.write_labels(lambda unit: {"label": "unknown"}, name="labels-" + name)
        return evaluate(self.run_dir, self.sampling, path, self.root / name)

    def test_default_provenance_is_unspecified(self):
        report = self._report()
        self.assertEqual(report["schema_version"], "evaluation-v0.2")
        self.assertEqual(report["schema_version"], SCHEMA_VERSION)
        self.assertEqual(report["validation_status"], "unvalidated")
        self.assertEqual(report["validation_status"], VALIDATION_STATUS)
        self.assertEqual(report["label_provenance"], "unspecified")
        self.assertEqual(report["caveat"], CAVEAT_UNSPECIFIED)
        self.assertIn("Label provenance is unspecified", report["caveat"])
        self.assertIn("not independent ground truth", report["caveat"])
        self.assertIn("no accuracy claim", report["caveat"])
        self.assertNotEqual(report["caveat"], CAVEAT_SYNTHETIC)
        self.assertEqual(report["warning"], WARNING)
        loaded = read_evaluation_report(self.root / "eval.json")
        self.assertEqual(loaded["caveat"], report["caveat"])

    def test_cli_without_the_flag_records_unspecified(self):
        labels = self.write_labels(lambda unit: {"label": "unknown"})
        out = self.root / "cli-default.json"
        stderr = io.StringIO()
        stdout = io.StringIO()
        argv = ["harborlens-evaluate", "--run", str(self.run_dir), "--sampling", str(self.sampling),
                "--labels", str(labels), "--out", str(out)]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr), contextlib.redirect_stdout(stdout):
            main()
        report = json.loads(out.read_text(encoding="utf-8"))
        self.assertEqual(report["label_provenance"], "unspecified")
        self.assertEqual(report["validation_status"], "unvalidated")
        self.assertEqual(report["caveat"], CAVEAT_UNSPECIFIED)
        printed = json.loads(stdout.getvalue())
        self.assertEqual(printed["label_provenance"], "unspecified")
        self.assertEqual(printed["caveat"], CAVEAT_UNSPECIFIED)
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_schema_rejects_validation_status_other_than_unvalidated(self):
        report = self._report("schema.json")
        schema = json.loads((SCHEMAS / "evaluation-report.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["properties"]["schema_version"]["const"], "evaluation-v0.2")
        self.assertEqual(schema["properties"]["validation_status"], {"const": "unvalidated"})
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(report)
        for status in ("validated", "provisional", "synthetic", "", None):
            mutated = json.loads(json.dumps(report))
            mutated["validation_status"] = status
            with self.subTest(status=status):
                with self.assertRaises(ValidationError) as caught:
                    validator.validate(mutated)
                self.assertIn("unvalidated", str(caught.exception))
        old = json.loads(json.dumps(report))
        old["schema_version"] = "evaluation-v0.1"
        with self.assertRaises(ValidationError) as caught:
            validator.validate(old)
        self.assertIn("evaluation-v0.2", str(caught.exception))
        swapped = json.loads(json.dumps(report))
        swapped["caveat"] = CAVEAT_SYNTHETIC
        with self.assertRaises(ValidationError):
            validator.validate(swapped)

    def test_mixed_unknown_and_unlabeled_are_not_counted_as_correct(self):
        candidates = [unit for unit in self.plan["key"] if unit["kind"] == "candidate"]
        negatives = [unit for unit in self.plan["key"] if unit["kind"] == "negative"]
        self.assertGreaterEqual(len(candidates), 2)
        self.assertGreaterEqual(len(negatives), 2)
        mixed_id = candidates[0]["sample_id"]
        unknown_id = negatives[0]["sample_id"]
        unlabeled_id = negatives[1]["sample_id"]

        def assign(unit):
            if unit["sample_id"] == mixed_id:
                return {"label": "mixed"}
            if unit["sample_id"] == unknown_id:
                return {"label": "unknown"}
            if unit["sample_id"] == unlabeled_id:
                return None
            if unit["kind"] == "candidate":
                return {"label": "at_berth"}
            return {"label": "transit"}

        report = evaluate(self.run_dir, self.sampling, self.write_labels(assign, "excluded.csv"),
                          self.root / "excluded.json")
        tp = len(candidates) - 1
        tn = len(negatives) - 2
        overall = report["overall"]
        self.assertEqual((overall["tp"], overall["fp"], overall["fn"], overall["tn"]), (tp, 0, 0, tn))
        self.assertEqual(overall["n"], tp + tn)
        self.assertNotEqual(overall["tn"], len(negatives))
        self.assertEqual(report["coverage"]["excluded"], {"mixed": 1, "unknown": 1, "unlabeled": 1})
        self.assertEqual(report["coverage"]["evaluated_units"], tp + tn)

    def test_zero_judged_units_leave_metrics_null(self):
        candidates = [unit for unit in self.plan["key"] if unit["kind"] == "candidate"]
        negatives = [unit for unit in self.plan["key"] if unit["kind"] == "negative"]
        self.assertGreaterEqual(len(candidates), 1)
        self.assertGreaterEqual(len(negatives), 1)
        mixed_id = candidates[0]["sample_id"]
        unlabeled_id = negatives[0]["sample_id"]

        def assign(unit):
            if unit["sample_id"] == unlabeled_id:
                return None
            if unit["sample_id"] == mixed_id:
                return {"label": "mixed"}
            return {"label": "unknown"}

        report = evaluate(self.run_dir, self.sampling, self.write_labels(assign, "none.csv"),
                          self.root / "none.json")
        overall = report["overall"]
        self.assertEqual((overall["tp"], overall["fp"], overall["fn"], overall["tn"], overall["n"]), (0, 0, 0, 0, 0))
        for name in ("precision", "recall", "f1", "specificity",
                     "precision_ci95", "recall_ci95", "specificity_ci95"):
            self.assertIsNone(overall[name], name)
            self.assertNotIn(overall[name], (0, 1, 0.0, 1.0))
        self.assertIsNone(report["design_weighted_precision"])
        self.assertNotIn(report["design_weighted_precision"], (0, 1, 0.0, 1.0))
        for edge in ("start", "end", "duration"):
            timing = report["boundary_error_minutes"][edge]
            self.assertEqual(timing["n"], 0)
            self.assertIsNone(timing["mae_minutes"])
            self.assertIsNone(timing["median_absolute_error_minutes"])
            self.assertNotIn(timing["mae_minutes"], (0, 1, 0.0, 1.0))
        self.assertEqual(report["coverage"]["evaluated_units"], 0)
        self.assertEqual(report["coverage"]["excluded"]["mixed"], 1)
        self.assertEqual(report["coverage"]["excluded"]["unlabeled"], 1)
        self.assertGreaterEqual(report["coverage"]["excluded"]["unknown"], 1)

    def test_denominator_of_one(self):
        candidate = next(unit for unit in self.plan["key"] if unit["kind"] == "candidate")

        def assign(unit):
            if unit["sample_id"] == candidate["sample_id"]:
                return {"label": "at_berth"}
            return {"label": "unknown"}

        report = evaluate(self.run_dir, self.sampling, self.write_labels(assign, "one.csv"),
                          self.root / "one.json")
        overall = report["overall"]
        self.assertEqual((overall["tp"], overall["fp"], overall["fn"], overall["tn"], overall["n"]), (1, 0, 0, 0, 1))
        self.assertEqual(overall["precision"], 1.0)
        self.assertEqual(overall["recall"], 1.0)
        self.assertEqual(overall["f1"], 1.0)
        self.assertIsNone(overall["specificity"])
        # Wilson 95% for 1 success in 1 trial, rounded to 4 decimals: 1 / (1 + 1.959963984540054**2).
        self.assertEqual(overall["precision_ci95"], [0.2065, 1.0])
        self.assertEqual(overall["recall_ci95"], [0.2065, 1.0])
        self.assertIsNone(overall["specificity_ci95"])
        self.assertIsNot(overall["precision"], None)

    def test_invalid_label_provenance_exits_2_and_writes_nothing(self):
        labels = self.write_labels(lambda unit: {"label": "unknown"})
        for value in ("ground_truth", "Synthetic", "synthetic ", ""):
            out = self.root / f"rejected-{len(value)}.json"
            stderr = io.StringIO()
            argv = ["harborlens-evaluate", "--run", str(self.run_dir), "--sampling", str(self.sampling),
                    "--labels", str(labels), "--out", str(out), "--label-provenance", value]
            with self.subTest(value=value):
                with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as caught:
                        main()
                self.assertEqual(caught.exception.code, 2)
                text = stderr.getvalue()
                self.assertNotIn("Traceback", text)
                self.assertIn("label_provenance", text)
                self.assertFalse(out.exists())
                self.assertFalse(Path(str(out) + ".partial").exists())

    def test_library_rejects_unknown_provenance_before_writing(self):
        labels = self.write_labels(lambda unit: {"label": "unknown"})
        out = self.root / "library-rejected.json"
        with self.assertRaises(AISInputError):
            evaluate(self.run_dir, self.sampling, labels, out, label_provenance="ground_truth")
        self.assertFalse(out.exists())


class CensoredTruePositiveTests(unittest.TestCase):
    def test_all_true_positives_censored_leave_mae_and_median_null(self):
        """A stop that begins on the window edge is censored, so timing stays null."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            src = root / "edge.csv"
            start = datetime(2024, 1, 2)
            with src.open("w", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(HEADER)
                for minute in range(0, 41):
                    writer.writerow(["367110009", (start + timedelta(minutes=minute)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                                     "29.73", "-95.16", "0.1", "70", "1"])
            run_dir = root / "run"
            run(src, run_dir, window_start="2024-01-02T00:00:00Z", window_end="2024-01-02T06:00:00Z")
            plan = draw_sample(run_dir, root / "sheet.csv", 3, candidates=1, negatives=0)
            candidates = [unit for unit in plan["key"] if unit["kind"] == "candidate"]
            self.assertEqual(len(candidates), 1)
            geo = json.loads((run_dir / "stationary_candidates.geojson").read_text(encoding="utf-8"))
            props = {feature["properties"]["event_id"]: feature["properties"] for feature in geo["features"]}
            event = props[candidates[0]["event_id"]]
            self.assertEqual(event["left_censoring"], "censored")
            labels = root / "adjudicated.csv"
            with labels.open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=ADJUDICATED_FIELDS)
                writer.writeheader()
                writer.writerow({"sample_id": candidates[0]["sample_id"], "label": "at_berth",
                                 "evidence_level": "L2", "duration_judgement": "assessable",
                                 "true_start_utc": "2024-01-02T00:00:00Z", "true_end_utc": "2024-01-02T00:40:00Z",
                                 "adjudicator_id": "J1"})
            report = evaluate(run_dir, root / "sheet.csv.sampling.json", labels, root / "eval.json")
            self.assertEqual(report["overall"]["tp"], 1)
            self.assertEqual(report["overall"]["n"], 1)
            for edge in ("start", "end", "duration"):
                timing = report["boundary_error_minutes"][edge]
                self.assertEqual(timing["n"], 0, edge)
                self.assertIsNone(timing["mae_minutes"], edge)
                self.assertIsNone(timing["median_absolute_error_minutes"], edge)
                self.assertNotIn(timing["mae_minutes"], (0, 0.0, 1, 1.0))


class EvaluationV01CompatibilityTests(unittest.TestCase):
    def test_v01_report_raises_evaluation_report_error(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "old-evaluation.json"
            path.write_text(json.dumps({
                "schema_version": "evaluation-v0.1",
                "validation_status": "unvalidated",
                "warning": "previous report",
            }), encoding="utf-8")
            with self.assertRaises(EvaluationReportError) as caught:
                read_evaluation_report(path)
            message = str(caught.exception)
            self.assertEqual(type(caught.exception).__name__, "EvaluationReportError")
            self.assertIsInstance(caught.exception, AISInputError)
            self.assertIn("evaluation-v0.1", message)
            self.assertIn("evaluation-v0.2", message)
            self.assertNotIn("Traceback", message)
            self.assertEqual(path.read_text(encoding="utf-8").count("evaluation-v0.1"), 1)


class MetricMathTests(unittest.TestCase):
    def test_binary_metrics_hand_computed(self):
        m = binary_metrics(tp=8, fp=2, fn=4, tn=6)
        self.assertEqual((m["precision"], m["recall"], m["specificity"]), (0.8, 0.6667, 0.75))
        self.assertEqual(m["f1"], round(2 * 0.8 * (8 / 12) / (0.8 + 8 / 12), 4))
        self.assertEqual(m["n"], 20)

    def test_empty_denominators_are_none(self):
        m = binary_metrics(0, 0, 0, 0)
        self.assertIsNone(m["precision"])
        self.assertIsNone(m["f1"])
        self.assertIsNone(wilson(0, 0))

    def test_wilson_interval_reference_value(self):
        # 8/10 successes: Wilson 95% interval is approximately [0.4902, 0.9433].
        self.assertEqual(wilson(8, 10), [0.4902, 0.9433])
        low, high = wilson(10, 10)
        self.assertEqual(high, 1.0)
        self.assertLess(low, 1.0)


if __name__ == "__main__":
    unittest.main()
