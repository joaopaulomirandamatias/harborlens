"""Offline, source-bounded LSA comparison tests (no actual PDFs downloaded)."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from harborlens.lsa_compare import LSAComparisonError, compare_official_lsa, save_report

TITLE = "TITLE 33—NAVIGATION AND NAVIGABLE WATERS\n" + "Historical Title 33 content. " * 30
PROPOSED = "\nProposed Rules:\n110 ......................47837, 89644, 89646, 89648\n117 ....12345\n"
END = "TITLE 34—EDUCATION\n" + "new unrelated title."
class FakePage:
    def __init__(self, text): self.text=text
    def extract_text(self): return self.text

class FakeReader:
    def __init__(self, section):
        self.pages = [FakePage("Title 32") for _ in range(30)] + [
            FakePage(section), FakePage(END),
        ]

class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

def opener(request, timeout):
    return Response(b"%PDF-SYNTHETIC")

def reader_factory(_raw):
    return FakeReader(TITLE + PROPOSED)

class GovInfoLSATests(unittest.TestCase):
    def test_known_source_receipts_are_non_certifying(self):
        r=compare_official_lsa(opener,reader_factory)
        self.assertEqual(r["source_months"],["2023-12","2024-01"])
        self.assertTrue(r["proposed_part110_pages_match"])
        self.assertFalse(r["ais_spatial_join_permitted"])
        self.assertFalse(r["intervening_amendments_excluded"])
        self.assertEqual(r["legal_effect_on_study_date"],"NOT_DETERMINED")
        for m,v in r["documents"].items():
            self.assertEqual(v["target_110_197_direct_occurrences"],0)
            self.assertEqual(v["part110_proposed_fr_pages"],["47837","89644","89646","89648"])

    def test_bad_proposed_page_reference_refused(self):
        altered=lambda raw: FakeReader(TITLE + PROPOSED.replace("89648","89649"))
        with self.assertRaisesRegex(LSAComparisonError,"citations changed"):
            compare_official_lsa(opener,altered)

    def test_target_110197_appearance_is_reported_not_suppressed(self):
        modified=lambda raw: FakeReader(TITLE + "\n110.197 revised.\n" + PROPOSED)
        r=compare_official_lsa(opener,modified)
        self.assertEqual(r["documents"]["2023-12"]["target_110_197_direct_occurrences"],1)
        self.assertFalse(r["historical_wgs84_geometry_approved"])

    def test_missing_title34_boundary_refused(self):
        def invalid(raw):
            f=FakeReader(TITLE+PROPOSED)
            f.pages[-1]=FakePage("No end title")
            return f
        with self.assertRaisesRegex(LSAComparisonError,"Title 33 end"):
            compare_official_lsa(opener,invalid)

    def test_missing_part110_entry_fails_closed(self):
        with self.assertRaisesRegex(LSAComparisonError,"missing"):
            compare_official_lsa(opener,lambda raw:FakeReader(TITLE+"\nProposed Rules:\n117....12345\n"))

    def test_oversized_download_rejected(self):
        def huge(req,timeout):
            resp=Response(b"%PDF-small")
            resp.headers["Content-Length"]="999999999"
            return resp
        with self.assertRaisesRegex(LSAComparisonError,"size cap"):
            compare_official_lsa(huge,reader_factory)

    def test_bad_pdf_signature_rejected(self):
        with self.assertRaisesRegex(LSAComparisonError,"invalid"):
            compare_official_lsa(lambda req,timeout:Response(b"<html>"),reader_factory)

    def test_save_report_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            dest=Path(folder)/"audit.json"
            report=save_report(dest,opener,reader_factory)
            self.assertEqual(json.loads(dest.read_text())["documents"].keys(),report["documents"].keys())
            with self.assertRaisesRegex(LSAComparisonError,"new"):
                save_report(dest,opener,reader_factory)

if __name__=="__main__":
    unittest.main()
