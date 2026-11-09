"""Synthetic-only NOAA anchorage polygon acquisition tests."""
import io
import json
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from harborlens.noaa_anchorages import (
    PolygonSourceError, collect, list_ids_url, save_polygons
)

SQUARE = [[[-95.2,29.7],[-95.0,29.7],[-95.0,29.8],[-95.2,29.8],[-95.2,29.7]]]

def feature(i, geometry=None):
    return {
        "type":"Feature","id":i,
        "geometry":geometry or {"type":"Polygon","coordinates":SQUARE},
        "properties":{"OBJECTID":i,"name":"Synthetic Anchorage"}
    }

class Response(io.BytesIO):
    def __init__(self, data):
        payload=json.dumps(data).encode("utf-8")
        super().__init__(payload)
        self.headers={"Content-Length":str(len(payload))}

def mocked(source_ids=(101,), features=None):
    """Simulated fixed NOAA MapServer; never performs real network calls."""
    if features is None:
        features=[feature(i) for i in source_ids]
    def open_url(request, timeout):
        params=parse_qs(urlparse(request.full_url).query)
        if "returnIdsOnly" in params:
            return Response({"objectIds":list(source_ids),"objectIdFieldName":"OBJECTID"})
        return Response({"type":"FeatureCollection","features":features})
    return open_url

class NOAAAnchorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.output=Path(self.temp.name)/"anchorages.geojson"
    def tearDown(self):
        self.temp.cleanup()

    def test_request_is_fixed_noaa_layer(self):
        self.assertIn("maps.coast.noaa.gov",list_ids_url())
        self.assertIn("returnIdsOnly=true",list_ids_url())

    def test_collect_and_source_provenance(self):
        data,urls=collect(opener=mocked())
        self.assertEqual(len(data["features"]),1)
        self.assertEqual(data["features"][0]["geometry"]["type"],"Polygon")
        self.assertEqual(data["features"][0]["properties"]["historical_validity"],"not_verified")
        self.assertEqual(len(urls),2)
        meta=save_polygons(self.output,opener=mocked())
        self.assertEqual(meta["feature_count"],1)
        self.assertEqual(meta["rights_status"],"review_required")
        self.assertTrue(self.output.with_name("anchorages.geojson.source.json").exists())
        with self.assertRaises(FileExistsError):
            save_polygons(self.output,opener=mocked())

    def test_refuse_oversized_source_feature_count(self):
        with self.assertRaisesRegex(PolygonSourceError,"exceeds limit"):
            collect(max_features=1,opener=mocked(source_ids=(101,102)))

    def test_refuse_point_in_polygon_layer(self):
        item=feature(101,{"type":"Point","coordinates":[-95.1,29.75]})
        with self.assertRaisesRegex(PolygonSourceError,"non-polygon"):
            collect(opener=mocked(features=[item]))

    def test_refuse_self_intersecting_polygon(self):
        bowtie=[[[-95.2,29.7],[-95.0,29.8],[-95.2,29.8],[-95.0,29.7],[-95.2,29.7]]]
        with self.assertRaisesRegex(PolygonSourceError,"invalid or degenerate"):
            collect(opener=mocked(features=[feature(101,{"type":"Polygon","coordinates":bowtie})]))

    def test_duplicate_source_ids_rejected(self):
        with self.assertRaisesRegex(PolygonSourceError,"duplicate source object IDs"):
            collect(opener=mocked(source_ids=(101,101)))

    def test_empty_and_bad_source_response(self):
        with self.assertRaisesRegex(PolygonSourceError,"No polygons"):
            collect(opener=mocked(source_ids=()))
        with self.assertRaisesRegex(PolygonSourceError,"error response"):
            collect(opener=lambda req,timeout:Response({"error":{"message":"down"}}))

if __name__=="__main__":
    unittest.main()
