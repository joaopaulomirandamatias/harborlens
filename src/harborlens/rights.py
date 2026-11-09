"""Fail-closed, offline source-rights decision gate (SPEC-003, issue #42).

A published catalog link or public URL is not a legal review. Only an explicit,
version-matched reviewer decision can change the default "review_required".
This module does not download data, modify source evidence, or give legal advice.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

MAX_REGISTRY_BYTES = 256 * 1024
PURPOSES = ("research", "public_aggregates", "commercial")
APPROVED_STATUSES = (
    "reviewed_public_domain_attribution_required",
    "reviewed_permitted_with_conditions",
)
PENDING = "review_required"
RESTRICTED = "use_restricted"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _valid_utc_time(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0
    except (TypeError, ValueError, AttributeError):
        return False


def _parse_registry_bytes(raw):
    try:
        data = json.loads(raw)
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Rights register is unreadable") from exc
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("Unsupported rights register version")
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) > 100:
        raise ValueError("Invalid source registry")
    identifiers = []
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("Invalid source record")
        identifier = source.get("source_id")
        if not isinstance(identifier, str) or not re.fullmatch(r"[a-z0-9_]{3,100}", identifier):
            raise ValueError("Invalid source identifier")
        if not isinstance(source.get("dataset_version"), str) or not source["dataset_version"]:
            raise ValueError("Missing source vintage/version")
        identifiers.append((identifier, source["dataset_version"]))
    if len(set(identifiers)) != len(identifiers):
        raise ValueError("Duplicate source/version pair")
    return data


def load_registry(path):
    """Load bounded local bytes, with no remote request or registry trust leap."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_REGISTRY_BYTES + 1)
    if len(raw) > MAX_REGISTRY_BYTES:
        raise ValueError("Missing or excessive rights register")
    return _parse_registry_bytes(raw)


def _rights_status_from_registry(registry, source_id, dataset_version, purpose):
    if purpose not in PURPOSES:
        raise ValueError("Unsupported use purpose")
    if not source_id or not dataset_version:
        return PENDING
    matched = [r for r in registry["sources"] if r["source_id"] == source_id
               and r["dataset_version"] == dataset_version]
    if len(matched) != 1:
        return PENDING
    row = matched[0]
    if row.get("decision") != "reviewed":
        return PENDING
    if row.get("rights_status") not in APPROVED_STATUSES:
        return PENDING
    if (not isinstance(row.get("reviewed_by"), str) or
            not row["reviewed_by"].strip() or
            not _valid_utc_time(row.get("reviewed_at_utc")) or
            not isinstance(row.get("terms_url"), str) or
            not row["terms_url"].startswith("https://") or
            not isinstance(row.get("evidence_url"), str) or
            not row["evidence_url"].startswith("https://") or
            not isinstance(row.get("terms_sha256"), str) or
            not _SHA256.fullmatch(row["terms_sha256"]) or
            not isinstance(row.get("attribution"), str) or
            not row["attribution"].strip()):
        return PENDING
    rights = row.get("permitted_uses")
    if not isinstance(rights, dict) or set(rights) != set(PURPOSES):
        return PENDING
    if any(v not in ("allowed", "prohibited", "unreviewed") for v in rights.values()):
        return PENDING
    if rights[purpose] == "allowed":
        return row["rights_status"]
    if rights[purpose] == "prohibited":
        return RESTRICTED
    return PENDING


def rights_status_for(source_id, *, dataset_version, purpose="research", register_path):
    """Return conservative status for a source version and a particular purpose."""
    if purpose not in PURPOSES:
        raise ValueError("Unsupported use purpose")
    try:
        registry = load_registry(register_path)
    except (ValueError, OSError):
        return PENDING
    return _rights_status_from_registry(registry, source_id, dataset_version, purpose)


def rights_receipt(source_id, *, dataset_version, purpose="research", register_path=None):
    """Snapshot a registry read once and produce an auditable sidecar receipt.

    Caller-visible reviewed statuses are *recorded assertions*, never legal
    guarantees. Absence/malformed data always produce review_required.
    """
    import hashlib

    if purpose not in PURPOSES:
        raise ValueError("Unsupported use purpose")
    result = {
        "schema_version": 1,
        "source_id": source_id,
        "dataset_version": dataset_version,
        "purpose": purpose,
        "registry_sha256": None,
        "evaluation": "not_supplied",
        "rights_status": PENDING,
    }
    if register_path is None:
        return result
    try:
        path = Path(register_path)
        with path.open("rb") as stream:
            raw = stream.read(MAX_REGISTRY_BYTES + 1)
        if len(raw) > MAX_REGISTRY_BYTES:
            raise ValueError("Rights register exceeds configured limit")
        # Parse the identical bytes whose fingerprint is returned in the receipt.
        document = _parse_registry_bytes(raw)
    except (OSError, UnicodeError, ValueError):
        result["evaluation"] = "invalid_registry"
        return result
    result["registry_sha256"] = hashlib.sha256(raw).hexdigest()
    result["rights_status"] = _rights_status_from_registry(
        document, source_id, dataset_version, purpose
    )
    result["evaluation"] = (
        "reviewed_record" if result["rights_status"] != PENDING
        else "pending_or_unmatched"
    )
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Offline, fail-closed source-rights audit; NOT legal advice"
    )
    parser.add_argument("--register", required=True, type=Path)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--purpose", choices=PURPOSES, default="research")
    args = parser.parse_args(argv)
    result = {
        "source_id": args.source_id,
        "dataset_version": args.dataset_version,
        "purpose": args.purpose,
        "rights_status": rights_status_for(
            args.source_id, dataset_version=args.dataset_version,
            purpose=args.purpose, register_path=args.register
        ),
        "notice": "A recorded decision is not legal advice or a data redistribution grant.",
    }
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
