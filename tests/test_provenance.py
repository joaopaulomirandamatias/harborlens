"""Synthetic file-integrity tests, not validation of maritime events."""
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlsplit
from harborlens.ais import run
from harborlens.io_safe import AISInputError
from harborlens.provenance import (
    _SOURCE_URL_IGNORABLE, _SOURCE_URL_IGNORABLE_RANGES, digests_equal,
    require_declared_source_url, verify_manifest,
)

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_ais.csv"

class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.out = Path(self.temp.name) / "out"

    def tearDown(self):
        self.temp.cleanup()

    def test_deterministic_provenance(self):
        first = run(FIXTURE, self.out)
        self.assertEqual(first["source_metadata"]["rights_status"], "review_required")
        self.assertTrue(verify_manifest(self.out / "manifest.json")["ok"])
        second = run(FIXTURE, self.out)
        self.assertEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["artifacts"], second["artifacts"])

    def test_detects_tampering(self):
        run(FIXTURE, self.out)
        with (self.out / "stationary_candidates.csv").open("a") as target:
            target.write("tampered,data\\n")
        check = verify_manifest(self.out / "manifest.json")
        self.assertFalse(check["ok"])
        self.assertEqual(check["artifacts"]["stationary_candidates.csv"], "mismatch")

    def test_rejects_non_http_source(self):
        with self.assertRaises(AISInputError) as caught:
            run(FIXTURE, self.out, source_url="file:///private/archive")
        self.assertIn("must name a host", str(caught.exception))
        self.assertFalse(self.out.exists())

    def test_source_url_accepts_http_and_rejects_empty_host_and_credentials(self):
        require_declared_source_url(None)
        for accepted in (
            "http://example.org",
            "https://example.org/ais.csv",
            "HTTP://example.org",
            "http://example.org:443/path?q=1",
            "http://example.org:1",
            "http://example.org:65535",
            "http://example.org:",
            "http://[::1]:443",
            "http://[::1]:65535",
            "http://example.org/path?tokenizer=1",
            "http://example.org/path?q=token",
            "http://example.org/path?keys=1",
            "http://example.org/path?apikeys=1",
            "http://example.org/path;token=example",
            "http://example.org/path#/token=example",
            "http://example.org/a\u0301",
            "http://example.org/path?q=1;note=plain",
            "http://example.org/path?x-goog-api=1",
            "http://example.org/path?%252574oken=example",
        ):
            with self.subTest(url=accepted):
                require_declared_source_url(accepted)
        for rejected in (
            "ftp://x",
            "",
            "   ",
            "http://",
            "https:///",
            "https://user@example.org",
            "https://user:secret@example.org",
            "http://[::1",
            "http://[",
            "http://example.org\t/ais.csv",
            "http://example.org\n",
            "http://example.org\r/x",
            "http://ex ample.org",
            "http://example.org/path with space",
            "http://example.org\u00a0",
            "http://example.org\u2028",
            "http://exam\x1bple.org",
            "http://example.org\x7f",
            "http://example.org\x80",
            "http://example.org:abc",
            "http://example.org:65536",
            "http://example.org:99999999",
            "http://example.org:-1",
            "http://[::1]:abc",
            "http://[::1]:99999999",
            "http://example.org:0",
            "http://example.org:00",
            "http://example.org/path?token=example",
            "http://example.org/path?Token=example",
            "http://example.org/path?access_token=example",
            "http://example.org/path?api_key=example",
            "http://example.org/path?secret=example",
            "http://example.org/path?password=example",
            "http://example.org/path?sig=example",
            "http://example.org/path?signature=example",
            "http://example.org/path?auth=example",
            "http://example.org/path?x-amz-signature=example",
            "http://example.org/path?x_amz_signature=example",
            "http://example.org/path?X-Amz-Security-Token=example",
            "http://example.org/path?%74oken=example",
            "http://example.org/path?%2574oken=example",
            "http://example.org/path#access_token=example",
            "http://example.org/path?client_secret=example",
            "http://example.org/path?Client_Secret=example",
            "http://example.org/path?apikey=example",
            "http://example.org/path?API-KEY=example",
            "http://example.org/path?private_token=example",
            "http://example.org/path?id_token=example",
            "http://example.org/path?refresh_token=example",
            "http://example.org/path?key=example",
            "http://example.org/path?passwd=example",
            "http://example.org/path?pwd=example",
            "http://example.org/path?authorization=example",
            "http://example.org/path?session=example",
            "http://example.org/path?jwt=example",
            "http://example.org/path?x-goog-signature=example",
            "http://example.org/path?X-Goog-Credential=example",
            "http://example.org/path?access-token=example",
            "http://example.org/path?access_key=sekrit-value",
            "http://example.org/path?secret-key=sekrit-value",
            "http://example.org/path?api_token=sekrit-value",
            "http://example.org/path?session_id=sekrit-value",
            "http://example.org/path?x-api-key=sekrit-value",
            "http://example.org/path?oauth_token=sekrit-value",
            "http://example.org/path?private_key=sekrit-value",
            "http://example.org/path?csrf=sekrit-value",
            "http://example.org/path?key=sekrit-value",
            "http://example.org/path?q=1;token=example",
            "http://example.org/path#q=1;jwt=example",
            "http://example.org/\u202e",
            "http://example.org/\u200b",
            "http://example.org/\ufeff",
            "http://example.org/\ufe0f",
            "http://ex\ufe0fample.org",
            "http://example.org/\ufe00",
            "http://example.org/\U000e0100",
            "http://example.org/\u180b",
            "http://example.org/\u034f",
        ):
            with self.subTest(url=rejected):
                with self.assertRaises(AISInputError) as caught:
                    run(FIXTURE, self.out, source_url=rejected)
                message = str(caught.exception)
                self.assertIn("must name a host", message)
                self.assertNotIn("Traceback", message)
                if "sekrit-value" in rejected:
                    self.assertIn("parameter '", message)
                    self.assertNotIn("sekrit-value", message)
                if rejected:
                    self.assertNotIn(rejected, message)
                self.assertNotIn("sekrit-value", message)
                self.assertFalse(self.out.exists())

    def test_source_url_ignorable_set_is_the_named_ranges(self):
        import unicodedata
        expected = set()
        for start, end in _SOURCE_URL_IGNORABLE_RANGES:
            expected.update(chr(code) for code in range(start, end + 1))
        self.assertEqual(_SOURCE_URL_IGNORABLE, frozenset(expected))
        for character in (
            "\u115f", "\u1160", "\u3164", "\uffa0", "\u17b4", "\u17b5", "\u2800",
            "\ufe0f", "\ufe00", "\U000e0100", "\U000e01ef", "\u180b", "\u180f",
            "\u034f", "\u2065",
        ):
            self.assertIn(character, _SOURCE_URL_IGNORABLE)
        # Combining marks in general stay accepted. U+0300 and U+0301 are Mn
        # and are not default-ignorable.
        self.assertNotIn("\u0300", _SOURCE_URL_IGNORABLE)
        self.assertNotIn("\u0301", _SOURCE_URL_IGNORABLE)
        self.assertEqual(unicodedata.category("\u0300"), "Mn")
        self.assertEqual(unicodedata.category("\u0301"), "Mn")
        named_mn = set(range(0x034F, 0x0350))
        named_mn.update(range(0x17B4, 0x17B6))
        named_mn.update(range(0x180B, 0x1810))
        named_mn.update(range(0xFE00, 0xFE10))
        named_mn.update(range(0xE0100, 0xE01F0))
        for character in _SOURCE_URL_IGNORABLE:
            if unicodedata.category(character) == "Mn":
                self.assertIn(ord(character), named_mn)

    def test_non_cf_default_ignorables_are_in_the_fixed_set(self):
        """Unicode 15.0.0 Default_Ignorable code points are rejected.

        Category Cc and Cf are rejected by the category check, so they are
        not repeated in the frozenset. Every other code point in this frozen
        list, plus the braille blank U+2800, is in the set. A new non-Cf
        default-ignorable has to be added to both lists.
        """
        import unicodedata
        # Unicode 15.0.0 DerivedCoreProperties Default_Ignorable_Code_Point.
        frozen = (
            (0x00AD, 0x00AD), (0x034F, 0x034F), (0x061C, 0x061C),
            (0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
            (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x206F),
            (0x3164, 0x3164), (0xFE00, 0xFE0F), (0xFEFF, 0xFEFF),
            (0xFFA0, 0xFFA0), (0xFFF0, 0xFFF8), (0x1BCA0, 0x1BCA3),
            (0x1D173, 0x1D17A), (0xE0000, 0xE001F), (0xE0020, 0xE007F),
            (0xE0080, 0xE00FF), (0xE0100, 0xE0FFF),
        )
        missing = []
        for start, end in frozen:
            for code in range(start, end + 1):
                character = chr(code)
                if character in _SOURCE_URL_IGNORABLE:
                    continue
                if unicodedata.category(character) in {"Cc", "Cf"}:
                    continue
                missing.append(f"U+{code:04X}")
        self.assertEqual(missing, [])
        self.assertIn("\u2800", _SOURCE_URL_IGNORABLE)
        require_declared_source_url("http://example.org/a\u0300")
        require_declared_source_url("http://example.org/a\u0301")
        for character in ("\u115f", "\u2800", "\u3164", "\uffa0"):
            with self.assertRaises(AISInputError):
                require_declared_source_url(f"http://example.org/{character}")

    def test_whitespace_is_rejected_before_urlsplit_strips_it(self):
        raw = "http://example.org\t/ais.csv"
        parsed = urlsplit(raw)
        self.assertEqual(parsed.hostname, "example.org")
        self.assertEqual(parsed.path, "/ais.csv")
        with self.assertRaises(AISInputError) as caught:
            require_declared_source_url(raw)
        self.assertNotIn("\t", str(caught.exception))
        self.assertNotIn(raw, str(caught.exception))
        spaced = "http://ex ample.org"
        self.assertIn(" ", urlsplit(spaced).hostname)
        with self.assertRaises(AISInputError):
            require_declared_source_url(spaced)

    def test_invalid_source_url_does_not_replace_an_existing_directory(self):
        self.out.mkdir()
        marker = self.out / "keep.txt"
        marker.write_text("previous", encoding="utf-8")
        with self.assertRaises(AISInputError):
            run(FIXTURE, self.out, source_url="ftp://x")
        self.assertEqual(marker.read_text(encoding="utf-8"), "previous")
        self.assertFalse((self.out / "houston_clean.csv").exists())
        self.assertFalse((self.out / "manifest.json").exists())

    def test_digests_equal_normalizes_hex_and_rejects_a_mismatch(self):
        pin = "ab" * 32
        self.assertTrue(digests_equal(pin.upper(), pin))
        self.assertFalse(digests_equal(pin, "ac" + pin[2:]))
        self.assertFalse(digests_equal(pin, None))
        self.assertFalse(digests_equal(pin.encode(), pin))
        self.assertTrue(digests_equal(b"\x00\x01", bytearray(b"\x00\x01")))
        self.assertFalse(digests_equal(b"\x00\x01", b"\x00\x02"))

    def test_preloaded_artifact_is_not_opened_again(self):
        run(FIXTURE, self.out)
        cleaned = self.out / "houston_clean.csv"
        raw = cleaned.read_bytes()
        opens = []
        real_open = Path.open

        def counting_open(self_path, *args, **kwargs):
            if self_path.name == "houston_clean.csv":
                opens.append(self_path)
            return real_open(self_path, *args, **kwargs)

        from unittest import mock
        with mock.patch.object(Path, "open", counting_open):
            check = verify_manifest(
                self.out / "manifest.json", preloaded={"houston_clean.csv": raw}
            )
        self.assertTrue(check["ok"])
        self.assertEqual(opens, [])
        self.assertEqual(check["artifacts"]["houston_clean.csv"], "verified")

    def test_source_url_is_never_preapproved(self):
        result = run(FIXTURE, self.out, source_url="https://example.org/ais.csv")
        self.assertEqual(result["source_metadata"]["source_url"], "https://example.org/ais.csv")
        self.assertEqual(result["source_metadata"]["metadata_origin"], "user_declared")
        self.assertEqual(result["source_metadata"]["rights_status"], "review_required")
