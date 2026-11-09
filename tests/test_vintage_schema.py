"""Offline JSON Schema conformance for unverified NOAA ENC vintage evidence."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from harborlens.vintage import audit_vintage

SCHEMAS=Path(__file__).resolve().parents[1]/"schemas"/"v1"

class VintageSchemaTests(unittest.TestCase):
    def test_evidence_and_audit_contracts(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            polygon=root/"polygon.geojson"
            polygon.write_text(json.dumps({"type":"FeatureCollection","features":[]}))
            receipt=Path(str(polygon)+".source.json")
            receipt.write_text(json.dumps({
                "source_agency":"NOAA",
                "output_sha256":hashlib.sha256(polygon.read_bytes()).hexdigest(),
                "retrieved_at_utc":"2026-11-09T08:00:00Z",
                "historical_validity":"not_verified",
                "geometry_review_status":"unreviewed",
                "rights_status":"review_required",
            }))
            evidence=root/"enc.json"
            record={
                "source_kind":"NOAA_ENC","cell_id":"US5TX1234",
                "edition_number":3,"edition_date":"2026-01-01",
                "last_issue_date":"2026-08-04",
                "evidence_url":"https://charts.noaa.gov/ENCs/ENCsIndv.shtml",
                "referenced_document_sha256":"e"*64,
                "evidence_status":"user_supplied_unverified",
            }
            evidence.write_text(json.dumps(record))
            es=json.loads((SCHEMAS/"noaa-enc-documentary-evidence.schema.json").read_text())
            rs=json.loads((SCHEMAS/"geometry-vintage-audit.schema.json").read_text())
            for schema in (es,rs):
                Draft202012Validator.check_schema(schema)
            Draft202012Validator(es,format_checker=FormatChecker()).validate(record)
            result=audit_vintage(polygon,root/"report.json",
                "2024-01-02T00:00:00Z","2024-01-02T06:00:00Z",enc_evidence=evidence)
            Draft202012Validator(rs,format_checker=FormatChecker()).validate(result)
            self.assertEqual(result["date_assessment"],"edition_postdates_study")
            self.assertEqual(result["historical_geometry_validity"],"not_verified")
            result2=audit_vintage(polygon,root/"report2.json",
                "2024-01-02T00:00:00Z","2024-01-02T06:00:00Z")
            Draft202012Validator(rs,format_checker=FormatChecker()).validate(result2)
            self.assertEqual(result2["date_assessment"],"no_documentary_enc_evidence")

if __name__=="__main__":
    unittest.main()
