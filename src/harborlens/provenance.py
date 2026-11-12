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

from harborlens import __version__
from urllib.parse import urlsplit

FILES = ("houston_clean.csv", "stationary_candidates.csv", "stationary_candidates.geojson")

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


def add_provenance(folder, manifest, source_url=None):
    if source_url is not None:
        parts = urlsplit(source_url)
        if parts.scheme not in ("https", "http") or not parts.netloc or parts.username or parts.password:
            raise ValueError("Source URL must be HTTP(S) without credentials")
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
    record = json.loads(path.read_text(encoding="utf-8"))
    items = record.get("artifacts")
    if not isinstance(items, dict) or set(items) != set(FILES):
        raise ValueError("Invalid artifact manifest")
    results = {}
    for name in FILES:
        expected = items[name]
        if not isinstance(expected, dict) or not isinstance(expected.get("sha256"), str):
            raise ValueError("Invalid artifact hash entry")
        if name in preloaded:
            raw = preloaded[name]
            if not isinstance(raw, (bytes, bytearray)):
                raise ValueError("Invalid preloaded artifact bytes")
            actual = hashlib.sha256(bytes(raw)).hexdigest()
            size = len(raw)
        else:
            file = path.parent / name
            if not file.is_file():
                results[name] = "missing"
                continue
            actual = checksum(file)
            size = file.stat().st_size
        if digests_equal(actual, expected["sha256"]) and size == expected.get("size_bytes"):
            results[name] = "verified"
        else:
            results[name] = "mismatch"
    return {"ok": all(x == "verified" for x in results.values()), "artifacts": results}

def main():
    parser = argparse.ArgumentParser(description="Verify local HarborLens export bytes")
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    result = verify_manifest(args.manifest)
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)
