"""Offline Federal Register part 110 index-contract tests."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from harborlens.fr_timeline import (
    FederalRegisterAuditError, initial_url, scan_part110, save_scan,
)

class Response(io.BytesIO):
    def __init__(self, value):
        raw = json.dumps(value).encode("utf-8")
        super().__init__(raw)
        self.headers = {"Content-Length": str(len(raw))}

def doc(number, published="2023-08-11"):
    return {
        "document_number": number, "title": "Synthetic Part 110 change",
        "publication_date": published, "effective_on": published,
        "type": "Rule", "html_url": "https://www.federalregister.gov/documents/synthetic",
        "cfr_references": [{"title": 33, "part": 110}],
        "abstract": "Synthetic only. No real legal conclusion.",
    }

class FederalRegisterTests(unittest.TestCase):
    def test_query_fixed_host_and_cfr_bounds(self):
        u = initial_url("2023-07-01", "2024-01-02")
        self.assertIn("www.federalregister.gov/api/v1/documents.json", u)
        self.assertIn("conditions%5Bcfr%5D%5Bpart%5D=110", u)
        self.assertIn("2024-01-02", u)

    def test_two_pages_all_docs_require_review(self):
        first = initial_url("2023-07-01", "2024-01-02", per_page=2)
        second = initial_url("2023-07-01", "2024-01-02", per_page=2) + "&page=2"
        def fetch(request,timeout):
            return Response({"count":3,"results":[doc("A"),doc("B")],
                             "next_page_url":second} if request.full_url == first
                            else {"count":3,"results":[doc("C")],"next_page_url":None})
        report = scan_part110(opener=fetch,per_page=2)
        self.assertEqual(report["count"],3)
        self.assertEqual(len(report["query_pages"]),2)
        self.assertTrue(report["index_pagination_complete"])
        self.assertEqual(report["cfr_section_110_197_effective_state"],"NOT_DETERMINED")
        self.assertFalse(report["intervening_amendments_excluded"])
        self.assertFalse(report["ais_spatial_join_permitted"])
        self.assertTrue(all(x["review_status"].startswith("requires_manual") for x in report["documents"]))

    def test_no_results_is_not_legal_clearance(self):
        result = scan_part110(opener=lambda req,timeout: Response({
            "count":0,"results":[],"next_page_url":None
        }))
        self.assertEqual(result["count"],0)
        self.assertIn("not proof",result["no_result_interpretation"])

    def test_fail_closed_on_missing_page(self):
        with self.assertRaisesRegex(FederalRegisterAuditError,"Incomplete paginated"):
            scan_part110(opener=lambda req,timeout: Response({"count":2,"results":[doc("A")]}))

    def test_reject_external_pagination_url(self):
        with self.assertRaisesRegex(FederalRegisterAuditError,"fixed official"):
            scan_part110(opener=lambda req,timeout: Response({
                "count":2,"results":[doc("A")],
                "next_page_url":"https://malicious.example/api/v1/documents.json"
            }))

    def test_reject_duplicate_document_numbers(self):
        with self.assertRaisesRegex(FederalRegisterAuditError,"Repeated"):
            scan_part110(opener=lambda req,timeout: Response({
                "count":2,"results":[doc("A"),doc("A")],
            }))

    def test_reject_out_of_range_publication_date(self):
        with self.assertRaisesRegex(FederalRegisterAuditError,"outside requested"):
            scan_part110(opener=lambda req,timeout: Response({
                "count":1,"results":[doc("A","2025-06-01")]
            }))

    def test_reject_excessive_window_and_invalid_dates(self):
        with self.assertRaises(FederalRegisterAuditError):
            initial_url("2022-01-01","2024-01-02")
        with self.assertRaises(FederalRegisterAuditError):
            initial_url("2024-01-02","2023-07-01")
        with self.assertRaises(FederalRegisterAuditError):
            initial_url("2024-02-30","2024-03-01")

    def test_response_size_and_format_guards(self):
        def bad(request,timeout):
            value=Response({"count":0,"results":[]})
            value.headers["Content-Length"]="999999999"
            return value
        with self.assertRaisesRegex(FederalRegisterAuditError,"byte limit"):
            scan_part110(opener=bad)
        with self.assertRaises(FederalRegisterAuditError):
            scan_part110(opener=lambda req,timeout: io.BytesIO(b"not JSON"))

    def test_file_persistence_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/"fr.json"
            result=save_scan(path,opener=lambda req,timeout: Response({
                "count":1,"results":[doc("A")],
            }))
            self.assertEqual(result["count"],1)
            self.assertEqual(json.loads(path.read_text())["count"],1)
            with self.assertRaisesRegex(FederalRegisterAuditError,"new"):
                save_scan(path,opener=lambda req,timeout: Response({"count":0,"results":[]}))

if __name__ == "__main__":
    unittest.main()
