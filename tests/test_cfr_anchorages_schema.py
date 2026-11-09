"""JSON Schema conformance for the non-operational USCG 2024 legal audit."""
import unittest
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from harborlens.cfr_anchorages import inspect_regulated_areas

SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "v1" / "cfr-2024-anchorages-audit.schema.json"

class LegalRegistrySchemaTests(unittest.TestCase):
    def test_regulatory_audit_matches_restrictive_schema(self):
        schema=json.loads(SCHEMA.read_text())
        Draft202012Validator.check_schema(schema)
        checker=Draft202012Validator(schema,format_checker=FormatChecker())
        for d in ("2024-07-01","2024-01-02"):
            with self.subTest(date=d):
                report=inspect_regulated_areas(d)
                checker.validate(report)
                self.assertTrue(all(not x["ais_spatial_join_permitted"] for x in report["areas"]))

if __name__ == "__main__":
    unittest.main()
