"""Offline synthetic observed-track-vs-polygon tests; NOT ground truth."""
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from harborlens.track_context import TrackEvidenceError, run_track_context

BASE=datetime(2024,1,2,23,40,tzinfo=timezone.utc)
MMSI="367800001"
OUTER=[[-95.2,29.7],[-95.0,29.7],[-95.0,29.8],[-95.2,29.8],[-95.2,29.7]]
HOLE=[[-95.13,29.73],[-95.07,29.73],[-95.07,29.77],[-95.13,29.77],[-95.13,29.73]]


def polygon(oid, rings=None):
    return {
        "type":"Feature","id":str(oid),
        "geometry":{"type":"Polygon","coordinates":rings or [OUTER]},
        "properties":{
            "historical_validity":"not_verified",
            "geometry_review_status":"unreviewed",
            "source_layer":"NOAA Designated Anchorage Areas",
        },
    }


class TrackEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.cleaned=root/"houston_clean.csv"
        self.candidates=root/"stationary_candidates.geojson"
        self.polygons=root/"anchorages.geojson"
        self.receipt=root/"anchorages.geojson.source.json"
        self.out=root/"track-context.geojson"

    def tearDown(self):
        self.tmp.cleanup()

    def prepare(self,lons=None, expected=10, step=5, zones=None, effective=None):
        lons=lons if lons is not None else [-95.16]*10
        with self.cleaned.open("w",encoding="utf-8",newline="") as f:
            writer=csv.writer(f)
            writer.writerow(["mmsi","timestamp_utc","lat","lon","sog_knots","vessel_type","nav_status"])
            for i,lon in enumerate(lons):
                stamp=(BASE+timedelta(minutes=i*step)).isoformat().replace("+00:00","Z")
                writer.writerow([MMSI,stamp,29.75,lon,0.2,70,5])
        last=(BASE+timedelta(minutes=(len(lons)-1)*step)).isoformat().replace("+00:00","Z")
        start=BASE.isoformat().replace("+00:00","Z")
        self.candidates.write_text(json.dumps({
            "type":"FeatureCollection","features":[{
                "type":"Feature",
                "geometry":{"type":"Point","coordinates":[sum(lons)/len(lons),29.75]},
                "properties":{"event_id":"event-test-001","mmsi":MMSI,
                              "start_utc":start,"end_utc":last,
                              "point_count":expected,"type":"stationary_candidate",
                              "confidence_label":"unvalidated"}
            }]
        }),encoding="utf-8")
        self.polygons.write_text(json.dumps({
            "type":"FeatureCollection","features":zones if zones is not None else [polygon(1)]
        }),encoding="utf-8")
        receipt={"output_sha256":hashlib.sha256(self.polygons.read_bytes()).hexdigest(),
                 "historical_validity":"not_verified","geometry_review_status":"unreviewed",
                 "rights_status":"review_required","retrieved_at_utc":"2026-11-09T07:00:00Z"}
        if effective is not None:
            receipt["effective_from_utc"],receipt["effective_to_utc"]=effective
        self.receipt.write_text(json.dumps(receipt),encoding="utf-8")

    def inspect(self):
        result=run_track_context(self.cleaned,self.candidates,self.polygons,self.out)
        data=json.loads(self.out.read_text())
        evidence=data["features"][0]["properties"]["full_track_zone_evidence"]
        self.assertEqual(result["candidate_count"],1)
        self.assertEqual(result["output_sha256"],hashlib.sha256(self.out.read_bytes()).hexdigest())
        self.assertEqual(evidence["operational_event_validation"],"not_verified")
        self.assertEqual(evidence["source_rights"],"review_required")
        self.assertEqual(data["features"][0]["properties"]["confidence_label"],"unvalidated")
        return evidence

    def test_all_ten_observations_in_one_polygon_even_across_midnight(self):
        self.prepare()
        result=self.inspect()
        self.assertEqual(result["status"],"all_observed_points_within_one_polygon")
        self.assertEqual(result["observed_points"],10)
        self.assertEqual(result["polygon_point_hits"],{"1":10})
        self.assertEqual(result["temporal_compatibility"],"historical_validity_not_established")

    def test_centroid_inside_does_not_imply_complete_trajectory_inside(self):
        # Five points are inside the area; five are outside. Centroid remains inside.
        self.prepare(lons=[-95.16]*5+[-94.99]*5)
        evidence=self.inspect()
        self.assertEqual(evidence["status"],"partial_observed_point_overlap")
        self.assertEqual(evidence["polygon_point_hits"],{"1":5})

    def test_mismatched_point_count_returns_unknown_not_full_overlap(self):
        self.prepare(expected=11)
        evidence=self.inspect()
        self.assertEqual(evidence["status"],"incomplete_track_unknown")
        self.assertFalse(evidence["observation_count_matches"])

    def test_sampling_gap_above_15_min_returns_unknown(self):
        self.prepare(step=16)
        evidence=self.inspect()
        self.assertEqual(evidence["status"],"incomplete_track_unknown")
        self.assertGreater(evidence["max_observed_gap_minutes"],15)

    def test_overlap_with_two_polygons_is_ambiguous(self):
        self.prepare(zones=[polygon(1),polygon(2)])
        evidence=self.inspect()
        self.assertEqual(evidence["status"],"multiple_zone_evidence_ambiguous")
        self.assertEqual(evidence["points_in_multiple_polygons"],10)

    def test_polygon_hole_not_treated_as_inside(self):
        self.prepare(lons=[-95.10]*10,zones=[polygon(1,[OUTER,HOLE])])
        evidence=self.inspect()
        self.assertEqual(evidence["status"],"no_observed_point_overlap")
        self.assertEqual(evidence["polygon_point_hits"],{})

    def test_boundary_is_counted_as_observed_overlap(self):
        self.prepare(lons=[-95.20]*10)
        evidence=self.inspect()
        self.assertEqual(evidence["status"],"all_observed_points_within_one_polygon")

    def test_temporally_outside_user_declared_vintage_stays_unknown(self):
        self.prepare(effective=("2025-01-01T00:00:00Z","2027-01-01T00:00:00Z"))
        evidence=self.inspect()
        self.assertEqual(evidence["temporal_compatibility"],"outside_declared_vintage")
        self.assertEqual(evidence["status"],"outside_declared_vintage_unknown")

    def test_inside_declared_vintage_never_becomes_verified(self):
        self.prepare(effective=("2020-01-01T00:00:00Z","2030-01-01T00:00:00Z"))
        evidence=self.inspect()
        self.assertEqual(evidence["temporal_compatibility"],"inside_unreviewed_declared_vintage")
        self.assertEqual(evidence["operational_event_validation"],"not_verified")

    def test_source_receipt_hash_mismatch_refused(self):
        self.prepare()
        receipt=json.loads(self.receipt.read_text())
        receipt["output_sha256"]="0"*64
        self.receipt.write_text(json.dumps(receipt))
        with self.assertRaisesRegex(TrackEvidenceError,"SHA-256 mismatch"):
            run_track_context(self.cleaned,self.candidates,self.polygons,self.out)
        self.assertFalse(self.out.exists())

    def test_usace_reference_point_refused_as_geofence(self):
        self.prepare(zones=[{"type":"Feature","id":"x","geometry":{
            "type":"Point","coordinates":[-95.16,29.75]
        },"properties":{"historical_validity":"not_verified"}}])
        self.receipt.write_text(json.dumps({
            **json.loads(self.receipt.read_text()),
            "output_sha256":hashlib.sha256(self.polygons.read_bytes()).hexdigest()
        }))
        with self.assertRaisesRegex(TrackEvidenceError,"NOT polygon zones"):
            run_track_context(self.cleaned,self.candidates,self.polygons,self.out)

    def test_do_not_overwrite_outputs_or_original_inputs(self):
        self.prepare()
        old=(self.cleaned.read_bytes(),self.candidates.read_bytes(),self.polygons.read_bytes())
        self.inspect()
        with self.assertRaisesRegex(TrackEvidenceError,"overwrite"):
            run_track_context(self.cleaned,self.candidates,self.polygons,self.out)
        self.assertEqual(old,(self.cleaned.read_bytes(),self.candidates.read_bytes(),self.polygons.read_bytes()))

if __name__=="__main__":
    unittest.main()
