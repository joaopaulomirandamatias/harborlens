"""Shared segmentation engine tests (SPEC-002, issues #37 and #38). Synthetic AIS only."""
import csv
import hashlib
import json
import math
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from harborlens.ais import EVENT_FIELDS, run
from harborlens.io_safe import AISInputError
from harborlens.multiday import run_multiday
from harborlens.segmentation import (
    METHOD_VERSION, MemoryStore, SegmentationParams, Segmenter,
)
from harborlens.censoring import WindowCensoring
from harborlens.sensitivity import run_sensitivity
from harborlens.track_context import TrackEvidenceError, run_track_context

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"
HEADER = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"]
DAY = datetime(2024, 1, 2)
LAT0, LON0 = 29.5, -95.0
M_PER_DEG_LAT = 111_195.0


def north(metres):
    return LAT0 + metres / M_PER_DEG_LAT


def stamp(when):
    text = when.strftime("%Y-%m-%d %H:%M:%S")
    return text + (f".{when.microsecond:06d}" if when.microsecond else "")


def row(mmsi, when, lat=LAT0, lon=LON0, sog=0.1, vessel_type="70"):
    return [mmsi, stamp(when), lat, lon, sog, vessel_type, "1"]


def scenario():
    """Observations exercising every split and discard rule, spanning UTC midnight."""
    rows = []
    t = DAY + timedelta(hours=23)
    rows += [row("367000001", t + timedelta(minutes=5 * i)) for i in range(25)]          # crosses midnight
    t = DAY + timedelta(hours=20)
    rows += [row("367000002", t + timedelta(minutes=5 * i)) for i in range(9)]           # 40 min stop
    rows += [row("367000002", t + timedelta(minutes=80 + 5 * i)) for i in range(9)]      # after a gap
    rows += [row("367000003", t + timedelta(minutes=5 * i), vessel_type="70" if i < 10 else "80")
             for i in range(20)]                                                         # identity conflict
    rows += [row("367000004", t + timedelta(minutes=5 * i)) for i in range(10)]
    rows += [row("367000004", t + timedelta(minutes=46), lat=north(5000))]               # implausible jump
    rows += [row("367000005", t + timedelta(minutes=5 * i), lat=north(600 * i)) for i in range(10)]  # drift
    rows += [row("367000006", t + timedelta(minutes=2 * i)) for i in range(10)]          # too short
    rows += [row("367000007", t + timedelta(minutes=10 * i)) for i in range(5)]          # too few points
    rows += [row("367000008", t + timedelta(minutes=5 * i)) for i in range(9)]
    rows += [row("367000008", t + timedelta(minutes=45), lat=north(1900))]               # radius exceeded
    moving = [row("367000009", t + timedelta(minutes=5 * i), sog=0.6 if i == 10 else 0.1) for i in range(21)]
    rows += moving                                                                       # SOG spike split
    # Same-second fractional timestamps (#38): one candidate expected.
    base = DAY + timedelta(hours=21)
    for i in range(12):
        rows.append(row("367000010", base + timedelta(minutes=5 * i)))
        rows.append(row("367000010", base + timedelta(minutes=5 * i, microseconds=500000), lat=north(1)))
    return rows


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def read_events(folder):
    with (folder / "stationary_candidates.csv").open(newline="") as handle:
        return [{k: r[k] for k in EVENT_FIELDS} for r in csv.DictReader(handle)]


COMMON_DIAGNOSTICS = ("vessels", "points", "moving_points", "timestamp_conflicts", "gap_splits",
                      "identity_conflicts", "implausible_jumps", "spatial_splits", "discarded_groups",
                      "discarded_by_reason", "stationary_candidates", "candidates_per_mmsi")


class EngineEquivalenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        rows = scenario()
        self.whole = write_csv(self.root / "whole.csv", rows)
        self.day1 = write_csv(self.root / "day-1.csv", [r for r in rows if r[1] < "2024-01-03"])
        self.day2 = write_csv(self.root / "day-2.csv", [r for r in rows if r[1] >= "2024-01-03"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_single_file_and_multiday_produce_identical_candidates_and_diagnostics(self):
        single = run(self.whole, self.root / "single")
        multi = run_multiday([self.day1, self.day2], self.root / "multi")
        self.assertEqual(read_events(self.root / "single"), read_events(self.root / "multi"))
        for key in COMMON_DIAGNOSTICS:
            self.assertEqual(single["events"][key], multi["events"][key], key)
        self.assertEqual(single["method_parameters"], multi["method_parameters"])

    def test_every_rule_is_counted_by_reason(self):
        events = run(self.whole, self.root / "single")["events"]
        for reason in ("gap_splits", "identity_conflicts", "implausible_jumps", "spatial_splits"):
            self.assertGreaterEqual(events[reason], 1, reason)
        for reason in ("too_few_points", "too_short", "radius_exceeded"):
            self.assertGreaterEqual(events["discarded_by_reason"][reason], 1, reason)
        self.assertEqual(events["discarded_groups"], sum(events["discarded_by_reason"].values()))
        self.assertGreaterEqual(events["moving_points"], 1)
        self.assertEqual(events["candidates_per_mmsi"]["max"], 2)
        self.assertGreaterEqual(events["candidates_per_mmsi"]["mmsi_with_multiple"], 1)

    def test_same_second_fractional_timestamps_keep_one_candidate(self):
        run_multiday([self.day1, self.day2], self.root / "multi")
        fractional = [e for e in read_events(self.root / "multi") if e["mmsi"] == "367000010"]
        self.assertEqual(len(fractional), 1)
        self.assertEqual(fractional[0]["point_count"], "24")

    def test_candidate_records_method_and_parameter_set(self):
        run(self.whole, self.root / "single")
        geo = json.loads((self.root / "single" / "stationary_candidates.geojson").read_text())
        block = geo["harborlens_method"]
        self.assertEqual(block["method_version"], METHOD_VERSION)
        self.assertTrue(all(f["properties"]["parameter_set"] == block["parameter_set"] for f in geo["features"]))


class ParameterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.src = write_csv(self.root / "in.csv", scenario())

    def tearDown(self):
        self.tmp.cleanup()

    def test_non_default_thresholds_change_manifest_parameter_set_and_run_id(self):
        default = run(self.src, self.root / "a")
        custom = run(self.src, self.root / "b", params=SegmentationParams(max_sog_knots=1.0))
        self.assertEqual(custom["method_parameters"]["max_sog_knots"], 1.0)
        self.assertNotEqual(default["method_parameters"]["parameter_set"],
                            custom["method_parameters"]["parameter_set"])
        self.assertNotEqual(default["run_id"], custom["run_id"])
        # The 0.6 kn spike no longer splits MMSI 367000009 at max_sog_knots=1.0.
        spike = [e for e in read_events(self.root / "b") if e["mmsi"] == "367000009"]
        self.assertEqual(len(spike), 1)

    def test_invalid_parameters_are_rejected(self):
        for bad in ({"max_sog_knots": -1}, {"min_points": 1}, {"max_gap_minutes": math.nan},
                    {"min_points": 2.5}, {"max_radius_m": 0}, {"max_jump_knots": True}):
            with self.subTest(bad=bad), self.assertRaises(AISInputError):
                SegmentationParams(**bad)

    def test_cli_and_api_values_are_canonical(self):
        self.assertEqual(SegmentationParams(min_duration_minutes=30).manifest(),
                         SegmentationParams(min_duration_minutes=30.0).manifest())
        self.assertIsInstance(SegmentationParams(min_points=8.0).min_points, int)

    def test_parameter_block_round_trip_and_tamper_detection(self):
        params = SegmentationParams(max_gap_minutes=20)
        self.assertEqual(SegmentationParams.from_manifest(params.manifest()), params)
        tampered = {**params.manifest(), "max_gap_minutes": 30}
        with self.assertRaises(AISInputError):
            SegmentationParams.from_manifest(tampered)

    def test_engine_rejects_unsorted_input(self):
        engine = Segmenter(SegmentationParams(), MemoryStore(), lambda r, g: None, WindowCensoring(None, 15))
        engine.feed("367000001", DAY + timedelta(minutes=10), LAT0, LON0, 0.1)
        with self.assertRaises(AISInputError):
            engine.feed("367000001", DAY, LAT0, LON0, 0.1)

    def test_cli_threshold_flags(self):
        out = self.root / "cli"
        result = subprocess.run([sys.executable, "-m", "harborlens.cli", "--input", str(self.src), "--out",
                                 str(out), "--max-sog-knots", "1.0", "--min-points", "6"],
                                capture_output=True, text=True, check=True)
        params = json.loads(result.stdout)["method_parameters"]
        self.assertEqual((params["max_sog_knots"], params["min_points"]), (1.0, 6))

    def test_outputs_satisfy_updated_schemas(self):
        manifest = run(self.src, self.root / "s", params=SegmentationParams(max_gap_minutes=20))
        schema = json.loads((SCHEMAS / "run-manifest.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(manifest)
        candidate = json.loads((SCHEMAS / "stationary-candidate.schema.json").read_text())
        validator = Draft202012Validator(candidate, format_checker=FormatChecker())
        geo = json.loads((self.root / "s" / "stationary_candidates.geojson").read_text())
        for feature in geo["features"]:
            validator.validate({**feature["properties"], "centroid_lon": feature["geometry"]["coordinates"][0],
                                "centroid_lat": feature["geometry"]["coordinates"][1]})


class TrackContextParameterTests(unittest.TestCase):
    """track_context must use the thresholds the candidates were produced with."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        start = DAY + timedelta(hours=1)
        # SOG 0.8 kn: a candidate only when max_sog_knots >= 0.8.
        rows = [row("367000020", start + timedelta(minutes=5 * i), sog=0.8) for i in range(10)]
        self.src = write_csv(self.root / "in.csv", rows)
        ring = [[LON0 - 0.01, LAT0 - 0.01], [LON0 + 0.01, LAT0 - 0.01], [LON0 + 0.01, LAT0 + 0.01],
                [LON0 - 0.01, LAT0 + 0.01], [LON0 - 0.01, LAT0 - 0.01]]
        self.polygons = self.root / "zones.geojson"
        self.polygons.write_text(json.dumps({"type": "FeatureCollection", "features": [{
            "type": "Feature", "id": "1", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {"historical_validity": "not_verified", "geometry_review_status": "unreviewed"}}]}))
        digest = hashlib.sha256(self.polygons.read_bytes()).hexdigest()
        (self.root / "zones.geojson.source.json").write_text(json.dumps({
            "output_sha256": digest, "historical_validity": "not_verified",
            "geometry_review_status": "unreviewed", "rights_status": "review_required"}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_custom_thresholds_flow_into_completeness_check(self):
        out = self.root / "run"
        run(self.src, out, params=SegmentationParams(max_sog_knots=1.0))
        summary = run_track_context(out / "houston_clean.csv", out / "stationary_candidates.geojson",
                                    self.polygons, self.root / "ctx.geojson")
        self.assertEqual(summary["candidate_method"]["parameters_source"], "candidate_geojson")
        self.assertEqual(summary["outcome_counts"], {"all_observed_points_within_one_polygon": 1})
        schema = json.loads((SCHEMAS / "track-zone-context-receipt.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(summary)

    def test_parameter_set_mismatch_is_rejected(self):
        out = self.root / "run"
        run(self.src, out, params=SegmentationParams(max_sog_knots=1.0))
        path = out / "stationary_candidates.geojson"
        geo = json.loads(path.read_text())
        geo["features"][0]["properties"]["parameter_set"] = "0" * 12
        path.write_text(json.dumps(geo))
        with self.assertRaisesRegex(TrackEvidenceError, "parameter_set"):
            run_track_context(out / "houston_clean.csv", path, self.polygons, self.root / "ctx.geojson")


class SensitivityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        run(write_csv(self.root / "in.csv", scenario()), self.root / "base")
        self.cleaned = self.root / "base" / "houston_clean.csv"

    def tearDown(self):
        self.tmp.cleanup()

    def test_grid_report_is_descriptive_and_schema_valid(self):
        report = run_sensitivity(self.cleaned, self.root / "sens.json",
                                 {"max_sog_knots": [0.5, 1.0], "min_duration_minutes": [30, 60]},
                                 window_start="2024-01-02T20:00:00Z", window_end="2024-01-03T01:00:00Z")
        self.assertEqual(len(report["settings"]), 4)
        by = {(s["parameters"]["max_sog_knots"], s["parameters"]["min_duration_minutes"]): s
              for s in report["settings"]}
        self.assertGreaterEqual(by[(0.5, 30)]["stationary_candidates"], by[(0.5, 60)]["stationary_candidates"])
        self.assertLess(by[(1.0, 30)]["splits"]["gap_splits"] + by[(1.0, 30)]["moving_points"],
                        by[(0.5, 30)]["splits"]["gap_splits"] + by[(0.5, 30)]["moving_points"])
        self.assertIsNotNone(by[(0.5, 30)]["duration_minutes_uncensored"])
        schema = json.loads((SCHEMAS / "sensitivity-report.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(report)
        self.assertIn("Do not select thresholds", report["warning"])

    def test_grid_limits_and_overwrite_protection(self):
        with self.assertRaises(AISInputError):
            run_sensitivity(self.cleaned, self.root / "big.json",
                            {name: [1, 2, 3] for name in ("max_sog_knots", "max_gap_minutes",
                                                         "max_radius_m", "max_jump_knots")})
        (self.root / "exists.json").write_text("{}")
        with self.assertRaises(AISInputError):
            run_sensitivity(self.cleaned, self.root / "exists.json", {})
        with self.assertRaises(AISInputError):
            run_sensitivity(self.cleaned, self.root / "x.json", {"unknown_field": [1]})


if __name__ == "__main__":
    unittest.main()
