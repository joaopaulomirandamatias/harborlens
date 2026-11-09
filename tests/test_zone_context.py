"""Centroid overlay tests: spatial context ONLY, not operational classification."""
import json
import tempfile
import unittest
from pathlib import Path

from harborlens.zone_context import spatial_context, ZoneContextError

OUTER=[[-95.2,29.7],[-95.0,29.7],[-95.0,29.8],[-95.2,29.8],[-95.2,29.7]]
HOLE=[[-95.13,29.73],[-95.07,29.73],[-95.07,29.77],[-95.13,29.77],[-95.13,29.73]]

def polygon(oid,coordinates=None):
    return {"type":"Feature","id":str(oid),"geometry":{"type":"Polygon","coordinates":coordinates or [OUTER]},
            "properties":{"geometry_review_status":"unreviewed","historical_validity":"not_verified"}}

def candidate(x=-95.1,y=29.75,label="unvalidated"):
    return {"type":"Feature","geometry":{"type":"Point","coordinates":[x,y]},
            "properties":{"event_id":"fixture","confidence_label":label,"type":"stationary_candidate"}}

class ZoneContextTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.candidates=self.root/"candidates.geojson"
        self.zones=self.root/"zones.geojson"
        self.out=self.root/"out.geojson"
    def tearDown(self):
        self.tmp.cleanup()
    def prepare(self,features,polygons):
        self.candidates.write_text(json.dumps({"type":"FeatureCollection","features":features}))
        self.zones.write_text(json.dumps({"type":"FeatureCollection","features":polygons}))
    def output(self):
        return json.loads(self.out.read_text())["features"]

    def test_single_match_is_explicitly_unverified(self):
        self.prepare([candidate()],[polygon(101)])
        result=spatial_context(self.candidates,self.zones,self.out)
        self.assertEqual(result["counts"]["one_overlap"],1)
        context=self.output()[0]["properties"]["zone_context"]
        self.assertEqual(context["status"],"possible_spatial_overlap")
        self.assertEqual(context["historical_validity"],"not_verified")
        self.assertEqual(self.output()[0]["properties"]["confidence_label"],"unvalidated")
        self.assertEqual(context["source_feature_ids"],["101"])
        self.assertTrue((self.root/"out.geojson.source.json").exists())

    def test_overlapping_polygons_remain_ambiguous(self):
        self.prepare([candidate()],[polygon(101),polygon(102)])
        result=spatial_context(self.candidates,self.zones,self.out)
        self.assertEqual(result["counts"]["multiple_overlaps"],1)
        self.assertEqual(self.output()[0]["properties"]["zone_context"]["status"],"ambiguous_multiple_polygons")

    def test_polygon_hole_does_not_match_candidate(self):
        self.prepare([candidate()],[polygon(101,[OUTER,HOLE])])
        result=spatial_context(self.candidates,self.zones,self.out)
        self.assertEqual(result["counts"]["no_overlap"],1)
        self.assertEqual(self.output()[0]["properties"]["zone_context"]["status"],"no_polygon_overlap_observed")

    def test_boundary_included_but_unverified(self):
        self.prepare([candidate(x=-95.2,y=29.75)],[polygon(101)])
        result=spatial_context(self.candidates,self.zones,self.out)
        self.assertEqual(result["counts"]["one_overlap"],1)
        self.assertEqual(self.output()[0]["properties"]["zone_context"]["historical_validity"],"not_verified")

    def test_reject_point_instead_of_polygon_catalog(self):
        point={"type":"Feature","id":"1","geometry":{"type":"Point","coordinates":[-95.1,29.75]},"properties":{}}
        self.prepare([candidate()],[point])
        with self.assertRaisesRegex(ZoneContextError,"Polygon/MultiPolygon"):
            spatial_context(self.candidates,self.zones,self.out)
        self.assertFalse(self.out.exists())

    def test_reject_claim_of_verified_event(self):
        self.prepare([candidate(label="verified")],[polygon(101)])
        with self.assertRaisesRegex(ZoneContextError,"explicitly unvalidated"):
            spatial_context(self.candidates,self.zones,self.out)

    def test_prevent_overwrite(self):
        self.prepare([candidate()],[polygon(101)])
        spatial_context(self.candidates,self.zones,self.out)
        with self.assertRaises(FileExistsError):
            spatial_context(self.candidates,self.zones,self.out)

if __name__=="__main__":
    unittest.main()
