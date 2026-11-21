"""Diff proof for CSV formula prefixes (SPEC-001, SPEC-003, NFR-006).

Package 0.2.0.dev19 skips a fixed set of invisible characters before a
formula trigger. ``prefix_text`` below is that writer rule. It does not
import ``harborlens.csv_safe`` or any HarborLens neutralizer. ``prefix_dev17``
is the previous rule (Unicode whitespace, U+FEFF, and U+200B) and is used
only to show which cells changed.

The fixture is synthetic. MMSIs use unassigned MID 199. A stationary
candidate is not a berth, anchorage, wait, or port call. GeoJSON is not
neutralized: a JSON string is not a spreadsheet formula.
"""
import csv
import hashlib
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path

from harborlens.ais import read_candidates_csv, run
from harborlens.multiday import run_multiday
from harborlens.provenance import verify_manifest
from harborlens.publication import _recount_cleaned

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais_formula.csv"
GOLDEN = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev19_formula"
DEV17_GOLDEN = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev17_formula"
MAIN_FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais.csv"
# Bytes of the main fixture. Neutralization does not touch them.
MAIN_SHA256 = {
    "houston_clean.csv": "4cd3986411530eef4296bcc2a964ab978f11925468bce8e67600c11c4aad1b75",
    "stationary_candidates.csv": "69989a5c0f6f53961ca2ce3987ba06d3381a6f92490fd16773e709d824a3fc05",
    "stationary_candidates.geojson": "0e3127c834035c27546b209d024f3c9ba8b7ae9e249200abb8fa8dee010008d3",
}
DEV17_FORMULA_SHA256 = {
    "houston_clean.csv": "4020e780a89cc7f3e4eb2cbfb6713c9da87cc5e79a87c8f13068b76bc38b813d",
    "stationary_candidates.csv": "67f31156d01bc33ddf7000b147817c552c7270a9656daff7e86a8ec77defd3f1",
    "stationary_candidates.geojson": "be466a567b7948f4a8e5c33a7293c150a13032137cb2c5a3e13c5aadf5f83cc1",
}
# Filled after the dev19 formula run. The test fails if these bytes move.
FORMULA_SHA256 = {
    "houston_clean.csv": "f3c509e9ab0b25a3e4a1355a97b5944192eaa563dfef2ed9b7771048930e8d1a",
    "stationary_candidates.csv": "13ea70fdd117cf46c47f00004d4fedae42b301ad983b08141369b265135e77de",
    "stationary_candidates.geojson": "8c7fc6233e8188d75bb76b0fff4fffb1c288f4c0fd80490e781fa28a861fc4c6",
}
CLEANED_TEXT = frozenset({"vessel_type", "nav_status"})
CANDIDATE_TEXT = frozenset({"vessel_type"})
# Local copy of the 0.2.0.dev19 writer rule. Not imported from harborlens.
_TRIGGERS = frozenset("=+-@\t\r\uff1d\uff0b\uff0d\uff20")
_IGNORABLE = frozenset(
    "\t\n\v\f\r"
    "\u001c\u001d\u001e\u001f"
    "\u0085"
    " \u00a0\u1680"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a"
    "\u2028\u2029"
    "\u202f\u205f\u3000"
    "\ufeff\u200b\u200c\u200d\u200e\u200f"
    "\u2060\u2061\u2062\u2063\u2064"
    "\u206a\u206b\u206c\u206d\u206e\u206f"
    "\u00ad\u180e"
    "\u061c"
    "\u202a\u202b\u202c\u202d\u202e"
    "\u2066\u2067\u2068\u2069"
)
_DEV17_EXTRA = frozenset("\ufeff\u200b")


def _ignorable(character):
    return character in _IGNORABLE


def _dev17_ignorable(character):
    """Previous rule: Unicode whitespace, U+FEFF, and U+200B."""
    return character.isspace() or character in _DEV17_EXTRA


def _matches(text, min_apostrophes, ignorable=_ignorable):
    """``^'*`` or ``^'+``, then ignorables, then a trigger. Local to this proof."""
    index = 0
    size = len(text)
    apostrophes = 0
    while index < size and text[index] == "'":
        apostrophes += 1
        index += 1
    if apostrophes < min_apostrophes:
        return False
    while index < size:
        if text[index] in _TRIGGERS:
            return True
        if ignorable(text[index]):
            index += 1
            continue
        return False
    return False


def prefix_text(text):
    """0.2.0.dev19 writer rule, implemented in this test."""
    if _matches(text, 0):
        return "'" + text
    return text


def prefix_dev17(text):
    """0.2.0.dev17 writer rule, implemented in this test."""
    if _matches(text, 0, _dev17_ignorable):
        return "'" + text
    return text


def recover_text(text):
    """Symmetric reader rule, implemented in this test."""
    if _matches(text, 1):
        return text[1:]
    return text


def quote_field(text):
    if any(character in text for character in ",\"\r\n"):
        return '"' + text.replace('"', '""') + '"'
    return text


def render_csv(fieldnames, rows):
    """Same quoting and ``\\r\\n`` line ending as the single-file writer."""
    lines = [",".join(fieldnames)]
    for row in rows:
        lines.append(",".join(quote_field(row[name]) for name in fieldnames))
    return ("\r\n".join(lines) + "\r\n").encode("utf-8")


def read_csv(path):
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames), list(reader)


def project_rows(fieldnames, rows, text_fields, transform):
    projected = []
    for row in rows:
        copy = dict(row)
        for field in text_fields:
            copy[field] = transform(copy[field])
        projected.append(copy)
    return projected


def run_id_for(manifest, version):
    """Same settings hash as ``harborlens.provenance.add_provenance``."""
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
    payload = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def differing_paths(left, right, prefix=""):
    if type(left) is not type(right):
        return [prefix or "$"]
    if isinstance(left, dict):
        found = []
        for key in sorted(set(left) | set(right)):
            path = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                found.append(path)
            else:
                found.extend(differing_paths(left[key], right[key], path))
        return found
    if isinstance(left, list):
        if len(left) != len(right):
            return [prefix or "$"]
        found = []
        for index, (item, other) in enumerate(zip(left, right)):
            found.extend(differing_paths(item, other, f"{prefix}[{index}]"))
        return found
    if left != right:
        return [prefix or "$"]
    return []


def scrub_manifest(manifest):
    body = json.loads(json.dumps(manifest))
    body["input_file"] = "INPUT"
    body["output"] = "OUTPUT"
    body["code_version"]["git_commit"] = None
    return body


class FormulaFixtureTests(unittest.TestCase):
    def test_main_fixture_bytes_stay_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            manifest = run(MAIN_FIXTURE, out)
            for name, digest in MAIN_SHA256.items():
                blob = (out / name).read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), digest, name)
            self.assertEqual(manifest["code_version"]["package_version"], "0.2.0.dev19")

    def test_dev17_formula_goldens_stay_byte_identical(self):
        """History. These files are not regenerated from the current fixture."""
        for name, digest in DEV17_FORMULA_SHA256.items():
            blob = (DEV17_GOLDEN / name).read_bytes()
            self.assertEqual(hashlib.sha256(blob).hexdigest(), digest, name)

    def test_formula_fixture_matches_dev19_goldens(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            manifest = run(FIXTURE, out)
            for name, digest in FORMULA_SHA256.items():
                blob = (out / name).read_bytes()
                self.assertEqual(blob, (GOLDEN / name).read_bytes(), name)
                self.assertEqual(hashlib.sha256(blob).hexdigest(), digest, name)
                self.assertEqual(manifest["artifacts"][name]["sha256"], digest, name)
                self.assertEqual(manifest["artifacts"][name]["size_bytes"], len(blob), name)
            golden = json.loads((GOLDEN / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(scrub_manifest(manifest), scrub_manifest(golden))
            self.assertEqual(manifest["counts"]["written"], 430)
            self.assertEqual(manifest["events"]["stationary_candidates"], 43)
            self.assertEqual(manifest["events"]["vessels"], 43)

    def test_diff_proof_only_prefixes_text_cells(self):
        """Logical cells plus the local prefix are the written text cells.

        ``prefix_dev17`` is the previous rule. Cells that differ are the ones
        a newly ignorable character exposes.
        """
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            manifest = run(FIXTURE, out)
            self.assertEqual(manifest["run_id"], run_id_for(manifest, "0.2.0.dev19"))
            self.assertNotEqual(run_id_for(manifest, "0.2.0.dev17"), manifest["run_id"])

            _header, source_rows = read_csv(FIXTURE)
            logical_by_mmsi = {}
            for row in source_rows:
                logical_by_mmsi[row["MMSI"]] = (row["VesselType"], row["Status"])

            cleaned_fields, cleaned = read_csv(out / "houston_clean.csv")
            candidate_fields, candidates = read_csv(out / "stationary_candidates.csv")
            self._assert_text_projection(
                cleaned_fields, cleaned, CLEANED_TEXT,
                lambda row: {
                    "vessel_type": logical_by_mmsi[row["mmsi"]][0],
                    "nav_status": logical_by_mmsi[row["mmsi"]][1],
                },
                out / "houston_clean.csv",
            )
            self._assert_text_projection(
                candidate_fields, candidates, CANDIDATE_TEXT,
                lambda row: {"vessel_type": logical_by_mmsi[row["mmsi"]][0]},
                out / "stationary_candidates.csv",
            )
            self._assert_geojson_is_logical(out / "stationary_candidates.geojson", logical_by_mmsi)
            self._assert_manifest_diff_is_version_and_csv_hashes(
                manifest, out, cleaned_fields, cleaned, candidate_fields, candidates,
            )
            for row in cleaned:
                self.assertFalse(row["lon"].startswith("'"), row["lon"])
                self.assertTrue(row["lon"].startswith("-"), row["lon"])
                self.assertFalse(row["lat"].startswith("'"))
                self.assertFalse(row["sog_knots"].startswith("'"))
                self.assertFalse(row["mmsi"].startswith("'"))

    def _assert_text_projection(self, fieldnames, rows, text_fields, logical_for, path):
        dev16_rows = []
        dev17_rows = []
        previous_rows = []
        changed = []
        rule_changed = []
        for row in rows:
            logical = logical_for(row)
            dev16 = dict(row)
            dev17 = dict(row)
            previous = dict(row)
            for field in text_fields:
                source = logical[field]
                self.assertEqual(recover_text(row[field]), source, field)
                self.assertEqual(row[field], prefix_text(source), field)
                dev16[field] = source
                dev17[field] = prefix_text(source)
                previous[field] = prefix_dev17(source)
                if dev16[field] != dev17[field]:
                    changed.append(field)
                if previous[field] != dev17[field]:
                    rule_changed.append((field, source, dev17[field]))
            for field in fieldnames:
                if field in text_fields:
                    continue
                self.assertFalse(row[field].startswith("'"), field)
                dev16[field] = row[field]
                dev17[field] = row[field]
                previous[field] = row[field]
            dev16_rows.append(dev16)
            dev17_rows.append(dev17)
            previous_rows.append(previous)
        written = Path(path).read_bytes()
        self.assertEqual(render_csv(fieldnames, dev17_rows), written)
        self.assertNotEqual(render_csv(fieldnames, dev16_rows), written)
        self.assertNotEqual(render_csv(fieldnames, previous_rows), written)
        self.assertTrue(changed)
        self.assertTrue(rule_changed)
        for field, source, disk in rule_changed:
            self.assertIn(field, text_fields)
            self.assertEqual(disk, "'" + source)
            self.assertNotEqual(prefix_dev17(source), disk)
        dev16_written = render_csv(fieldnames, dev16_rows)
        dev17_written = render_csv(fieldnames, dev17_rows)
        dev16_fields, dev16_parsed = _parse_bytes(dev16_written)
        dev17_fields, dev17_parsed = _parse_bytes(dev17_written)
        self.assertEqual(dev16_fields, fieldnames)
        self.assertEqual(dev17_fields, fieldnames)
        for left, right in zip(dev16_parsed, dev17_parsed):
            for field in fieldnames:
                if left[field] == right[field]:
                    continue
                self.assertIn(field, text_fields)
                self.assertEqual(right[field], prefix_text(left[field]))

    def _assert_geojson_is_logical(self, path, logical_by_mmsi):
        document = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(document["type"], "FeatureCollection")
        for feature in document["features"]:
            properties = feature["properties"]
            logical = logical_by_mmsi[properties["mmsi"]][0]
            self.assertEqual(properties["vessel_type"], logical)
            self.assertFalse(str(properties["vessel_type"]).startswith("'") and logical.startswith("="))
            longitude = feature["geometry"]["coordinates"][0]
            self.assertLess(longitude, 0)

    def _assert_manifest_diff_is_version_and_csv_hashes(
        self, manifest, out, cleaned_fields, cleaned, candidate_fields, candidates,
    ):
        dev16 = json.loads(json.dumps(manifest))
        dev16["code_version"] = dict(manifest["code_version"])
        dev16["code_version"]["package_version"] = "0.2.0.dev16"
        dev16["run_id"] = run_id_for(manifest, "0.2.0.dev16")
        cleaned_dev16 = render_csv(
            cleaned_fields,
            project_rows(cleaned_fields, cleaned, CLEANED_TEXT, recover_text),
        )
        candidate_dev16 = render_csv(
            candidate_fields,
            project_rows(candidate_fields, candidates, CANDIDATE_TEXT, recover_text),
        )
        geojson = (out / "stationary_candidates.geojson").read_bytes()
        dev16["artifacts"] = json.loads(json.dumps(manifest["artifacts"]))
        dev16["artifacts"]["houston_clean.csv"] = {
            "sha256": hashlib.sha256(cleaned_dev16).hexdigest(),
            "size_bytes": len(cleaned_dev16),
        }
        dev16["artifacts"]["stationary_candidates.csv"] = {
            "sha256": hashlib.sha256(candidate_dev16).hexdigest(),
            "size_bytes": len(candidate_dev16),
        }
        dev16["artifacts"]["stationary_candidates.geojson"] = {
            "sha256": hashlib.sha256(geojson).hexdigest(),
            "size_bytes": len(geojson),
        }
        diffs = differing_paths(dev16, manifest)
        allowed = {
            "run_id",
            "code_version.package_version",
            "artifacts.houston_clean.csv.sha256",
            "artifacts.houston_clean.csv.size_bytes",
            "artifacts.stationary_candidates.csv.sha256",
            "artifacts.stationary_candidates.csv.size_bytes",
        }
        self.assertEqual(set(diffs), allowed, diffs)
        self.assertNotIn("artifacts.stationary_candidates.geojson.sha256", diffs)
        self.assertEqual(
            manifest["artifacts"]["stationary_candidates.geojson"]["sha256"],
            hashlib.sha256(geojson).hexdigest(),
        )

    def test_recount_and_verify_use_the_written_bytes(self):
        """The release recount reads the prefixed CSV and returns the written row count.

        SHA-256 in the manifest is the hash of those bytes. ``harborlens-verify``
        checks that hash. ``harborlens-verify-release`` still does not open the
        CSV; its scope string is unchanged.
        """
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "out"
            manifest = run(FIXTURE, out)
            verified = verify_manifest(out / "manifest.json")
            self.assertTrue(verified["ok"], verified)
            for name in FORMULA_SHA256:
                blob = (out / name).read_bytes()
                self.assertEqual(hashlib.sha256(blob).hexdigest(), manifest["artifacts"][name]["sha256"])
                self.assertEqual(len(blob), manifest["artifacts"][name]["size_bytes"])
            retained, groups = _recount_cleaned(out / "houston_clean.csv")
            _fields, rows = read_csv(out / "houston_clean.csv")
            self.assertEqual(retained, len(rows))
            self.assertEqual(retained, manifest["counts"]["written"])
            self.assertEqual(groups, manifest["events"]["vessels"])
            self.assertEqual(groups, len({row["mmsi"] for row in rows}))
            records = {row["mmsi"]: row for row in read_candidates_csv(out / "stationary_candidates.csv")}
            self.assertEqual(len(records), 43)
            self.assertEqual(records["199010019"]["vessel_type"], "\u200c=cmd")
            self.assertEqual(records["199010036"]["vessel_type"], "\u200c\u200d\u00ad\u180e=cmd")
            self.assertEqual(records["199010040"]["vessel_type"], "x\u200c=cmd")
            self.assertEqual(records["199010043"]["vessel_type"], "'\u200c=x")
            self.assertEqual(records["199010001"]["vessel_type"], "=cmd")
            self.assertEqual(records["199010013"]["vessel_type"], "'abc")
            self.assertEqual(records["199010014"]["vessel_type"], "'=x")
            self.assertEqual(records["199010015"]["vessel_type"], "''=x")
            self.assertEqual(records["199010017"]["vessel_type"], "70")
            self.assertEqual(records["199010007"]["vessel_type"], "\uff1dcmd")
            for record in records.values():
                self.assertLess(record["centroid_lon"], 0)
        import harborlens.release_verify as release_verify
        source = inspect.getsource(release_verify)
        self.assertIn("signed_release_and_pinned_rights_only", source)
        self.assertNotIn("interpret_cleaned_row", source)
        self.assertNotIn("csv_safe", source)

    def test_multiday_source_files_json_stays_an_array(self):
        """A malicious file name inside the JSON array does not open a formula."""
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evil = root / "=cmd|'C calc.csv"
            other = root / "other.csv"
            _write_track(evil, "199010021", "=cmd")
            _write_track(other, "199010022", "70", moving=True)
            out = root / "out"
            run_multiday([evil, other], out)
            _fields, candidates = read_csv(out / "stationary_candidates.csv")
            self.assertEqual(len(candidates), 1)
            cell = candidates[0]["source_files_json"]
            self.assertTrue(cell.startswith("["), cell)
            self.assertFalse(cell.startswith("'"))
            self.assertNotIn(cell[0], _TRIGGERS)
            parsed = json.loads(cell)
            self.assertEqual(len(parsed), 1)
            self.assertTrue(parsed[0].startswith("=cmd|'C calc.csv@"), parsed[0])
            self.assertEqual(candidates[0]["vessel_type"], prefix_text("=cmd"))
            self.assertTrue(candidates[0]["centroid_lon"].startswith("-"))
            self.assertFalse(candidates[0]["centroid_lon"].startswith("'"))
            _clean_fields, cleaned = read_csv(out / "houston_clean.csv")
            evil_rows = [row for row in cleaned if row["mmsi"] == "199010021"]
            self.assertTrue(evil_rows)
            self.assertEqual(evil_rows[0]["vessel_type"], "'=cmd")
            self.assertTrue(evil_rows[0]["lon"].startswith("-"))
            document = json.loads((out / "stationary_candidates.geojson").read_text(encoding="utf-8"))
            self.assertEqual(document["features"][0]["properties"]["vessel_type"], "=cmd")
            self.assertEqual(document["features"][0]["properties"]["source_files"], parsed)


def _parse_bytes(blob):
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8"), newline=""))
    return list(reader.fieldnames), list(reader)


def _write_track(path, mmsi, vessel_type, moving=False):
    rows = []
    for step in range(10):
        minute = step * 4
        sog = "8.0" if moving else "0.1"
        rows.append([
            mmsi, f"2024-01-02T00:{minute:02d}:00Z", "29.73000", "-95.16000", sog, vessel_type, "0",
        ])
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"])
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
