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
    ANNOTATION_FIELDS, SAMPLE_SCHEMA, SAMPLE_SCHEMA_V01, SHEET_FIELDS, TRANSCEIVER_STRATA,
    VESSEL_GROUPS, _allocate, agreement, cohen_kappa, draw_sample, parse_stratum,
    transceiver_stratum, vessel_group,
)

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"
HEADER = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"]
DAY = datetime(2024, 1, 2)


def rows():
    """Six vessels: stops of several lengths and types, separated by movement."""
    out = []
    plans = [("199010001", "70", [60, 200]), ("199010002", "80", [40]), ("199010003", "31", [90, 35]),
             ("199010004", "60", [300]), ("199010005", "", [45]), ("199010006", "70", [50, 50])]
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


CLASS_HEADER = HEADER + ["TransceiverClass"]


def track(mmsi, vtype, tclass, stops, index):
    """One synthetic vessel: movement, then each stop. Transceiver class is a raw source value."""
    out = []
    t = DAY + timedelta(minutes=10 + index * 3)
    lat, lon = 29.4 + index * 0.02, -95.0
    for stop in stops:
        for i in range(0, 45, 3):
            lon += 0.002
            out.append([mmsi, (t + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
                        lat, lon, 8.0, vtype, "0", tclass])
        t += timedelta(minutes=45)
        for i in range(0, stop + 1, 5):
            out.append([mmsi, (t + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
                        lat, lon, 0.1, vtype, "1", tclass])
        t += timedelta(minutes=stop + 5)
    return out


def write_classed_run(root, rows, name="run"):
    src = root / f"{name}-in.csv"
    with src.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CLASS_HEADER)
        writer.writerows(rows)
    run_dir = root / name
    run(src, run_dir, window_start="2024-01-02T00:00:00Z", window_end="2024-01-02T12:00:00Z")
    return run_dir


class TransceiverStratumTests(unittest.TestCase):
    """Transceiver class is a labeling stratum (SPEC-003, FR-013, issue #65). Synthetic AIS only."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.schema = json.loads((SCHEMAS / "label-sample.schema.json").read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def draw(self, run_dir, name, seed=7, **kw):
        record = draw_sample(run_dir, self.root / name, seed, **kw)
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema, format_checker=FormatChecker()).validate(record)
        return record

    def test_missing_and_invalid_values_map_to_absent_or_unknown(self):
        mapped = [transceiver_stratum(v) for v in
                  ("A", " a ", "Class A", "B", "b", "Class B", "", None, "X", "C", "not-a-class", "AB")]
        self.assertEqual(mapped, ["A", "A", "A", "B", "B", "B",
                                  "absent_or_unknown", "absent_or_unknown", "absent_or_unknown",
                                  "absent_or_unknown", "absent_or_unknown", "absent_or_unknown"])
        self.assertEqual(parse_stratum("gt_180|censored|cargo|B", SAMPLE_SCHEMA),
                         {"kind": "candidate", "duration_band": "gt_180", "censoring": "censored",
                          "vessel_group": "cargo", "transceiver_class": "B"})
        self.assertEqual(parse_stratum("negative|tanker|absent_or_unknown", SAMPLE_SCHEMA)["transceiver_class"],
                         "absent_or_unknown")
        produced = {vessel_group(code) for code in ("70", "80", "60", "31", "", "nope", None)}
        self.assertEqual(produced, set(VESSEL_GROUPS))

    def test_v01_stratum_is_accepted_only_with_explicit_schema_version(self):
        parsed = parse_stratum("lt_60|uncensored|tug_or_service", SAMPLE_SCHEMA_V01, "S0001")
        self.assertEqual(parsed["vessel_group"], "tug_or_service")
        self.assertIsNone(parsed["transceiver_class"])
        self.assertEqual(parse_stratum("negative|cargo", SAMPLE_SCHEMA_V01, "S0002")["vessel_group"], "cargo")

    def test_damaged_stratum_raises_for_the_sample_id(self):
        cases = (
            ("v0.2 three-part key ending in A", "lt_60|uncensored|A", SAMPLE_SCHEMA, "S0101"),
            ("v0.2 five-part key", "lt_60|uncensored|cargo|A|extra", SAMPLE_SCHEMA, "S0102"),
            ("unknown vessel group", "lt_60|uncensored|ferry|A", SAMPLE_SCHEMA, "S0103"),
            ("unknown class", "lt_60|uncensored|cargo|class_unknown", SAMPLE_SCHEMA, "S0104"),
            ("missing schema_version", "lt_60|uncensored|cargo|A", None, "S0105"),
            ("unknown schema_version", "lt_60|uncensored|cargo|A", "label-sample-v0.9", "S0106"),
            ("v0.1 key under v0.2", "lt_60|uncensored|cargo", SAMPLE_SCHEMA, "S0107"),
            ("v0.2 key under v0.1", "lt_60|uncensored|cargo|A", SAMPLE_SCHEMA_V01, "S0108"),
            ("v0.1 unknown vessel group", "lt_60|uncensored|ferry", SAMPLE_SCHEMA_V01, "S0109"),
        )
        for name, key, schema, sample_id in cases:
            with self.subTest(name=name):
                with self.assertRaises(AISInputError) as caught:
                    parse_stratum(key, schema, sample_id)
                self.assertIn(sample_id, str(caught.exception))

    def test_every_non_empty_class_stratum_is_drawn_and_the_sheet_stays_blind(self):
        rows = (track("199010001", "70", "A", [40, 200], 0)
                + track("199010002", "80", "Class B", [40], 1)
                + track("199010003", "31", "B", [90], 2)
                + track("199010004", "60", "", [45], 3)
                + track("199010005", "70", "b", [50], 4))
        run_dir = write_classed_run(self.root, rows)
        record = self.draw(run_dir, "sheet.csv", seed=3, candidates=200, negatives=200)
        again = self.draw(run_dir, "again.csv", seed=3, candidates=200, negatives=200)
        self.assertEqual(record["key"], again["key"])
        self.assertEqual(record["schema_version"], "label-sample-v0.2")
        frame = {**record["frame"]["candidates"], **record["frame"]["negatives"]}
        self.assertEqual(set(record["allocation"]), set(frame))
        self.assertTrue(record["stratification"]["all_non_empty_strata_drawn"])
        drawn = {row["stratum"] for row in record["key"]}
        self.assertEqual(drawn, set(frame))
        for row in record["key"]:
            self.assertEqual(row["transceiver_class"], parse_stratum(row["stratum"], SAMPLE_SCHEMA)["transceiver_class"])
            self.assertIn(row["transceiver_class"], TRANSCEIVER_STRATA)
        classes = record["stratification"]["transceiver_classes"]
        self.assertEqual(classes["candidates"]["in_frame"], ["A", "B", "absent_or_unknown"])
        self.assertEqual(classes["candidates"]["drawn"], ["A", "B", "absent_or_unknown"])
        self.assertEqual(classes["negatives"]["drawn"], classes["negatives"]["in_frame"])
        self.assertEqual(set(classes["negatives"]["in_frame"]), {"A", "B", "absent_or_unknown"})
        geo = json.loads((run_dir / "stationary_candidates.geojson").read_text())
        self.assertEqual(sum(record["frame"]["candidates"].values()), len(geo["features"]))
        with (self.root / "sheet.csv").open(newline="") as handle:
            fields = csv.DictReader(handle).fieldnames
        self.assertEqual(fields, SHEET_FIELDS)
        self.assertNotIn("transceiver_class", fields)
        self.assertNotIn("kind", fields)
        self.assertNotIn("stratum", fields)

    def test_short_request_records_cross_cell_gap_and_covers_every_class(self):
        """Full stratum coverage is impossible when the request is smaller than the frame.

        all_non_empty_strata_drawn is false, and every present class is still drawn
        when the request is at least the number of classes (SPEC-003, FR-013, #65).
        """
        rows = (track("199010011", "70", "A", [40], 0)
                + track("199010012", "70", "A", [200], 1)
                + track("199010013", "80", "B", [40], 2)
                + track("199010014", "60", "", [90], 3))
        run_dir = write_classed_run(self.root, rows, name="small")
        for seed in range(8):
            with self.subTest(seed=seed):
                record = self.draw(run_dir, f"s{seed}.csv", seed=seed, candidates=3, negatives=0)
                candidate_frame = record["frame"]["candidates"]
                requested = record["requested"]["candidates"]
                coverage = record["stratification"]["transceiver_classes"]["candidates"]
                drawn_strata = {row["stratum"] for row in record["key"] if row["kind"] == "candidate"}
                self.assertLess(requested, len(candidate_frame))
                self.assertGreaterEqual(requested, len(coverage["in_frame"]))
                self.assertEqual(record["drawn"]["candidates"], requested)
                self.assertEqual(coverage["in_frame"], ["A", "B", "absent_or_unknown"])
                self.assertEqual(coverage["drawn"], coverage["in_frame"])
                self.assertLess(len(drawn_strata), len(candidate_frame))
                self.assertFalse(record["stratification"]["all_non_empty_strata_drawn"])

    def test_empty_transceiver_stratum_is_omitted(self):
        rows = track("199010021", "70", "A", [40, 50], 0) + track("199010022", "80", "A", [60], 1)
        run_dir = write_classed_run(self.root, rows, name="only_a")
        record = self.draw(run_dir, "only_a.csv", candidates=50, negatives=20)
        for bucket in ("candidates", "negatives"):
            present = set(record["stratification"]["transceiver_classes"][bucket]["in_frame"])
            drawn = set(record["stratification"]["transceiver_classes"][bucket]["drawn"])
            self.assertEqual(present, {"A"})
            self.assertEqual(drawn, {"A"})
        tokens = {parse_stratum(key, SAMPLE_SCHEMA)["transceiver_class"] for key in record["allocation"]}
        self.assertEqual(tokens, {"A"})
        self.assertNotIn("B", tokens)
        self.assertNotIn("absent_or_unknown", tokens)

    def test_singleton_stratum_is_drawn_once(self):
        rows = (track("199010031", "70", "A", [40, 50, 80], 0)
                + track("199010032", "80", "B", [40], 1))
        run_dir = write_classed_run(self.root, rows, name="one_b")
        geo = json.loads((run_dir / "stationary_candidates.geojson").read_text())
        class_b = [f["properties"]["event_id"] for f in geo["features"]
                   if f["properties"].get("transceiver_class") == "B"]
        self.assertEqual(len(class_b), 1)
        record = self.draw(run_dir, "one_b.csv", candidates=100, negatives=0)
        b_keys = [key for key, count in record["frame"]["candidates"].items()
                  if parse_stratum(key, SAMPLE_SCHEMA)["transceiver_class"] == "B"]
        self.assertEqual(len(b_keys), 1)
        self.assertEqual(record["frame"]["candidates"][b_keys[0]], 1)
        self.assertEqual(record["allocation"][b_keys[0]], 1)
        drawn = [row for row in record["key"] if row["transceiver_class"] == "B"]
        self.assertEqual(len(drawn), 1)
        self.assertEqual(drawn[0]["event_id"], class_b[0])

    def test_invalid_class_is_kept_in_the_absent_stratum(self):
        rows = (track("199010041", "70", "A", [40], 0)
                + track("199010042", "80", "X", [40], 1)
                + track("199010043", "31", "", [50], 2)
                + track("199010044", "60", "not-a-class", [45], 3))
        run_dir = write_classed_run(self.root, rows, name="invalid")
        geo = json.loads((run_dir / "stationary_candidates.geojson").read_text())
        absent_ids = {f["properties"]["event_id"] for f in geo["features"]
                      if not f["properties"].get("transceiver_class")}
        self.assertGreaterEqual(len(absent_ids), 3)
        record = self.draw(run_dir, "invalid.csv", candidates=100, negatives=50)
        self.assertEqual(sum(record["frame"]["candidates"].values()), len(geo["features"]))
        drawn_absent = {row["event_id"] for row in record["key"]
                        if row["kind"] == "candidate" and row["transceiver_class"] == "absent_or_unknown"}
        self.assertEqual(drawn_absent, absent_ids)
        self.assertNotIn("X", {row["transceiver_class"] for row in record["key"]})
        self.assertNotIn("not-a-class", {row["stratum"] for row in record["key"]})
        self.assertIn("absent_or_unknown", record["stratification"]["transceiver_classes"]["candidates"]["drawn"])
        self.assertIn("absent_or_unknown", record["stratification"]["transceiver_classes"]["negatives"]["drawn"])

    def test_allocation_omits_empty_and_keeps_a_singleton(self):
        strata = {
            "lt_60|uncensored|cargo|A": list(range(10)),
            "lt_60|uncensored|cargo|B": [1],
            "lt_60|uncensored|cargo|absent_or_unknown": [],
        }
        plan = _allocate(strata, 5, random.Random(1), cover=lambda key: key.rsplit("|", 1)[-1])
        self.assertNotIn("lt_60|uncensored|cargo|absent_or_unknown", plan)
        self.assertEqual(plan["lt_60|uncensored|cargo|B"], 1)
        self.assertEqual(plan["lt_60|uncensored|cargo|A"], 4)
        self.assertEqual(sum(plan.values()), 5)
        many = {}
        for band in ("a", "b", "c", "d"):
            many[f"{band}|A"] = list(range(20))
            many[f"{band}|B"] = list(range(2))
            many[f"{band}|absent_or_unknown"] = [0]
        many["empty|A"] = []
        for seed in range(12):
            short = _allocate(many, 3, random.Random(seed), cover=lambda key: key.rsplit("|", 1)[-1])
            self.assertEqual(sum(short.values()), 3)
            self.assertEqual({key.rsplit("|", 1)[-1] for key in short}, {"A", "B", "absent_or_unknown"})
            self.assertNotIn("empty|A", short)


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
        self.assertTrue(any(parse_stratum(s, SAMPLE_SCHEMA)["vessel_group"] == "tug_or_service" for s in strata))
        # This fixture has no transceiver column, so every unit is the absent/unknown stratum.
        self.assertEqual({parse_stratum(s, SAMPLE_SCHEMA)["transceiver_class"] for s in strata}, {"absent_or_unknown"})
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
