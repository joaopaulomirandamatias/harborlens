"""Guard for synthetic vessel identifiers (SPEC-001, FR-001, FR-002, BR-008, BR-016).

Committed synthetic MMSIs use unassigned MID 199, form ``1990xxxxx``.
The guard fails when a vessel id's MID is in the assigned range 201-775.

Exclusions, each with the reason the path is not a current vessel id:

* ``tests/fixtures/single_day_0.2.0.dev9/`` is the package 0.2.0.dev9 golden.
  It is kept as the input of the mapping proof: the proof substitutes legacy
  ids in those bytes and compares them with ``single_day_0.2.0.dev15``.
  Deleting it would remove that input. The directory still contains MID 367.
* ``docs/data/fr-2023-original-fulltext-evidence-2026-11-09.md`` records
  SHA-256 digests of Federal Register documents. A nine-digit run inside a
  digest is not a vessel id, and the quoted evidence note is not rewritten.
* ``tests/synthetic_id_map.py`` is the mapping table. Its keys are the retired
  identifiers. The same identifiers anywhere else still fail the guard.
* ``268435456`` in ``tests/multiday_memory_probe.py`` is ``PRAGMA mmap_size``
  for 256 MiB. It is a byte count. The same digits in an MMSI column still fail.

``mmsi_category`` classifies MID 199 as ``other`` and MID 367 as ``ship``.
The byte-identity proof below does not rewrite category, event id, counts, or
hashes. It only substitutes legacy vessel ids.
"""
from __future__ import annotations

import csv
import io
import json
import re
import tempfile
import unittest
from pathlib import Path

from harborlens.provenance import FILES, verify_manifest
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

# Path prefix, reason. The reason is part of the test, not only a comment.
EXCLUSIONS = (
    (
        "tests/fixtures/single_day_0.2.0.dev9",
        "Historical golden for package 0.2.0.dev9. Retained as the mapping-proof "
        "input so legacy MID 367 identifiers can be substituted and compared with "
        "tests/fixtures/single_day_0.2.0.dev15. It is not a current vessel-id source.",
    ),
    (
        "docs/data/fr-2023-original-fulltext-evidence-",
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

# Token, reason. Applied only to Python-source token scans, not to MMSI columns.
NON_MMSI_DIGIT_TOKENS = {
    str(256 * 1024 * 1024): (
        "tests/multiday_memory_probe.py sets PRAGMA mmap_size to 256 MiB. "
        "That decimal byte count is not a vessel identifier. The same nine "
        "digits in an MMSI column or mmsi field still fail."
    ),
}


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


def python_source_hits(text):
    """Assigned-MID vessel-id tokens in Python or other source text.

    A nine-digit token inside a hex digest of 32 or more characters is not a
    vessel id. ``NON_MMSI_DIGIT_TOKENS`` lists the other documented exceptions.
    An f-string prefix whose first three digits are an assigned MID is a hit
    even when the format field completes the nine digits at runtime.
    """
    hits = []
    for match in TOKEN_9.finditer(text):
        token = match.group(1)
        if token in NON_MMSI_DIGIT_TOKENS:
            continue
        if _inside_hex_blob(text, match.start(), match.end()):
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


def path_is_excluded(path):
    relative = path.resolve().relative_to(ROOT).as_posix()
    for prefix, _reason in EXCLUSIONS:
        if relative == prefix or relative.startswith(prefix):
            return True
    return False


def iter_repository_hits(root=ROOT):
    """Assigned-MID vessel ids in fixtures and in test/tool sources."""
    for path in sorted(root.rglob("*")):
        if not path.is_file() or ".git" in path.parts:
            continue
        if path_is_excluded(path):
            continue
        suffix = path.suffix.lower()
        if suffix == ".csv":
            kind = "csv"
        elif suffix in {".json", ".geojson"}:
            kind = "json"
        elif suffix == ".py" and (path.parts[0] in {"tests", "tools"} or "tests" in path.parts or "tools" in path.parts):
            # rglob from ROOT: parts[0] is the top directory.
            kind = "python"
        else:
            continue
        if kind == "python" and path.parts[0] not in {"tests", "tools"}:
            continue
        text = path.read_text(encoding="utf-8")
        for hit in source_hits(text, kind):
            yield path.relative_to(root).as_posix(), hit


def substitute_legacy_ids(data):
    """Replace legacy synthetic ids as whole tokens. No other bytes change."""
    text = data.decode("utf-8")
    for legacy, modern in sorted(SYNTHETIC_ID_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"(?<!\d){legacy}(?!\d)", modern, text)
    return text.encode("utf-8")


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


def golden_substitution_report():
    """Field-level diff after substituting legacy ids in the dev9 golden."""
    report = []
    compared = ("houston_clean.csv", "stationary_candidates.csv", "stationary_candidates.geojson", "manifest.json")
    for name in compared:
        before = substitute_legacy_ids((DEV9 / name).read_bytes())
        after = (DEV15 / name).read_bytes()
        if before == after:
            report.append(f"{name}: byte-identical after id substitution")
            continue
        if name.endswith(".csv"):
            detail, old_rows, new_rows = _csv_diffs(before, after)
            report.append(f"{name}: NOT byte-identical ({old_rows} dev9 rows, {new_rows} dev15 rows)")
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
        self.assertEqual(csv_mmsi_hits(column(201)), ["201000001"])
        self.assertEqual(csv_mmsi_hits(column(775)), ["775000001"])
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
        self.assertTrue(NON_MMSI_DIGIT_TOKENS[str(256 * 1024 * 1024)].strip())


class GuardScanTests(unittest.TestCase):
    def test_repository_has_no_assigned_mid_outside_the_exclusions(self):
        hits = list(iter_repository_hits())
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

    def test_byte_count_token_is_ignored_until_it_is_in_an_mmsi_column(self):
        token = str(256 * 1024 * 1024)
        probe = (ROOT / "tests" / "multiday_memory_probe.py").read_text(encoding="utf-8")
        self.assertIn(token, probe)
        self.assertNotIn(token, python_source_hits(probe))
        self.assertEqual(csv_mmsi_hits(f"MMSI\n{token}\n"), [token])

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
        self.assertIn("SHA-256", dict(EXCLUSIONS)["docs/data/fr-2023-original-fulltext-evidence-"])


class GoldenSubstitutionProofTests(unittest.TestCase):
    """ID substitution of the dev9 golden must be byte-identical to dev15.

    harborlens-verify checks the three artifact hashes. The release recount
    reads ``houston_clean.csv``. Both paths use the same substitution proof.
    """

    def test_dev15_manifest_verifies_its_own_artifacts(self):
        result = verify_manifest(DEV15 / "manifest.json")
        self.assertTrue(result["ok"], result)
        self.assertEqual(set(result["artifacts"]), set(FILES))

    def test_dev9_id_substitution_is_byte_identical_to_dev15(self):
        mismatches = []
        names = ("houston_clean.csv", "stationary_candidates.csv",
                 "stationary_candidates.geojson", "manifest.json")
        for name in names:
            substituted = substitute_legacy_ids((DEV9 / name).read_bytes())
            current = (DEV15 / name).read_bytes()
            if substituted != current:
                mismatches.append(name)
        report = "\n".join(golden_substitution_report())
        self.assertEqual(mismatches, [], report)

    def test_release_verify_path_id_substitution_is_byte_identical(self):
        """Same proof for the bytes ``harborlens-verify`` and the release recount read."""
        with tempfile.TemporaryDirectory() as folder:
            substituted_root = Path(folder)
            for name in ("houston_clean.csv", "stationary_candidates.csv",
                         "stationary_candidates.geojson", "manifest.json"):
                (substituted_root / name).write_bytes(
                    substitute_legacy_ids((DEV9 / name).read_bytes())
                )
            substituted_verify = verify_manifest(substituted_root / "manifest.json")
            current_verify = verify_manifest(DEV15 / "manifest.json")
            artifact_mismatches = []
            for name in FILES:
                if (substituted_root / name).read_bytes() != (DEV15 / name).read_bytes():
                    artifact_mismatches.append(name)
            # The release recount input is the cleaned CSV.
            cleaned_differs = (substituted_root / "houston_clean.csv").read_bytes() != (
                DEV15 / "houston_clean.csv"
            ).read_bytes()
            report = "\n".join(golden_substitution_report())
            report += (
                f"\nverify_manifest(dev9 substituted)={substituted_verify}"
                f"\nverify_manifest(dev15)={current_verify}"
                f"\nrelease recount input differs={cleaned_differs}"
            )
            self.assertEqual(artifact_mismatches, [], report)
            self.assertFalse(cleaned_differs, report)
            self.assertEqual(substituted_verify, current_verify, report)


if __name__ == "__main__":
    unittest.main()
