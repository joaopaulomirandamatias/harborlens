"""Schema conformance checks for multi-day output, using only synthetic AIS."""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from harborlens.multiday import run_multiday

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"
FIRST = datetime(2024, 1, 2, 23, 40, tzinfo=timezone.utc)

def fixture(minutes):
    rows = ["MMSI,BaseDateTime,LAT,LON,SOG,VesselType,Status\n"]
    for m in minutes:
        ts = (FIRST + timedelta(minutes=m)).isoformat().replace("+00:00", "Z")
        rows.append(f"367800001,{ts},29.73,-95.16,0.2,70,5\n")
    return "".join(rows)

class MultiDayContractTests(unittest.TestCase):
    def test_manifest_and_geojson_feature_satisfy_versioned_schemas(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            a, b = root / "2024-01-02.csv", root / "2024-01-03.csv"
            a.write_text(fixture(range(0, 25, 5)))
            b.write_text(fixture(range(20, 50, 5)))
            manifest = run_multiday([a, b], root / "out")
            manifest_schema = json.loads((SCHEMAS / "multi-day-run.schema.json").read_text())
            feature_schema = json.loads((SCHEMAS / "multi-day-candidate-feature.schema.json").read_text())
            Draft202012Validator.check_schema(manifest_schema)
            Draft202012Validator.check_schema(feature_schema)
            self.assertEqual(manifest["schema_version"], "multi-day-1.1")
            self.assertIn(manifest["resources"]["memory_bound"]["soft_heap_limit_enforced"], (True, False, "unknown"))
            checker = Draft202012Validator(manifest_schema, format_checker=FormatChecker())
            checker.validate(manifest)
            for enforced in (True, False, "unknown"):
                variant = json.loads(json.dumps(manifest))
                variant["resources"]["memory_bound"]["soft_heap_limit_enforced"] = enforced
                checker.validate(variant)
            legacy = json.loads(json.dumps(manifest))
            legacy["schema_version"] = "multi-day-1.0"
            del legacy["resources"]["memory_bound"]
            snapshot = json.loads(json.dumps(legacy))
            errors = list(Draft202012Validator(manifest_schema, format_checker=FormatChecker()).iter_errors(legacy))
            self.assertTrue(errors)
            self.assertTrue(any(list(err.path) == ["schema_version"] for err in errors))
            self.assertTrue(any(list(err.path) == ["resources", "memory_bound"] or err.message.find("memory_bound") >= 0
                                for err in errors))
            self.assertEqual(legacy, snapshot)
            self.assertNotIn("memory_bound", legacy["resources"])
            geo = json.loads((root / "out" / "stationary_candidates.geojson").read_text())
            self.assertEqual(len(geo["features"]), 1)
            validator = Draft202012Validator(feature_schema, format_checker=FormatChecker())
            for feature in geo["features"]:
                validator.validate(feature)

if __name__ == "__main__":
    unittest.main()
