"""USACE point-catalog JSON Schema conformance; synthetic ArcGIS response only."""
import io
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from harborlens.usace import save_catalog

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas" / "v1"

class Response(io.BytesIO):
    def __init__(self, payload):
        raw = json.dumps(payload).encode("utf-8")
        super().__init__(raw)
        self.headers = {"Content-Length": str(len(raw))}

class USACESchemaTests(unittest.TestCase):
    def test_geojson_point_and_provenance_contracts(self):
        response = {
            "features": [
                {
                    "attributes": {
                        "OBJECTID": 121, "NAV_UNIT_ID": "TX-121",
                        "NAV_UNIT_NAME": "Synthetic Dock",
                        "FAC_TYPE": "DOCK", "PORT_NAME": "HOUSTON",
                        "WTWY_NAME": "HOUSTON SHIP CHANNEL",
                        "DATA_RECORD_STATUS": "ACTIVE",
                    },
                    "geometry": {"x": -95.1, "y": 29.75},
                }
            ],
            "exceededTransferLimit": False,
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "facilities.geojson"
            saved = save_catalog(path, opener=lambda req, timeout: Response(response))
            actual = json.loads(path.read_text(encoding="utf-8"))
            geo_schema = json.loads((SCHEMAS / "usace-facility-collection.schema.json").read_text())
            meta_schema = json.loads((SCHEMAS / "usace-facility-source.schema.json").read_text())
            for schema in (geo_schema, meta_schema):
                Draft202012Validator.check_schema(schema)
            Draft202012Validator(geo_schema, format_checker=FormatChecker()).validate(actual)
            Draft202012Validator(meta_schema, format_checker=FormatChecker()).validate(saved)
            self.assertEqual(actual["features"][0]["geometry"]["type"], "Point")
            self.assertEqual(saved["license_status"], "review_required")

if __name__ == "__main__":
    unittest.main()
