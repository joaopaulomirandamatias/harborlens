"""Offline synthetic historical NOAA ENC metadata audit tests. No network."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from harborlens.vintage import VintageAuditError, audit_vintage

START = "2024-01-02T00:00:00Z"
END = "2024-01-02T06:00:00Z"


class VintageAuditTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.polygon = self.root / "noaa-areas.geojson"
        self.receipt = self.root / "noaa-areas.geojson.source.json"
        self.evidence = self.root / "enc-record.json"
        self.output = self.root / "vintage-report.json"
        self.polygon.write_text(
            json.dumps({"type":"FeatureCollection","features":[{
                "type":"Feature","id":"1","geometry":{"type":"Polygon",
                "coordinates":[[[-95.2,29.7],[-95.0,29.7],[-95.0,29.8],[-95.2,29.7]]]},
                "properties":{"historical_validity":"not_verified"}}]}),
            encoding="utf-8",
        )
        self.receipt.write_text(json.dumps({
            "source_agency":"NOAA","output_sha256":hashlib.sha256(self.polygon.read_bytes()).hexdigest(),
            "retrieved_at_utc":"2026-11-09T08:00:00Z",
            "historical_validity":"not_verified","geometry_review_status":"unreviewed",
            "rights_status":"review_required"
        }), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def metadata(self, edition="2026-08-04", issue="2026-09-01"):
        self.evidence.write_text(json.dumps({
            "source_kind":"NOAA_ENC","cell_id":"US5TX1234",
            "edition_number":4,"edition_date":edition,
            "last_issue_date":issue,
            "evidence_url":"https://charts.noaa.gov/ENCs/ENCsIndv.shtml",
            "referenced_document_sha256":"a"*64,
            "evidence_status":"user_supplied_unverified"
        }),encoding="utf-8")
        return self.evidence

    def audit(self, evidence=None):
        return audit_vintage(self.polygon, self.output, START, END, enc_evidence=evidence)

    def test_no_documentary_evidence_remains_unverified(self):
        result=self.audit()
        self.assertEqual(result["date_assessment"],"no_documentary_enc_evidence")
        self.assertEqual(result["historical_geometry_validity"],"not_verified")
        self.assertEqual(result["source_rights"],"review_required")
        self.assertIsNone(result["documentary_evidence"])
        self.assertTrue(self.output.exists())

    def test_later_edition_explicitly_postdates_study(self):
        result=self.audit(self.metadata())
        self.assertEqual(result["date_assessment"],"edition_postdates_study")
        self.assertEqual(result["historical_geometry_validity"],"not_verified")
        self.assertEqual(result["documentary_evidence"]["evidence_status"],"user_supplied_unverified")
        self.assertEqual(result["evidence_metadata_sha256"],hashlib.sha256(self.evidence.read_bytes()).hexdigest())

    def test_earlier_dates_do_not_certify_historical_equivalence(self):
        result=self.audit(self.metadata("2022-01-01","2023-12-15"))
        self.assertEqual(result["date_assessment"],"document_dates_compatible_but_geometry_unverified")
        self.assertEqual(result["historical_geometry_validity"],"not_verified")
        self.assertEqual(result["operational_event_validation"],"not_verified")

    def test_update_date_after_start_is_flagged(self):
        result=self.audit(self.metadata("2023-01-01","2024-01-04"))
        self.assertEqual(result["date_assessment"],"update_issue_after_study_start")

    def test_source_receipt_mismatch_fails_without_partial_report(self):
        data=json.loads(self.receipt.read_text())
        data["output_sha256"]="0"*64
        self.receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(VintageAuditError,"hash"):
            self.audit()
        self.assertFalse(self.output.exists())

    def test_forged_geometry_approval_is_rejected(self):
        data=json.loads(self.receipt.read_text())
        data["historical_validity"]="verified"
        self.receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(VintageAuditError,"verified historical"):
            self.audit()

    def test_rights_must_remain_review_required(self):
        data=json.loads(self.receipt.read_text())
        data["rights_status"]="approved_commercial_use"
        self.receipt.write_text(json.dumps(data))
        with self.assertRaisesRegex(VintageAuditError,"review"):
            self.audit()

    def test_evidence_cannot_claim_self_certified_status(self):
        self.metadata()
        data=json.loads(self.evidence.read_text())
        data["evidence_status"]="officially_certified"
        self.evidence.write_text(json.dumps(data))
        with self.assertRaisesRegex(VintageAuditError,"user_supplied_unverified"):
            self.audit(self.evidence)

    def test_invalid_edition_and_update_dates_fail(self):
        self.metadata("2024-03-01","2023-12-31")
        with self.assertRaisesRegex(VintageAuditError,"cannot predate"):
            self.audit(self.evidence)
        self.metadata("2026-13-12","2026-12-13")
        with self.assertRaises(VintageAuditError):
            self.audit(self.evidence)

    def test_naive_time_or_reversed_time_fails(self):
        with self.assertRaisesRegex(VintageAuditError,"offset"):
            audit_vintage(self.polygon,self.output,"2024-01-02T00:00:00",END)
        with self.assertRaisesRegex(VintageAuditError,"precede"):
            audit_vintage(self.polygon,self.output,END,START)

    def test_unsupported_embedded_credentials_fail(self):
        self.metadata()
        data=json.loads(self.evidence.read_text())
        data["evidence_url"]="https://user:pass@charts.noaa.gov/ENCs/ENCsIndv.shtml"
        self.evidence.write_text(json.dumps(data))
        with self.assertRaisesRegex(VintageAuditError,"HTTPS"):
            self.audit(self.evidence)

    def test_no_overwrite_of_source_and_outputs(self):
        original=self.polygon.read_bytes()
        self.audit()
        with self.assertRaisesRegex(VintageAuditError,"overwrite"):
            self.audit()
        self.assertEqual(self.polygon.read_bytes(),original)
        with self.assertRaisesRegex(VintageAuditError,"distinct"):
            audit_vintage(self.polygon,self.polygon,START,END)


if __name__=="__main__":
    unittest.main()
