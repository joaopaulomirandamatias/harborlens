"""Depth 512 is parsed and depth 513 is each reader's existing JSON error.

Synthetic documents only. No authentic AIS, MMSI label sheet, or secret.
Each test is tied to one guard: removing that guard makes this test fail.
"""
import contextlib
import csv
import hashlib
import io
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from harborlens.evaluation import (
    CAVEATS, SCHEMA_VERSION, VALIDATION_STATUS, main as evaluate_main,
    read_evaluation_report,
)
from harborlens.fr_fulltext import DOCUMENTS, main as fulltext_main
from harborlens.fr_timeline import main as fr_main
from harborlens.json_depth import MAX_JSON_NESTING, max_container_depth
from harborlens.labeling import sample_main
from harborlens.noaa_anchorages import main as noaa_main
from harborlens.provenance import main as verify_main
from harborlens.publication import main as publication_main
from harborlens.release_verify import main as release_main
from harborlens.track_context import main as track_main
from harborlens.usace import main as usace_main
from harborlens.vintage import main as vintage_main
from harborlens.zone_context import main as zone_main
from harborlens.cli import main as harborlens_main

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais.csv"
OUTER = [[-95.2, 29.7], [-95.0, 29.7], [-95.0, 29.8], [-95.2, 29.8], [-95.2, 29.7]]
SQUARE = [OUTER]


def _invoke(main, argv):
    stderr = io.StringIO()
    stdout = io.StringIO()
    with mock.patch.object(sys, "argv", argv), \
            contextlib.redirect_stderr(stderr), \
            contextlib.redirect_stdout(stdout):
        try:
            main()
        except SystemExit as caught:
            code = 0 if caught.code is None else caught.code
        else:
            code = 0
    return code, stdout.getvalue(), stderr.getvalue()


def _nested(levels):
    value = 0
    for _ in range(levels):
        value = [value]
    return value


def _at_depth(document, depth):
    """Return JSON text whose container depth is exactly ``depth``.

    The pad hangs off the root object, so a list of ``depth - 1`` arrays
    is depth ``depth`` even when the rest of the document is shallower.
    """
    body = json.loads(json.dumps(document))
    body["pad"] = _nested(depth - 1)
    text = json.dumps(body)
    if max_container_depth(text) != depth:
        raise AssertionError(max_container_depth(text))
    return text


def _run(root):
    run_dir = root / "run"
    code, _stdout, err = _invoke(harborlens_main, [
        "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
    ])
    if code != 0:
        raise AssertionError(err)
    return run_dir


def _assert_clean(test, code, stdout, err, phrase):
    test.assertEqual(code, 2, err)
    test.assertEqual(stdout, "")
    test.assertIn(phrase, err)
    test.assertNotIn("Traceback", err)
    test.assertNotIn("RecursionError", err)


class _Body:
    def __init__(self, raw):
        self.raw = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        self.headers = {"Content-Length": str(len(self.raw))}

    def read(self, _n=-1):
        return self.raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class VerifyManifestDepthTests(unittest.TestCase):
    def test_accepts_512_and_rejects_513(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = _run(root)
            manifest = run_dir / "manifest.json"
            record = json.loads(manifest.read_text(encoding="utf-8"))
            accepted = _at_depth(record, MAX_JSON_NESTING)
            manifest.write_text(accepted, encoding="utf-8")
            code, stdout, err = _invoke(verify_main, [
                "harborlens-verify", "--manifest", str(manifest),
            ])
            self.assertEqual(code, 0, err)
            self.assertIn('"ok": true', stdout)
            self.assertNotIn("Traceback", err)
            rejected = _at_depth(record, MAX_JSON_NESTING + 1)
            manifest.write_text(rejected, encoding="utf-8")
            code, stdout, err = _invoke(verify_main, [
                "harborlens-verify", "--manifest", str(manifest),
            ])
            _assert_clean(
                self, code, stdout, err,
                f"manifest '{manifest}' is not a valid HarborLens manifest",
            )


class EvaluateManifestRereadDepthTests(unittest.TestCase):
    """The second manifest parse, after ``verify_manifest`` has returned."""

    def _call(self, root, run_dir, manifest_text, out_name):
        manifest = run_dir / "manifest.json"
        manifest.write_text(manifest_text, encoding="utf-8")
        record = json.loads(manifest_text)
        labels = root / "labels.csv"
        labels.write_text(
            "sample_id,label,evidence_level,duration_judgement,"
            "true_start_utc,true_end_utc,adjudicator_id\n",
            encoding="utf-8",
        )
        sampling = root / f"{out_name}.sampling.json"
        sampling.write_text(json.dumps({
            "key": [],
            "frame": {"candidates": {}},
            "run_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
            "parameter_set": record["method_parameters"]["parameter_set"],
        }), encoding="utf-8")
        out = root / f"{out_name}.json"
        with mock.patch(
            "harborlens.evaluation.verify_manifest",
            return_value={"ok": True, "artifacts": {}},
        ):
            return out, _invoke(evaluate_main, [
                "harborlens-evaluate", "--run", str(run_dir),
                "--sampling", str(sampling), "--labels", str(labels),
                "--out", str(out), "--label-provenance", "synthetic",
            ])

    def test_accepts_512_and_rejects_513(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = _run(root)
            record = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            out, (code, stdout, err) = self._call(
                root, run_dir, _at_depth(record, MAX_JSON_NESTING), "ok",
            )
            self.assertEqual(code, 0, err)
            self.assertNotIn("is not a valid HarborLens manifest", err)
            self.assertTrue(out.is_file())
            manifest = run_dir / "manifest.json"
            _out, (code, stdout, err) = self._call(
                root, run_dir, _at_depth(record, MAX_JSON_NESTING + 1), "bad",
            )
            _assert_clean(
                self, code, stdout, err,
                f"manifest '{manifest}' is not a valid HarborLens manifest",
            )
            self.assertFalse((root / "bad.json").exists())


class EvaluationReportDepthTests(unittest.TestCase):
    def test_accepts_512_and_rejects_513(self):
        base = {
            "schema_version": SCHEMA_VERSION,
            "validation_status": VALIDATION_STATUS,
            "label_provenance": "synthetic",
            "caveat": CAVEATS["synthetic"],
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.json"
            path.write_text(_at_depth(base, MAX_JSON_NESTING), encoding="utf-8")
            loaded = read_evaluation_report(path)
            self.assertEqual(loaded["schema_version"], SCHEMA_VERSION)
            self.assertEqual(loaded["validation_status"], VALIDATION_STATUS)
            path.write_text(_at_depth(base, MAX_JSON_NESTING + 1), encoding="utf-8")
            with self.assertRaises(Exception) as caught:
                read_evaluation_report(path)
            self.assertEqual(type(caught.exception).__name__, "EvaluationReportError")
            self.assertIn("is not a readable evaluation report", str(caught.exception))
            self.assertNotIn("RecursionError", str(caught.exception))


class LabelSampleManifestDepthTests(unittest.TestCase):
    def test_accepts_512_and_rejects_513(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = _run(root)
            manifest = run_dir / "manifest.json"
            record = json.loads(manifest.read_text(encoding="utf-8"))

            def draw(text, sheet_name):
                manifest.write_text(text, encoding="utf-8")
                sheet = root / sheet_name
                with mock.patch(
                    "harborlens.labeling.verify_manifest",
                    return_value={"ok": True, "artifacts": {}},
                ):
                    return sheet, _invoke(sample_main, [
                        "harborlens-label-sample", "--run", str(run_dir),
                        "--sheet", str(sheet), "--seed", "1",
                    ])

            sheet, (code, stdout, err) = draw(_at_depth(record, MAX_JSON_NESTING), "ok.csv")
            self.assertEqual(code, 0, err)
            self.assertTrue(sheet.is_file())
            self.assertNotIn("is not a valid HarborLens manifest", err)
            bad, (code, stdout, err) = draw(
                _at_depth(record, MAX_JSON_NESTING + 1), "bad.csv",
            )
            _assert_clean(
                self, code, stdout, err,
                f"manifest '{manifest}' is not a valid HarborLens manifest",
            )
            self.assertFalse(bad.exists())


class ZoneContextDepthTests(unittest.TestCase):
    def _files(self, root, candidate_text):
        candidates = root / "candidates.geojson"
        zones = root / "zones.geojson"
        candidates.write_text(candidate_text, encoding="utf-8")
        zones.write_text(json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature", "id": "101",
                "geometry": {"type": "Polygon", "coordinates": SQUARE},
                "properties": {
                    "geometry_review_status": "unreviewed",
                    "historical_validity": "not_verified",
                },
            }],
        }), encoding="utf-8")
        return candidates, zones

    def test_accepts_512_and_rejects_513(self):
        base = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-95.1, 29.75]},
                "properties": {
                    "event_id": "fixture",
                    "confidence_label": "unvalidated",
                    "type": "stationary_candidate",
                },
            }],
        }
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidates, zones = self._files(root, _at_depth(base, MAX_JSON_NESTING))
            out = root / "ok.geojson"
            code, stdout, err = _invoke(zone_main, [
                "harborlens-zone-context", "--candidates", str(candidates),
                "--polygons", str(zones), "--out", str(out),
            ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            self.assertNotIn("Invalid GeoJSON document", err)
            candidates.write_text(_at_depth(base, MAX_JSON_NESTING + 1), encoding="utf-8")
            bad = root / "bad.geojson"
            code, stdout, err = _invoke(zone_main, [
                "harborlens-zone-context", "--candidates", str(candidates),
                "--polygons", str(zones), "--out", str(bad),
            ])
            _assert_clean(self, code, stdout, err, "Invalid GeoJSON document")
            self.assertFalse(bad.exists())


class TrackContextDepthTests(unittest.TestCase):
    def test_accepts_512_and_rejects_513(self):
        base_time = datetime(2024, 1, 2, 23, 40, tzinfo=timezone.utc)
        mmsi = "199080001"
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cleaned = root / "houston_clean.csv"
            with cleaned.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow([
                    "mmsi", "timestamp_utc", "lat", "lon", "sog_knots",
                    "vessel_type", "nav_status",
                ])
                for index in range(10):
                    stamp = (base_time + timedelta(minutes=index * 5)).isoformat().replace("+00:00", "Z")
                    writer.writerow([mmsi, stamp, 29.75, -95.16, 0.2, 70, 5])
            start = base_time.isoformat().replace("+00:00", "Z")
            last = (base_time + timedelta(minutes=9 * 5)).isoformat().replace("+00:00", "Z")
            candidates = root / "candidates.geojson"
            candidates.write_text(json.dumps({
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [-95.16, 29.75]},
                    "properties": {
                        "event_id": "event-test-001", "mmsi": mmsi,
                        "start_utc": start, "end_utc": last, "point_count": 10,
                        "type": "stationary_candidate", "confidence_label": "unvalidated",
                    },
                }],
            }), encoding="utf-8")
            polygons = root / "zones.geojson"
            zone_doc = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature", "id": "1",
                    "geometry": {"type": "Polygon", "coordinates": SQUARE},
                    "properties": {
                        "historical_validity": "not_verified",
                        "geometry_review_status": "unreviewed",
                        "source_layer": "NOAA Designated Anchorage Areas",
                    },
                }],
            }
            polygons.write_text(_at_depth(zone_doc, MAX_JSON_NESTING), encoding="utf-8")
            receipt = root / "zones.geojson.source.json"
            receipt.write_text(json.dumps({
                "output_sha256": hashlib.sha256(polygons.read_bytes()).hexdigest(),
                "historical_validity": "not_verified",
                "geometry_review_status": "unreviewed",
                "rights_status": "review_required",
                "retrieved_at_utc": "2026-11-09T07:00:00Z",
            }), encoding="utf-8")
            out = root / "ok.geojson"
            code, _stdout, err = _invoke(track_main, [
                "harborlens-track-context", "--cleaned", str(cleaned),
                "--candidates", str(candidates), "--polygons", str(polygons),
                "--out", str(out),
            ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            polygons.write_text(_at_depth(zone_doc, MAX_JSON_NESTING + 1), encoding="utf-8")
            receipt.write_text(json.dumps({
                "output_sha256": hashlib.sha256(polygons.read_bytes()).hexdigest(),
                "historical_validity": "not_verified",
                "geometry_review_status": "unreviewed",
                "rights_status": "review_required",
                "retrieved_at_utc": "2026-11-09T07:00:00Z",
            }), encoding="utf-8")
            bad = root / "bad.geojson"
            code, stdout, err = _invoke(track_main, [
                "harborlens-track-context", "--cleaned", str(cleaned),
                "--candidates", str(candidates), "--polygons", str(polygons),
                "--out", str(bad),
            ])
            _assert_clean(self, code, stdout, err, "Invalid JSON input")
            self.assertFalse(bad.exists())


class PublicationJsonDepthTests(unittest.TestCase):
    def _call(self, root, run_dir, manifest_text):
        (run_dir / "manifest.json").write_text(manifest_text, encoding="utf-8")
        source = root / "input.csv"
        if not source.exists():
            source.write_bytes(FIXTURE.read_bytes())
        (root / "input.csv.source.json").write_text("{}", encoding="utf-8")
        return _invoke(publication_main, [
            "harborlens-release-summary", "--run", str(run_dir),
            "--source-file", str(source),
            "--rights-register", str(root / "rights.json"),
            "--dry-run",
        ])

    def test_accepts_512_and_rejects_513(self):
        """Depth 512 is parsed. The next existing sidecar gate then speaks.

        A schema-valid aggregate release is not 512 containers deep. The
        accept case is that the depth gate lets the parser run.
        """
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = _run(root)
            record = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
            code, stdout, err = self._call(root, run_dir, _at_depth(record, MAX_JSON_NESTING))
            self.assertEqual(code, 2, err)
            self.assertEqual(stdout, "")
            self.assertIn("Acquisition lacks a source-rights receipt", err)
            self.assertNotIn("Missing or invalid JSON evidence", err)
            self.assertNotIn("Traceback", err)
            code, stdout, err = self._call(
                root, run_dir, _at_depth(record, MAX_JSON_NESTING + 1),
            )
            _assert_clean(self, code, stdout, err, "Missing or invalid JSON evidence")


class ReleaseVerifyDepthTests(unittest.TestCase):
    def _argv(self, path, root):
        key = root / "reviewer.pem"
        key.write_text("synthetic\n", encoding="utf-8")
        return [
            "harborlens-verify-release", "--release", str(path),
            "--rights-register", str(root / "rights.json"),
            "--expected-rights-register-sha256", "a" * 64,
            "--trusted-reviewer-key", str(key),
            "--trusted-reviewer-key-sha256", "b" * 64,
            "--trusted-reviewer-id", "rev1",
            "--purpose", "public_aggregates",
            "--source-id", "noaa_pmel_erddap",
            "--dataset-version", "AIS2024_AIS",
        ]

    def test_accepts_512_parse_and_rejects_513(self):
        """Depth 512 reaches the existing field check. Depth 513 does not.

        The release allowlist has no nested array, so a verified release
        cannot be 512 containers deep. Accept means the parser ran.
        """
        base = {"summary": {}, "summary_sha256": "c" * 64, "release_review": {}}
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "release.json"
            path.write_text(_at_depth(base, MAX_JSON_NESTING), encoding="utf-8")
            code, stdout, err = _invoke(release_main, self._argv(path, root))
            self.assertEqual(code, 2, err)
            self.assertEqual(stdout, "")
            self.assertIn("Unexpected top-level release fields", err)
            self.assertNotIn("unreadable or malformed", err)
            self.assertNotIn("Traceback", err)
            path.write_text(_at_depth(base, MAX_JSON_NESTING + 1), encoding="utf-8")
            code, stdout, err = _invoke(release_main, self._argv(path, root))
            _assert_clean(self, code, stdout, err, "Release is unreadable or malformed")
            deep = root / "deep.json"
            deep.write_text("[" * 12000 + "0" + "]" * 12000, encoding="utf-8")
            self.assertLess(deep.stat().st_size, 128 * 1024)
            code, stdout, err = _invoke(release_main, self._argv(deep, root))
            _assert_clean(self, code, stdout, err, "Release is unreadable or malformed")


class UsaceDepthTests(unittest.TestCase):
    def _payload(self, depth):
        return _at_depth({
            "features": [{
                "attributes": {
                    "OBJECTID": 8, "NAV_UNIT_ID": "N-8",
                    "NAV_UNIT_NAME": "Demo Facility 8", "FAC_TYPE": "DOCK",
                    "PORT_NAME": "HOUSTON", "WTWY_NAME": "HOUSTON SHIP CHANNEL",
                    "DATA_RECORD_STATUS": "ACTIVE",
                },
                "geometry": {"x": -95.10, "y": 29.75},
            }],
            "exceededTransferLimit": False,
        }, depth).encode("utf-8")

    def test_accepts_512_and_rejects_513(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            out = root / "facilities.geojson"
            with mock.patch("harborlens.usace.urlopen", return_value=_Body(self._payload(MAX_JSON_NESTING))):
                code, _stdout, err = _invoke(usace_main, [
                    "harborlens-fetch-usace", "--out", str(out),
                ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            bad = root / "bad.geojson"
            with mock.patch("harborlens.usace.urlopen", return_value=_Body(self._payload(MAX_JSON_NESTING + 1))):
                code, stdout, err = _invoke(usace_main, [
                    "harborlens-fetch-usace", "--out", str(bad),
                ])
            _assert_clean(self, code, stdout, err, "USACE service returned non-JSON content")
            self.assertFalse(bad.exists())


class NoaaAnchorageDepthTests(unittest.TestCase):
    def _opener(self, depth):
        ids = _at_depth({
            "objectIds": [101], "objectIdFieldName": "OBJECTID",
        }, depth).encode("utf-8")
        features = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature", "id": 101,
                "geometry": {"type": "Polygon", "coordinates": SQUARE},
                "properties": {"OBJECTID": 101, "name": "Synthetic Anchorage"},
            }],
        }).encode("utf-8")

        def open_url(request, timeout):
            if "returnIdsOnly" in request.full_url:
                return _Body(ids)
            return _Body(features)

        return open_url

    def test_accepts_512_and_rejects_513(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            out = root / "anchorages.geojson"
            with mock.patch("harborlens.noaa_anchorages.urlopen", side_effect=self._opener(MAX_JSON_NESTING)):
                code, _stdout, err = _invoke(noaa_main, [
                    "harborlens-fetch-noaa-anchorages", "--out", str(out),
                ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            bad = root / "bad.geojson"
            with mock.patch("harborlens.noaa_anchorages.urlopen", side_effect=self._opener(MAX_JSON_NESTING + 1)):
                code, stdout, err = _invoke(noaa_main, [
                    "harborlens-fetch-noaa-anchorages", "--out", str(bad),
                ])
            _assert_clean(self, code, stdout, err, "NOAA service returned non-JSON data")
            self.assertFalse(bad.exists())


class VintageDepthTests(unittest.TestCase):
    def test_accepts_512_and_rejects_513(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            polygons = root / "areas.geojson"
            polygons.write_text('{"type":"FeatureCollection","features":[]}\n', encoding="utf-8")
            receipt = {
                "source_agency": "NOAA",
                "output_sha256": hashlib.sha256(polygons.read_bytes()).hexdigest(),
                "retrieved_at_utc": "2026-11-09T08:00:00Z",
                "historical_validity": "not_verified",
                "geometry_review_status": "unreviewed",
                "rights_status": "review_required",
            }
            side = root / "areas.geojson.source.json"
            side.write_text(_at_depth(receipt, MAX_JSON_NESTING), encoding="utf-8")
            out = root / "ok.json"
            code, stdout, err = _invoke(vintage_main, [
                "harborlens-geometry-vintage", "--polygons", str(polygons),
                "--start", "2024-01-02T00:00:00Z", "--end", "2024-01-02T06:00:00Z",
                "--out", str(out),
            ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            self.assertIn("not_verified", stdout)
            side.write_text(_at_depth(receipt, MAX_JSON_NESTING + 1), encoding="utf-8")
            bad = root / "bad.json"
            code, stdout, err = _invoke(vintage_main, [
                "harborlens-geometry-vintage", "--polygons", str(polygons),
                "--start", "2024-01-02T00:00:00Z", "--end", "2024-01-02T06:00:00Z",
                "--out", str(bad),
            ])
            _assert_clean(self, code, stdout, err, "Invalid metadata JSON")
            self.assertFalse(bad.exists())


class FederalRegisterTimelineDepthTests(unittest.TestCase):
    def _page(self, depth):
        return _at_depth({
            "count": 1,
            "results": [{
                "document_number": "2023-00001",
                "title": "Synthetic Part 110 change",
                "publication_date": "2023-08-11",
                "effective_on": "2023-08-11",
                "type": "Rule",
                "html_url": "https://www.federalregister.gov/documents/synthetic",
                "cfr_references": [{"title": 33, "part": 110}],
                "abstract": "Synthetic only.",
            }],
        }, depth).encode("utf-8")

    def test_accepts_512_and_rejects_513(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            out = root / "ok.json"
            with mock.patch("harborlens.fr_timeline.urlopen", return_value=_Body(self._page(MAX_JSON_NESTING))):
                code, stdout, err = _invoke(fr_main, [
                    "harborlens-fr-timeline", "--out", str(out),
                ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            self.assertIn("NOT_DETERMINED", stdout)
            bad = root / "bad.json"
            with mock.patch("harborlens.fr_timeline.urlopen", return_value=_Body(self._page(MAX_JSON_NESTING + 1))):
                code, stdout, err = _invoke(fr_main, [
                    "harborlens-fr-timeline", "--out", str(bad),
                ])
            _assert_clean(self, code, stdout, err, "Official API response is not valid JSON")
            self.assertFalse(bad.exists())


class FederalRegisterFulltextDepthTests(unittest.TestCase):
    def _opener(self, depth):
        def open_url(request, timeout=None):
            url = request.full_url
            number = next(item for item, _published in DOCUMENTS if item in url)
            published = dict(DOCUMENTS)[number]
            if url.endswith(".json"):
                body = _at_depth({
                    "document_number": number,
                    "publication_date": published,
                    "type": "Proposed Rule",
                    "title": "Synthetic Columbia River proposal",
                    "effective_on": None,
                    "html_url": "https://www.federalregister.gov/documents/synthetic",
                    "raw_text_url": (
                        "https://www.federalregister.gov/documents/full_text/text/"
                        + published.replace("-", "/") + "/" + number + ".txt"
                    ),
                }, depth)
                return _Body(body)
            return _Body(("Columbia River Oregon Washington proposed anchorage text. " * 25).encode("utf-8"))

        class _Opener:
            def open(self, request, timeout=None):
                return open_url(request, timeout)

        return _Opener()

    def test_accepts_512_and_rejects_513(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            out = root / "ok.json"
            with mock.patch("harborlens.fr_fulltext.build_opener", return_value=self._opener(MAX_JSON_NESTING)):
                code, stdout, err = _invoke(fulltext_main, [
                    "harborlens-fr-fulltext", "--out", str(out),
                ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            self.assertIn("NOT_DETERMINED", stdout)
            bad = root / "bad.json"
            with mock.patch("harborlens.fr_fulltext.build_opener", return_value=self._opener(MAX_JSON_NESTING + 1)):
                code, stdout, err = _invoke(fulltext_main, [
                    "harborlens-fr-fulltext", "--out", str(bad),
                ])
            _assert_clean(self, code, stdout, err, "Official document metadata was not valid JSON")
            self.assertFalse(bad.exists())


if __name__ == "__main__":
    unittest.main()
