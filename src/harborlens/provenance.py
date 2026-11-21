"""HarborLens local output integrity and provenance checks.

Byte hashes establish file consistency only; they do not certify dataset
authenticity, rights, or actual vessel behavior.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from harborlens import __version__
from harborlens.cli_usage import add_version_argument
from harborlens.io_safe import AISInputError

FILES = ("houston_clean.csv", "stationary_candidates.csv", "stationary_candidates.geojson")

class ManifestFormatError(ValueError):
    """``manifest.json`` is not a HarborLens artifact manifest."""

def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digests_equal(left, right):
    """Compare a digest, fingerprint or pin without an early content mismatch.

    Hex strings are compared in lowercase. Byte strings are compared as raw
    bytes. The two sides must be the same kind and the same length; anything
    else is unequal. ``hmac.compare_digest`` covers the equal-length content.
    """
    try:
        if isinstance(left, str) and isinstance(right, str):
            left, right = left.lower(), right.lower()
            if len(left) != len(right):
                return False
            return hmac.compare_digest(left, right)
        if isinstance(left, (bytes, bytearray)) and isinstance(right, (bytes, bytearray)):
            left, right = bytes(left), bytes(right)
            if len(left) != len(right):
                return False
            return hmac.compare_digest(left, right)
    except (TypeError, ValueError):
        return False
    return False

def code_version():
    """Package version (part of run identity) and, in CI, the git commit (metadata only).

    The commit comes from ``GITHUB_SHA`` or ``HARBORLENS_GIT_COMMIT`` when it is a
    40-hex SHA; it is recorded but not hashed into run IDs, so identical code gives
    identical run IDs locally and in CI. Bump the package version on any change
    that can alter outputs.
    """
    commit = os.environ.get("HARBORLENS_GIT_COMMIT") or os.environ.get("GITHUB_SHA") or ""
    return {"package_version": __version__,
            "git_commit": commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None}


_SOURCE_URL_MESSAGE = (
    "source URL must be http or https, must name a host, and must not include credentials"
)


def require_declared_source_url(source_url):
    """Accept a missing URL or an HTTP(S) URL with a host and no userinfo.

    ``None`` means ``--source-url`` was omitted. An empty string, a URL with
    no host (``http://``, ``https:///path``), a scheme other than ``http`` or
    ``https`` (``ftp://x``), and a URL that carries a username or password
    raise ``AISInputError``. This does not fetch the URL and does not change
    ``rights_status``.
    """
    if source_url is None:
        return
    if not isinstance(source_url, str):
        raise AISInputError(_SOURCE_URL_MESSAGE)
    parts = urlsplit(source_url)
    if (parts.scheme not in ("https", "http") or not parts.netloc
            or parts.username or parts.password):
        raise AISInputError(_SOURCE_URL_MESSAGE)


def add_provenance(folder, manifest, source_url=None):
    require_declared_source_url(source_url)
    settings = {"input_sha256": manifest["input_sha256"], "bbox_lon_lat": manifest["bbox_lon_lat"],
                "method_parameters": manifest["method_parameters"],
                "method_version": manifest["method_parameters"].get("method_version", "stationary-v0.1"),
                "harborlens_version": __version__}
    window = manifest.get("analysis_window") or {}
    if window.get("status") == "known":
        # A known window changes censoring outputs, so it is part of run identity.
        # Runs without a window keep the legacy run_id derivation.
        settings["analysis_window"] = [[b["start_utc"], b["end_utc"]] for b in window["blocks"]]
    manifest["run_id"] = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest["provenance_schema_version"] = "1.1"
    manifest["code_version"] = code_version()
    manifest["source_metadata"] = {"source_url": source_url, "metadata_origin": "user_declared",
                                   "rights_status": "review_required"}
    manifest["artifacts"] = {
        name: {"sha256": checksum(Path(folder) / name), "size_bytes": (Path(folder) / name).stat().st_size}
        for name in FILES
    }
    manifest["provenance_warning"] = "Integrity hashes do not establish source authenticity, data rights or verified events."
    return manifest

def verify_manifest(path, preloaded=None):
    """Check artifact SHA-256 and size against the manifest.

    ``preloaded`` maps an artifact name to bytes already read by the caller.
    Those names are hashed from that buffer and are not opened again, so a
    release recount can share one read with this check.
    """
    path = Path(path)
    preloaded = {} if preloaded is None else preloaded
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestFormatError("Invalid artifact manifest") from exc
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestFormatError("Invalid artifact manifest") from exc
    items = record.get("artifacts") if isinstance(record, dict) else None
    if not isinstance(items, dict) or set(items) != set(FILES):
        raise ManifestFormatError("Invalid artifact manifest")
    results = {}
    for name in FILES:
        expected = items[name]
        if not isinstance(expected, dict) or not isinstance(expected.get("sha256"), str):
            raise ManifestFormatError("Invalid artifact hash entry")
        if name in preloaded:
            raw = preloaded[name]
            if not isinstance(raw, (bytes, bytearray)):
                raise ManifestFormatError("Invalid preloaded artifact bytes")
            actual = hashlib.sha256(bytes(raw)).hexdigest()
            size = len(raw)
        else:
            file = path.parent / name
            try:
                is_file = file.is_file()
            except OSError:
                results[name] = "unreadable"
                continue
            if not is_file:
                results[name] = "missing"
                continue
            try:
                actual = checksum(file)
                size = file.stat().st_size
            except OSError:
                results[name] = "unreadable"
                continue
        if digests_equal(actual, expected["sha256"]) and size == expected.get("size_bytes"):
            results[name] = "verified"
        else:
            results[name] = "mismatch"
    return {"ok": all(x == "verified" for x in results.values()), "artifacts": results}

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Verify SHA-256 and sizes of a HarborLens run against manifest.json. "
            "This checks local bytes only; it does not prove source authenticity, "
            "data rights, or verified events."
        )
    )
    add_version_argument(parser)
    parser.add_argument(
        "--manifest", required=True, type=Path,
        help="path to the manifest.json written by harborlens (required)",
    )
    args = parser.parse_args()
    try:
        result = verify_manifest(args.manifest)
    except ManifestFormatError:
        parser.error(f"manifest '{args.manifest}' is not a valid HarborLens manifest")
    except OSError as exc:
        detail = exc.strerror if exc.strerror else type(exc).__name__
        parser.error(
            f"cannot read manifest '{args.manifest}' ({detail}). "
            "Give --manifest the manifest.json written by harborlens."
        )
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)
