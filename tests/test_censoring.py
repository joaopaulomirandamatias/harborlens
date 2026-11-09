"""BR-019 analysis-window censoring tests (SPEC-002, issue #34). Synthetic AIS only."""
import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from harborlens.ais import EVENT_FIELDS, infer_candidates, ingest, run
from harborlens.censoring import AnalysisWindowError
from harborlens.multiday import run_multiday

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"
HEADER = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"]


def stop(mmsi, start, minutes, step=5, lat=29.5, lon=-95.0):
    """Stationary observations every ``step`` minutes for ``minutes`` minutes."""
    return [[mmsi, (start + timedelta(minutes=m)).strftime("%Y-%m-%d %H:%M:%S"), lat, lon, 0.1, "70", "1"]
            for m in range(0, minutes + 1, step)]


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        writer.writerows(rows)
    return path


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extraction_sidecar(path, start, end, digest=None):
    record = {"source_type": "local_noaa_daily_archive", "output_filename": path.name,
              "output_sha256": digest or sha(path), "window_start_utc": start, "window_end_utc": end,
              "rights_status": "review_required"}
    path.with_name(path.name + ".source.json").write_text(json.dumps(record))


def by_mmsi(out):
    with (out / "stationary_candidates.csv").open(newline="") as handle:
        return {row["mmsi"]: row for row in csv.DictReader(handle)}


DAY = datetime(2024, 1, 2)


class SingleFileCensoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        rows = (stop("367000001", DAY, 60)                              # 00:00-01:00, touches start
                + stop("367000002", DAY + timedelta(hours=2), 60)       # 02:00-03:00, interior
                + stop("367000003", DAY + timedelta(hours=5), 60))      # 05:00-06:00, touches end
        self.src = write_csv(self.root / "houston.csv", rows)

    def tearDown(self):
        self.tmp.cleanup()

    def test_edges_flagged_and_interior_not_censored(self):
        manifest = run(self.src, self.root / "out", window_start="2024-01-02T00:00:00Z",
                       window_end="2024-01-02T06:00:00Z")
        events = by_mmsi(self.root / "out")
        self.assertEqual((events["367000001"]["left_censoring"], events["367000001"]["right_censoring"]),
                         ("censored", "not_censored"))
        self.assertEqual((events["367000002"]["left_censoring"], events["367000002"]["right_censoring"]),
                         ("not_censored", "not_censored"))
        self.assertEqual((events["367000003"]["left_censoring"], events["367000003"]["right_censoring"]),
                         ("not_censored", "censored"))
        census = manifest["events"]["censoring"]
        self.assertEqual((census["left_censored"], census["right_censored"], census["uncensored"],
                          census["both_censored"], census["unknown"]), (1, 1, 1, 0, 0))
        window = manifest["analysis_window"]
        self.assertEqual(window["status"], "known")
        self.assertEqual(window["declarations"][0]["source"], "user_declared")
        self.assertEqual(window["observed_time_range"],
                         {"start_utc": "2024-01-02T00:00:00Z", "end_utc": "2024-01-02T06:00:00Z"})

    def test_whole_window_stop_is_censored_on_both_sides(self):
        src = write_csv(self.root / "long.csv", stop("367000009", DAY, 360))
        manifest = run(src, self.root / "long-out", window_start="2024-01-02T00:00:00Z",
                       window_end="2024-01-02T06:00:00Z")
        event = by_mmsi(self.root / "long-out")["367000009"]
        self.assertEqual((event["left_censoring"], event["right_censoring"]), ("censored", "censored"))
        self.assertEqual(manifest["events"]["censoring"]["both_censored"], 1)

    def test_without_window_censoring_is_unknown_never_false(self):
        manifest = run(self.src, self.root / "out")
        self.assertEqual(manifest["analysis_window"]["status"], "unknown")
        self.assertEqual(manifest["analysis_window"]["declarations"], [{"input": "houston.csv", "source": "none"}])
        for event in by_mmsi(self.root / "out").values():
            self.assertEqual((event["left_censoring"], event["right_censoring"]), ("unknown", "unknown"))
        self.assertEqual(manifest["events"]["censoring"]["unknown"], 3)

    def test_runs_without_window_keep_legacy_run_id(self):
        manifest = run(self.src, self.root / "out")
        settings = {"input_sha256": manifest["input_sha256"], "bbox_lon_lat": manifest["bbox_lon_lat"],
                    "method_parameters": manifest["method_parameters"], "method_version": "stationary-v0.1"}
        legacy = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.assertEqual(manifest["run_id"], legacy)
        windowed = run(self.src, self.root / "out2", window_start="2024-01-02T00:00:00Z",
                       window_end="2024-01-02T06:00:00Z")
        self.assertNotEqual(windowed["run_id"], legacy)

    def test_verified_extraction_sidecar_is_used_automatically(self):
        extraction_sidecar(self.src, "2024-01-02T00:00:00Z", "2024-01-02T06:00:00Z")
        manifest = run(self.src, self.root / "out")
        declaration = manifest["analysis_window"]["declarations"][0]
        self.assertEqual(declaration["source"], "extraction_sidecar")
        self.assertRegex(declaration["sidecar_sha256"], "^[a-f0-9]{64}$")
        self.assertEqual(by_mmsi(self.root / "out")["367000001"]["left_censoring"], "censored")

    def test_erddap_sidecar_is_supported(self):
        record = {"dataset": "AIS2024_AIS", "csv_sha256": sha(self.src),
                  "time_start_utc": "2024-01-02T00:00:00Z", "time_end_utc": "2024-01-02T06:00:00Z"}
        self.src.with_name(self.src.name + ".source.json").write_text(json.dumps(record))
        manifest = run(self.src, self.root / "out")
        self.assertEqual(manifest["analysis_window"]["declarations"][0]["source"], "erddap_sidecar")

    def test_sidecar_for_other_bytes_fails_closed(self):
        extraction_sidecar(self.src, "2024-01-02T00:00:00Z", "2024-01-02T06:00:00Z", digest="0" * 64)
        with self.assertRaisesRegex(AnalysisWindowError, "does not match the input bytes"):
            run(self.src, self.root / "out")

    def test_declaration_conflicting_with_sidecar_fails(self):
        extraction_sidecar(self.src, "2024-01-02T00:00:00Z", "2024-01-02T06:00:00Z")
        with self.assertRaisesRegex(AnalysisWindowError, "conflicts"):
            run(self.src, self.root / "out", window_start="2024-01-02T00:00:00Z",
                window_end="2024-01-02T12:00:00Z")

    def test_observations_outside_declared_window_fail(self):
        with self.assertRaisesRegex(AnalysisWindowError, "outside the declared analysis window"):
            run(self.src, self.root / "out", window_start="2024-01-02T01:00:00Z",
                window_end="2024-01-02T06:00:00Z")

    def test_invalid_window_declarations_fail(self):
        for start, end in (("2024-01-02T00:00:00Z", None), ("2024-01-02T00:00:00", "2024-01-02T06:00:00Z"),
                           ("2024-01-02T06:00:00Z", "2024-01-02T00:00:00Z")):
            with self.subTest(start=start, end=end):
                with self.assertRaises(AnalysisWindowError):
                    run(self.src, self.root / f"bad-{len(str(start))}-{end}".replace(":", ""),
                        window_start=start, window_end=end)

    def test_max_rows_truncation_makes_censoring_unknown(self):
        manifest = run(self.src, self.root / "out", max_rows=20, window_start="2024-01-02T00:00:00Z",
                       window_end="2024-01-02T06:00:00Z")
        self.assertTrue(manifest["input_truncated"])
        self.assertEqual(manifest["analysis_window"]["status"], "unknown")
        self.assertEqual(manifest["analysis_window"]["declarations"][0]["ignored_reason"],
                         "input_truncated_by_max_rows")

    def test_infer_candidates_default_is_unknown(self):
        cleaned = self.root / "clean.csv"
        ingest(self.src, cleaned)
        events, stats = infer_candidates(cleaned)
        self.assertTrue(all(e["left_censoring"] == e["right_censoring"] == "unknown" for e in events))
        self.assertEqual(stats["censoring"]["unknown"], len(events))

    def test_outputs_satisfy_schemas(self):
        manifest = run(self.src, self.root / "out", window_start="2024-01-02T00:00:00Z",
                       window_end="2024-01-02T06:00:00Z")
        manifest_schema = json.loads((SCHEMAS / "run-manifest.schema.json").read_text())
        candidate_schema = json.loads((SCHEMAS / "stationary-candidate.schema.json").read_text())
        for schema in (manifest_schema, candidate_schema):
            Draft202012Validator.check_schema(schema)
        Draft202012Validator(manifest_schema, format_checker=FormatChecker()).validate(manifest)
        cleaned = self.root / "out" / "houston_clean.csv"
        events, _ = infer_candidates(cleaned)
        validator = Draft202012Validator(candidate_schema, format_checker=FormatChecker())
        for event in events:
            validator.validate(event)
        self.assertEqual(EVENT_FIELDS[-2:], ["left_censoring", "right_censoring"])

    def test_real_extractor_sidecar_feeds_censoring(self):
        import zstandard
        from harborlens.archive_extract import extract_archive
        archive = self.root / "ais-2024-01-02.csv.zst"
        archive.write_bytes(zstandard.ZstdCompressor().compress(self.src.read_bytes()))
        subset = self.root / "subset.csv"
        extract_archive(archive, subset, "2024-01-02T00:00:00Z", "2024-01-02T06:00:00Z")
        manifest = run(subset, self.root / "out")
        self.assertEqual(manifest["analysis_window"]["declarations"][0]["source"], "extraction_sidecar")
        self.assertEqual(manifest["events"]["censoring"]["left_censored"], 1)
        self.assertEqual(manifest["events"]["censoring"]["right_censored"], 1)

    def test_cli_accepts_window_flags(self):
        out = self.root / "cli-out"
        result = subprocess.run(
            [sys.executable, "-m", "harborlens.cli", "--input", str(self.src), "--out", str(out),
             "--window-start", "2024-01-02T00:00:00Z", "--window-end", "2024-01-02T06:00:00Z"],
            capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout)["analysis_window"]["status"], "known")


class MultiDayCensoringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        evening, morning = DAY + timedelta(hours=18), DAY + timedelta(days=1)
        # Crosses midnight far from both outer edges; one stop touches the final edge.
        crossing = stop("367000010", DAY + timedelta(hours=23), 120)
        self.a = write_csv(self.root / "day-1.csv", [r for r in crossing if r[1] < "2024-01-03"]
                           + stop("367000011", evening, 60))
        self.b = write_csv(self.root / "day-2.csv", [r for r in crossing if r[1] >= "2024-01-03"]
                           + stop("367000012", morning + timedelta(hours=5), 59))

    def tearDown(self):
        self.tmp.cleanup()

    def sidecars(self):
        extraction_sidecar(self.a, "2024-01-02T18:00:00Z", "2024-01-02T23:59:59Z")
        extraction_sidecar(self.b, "2024-01-03T00:00:00Z", "2024-01-03T05:59:59Z")

    def test_adjacent_daily_windows_merge_into_one_block(self):
        self.sidecars()
        manifest = run_multiday([self.a, self.b], self.root / "out")
        window = manifest["analysis_window"]
        self.assertEqual(window["status"], "known")
        self.assertEqual(window["internal_gaps"], 0)
        self.assertEqual(window["blocks"], [{"start_utc": "2024-01-02T18:00:00Z", "end_utc": "2024-01-03T05:59:59Z"}])
        events = by_mmsi(self.root / "out")
        self.assertEqual(events["367000010"]["crosses_utc_date"], "True")
        self.assertEqual((events["367000010"]["left_censoring"], events["367000010"]["right_censoring"]),
                         ("not_censored", "not_censored"))
        self.assertEqual(events["367000011"]["left_censoring"], "censored")
        self.assertEqual(events["367000012"]["right_censoring"], "censored")
        self.assertEqual(manifest["events"]["censoring"]["uncensored"], 1)

    def test_separated_windows_report_internal_gap_and_censor_its_edges(self):
        extraction_sidecar(self.a, "2024-01-02T18:00:00Z", "2024-01-02T23:00:00Z")
        extraction_sidecar(self.b, "2024-01-03T01:00:00Z", "2024-01-03T05:59:59Z")
        a = write_csv(self.root / "gap-1.csv", stop("367000020", DAY + timedelta(hours=22), 60))
        b = write_csv(self.root / "gap-2.csv", stop("367000021", DAY + timedelta(days=1, hours=1), 60))
        extraction_sidecar(a, "2024-01-02T18:00:00Z", "2024-01-02T23:00:00Z")
        extraction_sidecar(b, "2024-01-03T01:00:00Z", "2024-01-03T05:59:59Z")
        manifest = run_multiday([a, b], self.root / "gap-out")
        self.assertEqual(manifest["analysis_window"]["internal_gaps"], 1)
        events = by_mmsi(self.root / "gap-out")
        self.assertEqual(events["367000020"]["right_censoring"], "censored")
        self.assertEqual(events["367000021"]["left_censoring"], "censored")

    def test_partial_sidecars_yield_unknown(self):
        extraction_sidecar(self.a, "2024-01-02T18:00:00Z", "2024-01-02T23:59:59Z")
        manifest = run_multiday([self.a, self.b], self.root / "out")
        self.assertEqual(manifest["analysis_window"]["status"], "unknown")
        sources = sorted(d["source"] for d in manifest["analysis_window"]["declarations"])
        self.assertEqual(sources, ["extraction_sidecar", "none"])
        self.assertEqual({e["left_censoring"] for e in by_mmsi(self.root / "out").values()}, {"unknown"})

    def test_explicit_window_with_sidecars_is_rejected(self):
        self.sidecars()
        with self.assertRaisesRegex(AnalysisWindowError, "do not also pass"):
            run_multiday([self.a, self.b], self.root / "out", window_start="2024-01-02T18:00:00Z",
                         window_end="2024-01-03T06:00:00Z")

    def test_explicit_window_without_sidecars(self):
        manifest = run_multiday([self.a, self.b], self.root / "out", window_start="2024-01-02T18:00:00Z",
                                window_end="2024-01-03T06:00:00Z")
        self.assertEqual(manifest["analysis_window"]["declarations"][0]["input"], "all_inputs")
        self.assertEqual(by_mmsi(self.root / "out")["367000011"]["left_censoring"], "censored")

    def test_multiday_outputs_satisfy_schemas(self):
        self.sidecars()
        manifest = run_multiday([self.a, self.b], self.root / "out")
        run_schema = json.loads((SCHEMAS / "multi-day-run.schema.json").read_text())
        feature_schema = json.loads((SCHEMAS / "multi-day-candidate-feature.schema.json").read_text())
        Draft202012Validator(run_schema, format_checker=FormatChecker()).validate(manifest)
        geo = json.loads((self.root / "out" / "stationary_candidates.geojson").read_text())
        validator = Draft202012Validator(feature_schema, format_checker=FormatChecker())
        for feature in geo["features"]:
            validator.validate(feature)


if __name__ == "__main__":
    unittest.main()
