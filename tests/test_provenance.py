"""Synthetic file-integrity tests, not validation of maritime events."""
import tempfile
import unittest
from pathlib import Path
from harborlens.ais import run
from harborlens.io_safe import AISInputError
from harborlens.provenance import digests_equal, require_declared_source_url, verify_manifest

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
        ):
            with self.subTest(url=rejected):
                with self.assertRaises(AISInputError) as caught:
                    run(FIXTURE, self.out, source_url=rejected)
                self.assertIn("must name a host", str(caught.exception))
                self.assertNotIn("Traceback", str(caught.exception))
                self.assertFalse(self.out.exists())

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
