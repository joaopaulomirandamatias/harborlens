"""No external services are contacted by these USACE feature-adapter tests."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from harborlens.usace import FacilityDataError, collect, query_url, save_catalog

def row(i, lon=-95.10, lat=29.75, kind="DOCK"):
    return {"attributes": {
        "OBJECTID": i, "NAV_UNIT_ID": f"N-{i}", "NAV_UNIT_NAME": f"Demo Facility {i}",
        "FAC_TYPE": kind, "PORT_NAME": "HOUSTON",
        "WTWY_NAME": "HOUSTON SHIP CHANNEL", "DATA_RECORD_STATUS": "ACTIVE",
    }, "geometry": {"x": lon, "y": lat}}

class MockResponse(io.BytesIO):
    def __init__(self, payload):
        content = json.dumps(payload).encode()
        super().__init__(content)
        self.headers = {"Content-Length": str(len(content))}

def mock_pages(pages):
    def opener(req, timeout):
        offset = int(parse_qs(urlparse(req.full_url).query)["resultOffset"][0])
        return MockResponse(pages[offset])
    return opener

class USACEFacilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "facilities.geojson"

    def tearDown(self):
        self.tmp.cleanup()

    def test_fixed_host_and_envelope(self):
        url = query_url(page_size=2)
        params = parse_qs(urlparse(url).query)
        self.assertTrue(url.startswith("https://services7.arcgis.com/"))
        self.assertEqual(params["geometryType"], ["esriGeometryEnvelope"])
        self.assertEqual(params["outSR"], ["4326"])
        self.assertEqual(params["returnGeometry"], ["true"])
        self.assertEqual(params["outFields"][0].split(",")[0], "OBJECTID")

    def test_two_pages_and_point_labels_only(self):
        first = {"features": [row(1), row(2)], "exceededTransferLimit": True}
        second = {"features": [row(3)], "exceededTransferLimit": False}
        data, urls = collect(page_size=2, opener=mock_pages({0:first,2:second}))
        self.assertEqual(len(data["features"]), 3)
        self.assertEqual(len(urls), 2)
        self.assertTrue(all(f["geometry"]["type"] == "Point" for f in data["features"]))
        self.assertTrue(all(f["properties"]["event_verification"] == "not_verified" for f in data["features"]))
        self.assertEqual(data["features"][0]["properties"]["facility_status"], "reference_point_only")

    def test_export_provenance_and_no_overwrite(self):
        one = {"features": [row(8)], "exceededTransferLimit": False}
        summary = save_catalog(self.out, opener=mock_pages({0:one}))
        self.assertEqual(summary["feature_count"], 1)
        self.assertEqual(summary["geometric_type"], "Point")
        self.assertEqual(summary["license_status"], "review_required")
        self.assertEqual(json.loads(self.out.read_text())["features"][0]["id"], "8")
        self.assertTrue((self.out.parent / "facilities.geojson.source.json").is_file())
        with self.assertRaises(FileExistsError):
            save_catalog(self.out, opener=mock_pages({0:one}))

    def test_reject_polygon_as_facility_point(self):
        data = {"features":[{"attributes":row(3)["attributes"],
                 "geometry":{"rings":[[[0,0],[1,0],[0,1],[0,0]]]}}]}
        with self.assertRaisesRegex(FacilityDataError,"POINT"):
            collect(opener=mock_pages({0:data}))

    def test_reject_truncated_pagination(self):
        pages={0:{"features":[row(1),row(2)],"exceededTransferLimit":True}}
        with self.assertRaisesRegex(FacilityDataError,"cap"):
            collect(page_size=2,max_features=2,opener=mock_pages(pages))

    def test_reject_duplicate_identifier_across_pages(self):
        first={"features":[row(1),row(2)],"exceededTransferLimit":True}
        second={"features":[row(2)],"exceededTransferLimit":False}
        with self.assertRaisesRegex(FacilityDataError,"Repeated OBJECTID"):
            collect(page_size=2,opener=mock_pages({0:first,2:second}))

    def test_invalid_geometry_empty_and_bad_bbox(self):
        with self.assertRaisesRegex(FacilityDataError,"No facility points"):
            collect(opener=mock_pages({0:{"features":[]}}))
        with self.assertRaises(FacilityDataError):
            query_url(bbox=(0,0,-1,1))
        with self.assertRaises(FacilityDataError):
            query_url(bbox=(float("nan"),0,1,1))
        with self.assertRaises(FacilityDataError):
            query_url(page_size=2001)

    def test_error_response_and_invalid_json(self):
        with self.assertRaisesRegex(FacilityDataError,"error response"):
            collect(opener=mock_pages({0:{"error":{"message":"bad request"}}}))
        with self.assertRaises(FacilityDataError):
            collect(opener=lambda request, timeout: io.BytesIO(b"<html>blocked</html>"))

    def test_bbox_filter_has_no_claim_of_absence(self):
        outside={"features":[row(1,lon=-80.0,lat=29.75)]}
        with self.assertRaisesRegex(FacilityDataError,"No facility points"):
            collect(opener=mock_pages({0:outside}))

if __name__ == "__main__":
    unittest.main()
