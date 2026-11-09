"""Labeling-pilot tooling tests (SPEC-003, issue #8). Synthetic AIS only."""
import csv
import json
import random
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from harborlens.ais import run
from harborlens.io_safe import AISInputError
from harborlens.labeling import (
    ANNOTATION_FIELDS, SHEET_FIELDS, _allocate, agreement, cohen_kappa, draw_sample, parse_stratum,
    transceiver_stratum,
)

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"
HEADER = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"]
DAY = datetime(2024, 1, 2)


def rows():
    """Six vessels: stops of several lengths and types, separated by movement."""
    out = []
    plans = [("367100001", "70", [60, 200]), ("367100002", "80", [40]), ("367100003", "31", [90, 35]),
             ("367100004", "60", [300]), ("367100005", "", [45]), ("367100006", "70", [50, 50])]
    for n, (mmsi, vtype, stops) in enumerate(plans):
        t = DAY + timedelta(minutes=10 + n)
        lat, lon = 29.4 + n * 0.01, -95.0
        for stop in stops:
            for i in range(0, 45, 3):                     # 42 min of movement before each stop
                lon += 0.002
                out.append([mmsi, (t + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"), lat, lon, 8.0, vtype, "0"])
            t += timedelta(minutes=45)
            for i in range(0, stop + 1, 5):
                out.append([mmsi, (t + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"), lat, lon, 0.1, vtype, "1"])
            t += timedelta(minutes=stop + 5)
    return out


CLASSES = {"367100001": "A", "367100002": "A", "367100003": "Class B", "367100004": "B", "367100005": "",
           "367100006": "A"}


def write_with_classes(path):
    """Same synthetic vessels with a transceiver column: A, B and missing classes."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER + ["TransceiverClass"])
        for row in rows():
            writer.writerow(row + [CLASSES[row[0]]])
    return path


class TransceiverStratumTests(unittest.TestCase):
    """Transceiver class is a stratum (issue #65): Class B dominates real candidates."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.run_dir = self.root / "run"
        run(write_with_classes(self.root / "in.csv"), self.run_dir,
            window_start="2024-01-02T00:00:00Z", window_end="2024-01-02T12:00:00Z")
        self.schema = json.loads((SCHEMAS / "label-sample.schema.json").read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def test_bucket_and_key_parsing(self):
        self.assertEqual([transceiver_stratum(v) for v in ("A", "b", "Class B", "", None, "X")],
                         ["class_A", "class_B", "class_unknown", "class_unknown", "class_unknown", "class_unknown"])
        self.assertEqual(parse_stratum("gt_180|censored|cargo|class_B"),
                         {"kind": "candidate", "duration_band": "gt_180", "censoring": "censored",
                          "vessel_group": "cargo", "transceiver_class": "class_B"})
        self.assertEqual(parse_stratum("negative|tanker|class_A")["transceiver_class"], "class_A")
        # label-sample-v0.1 keys have no transceiver component and still parse.
        self.assertEqual(parse_stratum("lt_60|uncensored|cargo"),
                         {"kind": "candidate", "duration_band": "lt_60", "censoring": "uncensored",
                          "vessel_group": "cargo", "transceiver_class": None})
        self.assertEqual(parse_stratum("negative|cargo"), {"kind": "negative", "vessel_group": "cargo",
                                                           "transceiver_class": None})

    def test_every_class_is_a_stratum_and_recorded(self):
        record = draw_sample(self.run_dir, self.root / "sheet.csv", 3, candidates=200, negatives=200)
        Draft202012Validator(self.schema, format_checker=FormatChecker()).validate(record)
        self.assertEqual(record["schema_version"], "label-sample-v0.2")
        classes = {parse_stratum(k)["transceiver_class"] for k in record["frame"]["candidates"]}
        # "Class B" in the source normalizes to B at ingestion; a missing class stays its own stratum.
        self.assertEqual(classes, {"class_A", "class_B", "class_unknown"})
        coverage = record["stratification"]
        self.assertTrue(coverage["all_non_empty_strata_drawn"])
        self.assertEqual(coverage["transceiver_classes"]["candidates"]["drawn"],
                         ["class_A", "class_B", "class_unknown"])
        self.assertEqual(coverage["transceiver_classes"]["negatives"]["in_frame"],
                         coverage["transceiver_classes"]["negatives"]["drawn"])
        with (self.root / "sheet.csv").open(newline="") as handle:
            self.assertEqual(csv.DictReader(handle).fieldnames, SHEET_FIELDS)  # sheet stays blinded and unchanged

    def test_small_sample_still_covers_every_class(self):
        for seed in range(10):
            with self.subTest(seed=seed):
                record = draw_sample(self.run_dir, self.root / f"s{seed}.csv", seed, candidates=3, negatives=0)
                coverage = record["stratification"]
                self.assertFalse(coverage["all_non_empty_strata_drawn"])
                self.assertEqual(coverage["transceiver_classes"]["candidates"]["drawn"],
                                 coverage["transceiver_classes"]["candidates"]["in_frame"])
                self.assertEqual(record["drawn"]["candidates"], 3)

    def test_allocation_covers_each_value_when_short(self):
        strata = {f"{band}|x|y|{cls}": list(range(20 if cls == "class_A" else 2))
                  for band in ("a", "b", "c", "d") for cls in ("class_A", "class_B")}
        for seed in range(20):
            plan = _allocate(strata, 2, random.Random(seed), cover=lambda k: k.rsplit("|", 1)[-1])
            self.assertEqual(sum(plan.values()), 2)
            self.assertEqual({k.rsplit("|", 1)[-1] for k in plan}, {"class_A", "class_B"})


class SamplerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        src = self.root / "in.csv"
        with src.open("w", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(HEADER)
            writer.writerows(rows())
        self.run_dir = self.root / "run"
        self.manifest = run(src, self.run_dir, window_start="2024-01-02T00:00:00Z",
                            window_end="2024-01-02T12:00:00Z")

    def tearDown(self):
        self.tmp.cleanup()

    def sheet(self, name="sheet.csv", seed=7, **kw):
        record = draw_sample(self.run_dir, self.root / name, seed, **kw)
        with (self.root / name).open(newline="") as handle:
            return record, list(csv.DictReader(handle))

    def test_sample_is_reproducible_blinded_and_schema_valid(self):
        record, sheet = self.sheet(candidates=6, negatives=4)
        again = draw_sample(self.run_dir, self.root / "again.csv", 7, candidates=6, negatives=4)
        self.assertEqual((self.root / "sheet.csv").read_bytes(), (self.root / "again.csv").read_bytes())
        self.assertEqual(record["key"], again["key"])
        with (self.root / "sheet.csv").open(newline="") as handle:
            self.assertEqual(csv.DictReader(handle).fieldnames, SHEET_FIELDS)
        self.assertNotIn("kind", SHEET_FIELDS)
        self.assertNotIn("event_id", SHEET_FIELDS)
        self.assertEqual({r["sample_id"] for r in sheet}, {k["sample_id"] for k in record["key"]})
        self.assertEqual(record["drawn"], {"candidates": 6, "negatives": 4})
        self.assertEqual(record["parameter_set"], self.manifest["method_parameters"]["parameter_set"])
        schema = json.loads((SCHEMAS / "label-sample.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(record)

    def test_every_non_empty_stratum_is_represented(self):
        record, _ = self.sheet(candidates=100, negatives=100)
        frame = {**record["frame"]["candidates"], **record["frame"]["negatives"]}
        self.assertEqual(set(record["allocation"]), set(frame))
        self.assertEqual(record["drawn"]["candidates"], sum(record["frame"]["candidates"].values()))
        strata = {k["stratum"] for k in record["key"]}
        self.assertTrue(any(s.startswith("gt_180") for s in strata))
        self.assertTrue(any(parse_stratum(s)["vessel_group"] == "tug_or_service" for s in strata))
        self.assertTrue(record["stratification"]["all_non_empty_strata_drawn"])

    def test_negatives_are_moving_and_do_not_overlap_candidates(self):
        record, sheet = self.sheet(candidates=0, negatives=50)
        by_id = {r["sample_id"]: r for r in sheet}
        geo = json.loads((self.run_dir / "stationary_candidates.geojson").read_text())
        stops = [(f["properties"]["mmsi"], f["properties"]["start_utc"], f["properties"]["end_utc"])
                 for f in geo["features"]]
        self.assertGreater(record["drawn"]["negatives"], 0)
        for key in record["key"]:
            unit = by_id[key["sample_id"]]
            self.assertEqual(key["kind"], "negative")
            for mmsi, start, end in stops:
                if mmsi == unit["mmsi"]:
                    self.assertTrue(unit["end_utc"] < start or unit["start_utc"] > end)

    def test_tampered_run_and_overwrite_are_rejected(self):
        self.sheet()
        with self.assertRaises(AISInputError):
            draw_sample(self.run_dir, self.root / "sheet.csv", 7)
        path = self.run_dir / "stationary_candidates.geojson"
        path.write_text(path.read_text().replace('"unvalidated"', '"unvalidated" '))
        with self.assertRaisesRegex(AISInputError, "integrity"):
            draw_sample(self.run_dir, self.root / "other.csv", 7)

    def test_allocation_rules(self):
        rng = random.Random(1)
        strata = {"a": list(range(50)), "b": list(range(5)), "c": [1], "d": []}
        plan = _allocate(strata, 20, rng)
        self.assertEqual(sum(plan.values()), 20)
        self.assertEqual(set(plan), {"a", "b", "c"})
        self.assertGreater(plan["a"], plan["b"])
        self.assertEqual(sum(_allocate(strata, 2, rng).values()), 2)
        self.assertEqual(sum(_allocate(strata, 999, rng).values()), 56)

    def fill(self, name, annotator, labels, sheet_name="sheet.csv", level="L2", sources="ais_track"):
        with (self.root / sheet_name).open(newline="") as handle:
            sheet = list(csv.DictReader(handle))
        path = self.root / name
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=SHEET_FIELDS)
            writer.writeheader()
            for row, label in zip(sheet, labels):
                writer.writerow({**row, "annotator_id": annotator, "label": label, "confidence": "medium",
                                 "evidence_level": level, "evidence_sources": sources,
                                 "fragment_of_longer_stop": "false", "duration_judgement": "assessable",
                                 "notes": ""})
        return path

    def test_agreement_report(self):
        record, sheet = self.sheet(candidates=3, negatives=1)
        a = self.fill("a.csv", "A1", ["at_anchor", "at_anchor", "transit", "at_anchor"])
        b = self.fill("b.csv", "A2", ["at_anchor", "at_anchor", "transit", "transit"])
        report = agreement(a, b, self.root / "agreement.json", self.root / "sheet.csv.sampling.json")
        self.assertEqual(report["units"], 4)
        self.assertEqual(report["raw_agreement"], 0.75)
        self.assertEqual(report["kappa_labels"], 0.5)        # (0.75 - 0.5) / (1 - 0.5)
        self.assertEqual(len(report["disagreements"]), 1)
        self.assertEqual(set(report["by_kind"]), {"candidate", "negative"})
        schema = json.loads((SCHEMAS / "label-agreement.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
        record_schema = Draft202012Validator(json.loads((SCHEMAS / "label-record.schema.json").read_text()))
        with a.open(newline="") as handle:
            for row in csv.DictReader(handle):
                record_schema.validate({k: row[k] for k in ["sample_id", *ANNOTATION_FIELDS]})

    def test_agreement_rejects_invalid_sheets(self):
        self.sheet(candidates=3, negatives=1)
        good = self.fill("a.csv", "A1", ["unknown"] * 4)
        cases = {
            "bad-label.csv": dict(annotator="A2", labels=["anchored"] * 4),
            "same-annotator.csv": dict(annotator="A1", labels=["unknown"] * 4),
            "l3.csv": dict(annotator="A2", labels=["unknown"] * 4, level="L3", sources="ais_track"),
            "short.csv": dict(annotator="A2", labels=["unknown"] * 3),
        }
        for name, kwargs in cases.items():
            with self.subTest(name=name), self.assertRaises(AISInputError):
                agreement(good, self.fill(name, **kwargs), self.root / f"{name}.json")

    def test_kappa_edge_cases(self):
        self.assertIsNone(cohen_kappa([]))
        self.assertIsNone(cohen_kappa([("transit", "transit")] * 3))
        self.assertEqual(cohen_kappa([("a", "a"), ("b", "b")]), 1.0)


if __name__ == "__main__":
    unittest.main()
