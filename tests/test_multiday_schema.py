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
            Draft202012Validator(manifest_schema, format_checker=FormatChecker()).validate(manifest)
            geo = json.loads((root / "out" / "stationary_candidates.geojson").read_text())
            self.assertEqual(len(geo["features"]), 1)
            validator = Draft202012Validator(feature_schema, format_checker=FormatChecker())
            for feature in geo["features"]:
                validator.validate(feature)

if __name__ == "__main__":
    unittest.main()
