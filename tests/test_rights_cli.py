"""Offline CLI contract smoke checks, without real source data or network."""
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from unittest.mock import patch

from harborlens.rights import APPROVED_STATUSES, _MISSING_JSONSCHEMA, _NOTICE, main


ROOT = Path(__file__).resolve().parents[1]
_DECISION_KEYS = {"dataset_version", "notice", "purpose", "rights_status", "source_id"}


def _reviewed_register():
    return {
        "schema_version": 1,
        "sources": [{
            "source_id": "noaa_pmel_erddap",
            "dataset_version": "AIS2024_AIS",
            "source_url": "https://example.org/source",
            "terms_url": "https://example.org/terms",
            "rights_status": "reviewed_public_domain_attribution_required",
            "decision": "reviewed",
            "permitted_uses": {
                "research": "allowed",
                "public_aggregates": "allowed",
                "commercial": "prohibited",
            },
            "attribution": "Source agency and dataset.",
            "reviewed_by": "Independent reviewer",
            "reviewed_at_utc": "2026-11-09T12:00:00Z",
            "terms_sha256": "a" * 64,
            "evidence_url": "https://example.org/review",
            "review_note": "Synthetic review record; not a real source approval.",
        }],
    }


class RightsCLITests(unittest.TestCase):
    def _invoke(self, args):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = main(args)
        result = json.loads(out.getvalue())
        return code, result

    def test_source_rights_are_pending_in_checked_in_registry(self):
        code, result = self._invoke([
            "--register", str(ROOT / "docs/data/rights-register.json"),
            "--source-id", "noaa_pmel_erddap",
            "--dataset-version", "AIS2024_AIS",
            "--purpose", "commercial",
        ])
        self.assertEqual(code, 1)
        self.assertEqual(result["rights_status"], "review_required")
        self.assertEqual(result["purpose"], "commercial")
        self.assertEqual(set(result), _DECISION_KEYS)

    def test_version_mismatch_does_not_upgrade_rights(self):
        code, result = self._invoke([
            "--register", str(ROOT / "docs/data/rights-register.json"),
            "--source-id", "usace_ntad_navigation_facilities",
            "--dataset-version", "2024-01-02",
        ])
        self.assertEqual(code, 1)
        self.assertEqual(result["rights_status"], "review_required")
        self.assertNotIn("error", result)

    def test_exit_codes_and_json_shape(self):
        register = ROOT / "docs/data/rights-register.json"
        pending_code, pending = self._invoke([
            "--register", str(register),
            "--source-id", "noaa_pmel_erddap",
            "--dataset-version", "AIS2024_AIS",
            "--purpose", "research",
        ])
        self.assertEqual(pending_code, 1)
        self.assertEqual(pending["rights_status"], "review_required")
        self.assertEqual(set(pending), _DECISION_KEYS)
        self.assertEqual(pending["notice"], _NOTICE)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rights.json"
            path.write_text(json.dumps(_reviewed_register()), encoding="utf-8")
            approved_code, approved = self._invoke([
                "--register", str(path),
                "--source-id", "noaa_pmel_erddap",
                "--dataset-version", "AIS2024_AIS",
                "--purpose", "research",
            ])
            self.assertEqual(approved_code, 0)
            self.assertIn(approved["rights_status"], APPROVED_STATUSES)
            self.assertEqual(set(approved), _DECISION_KEYS)

            restricted_code, restricted = self._invoke([
                "--register", str(path),
                "--source-id", "noaa_pmel_erddap",
                "--dataset-version", "AIS2024_AIS",
                "--purpose", "commercial",
            ])
            self.assertEqual(restricted_code, 1)
            self.assertEqual(restricted["rights_status"], "use_restricted")
            self.assertNotIn("error", restricted)

            broken = json.loads(path.read_text(encoding="utf-8"))
            broken["sources"][0]["unexpected_field"] = "schema-invalid with full evidence"
            path.write_text(json.dumps(broken), encoding="utf-8")
            invalid_code, invalid = self._invoke([
                "--register", str(path),
                "--source-id", "noaa_pmel_erddap",
                "--dataset-version", "AIS2024_AIS",
                "--purpose", "research",
            ])
            self.assertEqual(invalid_code, 2)
            self.assertEqual(invalid["rights_status"], "review_required")
            self.assertEqual(invalid["error"], "Rights register failed schema validation")
            self.assertEqual(set(invalid), _DECISION_KEYS | {"error"})
            self.assertNotIn(invalid["rights_status"], APPROVED_STATUSES)

            path.write_text("{", encoding="utf-8")
            parse_code, parsed = self._invoke([
                "--register", str(path),
                "--source-id", "noaa_pmel_erddap",
                "--dataset-version", "AIS2024_AIS",
            ])
            self.assertEqual(parse_code, 2)
            self.assertEqual(parsed["error"], "Rights register is unreadable")
            self.assertEqual(parsed["rights_status"], "review_required")
            self.assertIn("error", parsed)

        missing_code, missing = self._invoke([
            "--register", str(ROOT / "docs/data/does-not-exist-rights.json"),
            "--source-id", "noaa_pmel_erddap",
            "--dataset-version", "AIS2024_AIS",
        ])
        self.assertEqual(missing_code, 2)
        self.assertEqual(missing["error"], "Missing or excessive rights register")
        self.assertEqual(missing["rights_status"], "review_required")
        self.assertNotEqual(missing, pending)

    def test_process_exit_codes(self):
        """python -m harborlens.rights must propagate 0, 1 and 2."""
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rights.json"
            path.write_text(json.dumps(_reviewed_register()), encoding="utf-8")
            cases = (
                (0, [str(path), "noaa_pmel_erddap", "AIS2024_AIS", "research"]),
                (1, [str(path), "noaa_pmel_erddap", "AIS2024_AIS", "commercial"]),
                (1, [str(ROOT / "docs/data/rights-register.json"),
                     "noaa_pmel_erddap", "AIS2024_AIS", "research"]),
            )
            for expected, args in cases:
                completed = subprocess.run(
                    [sys.executable, "-m", "harborlens.rights",
                     "--register", args[0], "--source-id", args[1],
                     "--dataset-version", args[2], "--purpose", args[3]],
                    capture_output=True, text=True, check=False,
                )
                self.assertEqual(completed.returncode, expected, completed.stdout)
                payload = json.loads(completed.stdout)
                self.assertNotIn("error", payload)
                if expected == 0:
                    self.assertIn(payload["rights_status"], APPROVED_STATUSES)
                else:
                    self.assertNotIn(payload["rights_status"], APPROVED_STATUSES)

            path.write_text("{", encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, "-m", "harborlens.rights",
                 "--register", str(path), "--source-id", "noaa_pmel_erddap",
                 "--dataset-version", "AIS2024_AIS"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(completed.returncode, 2, completed.stderr)
            payload = json.loads(completed.stdout)
            self.assertEqual(payload["error"], "Rights register is unreadable")
            self.assertEqual(payload["rights_status"], "review_required")

    def test_missing_jsonschema_error_names_rights_extra(self):
        with patch("harborlens.rights._load_jsonschema", side_effect=ImportError("blocked")):
            code, result = self._invoke([
                "--register", str(ROOT / "docs/data/rights-register.json"),
                "--source-id", "noaa_pmel_erddap",
                "--dataset-version", "AIS2024_AIS",
                "--purpose", "research",
            ])
        self.assertEqual(code, 2)
        self.assertEqual(result["error"], _MISSING_JSONSCHEMA)
        self.assertIn("pip install 'harborlens[rights]'", result["error"])
        self.assertEqual(result["rights_status"], "review_required")
        self.assertNotIn(result["rights_status"], APPROVED_STATUSES)


if __name__ == "__main__":
    unittest.main()
