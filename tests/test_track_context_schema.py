"""JSON Schema contract checks for source-pinned unverified track evidence."""
import csv
import hashlib
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from harborlens.track_context import run_track_context

ROOT=Path(__file__).resolve().parents[1]
SCHEMAS=ROOT/"schemas"/"v1"
START=datetime(2024,1,2,23,40,tzinfo=timezone.utc)

class TrackContextSchemaTests(unittest.TestCase):
    def test_annotated_feature_and_receipt_conform_to_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            csv_path=root/"cleaned.csv"
            candidates=root/"stationary_candidates.geojson"
            polygons=root/"zones.geojson"
            with csv_path.open("w",newline="",encoding="utf-8") as handle:
                writer=csv.writer(handle)
                writer.writerow(["mmsi","timestamp_utc","lat","lon","sog_knots"])
                for minute in range(0,50,5):
                    t=(START+timedelta(minutes=minute)).isoformat().replace("+00:00","Z")
                    writer.writerow(["367800001",t,29.75,-95.16,0.2])
            start=START.isoformat().replace("+00:00","Z")
            end=(START+timedelta(minutes=45)).isoformat().replace("+00:00","Z")
            candidates.write_text(json.dumps({"type":"FeatureCollection","features":[{
                "type":"Feature","geometry":{"type":"Point","coordinates":[-95.16,29.75]},
                "properties":{"event_id":"abcd12345","mmsi":"367800001",
                              "start_utc":start,"end_utc":end,"point_count":10,
                              "type":"stationary_candidate","confidence_label":"unvalidated"}
            }]}))
            outer=[[-95.2,29.7],[-95.0,29.7],[-95.0,29.8],[-95.2,29.8],[-95.2,29.7]]
            polygons.write_text(json.dumps({"type":"FeatureCollection","features":[{
                "type":"Feature","id":"1","geometry":{"type":"Polygon","coordinates":[outer]},
                "properties":{"historical_validity":"not_verified"}
            }]}))
            metadata={"output_sha256":hashlib.sha256(polygons.read_bytes()).hexdigest(),
                      "historical_validity":"not_verified","geometry_review_status":"unreviewed",
                      "rights_status":"review_required",
                      "retrieved_at_utc":"2026-11-09T00:00:00Z"}
            Path(str(polygons)+".source.json").write_text(json.dumps(metadata))
            output=root/"context.geojson"
            receipt=run_track_context(csv_path,candidates,polygons,output)
            data=json.loads(output.read_text())
            evidence=data["features"][0]["properties"]["full_track_zone_evidence"]
            evid_schema=json.loads((SCHEMAS/"track-zone-evidence.schema.json").read_text())
            receipt_schema=json.loads((SCHEMAS/"track-zone-context-receipt.schema.json").read_text())
            for schema in (evid_schema,receipt_schema):
                Draft202012Validator.check_schema(schema)
            Draft202012Validator(evid_schema,format_checker=FormatChecker()).validate(evidence)
            Draft202012Validator(receipt_schema,format_checker=FormatChecker()).validate(receipt)
            self.assertEqual(evidence["operational_event_validation"],"not_verified")

if __name__=="__main__":
    unittest.main()
