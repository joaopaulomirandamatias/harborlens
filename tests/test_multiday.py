"""Synthetic multi-day regression tests. No network access is required."""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from harborlens.multiday import run_multiday
from harborlens.provenance import verify_manifest
from harborlens.io_safe import AISInputError

HEADER = "MMSI,BaseDateTime,LAT,LON,SOG,VesselType,Status\n"
BASE = datetime(2024, 1, 2, 23, 40, tzinfo=timezone.utc)
MMSI = "199080001"

def fixture(minutes, vessel_type="70", longitude="-95.16"):
    values = [HEADER]
    for i in minutes:
        at = (BASE + timedelta(minutes=i)).isoformat().replace("+00:00", "Z")
        values.append(f"{MMSI},{at},29.73,{longitude},0.2,{vessel_type},5\n")
    return "".join(values)

class MultiDaySyntheticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.a, self.b = root / "part-1.csv", root / "part-2.csv"
        self.out = root / "report"
        self.other = root / "other"

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, first=range(0,25,5), second=range(20,50,5), first_type="70",
                second_type="70", second_lon="-95.16"):
        self.a.write_text(fixture(first, first_type))
        self.b.write_text(fixture(second, second_type, second_lon))

    def events(self):
        with (self.out / "stationary_candidates.csv").open(newline="") as f:
            return list(csv.DictReader(f))

    def test_midnight_duplicate_retains_both_sources(self):
        self.prepare()
        report = run_multiday([self.b, self.a], self.out)
        self.assertEqual(report["counts"]["total"], 11)
        self.assertEqual(report["counts"]["duplicate"], 1)
        self.assertEqual(report["counts"]["duplicate_across_files"], 1)
        self.assertEqual(report["counts"]["written"], 10)
        self.assertEqual(report["events"]["stationary_candidates"], 1)
        self.assertEqual(report["events"]["cross_day_candidates"], 1)
        event = self.events()[0]
        self.assertEqual(float(event["duration_min"]), 45.0)
        self.assertEqual(event["confidence_label"], "unvalidated")
        self.assertEqual(int(event["source_count"]), 2)
        self.assertEqual(event["crosses_utc_date"], "True")
        self.assertEqual(len(json.loads(event["source_files_json"])), 2)
        self.assertTrue(verify_manifest(self.out / "manifest.json")["ok"])
        geo = json.loads((self.out / "stationary_candidates.geojson").read_text())
        self.assertEqual(len(geo["features"][0]["properties"]["source_files"]), 2)

    def test_gap_prevents_false_continuity(self):
        self.prepare(range(0,20,5), range(40,60,5))
        result = run_multiday([self.a, self.b], self.out)
        self.assertEqual(result["events"]["stationary_candidates"], 0)
        self.assertGreaterEqual(result["events"]["gap_splits"], 1)
        self.assertEqual(self.events(), [])

    def test_conflicting_vessel_type_splits_candidate(self):
        self.prepare(range(0,25,5), range(25,50,5), second_type="80")
        result = run_multiday([self.a, self.b], self.out)
        self.assertEqual(result["events"]["stationary_candidates"], 0)
        self.assertGreaterEqual(result["events"]["identity_conflicts"], 1)

    def test_implausible_jump_splits_candidate(self):
        self.prepare(range(0,25,5), range(25,50,5), second_lon="-94.5")
        result = run_multiday([self.a, self.b], self.out)
        self.assertEqual(result["events"]["stationary_candidates"], 0)
        self.assertGreaterEqual(result["events"]["implausible_jumps"], 1)

    def test_invalid_and_outside_bbox_exclusions(self):
        self.prepare()
        with self.a.open("a") as f:
            f.write("199080002,2024-01-02T23:50:00Z,NaN,-95.16,0.2,70,0\n")
            f.write("199080003,2024-01-02T23:50:00Z,40.0,-95.16,0.2,70,0\n")
        result = run_multiday([self.a, self.b], self.out)
        self.assertEqual(result["counts"]["invalid"], 1)
        self.assertEqual(result["counts"]["outside_bbox"], 1)
        self.assertEqual(result["events"]["stationary_candidates"], 1)

    def test_determinism_independent_of_argument_order(self):
        self.prepare()
        a = run_multiday([self.a, self.b], self.out)
        b = run_multiday([self.b, self.a], self.other)
        self.assertEqual(a["run_id"], b["run_id"])
        self.assertEqual(a["artifacts"], b["artifacts"])

    def test_input_caps_fail_instead_of_silent_truncation(self):
        self.prepare()
        with self.assertRaisesRegex(AISInputError, "cap"):
            run_multiday([self.a, self.b], self.out, max_points=6)
        self.assertFalse((self.out / "manifest.json").exists())
        self.assertFalse((self.out / "houston_clean.csv").exists())
        run_multiday([self.a, self.b], self.out)
        with self.assertRaisesRegex(FileExistsError, "already exist"):
            run_multiday([self.a, self.b], self.out)

    def test_reject_single_and_duplicate_file(self):
        self.prepare()
        with self.assertRaises(AISInputError):
            run_multiday([self.a], self.out)
        with self.assertRaises(AISInputError):
            run_multiday([self.a, self.a], self.out)

    def test_tamper_detection_and_no_input_modification(self):
        self.prepare()
        before = (self.a.read_bytes(), self.b.read_bytes())
        run_multiday([self.a, self.b], self.out)
        self.assertEqual((self.a.read_bytes(), self.b.read_bytes()), before)
        with (self.out / "stationary_candidates.csv").open("a") as f:
            f.write("tampered\n")
        result = verify_manifest(self.out / "manifest.json")
        self.assertFalse(result["ok"])
        self.assertEqual(result["artifacts"]["stationary_candidates.csv"], "mismatch")

if __name__ == "__main__":
    unittest.main()
