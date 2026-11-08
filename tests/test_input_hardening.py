"""Adversarial and boundary tests use synthetic data only."""
import csv
import gzip
import math
import tempfile
import unittest
import zipfile
from pathlib import Path

from harborlens.ais import ingest
from harborlens.io_safe import AISInputError, stream_rows, MAX_ZIP_EXPANSION_RATIO


HEADER = "MMSI,BaseDateTime,LAT,LON,SOG,VesselType,Status\n"
VALID = "367800001,2024-01-02T00:00:00Z,29.73,-95.16,0.2,70,5\n"


class InputHardeningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, data):
        path = self.root / name
        path.write_text(data, encoding="utf-8")
        return path

    def test_reject_nan_and_infinite_coordinates_and_sog(self):
        rows = "".join((
            "367800002,2024-01-02T00:00:00Z,NaN,-95.16,0.2,70,0\n",
            "367800003,2024-01-02T00:00:00Z,29.73,Infinity,0.2,70,0\n",
            "367800004,2024-01-02T00:00:00Z,29.73,-95.16,NaN,70,0\n"
        ))
        raw = self.write("nan.csv", HEADER + VALID + rows)
        result = ingest(raw, self.root / "normalized.csv")
        self.assertEqual(result["counts"]["invalid"], 3)
        self.assertEqual(result["counts"]["written"], 1)

    def test_reject_zip_expansion_bomb_using_file_metadata(self):
        path = self.root / "bomb.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("sample.csv", HEADER + ("0" * 100_000))
        self.assertGreater(MAX_ZIP_EXPANSION_RATIO, 1)
        with self.assertRaisesRegex(AISInputError, "compression ratio"):
            list(stream_rows(path))

    def test_reject_zip_multiple_entries(self):
        path = self.root / "multiple.zip"
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("one.csv", HEADER + VALID)
            archive.writestr("two.csv", HEADER + VALID)
        with self.assertRaisesRegex(AISInputError, "exactly one"):
            list(stream_rows(path))

    def test_gzip_round_trip(self):
        path = self.root / "sample.gz"
        with gzip.open(path, "wt", encoding="utf-8") as output:
            output.write(HEADER + VALID)
        records = list(stream_rows(path))
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["MMSI"], "367800001")

    def test_reject_headerless_and_extra_columns(self):
        raw = self.write("bad.csv", "")
        with self.assertRaisesRegex(AISInputError, "empty"):
            list(stream_rows(raw))
        raw = self.write("extra.csv", HEADER + VALID.rstrip("\n") + ",EXTRA\n")
        with self.assertRaisesRegex(AISInputError, "more values"):
            list(stream_rows(raw))

    def test_no_clobber_same_input_output_and_reject_negative_row_count(self):
        raw = self.write("input.csv", HEADER + VALID)
        with self.assertRaisesRegex(AISInputError, "different"):
            ingest(raw, raw)
        with self.assertRaisesRegex(AISInputError, "negative"):
            ingest(raw, self.root / "other.csv", max_rows=-1)
        self.assertEqual(raw.read_text(), HEADER + VALID)

    def test_reject_invalid_bbox(self):
        raw = self.write("input.csv", HEADER + VALID)
        with self.assertRaisesRegex(AISInputError, "ordered"):
            ingest(raw, self.root / "out.csv", bbox=(0, 0, -1, 1))


if __name__ == "__main__":
    unittest.main()
