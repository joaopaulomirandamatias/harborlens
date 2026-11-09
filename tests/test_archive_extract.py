"""Offline synthetic national-archive extraction tests (zstandard optional extra)."""
import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

import zstandard

from harborlens.ais import run
from harborlens.archive_extract import extract_archive
from harborlens.io_safe import AISInputError

FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_ais.csv"
START = "2024-01-02T00:00:00Z"
END = "2024-01-02T00:59:00Z"


class ArchiveExtractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive = self.root / "ais-2024-01-02.csv.zst"
        self.archive.write_bytes(zstandard.ZstdCompressor().compress(FIXTURE.read_bytes()))
        self.output = self.root / "houston.csv"

    def tearDown(self):
        self.temp.cleanup()

    def test_extract_and_reprocess_synthetic_records(self):
        report = extract_archive(self.archive, self.output, START, END)
        self.assertEqual(report["counts"]["rows_scanned"], 63)
        self.assertEqual(report["counts"]["selected"], 61)
        self.assertEqual(report["counts"]["invalid"], 1)
        self.assertEqual(report["counts"]["outside_bbox"], 1)
        self.assertEqual(report["rights_status"], "review_required")
        self.assertEqual(report["output_sha256"], hashlib.sha256(self.output.read_bytes()).hexdigest())
        self.assertTrue(self.output.with_name("houston.csv.source.json").exists())
        result = run(self.output, self.root / "results")
        self.assertEqual(result["counts"]["written"], 60)
        self.assertEqual(result["events"]["stationary_candidates"], 1)

    def test_explicit_time_window_changes_selection(self):
        report = extract_archive(
            self.archive, self.output, "2024-01-02T00:30:00Z", "2024-01-02T00:45:00Z"
        )
        self.assertLess(report["counts"]["selected"], 61)
        self.assertGreater(report["counts"]["selected"], 0)

    def test_refuses_silent_truncation_and_cleans_partial_files(self):
        with self.assertRaisesRegex(AISInputError, "exceed cap"):
            extract_archive(self.archive, self.output, START, END, max_rows=2)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.output.with_name("houston.csv.source.json").exists())
        self.assertFalse(self.output.with_name("houston.csv.partial").exists())

    def test_refuses_overwrite(self):
        extract_archive(self.archive, self.output, START, END)
        with self.assertRaises(FileExistsError):
            extract_archive(self.archive, self.output, START, END)

    def test_rejects_cross_day_and_invalid_box(self):
        with self.assertRaisesRegex(AISInputError, "one UTC day"):
            extract_archive(self.archive, self.output, START, "2024-01-03T01:00:00Z")
        with self.assertRaisesRegex(AISInputError, "bounding box"):
            extract_archive(self.archive, self.output, START, END, bbox=(0, 0, -1, 1))


if __name__ == "__main__":
    unittest.main()
