"""Non-object JSON exits 2, and a UTF-8 BOM is accepted where main accepted it.

Synthetic documents only. No authentic AIS, licensed data, or secrets.
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

from harborlens.cli import main as harborlens_main
from harborlens.fr_timeline import main as fr_main
from harborlens.noaa_anchorages import main as noaa_main
from harborlens.publication import main as publication_main
from harborlens.release_verify import main as release_main
from harborlens.track_context import main as track_main
from harborlens.usace import main as usace_main
from harborlens.zone_context import main as zone_main

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais.csv"
BOM = b"\xef\xbb\xbf"
OUTER = [[-95.2, 29.7], [-95.0, 29.7], [-95.0, 29.8], [-95.2, 29.8], [-95.2, 29.7]]
NON_OBJECTS = (
    ("array", "[]"),
    ("string", '"hello"'),
    ("number", "1"),
    ("null", "null"),
)


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


def _assert_domain(test, code, stdout, err, phrase):
    test.assertEqual(code, 2, err)
    test.assertEqual(stdout, "")
    test.assertIn(phrase, err)
    test.assertNotIn("Traceback", err)
    test.assertNotIn("AttributeError", err)


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


def _zones():
    return {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature", "id": "101",
            "geometry": {"type": "Polygon", "coordinates": [OUTER]},
            "properties": {
                "geometry_review_status": "unreviewed",
                "historical_validity": "not_verified",
            },
        }],
    }


def _candidates():
    return {
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


class ZoneNonObjectTests(unittest.TestCase):
    def test_object_is_accepted_and_each_non_object_exits_2(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            candidates = root / "candidates.geojson"
            zones = root / "zones.geojson"
            zones.write_text(json.dumps(_zones()), encoding="utf-8")
            candidates.write_text(json.dumps(_candidates()), encoding="utf-8")
            out = root / "ok.geojson"
            code, _stdout, err = _invoke(zone_main, [
                "harborlens-zone-context", "--candidates", str(candidates),
                "--polygons", str(zones), "--out", str(out),
            ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            self.assertNotIn("Traceback", err)
            for name, text in NON_OBJECTS:
                with self.subTest(kind=name):
                    candidates.write_text(text, encoding="utf-8")
                    bad = root / f"bad-{name}.geojson"
                    code, stdout, err = _invoke(zone_main, [
                        "harborlens-zone-context", "--candidates", str(candidates),
                        "--polygons", str(zones), "--out", str(bad),
                    ])
                    _assert_domain(self, code, stdout, err, "Invalid GeoJSON document")
                    self.assertFalse(bad.exists())


class TrackNonObjectTests(unittest.TestCase):
    def _prepare(self, root, polygon_text):
        base = datetime(2024, 1, 2, 23, 40, tzinfo=timezone.utc)
        cleaned = root / "houston_clean.csv"
        with cleaned.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow([
                "mmsi", "timestamp_utc", "lat", "lon", "sog_knots",
                "vessel_type", "nav_status",
            ])
            for index in range(10):
                stamp = (base + timedelta(minutes=index * 5)).isoformat().replace("+00:00", "Z")
                writer.writerow(["199080001", stamp, 29.75, -95.16, 0.2, 70, 5])
        start = base.isoformat().replace("+00:00", "Z")
        last = (base + timedelta(minutes=45)).isoformat().replace("+00:00", "Z")
        candidates = root / "candidates.geojson"
        candidates.write_text(json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [-95.16, 29.75]},
                "properties": {
                    "event_id": "event-test-001", "mmsi": "199080001",
                    "start_utc": start, "end_utc": last, "point_count": 10,
                    "type": "stationary_candidate", "confidence_label": "unvalidated",
                },
            }],
        }), encoding="utf-8")
        polygons = root / "zones.geojson"
        polygons.write_text(polygon_text, encoding="utf-8")
        (root / "zones.geojson.source.json").write_text(json.dumps({
            "output_sha256": hashlib.sha256(polygons.read_bytes()).hexdigest(),
            "historical_validity": "not_verified",
            "geometry_review_status": "unreviewed",
            "rights_status": "review_required",
            "retrieved_at_utc": "2026-11-09T07:00:00Z",
        }), encoding="utf-8")
        return cleaned, candidates, polygons

    def test_object_is_accepted_and_each_non_object_exits_2(self):
        zone = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature", "id": "1",
                "geometry": {"type": "Polygon", "coordinates": [OUTER]},
                "properties": {
                    "historical_validity": "not_verified",
                    "geometry_review_status": "unreviewed",
                    "source_layer": "NOAA Designated Anchorage Areas",
                },
            }],
        })
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            cleaned, candidates, polygons = self._prepare(root, zone)
            out = root / "ok.geojson"
            code, _stdout, err = _invoke(track_main, [
                "harborlens-track-context", "--cleaned", str(cleaned),
                "--candidates", str(candidates), "--polygons", str(polygons),
                "--out", str(out),
            ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            for name, text in NON_OBJECTS:
                with self.subTest(kind=name):
                    self._prepare(root, text)
                    bad = root / f"bad-{name}.geojson"
                    code, stdout, err = _invoke(track_main, [
                        "harborlens-track-context", "--cleaned", str(cleaned),
                        "--candidates", str(candidates), "--polygons", str(polygons),
                        "--out", str(bad),
                    ])
                    _assert_domain(self, code, stdout, err, "Invalid JSON input")
                    self.assertFalse(bad.exists())


def _run(root):
    run_dir = root / "run"
    code, _stdout, err = _invoke(harborlens_main, [
        "harborlens", "--input", str(FIXTURE), "--out", str(run_dir),
    ])
    if code != 0:
        raise AssertionError(err)
    return run_dir


class PublicationBomTests(unittest.TestCase):
    def _call(self, root, run_dir):
        source = root / "input.csv"
        source.write_bytes(FIXTURE.read_bytes())
        (root / "input.csv.source.json").write_text("{}", encoding="utf-8")
        return _invoke(publication_main, [
            "harborlens-release-summary", "--run", str(run_dir),
            "--source-file", str(source),
            "--rights-register", str(root / "rights.json"),
            "--dry-run",
        ])

    def test_utf8_bom_is_parsed_then_refused_by_verify_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            run_dir = _run(root)
            manifest = run_dir / "manifest.json"
            plain = manifest.read_bytes()
            code, stdout, plain_err = self._call(root, run_dir)
            self.assertEqual(code, 2)
            self.assertIn("Acquisition lacks a source-rights receipt", plain_err)
            manifest.write_bytes(BOM + plain)
            bom_code, bom_stdout, bom_err = self._call(root, run_dir)
            # ``_json_file`` accepts the BOM. ``verify_manifest`` still reads
            # the file as UTF-8 text, which is the refusal main produced.
            self.assertEqual(bom_code, 2)
            self.assertEqual(bom_stdout, stdout)
            self.assertIn("Run manifest cannot be verified", bom_err)
            self.assertNotIn("Missing or invalid JSON evidence", bom_err)
            self.assertNotIn("Traceback", bom_err)


class ReleaseBomTests(unittest.TestCase):
    def _call(self, path, root):
        key = root / "reviewer.pem"
        key.write_text("synthetic\n", encoding="utf-8")
        return _invoke(release_main, [
            "harborlens-verify-release", "--release", str(path),
            "--rights-register", str(root / "rights.json"),
            "--expected-rights-register-sha256", "a" * 64,
            "--trusted-reviewer-key", str(key),
            "--trusted-reviewer-key-sha256", "b" * 64,
            "--trusted-reviewer-id", "rev1",
            "--purpose", "public_aggregates",
            "--source-id", "noaa_pmel_erddap",
            "--dataset-version", "AIS2024_AIS",
        ])

    def test_utf8_bom_reaches_the_same_field_check(self):
        body = json.dumps({
            "summary": {}, "summary_sha256": "c" * 64, "release_review": {},
        }).encode("utf-8")
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            path = root / "release.json"
            path.write_bytes(body)
            code, stdout, plain_err = self._call(path, root)
            path.write_bytes(BOM + body)
            bom_code, bom_stdout, bom_err = self._call(path, root)
            self.assertEqual((bom_code, bom_stdout, bom_err), (code, stdout, plain_err))
            self.assertEqual(bom_code, 2)
            self.assertIn("Summary has unapproved or missing fields", bom_err)
            self.assertNotIn("unreadable or malformed", bom_err)
            self.assertNotIn("Traceback", bom_err)
            deep = BOM + ("[" * 513 + "0" + "]" * 513).encode("ascii")
            path.write_bytes(deep)
            code, stdout, err = self._call(path, root)
            _assert_domain(self, code, stdout, err, "Release is unreadable or malformed")


class FederalRegisterBomTests(unittest.TestCase):
    def _page(self, prefix=b""):
        body = json.dumps({
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
        }).encode("utf-8")
        return _Body(prefix + body)

    def test_utf8_bom_is_a_valid_page(self):
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "fr.json"
            with mock.patch("harborlens.fr_timeline.urlopen", return_value=self._page(BOM)):
                code, stdout, err = _invoke(fr_main, [
                    "harborlens-fr-timeline", "--out", str(out),
                ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            self.assertIn("NOT_DETERMINED", stdout)
            self.assertNotIn("not valid JSON", err)


class UsaceBomTests(unittest.TestCase):
    def test_utf8_bom_is_valid_json(self):
        body = json.dumps({
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
        }).encode("utf-8")
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "facilities.geojson"
            with mock.patch("harborlens.usace.urlopen", return_value=_Body(BOM + body)):
                code, _stdout, err = _invoke(usace_main, [
                    "harborlens-fetch-usace", "--out", str(out),
                ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            self.assertNotIn("non-JSON", err)


class NoaaBomTests(unittest.TestCase):
    def test_utf8_bom_is_valid_json(self):
        ids = BOM + json.dumps({
            "objectIds": [101], "objectIdFieldName": "OBJECTID",
        }).encode("utf-8")
        features = json.dumps({
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature", "id": 101,
                "geometry": {"type": "Polygon", "coordinates": [OUTER]},
                "properties": {"OBJECTID": 101, "name": "Synthetic Anchorage"},
            }],
        }).encode("utf-8")

        def open_url(request, timeout):
            if "returnIdsOnly" in request.full_url:
                return _Body(ids)
            return _Body(features)

        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "anchorages.geojson"
            with mock.patch("harborlens.noaa_anchorages.urlopen", side_effect=open_url):
                code, _stdout, err = _invoke(noaa_main, [
                    "harborlens-fetch-noaa-anchorages", "--out", str(out),
                ])
            self.assertEqual(code, 0, err)
            self.assertTrue(out.is_file())
            self.assertNotIn("non-JSON", err)


if __name__ == "__main__":
    unittest.main()
