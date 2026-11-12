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

    def test_pending_record_cannot_advertise_approval(self):
        row = dict(self.registry["sources"][0])
        row["rights_status"] = "reviewed_public_domain_attribution_required"
        self.registry["sources"] = [row]
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.registry))
        row["rights_status"] = "review_required"
        row["permitted_uses"] = dict(row["permitted_uses"], research="allowed")
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.registry))

    def test_reviewed_record_requires_exact_terms_url(self):
        row = dict(self.registry["sources"][0])
        row.update({
            "decision": "reviewed",
            "rights_status": "reviewed_public_domain_attribution_required",
            "reviewed_by": "Independent reviewer",
            "reviewed_at_utc": "2026-11-09T12:00:00Z",
            "terms_sha256": "a" * 64,
            "attribution": "Source institution.",
            "evidence_url": "https://example.org/review",
            "terms_url": "https://example.org/terms",
            "permitted_uses": {
                "research": "allowed",
                "public_aggregates": "unreviewed",
                "commercial": "prohibited",
            },
        })
        self.registry["sources"] = [row]
        self.assertTrue(Draft202012Validator(self.schema).is_valid(self.registry))
        row["terms_url"] = None
        self.assertFalse(Draft202012Validator(self.schema).is_valid(self.registry))


if __name__ == "__main__":
    unittest.main()
