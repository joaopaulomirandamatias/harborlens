"""Schema checks for the checked-in source-rights register (SPEC-003)."""
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]


class RightsRegistrySchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = json.loads(
            (ROOT / "schemas/v1/source-rights-register.schema.json").read_text()
        )
        self.registry = json.loads(
            (ROOT / "docs/data/rights-register.json").read_text()
        )

    def test_schema_and_baseline_are_valid(self):
        Draft202012Validator.check_schema(self.schema)
        Draft202012Validator(self.schema).validate(self.registry)
        self.assertTrue(self.registry["sources"])
        self.assertTrue(all(s["decision"] == "pending" for s in self.registry["sources"]))
        self.assertTrue(all(s["rights_status"] == "review_required"
                            for s in self.registry["sources"]))

    def test_approved_without_provenance_is_rejected(self):
        row = dict(self.registry["sources"][0])
        row["decision"] = "reviewed"
        self.registry["sources"] = [row]
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.registry))


if __name__ == "__main__":
    unittest.main()
