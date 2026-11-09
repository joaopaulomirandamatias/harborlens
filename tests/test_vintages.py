"""NOAA archive vintages, ZIP extraction and missing-value accounting (issue #36). No network."""
import csv
import io
import json
import sys
import tempfile
import unittest
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest import mock

import zstandard

import harborlens.download as download
from harborlens.ais import read_candidates_csv, run
from harborlens.archive_extract import extract_archive
from harborlens.io_safe import AISInputError
from harborlens.vintages import CSV2_HEADER, LEGACY_HEADER, header_style, vintage_for

DAY = datetime(2023, 6, 1)


def legacy_rows(minutes=60):
    return [["367000501", (DAY + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S"), 29.5, -95.0, 0.1, 360.0,
             511, "SYNTHETIC", "", "", 70, 1, 0, 0, 0, "", "B"] for i in range(0, minutes + 1, 5)]


def csv_bytes(header, rows):
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue().encode()


class FakeResponse(io.BytesIO):
    headers = {"Content-Length": "5"}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class RegistryTests(unittest.TestCase):
    def test_years_map_to_layouts_and_unknown_years_are_refused(self):
        self.assertEqual(vintage_for(date(2015, 1, 1)).layout, "marinecadastre_zip_daily_v1")
        self.assertEqual(vintage_for(date(2023, 6, 1)).url(date(2023, 6, 1)),
                         "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2023/AIS_2023_06_01.zip")
        self.assertEqual(vintage_for(date(2024, 1, 2)).url(date(2024, 1, 2)),
                         "https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-01-02.csv.zst")
        for year in (2014, 2027):
            with self.subTest(year=year), self.assertRaises(AISInputError):
                vintage_for(date(year, 1, 1))

    def test_header_styles(self):
        self.assertEqual(header_style(LEGACY_HEADER), "legacy_camel_case")
        self.assertEqual(header_style(CSV2_HEADER), "lowercase_snake_case")
        self.assertEqual(header_style(["a", "b"]), "unrecognized")

    def test_downloader_uses_registry_and_refuses_unknown_years(self):
        with tempfile.TemporaryDirectory() as folder:
            requested = []

            def fake(request, timeout):
                requested.append(request.full_url)
                return FakeResponse(b"bytes")

            with mock.patch.object(download, "urlopen", fake), \
                    mock.patch.object(sys, "argv", ["dl", "--date", "2023-06-01", "--directory", folder]):
                download.main()
            self.assertEqual(requested, ["https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2023/AIS_2023_06_01.zip"])
            self.assertTrue((Path(folder) / "AIS_2023_06_01.zip").is_file())
            with mock.patch.object(sys, "argv", ["dl", "--date", "2014-06-01", "--directory", folder]), \
                    self.assertRaises(SystemExit):
                download.main()


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_zip_archive_extracts_and_runs(self):
        archive = self.root / "AIS_2023_06_01.zip"
        with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as handle:
            handle.writestr("AIS_2023_06_01.csv", csv_bytes(LEGACY_HEADER, legacy_rows()))
        subset = self.root / "houston-2023-06-01.csv"
        report = extract_archive(archive, subset, "2023-06-01T00:00:00Z", "2023-06-01T23:59:59Z")
        self.assertEqual(report["source_vintage"]["layout"], "marinecadastre_zip_daily_v1")
        self.assertEqual(report["source_vintage"]["detected_header_style"], "legacy_camel_case")
        self.assertEqual(report["counts"]["selected"], 13)
        manifest = run(subset, self.root / "out")
        self.assertEqual(manifest["analysis_window"]["declarations"][0]["source"], "extraction_sidecar")
        record = read_candidates_csv(self.root / "out" / "stationary_candidates.csv")[0]
        self.assertEqual(record["transceiver_class"], "B")
        self.assertIsNone(record["length_m"])           # legacy sentinel 0 -> missing

    def test_compression_must_match_the_year_layout(self):
        archive = self.root / "ais-2023-06-01.csv.zst"
        archive.write_bytes(zstandard.ZstdCompressor().compress(csv_bytes(LEGACY_HEADER, legacy_rows())))
        with self.assertRaisesRegex(AISInputError, "zip-compressed"):
            extract_archive(archive, self.root / "x.csv", "2023-06-01T00:00:00Z", "2023-06-01T23:59:59Z")
        with self.assertRaisesRegex(AISInputError, "No verified NOAA daily archive layout"):
            extract_archive(archive, self.root / "y.csv", "2014-06-01T00:00:00Z", "2014-06-01T23:59:59Z")

    def test_null_values_are_missing_not_invalid(self):
        rows = [["367000601", "2025-03-01 00:00:00", "-95.0", "29.5", "0.1", "", "", "", "", "", "70", "1",
                 "", "", "", "", "A"],
                ["367000601", "2025-03-01 00:05:00", "-95.0", "", "0.1", "", "", "", "", "", "70", "1",
                 "", "", "", "", "A"],
                ["367000601", "2025-03-01 00:10:00", "-95.0", "29.5", "", "", "", "", "", "", "70", "1",
                 "", "", "", "", "A"],
                ["367000601", "2025-03-01 00:15:00", "-95.0", "not-a-number", "0.1", "", "", "", "", "", "70",
                 "1", "", "", "", "", "A"]]
        archive = self.root / "ais-2025-03-01.csv.zst"
        archive.write_bytes(zstandard.ZstdCompressor().compress(csv_bytes(CSV2_HEADER, rows)))
        report = extract_archive(archive, self.root / "sub.csv", "2025-03-01T00:00:00Z", "2025-03-01T23:59:59Z")
        self.assertEqual((report["counts"]["missing_value"], report["counts"]["invalid"]), (1, 1))
        manifest = run(self.root / "sub.csv", self.root / "out")
        # Of the two extracted rows, the one with an empty SOG is missing, not invalid.
        self.assertEqual((manifest["counts"]["missing_value"], manifest["counts"]["invalid"]), (1, 0))
        self.assertEqual(json.loads((self.root / "sub.csv.source.json").read_text())["source_vintage"]["year"], 2025)


if __name__ == "__main__":
    unittest.main()
