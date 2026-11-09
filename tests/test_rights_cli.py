"""Offline CLI contract smoke checks, without real source data or network."""
import contextlib
import io
import json
import unittest
from pathlib import Path

from harborlens.rights import main


ROOT = Path(__file__).resolve().parents[1]


class RightsCLITests(unittest.TestCase):
    def test_source_rights_are_pending_in_checked_in_registry(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([
                "--register", str(ROOT / "docs/data/rights-register.json"),
                "--source-id", "noaa_pmel_erddap",
                "--dataset-version", "AIS2024_AIS",
                "--purpose", "commercial",
            ])
        result = json.loads(out.getvalue())
        self.assertEqual(result["rights_status"], "review_required")
        self.assertEqual(result["purpose"], "commercial")

    def test_version_mismatch_does_not_upgrade_rights(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            main([
                "--register", str(ROOT / "docs/data/rights-register.json"),
                "--source-id", "usace_ntad_navigation_facilities",
                "--dataset-version", "2024-01-02",
            ])
        self.assertEqual(json.loads(out.getvalue())["rights_status"], "review_required")


if __name__ == "__main__":
    unittest.main()
