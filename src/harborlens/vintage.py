"""SPEC-004: conservative historical-geometry vintage audit.

An official NOAA ENC has edition and update/issue dates. Those metadata do NOT
prove a current reference Polygon is identical to its state on a historic date.
This module checks local hashes and date contradictions without granting
historical, operational or licensing approval. No network calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from harborlens.provenance import checksum

MAX_POLYGON_MIB = 32
MAX_JSON_BYTES = 128 * 1024
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
CELL_PATTERN = re.compile(r"^[A-Z0-9]{5,16}$")


class VintageAuditError(ValueError):
    """Historically unsupported geometry evidence or invalid input."""


def _small_json(path):
    path = Path(path)
    if not path.is_file() or not (0 < path.stat().st_size <= MAX_JSON_BYTES):
        raise VintageAuditError("Metadata JSON is missing, empty or too large")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise VintageAuditError("Invalid metadata JSON") from exc
    if not isinstance(result, dict):
        raise VintageAuditError("Expected JSON object")
    return result


def _aware_time(value):
    if not isinstance(value, str):
        raise VintageAuditError("Timestamp must be a string with UTC offset")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise VintageAuditError("Invalid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise VintageAuditError("Time must specify an explicit UTC offset")
    return parsed.astimezone(timezone.utc)


def _calendar_date(value, name):
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise VintageAuditError(f"{name} must be a YYYY-MM-DD calendar date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise VintageAuditError(f"Invalid {name} calendar date") from exc


def _documentary_source(path):
    """Capture user-supplied ENC metadata as unverified evidence, never approval."""
    record = _small_json(path)
    required = {
        "source_kind", "cell_id", "edition_number", "edition_date",
        "last_issue_date", "evidence_url", "referenced_document_sha256",
        "evidence_status",
    }
    if set(record) != required:
        raise VintageAuditError("ENC evidence must use the exact documented field set")
    if record["source_kind"] != "NOAA_ENC" or record["evidence_status"] != "user_supplied_unverified":
        raise VintageAuditError("ENC evidence must remain user_supplied_unverified")
    if not isinstance(record["cell_id"], str) or not CELL_PATTERN.fullmatch(record["cell_id"]):
        raise VintageAuditError("Invalid ENC chart cell ID")
    if type(record["edition_number"]) is not int or record["edition_number"] < 1:
        raise VintageAuditError("ENC edition number must be a positive integer")
    edition = _calendar_date(record["edition_date"], "edition_date")
    issue = _calendar_date(record["last_issue_date"], "last_issue_date")
    if issue < edition:
        raise VintageAuditError("Last issue date cannot predate edition date")
    if not isinstance(record["referenced_document_sha256"], str) or not SHA256_PATTERN.fullmatch(record["referenced_document_sha256"]):
        raise VintageAuditError("ENC document SHA-256 must be a 64-digit lowercase hex string")
    u = urlsplit(str(record["evidence_url"]))
    if u.scheme != "https" or not u.netloc or u.username or u.password:
        raise VintageAuditError("Evidence URL must use HTTPS with no embedded credentials")
    return record, edition, issue


def _date_assessment(start, end, edition, issue):
    # We intentionally never return a "historically_valid" state: an edition
    # date is NOT evidence the present geometry matched a past ENC.
    if edition > end.date():
        return "edition_postdates_study"
    if issue > start.date():
        return "update_issue_after_study_start"
    return "document_dates_compatible_but_geometry_unverified"


def audit_vintage(polygons, output, start_utc, end_utc, source_receipt=None, enc_evidence=None):
    polygons, output = Path(polygons), Path(output)
    if output.suffix.lower() != ".json" or polygons.resolve() == output.resolve():
        raise VintageAuditError("Output must be a distinct .json report")
    if not polygons.is_file() or not (0 < polygons.stat().st_size <= MAX_POLYGON_MIB * 1048576):
        raise VintageAuditError("Missing or oversized polygon GeoJSON")
    receipt_path = Path(source_receipt) if source_receipt else Path(str(polygons) + ".source.json")
    destination = output.resolve()
    protected = {polygons.resolve(), receipt_path.resolve()}
    if enc_evidence:
        protected.add(Path(enc_evidence).resolve())
    if destination in protected or output.exists():
        raise VintageAuditError("Refusing to overwrite input/receipt/existing report")
    start, end = _aware_time(start_utc), _aware_time(end_utc)
    if not start < end:
        raise VintageAuditError("Study start must precede study end")
    source = _small_json(receipt_path)
    geometry_sha = checksum(polygons)
    if source.get("output_sha256") != geometry_sha:
        raise VintageAuditError("Source receipt hash does not match polygon GeoJSON")
    if source.get("historical_validity") != "not_verified":
        raise VintageAuditError("Source may not claim verified historical geometry")
    if source.get("geometry_review_status") != "unreviewed" or source.get("rights_status") != "review_required":
        raise VintageAuditError("Unsupported source review or redistribution status")
    if source.get("source_agency") != "NOAA":
        raise VintageAuditError("A NOAA polygon source receipt is required")
    details = None
    assessment = "no_documentary_enc_evidence"
    evidence_sha = None
    if enc_evidence:
        item, edition, issue = _documentary_source(enc_evidence)
        assessment = _date_assessment(start, end, edition, issue)
        evidence_sha = checksum(enc_evidence)
        details = {
            "kind": "NOAA_ENC",
            "cell_id": item["cell_id"],
            "edition_number": item["edition_number"],
            "edition_date": item["edition_date"],
            "last_issue_date": item["last_issue_date"],
            "evidence_url": item["evidence_url"],
            "referenced_document_sha256": item["referenced_document_sha256"],
            "evidence_status": "user_supplied_unverified",
        }
    output_doc = {
        "schema_version": "geometry-vintage-audit-v1",
        "study_window_utc": {
            "start": start.isoformat().replace("+00:00", "Z"),
            "end": end.isoformat().replace("+00:00", "Z"),
        },
        "polygon_sha256": geometry_sha,
        "polygon_receipt_sha256": checksum(receipt_path),
        "source_retrieved_at_utc": source.get("retrieved_at_utc"),
        "source_rights": "review_required",
        "historical_geometry_validity": "not_verified",
        "operational_event_validation": "not_verified",
        "date_assessment": assessment,
        "documentary_evidence": details,
        "evidence_metadata_sha256": evidence_sha,
        "warning": (
            "ENC edition and update dates do not prove current polygon boundaries "
            "were valid in a historical AIS period; no operational labels are authorized."
        ),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(output.name + ".partial")
    try:
        with tmp.open("xb", encoding="utf-8") as handle:
            json.dump(output_doc, handle, indent=2)
        os.replace(tmp, output)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return output_doc


def main():
    parser = argparse.ArgumentParser(description="Audit historical NOAA polygon vintage evidence; no validity approval")
    parser.add_argument("--polygons", type=Path, required=True)
    parser.add_argument("--source-receipt", type=Path)
    parser.add_argument("--enc-evidence", type=Path, help="Optional unverified, user-supplied ENC documentary record")
    parser.add_argument("--start", required=True, help="Study start in ISO 8601 UTC")
    parser.add_argument("--end", required=True, help="Study end in ISO 8601 UTC")
    parser.add_argument("--out", type=Path, required=True)
    a = parser.parse_args()
    print(json.dumps(audit_vintage(a.polygons, a.out, a.start, a.end, a.source_receipt, a.enc_evidence), indent=2))


if __name__ == "__main__":
    main()
