"""Volume ceilings and recorded limits (SPEC-001/SPEC-002, issue #35). Synthetic AIS only."""
import csv
import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import zstandard

import harborlens.multiday as multiday
from harborlens.ais import load_cleaned, run
from harborlens.archive_extract import MAX_MATCHING_ROWS, MAX_OUTPUT_MIB, extract_archive
from harborlens.io_safe import AISInputError
from harborlens.multiday import MAX_POINTS, MAX_SCRATCH_MIB, ScratchMeter, run_multiday
from harborlens.track_context import MAX_OBSERVATIONS_PER_EVENT, _load_candidates

HEADER = ["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "VesselType", "Status"]
DAY = datetime(2024, 1, 2)


def write(path, start, minutes, mmsi="367300001"):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(HEADER)
        for i in range(0, minutes, 5):
            writer.writerow([mmsi, (start + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S"),
                             29.5, -95.0, 0.1, "70", "1"])
    return path


class VolumeCapTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.a = write(self.root / "a.csv", DAY + timedelta(hours=23), 60)
        self.b = write(self.root / "b.csv", DAY + timedelta(days=1), 60)

    def tearDown(self):
        self.tmp.cleanup()

    def test_ceilings_cover_seven_full_houston_days(self):
        # ~560,000 rows per full day in the Houston research rectangle (2024-01-02/03 smokes).
        self.assertGreaterEqual(MAX_MATCHING_ROWS, 560_000)
        self.assertGreaterEqual(MAX_POINTS, 7 * 560_000)
        # Measured ~168 bytes of SQLite scratch per row on 3.9 million synthetic rows.
        self.assertGreaterEqual(MAX_SCRATCH_MIB * 1048576, 168 * 7 * 560_000)
        self.assertGreaterEqual(MAX_OBSERVATIONS_PER_EVENT, 7 * 24 * 60)

    def test_multiday_records_limits_and_scratch_peak(self):
        manifest = run_multiday([self.a, self.b], self.root / "out", max_points=MAX_POINTS,
                                max_scratch_mib=MAX_SCRATCH_MIB)
        self.assertEqual(manifest["limits"], {"max_points": MAX_POINTS, "max_scratch_mib": MAX_SCRATCH_MIB,
                                              "max_export_mib": multiday.DEFAULT_EXPORT_MIB})
        self.assertGreater(manifest["resources"]["scratch_peak_bytes"], 0)
        with self.assertRaises(AISInputError):
            run_multiday([self.a, self.b], self.root / "out2", max_points=MAX_POINTS + 1)

    def test_scratch_cap_fails_closed_without_outputs(self):
        tiny = lambda path, cap: ScratchMeter(path, 1024)  # noqa: E731
        with mock.patch.object(multiday, "ScratchMeter", tiny):
            with self.assertRaisesRegex(AISInputError, "scratch store exceeded"):
                run_multiday([self.a, self.b], self.root / "capped")
        self.assertEqual(list((self.root / "capped").glob("*")), [])

    def test_scratch_meter_tracks_peak(self):
        path = self.root / "db.sqlite3"
        meter = ScratchMeter(path, 10_000)
        self.assertEqual(meter.check(), 0)
        path.write_bytes(b"x" * 500)
        (self.root / "db.sqlite3-journal").write_bytes(b"x" * 100)
        self.assertEqual(meter.check(), 600)
        path.write_bytes(b"x" * 10)
        meter.check()
        self.assertEqual(meter.peak_bytes, 600)
        path.write_bytes(b"x" * 20_000)
        with self.assertRaises(AISInputError):
            meter.check()

    def test_extraction_accepts_full_day_ceiling_and_records_limits(self):
        archive = self.root / "ais-2024-01-02.csv.zst"
        archive.write_bytes(zstandard.ZstdCompressor().compress(self.a.read_bytes()))
        report = extract_archive(archive, self.root / "sub.csv", "2024-01-02T00:00:00Z",
                                 "2024-01-02T23:59:59Z", max_rows=MAX_MATCHING_ROWS,
                                 max_output_mib=MAX_OUTPUT_MIB)
        self.assertEqual(report["limits"]["max_rows"], MAX_MATCHING_ROWS)
        sidecar = json.loads((self.root / "sub.csv.source.json").read_text())
        self.assertEqual(sidecar["limits"], report["limits"])
        for kwargs in ({"max_rows": MAX_MATCHING_ROWS + 1}, {"max_output_mib": MAX_OUTPUT_MIB + 1}):
            with self.subTest(**kwargs), self.assertRaises(AISInputError):
                extract_archive(archive, self.root / "x.csv", "2024-01-02T00:00:00Z",
                                "2024-01-02T23:59:59Z", **kwargs)

    def test_single_file_manifest_records_row_limit(self):
        self.assertEqual(run(self.a, self.root / "r1")["limits"], {"max_rows": None})
        self.assertEqual(run(self.a, self.root / "r2", max_rows=5)["limits"], {"max_rows": 5})

    def test_in_memory_loader_fails_closed(self):
        run(self.a, self.root / "r")
        rows, _ = load_cleaned(self.root / "r" / "houston_clean.csv")
        self.assertEqual(len(rows), 12)
        with self.assertRaisesRegex(AISInputError, "in-memory row cap"):
            load_cleaned(self.root / "r" / "houston_clean.csv", max_rows=5)

    def test_track_context_accepts_week_long_candidates(self):
        path = self.root / "candidates.geojson"
        path.write_text(json.dumps({"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": {"type": "Point", "coordinates": [-95.0, 29.5]},
            "properties": {"event_id": "week-long", "mmsi": "367300001", "start_utc": "2024-01-02T00:00:00Z",
                           "end_utc": "2024-01-09T00:00:00Z", "point_count": 10_080,
                           "type": "stationary_candidate", "confidence_label": "unvalidated"}}]}))
        rows, method = _load_candidates(path)
        self.assertEqual(len(rows), 1)
        self.assertEqual(method["parameters_source"], "legacy_default_v0.1")


if __name__ == "__main__":
    unittest.main()
