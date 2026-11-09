"""HarborLens local output integrity and provenance checks.

Byte hashes establish file consistency only; they do not certify dataset
authenticity, rights, or actual vessel behavior.
"""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

FILES = ("houston_clean.csv", "stationary_candidates.csv", "stationary_candidates.geojson")

def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def add_provenance(folder, manifest, source_url=None):
    if source_url is not None:
        parts = urlsplit(source_url)
        if parts.scheme not in ("https", "http") or not parts.netloc or parts.username or parts.password:
            raise ValueError("Source URL must be HTTP(S) without credentials")
    settings = {"input_sha256": manifest["input_sha256"], "bbox_lon_lat": manifest["bbox_lon_lat"],
                "method_parameters": manifest["method_parameters"], "method_version": "stationary-v0.1"}
    window = manifest.get("analysis_window") or {}
    if window.get("status") == "known":
        # A known window changes censoring outputs, so it is part of run identity.
        # Runs without a window keep the legacy run_id derivation.
        settings["analysis_window"] = [[b["start_utc"], b["end_utc"]] for b in window["blocks"]]
    manifest["run_id"] = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest["provenance_schema_version"] = "1.1"
    manifest["source_metadata"] = {"source_url": source_url, "metadata_origin": "user_declared",
                                   "rights_status": "review_required"}
    manifest["artifacts"] = {
        name: {"sha256": checksum(Path(folder) / name), "size_bytes": (Path(folder) / name).stat().st_size}
        for name in FILES
    }
    manifest["provenance_warning"] = "Integrity hashes do not establish source authenticity, data rights or verified events."
    return manifest

def verify_manifest(path):
    path = Path(path)
    record = json.loads(path.read_text(encoding="utf-8"))
    items = record.get("artifacts")
    if not isinstance(items, dict) or set(items) != set(FILES):
        raise ValueError("Invalid artifact manifest")
    results = {}
    for name in FILES:
        expected = items[name]
        if not isinstance(expected, dict) or not isinstance(expected.get("sha256"), str):
            raise ValueError("Invalid artifact hash entry")
        file = path.parent / name
        if not file.is_file():
            results[name] = "missing"
        elif checksum(file) == expected["sha256"] and file.stat().st_size == expected.get("size_bytes"):
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
