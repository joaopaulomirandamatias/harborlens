"""Controlled, local release of coarse HarborLens research summaries.

SPEC-003 / FR-010 / BR-015, BR-016. Not a replacement for an organization's
access controls, DLP, legal review, or publication approval process. No raw AIS,
coordinates, timestamps, MMSI, event IDs or arbitrary input text are exported.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import tempfile
from datetime import datetime, timedelta, timezone
from importlib.resources import files
from pathlib import Path

from harborlens.ais import interpret_cleaned_row
from harborlens.provenance import checksum, digests_equal, verify_manifest
from harborlens.rights import APPROVED_STATUSES, PURPOSES, rights_receipt
from harborlens.review_signatures import ReviewSignatureError, verify_review_signature
from harborlens.timeparse import parse_review_utc

MAX_DOCUMENT_BYTES = 1024 * 1024
# Same 256 MiB output ceiling as archive extraction (MAX_OUTPUT_MIB) and
# track-context output (MAX_OUTPUT_BYTES). The scale benchmark's synthetic
# seven-day cleaned CSV is 226.6 MiB, so that density still fits. The release
# path reads houston_clean.csv once into this bound.
MAX_CLEANED_RECOUNT_BYTES = 256 * 1024 * 1024
MIN_OBSERVATIONS = 100
MIN_VESSELS = 10
# Fixed review freshness window. Not a configuration knob.
# A timestamp may be at most REVIEW_FUTURE_TOLERANCE ahead of the checker
# clock. That allowance is clock skew. Older than REVIEW_MAX_AGE is stale.
REVIEW_MAX_AGE = timedelta(days=30)
REVIEW_FUTURE_TOLERANCE = timedelta(minutes=5)
# Release-gate contracts shipped in the wheel. The rights register schema
# stays on its own loader. Other research schemas are not packaged.
PACKAGED_RELEASE_SCHEMAS = (
    "public-summary.schema.json",
    "publication-review.schema.json",
    "release-verification-result.schema.json",
)
RELEASE_PURPOSES = ("public_aggregates", "commercial")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REVIEWER_ID = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
CAUTION = (
    "Offline research diagnostics only; inferred stationary candidates are "
    "NOT verified anchoring, berth occupancy, waiting, port calls or navigation signals. "
    "Counts do not prove data coverage, independent accuracy or anonymity."
)


class ReleaseDenied(ValueError):
    """Rights, provenance, scope or publication-review gate was not satisfied."""


def _json_file(path):
    path = Path(path)
    try:
        with path.open("rb") as handle:
            raw = handle.read(MAX_DOCUMENT_BYTES + 1)
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise ReleaseDenied("Input JSON exceeds bounded size")
        data = json.loads(raw)
    except (OSError, UnicodeError, ValueError) as exc:
        if isinstance(exc, ReleaseDenied):
            raise
        raise ReleaseDenied("Missing or invalid JSON evidence") from exc
    if not isinstance(data, dict):
        raise ReleaseDenied("Evidence must be a JSON object")
    return data


def _int_nonnegative(value, field):
    if type(value) is not int or value < 0:
        raise ReleaseDenied(f"Invalid nonnegative count: {field}")
    return value


def _source_context(sidecar):
    """Infer identity only from source-specific acquisition metadata."""
    previous = sidecar.get("rights_review")
    if not isinstance(previous, dict):
        raise ReleaseDenied("Acquisition lacks a source-rights receipt")
    if (sidecar.get("agency") == "NOAA/OAR/PMEL"
            and sidecar.get("dataset") == "AIS2024_AIS"
            and isinstance(sidecar.get("source_url"), str)
            and sidecar["source_url"].startswith(
                "https://data.pmel.noaa.gov/pmel/erddap/tabledap/AIS2024_AIS.csv?"
            )):
        source_id, version, file_digest = (
            "noaa_pmel_erddap", "AIS2024_AIS", sidecar.get("csv_sha256")
        )
    elif sidecar.get("source_type") == "local_noaa_daily_archive":
        vintage = sidecar.get("source_vintage")
        year = vintage.get("year") if isinstance(vintage, dict) else None
        archive_digest = sidecar.get("input_sha256")
        if (type(year) is not int or not 2015 <= year <= 2026
                or not isinstance(archive_digest, str)
                or not HEX64.fullmatch(archive_digest)):
            raise ReleaseDenied("Archive vintage or original checksum is missing")
        source_id, version, file_digest = (
            "noaa_ocm_ais_daily",
            f"{year}/archive-sha256:{archive_digest}",
            sidecar.get("output_sha256")
        )
    else:
        raise ReleaseDenied("Only source-pinned NOAA AIS acquisition is supported")
    if not isinstance(file_digest, str) or not HEX64.fullmatch(file_digest):
        raise ReleaseDenied("Acquisition output checksum is missing or invalid")
    if (previous.get("source_id") != source_id
            or previous.get("dataset_version") != version
            or previous.get("schema_version") != 1
            or previous.get("purpose") not in PURPOSES):
        raise ReleaseDenied("Acquisition receipt identity/version mismatch")
    return source_id, version, file_digest, previous


def _canonical(value):
    """ASCII canonical JSON. Non-finite numbers are rejected, never hashed."""
    try:
        encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False)
    except ValueError as exc:
        raise ReleaseDenied("Release document contains a non-finite number") from exc
    return (encoded + "\n").encode("ascii")


def _read_cleaned_once(path):
    """Read the cleaned CSV once, stopping at the size ceiling plus one byte.

    The extra byte detects an oversize file without reading the remainder.
    Callers hash and recount this buffer and must not open the path again.
    """
    ceiling = MAX_CLEANED_RECOUNT_BYTES
    try:
        with Path(path).open("rb") as handle:
            raw = handle.read(ceiling + 1)
    except OSError as exc:
        raise ReleaseDenied("Verified cleaned AIS cannot be recounted") from exc
    if len(raw) > ceiling:
        raise ReleaseDenied("Verified cleaned AIS exceeds the recount size ceiling")
    return raw


def _recount_cleaned_bytes(raw):
    """Count retained rows and distinct MMSI groups in an already-read CSV buffer."""
    observations = 0
    groups = set()
    try:
        with io.BytesIO(raw) as buffer:
            with io.TextIOWrapper(buffer, encoding="utf-8", newline="") as text:
                reader = csv.DictReader(text)
                if not reader.fieldnames or "mmsi" not in reader.fieldnames:
                    raise ReleaseDenied("Verified cleaned AIS cannot be recounted")
                for row in reader:
                    # Free-text cells use the shared reader. mmsi stays the raw
                    # cell, so a formula prefix on vessel_type does not change
                    # the observation count or the MMSI set. SHA-256 is of
                    # these bytes, not of the recovered text.
                    interpreted = interpret_cleaned_row(row)
                    mmsi = interpreted.get("mmsi")
                    if not isinstance(mmsi, str) or mmsi == "":
                        raise ReleaseDenied("Verified cleaned AIS cannot be recounted")
                    observations += 1
                    groups.add(mmsi)
    except ReleaseDenied:
        raise
    except (OSError, UnicodeError, csv.Error) as exc:
        raise ReleaseDenied("Verified cleaned AIS cannot be recounted") from exc
    return observations, len(groups)


def _recount_cleaned(path):
    """Count retained rows and distinct MMSI groups in verified cleaned AIS.

    Suppression floors use these figures. Manifest copies that disagree are denied.
    The file is read once, under ``MAX_CLEANED_RECOUNT_BYTES``.
    """
    return _recount_cleaned_bytes(_read_cleaned_once(path))


def _review_moment(reviewed_at):
    """Parse a release-review UTC timestamp. Date-only values are a validation failure.

    The accepted grammar is narrower than the rights register: ASCII
    ``YYYY-MM-DDTHH:MM:SS`` with no fraction or 1 to 6 fractional digits,
    then ``Z`` only. ``+00:00`` is rejected. The clock is built from the
    captured fields, so Python 3.10 and 3.12 agree. Seven fractional
    digits, a comma fraction, another offset, a non-ASCII digit, and an
    impossible calendar time (including hour 24) are denied.
    """
    try:
        moment = parse_review_utc(reviewed_at)
    except ValueError as exc:
        message = str(exc)
        if message == "Invalid review timestamp":
            raise ReleaseDenied("Invalid review timestamp") from exc
        raise ReleaseDenied("Review timestamp must be an RFC3339 UTC date-time") from exc
    if moment.utcoffset() != timedelta(0):
        raise ReleaseDenied("Review timestamp must be an RFC3339 UTC date-time")
    return moment


def _utcnow():
    """Checker clock. Tests replace this; callers cannot configure it."""
    return datetime.now(timezone.utc)


def _release_rights_status(summary):
    """Return the summary status only when it is an approved string.

    A missing key, ``None``, a non-string, or any value outside
    ``APPROVED_STATUSES`` is denied. Absence must not skip the
    conditions-review requirement.
    """
    if not isinstance(summary, dict) or "rights_status" not in summary:
        raise ReleaseDenied(
            "Release summary rights_status is missing or not an approved status"
        )
    status = summary["rights_status"]
    if type(status) is not str or status not in APPROVED_STATUSES:
        raise ReleaseDenied(
            "Release summary rights_status is missing or not an approved status"
        )
    return status


def review_timestamp_is_current(moment, now):
    """Return whether ``moment`` sits in the fixed review freshness window.

    Inclusive bounds are ``now - 30 days`` through ``now + 5 minutes``.
    The five minutes are a fixed clock-skew allowance, not a setting.
    Comparing a naive ``moment`` with an aware ``now`` raises ``TypeError``.
    Callers deny the review in that case.
    """
    return now - REVIEW_MAX_AGE <= moment <= now + REVIEW_FUTURE_TOLERANCE


def read_packaged_release_schema(name):
    """Read one release-gate schema shipped inside this package.

    ``importlib.resources`` only. A name outside ``PACKAGED_RELEASE_SCHEMAS``
    is refused, including a path. Parent directories are not searched.
    """
    if name not in PACKAGED_RELEASE_SCHEMAS:
        raise ValueError("Unknown packaged schema")
    try:
        text = files("harborlens").joinpath(
            "schemas", "v1", name
        ).read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("Packaged schema is unreadable") from exc
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Packaged schema is unreadable")
    return text


def prepare_summary(run_dir, source_file, registry, purpose="public_aggregates"):
    """Verify artifacts, review rights and construct a non-published summary."""
    if purpose not in RELEASE_PURPOSES:
        raise ReleaseDenied("Only public_aggregates or commercial release is supported")
    run_dir, source_file = Path(run_dir), Path(source_file)
    manifest_path = run_dir / "manifest.json"
    sidecar_path = source_file.with_name(source_file.name + ".source.json")
    manifest, sidecar = _json_file(manifest_path), _json_file(sidecar_path)
    # One bounded read. The manifest hash and the recount both use these bytes.
    cleaned_bytes = _read_cleaned_once(run_dir / "houston_clean.csv")
    try:
        verified = verify_manifest(
            manifest_path, preloaded={"houston_clean.csv": cleaned_bytes}
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ReleaseDenied("Run manifest cannot be verified") from exc
    if not verified.get("ok"):
        raise ReleaseDenied("Run artifact checksums do not verify")
    source_id, version, expected_digest, previous = _source_context(sidecar)
    try:
        file_digest = checksum(source_file)
    except OSError as exc:
        raise ReleaseDenied("Source file cannot be verified") from exc
    if (not digests_equal(file_digest, expected_digest)
            or not digests_equal(manifest.get("input_sha256"), file_digest)
            or not HEX64.fullmatch(str(manifest.get("run_id", "")))):
        raise ReleaseDenied("Source, acquisition receipt and analysis input do not match")
    if manifest.get("input_truncated") is not False:
        raise ReleaseDenied("Truncated or unknown input completeness")
    counts, events = manifest.get("counts"), manifest.get("events")
    if not isinstance(counts, dict) or not isinstance(events, dict):
        raise ReleaseDenied("Missing batch diagnostics")
    total = _int_nonnegative(counts.get("total"), "total")
    written = _int_nonnegative(counts.get("written"), "written")
    vessels = _int_nonnegative(events.get("vessels"), "vessels")
    candidates = _int_nonnegative(events.get("stationary_candidates"), "stationary_candidates")
    # Same buffer verify_manifest hashed. Do not open houston_clean.csv again.
    retained, mmsi_groups = _recount_cleaned_bytes(cleaned_bytes)
    if written != retained or vessels != mmsi_groups:
        raise ReleaseDenied(
            "Manifest counts do not match the verified cleaned AIS recount "
            f"(retained observations {retained} vs manifest written {written}; "
            f"MMSI groups {mmsi_groups} vs manifest vessels {vessels})"
        )
    if (total < MIN_OBSERVATIONS or retained < MIN_OBSERVATIONS
            or mmsi_groups < MIN_VESSELS or retained > total
            or candidates > retained):
        raise ReleaseDenied("Aggregate count/suppression gate is not satisfied")
    params = manifest.get("method_parameters")
    if not isinstance(params, dict) or not isinstance(params.get("method_version"), str):
        raise ReleaseDenied("Missing segmentation method identity")
    # A current registry decision is authoritative for this attempted release;
    # acquisition rights metadata cannot promote a pending/prohibited source.
    current = rights_receipt(source_id, dataset_version=version,
                             purpose=purpose, register_path=registry)
    if (current.get("evaluation") != "reviewed_record"
            or current.get("rights_status") not in APPROVED_STATUSES
            or not isinstance(current.get("registry_sha256"), str)
            or not HEX64.fullmatch(current["registry_sha256"])):
        raise ReleaseDenied("No reviewed, purpose-specific source rights decision")
    if (previous.get("rights_status") not in (
            "review_required", "use_restricted", *APPROVED_STATUSES)
            or previous.get("evaluation") not in (
                "not_supplied", "pending_or_unmatched", "invalid_registry", "reviewed_record")
            or sidecar.get("rights_status", sidecar.get("license_status"))
               != previous["rights_status"]):
        raise ReleaseDenied("Acquisition rights receipt conflicts with its sidecar")
    return {
        "schema_version": "public-summary-v0.1",
        "research_status": "unvalidated_stationary_candidates",
        "purpose": purpose,
        "method_version": params["method_version"],
        "run_id": manifest["run_id"],
        "run_manifest_sha256": checksum(manifest_path),
        "acquisition_sha256": file_digest,
        "source_id": source_id,
        "dataset_version": version,
        "rights_registry_sha256": current["registry_sha256"],
        "rights_status": current["rights_status"],
        "counts": {
            "observations_scanned": total,
            "observations_retained": retained,
            "unique_mmsi_groups": mmsi_groups,
            "unvalidated_stationary_candidates": candidates,
        },
        "warning": CAUTION,
    }


def summary_sha256(summary):
    return hashlib.sha256(_canonical(summary)).hexdigest()


def _validate_review(path, expected_sha, purpose, needs_conditions, *,
                     trusted_public_key, expected_public_key_sha256,
                     expected_reviewer_id):
    review = _json_file(path)
    if (set(review) != {
            "schema_version", "decision", "summary_sha256", "purpose",
            "reviewer_id", "reviewed_at_utc", "privacy_reviewed",
            "source_rights_reviewed", "scientific_limitations_reviewed",
            "conditions_reviewed", "signature_algorithm",
            "public_key_sha256", "signature_b64"
        } or review.get("schema_version") != 1
            or review.get("decision") != "approved"
            or not digests_equal(review.get("summary_sha256"), expected_sha)
            or review.get("purpose") != purpose
            or not isinstance(review.get("reviewer_id"), str)
            or not REVIEWER_ID.fullmatch(review["reviewer_id"])
            or any(review.get(field) is not True for field in (
                "privacy_reviewed", "source_rights_reviewed",
                "scientific_limitations_reviewed"))):
        raise ReleaseDenied("Independent release review is missing or does not match summary")
    conditions = review.get("conditions_reviewed")
    if type(conditions) is not bool or (needs_conditions and not conditions):
        raise ReleaseDenied("License-specific conditions lack recorded human review")
    moment = _review_moment(review.get("reviewed_at_utc"))
    now = _utcnow()
    try:
        fresh = review_timestamp_is_current(moment, now)
    except TypeError as exc:
        raise ReleaseDenied("Review timestamp must be an RFC3339 UTC date-time") from exc
    if not fresh:
        raise ReleaseDenied("Publication review is stale or in the future")
    try:
        verify_review_signature(
            review,
            trusted_public_key=trusted_public_key,
            expected_public_key_sha256=expected_public_key_sha256,
            expected_reviewer_id=expected_reviewer_id,
        )
    except ReviewSignatureError as exc:
        raise ReleaseDenied("Signed reviewer approval cannot be authenticated: " + str(exc)) from exc
    return review


def _stage_release(summary, out, review, *, trusted_public_key,
                   expected_public_key_sha256, expected_reviewer_id):
    """Write one already prepared summary. Does not call ``prepare_summary``."""
    out = Path(out)
    if out.suffix.lower() != ".json" or out.is_file() or out.is_symlink():
        raise ReleaseDenied("Output must be a new JSON file")
    if (not isinstance(summary, dict)
            or summary.get("purpose") not in RELEASE_PURPOSES):
        raise ReleaseDenied("Only public_aggregates or commercial release is supported")
    # Strict subscript after the allowlist. A missing or other status denies
    # before the conditions flag can be skipped.
    status = _release_rights_status(summary)
    digest = summary_sha256(summary)
    approval = _validate_review(
        review, digest, summary["purpose"],
        status == "reviewed_permitted_with_conditions",
        trusted_public_key=trusted_public_key,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_reviewer_id=expected_reviewer_id,
    )
    result = {
        "summary": summary,
        "summary_sha256": digest,
        "release_review": approval,
    }
    raw = _canonical(result)
    out.parent.mkdir(parents=True, exist_ok=True)
    # Local atomic publish with no clobber: do not replace an existing release.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=out.parent,
                                         prefix=".harborlens-release-",
                                         suffix=".partial", delete=False) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, out)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return result


def release_summary(run_dir, source_file, register, out, review,
                    purpose="public_aggregates", *, trusted_public_key=None,
                    expected_public_key_sha256=None, expected_reviewer_id=None):
    """Create a reviewed, sanitized local release JSON; never auto-upload it.

    ``prepare_summary`` runs once. The staged file is that result.
    """
    out = Path(out)
    if out.suffix.lower() != ".json" or out.is_file() or out.is_symlink():
        raise ReleaseDenied("Output must be a new JSON file")
    summary = prepare_summary(run_dir, source_file, register, purpose)
    return _stage_release(
        summary, out, review,
        trusted_public_key=trusted_public_key,
        expected_public_key_sha256=expected_public_key_sha256,
        expected_reviewer_id=expected_reviewer_id,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Offline rights-gated aggregate release (NOT raw AIS export). "
            "reviewed_at_utc must be an RFC3339 UTC date-time no older than "
            "30 days and at most 5 minutes ahead of this clock. The 5 minutes "
            "are a fixed clock-skew allowance."
        )
    )
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--source-file", required=True, type=Path)
    parser.add_argument("--rights-register", required=True, type=Path)
    parser.add_argument("--purpose", choices=RELEASE_PURPOSES, default="public_aggregates")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--review", type=Path)
    parser.add_argument("--trusted-reviewer-key", type=Path)
    parser.add_argument("--trusted-reviewer-key-sha256")
    parser.add_argument("--trusted-reviewer-id")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args(argv)
    try:
        # One prepare_summary for this process. Dry-run prints its digest.
        # A real staging reuses that same object and does not compute it again.
        summary = prepare_summary(args.run, args.source_file,
                                  args.rights_register, args.purpose)
        if summary.get("purpose") != args.purpose:
            raise ReleaseDenied("Prepared summary purpose does not match the request")
        digest = summary_sha256(summary)
        if args.dry_run:
            print(json.dumps({"decision": "requires_human_release_review",
                              "summary_sha256": digest, "purpose": args.purpose},
                             indent=2))
            return
        if (args.review is None or args.out is None
                or args.trusted_reviewer_key is None
                or args.trusted_reviewer_key_sha256 is None
                or args.trusted_reviewer_id is None):
            raise ReleaseDenied(
                "--review, --out, --trusted-reviewer-key, "
                "--trusted-reviewer-key-sha256 and --trusted-reviewer-id "
                "are required without --dry-run"
            )
        release = _stage_release(
            summary, args.out, args.review,
            trusted_public_key=args.trusted_reviewer_key,
            expected_public_key_sha256=args.trusted_reviewer_key_sha256,
            expected_reviewer_id=args.trusted_reviewer_id,
        )
        print(json.dumps({"decision": "locally_staged_not_uploaded",
                          "summary_sha256": release["summary_sha256"],
                          "output": str(args.out)}, indent=2))
    except ReleaseDenied as exc:
        parser.exit(2, "Release denied: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
