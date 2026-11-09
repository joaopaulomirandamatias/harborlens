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
    ANNOTATION_FIELDS, SHEET_FIELDS, _allocate, agreement, cohen_kappa, draw_sample,
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
        self.assertTrue(any(s.endswith("tug_or_service") for s in strata))

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
