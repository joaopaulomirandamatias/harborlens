"""Offline tests for official Federal Register full-text triage."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from harborlens.fr_fulltext import (
    DOCUMENTS, FullTextAuditError, inspect_documents, save_review, _validate,
)

class Fake(io.BytesIO):
    def __init__(self,data):
        super().__init__(data)
        self.headers={"Content-Length":str(len(data))}

def mock_opener(mutator=None):
    def get(request,timeout):
        url=request.full_url
        number=next((n for n,_ in DOCUMENTS if n in url),None)
        published=dict(DOCUMENTS)[number]
        if url.endswith(".json"):
            obj={
                "document_number":number,"publication_date":published,
                "type":"Proposed Rule","title":"Synthetic Columbia River proposal",
                "effective_on":None,
                "html_url":"https://www.federalregister.gov/documents/synthetic",
                "raw_text_url":"https://www.federalregister.gov/documents/full_text/text/"+published.replace("-","/")+"/"+number+".txt",
            }
            if mutator:
                obj=mutator(obj,url)
            return Fake(json.dumps(obj).encode())
        if number=="2023-15652":
            text="Hudson River withdrawal document. "
        else:
            text="Columbia River Oregon Washington proposed anchorage text. "
        text=(text*25)
        return Fake(text.encode())
    return get

class FederalRegisterFullTextTests(unittest.TestCase):
    def test_all_four_official_record_texts_mocked(self):
        report=inspect_documents(opener=mock_opener())
        self.assertEqual(report["document_count"],4)
        self.assertTrue(report["full_text_fetch_complete"])
        self.assertFalse(report["lsa_full_review_complete"])
        self.assertEqual(report["section_110_197_historical_effect"],"NOT_DETERMINED")
        self.assertFalse(report["ais_geofence_approval"])
        self.assertTrue(all(not row["text_mentions_110_197"] for row in report["documents"]))
        self.assertTrue(all(len(row["raw_text_sha256"])==64 for row in report["documents"]))

    def test_withdrawal_signal_does_not_override_api_category(self):
        record=inspect_documents(opener=mock_opener())["documents"][0]
        self.assertEqual(record["indexed_document_type"],"Proposed Rule")
        self.assertTrue(record["text_mentions_withdrawal"])
        self.assertTrue(record["location_text_signals"]["hudson_river"])

    def test_official_document_hijack_rejected(self):
        def hijack(item,url):
            item["raw_text_url"]="https://malicious.example/full_text.txt"
            return item
        with self.assertRaisesRegex(FullTextAuditError,"official"):
            inspect_documents(opener=mock_opener(hijack))

    def test_metadata_document_number_mismatch_rejected(self):
        def alter(item,url):
            item["document_number"]="2024-99999"
            return item
        with self.assertRaisesRegex(FullTextAuditError,"mismatch"):
            inspect_documents(opener=mock_opener(alter))

    def test_metadata_publication_date_mismatch_rejected(self):
        def alter(item,url):
            item["publication_date"]="2026-11-09"
            return item
        with self.assertRaisesRegex(FullTextAuditError,"mismatch"):
            inspect_documents(opener=mock_opener(alter))

    def test_short_source_not_complete(self):
        def fetch(request,timeout):
            if request.full_url.endswith(".txt"):
                return Fake(b"short")
            return mock_opener()(request,timeout)
        with self.assertRaisesRegex(FullTextAuditError,"short"):
            inspect_documents(opener=fetch)

    def test_missing_raw_text_url_rejected(self):
        def alter(item,url):
            item.pop("raw_text_url")
            return item
        with self.assertRaisesRegex(FullTextAuditError,"lacks"):
            inspect_documents(opener=mock_opener(alter))

    def test_size_cap_enforced_on_headers(self):
        def fetch(request,timeout):
            data=mock_opener()(request,timeout)
            data.headers["Content-Length"]="999999999"
            return data
        with self.assertRaisesRegex(FullTextAuditError,"cap"):
            inspect_documents(opener=fetch)

    def test_document_path_must_match_number_and_date(self):
        n,d=DOCUMENTS[0]
        with self.assertRaisesRegex(FullTextAuditError,"expected"):
            _validate("https://www.federalregister.gov/documents/full_text/text/2025/01/01/"+n+".txt",n,d,"text")

    def test_save_is_atomic_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"review.json"
            data=save_review(path,opener=mock_opener())
            self.assertEqual(json.loads(path.read_text())["document_count"],4)
            self.assertEqual(data["section_110_197_historical_effect"],"NOT_DETERMINED")
            with self.assertRaisesRegex(FullTextAuditError,"new"):
                save_review(path,opener=mock_opener())

if __name__=="__main__":
    unittest.main()
