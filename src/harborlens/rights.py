"""Fail-closed, offline source-rights decision gate (SPEC-003, issue #42).

A published catalog link or public URL is not a legal review. Only an explicit,
version-matched reviewer decision can change the default "review_required".
This module does not download data, modify source evidence, or give legal advice.
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

MAX_REGISTRY_BYTES = 256 * 1024
PURPOSES = ("research", "public_aggregates", "commercial")
APPROVED_STATUSES = (
    "reviewed_public_domain_attribution_required",
    "reviewed_permitted_with_conditions",
)
PENDING = "review_required"
RESTRICTED = "use_restricted"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
# Same strings as schemas/v1/source-rights-register.schema.json. ASCII
# hostnames only: punycode is accepted, IPv6 literals and raw IDN are not.
# Whitespace anywhere in the URL, including a trailing path space, fails.
# ``(?![\s\S])`` is the end of the string. ``$`` would still match before a
# trailing newline, and a newline is not part of an https URL or a timestamp.
_HTTPS_URL_PATTERN = (
    r"^https://[A-Za-z0-9][A-Za-z0-9.-]*[A-Za-z0-9]"
    r"(?::[0-9]{1,5})?(?:[/?#]\S*)?(?![\s\S])"
)
# ASCII digits only. No fraction, or 1 to 6 fractional digits. Suffix is
# Z or +00:00. ``(?![\s\S])`` is the end of the string; ``$`` would still
# match before a trailing newline. This is the same string as the schema.
_UTC_TIMESTAMP_PATTERN = (
    r"^([0-9]{4})-([0-9]{2})-([0-9]{2})"
    r"T([0-9]{2}):([0-9]{2}):([0-9]{2})"
    r"(?:\.([0-9]{1,6}))?"
    r"(?:Z|\+00:00)"
    r"(?![\s\S])"
)
_HTTPS_URL = re.compile(_HTTPS_URL_PATTERN)
_UTC_TIMESTAMP = re.compile(_UTC_TIMESTAMP_PATTERN)
_UTF8_BOM = b"\xef\xbb\xbf"
_UTF8_BOM_ERROR = "Rights register has a UTF-8 BOM"
_NOTICE = "A recorded decision is not legal advice or a data redistribution grant."
_MISSING_JSONSCHEMA = (
    "Rights register schema validator is unavailable; "
    "pip install 'harborlens[rights]'"
)


def _is_https_url(value):
    """True only for an https URL the rights schema also accepts.

    The hostname is ASCII (letters, digits, dots, hyphens), at least two
    characters, and not only dots. Punycode (``xn--``) is accepted. IPv6
    literals, raw IDN hostnames, userinfo, an uppercase scheme, and any
    whitespace — including a trailing space or tab on the path — are rejected.
    ``netloc`` alone would accept ``https://user@example.org`` and
    ``https://example.org/terms ``.
    """
    if not isinstance(value, str) or _HTTPS_URL.fullmatch(value) is None:
        return False
    try:
        parts = urlsplit(value)
        host = parts.hostname
    except ValueError:
        return False
    if parts.scheme != "https" or parts.username is not None or parts.password is not None:
        return False
    if not isinstance(host, str) or not host or not host.strip("."):
        return False
    if any(ch.isspace() for ch in host) or ":" in host:
        return False
    return True


def _load_jsonschema():
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import SchemaError, ValidationError
    return Draft202012Validator, SchemaError, ValidationError


def _read_packaged_schema():
    """Read the schema shipped inside this package.

    ``importlib.resources`` only. Searching parent directories would let a
    foreign file next to a virtualenv replace the contract.
    """
    try:
        text = files("harborlens").joinpath(
            "schemas", "v1", "source-rights-register.schema.json"
        ).read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError, TypeError) as exc:
        raise ValueError("Rights register schema is unreadable") from exc
    if not text.strip():
        raise ValueError("Rights register schema is unreadable")
    return text


def _validate_registry_schema(data):
    """Reject registers that do not match the packaged source-rights schema."""
    try:
        validator_cls, schema_error, validation_error = _load_jsonschema()
    except ImportError as exc:
        raise ValueError(_MISSING_JSONSCHEMA) from exc
    try:
        schema = json.loads(_read_packaged_schema())
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Rights register schema is unreadable") from exc
    try:
        validator_cls(schema).validate(data)
    except (validation_error, schema_error) as exc:
        raise ValueError("Rights register failed schema validation") from exc


def _valid_utc_time(value):
    """True for a schema-shaped UTC timestamp that is a real calendar time.

    Accepted shape, on Python 3.10 and 3.12 alike: ASCII
    ``YYYY-MM-DDTHH:MM:SS`` with no fraction or with 1 to 6 fractional
    digits, then ``Z`` or ``+00:00``. Seven or more fractional digits, any
    other offset, a lowercase ``z`` or ``t``, a space separator, and
    non-ASCII digits do not match. The clock is built with ``datetime``
    from those captured fields. The fraction is padded to six digits.
    ``datetime`` rejects an impossible calendar value (31 February, 29
    February in a non-leap year, hour 24, minute 60, second 60), so that
    value stays unapproved. This function does not call the ISO parser.
    """
    if not isinstance(value, str):
        return False
    match = _UTC_TIMESTAMP.fullmatch(value)
    if match is None:
        return False
    year, month, day, hour, minute, second, fraction = match.groups()
    microsecond = int(fraction.ljust(6, "0")) if fraction is not None else 0
    try:
        parsed = datetime(
            int(year), int(month), int(day),
            int(hour), int(minute), int(second),
            microsecond, tzinfo=timezone.utc,
        )
    except ValueError:
        return False
    return parsed.tzinfo is timezone.utc and parsed.utcoffset().total_seconds() == 0


def _load_registry_bytes(raw):
    """Validate one register buffer with the packaged schema.

    ``raw`` is parsed as UTF-8 JSON and checked with the schema shipped inside
    this package (``importlib.resources`` only). A leading UTF-8 BOM is a
    named load error and is not stripped. The same structural errors as
    ``load_registry`` are raised. URL and timestamp rules are enforced by
    that schema and again by ``_is_https_url`` and ``_valid_utc_time`` when
    a decision is made. Unknown, malformed, or whitespace-only evidence does
    not grant an approved status.
    """
    if not isinstance(raw, (bytes, bytearray)) or len(raw) > MAX_REGISTRY_BYTES:
        raise ValueError("Missing or excessive rights register")
    blob = bytes(raw)
    if blob.startswith(_UTF8_BOM):
        raise ValueError(_UTF8_BOM_ERROR)
    try:
        data = json.loads(blob.decode("utf-8"))
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
    _validate_registry_schema(data)
    return data


def load_registry(path):
    """Load an explicit local decision record; never fetch from the network."""
    target = Path(path)
    if not target.is_file() or target.stat().st_size > MAX_REGISTRY_BYTES:
        raise ValueError("Missing or excessive rights register")
    try:
        raw = target.read_bytes()
    except OSError as exc:
        raise ValueError("Rights register is unreadable") from exc
    return _load_registry_bytes(raw)


def _rights_status_from_registry(document, source_id, dataset_version, purpose):
    """Decide from an already validated register document."""
    if purpose not in PURPOSES:
        raise ValueError("Unsupported use purpose")
    if not source_id or not dataset_version:
        return PENDING
    records = document["sources"]
    matched = [r for r in records if r["source_id"] == source_id
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
            not _is_https_url(row.get("terms_url")) or
            not _is_https_url(row.get("evidence_url")) or
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
    """Return only conservative decisions for an exact source, vintage and use.

    Invalid or absent records fail closed to review_required. A reviewer entry
    is an audit assertion, not cryptographic authentication or legal approval.
    """
    if purpose not in PURPOSES:
        raise ValueError("Unsupported use purpose")
    if not source_id or not dataset_version:
        return PENDING
    try:
        document = load_registry(register_path)
    except (ValueError, OSError):
        return PENDING
    return _rights_status_from_registry(
        document, source_id, dataset_version, purpose
    )


def rights_receipt(source_id, *, dataset_version, purpose="research", register_path=None):
    """Return a sidecar receipt for one in-memory read of a local register.

    The path is read once. That buffer is parsed and schema-validated, and
    both the SHA-256 and the decision come from it. The path is not opened
    again. The schema is the packaged file via ``importlib.resources`` only.
    A missing, unreadable, oversized, BOM-prefixed, or schema-invalid
    register is ``invalid_registry`` and ``review_required``. A recorded
    status is an audit assertion, not legal advice or a redistribution grant.
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
        if not path.is_file() or path.stat().st_size > MAX_REGISTRY_BYTES:
            raise ValueError("Missing or excessive rights register")
        raw = path.read_bytes()
        document = _load_registry_bytes(raw)
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
        "notice": _NOTICE,
    }
    # Load errors must not look like a pending decision. rights_status_for still
    # fails closed to review_required for library callers; the CLI reports them
    # separately so a broken register is not silent success.
    try:
        document = load_registry(args.register)
    except (ValueError, OSError) as exc:
        result["rights_status"] = PENDING
        result["error"] = str(exc)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    result["rights_status"] = _rights_status_from_registry(
        document, args.source_id, args.dataset_version, args.purpose
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["rights_status"] in APPROVED_STATUSES:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
