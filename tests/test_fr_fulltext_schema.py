"""JSON Schema ensures full-text search cannot imply legal approval."""
import json
import unittest
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker
from harborlens.fr_fulltext import inspect_documents
from test_fr_fulltext import mock_opener

SCHEMA=Path(__file__).resolve().parents[1]/"schemas"/"v1"/"fr-official-text-triage.schema.json"

class SourceTextContractTests(unittest.TestCase):
    def test_report_matches_noncertification_contract(self):
        schema=json.loads(SCHEMA.read_text())
        Draft202012Validator.check_schema(schema)
        report=inspect_documents(opener=mock_opener())
        Draft202012Validator(schema,format_checker=FormatChecker()).validate(report)
        self.assertEqual(report["section_110_197_historical_effect"],"NOT_DETERMINED")
        self.assertFalse(report["lsa_full_review_complete"])
        self.assertFalse(report["ais_geofence_approval"])

if __name__=="__main__":
    unittest.main()
