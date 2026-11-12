"""Offline, source-bounded LSA comparison tests (no actual PDFs downloaded)."""
import contextlib
import hashlib
import io
import json
import socket
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request

import harborlens.lsa_compare as lsa_compare
from harborlens.lsa_compare import (
    FIXED_GOVINFO_URLS,
    LSAComparisonError,
    MAX_REDIRECTS,
    MAX_SOURCE_BYTES,
    MAX_TITLE33_CHARS,
    TIMEOUT_SECONDS,
    _GovInfoRedirects,
    _require_fixed_govinfo_url,
    compare_official_lsa,
    digests_equal,
    save_report,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas" / "v1" / "govinfo-lsa-dec-jan-comparison.schema.json"
TITLE = "TITLE 33—NAVIGATION AND NAVIGABLE WATERS\n" + "Historical Title 33 content. " * 30
PROPOSED = "\nProposed Rules:\n110 ......................47837, 89644, 89646, 89648\n117 ....12345\n"
END = "TITLE 34—EDUCATION\n" + "new unrelated title."
SYNTHETIC_PDF = b"%PDF-SYNTHETIC"
REMOVED_WORKFLOW = ROOT / ".github" / "workflows" / "lsa-dec-2023-jan-2024-comparison.yml"


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class FakeReader:
    def __init__(self, section, prefix=30, end=END):
        self.pages = [FakePage("Title 32") for _ in range(prefix)] + [
            FakePage(section),
            FakePage(end),
        ]


class Response(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
        return False


def opener(request, timeout):
    return Response(SYNTHETIC_PDF)


def reader_factory(_raw):
    return FakeReader(TITLE + PROPOSED)


def section_of_length(length):
    core = TITLE[: TITLE.index("\n") + 1] + PROPOSED
    if length < len(core):
        raise ValueError("section shorter than the synthetic header")
    return core + ("." * (length - len(core)))


class GovInfoLSATests(unittest.TestCase):
    def setUp(self):
        self._create_connection = socket.create_connection

        def blocked(*args, **kwargs):
            raise AssertionError("test attempted a real network connection")

        socket.create_connection = blocked

    def tearDown(self):
        socket.create_connection = self._create_connection

    def assert_same_digest(self, left, right):
        self.assertTrue(digests_equal(left, right), "synthetic digest mismatch")

    def test_known_source_receipts_are_non_certifying(self):
        report = compare_official_lsa(opener, reader_factory)
        self.assertEqual(report["source_months"], ["2023-12", "2024-01"])
        self.assertTrue(report["proposed_part110_pages_match"])
        self.assertFalse(report["ais_spatial_join_permitted"])
        self.assertFalse(report["intervening_amendments_excluded"])
        self.assertFalse(report["historical_wgs84_geometry_approved"])
        self.assertEqual(report["legal_effect_on_study_date"], "NOT_DETERMINED")
        self.assertEqual(report["rights_status"], "review_required")
        expected_pdf = hashlib.sha256(SYNTHETIC_PDF).hexdigest()
        expected_text = hashlib.sha256((TITLE + PROPOSED).encode("utf-8")).hexdigest()
        for month, document in report["documents"].items():
            self.assertEqual(document["official_pdf_url"], FIXED_GOVINFO_URLS[month])
            self.assertEqual(document["target_110_197_direct_occurrences"], 0)
            self.assertEqual(document["part110_proposed_fr_pages"], ["47837", "89644", "89646", "89648"])
            self.assertEqual(document["rights_status"], "review_required")
            self.assert_same_digest(document["official_pdf_sha256"], expected_pdf)
            self.assert_same_digest(document["title33_extracted_text_sha256"], expected_text)
            self.assert_same_digest(document["official_pdf_sha256"], expected_pdf.upper())

    def test_digest_helper_rejects_mismatch_and_bad_shape(self):
        digest = hashlib.sha256(SYNTHETIC_PDF).hexdigest()
        flipped = digest[:-1] + ("0" if digest[-1] != "0" else "1")
        self.assertTrue(digests_equal(digest, digest))
        self.assertFalse(digests_equal(digest, flipped))
        self.assertFalse(digests_equal(digest, digest[:-1]))
        self.assertFalse(digests_equal(digest, digest + "aa"))
        self.assertFalse(digests_equal(digest, None))
        self.assertFalse(digests_equal("g" * 64, "g" * 64))

    def test_json_schema_forbids_effective_law_or_ais_approval(self):
        from jsonschema import Draft202012Validator, FormatChecker

        schema = json.loads(SCHEMA_PATH.read_text())
        Draft202012Validator.check_schema(schema)
        record = compare_official_lsa(opener, reader_factory)
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        validator.validate(record)
        self.assertEqual(schema["properties"]["legal_effect_on_study_date"]["const"], "NOT_DETERMINED")
        self.assertIs(schema["properties"]["ais_spatial_join_permitted"]["const"], False)
        self.assertIs(schema["properties"]["historical_wgs84_geometry_approved"]["const"], False)
        self.assertEqual(schema["properties"]["rights_status"]["const"], "review_required")
        self.assertEqual(
            schema["properties"]["documents"]["properties"]["2023-12"]["properties"]["official_pdf_url"]["const"],
            FIXED_GOVINFO_URLS["2023-12"],
        )
        self.assertEqual(
            schema["properties"]["documents"]["properties"]["2024-01"]["properties"]["official_pdf_url"]["const"],
            FIXED_GOVINFO_URLS["2024-01"],
        )
        for mutated in (
            {"legal_effect_on_study_date": "VERIFIED"},
            {"legal_effect_on_study_date": "APPROVED"},
            {"historical_wgs84_geometry_approved": True},
            {"ais_spatial_join_permitted": True},
            {"rights_status": "granted"},
            {"certification": "approved"},
        ):
            candidate = json.loads(json.dumps(record))
            candidate.update(mutated)
            self.assertGreater(len(list(validator.iter_errors(candidate))), 0, mutated)

    def test_bad_proposed_page_reference_refused(self):
        altered = lambda raw: FakeReader(TITLE + PROPOSED.replace("89648", "89649"))
        with self.assertRaisesRegex(LSAComparisonError, "citations changed"):
            compare_official_lsa(opener, altered)

    def test_ambiguous_part110_line_fails_closed(self):
        doubled = TITLE + PROPOSED + "110 ......................47837, 89644, 89646, 89648\n"
        with self.assertRaisesRegex(LSAComparisonError, "ambiguous"):
            compare_official_lsa(opener, lambda raw: FakeReader(doubled))

    def test_target_110197_appearance_is_reported_not_suppressed(self):
        modified = lambda raw: FakeReader(TITLE + "\n110.197 revised.\n" + PROPOSED)
        report = compare_official_lsa(opener, modified)
        self.assertEqual(report["documents"]["2023-12"]["target_110_197_direct_occurrences"], 1)
        self.assertFalse(report["historical_wgs84_geometry_approved"])
        self.assertEqual(report["legal_effect_on_study_date"], "NOT_DETERMINED")

    def test_missing_title34_boundary_refused(self):
        def invalid(raw):
            reader = FakeReader(TITLE + PROPOSED)
            reader.pages[-1] = FakePage("No end title")
            return reader

        with self.assertRaisesRegex(LSAComparisonError, "Title 33 end"):
            compare_official_lsa(opener, invalid)

    def test_missing_part110_entry_fails_closed(self):
        with self.assertRaisesRegex(LSAComparisonError, "missing"):
            compare_official_lsa(opener, lambda raw: FakeReader(TITLE + "\nProposed Rules:\n117....12345\n"))

    def test_page_count_bounds(self):
        compare_official_lsa(opener, lambda raw: FakeReader(TITLE + PROPOSED, prefix=24))
        compare_official_lsa(opener, lambda raw: FakeReader(TITLE + PROPOSED, prefix=297))
        with self.assertRaisesRegex(LSAComparisonError, "page count"):
            compare_official_lsa(opener, lambda raw: FakeReader(TITLE + PROPOSED, prefix=23))
        with self.assertRaisesRegex(LSAComparisonError, "page count"):
            compare_official_lsa(opener, lambda raw: FakeReader(TITLE + PROPOSED, prefix=298))

    def test_extracted_text_length_bounds(self):
        compare_official_lsa(opener, lambda raw: FakeReader(section_of_length(300)))
        with self.assertRaisesRegex(LSAComparisonError, "unexpectedly short"):
            compare_official_lsa(opener, lambda raw: FakeReader(section_of_length(299)))
        with self.assertRaisesRegex(LSAComparisonError, "exceeds the size cap"):
            compare_official_lsa(opener, lambda raw: FakeReader(section_of_length(MAX_TITLE33_CHARS + 1)))

    def test_oversized_download_rejected(self):
        def huge(req, timeout):
            resp = Response(b"%PDF-small")
            resp.headers["Content-Length"] = "999999999"
            return resp

        with self.assertRaisesRegex(LSAComparisonError, "size cap"):
            compare_official_lsa(huge, reader_factory)

    def test_body_over_cap_rejected_when_header_understates(self):
        def huge(req, timeout):
            resp = Response(b"%PDF-" + b"A" * (MAX_SOURCE_BYTES + 1))
            resp.headers["Content-Length"] = "10"
            return resp

        with self.assertRaisesRegex(LSAComparisonError, "oversized"):
            compare_official_lsa(huge, reader_factory)

    def test_non_integer_content_length_rejected(self):
        def bad(req, timeout):
            resp = Response(SYNTHETIC_PDF)
            resp.headers["Content-Length"] = "10mb"
            return resp

        with self.assertRaisesRegex(LSAComparisonError, "Content-Length"):
            compare_official_lsa(bad, reader_factory)

    def test_bad_pdf_signature_rejected(self):
        with self.assertRaisesRegex(LSAComparisonError, "invalid"):
            compare_official_lsa(lambda req, timeout: Response(b"<html>"), reader_factory)

    def test_fixed_urls_and_recorded_timeout(self):
        seen = []

        def recording(request, timeout):
            seen.append((request.full_url, request.get_method(), request.data, timeout))
            return Response(SYNTHETIC_PDF)

        compare_official_lsa(recording, reader_factory)
        self.assertEqual([item[0] for item in seen], list(FIXED_GOVINFO_URLS.values()))
        self.assertTrue(all(item[1] == "GET" and item[2] is None for item in seen))
        self.assertTrue(all(item[3] == TIMEOUT_SECONDS for item in seen))
        self.assertLessEqual(TIMEOUT_SECONDS, 60)
        self.assertEqual(MAX_SOURCE_BYTES, 10 * 1048576)
        self.assertEqual(MAX_REDIRECTS, 3)

    def test_only_two_fixed_https_urls_are_accepted(self):
        for url in FIXED_GOVINFO_URLS.values():
            self.assertEqual(_require_fixed_govinfo_url(url), url)
        rejected = [
            "http://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf",
            "https://evil.example/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf",
            "https://www.govinfo.gov/content/pkg/LSA-2023-11/pdf/LSA-2023-11.pdf",
            "https://user:pw@www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf",
            FIXED_GOVINFO_URLS["2023-12"] + "?download=1",
            "file:///tmp/LSA-2023-12.pdf",
            "https://www.govinfo.gov:444/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf",
        ]
        for url in rejected:
            with self.assertRaises(LSAComparisonError):
                _require_fixed_govinfo_url(url)

    def test_redirect_must_stay_on_the_requested_url(self):
        handler = _GovInfoRedirects()
        self.assertEqual(handler.max_redirections, MAX_REDIRECTS)
        request = Request(FIXED_GOVINFO_URLS["2023-12"])
        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, FIXED_GOVINFO_URLS["2023-12"]
        )
        self.assertEqual(redirected.full_url, FIXED_GOVINFO_URLS["2023-12"])
        for target in (
            FIXED_GOVINFO_URLS["2024-01"],
            "https://evil.example/LSA.pdf",
            "http://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf",
            "https://www.govinfo.gov/other.pdf",
        ):
            with self.assertRaises(LSAComparisonError):
                handler.redirect_request(request, None, 302, "Found", {}, target)
        with self.assertRaises(LSAComparisonError):
            handler.redirect_request(request, None, 306, "Unused", {}, FIXED_GOVINFO_URLS["2023-12"])

    def test_default_call_does_not_build_an_opener(self):
        def boom(*args, **kwargs):
            raise AssertionError("network opener built")

        original = lsa_compare.build_opener
        lsa_compare.build_opener = boom
        try:
            with self.assertRaisesRegex(LSAComparisonError, "opt-in"):
                compare_official_lsa()
        finally:
            lsa_compare.build_opener = original

    def test_allow_network_uses_the_restricted_opener(self):
        seen = []

        class Director:
            def open(self, request, timeout):
                seen.append((request.full_url, timeout))
                return Response(SYNTHETIC_PDF)

        def fake_build_opener(*handlers):
            self.assertEqual(len(handlers), 1)
            self.assertIsInstance(handlers[0], _GovInfoRedirects)
            self.assertEqual(handlers[0].max_redirections, MAX_REDIRECTS)
            return Director()

        original = lsa_compare.build_opener
        lsa_compare.build_opener = fake_build_opener
        try:
            report = compare_official_lsa(reader_factory=reader_factory, allow_network=True)
        finally:
            lsa_compare.build_opener = original
        self.assertEqual(seen, [(url, TIMEOUT_SECONDS) for url in FIXED_GOVINFO_URLS.values()])
        self.assertEqual(report["legal_effect_on_study_date"], "NOT_DETERMINED")

    def test_cli_without_fetch_does_not_open_network(self):
        def boom(*args, **kwargs):
            raise AssertionError("network opener built")

        original = lsa_compare.build_opener
        lsa_compare.build_opener = boom
        try:
            with tempfile.TemporaryDirectory() as folder:
                dest = Path(folder) / "audit.json"
                with contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        lsa_compare.main(["--out", str(dest)])
                self.assertEqual(raised.exception.code, 2)
                self.assertFalse(dest.exists())
        finally:
            lsa_compare.build_opener = original

    def test_save_without_opt_in_writes_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "audit.json"
            with self.assertRaisesRegex(LSAComparisonError, "opt-in"):
                save_report(dest)
            self.assertFalse(dest.exists())
            self.assertFalse(Path(str(dest) + ".partial").exists())

    def test_save_report_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            dest = Path(folder) / "audit.json"
            report = save_report(dest, opener, reader_factory)
            self.assertEqual(json.loads(dest.read_text())["documents"].keys(), report["documents"].keys())
            self.assertEqual(json.loads(dest.read_text())["rights_status"], "review_required")
            with self.assertRaisesRegex(LSAComparisonError, "new"):
                save_report(dest, opener, reader_factory)

    def test_module_does_not_join_ais_or_add_a_console_script(self):
        source = Path(lsa_compare.__file__).read_text(encoding="utf-8")
        self.assertNotIn("harborlens.ais", source)
        self.assertNotIn("mmsi", source.lower())
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotIn("lsa_compare", pyproject)
        self.assertNotIn("lsa_compare", (ROOT / "src" / "harborlens" / "cli.py").read_text(encoding="utf-8"))
        self.assertNotIn("lsa_compare", (ROOT / "src" / "harborlens" / "__init__.py").read_text(encoding="utf-8"))
        self.assertFalse(REMOVED_WORKFLOW.exists())


if __name__ == "__main__":
    unittest.main()
