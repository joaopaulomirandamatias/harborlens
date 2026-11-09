"""Independent, offline signed-release verification with synthetic-only fixtures."""
import base64
import contextlib
import hashlib
import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from harborlens.release_verify import (
    ReleaseVerificationError, WARNING, main, verify_release,
)
from harborlens.review_signatures import public_key_fingerprint, review_message


def sha(value):
    return hashlib.sha256(value).hexdigest()


def canonical_digest(obj):
    return sha((json.dumps(obj, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True) + "\n").encode("ascii"))


class IndependentReleaseVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.out = self.root / "aggregate-release.json"
        self.registry = self.root / "rights.json"
        self.public = self.root / "reviewer.pem"
        self.private = Ed25519PrivateKey.generate()  # synthetic only
        self.public.write_bytes(self.private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        _, self.key_sha = public_key_fingerprint(self.public)
        self.source_id = "noaa_pmel_erddap"
        self.version = "AIS2024_AIS"
        self.purpose = "public_aggregates"
        self.rights_record = {
            "schema_version": 1,
            "sources": [{
                "source_id": self.source_id,
                "dataset_version": self.version,
                "decision": "reviewed",
                "rights_status": "reviewed_public_domain_attribution_required",
                "reviewed_by": "Synthetic test reviewer",
                "reviewed_at_utc": "2026-11-09T12:00:00Z",
                "terms_url": "https://example.invalid/terms",
                "evidence_url": "https://example.invalid/evidence",
                "terms_sha256": "c" * 64,
                "attribution": "Synthetic data only",
                "permitted_uses": {
                    "research": "allowed",
                    "public_aggregates": "allowed",
                    "commercial": "prohibited",
                },
            }],
        }
        self._write_registry()
        self.summary = {
            "schema_version": "public-summary-v0.1",
            "research_status": "unvalidated_stationary_candidates",
            "purpose": self.purpose,
            "method_version": "stationary-v0.2",
            "run_id": "a" * 64,
            "run_manifest_sha256": "b" * 64,
            "acquisition_sha256": "d" * 64,
            "source_id": self.source_id,
            "dataset_version": self.version,
            "rights_registry_sha256": self.registry_sha,
            "rights_status": "reviewed_public_domain_attribution_required",
            "counts": {
                "observations_scanned": 140,
                "observations_retained": 120,
                "unique_mmsi_groups": 12,
                "unvalidated_stationary_candidates": 3,
            },
            "warning": WARNING,
        }
        self.review = {}
        self._sign_and_write()

    def tearDown(self):
        self.temp.cleanup()

    def _write_registry(self):
        self.registry.write_text(json.dumps(self.rights_record), encoding="utf-8")
        self.registry_sha = sha(self.registry.read_bytes())

    def _sign_and_write(self):
        digest = canonical_digest(self.summary)
        self.review = {
            "schema_version": 1,
            "decision": "approved",
            "summary_sha256": digest,
            "purpose": self.summary["purpose"],
            "reviewer_id": "synthetic-reviewer",
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "privacy_reviewed": True,
            "source_rights_reviewed": True,
            "scientific_limitations_reviewed": True,
            "conditions_reviewed": False,
            "signature_algorithm": "Ed25519",
            "public_key_sha256": self.key_sha,
            "signature_b64": "",
        }
        self._write_signed()

    def _write_signed(self):
        self.review["signature_b64"] = ""
        self.review["signature_b64"] = base64.b64encode(
            self.private.sign(review_message(self.review))
        ).decode("ascii")
        self._write_document()

    def _write_document(self):
        body = {
            "summary": self.summary,
            "summary_sha256": canonical_digest(self.summary),
            "release_review": self.review,
        }
        self.out.write_text(json.dumps(body, indent=2), encoding="utf-8")

    def verify(self, **overrides):
        args = {
            "rights_register": self.registry,
            "expected_rights_register_sha256": self.registry_sha,
            "trusted_public_key": self.public,
            "expected_public_key_sha256": self.key_sha,
            "expected_reviewer_id": "synthetic-reviewer",
            "expected_purpose": self.purpose,
            "expected_source_id": self.source_id,
            "expected_dataset_version": self.version,
            "expected_run_id": "a" * 64,
            "expected_summary_sha256": canonical_digest(self.summary),
        }
        args.update(overrides)
        return verify_release(self.out, **args)

    def test_valid_signed_release_is_verified_without_ais_files(self):
        result = self.verify()
        self.assertTrue(result["verified"])
        self.assertEqual(result["summary_sha256"], canonical_digest(self.summary))
        self.assertEqual(result["release_sha256"], sha(self.out.read_bytes()))
        self.assertEqual(result["verification_scope"], "signed_release_and_pinned_rights_only")
        self.assertIn("unverified", result["caveat"])
        self.assertEqual(list(self.root.glob("*.csv")), [])

    def test_cli_verifies_without_writing_any_file(self):
        args = [
            "--release", str(self.out),
            "--rights-register", str(self.registry),
            "--expected-rights-register-sha256", self.registry_sha,
            "--trusted-reviewer-key", str(self.public),
            "--trusted-reviewer-key-sha256", self.key_sha,
            "--trusted-reviewer-id", "synthetic-reviewer",
            "--purpose", self.purpose,
            "--source-id", self.source_id,
            "--dataset-version", self.version,
            "--run-id", "a" * 64,
            "--expected-summary-sha256", canonical_digest(self.summary),
        ]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            main(args)
        self.assertTrue(json.loads(output.getvalue())["verified"])
        self.assertEqual(len(list(self.root.iterdir())), 3)

    def test_summary_cannot_be_changed_even_with_updated_unsigned_digest(self):
        self.summary["counts"]["observations_scanned"] = 999
        self._write_document()
        with self.assertRaisesRegex(ReleaseVerificationError, "approval"):
            # A changed summary hash does not change the signed review.
            self.verify(expected_summary_sha256=None)

    def test_source_scope_and_purpose_cannot_be_substituted(self):
        with self.assertRaisesRegex(ReleaseVerificationError, "scope"):
            self.verify(expected_source_id="noaa_ocm_ais_daily")
        with self.assertRaisesRegex(ReleaseVerificationError, "scope"):
            self.verify(expected_purpose="commercial")
        with self.assertRaisesRegex(ReleaseVerificationError, "scope"):
            self.verify(expected_dataset_version="AIS2023_AIS")
        with self.assertRaisesRegex(ReleaseVerificationError, "Run ID"):
            self.verify(expected_run_id="e" * 64)

    def test_wrong_signature_or_key_cannot_pass(self):
        self.review["scientific_limitations_reviewed"] = False
        self._write_document()
        with self.assertRaises(ReleaseVerificationError):
            self.verify()
        self.review["scientific_limitations_reviewed"] = True
        self.review["conditions_reviewed"] = True  # otherwise valid, but unsigned edit
        self._write_document()
        with self.assertRaisesRegex(ReleaseVerificationError, "signature"):
            self.verify()
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "signature"):
            self.verify(expected_public_key_sha256="f" * 64)
        with self.assertRaisesRegex(ReleaseVerificationError, "signature"):
            self.verify(expected_reviewer_id="attacker")

    def test_untrusted_rights_registry_fails_even_if_report_is_signed(self):
        with self.assertRaisesRegex(ReleaseVerificationError, "rights"):
            self.verify(expected_rights_register_sha256="f" * 64)
        self.rights_record["sources"][0]["decision"] = "pending"
        self._write_registry()
        with self.assertRaisesRegex(ReleaseVerificationError, "rights"):
            self.verify()
        self.summary["rights_registry_sha256"] = self.registry_sha
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "rights"):
            self.verify()

    def test_prohibited_commercial_reuse_is_not_verifiable(self):
        self.purpose = "commercial"
        self.summary["purpose"] = "commercial"
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "rights"):
            self.verify()

    def test_conditioned_rights_require_explicit_attestation(self):
        self.rights_record["sources"][0]["rights_status"] = "reviewed_permitted_with_conditions"
        self._write_registry()
        self.summary["rights_registry_sha256"] = self.registry_sha
        self.summary["rights_status"] = "reviewed_permitted_with_conditions"
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "Conditions"):
            self.verify()
        self.review["conditions_reviewed"] = True
        self._write_signed()
        self.assertTrue(self.verify()["verified"])

    def test_unsigned_duplicate_keys_and_extra_raw_data_are_rejected(self):
        self.review.pop("signature_b64")
        self._write_document()
        with self.assertRaisesRegex(ReleaseVerificationError, "review"):
            self.verify()
        self._sign_and_write()
        self.out.write_text('{"summary":{}, "summary":{}, "summary_sha256":"a","release_review":{}}')
        with self.assertRaisesRegex(ReleaseVerificationError, "Duplicate keys"):
            self.verify()
        self._write_document()
        self.summary["raw_ais"] = ["367800001", "-95.20"]
        self._write_document()
        with self.assertRaisesRegex(ReleaseVerificationError, "unapproved"):
            self.verify()

    def test_nonfinite_json_boolean_counts_and_small_cohorts_rejected(self):
        self.out.write_text('{"summary":NaN,"summary_sha256":"a","release_review":{}}')
        with self.assertRaisesRegex(ReleaseVerificationError, "Non-finite"):
            self.verify()
        self.summary["counts"]["observations_scanned"] = True
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "nonnegative"):
            self.verify()
        self.summary["counts"]["observations_scanned"] = 140
        self.summary["counts"]["unique_mmsi_groups"] = 1
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "aggregate"):
            self.verify()

    def test_stale_review_fails_even_with_valid_signature(self):
        self.review["reviewed_at_utc"] = (
            datetime.now(timezone.utc) - timedelta(days=31)
        ).isoformat().replace("+00:00", "Z")
        self._write_signed()
        with self.assertRaisesRegex(ReleaseVerificationError, "stale"):
            self.verify()

    def test_malformed_file_and_untrusted_summary_rejected(self):
        self.out.write_bytes(b"x" * (128 * 1024 + 1))
        with self.assertRaisesRegex(ReleaseVerificationError, "bounded size"):
            self.verify()
        self._write_document()
        self.summary["warning"] = "Confirmed port call"
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "labels"):
            self.verify()

    def test_archive_vintage_must_be_output_hash_bound(self):
        self.source_id = "noaa_ocm_ais_daily"
        self.version = "2024"
        self.summary["source_id"] = self.source_id
        self.summary["dataset_version"] = self.version
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "vintage"):
            self.verify()

    def test_unrecognized_segmentation_version_is_not_accepted(self):
        self.summary["method_version"] = "stationary-v999"
        self._sign_and_write()
        with self.assertRaisesRegex(ReleaseVerificationError, "labels"):
            self.verify()

    def test_release_review_schemas_match_fixture(self):
        from jsonschema import Draft202012Validator
        root = Path(__file__).resolve().parents[1]
        review_schema = json.loads(
            (root / "schemas/v1/publication-review.schema.json").read_text()
        )
        release_schema = json.loads(
            (root / "schemas/v1/public-summary.schema.json").read_text()
        )
        Draft202012Validator(review_schema).validate(self.review)
        Draft202012Validator(release_schema).validate(
            json.loads(self.out.read_text(encoding="utf-8"))
        )

    def test_verification_result_matches_versioned_contract(self):
        from jsonschema import Draft202012Validator
        root = Path(__file__).resolve().parents[1]
        schema = json.loads(
            (root / "schemas/v1/release-verification-result.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(self.verify())



if __name__ == "__main__":
    unittest.main()
