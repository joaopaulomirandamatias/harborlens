"""Versioned Federal Register index report contract, entirely offline."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from harborlens.fr_timeline import scan_part110

SCHEMA=Path(__file__).resolve().parents[1]/"schemas"/"v1"/"fr-part110-index-audit.schema.json"

class Fake(io.BytesIO):
    def __init__(self, data):
        raw=json.dumps(data).encode()
        super().__init__(raw)
        self.headers={"Content-Length":str(len(raw))}

class FederalRegisterSchemaTests(unittest.TestCase):
    def test_empty_and_one_item_reports_are_noncertifying_and_schema_valid(self):
        schema=json.loads(SCHEMA.read_text())
        Draft202012Validator.check_schema(schema)
        validator=Draft202012Validator(schema,format_checker=FormatChecker())
        document={
            "document_number":"2023-00001","title":"Synthetic Proposed Anchorage Rule",
            "publication_date":"2023-09-01","effective_on":None,"type":"Proposed Rule",
            "html_url":"https://www.federalregister.gov/documents/synthetic",
            "cfr_references":[{"title":33,"part":110}],
            "abstract":"Synthetic example."
        }
        for rows in ([],[document]):
            with self.subTest(records=len(rows)):
                report=scan_part110(opener=lambda req,timeout:Fake({
                    "count":len(rows),"results":rows,"next_page_url":None
                }))
                validator.validate(report)
                self.assertEqual(report["cfr_section_110_197_effective_state"],"NOT_DETERMINED")
                self.assertFalse(report["intervening_amendments_excluded"])

if __name__ == "__main__":
    unittest.main()
