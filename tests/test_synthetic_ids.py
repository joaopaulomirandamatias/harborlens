"""Guard for synthetic vessel identifiers (SPEC-001, FR-001, FR-002, BR-008, BR-016).

Committed synthetic MMSIs use unassigned MID 199, form ``1990xxxxx``.
The guard fails when a vessel id's MID is in the assigned range 201-775.

Exclusions, each with the reason the path is not a current vessel id:

* ``tests/fixtures/single_day_0.2.0.dev9/`` is the package 0.2.0.dev9 golden.
  It is kept as the input of the mapping proof: the proof substitutes legacy
  ids in those bytes and compares them with ``single_day_0.2.0.dev15``.
  Each of those files is excluded by its exact path. A new file in that directory is scanned. The directory still contains MID 367.
* ``docs/data/fr-2023-original-fulltext-evidence-2026-11-09.md`` records
  SHA-256 digests of Federal Register documents. A nine-digit run inside a
  digest is not a vessel id, and the quoted evidence note is not rewritten.
* ``tests/synthetic_id_map.py`` is the mapping table. Its keys are the retired
  identifiers. The same identifiers anywhere else still fail the guard.
* A nine-digit token is ignored only on a line that sets ``mmap_size``
  (``PRAGMA mmap_size=`` or ``mmap_size =``). In
  ``tests/multiday_memory_probe.py`` that line is a 256 MiB byte count.
  The same digits in an MMSI column, a ``mmsi`` field, or any other line fail.

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
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from synthetic_id_map import SYNTHETIC_ID_MAP, SYNTHETIC_ID_RULES

ROOT = Path(__file__).resolve().parents[1]
DEV9 = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev9"
DEV15 = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev15"
FR_EVIDENCE = ROOT / "docs" / "data" / "fr-2023-original-fulltext-evidence-2026-11-09.md"
MAP_SOURCE = ROOT / "tests" / "synthetic_id_map.py"

ASSIGNED_MID_LOW = 201
ASSIGNED_MID_HIGH = 775
# Nine digits bounded by a non-digit. A longer digit run is not one MMSI.
TOKEN_9 = re.compile(r"(?<!\d)(\d{9})(?!\d)")
# An f-string whose literal digit prefix selects an assigned MID has no nine-digit token.
FSTRING_PREFIX = re.compile(r"""f(?P<quote>['"])(?P<prefix>\d{3,8})\{""")
HEX_BLOB = re.compile(r"[0-9a-fA-F]{32,}")
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
        "docs/data/fr-2023-original-fulltext-evidence-2026-11-09.md",
        "Federal Register evidence note. Digit runs sit inside SHA-256 digests of "
        "official documents. They are not MMSI columns or vessel ids, and the "
        "quoted source note is not rewritten.",
    ),
    (
        "tests/synthetic_id_map.py",
        "Mapping table. Legacy identifiers appear only as the keys this change "
        "retires. Every key is an assigned MID and every value is 1990xxxxx. "
        "The same legacy identifier outside this file still fails the guard.",
    ),
)
EXCLUSION_PATHS = {path for path, _reason in EXCLUSIONS}

# Files harborlens-verify hashes, and the cleaned CSV the release recount reads.
VERIFY_ARTIFACTS = (
    "houston_clean.csv",
    "stationary_candidates.csv",
    "stationary_candidates.geojson",
)
MMAP_SIZE_ASSIGNMENT = re.compile(r"mmap_size\s*=")


def mid_is_assigned(mid):
    """True when ``mid`` is in the assigned MID block 201-775 inclusive."""
    return ASSIGNED_MID_LOW <= int(mid) <= ASSIGNED_MID_HIGH


def _assigned_nine(value):
    text = str(value).strip()
    if re.fullmatch(r"\d{9}", text) and mid_is_assigned(text[:3]):
        return text
    return None


def csv_mmsi_hits(text):
    """Nine-digit assigned-MID values in a column named MMSI."""
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
    """Nine-digit assigned-MID values of a key named mmsi."""
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


def _line_containing(text, offset):
    start = text.rfind("\n", 0, offset) + 1
    end = text.find("\n", offset)
    if end < 0:
        end = len(text)
    return text[start:end]


def python_source_hits(text):
    """Assigned-MID vessel-id tokens in Python or other source text.

    A nine-digit token inside a hex digest of 32 or more characters is not a
    vessel id. A token on a line that assigns ``mmap_size`` is a byte count
    (``PRAGMA mmap_size=`` in ``tests/multiday_memory_probe.py``), not an
    allowlisted number: the same digits on any other line are a hit. An
    f-string prefix whose first three digits are an assigned MID is a hit
    even when the format field completes the nine digits at runtime.
    """
    hits = []
    for match in TOKEN_9.finditer(text):
        token = match.group(1)
        if _inside_hex_blob(text, match.start(), match.end()):
            continue
        if MMAP_SIZE_ASSIGNMENT.search(_line_containing(text, match.start())):
            continue
        if mid_is_assigned(token[:3]):
            hits.append(token)
    for match in FSTRING_PREFIX.finditer(text):
        prefix = match.group("prefix")
        if mid_is_assigned(prefix[:3]):
            hits.append(prefix + "{...}")
    return hits


def source_hits(text, kind):
    """Dispatch one text blob. ``kind`` is csv, json, or python."""
    if kind == "csv":
        return csv_mmsi_hits(text)
    if kind == "json":
        return json_mmsi_hits(text)
    if kind == "python":
        return python_source_hits(text)
    raise ValueError(kind)


def path_is_excluded(path, root=ROOT):
    """True only when the relative path is one exact exclusion entry."""
    relative = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    return relative in EXCLUSION_PATHS


def scan_repository(root=ROOT):
    """Scan fixture tables and Python sources under ``tests/`` and ``tools/``.

    Returns ``(hits, visited_python)``. ``hits`` are ``(relative path, token)``.
    ``visited_python`` is every ``.py`` file the walk read under ``tests/`` or
    ``tools/`` after the exact exclusions. Classification uses
    ``path.relative_to(root).parts[0]``, because ``path.parts[0]`` is ``/``
    when ``root`` is absolute.
    """
    root = Path(root)
    hits = []
    visited = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        relative_path = path.resolve().relative_to(root.resolve())
        relative = relative_path.as_posix()
        if relative in EXCLUSION_PATHS:
            continue
        suffix = path.suffix.lower()
        top = relative_path.parts[0]
        if suffix == ".csv":
            kind = "csv"
        elif suffix in {".json", ".geojson"}:
            kind = "json"
        elif suffix == ".py" and top in {"tests", "tools"}:
            kind = "python"
        else:
            continue
        text = path.read_text(encoding="utf-8")
        if kind == "python":
            visited.append(relative)
        for hit in source_hits(text, kind):
            hits.append((relative, hit))
    return hits, visited


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
            self.assertGreater(len(reason.split()), 8, path)


class GuardScanTests(unittest.TestCase):
    def test_repository_has_no_assigned_mid_outside_the_exclusions(self):
        hits, _visited = scan_repository()
        self.assertEqual(hits, [])

    def test_dev9_golden_would_fail_without_its_exclusion(self):
        hits = []
        for path in sorted(DEV9.iterdir()):
            kind = "csv" if path.suffix == ".csv" else "json"
            hits.extend(source_hits(path.read_text(encoding="utf-8"), kind))
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
        # Same digits, not an mmap_size assignment: the guard fails.
        self.assertEqual(python_source_hits(f'mmsi = "{token}"\n'), [token])
        self.assertEqual(python_source_hits(f"value = {token}\n"), [token])
        self.assertEqual(csv_mmsi_hits(f"MMSI\n{token}\n"), [token])
        self.assertEqual(json_mmsi_hits(json.dumps({"mmsi": token})), [token])
        self.assertEqual(json_mmsi_hits(json.dumps({"properties": {"mmsi": token}})), [token])

    def test_federal_register_digit_run_is_inside_a_sha256_not_a_vessel_id(self):
        text = FR_EVIDENCE.read_text(encoding="utf-8")
        self.assertNotIn("mmsi", text.lower())
        self.assertIsNone(re.search(r"(?i)^mmsi,", text, flags=re.MULTILINE))
        raw_hits = []
        for match in TOKEN_9.finditer(text):
            token = match.group(1)
            if mid_is_assigned(token[:3]) and _inside_hex_blob(text, match.start(), match.end()):
                raw_hits.append(token)
        self.assertTrue(raw_hits)
        self.assertEqual(python_source_hits(text), [])
        self.assertTrue(path_is_excluded(FR_EVIDENCE))
        fr_key = "docs/data/fr-2023-original-fulltext-evidence-2026-11-09.md"
        self.assertIn("SHA-256", dict(EXCLUSIONS)[fr_key])


def tracked_python_under_tests_and_tools():
    """Tracked ``.py`` files under ``tests/`` and ``tools/``, minus exclusions.

    Independent of the scanner walk: ``git ls-files`` lists the index.
    """
    listed = subprocess.check_output(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
    )
    paths = [item.decode("utf-8") for item in listed.split(b"\0") if item]
    return sorted(
        path for path in paths
        if path.endswith(".py")
        and (path.startswith("tests/") or path.startswith("tools/"))
        and path not in EXCLUSION_PATHS
    )


class GuardCoverageTests(unittest.TestCase):
    """The repository scan must walk the real ``tests/`` and ``tools/`` trees."""

    def test_visited_python_files_match_git_ls_files(self):
        _hits, visited = scan_repository()
        expected = tracked_python_under_tests_and_tools()
        self.assertGreater(len(visited), 0)
        self.assertEqual(sorted(visited), expected)

    def test_planted_assigned_mid_inside_tests_is_reported(self):
        planted = "367" + "123456"
        extra = ROOT / "tests" / "_qa_planted_assigned_mid.py"
        relative = extra.relative_to(ROOT).as_posix()
        extra.write_text(f'mmsi = "{planted}"\n', encoding="utf-8")
        try:
            hits, visited = scan_repository()
            self.assertIn(relative, visited)
            self.assertIn((relative, planted), hits)
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
            hits, visited = scan_repository()
            self.assertIn(relative, visited)
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
