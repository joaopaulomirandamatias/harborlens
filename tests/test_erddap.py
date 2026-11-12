"""No network is used: all NOAA response samples are synthetic."""
import io
import tempfile
import unittest
from pathlib import Path
from urllib.parse import unquote
from harborlens.erddap import AcquisitionError, build_url, fetch_subset
from harborlens.ais import run

START = "2024-06-10T00:00:00Z"
END = "2024-06-10T01:00:00Z"
BBOX = (-95.7, 29.1, -94.2, 30.1)
HEADER = "MMSI,time,Lat,Lon,SOG,VesselType,Status\n"
UNITS = ",UTC,degrees_north,degrees_east,knots,,\n"
RECORDS = (
    "199080001,2024-06-10T00:00:00Z,29.73,-95.16,0.1,70,5\n"
    "199080001,2024-06-10T00:01:00Z,29.73,-95.16,0.2,70,5\n"
)


class FakeResponse(io.BytesIO):
    def __init__(self, body):
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}


def opener(body):
    return lambda request, timeout: FakeResponse(body)


class ERDDAPTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "houston.csv"

    def tearDown(self):
        self.temp.cleanup()

    def test_fixed_official_host_and_constraints(self):
        url = unquote(build_url(START, END, BBOX))
        self.assertTrue(url.startswith("https://data.pmel.noaa.gov/pmel/erddap/tabledap/AIS2024_AIS.csv?"))
        self.assertIn("&time>=2024-06-10T00:00:00Z", url)
        self.assertIn("&Lon<=-94.2", url)

    def test_invalid_time_and_bounds(self):
        with self.assertRaises(AcquisitionError):
            build_url("2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z")
        with self.assertRaises(AcquisitionError):
            build_url("2025-01-01T00:00:00Z", "2025-01-01T00:15:00Z")
        with self.assertRaises(AcquisitionError):
            build_url(START, END, (0, 0, -1, 1))

    def test_strip_erddap_units_and_pipeline_compatibility(self):
        report = fetch_subset(START, END, BBOX, self.path, opener=opener((HEADER + UNITS + RECORDS).encode()))
        self.assertEqual(report["rows"], 2)
        self.assertEqual(report["rights_status"], "review_required")
        self.assertEqual(len(self.path.read_text().splitlines()), 3)
        self.assertTrue((self.path.parent / "houston.csv.source.json").exists())
        result = run(self.path, self.path.parent / "analysis", source_url=report["source_url"])
        self.assertEqual(result["counts"]["written"], 2)
        self.assertEqual(result["events"]["stationary_candidates"], 0)

    def test_refuse_existing_path(self):
        fetch_subset(START, END, BBOX, self.path, opener=opener((HEADER + UNITS + RECORDS).encode()))
        with self.assertRaises(FileExistsError):
            fetch_subset(START, END, BBOX, self.path, opener=opener((HEADER + UNITS + RECORDS).encode()))

    def test_html_and_empty_subset_are_errors(self):
        with self.assertRaises(AcquisitionError):
            fetch_subset(START, END, BBOX, self.path, opener=opener(b"<html>error</html>"))
        self.assertFalse(self.path.exists())
        with self.assertRaisesRegex(AcquisitionError, "no observations"):
            fetch_subset(START, END, BBOX, self.path, opener=opener((HEADER + UNITS).encode()))
        self.assertFalse(self.path.exists())

    def test_download_size_limit(self):
        big = (HEADER + UNITS + RECORDS).encode() + b"x" * (1048576 + 1)
        with self.assertRaisesRegex(AcquisitionError, "cap"):
            fetch_subset(START, END, BBOX, self.path, max_mib=1, opener=opener(big))
        self.assertFalse(self.path.exists())

    def test_bad_csv_shape_and_missing_rights_approval(self):
        with self.assertRaisesRegex(AcquisitionError, "column"):
            fetch_subset(START, END, BBOX, self.path, opener=opener((HEADER + UNITS + "123,123\n").encode()))
        self.assertFalse(self.path.exists())
        self.assertNotIn("approved", str(build_url(START, END)))

if __name__ == "__main__":
    unittest.main()
