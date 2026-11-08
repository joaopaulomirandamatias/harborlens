"""Synthetic file-integrity tests, not validation of maritime events."""
import tempfile
import unittest
from pathlib import Path
from harborlens.ais import run
from harborlens.provenance import verify_manifest

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
        with self.assertRaisesRegex(ValueError, "HTTP"):
            run(FIXTURE, self.out, source_url="file:///private/archive")

    def test_source_url_is_never_preapproved(self):
        result = run(FIXTURE, self.out, source_url="https://example.org/ais.csv")
        self.assertEqual(result["source_metadata"]["source_url"], "https://example.org/ais.csv")
        self.assertEqual(result["source_metadata"]["metadata_origin"], "user_declared")
        self.assertEqual(result["source_metadata"]["rights_status"], "review_required")
