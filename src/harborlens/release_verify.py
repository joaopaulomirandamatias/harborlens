"""Offline, independent inspection of a signed HarborLens aggregate release.

SPEC-003 / FR-010 / BR-015..016. This verifier needs only the staged JSON,
an independently pinned rights-register snapshot and an out-of-band pinned
reviewer public key. It does not read AIS data or accept network URLs.

It verifies claim integrity, scope and local evidence; it cannot prove the
truth of the original AIS observations, source authenticity, or legal rights.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

from harborlens.provenance import digests_equal
from harborlens.publication import (
    CAUTION,
    MIN_OBSERVATIONS,
    MIN_VESSELS,
    ReleaseDenied,
    _review_moment,
    _utcnow,
    review_timestamp_is_current,
    summary_sha256,
)
from harborlens.review_signatures import ReviewSignatureError, verify_review_signature
from harborlens.rights import APPROVED_STATUSES, rights_receipt

MAX_RELEASE_BYTES = 128 * 1024
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REVIEWER = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
ARCHIVE_VINTAGE = re.compile(r"^(201[5-9]|202[0-6])/archive-sha256:[0-9a-f]{64}$")
PURPOSES = ("public_aggregates", "commercial")
SOURCE_IDS = ("noaa_pmel_erddap", "noaa_ocm_ais_daily")
REVIEW_FIELDS = frozenset({
    "schema_version", "decision", "summary_sha256", "purpose",
    "reviewer_id", "reviewed_at_utc", "privacy_reviewed",
    "source_rights_reviewed", "scientific_limitations_reviewed",
    "conditions_reviewed", "signature_algorithm", "public_key_sha256",
    "signature_b64",
})
SUMMARY_FIELDS = frozenset({
    "schema_version", "research_status", "purpose", "method_version",
    "run_id", "run_manifest_sha256", "acquisition_sha256", "source_id",
    "dataset_version", "rights_registry_sha256", "rights_status",
    "counts", "warning",
})
COUNT_FIELDS = frozenset({
    "observations_scanned", "observations_retained", "unique_mmsi_groups",
    "unvalidated_stationary_candidates",
})
# Same caution string the publisher hashes. A divergent copy would change the digest.
WARNING = CAUTION


class ReleaseVerificationError(ValueError):
    """The staged release cannot be verified with independently supplied trust."""


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReleaseVerificationError("Duplicate keys in staged release")
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise ReleaseVerificationError("Non-finite values are forbidden in staged release")


def _read_release(path):
    path = Path(path)
    if path.suffix.lower() != ".json":
        raise ReleaseVerificationError("Release must be a JSON file")
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_RELEASE_BYTES + 1)
        if len(raw) > MAX_RELEASE_BYTES:
            raise ReleaseVerificationError("Release exceeds bounded size")
        document = json.loads(
            raw, object_pairs_hook=_unique_pairs, parse_constant=_reject_nonfinite
        )
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        if isinstance(exc, ReleaseVerificationError):
            raise
        raise ReleaseVerificationError("Release is unreadable or malformed") from exc
    if not isinstance(document, dict) or set(document) != {
            "summary", "summary_sha256", "release_review"}:
        raise ReleaseVerificationError("Unexpected top-level release fields")
    return document, hashlib.sha256(raw).hexdigest()


def _hex(value):
    return isinstance(value, str) and HEX64.fullmatch(value) is not None


def _canonical_summary_digest(summary):
    """SHA-256 of the publisher's canonical summary bytes.

    ``summary_sha256`` is the publisher path: sorted keys, compact separators,
    ASCII escaping, ``allow_nan=False``, and a trailing newline. Reusing it
    keeps this check from accepting a divergent encoding. The Ed25519 message
    is ``review_message`` (domain separator plus those canonical review bytes).
    """
    try:
        return summary_sha256(summary)
    except ReleaseDenied as exc:
        raise ReleaseVerificationError(
            "Summary canonical bytes are not finite"
        ) from exc


def _validate_summary(summary, purpose, source_id, dataset_version, expected_run_id):
    if not isinstance(summary, dict) or set(summary) != SUMMARY_FIELDS:
        raise ReleaseVerificationError("Summary has unapproved or missing fields")
    if (summary.get("schema_version") != "public-summary-v0.1"
            or summary.get("research_status") != "unvalidated_stationary_candidates"
            or summary.get("purpose") != purpose
            or purpose not in PURPOSES
            or summary.get("source_id") != source_id
            or source_id not in SOURCE_IDS
            or summary.get("dataset_version") != dataset_version
            or not isinstance(dataset_version, str)
            or len(dataset_version) > 200):
        raise ReleaseVerificationError("Summary identity/purpose is outside expected scope")
    if (source_id == "noaa_pmel_erddap" and dataset_version != "AIS2024_AIS"
            or source_id == "noaa_ocm_ais_daily"
            and not ARCHIVE_VINTAGE.fullmatch(dataset_version)):
        raise ReleaseVerificationError("Source vintage does not satisfy acquisition contract")
    if (summary.get("method_version") != "stationary-v0.2"
            or summary.get("warning") != WARNING
            or summary.get("rights_status") not in APPROVED_STATUSES):
        raise ReleaseVerificationError("Summary research and rights labels are invalid")
    for field in (
            "run_id", "run_manifest_sha256", "acquisition_sha256",
            "rights_registry_sha256"):
        if not _hex(summary.get(field)):
            raise ReleaseVerificationError("Summary evidence digest is invalid")
    if expected_run_id is not None and not digests_equal(summary["run_id"], expected_run_id):
        raise ReleaseVerificationError("Run ID does not match expected study")
    counts = summary.get("counts")
    if not isinstance(counts, dict) or set(counts) != COUNT_FIELDS:
        raise ReleaseVerificationError("Summary count allowlist is invalid")
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise ReleaseVerificationError("Counts must be nonnegative integers")
    scanned, retained, groups, episodes = (
        counts["observations_scanned"], counts["observations_retained"],
        counts["unique_mmsi_groups"], counts["unvalidated_stationary_candidates"],
    )
    # observations_scanned is the manifest total. It cannot satisfy the floor
    # alone: retained observations and MMSI groups use the same recounted
    # floors harborlens-release-summary applies to verified houston_clean.csv.
    if (scanned < MIN_OBSERVATIONS or retained < MIN_OBSERVATIONS
            or groups < MIN_VESSELS or retained > scanned
            or groups > retained or episodes > retained):
        raise ReleaseVerificationError(
            "Summary is below recounted aggregate floors or breaks conservation bounds"
        )


def _validate_review(review, summary, digest, expected_reviewer_id, *,
                     trusted_public_key, expected_public_key_sha256):
    if not isinstance(review, dict) or set(review) != REVIEW_FIELDS:
        raise ReleaseVerificationError("Signed review has unexpected or missing fields")
    if (review.get("schema_version") != 1
            or review.get("decision") != "approved"
            or not digests_equal(review.get("summary_sha256"), digest)
            or review.get("purpose") != summary["purpose"]
            or review.get("reviewer_id") != expected_reviewer_id
            or not isinstance(expected_reviewer_id, str)
            or not REVIEWER.fullmatch(expected_reviewer_id)
            or review.get("signature_algorithm") != "Ed25519"):
        raise ReleaseVerificationError("Signed approval does not match expected summary/reviewer")
    if any(review.get(k) is not True for k in (
            "privacy_reviewed", "source_rights_reviewed",
            "scientific_limitations_reviewed")):
        raise ReleaseVerificationError("Mandatory independent review attestations missing")
    conditions = review.get("conditions_reviewed")
    if (type(conditions) is not bool or
            summary["rights_status"] == "reviewed_permitted_with_conditions"
            and not conditions):
        raise ReleaseVerificationError("Conditions require explicit reviewer attestation")
    try:
        reviewed = _review_moment(review.get("reviewed_at_utc"))
    except ReleaseDenied as exc:
        raise ReleaseVerificationError(
            "Review timestamp must be an RFC3339 UTC date-time"
        ) from exc
    now = _utcnow()
    try:
        fresh = review_timestamp_is_current(reviewed, now)
    except TypeError as exc:
        raise ReleaseVerificationError(
            "Review timestamp must be an RFC3339 UTC date-time"
        ) from exc
    if not fresh:
        raise ReleaseVerificationError("Review is stale or future-dated")
    try:
        verify_review_signature(
            review, trusted_public_key=trusted_public_key,
            expected_public_key_sha256=expected_public_key_sha256,
            expected_reviewer_id=expected_reviewer_id,
        )
    except ReviewSignatureError as exc:
        raise ReleaseVerificationError(
            "Reviewer signature/trust anchor invalid: " + str(exc)
        ) from exc


def verify_release(
    release_file, *, rights_register, expected_rights_register_sha256,
    trusted_public_key, expected_public_key_sha256, expected_reviewer_id,
    expected_purpose, expected_source_id, expected_dataset_version,
    expected_run_id=None, expected_summary_sha256=None,
):
    """Verify a staged report without original AIS or source artifacts.

    The register SHA and reviewer fingerprint MUST be learned independently,
    not copied from the untrusted report under inspection.
    """
    if (not _hex(expected_rights_register_sha256)
            or not _hex(expected_public_key_sha256)
            or expected_purpose not in PURPOSES
            or expected_source_id not in SOURCE_IDS
            or not isinstance(expected_dataset_version, str)
            or (expected_run_id is not None and not _hex(expected_run_id))
            or (expected_summary_sha256 is not None
                and not _hex(expected_summary_sha256))):
        raise ReleaseVerificationError("Explicit independent verification scope is invalid")
    doc, file_sha = _read_release(release_file)
    summary, signed = doc["summary"], doc["release_review"]
    _validate_summary(summary, expected_purpose, expected_source_id,
                      expected_dataset_version, expected_run_id)
    digest = _canonical_summary_digest(summary)
    if (not digests_equal(doc.get("summary_sha256"), digest) or
            expected_summary_sha256 is not None
            and not digests_equal(digest, expected_summary_sha256)):
        raise ReleaseVerificationError("Summary was modified or replaced")
    _validate_review(
        signed, summary, digest, expected_reviewer_id,
        trusted_public_key=trusted_public_key,
        expected_public_key_sha256=expected_public_key_sha256,
    )
    checked = rights_receipt(
        expected_source_id, dataset_version=expected_dataset_version,
        purpose=expected_purpose, register_path=rights_register,
    )
    if (checked.get("evaluation") != "reviewed_record"
            or checked.get("rights_status") != summary["rights_status"]
            or checked.get("rights_status") not in APPROVED_STATUSES
            or not digests_equal(
                checked.get("registry_sha256"), expected_rights_register_sha256)
            or not digests_equal(
                summary["rights_registry_sha256"], expected_rights_register_sha256)):
        raise ReleaseVerificationError("Pinned source-rights snapshot does not authorize scope")
    return {
        "verified": True,
        "verification_scope": "signed_release_and_pinned_rights_only",
        "source_id": expected_source_id,
        "dataset_version": expected_dataset_version,
        "purpose": expected_purpose,
        "run_id": summary["run_id"],
        "summary_sha256": digest,
        "release_sha256": file_sha,
        "rights_register_sha256": expected_rights_register_sha256,
        "reviewer_id": expected_reviewer_id,
        "caveat": (
            "No original AIS supplied: content statistics, event accuracy, "
            "upstream authenticity, legal rights and anonymity remain unverified."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Independently verify a signed aggregate-only release (no AIS needed). "
            "reviewed_at_utc must be an RFC3339 UTC date-time no older than "
            "30 days and at most 5 minutes ahead of this clock. The 5 minutes "
            "are a fixed clock-skew allowance."
        )
    )
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--rights-register", required=True, type=Path)
    parser.add_argument("--expected-rights-register-sha256", required=True)
    parser.add_argument("--trusted-reviewer-key", required=True, type=Path)
    parser.add_argument("--trusted-reviewer-key-sha256", required=True)
    parser.add_argument("--trusted-reviewer-id", required=True)
    parser.add_argument("--purpose", required=True, choices=PURPOSES)
    parser.add_argument("--source-id", required=True, choices=SOURCE_IDS)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--expected-summary-sha256", default=None)
    args = parser.parse_args(argv)
    try:
        verified = verify_release(
            args.release,
            rights_register=args.rights_register,
            expected_rights_register_sha256=args.expected_rights_register_sha256,
            trusted_public_key=args.trusted_reviewer_key,
            expected_public_key_sha256=args.trusted_reviewer_key_sha256,
            expected_reviewer_id=args.trusted_reviewer_id,
            expected_purpose=args.purpose, expected_source_id=args.source_id,
            expected_dataset_version=args.dataset_version,
            expected_run_id=args.run_id,
            expected_summary_sha256=args.expected_summary_sha256,
        )
    except ReleaseVerificationError as exc:
        parser.exit(2, "Release verification denied: " + str(exc) + "\n")
    print(json.dumps(verified, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
