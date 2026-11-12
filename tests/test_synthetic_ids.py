"""Guard for synthetic vessel identifiers (SPEC-001, FR-001, FR-002, BR-008, BR-016).

Committed synthetic MMSIs use unassigned MID 199, form ``1990xxxxx``.
The guard fails when a nine-digit token's MID is in the assigned range 201-775.

The scan reads every text file ``git ls-files`` tracks, plus untracked files
that are not gitignored, so a planted negative uses the same path. Paths are
classified relative to the repository root. A binary file (a NUL byte, or
bytes that are not UTF-8) is skipped and counted.

A candidate is nine digits bounded by a non-digit. A longer digit run does
not match. Nine digits are a decimal fraction only when a digit precedes the
dot (``29.123456789``). A dot that is not part of a decimal (``id.`` before
nine digits) still matches. The MID is the first three digits. The previous
guard did not read digits 2-4 of a leading-0 or leading-9 form, and this
guard does not either.

The repository scan applies that rule to the raw text. It is not limited to
an ``mmsi`` column, a ``vessel_id`` column, or a JSON key named ``mmsi``.

Exclusions are file-exact or context-based. Each one has a written reason.

* ``tests/fixtures/single_day_0.2.0.dev9/`` is the package 0.2.0.dev9 golden.
  It is kept as the input of the mapping proof: the proof substitutes legacy
  ids in those bytes and compares them with ``single_day_0.2.0.dev15``.
  Each of those files is excluded by its exact path. A new file in that
  directory is scanned. The directory still contains MID 367.
* ``tests/synthetic_id_map.py`` is the mapping table. Its keys are the retired
  identifiers, including one former Marshall Islands MID. The same identifiers
  anywhere else still fail the guard.
* A nine-digit run inside a hexadecimal run of 64 or more characters is a
  SHA-256 digest or a longer hex blob, not a vessel id. A standalone token
  in the same file still fails.
* The value assigned by a whole-word ``mmap_size`` is ignored. In
  ``tests/multiday_memory_probe.py`` that value is a 256 MiB byte count
  (``PRAGMA mmap_size=`` or ``mmap_size =``). Only the token that starts
  immediately after the ``=`` is ignored. The same digits anywhere else fail.

The byte-identity proof starts from the dev9 goldens, applies
``SYNTHETIC_ID_MAP``, then recomputes only the ID-derived fields with
``hashlib``. It does not call the pipeline. ``mmsi_category`` changes from
``ship`` to ``other`` only on rows whose identifier was mapped.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from synthetic_id_map import SYNTHETIC_ID_MAP, SYNTHETIC_ID_RULES

ROOT = Path(__file__).resolve().parents[1]
DEV9 = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev9"
DEV15 = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev15"
FR_EVIDENCE = ROOT / "docs" / "data" / "fr-2023-original-fulltext-evidence-2026-11-09.md"
MAP_SOURCE = ROOT / "tests" / "synthetic_id_map.py"

ASSIGNED_MID_LOW = 201
ASSIGNED_MID_HIGH = 775
# Nine digits, not part of a longer digit run. A decimal fraction is nine
# digits after a digit and a dot (``(?<!\d\.)``). Any other dot still matches.
TOKEN_9 = re.compile(r"(?<!\d\.)(?<!\d)(\d{9})(?!\d)")
# An f-string whose literal digit prefix selects an assigned MID has no
# nine-digit token until runtime. Covers f/F, fr/rf in either case, and
# single or triple quotes. A raw string with no f is not a match.
FSTRING_PREFIX = re.compile(
    r"""(?<![A-Za-z0-9_])(?:[fF][rR]?|[rR][fF])(?P<quote>'''|\"\"\"|['\"])(?P<prefix>\d{3,8})\{"""
)
# SHA-256 is 64 hex characters. Longer hex blobs are ignored the same way.
HEX_BLOB = re.compile(r"[0-9a-fA-F]{64,}")
FORBIDDEN_PREFIXES = ("111", "970", "972", "974", "98", "99", "0")

# Exact relative path, reason. A directory prefix is not an exclusion.
# The dev9 names are the files ``git ls-files`` lists in that directory.
EXCLUSIONS = (
    (
        "tests/fixtures/single_day_0.2.0.dev9/houston_clean.csv",
        "Historical cleaned CSV for package 0.2.0.dev9. Retained as a mapping-proof "
        "input so legacy MID 367 identifiers can be substituted and compared with "
        "tests/fixtures/single_day_0.2.0.dev15. It is not a current vessel-id source.",
    ),
    (
        "tests/fixtures/single_day_0.2.0.dev9/stationary_candidates.csv",
        "Historical candidate CSV for package 0.2.0.dev9. Retained as a mapping-proof "
        "input. Its MMSI column still contains legacy MID 367 identifiers. It is not "
        "a current vessel-id source.",
    ),
    (
        "tests/fixtures/single_day_0.2.0.dev9/stationary_candidates.geojson",
        "Historical candidate GeoJSON for package 0.2.0.dev9. Retained as a mapping-proof "
        "input. Its mmsi properties still contain legacy MID 367 identifiers. It is not "
        "a current vessel-id source.",
    ),
    (
        "tests/fixtures/single_day_0.2.0.dev9/manifest.json",
        "Historical run manifest for package 0.2.0.dev9. Retained as a mapping-proof "
        "input beside the other three golden files. It is not a current vessel-id source.",
    ),
    (
        "tests/synthetic_id_map.py",
        "Mapping table. Legacy identifiers appear only as the keys this change "
        "retires, including one former Marshall Islands MID. Every key is an "
        "assigned MID and every value is 1990xxxxx. The same legacy identifier "
        "outside this file still fails the guard. The file is excluded by its "
        "exact path so the proof can keep those keys.",
    ),
)
EXCLUSION_PATHS = {path for path, _reason in EXCLUSIONS}

# Context exclusions. These are not path allowlists. The same digits outside
# the context still fail. Each entry is (name, reason).
CONTEXT_EXCLUSIONS = (
    (
        "hex-run-64-or-longer",
        "A nine-digit run inside a hexadecimal run of 64 or more characters "
        "is a SHA-256 digest or a longer hex blob, not a vessel identifier. "
        "A standalone nine-digit token in the same file still fails.",
    ),
    (
        "mmap-size-assignment",
        "The nine-digit value assigned by a whole-word mmap_size is a byte "
        "count. Only the token that starts immediately after mmap_size = is "
        "ignored. In tests/multiday_memory_probe.py that value is 256 MiB. "
        "The same digits in not_mmap_size, earlier on the line, or in any "
        "other assignment still fail.",
    ),
)

# Files harborlens-verify hashes, and the cleaned CSV the release recount reads.
VERIFY_ARTIFACTS = (
    "houston_clean.csv",
    "stationary_candidates.csv",
    "stationary_candidates.geojson",
)
MMAP_SIZE_ASSIGNMENT = re.compile(r"\bmmap_size\s*=\s*")


def mid_is_assigned(mid):
    """True when ``mid`` is in the assigned MID block 201-775 inclusive."""
    return ASSIGNED_MID_LOW <= int(mid) <= ASSIGNED_MID_HIGH


def _assigned_nine(value):
    text = str(value).strip()
    if re.fullmatch(r"\d{9}", text) and mid_is_assigned(text[:3]):
        return text
    return None


def csv_mmsi_hits(text):
    """Nine-digit assigned-MID values in a column named MMSI.

    The repository scan does not use this helper. It calls ``text_hits`` on
    the raw file, so a ``vessel_id`` column is visible there.
    """
    hits = []
    try:
        rows = csv.reader(io.StringIO(text))
        header = next(rows, None)
    except csv.Error:
        return hits
    if not header:
        return hits
    indexes = [i for i, name in enumerate(header) if name.strip().lower() == "mmsi"]
    if not indexes:
        return hits
    for row in rows:
        for index in indexes:
            if index >= len(row):
                continue
            found = _assigned_nine(row[index])
            if found:
                hits.append(found)
    return hits


def json_mmsi_hits(text):
    """Nine-digit assigned-MID values of a key named mmsi.

    The repository scan does not use this helper. ``text_hits`` sees every
    JSON key and value.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return []
    hits = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() == "mmsi":
                    found = _assigned_nine(value)
                    if found:
                        hits.append(found)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return hits


def _inside_hex_blob(text, start, end):
    for match in HEX_BLOB.finditer(text):
        if match.start() <= start and end <= match.end():
            return True
    return False


def text_hits(text):
    """Assigned-MID tokens in any text.

    The MID is the first three digits. A leading-0 or leading-9 form does not
    move the MID to digits 2-4; the previous guard did not do that.

    A nine-digit token inside a hex run of 64 or more characters is not a
    vessel id (``hex-run-64-or-longer``). The token that starts immediately
    after a whole-word ``mmap_size`` assignment is a byte count
    (``mmap-size-assignment``). The same digits outside that value are a hit.
    An f-string prefix whose first three digits are an assigned MID is a hit
    even when the format field completes the nine digits at runtime. The
    prefix may be ``f`` or ``F``, with an optional ``r`` on either side, and
    the quote may be single or triple.
    """
    hits = []
    mmap_values = {match.end() for match in MMAP_SIZE_ASSIGNMENT.finditer(text)}
    for match in TOKEN_9.finditer(text):
        token = match.group(1)
        if _inside_hex_blob(text, match.start(), match.end()):
            continue
        if match.start() in mmap_values:
            continue
        if mid_is_assigned(token[:3]):
            hits.append(token)
    for match in FSTRING_PREFIX.finditer(text):
        prefix = match.group("prefix")
        if mid_is_assigned(prefix[:3]):
            hits.append(prefix + "{...}")
    return hits


def python_source_hits(text):
    """Earlier name for ``text_hits``. The repository scan calls ``text_hits``."""
    return text_hits(text)


def relative_posix(path, root=ROOT):
    """Path relative to the repository root, with ``/`` separators.

    ``Path.parts[0]`` on an absolute path is ``/``. Classification uses this
    string, not the absolute parts.
    """
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def path_is_excluded(path, root=ROOT):
    """True only when the relative path is one exact exclusion entry."""
    return relative_posix(path, root) in EXCLUSION_PATHS


class GitUnavailable(RuntimeError):
    """``git ls-files`` could not be run.

    The coverage test calls ``skipTest`` with this message when the
    environment variable ``CI`` is not the string ``true``. When ``CI`` is
    ``true`` that test fails instead of skipping.
    """


def _git_ls_files(root, others=False):
    """Tracked paths, or untracked paths that are not gitignored.

    Paths are relative to ``root``. ``git`` is invoked with ``-C`` so the
    result does not depend on the process working directory.
    """
    command = ["git", "-C", str(root), "ls-files", "-z"]
    if others:
        command.extend(["--others", "--exclude-standard"])
    try:
        listed = subprocess.check_output(command, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise GitUnavailable("git executable was not found") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        message = detail or f"git ls-files exited {exc.returncode}"
        raise GitUnavailable(message) from exc
    return [item.decode("utf-8") for item in listed.split(b"\0") if item]


def read_tracked_text(path):
    """Return decoded text, or None when the file is binary.

    Binary means a NUL byte is present, or the bytes are not UTF-8. The
    caller counts None and does not search it for tokens.
    """
    data = Path(path).read_bytes()
    if b"\0" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def extension_key(relative):
    """Lowercase suffix, or ``<none>`` when the tracked name has no suffix."""
    suffix = Path(relative).suffix.lower()
    return suffix if suffix else "<none>"


def scan_repository(root=ROOT):
    """Scan every tracked text file, plus untracked files git does not ignore.

    ``git ls-files`` supplies the tracked set. ``git ls-files --others
    --exclude-standard`` adds a file a test just wrote, so a planted negative
    uses this function. File-exact exclusions are skipped before the read.
    A binary file is skipped and recorded under ``binaries``.

    Returns ``(hits, coverage)``. ``hits`` are ``(relative path, token)``.
    ``coverage`` has ``visited`` (text files searched), ``binaries``, and
    ``tracked``. Every path is relative to ``root``.
    """
    root = Path(root)
    tracked = _git_ls_files(root)
    extras = _git_ls_files(root, others=True)
    hits = []
    visited = []
    binaries = []
    for relative in dict.fromkeys([*tracked, *extras]):
        if relative in EXCLUSION_PATHS:
            continue
        path = root / relative
        if not path.is_file():
            continue
        text = read_tracked_text(path)
        if text is None:
            binaries.append(relative)
            continue
        visited.append(relative)
        for hit in text_hits(text):
            hits.append((relative, hit))
    return hits, {"visited": visited, "binaries": binaries, "tracked": tracked}


def substitute_legacy_ids(data, mapping=None):
    """Replace legacy synthetic ids as whole tokens. No other bytes change."""
    mapping = SYNTHETIC_ID_MAP if mapping is None else mapping
    text = data.decode("utf-8")
    for legacy, modern in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"(?<!\d){legacy}(?!\d)", modern, text)
    return text.encode("utf-8")


def mapped_mmsi_images(mapping=None):
    mapping = SYNTHETIC_ID_MAP if mapping is None else mapping
    return set(mapping.values())


def package_version_text():
    """Package version string.

    Defined as ``__version__`` in ``src/harborlens/__init__.py``.
    ``harborlens.provenance.code_version`` copies it into
    ``code_version.package_version``. Read as text so this proof does not
    import the package.
    """
    source = (ROOT / "src" / "harborlens" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', source, re.MULTILINE)
    if match is None:
        raise AssertionError("package version is not defined")
    return match.group(1)


def event_id_digest(mmsi, start, end, method_version, parameter_set):
    """First 18 hex characters of SHA-256(mmsi|start|end|method|parameter_set).

    Defined in ``harborlens.segmentation`` where ``Segmenter`` builds
    ``event_id`` (the ``hashlib.sha256`` call on that joined string).
    """
    payload = f"{mmsi}|{start}|{end}|{method_version}|{parameter_set}".encode()
    return hashlib.sha256(payload).hexdigest()[:18]


def input_sha256_digest(path):
    """SHA-256 of the input file bytes.

    Defined as ``harborlens.ais.sha256``, stored on the manifest as
    ``input_sha256`` by ``ingest``.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_id_digest(manifest, version):
    """SHA-256 of the canonical run-identity JSON.

    Defined in ``harborlens.provenance.add_provenance``. The hashed object is
    ``input_sha256``, ``bbox_lon_lat``, ``method_parameters``,
    ``method_version``, and ``harborlens_version``. A known analysis window
    adds ``analysis_window`` as ``[start_utc, end_utc]`` pairs. An unknown
    window is not hashed. Encoding is ``sort_keys`` and ``separators=(",", ":")``.
    """
    settings = {
        "input_sha256": manifest["input_sha256"],
        "bbox_lon_lat": manifest["bbox_lon_lat"],
        "method_parameters": manifest["method_parameters"],
        "method_version": manifest["method_parameters"].get("method_version", "stationary-v0.1"),
        "harborlens_version": version,
    }
    window = manifest.get("analysis_window") or {}
    if window.get("status") == "known":
        settings["analysis_window"] = [[block["start_utc"], block["end_utc"]] for block in window["blocks"]]
    encoded = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _line_ending(line):
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _flip_mapped_category(body, mmsi, category, images):
    """Change a trailing ``ship`` category to ``other`` only for a mapped id."""
    if mmsi in images and category == "ship" and body.endswith("ship"):
        return body[:-len("ship")] + "other"
    return body


def project_cleaned_csv(data, mapping=None):
    """Map ids, then set ``mmsi_category`` from ``ship`` to ``other`` on those rows.

    ``ingest`` writes ``mmsi_category(mmsi)`` on each cleaned row
    (``harborlens.ais``). MID 199 is ``other`` because the first digit is not
    in ``2``–``7`` (``harborlens.vessel.mmsi_category``).
    """
    images = mapped_mmsi_images(mapping)
    text = substitute_legacy_ids(data, mapping).decode("utf-8")
    lines = text.splitlines(keepends=True)
    projected = [lines[0]]
    for line in lines[1:]:
        if not line.strip():
            projected.append(line)
            continue
        ending = _line_ending(line)
        body = line[:-len(ending)] if ending else line
        row = next(csv.reader([body]))
        body = _flip_mapped_category(body, row[0], row[-1], images)
        projected.append(body + ending)
    return "".join(projected).encode("utf-8")


def project_candidates_csv(data, mapping=None):
    """Map ids, recompute ``event_id``, and flip ``ship`` to ``other`` on those rows."""
    images = mapped_mmsi_images(mapping)
    text = substitute_legacy_ids(data, mapping).decode("utf-8")
    lines = text.splitlines(keepends=True)
    header = next(csv.reader([lines[0].strip("\r\n")]))
    index = {name: position for position, name in enumerate(header)}
    projected = [lines[0]]
    for line in lines[1:]:
        if not line.strip():
            projected.append(line)
            continue
        ending = _line_ending(line)
        body = line[:-len(ending)] if ending else line
        row = next(csv.reader([body]))
        mmsi = row[index["mmsi"]]
        if mmsi in images:
            old_id = row[index["event_id"]]
            new_id = event_id_digest(
                mmsi, row[index["start_utc"]], row[index["end_utc"]],
                row[index["method_version"]], row[index["parameter_set"]],
            )
            if body.startswith(old_id):
                body = new_id + body[len(old_id):]
            body = _flip_mapped_category(body, mmsi, row[index["mmsi_category"]], images)
        projected.append(body + ending)
    return "".join(projected).encode("utf-8")


def project_candidates_geojson(data, mapping=None):
    """Map ids, recompute ``event_id``, and flip ``ship`` to ``other`` on those features.

    Serialization is ``json.dumps(..., indent=2)``, the writer in
    ``harborlens.ais.write_events``.
    """
    images = mapped_mmsi_images(mapping)
    document = json.loads(substitute_legacy_ids(data, mapping).decode("utf-8"))
    for feature in document["features"]:
        props = feature["properties"]
        if props.get("mmsi") not in images:
            continue
        props["event_id"] = event_id_digest(
            props["mmsi"], props["start_utc"], props["end_utc"],
            props["method_version"], props["parameter_set"],
        )
        if props.get("mmsi_category") == "ship":
            props["mmsi_category"] = "other"
    return json.dumps(document, indent=2).encode("utf-8")


def category_counts(cleaned):
    """Category histogram in first-seen order.

    ``ingest`` increments ``mmsi_categories`` once per written row
    (``harborlens.ais``).
    """
    counts = {}
    for row in csv.DictReader(io.StringIO(cleaned.decode("utf-8"))):
        category = row["mmsi_category"]
        counts[category] = counts.get(category, 0) + 1
    return counts


def project_manifest(data, artifacts, version=None):
    """Map ids, then recompute the ID-derived manifest fields.

    ``input_sha256`` is the fixture digest (``ais.sha256``).
    ``code_version.package_version`` is ``__version__`` unless ``version``
    is passed. A pin of ``0.2.0.dev15`` reproduces that golden manifest.
    The live version changes ``package_version`` and ``run_id`` only.
    ``mmsi_categories`` is the cleaned-row histogram after the ship-to-other
    flip on mapped rows. ``run_id`` is ``run_id_digest``. Artifact ``sha256``
    and ``size_bytes`` are SHA-256 and length of the projected artifact bytes,
    the check ``harborlens.provenance.add_provenance`` stores and
    ``verify_manifest`` repeats. The manifest text is ``json.dumps`` with
    indent 2 plus a trailing newline, matching the committed golden.
    """
    manifest = json.loads(substitute_legacy_ids(data).decode("utf-8"))
    if version is None:
        version = package_version_text()
    manifest["input_sha256"] = input_sha256_digest(ROOT / "tests" / "fixtures" / "synthetic_ais.csv")
    manifest["code_version"]["package_version"] = version
    manifest["mmsi_categories"] = category_counts(artifacts["houston_clean.csv"])
    manifest["run_id"] = run_id_digest(manifest, version)
    for name in VERIFY_ARTIFACTS:
        body = artifacts[name]
        manifest["artifacts"][name] = {
            "sha256": hashlib.sha256(body).hexdigest(),
            "size_bytes": len(body),
        }
    return (json.dumps(manifest, indent=2) + "\n").encode("utf-8")


def project_dev9(mapping=None, source=DEV9, version=None):
    """dev9 goldens after the mapping and the ID-derived recomputation.

    ``mapping`` defaults to ``SYNTHETIC_ID_MAP``. ``source`` defaults to the
    committed golden directory. Callers that pass another directory must not
    point it at the committed files when they intend to mutate bytes.
    ``version`` defaults to ``__version__``. Pass ``0.2.0.dev15`` to reproduce
    the committed golden manifest.
    """
    source = Path(source)
    artifacts = {
        "houston_clean.csv": project_cleaned_csv(
            (source / "houston_clean.csv").read_bytes(), mapping
        ),
        "stationary_candidates.csv": project_candidates_csv(
            (source / "stationary_candidates.csv").read_bytes(), mapping
        ),
        "stationary_candidates.geojson": project_candidates_geojson(
            (source / "stationary_candidates.geojson").read_bytes(), mapping
        ),
    }
    artifacts["manifest.json"] = project_manifest(
        (source / "manifest.json").read_bytes(), artifacts, version=version
    )
    return artifacts


def independent_verify(files):
    """Hash and size check from ``harborlens.provenance.verify_manifest``.

    Computed here with ``hashlib`` only. ``ok`` is true when every artifact
    digest and byte length matches the manifest entry.
    """
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    results = {}
    for name in VERIFY_ARTIFACTS:
        body = files[name]
        expected = manifest["artifacts"][name]
        digest = hashlib.sha256(body).hexdigest()
        if digest == expected["sha256"] and len(body) == expected["size_bytes"]:
            results[name] = "verified"
        else:
            results[name] = "mismatch"
    return {"ok": all(item == "verified" for item in results.values()), "artifacts": results}


def _csv_diffs(before, after):
    left = list(csv.DictReader(io.StringIO(before.decode("utf-8"))))
    right = list(csv.DictReader(io.StringIO(after.decode("utf-8"))))
    lines = []
    if len(left) != len(right):
        lines.append(f"row count {len(left)} -> {len(right)}")
    grouped = {}
    for index, (old, new) in enumerate(zip(left, right), start=1):
        for key in list(dict.fromkeys([*old.keys(), *new.keys()])):
            if old.get(key) != new.get(key):
                grouped.setdefault((key, old.get(key), new.get(key)), []).append(index)
    for (key, old, new), rows in grouped.items():
        if len(rows) > 3:
            lines.append(f"{key}: {old!r} -> {new!r} on {len(rows)} rows (first row {rows[0]})")
        else:
            lines.append(f"{key}: {old!r} -> {new!r} on rows {rows}")
    if not lines and before != after:
        lines.append("parsed rows match; raw bytes still differ")
    return lines, len(left), len(right)


def _json_diffs(before, after, prefix=""):
    lines = []

    def walk(old, new, path):
        if isinstance(old, dict) and isinstance(new, dict):
            for key in list(dict.fromkeys([*old.keys(), *new.keys()])):
                child = f"{path}.{key}" if path else key
                if key not in old:
                    lines.append(f"{child}: <missing> -> {new[key]!r}")
                elif key not in new:
                    lines.append(f"{child}: {old[key]!r} -> <missing>")
                else:
                    walk(old[key], new[key], child)
        elif isinstance(old, list) and isinstance(new, list):
            if len(old) != len(new):
                lines.append(f"{path} length {len(old)} -> {len(new)}")
            for index, (left, right) in enumerate(zip(old, new)):
                walk(left, right, f"{path}[{index}]")
        elif old != new:
            lines.append(f"{path}: {old!r} -> {new!r}")

    walk(json.loads(before.decode("utf-8")), json.loads(after.decode("utf-8")), prefix)
    if not lines and before != after:
        lines.append("parsed JSON matches; raw bytes still differ")
    return lines


def golden_projection_report(projected):
    """Field-level diff when the projected dev9 bytes are not dev15."""
    report = []
    for name in ("houston_clean.csv", "stationary_candidates.csv",
                 "stationary_candidates.geojson", "manifest.json"):
        before = projected[name]
        after = (DEV15 / name).read_bytes()
        if before == after:
            report.append(f"{name}: byte-identical")
            continue
        if name.endswith(".csv"):
            detail, old_rows, new_rows = _csv_diffs(before, after)
            report.append(f"{name}: NOT byte-identical ({old_rows} projected rows, {new_rows} dev15 rows)")
        else:
            detail = _json_diffs(before, after)
            report.append(f"{name}: NOT byte-identical")
        report.extend(f"  {line}" for line in detail)
    return report


class MidBoundaryTests(unittest.TestCase):
    def test_assigned_range_boundaries(self):
        self.assertFalse(mid_is_assigned(199))
        self.assertFalse(mid_is_assigned(200))
        self.assertTrue(mid_is_assigned(201))
        self.assertTrue(mid_is_assigned(775))
        self.assertFalse(mid_is_assigned(776))

    def test_constructed_mmsi_boundaries_in_a_column(self):
        def column(mid):
            return f"MMSI,BaseDateTime\n{mid:03d}000001,2024-01-02T00:00:00Z\n"

        self.assertEqual(csv_mmsi_hits(column(199)), [])
        self.assertEqual(csv_mmsi_hits(column(200)), [])
        self.assertEqual(csv_mmsi_hits(column(201)), ["201" + "000001"])
        self.assertEqual(csv_mmsi_hits(column(775)), ["775" + "000001"])
        self.assertEqual(csv_mmsi_hits(column(776)), [])

    def test_unassigned_1990_prefix_passes_and_planted_assigned_mid_fails(self):
        allowed = "199" + "080001"
        self.assertEqual(csv_mmsi_hits(f"MMSI\n{allowed}\n"), [])
        self.assertEqual(python_source_hits(f'mmsi="{allowed}"'), [])
        planted = "367" + "000001"
        self.assertEqual(csv_mmsi_hits("mmsi\n" + planted + "\n"), [planted])
        self.assertEqual(python_source_hits(f'mmsi="{planted}"'), [planted])
        self.assertEqual(json_mmsi_hits(json.dumps({"mmsi": planted})), [planted])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "planted.csv"
            path.write_text("MMSI,LAT\n" + planted + ",29.73\n", encoding="utf-8")
            self.assertEqual(csv_mmsi_hits(path.read_text(encoding="utf-8")), [planted])
            clean = Path(folder) / "clean.csv"
            clean.write_text("MMSI,LAT\n" + allowed + ",29.73\n", encoding="utf-8")
            self.assertEqual(csv_mmsi_hits(clean.read_text(encoding="utf-8")), [])


class MappingTableTests(unittest.TestCase):
    def test_rules_are_a_one_to_one_mid_199_map(self):
        images = list(SYNTHETIC_ID_MAP.values())
        self.assertEqual(len(images), len(set(images)))
        self.assertEqual(len(SYNTHETIC_ID_MAP), len(images))
        for legacy, modern in SYNTHETIC_ID_MAP.items():
            self.assertEqual(len(legacy), 9)
            self.assertEqual(len(modern), 9)
            self.assertTrue(modern.startswith("1990"), modern)
            self.assertTrue(mid_is_assigned(legacy[:3]), legacy)
            self.assertFalse(mid_is_assigned(modern[:3]), modern)
            for prefix in FORBIDDEN_PREFIXES:
                self.assertFalse(modern.startswith(prefix), modern)
        # The constant the proof and the PR table use is this expanded map.
        # The fixture block is the rule whose image starts at 199080001.
        self.assertGreaterEqual(len(SYNTHETIC_ID_RULES), 8)
        fixture_rule = next(rule for rule in SYNTHETIC_ID_RULES if rule[2] == 199080001)
        self.assertEqual(SYNTHETIC_ID_MAP[str(fixture_rule[0])], "199080001")

    def test_exclusions_record_a_reason(self):
        for path, reason in EXCLUSIONS:
            self.assertTrue(path.strip())
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertGreater(len(reason.split()), 8, path)
        for name, reason in CONTEXT_EXCLUSIONS:
            self.assertTrue(name.strip())
            self.assertGreater(len(reason.split()), 8, name)


class TokenRuleTests(unittest.TestCase):
    """Nine-digit boundaries. The MID is the first three digits only."""

    def test_ten_digit_run_does_not_fire(self):
        ten = "367" + "123456" + "7"
        self.assertEqual(len(ten), 10)
        self.assertEqual(text_hits(ten), [])
        self.assertEqual(text_hits(f"id {ten} next"), [])
        bare = "367" + "123456"
        self.assertEqual(text_hits(bare), [bare])
        self.assertEqual(text_hits(f"{ten} {bare}"), [bare])

    def test_decimal_fraction_does_not_fire(self):
        planted = "367" + "123456"
        self.assertEqual(text_hits("29.123456789"), [])
        self.assertEqual(text_hits("-29.123456789"), [])
        self.assertEqual(text_hits("1." + planted), [])
        self.assertEqual(text_hits("29." + planted), [])
        self.assertEqual(text_hits("lat 29.123456789 lon"), [])
        self.assertEqual(text_hits(planted + ".12"), [planted])
        self.assertEqual(text_hits("29.123456789 " + planted), [planted])

    def test_dot_without_a_preceding_digit_still_fires(self):
        planted = "367" + "123456"
        samples = (
            "id." + planted,
            "vessel." + planted,
            "..." + planted,
            "https://example.com/id." + planted,
            "foo/bar." + planted,
        )
        for sample in samples:
            self.assertEqual(text_hits(sample), [planted], sample)

    def test_fstring_prefix_variants_with_an_assigned_mid_fire(self):
        mid = "367"
        self.assertTrue(mid_is_assigned(int(mid)))
        openers = (
            "f'", 'f"', "F'", 'F"',
            "fr'", 'fr"', "Fr'", 'Fr"', "fR'", 'fR"', "FR'", 'FR"',
            "rf'", 'rf"', "Rf'", 'Rf"', "rF'", 'rF"', "RF'", 'RF"',
            'f"""', "f'''", 'F"""', "F'''",
            'fr"""', "fr'''", 'rf"""', "RF'''",
        )
        expected = mid + "{...}"
        for opener in openers:
            text = opener + mid + "{n}"
            self.assertIn(expected, text_hits(text), opener)
        self.assertEqual(text_hits('"' + mid + '{n}"'), [])
        self.assertEqual(text_hits("r'" + mid + "{n}'"), [])
        self.assertEqual(text_hits('f"199{n}"'), [])

    def test_leading_zero_and_leading_nine_do_not_use_digits_2_to_4(self):
        group = "0" + "367" + "12345"
        leading_nine = "9" + "367" + "12345"
        self.assertEqual(len(group), 9)
        self.assertEqual(len(leading_nine), 9)
        self.assertEqual(text_hits(group), [])
        self.assertEqual(text_hits(leading_nine), [])

    def test_hex_run_of_64_is_ignored_and_a_shorter_run_is_not(self):
        planted = "367" + "123456"
        digest = ("ab" * 20) + planted + ("cd" * 15)
        self.assertGreaterEqual(len(digest), 64)
        self.assertEqual(text_hits(digest), [])
        self.assertEqual(text_hits(digest.upper()), [])
        self.assertEqual(text_hits(digest + "\n" + planted + "\n"), [planted])
        short = ("ab" * 27) + planted
        self.assertEqual(len(short), 63)
        self.assertEqual(text_hits(short), [planted])


class GuardScanTests(unittest.TestCase):
    def test_repository_has_no_assigned_mid_outside_the_exclusions(self):
        hits, coverage = scan_repository()
        self.assertEqual(hits, [])
        self.assertGreater(len(coverage["visited"]), 0)

    def test_dev9_golden_would_fail_without_its_exclusion(self):
        hits = []
        for path in sorted(DEV9.iterdir()):
            hits.extend(text_hits(path.read_text(encoding="utf-8")))
        legacy_fixture = str(next(rule[0] for rule in SYNTHETIC_ID_RULES if rule[2] == 199080001))
        self.assertIn(legacy_fixture, hits)
        self.assertTrue(path_is_excluded(DEV9 / "houston_clean.csv"))

    def test_mapping_table_would_fail_without_its_exclusion(self):
        hits = python_source_hits(MAP_SOURCE.read_text(encoding="utf-8"))
        self.assertTrue(hits)
        self.assertTrue(all(mid_is_assigned(hit[:3]) for hit in hits if hit.isdigit()))
        self.assertTrue(path_is_excluded(MAP_SOURCE))

    def test_mmap_size_byte_count_is_contextual_and_an_mmsi_still_fails(self):
        token = str(256 * 1024 * 1024)
        probe = (ROOT / "tests" / "multiday_memory_probe.py").read_text(encoding="utf-8")
        self.assertIn(token, probe)
        self.assertNotIn(token, python_source_hits(probe))
        self.assertEqual(
            python_source_hits(f'db.execute("PRAGMA mmap_size={token}")'),
            [],
        )
        self.assertEqual(python_source_hits(f"mmap_size = {token}\n"), [])
        # The assigned value is exempt. These three are not that value.
        other = "367" + "123456"
        self.assertEqual(text_hits("not_mmap_size = " + other), [other])
        self.assertEqual(text_hits("mmsi = " + other + "; mmap_size = 0"), [other])
        self.assertEqual(text_hits(other + "  # mmap_size = 1"), [other])
        # Same digits, not an mmap_size assignment: the guard fails.
        self.assertEqual(python_source_hits(f'mmsi = "{token}"\n'), [token])
        self.assertEqual(python_source_hits(f"value = {token}\n"), [token])
        self.assertEqual(csv_mmsi_hits(f"MMSI\n{token}\n"), [token])
        self.assertEqual(json_mmsi_hits(json.dumps({"mmsi": token})), [token])
        self.assertEqual(json_mmsi_hits(json.dumps({"properties": {"mmsi": token}})), [token])

    def test_hex_digest_is_ignored_and_a_standalone_mmsi_in_the_same_file_fails(self):
        text = FR_EVIDENCE.read_text(encoding="utf-8")
        self.assertFalse(path_is_excluded(FR_EVIDENCE))
        self.assertNotIn("mmsi", text.lower())
        raw_hits = []
        for match in TOKEN_9.finditer(text):
            token = match.group(1)
            if mid_is_assigned(token[:3]):
                self.assertTrue(_inside_hex_blob(text, match.start(), match.end()), token)
                raw_hits.append(token)
        self.assertTrue(raw_hits)
        self.assertEqual(text_hits(text), [])
        planted = "367" + "123456"
        combined = text + "\n" + planted + "\n"
        self.assertEqual(text_hits(combined), [planted])
        extra = ROOT / "docs" / "data" / "_qa_hex_and_standalone.md"
        relative = extra.relative_to(ROOT).as_posix()
        extra.write_text(combined, encoding="utf-8")
        try:
            hits, coverage = scan_repository()
            self.assertIn(relative, coverage["visited"])
            self.assertEqual(
                [item for item in hits if item[0] == relative],
                [(relative, planted)],
            )
        finally:
            extra.unlink(missing_ok=True)
        self.assertIn("SHA-256", dict(CONTEXT_EXCLUSIONS)["hex-run-64-or-longer"])

    def test_retired_marshall_islands_id_is_redacted_outside_the_map(self):
        retired = "538" + "001234"
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        trace = (ROOT / "docs" / "requirements" / "traceability.md").read_text(encoding="utf-8")
        phrase = "former Marshall Islands-MID synthetic ID"
        self.assertNotIn(retired, changelog)
        self.assertNotIn(retired, trace)
        self.assertIn(phrase, changelog)
        self.assertIn(phrase, trace)
        self.assertIn(retired, MAP_SOURCE.read_text(encoding="utf-8"))
        self.assertTrue(path_is_excluded(MAP_SOURCE))


def assert_tracked_coverage(test, coverage):
    """Visited text files equal tracked files minus binaries minus exclusions.

    Paths are relative to the repository root. Untracked planted files are
    scanned by the same function and are not part of this total.
    """
    tracked = coverage["tracked"]
    tracked_set = set(tracked)
    test.assertTrue(EXCLUSION_PATHS <= tracked_set)
    visited_tracked = [path for path in coverage["visited"] if path in tracked_set]
    binaries_tracked = [path for path in coverage["binaries"] if path in tracked_set]
    test.assertFalse(set(visited_tracked) & EXCLUSION_PATHS)
    test.assertFalse(set(binaries_tracked) & EXCLUSION_PATHS)
    test.assertFalse(set(visited_tracked) & set(binaries_tracked))
    by_ext = Counter(extension_key(path) for path in visited_tracked)
    total = sum(by_ext.values())
    expected = len(tracked) - len(binaries_tracked) - len(EXCLUSION_PATHS)
    detail = ", ".join(f"{key}={by_ext[key]}" for key in sorted(by_ext))
    test.assertGreater(total, 0, detail)
    test.assertEqual(total, expected, detail)
    test.assertEqual(
        len(visited_tracked) + len(binaries_tracked) + len(EXCLUSION_PATHS),
        len(tracked),
        detail,
    )
    for path in coverage["visited"]:
        test.assertFalse(path.startswith("/"), path)
        test.assertNotIn("\\", path)
    tops = {path.split("/", 1)[0] for path in visited_tracked}
    for name in ("src", "docs", "schemas", "specs", "tests", "tools"):
        test.assertIn(name, tops, sorted(tops))
    for suffix in (
        ".py", ".md", ".json", ".csv", ".geojson", ".yml", ".yaml",
        ".toml", ".cff", ".sh", "<none>",
    ):
        test.assertGreater(by_ext[suffix], 0, detail)
    return by_ext


def run_coverage_check(test):
    """Run the coverage meta-test.

    When git cannot be run, skip unless the environment variable ``CI`` is
    the string ``true``. In that case the test fails.
    """
    try:
        _hits, coverage = scan_repository()
    except GitUnavailable as exc:
        reason = f"git is unavailable: {exc}"
        if os.environ.get("CI") == "true":
            test.fail(reason)
        test.skipTest(reason)
    return assert_tracked_coverage(test, coverage)


class GuardCoverageTests(unittest.TestCase):
    """The repository scan must cover every tracked text file."""

    def test_visited_text_files_equal_git_ls_files_minus_binaries_and_exclusions(self):
        run_coverage_check(self)

    def test_missing_git_skips_outside_ci_and_fails_when_ci_is_true(self):
        def boom(*_args, **_kwargs):
            raise GitUnavailable("git executable was not found")

        module = __import__(__name__)
        with mock.patch.dict(os.environ, {"CI": "false"}):
            with mock.patch.object(module, "scan_repository", side_effect=boom):
                with self.assertRaises(unittest.SkipTest) as skipped:
                    run_coverage_check(self)
        self.assertIn("git is unavailable", str(skipped.exception))
        self.assertIn("git executable was not found", str(skipped.exception))

        with mock.patch.dict(os.environ, {"CI": "true"}):
            with mock.patch.object(module, "scan_repository", side_effect=boom):
                with self.assertRaises(AssertionError) as failed:
                    run_coverage_check(self)
        self.assertIn("git is unavailable", str(failed.exception))
        self.assertIn("git executable was not found", str(failed.exception))

    def test_paths_are_classified_from_the_repository_root(self):
        absolute = (ROOT / "src" / "harborlens" / "ais.py").resolve()
        self.assertNotEqual(absolute.parts[0], "src")
        self.assertTrue(relative_posix(absolute).startswith("src/"))

    def _assert_planted(self, relative, text, planted):
        path = ROOT / relative
        self.assertFalse(path.exists(), relative)
        path.write_text(text, encoding="utf-8")
        try:
            hits, coverage = scan_repository()
            self.assertIn(relative, coverage["visited"])
            self.assertEqual(
                [item for item in hits if item[0] == relative],
                [(relative, planted)],
            )
        finally:
            path.unlink(missing_ok=True)

    def test_planted_assigned_mid_inside_tests_is_reported(self):
        planted = "367" + "123456"
        self._assert_planted(
            "tests/_qa_planted_assigned_mid.py",
            f'mmsi = "{planted}"\n',
            planted,
        )

    def test_planted_markdown_line_outside_tests_is_reported(self):
        planted = "367" + "123456"
        ten = planted + "7"
        text = (
            f"A ten-digit run {ten} does not match.\n"
            "A decimal fraction 29.123456789 does not match.\n"
            f"A decimal fraction 29.{planted} does not match.\n"
            f"A prose identifier {planted} matches.\n"
        )
        self._assert_planted("docs/_qa_planted_assigned_mid.md", text, planted)

    def test_planted_csv_vessel_id_column_is_reported(self):
        planted = "367" + "123456"
        table = f"vessel_id,lat\n{planted},29.73\n"
        self.assertEqual(csv_mmsi_hits(table), [])
        self.assertEqual(text_hits(table), [planted])
        self._assert_planted("tests/_qa_planted_vessel_id.csv", table, planted)

    def test_planted_json_value_outside_an_mmsi_key_is_reported(self):
        planted = "367" + "123456"
        body = json.dumps({"note": planted})
        self.assertEqual(json_mmsi_hits(body), [])
        self.assertEqual(text_hits(body), [planted])
        self._assert_planted("schemas/_qa_planted_value.json", body, planted)

    def test_binary_file_is_skipped_and_counted(self):
        planted = "367" + "123456"
        extra = ROOT / "tests" / "_qa_binary_with_mmsi.bin"
        relative = extra.relative_to(ROOT).as_posix()
        extra.write_bytes(planted.encode("ascii") + b"\0" + planted.encode("ascii"))
        try:
            hits, coverage = scan_repository()
            self.assertIn(relative, coverage["binaries"])
            self.assertNotIn(relative, coverage["visited"])
            self.assertFalse(any(path == relative for path, _token in hits))
        finally:
            extra.unlink(missing_ok=True)

    def test_unexpected_file_in_dev9_is_not_excluded(self):
        planted = "367" + "123456"
        extra = DEV9 / "_qa_not_a_golden.py"
        relative = extra.relative_to(ROOT).as_posix()
        self.assertNotIn(relative, EXCLUSION_PATHS)
        self.assertFalse(path_is_excluded(extra))
        for name in (
            "houston_clean.csv",
            "stationary_candidates.csv",
            "stationary_candidates.geojson",
            "manifest.json",
        ):
            self.assertTrue(path_is_excluded(DEV9 / name), name)
        extra.write_text(f'mmsi = "{planted}"\n', encoding="utf-8")
        try:
            hits, coverage = scan_repository()
            self.assertIn(relative, coverage["visited"])
            self.assertIn((relative, planted), hits)
        finally:
            extra.unlink(missing_ok=True)


class GoldenSubstitutionProofTests(unittest.TestCase):
    """Projected dev9 artifacts must be byte-identical to dev15.

    The projection applies ``SYNTHETIC_ID_MAP``, flips ``ship`` to ``other``
    only on mapped rows, and recomputes ``event_id``, ``input_sha256``,
    ``run_id``, and ``package_version`` with ``hashlib``. It does not import
    or call the pipeline. Any other difference fails.

    Pinning the version to ``0.2.0.dev15`` reproduces the golden manifest.
    The live package version changes ``package_version`` and ``run_id`` only.
    ``harborlens-verify`` checks the three artifact hashes. The release
    recount reads ``houston_clean.csv``. Those bytes stay the dev15 bytes.
    """

    def test_dev15_manifest_verifies_its_own_artifacts(self):
        files = {name: (DEV15 / name).read_bytes() for name in (*VERIFY_ARTIFACTS, "manifest.json")}
        result = independent_verify(files)
        self.assertTrue(result["ok"], result)
        self.assertEqual(set(result["artifacts"]), set(VERIFY_ARTIFACTS))

    def test_dev9_projection_is_byte_identical_to_dev15(self):
        pinned = project_dev9(version="0.2.0.dev15")
        mismatches = [
            name for name, body in pinned.items()
            if body != (DEV15 / name).read_bytes()
        ]
        self.assertEqual(mismatches, [], "\n".join(golden_projection_report(pinned)))
        live = project_dev9()
        for name in VERIFY_ARTIFACTS:
            self.assertEqual(live[name], (DEV15 / name).read_bytes(), name)
        live_manifest = json.loads(live["manifest.json"])
        golden_manifest = json.loads((DEV15 / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(live_manifest["code_version"]["package_version"], package_version_text())
        self.assertEqual(live_manifest["code_version"]["package_version"], "0.2.0.dev16")
        self.assertNotEqual(live_manifest["run_id"], golden_manifest["run_id"])
        golden_manifest["code_version"]["package_version"] = "0.2.0.dev16"
        golden_manifest["run_id"] = live_manifest["run_id"]
        self.assertEqual(live_manifest, golden_manifest)

    def test_release_verify_path_projection_is_byte_identical(self):
        """Verify artifacts and the release recount input stay the dev15 bytes."""
        projected = project_dev9()
        dev15 = {
            name: (DEV15 / name).read_bytes()
            for name in (*VERIFY_ARTIFACTS, "manifest.json")
        }
        mismatches = [name for name in VERIFY_ARTIFACTS if projected[name] != dev15[name]]
        cleaned_differs = projected["houston_clean.csv"] != dev15["houston_clean.csv"]
        projected_verify = independent_verify(projected)
        current_verify = independent_verify(dev15)
        pinned = project_dev9(version="0.2.0.dev15")
        report = "\n".join(golden_projection_report(pinned))
        report += (
            f"\nindependent verify(projected)={projected_verify}"
            f"\nindependent verify(dev15)={current_verify}"
            f"\nrelease recount input differs={cleaned_differs}"
        )
        self.assertEqual(mismatches, [], report)
        self.assertFalse(cleaned_differs, report)
        self.assertEqual(pinned["manifest.json"], dev15["manifest.json"], report)
        self.assertNotEqual(projected["manifest.json"], dev15["manifest.json"])
        self.assertTrue(projected_verify["ok"], report)
        self.assertTrue(current_verify["ok"], report)


class ProofMutationTests(unittest.TestCase):
    """The proof fails when a golden, an unmapped category, or the map changes.

    Copies stay in memory or in a temporary directory. Committed fixtures
    are only read.
    """

    def test_one_changed_golden_byte_fails(self):
        committed = (DEV15 / "houston_clean.csv").read_bytes()
        projected = project_dev9(version="0.2.0.dev15")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for name in projected:
                data = bytearray((DEV15 / name).read_bytes())
                if name == "houston_clean.csv":
                    data[20] ^= 0x01
                (dest / name).write_bytes(bytes(data))
            mismatches = [
                name for name in projected
                if projected[name] != (dest / name).read_bytes()
            ]
        self.assertEqual(mismatches, ["houston_clean.csv"])
        self.assertEqual((DEV15 / "houston_clean.csv").read_bytes(), committed)

    def test_flipping_an_unmapped_row_category_fails(self):
        unmapped = "790" + "000001"
        self.assertNotIn(unmapped, SYNTHETIC_ID_MAP.values())
        source = (DEV9 / "houston_clean.csv").read_bytes()
        extra = (
            unmapped + ",2024-01-02T00:00:00Z,29.73,-95.16,0.1,70,5,,,,,,,ship\r\n"
        ).encode("utf-8")
        projected = project_cleaned_csv(source + extra)
        unmapped_lines = [
            line for line in projected.decode("utf-8").splitlines()
            if line.startswith(unmapped + ",")
        ]
        self.assertEqual(len(unmapped_lines), 1)
        self.assertTrue(unmapped_lines[0].endswith("ship"))
        lines = []
        for line in projected.decode("utf-8").splitlines(keepends=True):
            if line.startswith(unmapped + ",") and line.rstrip("\r\n").endswith("ship"):
                ending = "\r\n" if line.endswith("\r\n") else "\n"
                line = line[: -len("ship") - len(ending)] + "other" + ending
            lines.append(line)
        flipped = "".join(lines).encode("utf-8")
        self.assertNotEqual(projected, flipped)
        self.assertTrue(flipped.decode("utf-8").splitlines()[-1].endswith("other"))

    def test_altered_map_entry_fails(self):
        legacy = next(
            key for key, value in SYNTHETIC_ID_MAP.items() if value == "199080001"
        )
        altered = dict(SYNTHETIC_ID_MAP)
        altered[legacy] = "199080099"
        self.assertEqual(SYNTHETIC_ID_MAP[legacy], "199080001")
        projected = project_dev9(mapping=altered)
        self.assertNotEqual(
            projected["houston_clean.csv"],
            (DEV15 / "houston_clean.csv").read_bytes(),
        )
        self.assertEqual(SYNTHETIC_ID_MAP[legacy], "199080001")


if __name__ == "__main__":
    unittest.main()
