"""Offline, synthetic Ed25519 reviewer trust tests (SPEC-003).

No production secrets or trust roots live in this repository.
"""
import base64
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from harborlens.review_signatures import (
    ReviewSignatureError, public_key_fingerprint, review_message,
    verify_review_signature,
)


class SignedReviewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.private = Ed25519PrivateKey.generate()
        self.public = self.root / "approved-reviewer.pem"
        self.public.write_bytes(self.private.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        _, self.fingerprint = public_key_fingerprint(self.public)
        self.review = {
            "signature_algorithm": "Ed25519",
            "public_key_sha256": self.fingerprint,
            "reviewer_id": "approved-reviewer",
            "summary_sha256": "a" * 64,
            "purpose": "public_aggregates",
            "decision": "approved",
            "signature_b64": "",
        }
        self.sign()

    def tearDown(self):
        self.temp.cleanup()

    def sign(self):
        self.review["signature_b64"] = ""
        self.review["signature_b64"] = base64.b64encode(
            self.private.sign(review_message(self.review))
        ).decode("ascii")

    def verify(self, **kwargs):
        arguments = {
            "trusted_public_key": self.public,
            "expected_public_key_sha256": self.fingerprint,
            "expected_reviewer_id": "approved-reviewer",
        }
        arguments.update(kwargs)
        return verify_review_signature(self.review, **arguments)

    def test_pinned_key_and_identity_verify(self):
        self.assertEqual(self.verify(), self.fingerprint)

    def test_any_signed_field_change_fails(self):
        self.review["purpose"] = "commercial"
        with self.assertRaisesRegex(ReviewSignatureError, "signature"):
            self.verify()

    def test_wrong_reviewer_identity_is_denied(self):
        with self.assertRaisesRegex(ReviewSignatureError, "identity"):
            self.verify(expected_reviewer_id="attacker")

    def test_wrong_pinned_fingerprint_is_denied(self):
        with self.assertRaisesRegex(ReviewSignatureError, "fingerprint"):
            self.verify(expected_public_key_sha256="b" * 64)

    def test_signature_malformed_and_missing(self):
        self.review["signature_b64"] = "not valid base64"
        with self.assertRaises(ReviewSignatureError):
            self.verify()
        self.review["signature_b64"] = ""
        with self.assertRaises(ReviewSignatureError):
            self.verify()

    def test_public_key_bytes_cannot_be_replaced(self):
        attacker = Ed25519PrivateKey.generate()
        self.public.write_bytes(attacker.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        with self.assertRaisesRegex(ReviewSignatureError, "fingerprint"):
            self.verify()

    def test_missing_or_oversized_key_is_denied(self):
        self.public.unlink()
        with self.assertRaises(ReviewSignatureError):
            self.verify()
        self.public.write_bytes(b"x" * 9000)
        with self.assertRaisesRegex(ReviewSignatureError, "byte limit"):
            self.verify()

    def test_signature_payload_excludes_only_signature_field(self):
        message = review_message(self.review)
        self.assertIn(b'"reviewer_id":"approved-reviewer"', message)
        self.assertNotIn(b"signature_b64", message)
        self.assertTrue(message.endswith(b"\n"))

    def test_unsupported_algorithm_is_denied(self):
        self.review["signature_algorithm"] = "HMAC-SHA256"
        with self.assertRaisesRegex(ReviewSignatureError, "algorithm"):
            self.verify()


if __name__ == "__main__":
    unittest.main()
