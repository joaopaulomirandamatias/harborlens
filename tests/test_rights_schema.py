"""Schema checks for the checked-in source-rights register (SPEC-003)."""
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from harborlens.rights import _HTTPS_URL_PATTERN, _UTC_TIMESTAMP_PATTERN


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

    def test_timestamp_and_url_patterns_match_the_parser(self):
        items = self.schema["properties"]["sources"]["items"]
        for prop in ("source_url", "terms_url", "evidence_url"):
            self.assertEqual(items["properties"][prop]["pattern"], _HTTPS_URL_PATTERN)
        self.assertEqual(
            items["properties"]["reviewed_at_utc"]["pattern"], _UTC_TIMESTAMP_PATTERN
        )
        reviewed = items["allOf"][0]["then"]["properties"]
        self.assertEqual(reviewed["reviewed_at_utc"]["pattern"], _UTC_TIMESTAMP_PATTERN)
        self.assertEqual(reviewed["terms_url"]["pattern"], _HTTPS_URL_PATTERN)
        self.assertEqual(reviewed["evidence_url"]["pattern"], _HTTPS_URL_PATTERN)
        self.assertEqual(reviewed["reviewed_by"]["pattern"], r"\S")
        self.assertEqual(reviewed["attribution"]["pattern"], r"\S")

    def test_mere_z_suffix_and_trailing_url_space_fail_the_schema(self):
        validator = Draft202012Validator(self.schema)
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
        self.assertTrue(validator.is_valid(self.registry))
        for stamp in ("not-a-dateZ", "2026-11-09Z", "2026-11-09t12:00:00Z", "Z"):
            row["reviewed_at_utc"] = stamp
            self.assertFalse(validator.is_valid(self.registry), stamp)
        row["reviewed_at_utc"] = "2026-11-09T12:00:00Z"
        row["terms_url"] = "https://example.org/terms "
        self.assertFalse(validator.is_valid(self.registry))
        row["terms_url"] = "https://example.org/terms"
        row["evidence_url"] = "https://[2001:db8::1]/review"
        self.assertFalse(validator.is_valid(self.registry))
        row["evidence_url"] = "https://exämple.org/review"
        self.assertFalse(validator.is_valid(self.registry))
        row["evidence_url"] = "https://xn--exmple-cua.org/review"
        self.assertTrue(validator.is_valid(self.registry))
        row["reviewed_by"] = "   "
        self.assertFalse(validator.is_valid(self.registry))


if __name__ == "__main__":
    unittest.main()
