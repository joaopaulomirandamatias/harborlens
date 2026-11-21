"""SPEC-003: synthetic-only source-rights receipts on all four adapters."""
import hashlib
import io
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import zstandard
from jsonschema import Draft202012Validator

from harborlens.archive_extract import extract_archive
from harborlens.erddap import fetch_subset
from harborlens.noaa_anchorages import save_polygons
from harborlens.rights import rights_receipt
from harborlens.usace import save_catalog


ROOT = Path(__file__).resolve().parents[1]
HEADER = "MMSI,time,Lat,Lon,SOG,VesselType,Status\n"
UNITS = ",UTC,degrees_north,degrees_east,knots,,\n"
RECORD = "199080001,2024-06-10T00:00:00Z,29.73,-95.16,0.1,70,5\n"


class FakeResponse(io.BytesIO):
    def __init__(self, body):
        if not isinstance(body, bytes):
            body = json.dumps(body).encode("utf-8")
        super().__init__(body)
        self.headers = {"Content-Length": str(len(body))}


def erddap_mock(req, timeout):
    return FakeResponse((HEADER + UNITS + RECORD).encode())


def usace_mock(req, timeout):
    return FakeResponse({
        "features": [{
            "attributes": {"OBJECTID": 3, "NAV_UNIT_NAME": "Synthetic"},
            "geometry": {"x": -95.10, "y": 29.75}
        }],
        "exceededTransferLimit": False
    })


def noaa_polygon_mock(req, timeout):
    params = parse_qs(urlparse(req.full_url).query)
    if params.get("returnIdsOnly"):
        return FakeResponse({"objectIds": [5], "objectIdFieldName": "OBJECTID"})
    ring = [[-95.2, 29.7], [-95.0, 29.7], [-95.0, 29.8],
            [-95.2, 29.8], [-95.2, 29.7]]
    return FakeResponse({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "id": 5,
            "properties": {"OBJECTID": 5, "name": "Synthetic only"},
            "geometry": {"type": "Polygon", "coordinates": [ring]}
        }]
    })


class RightsAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.register = self.root / "review.json"
        self.receipt_schema = json.loads(
            (ROOT / "schemas/v1/source-rights-receipt.schema.json").read_text()
        )
        self.erddap_schema = json.loads(
            (ROOT / "schemas/v1/erddap-ais-source.schema.json").read_text()
        )
        self.archive_schema = json.loads(
            (ROOT / "schemas/v1/noaa-archive-extract-source.schema.json").read_text()
        )

    def tearDown(self):
        self.tmp.cleanup()

    def reviewed(self, source_id, dataset_version, *, commercial="prohibited"):
        base = json.loads((ROOT / "docs/data/rights-register.json").read_text())
        item = deepcopy(next(s for s in base["sources"] if s["source_id"] == source_id))
        item.update({
            "dataset_version": dataset_version,
            "decision": "reviewed",
            "rights_status": "reviewed_public_domain_attribution_required",
            "reviewed_by": "Synthetic example reviewer",
            "reviewed_at_utc": "2026-11-09T00:00:00Z",
            "terms_url": "https://example.test/terms",
            "terms_sha256": "a" * 64,
            "evidence_url": "https://example.test/review",
            "attribution": "Synthetic dataset attribution",
            "permitted_uses": {
                "research": "allowed",
                "public_aggregates": "unreviewed",
                "commercial": commercial
            },
        })
        self.register.write_text(json.dumps({"schema_version": 1, "sources": [item]}))
        return hashlib.sha256(self.register.read_bytes()).hexdigest()

    def assert_receipt(self, sidecar, *, status, source_id, version):
        receipt = sidecar["rights_review"]
        Draft202012Validator(self.receipt_schema).validate(receipt)
        self.assertEqual(receipt["source_id"], source_id)
        self.assertEqual(receipt["dataset_version"], version)
        self.assertEqual(receipt["rights_status"], status)
        self.assertEqual(sidecar.get("rights_status", sidecar.get("license_status")), status)

    def test_no_registry_preserves_pending(self):
        r = rights_receipt("noaa_pmel_erddap", dataset_version="AIS2024_AIS")
        self.assertEqual(r["evaluation"], "not_supplied")
        self.assertIsNone(r["registry_sha256"])
        self.assertEqual(r["rights_status"], "review_required")
        Draft202012Validator(self.receipt_schema).validate(r)

    def test_erddap_reviewed_restricted_and_invalid_registry(self):
        sha = self.reviewed("noaa_pmel_erddap", "AIS2024_AIS")
        one = fetch_subset("2024-06-10T00:00:00Z", "2024-06-10T01:00:00Z",
                           (-95.7, 29.1, -94.2, 30.1), self.root / "one.csv",
                           opener=erddap_mock, rights_register=self.register)
        self.assert_receipt(one, status="reviewed_public_domain_attribution_required",
                            source_id="noaa_pmel_erddap", version="AIS2024_AIS")
        self.assertEqual(one["rights_review"]["registry_sha256"], sha)
        self.assertEqual(one["rights_review"]["evaluation"], "reviewed_record")
        other = fetch_subset("2024-06-10T00:00:00Z", "2024-06-10T01:00:00Z",
                             (-95.7, 29.1, -94.2, 30.1), self.root / "two.csv",
                             opener=erddap_mock, rights_register=self.register,
                             rights_purpose="commercial")
        self.assertEqual(other["rights_status"], "use_restricted")
        self.register.write_text("{ broken")
        third = fetch_subset("2024-06-10T00:00:00Z", "2024-06-10T01:00:00Z",
                             (-95.7, 29.1, -94.2, 30.1), self.root / "three.csv",
                             opener=erddap_mock, rights_register=self.register)
        self.assert_receipt(third, status="review_required",
                            source_id="noaa_pmel_erddap", version="AIS2024_AIS")
        self.assertEqual(third["rights_review"]["evaluation"], "invalid_registry")

    def test_usace_snapshot_is_version_pinned(self):
        before = save_catalog(self.root / "one.geojson", opener=usace_mock)
        version = "output-sha256:" + before["output_sha256"]
        self.reviewed("usace_ntad_navigation_facilities", version)
        after = save_catalog(self.root / "two.geojson", opener=usace_mock,
                             rights_register=self.register)
        self.assert_receipt(after, status="reviewed_public_domain_attribution_required",
                            source_id="usace_ntad_navigation_facilities", version=version)
        schema = json.loads(
            (ROOT / "schemas/v1/usace-facility-source.schema.json").read_text()
        )
        Draft202012Validator(schema).validate(after)
        self.reviewed("usace_ntad_navigation_facilities", "2026-09-30")
        mismatch = save_catalog(self.root / "three.geojson", opener=usace_mock,
                                rights_register=self.register)
        self.assertEqual(mismatch["license_status"], "review_required")
        self.assertEqual(mismatch["rights_review"]["evaluation"], "pending_or_unmatched")

    def test_noaa_geometry_current_is_not_historically_verified(self):
        before = save_polygons(self.root / "before.geojson", opener=noaa_polygon_mock)
        version = "output-sha256:" + before["output_sha256"]
        self.reviewed("noaa_oceanreports_anchorages", version)
        after = save_polygons(self.root / "after.geojson", opener=noaa_polygon_mock,
                              rights_register=self.register)
        self.assert_receipt(after, status="reviewed_public_domain_attribution_required",
                            source_id="noaa_oceanreports_anchorages", version=version)
        self.assertEqual(after["historical_validity"], "not_verified")
        self.assertEqual(after["geometry_review_status"], "unreviewed")
        schema = json.loads(
            (ROOT / "schemas/v1/noaa-anchorage-source.schema.json").read_text()
        )
        Draft202012Validator(schema).validate(after)

    def test_local_archive_requires_matching_input_hash(self):
        fixture = ROOT / "tests/fixtures/synthetic_ais.csv"
        archive = self.root / "ais-2024-01-02.csv.zst"
        archive.write_bytes(zstandard.ZstdCompressor().compress(fixture.read_bytes()))
        version = "2024/archive-sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
        self.reviewed("noaa_ocm_ais_daily", version)
        report = extract_archive(archive, self.root / "one.csv",
                                 "2024-01-02T00:00:00Z", "2024-01-02T00:59:00Z",
                                 rights_register=self.register)
        self.assert_receipt(report, status="reviewed_public_domain_attribution_required",
                            source_id="noaa_ocm_ais_daily", version=version)
        self.assertEqual(report["input_sha256"], version.split(":")[-1])
        self.reviewed("noaa_ocm_ais_daily", "2024")
        mismatch = extract_archive(archive, self.root / "two.csv",
                                   "2024-01-02T00:00:00Z", "2024-01-02T00:59:00Z",
                                   rights_register=self.register)
        self.assertEqual(mismatch["rights_status"], "review_required")

    def writer_sidecars(self, tag):
        erddap = fetch_subset(
            "2024-06-10T00:00:00Z", "2024-06-10T01:00:00Z",
            (-95.7, 29.1, -94.2, 30.1), self.root / f"{tag}-erddap.csv",
            opener=erddap_mock,
        )
        fixture = ROOT / "tests/fixtures/synthetic_ais.csv"
        archive = self.root / f"{tag}-ais-2024-01-02.csv.zst"
        archive.write_bytes(zstandard.ZstdCompressor().compress(fixture.read_bytes()))
        report = extract_archive(
            archive, self.root / f"{tag}-extract.csv",
            "2024-01-02T00:00:00Z", "2024-01-02T00:59:00Z",
        )
        return (
            ("erddap", erddap, self.erddap_schema),
            ("archive", report, self.archive_schema),
        )

    def test_official_register_does_not_grant_adapter_rights(self):
        official = ROOT / "docs/data/rights-register.json"
        before = official.read_bytes()
        register = json.loads(before)
        self.assertEqual(len(register["sources"]), 5)
        for source in register["sources"]:
            self.assertEqual(source["decision"], "pending", source["source_id"])
            self.assertEqual(source["rights_status"], "review_required", source["source_id"])
        granted = {
            "reviewed_public_domain_attribution_required",
            "reviewed_permitted_with_conditions",
        }
        fixture = ROOT / "tests/fixtures/synthetic_ais.csv"
        archive = self.root / "ais-2024-01-02.csv.zst"
        archive.write_bytes(zstandard.ZstdCompressor().compress(fixture.read_bytes()))
        calls = (
            lambda purpose: fetch_subset(
                "2024-06-10T00:00:00Z", "2024-06-10T01:00:00Z",
                (-95.7, 29.1, -94.2, 30.1),
                self.root / f"erddap-{purpose}.csv",
                opener=erddap_mock, rights_register=official,
                rights_purpose=purpose,
            ),
            lambda purpose: save_catalog(
                self.root / f"usace-{purpose}.geojson", opener=usace_mock,
                rights_register=official, rights_purpose=purpose,
            ),
            lambda purpose: save_polygons(
                self.root / f"noaa-{purpose}.geojson", opener=noaa_polygon_mock,
                rights_register=official, rights_purpose=purpose,
            ),
            lambda purpose: extract_archive(
                archive, self.root / f"archive-{purpose}.csv",
                "2024-01-02T00:00:00Z", "2024-01-02T00:59:00Z",
                rights_register=official, rights_purpose=purpose,
            ),
        )
        for purpose in ("research", "public_aggregates", "commercial"):
            for call in calls:
                sidecar = call(purpose)
                status = sidecar.get("rights_status", sidecar.get("license_status"))
                self.assertEqual(status, "review_required", purpose)
                self.assertEqual(sidecar["rights_review"]["rights_status"], "review_required")
                self.assertNotIn(status, granted)
                if sidecar.get("dataset") == "AIS2024_AIS":
                    Draft202012Validator(self.erddap_schema).validate(sidecar)
                if sidecar.get("source_type") == "local_noaa_daily_archive":
                    Draft202012Validator(self.archive_schema).validate(sidecar)
        self.assertEqual(official.read_bytes(), before)

    def test_erddap_and_archive_sidecars_without_a_register_match_schema(self):
        erddap = fetch_subset(
            "2024-06-10T00:00:00Z", "2024-06-10T01:00:00Z",
            (-95.7, 29.1, -94.2, 30.1), self.root / "plain.csv", opener=erddap_mock,
        )
        Draft202012Validator(self.erddap_schema).validate(erddap)
        self.assertEqual(erddap["rights_status"], "review_required")
        self.assertEqual(erddap["rights_review"]["evaluation"], "not_supplied")
        self.assertNotIn(erddap["rights_status"], {
            "reviewed_public_domain_attribution_required",
            "reviewed_permitted_with_conditions",
        })
        fixture = ROOT / "tests/fixtures/synthetic_ais.csv"
        archive = self.root / "ais-2024-01-02.csv.zst"
        archive.write_bytes(zstandard.ZstdCompressor().compress(fixture.read_bytes()))
        report = extract_archive(
            archive, self.root / "plain-extract.csv",
            "2024-01-02T00:00:00Z", "2024-01-02T00:59:00Z",
        )
        Draft202012Validator(self.archive_schema).validate(report)
        self.assertEqual(report["rights_status"], "review_required")
        self.assertEqual(report["rights_review"]["evaluation"], "not_supplied")

    def test_sidecar_schemas_reject_a_disguised_grant(self):
        for name, sidecar, schema in self.writer_sidecars("neg"):
            validator = Draft202012Validator(schema)
            validator.validate(sidecar)
            disguised = deepcopy(sidecar)
            disguised["rights_review"]["evaluation"] = "reviewed_record"
            disguised["rights_review"]["rights_status"] = "review_required"
            self.assertFalse(validator.is_valid(disguised), name)
            unknown = deepcopy(sidecar)
            unknown["rights_status"] = "approved"
            unknown["rights_review"]["evaluation"] = "not_supplied"
            unknown["rights_review"]["rights_status"] = "review_required"
            unknown["rights_review"]["registry_sha256"] = None
            self.assertFalse(validator.is_valid(unknown), name)
            padded = deepcopy(sidecar)
            padded["rights_status"] = "review_required "
            self.assertFalse(validator.is_valid(padded), name)
            missing = deepcopy(sidecar)
            missing.pop("rights_status")
            self.assertFalse(validator.is_valid(missing), name)

    def test_optional_receipt_and_not_supplied_hash_boundary(self):
        for name, sidecar, schema in self.writer_sidecars("optional"):
            validator = Draft202012Validator(schema)
            self.assertEqual(sidecar["rights_status"], "review_required")
            self.assertEqual(sidecar["rights_review"]["evaluation"], "not_supplied")
            self.assertIsNone(sidecar["rights_review"]["registry_sha256"])
            omitted = deepcopy(sidecar)
            omitted.pop("rights_review")
            validator.validate(omitted)
            hashed = deepcopy(sidecar)
            hashed["rights_review"]["registry_sha256"] = "c" * 64
            self.assertFalse(validator.is_valid(hashed), name)
            short = deepcopy(sidecar)
            short["warning"] = "x" * 9
            self.assertFalse(validator.is_valid(short), name)
            exact = deepcopy(sidecar)
            exact["warning"] = "x" * 10
            validator.validate(exact)

    def test_sidecar_count_and_digest_boundaries(self):
        pairs = {
            name: (doc, schema)
            for name, doc, schema in self.writer_sidecars("count")
        }
        erddap, erddap_schema = pairs["erddap"]
        archive, archive_schema = pairs["archive"]
        erddap_validator = Draft202012Validator(erddap_schema)
        zero_rows = deepcopy(erddap)
        zero_rows["rows"] = 0
        self.assertFalse(erddap_validator.is_valid(zero_rows))
        one_row = deepcopy(erddap)
        one_row["rows"] = 1
        erddap_validator.validate(one_row)
        short_hash = deepcopy(erddap)
        short_hash["raw_sha256"] = "a" * 63
        self.assertFalse(erddap_validator.is_valid(short_hash))
        full_hash = deepcopy(erddap)
        full_hash["raw_sha256"] = "a" * 64
        erddap_validator.validate(full_hash)

        archive_validator = Draft202012Validator(archive_schema)
        self.assertGreaterEqual(archive["counts"]["selected"], 1)
        zero_selected = deepcopy(archive)
        zero_selected["counts"]["selected"] = 0
        self.assertFalse(archive_validator.is_valid(zero_selected))
        one_selected = deepcopy(archive)
        one_selected["counts"]["selected"] = 1
        archive_validator.validate(one_selected)
        short_input = deepcopy(archive)
        short_input["input_sha256"] = "b" * 63
        self.assertFalse(archive_validator.is_valid(short_input))
        full_input = deepcopy(archive)
        full_input["input_sha256"] = "b" * 64
        archive_validator.validate(full_input)

    def test_sidecar_receipt_block_matches_the_receipt_schema(self):
        receipt = json.loads(
            (ROOT / "schemas/v1/source-rights-receipt.schema.json").read_text()
        )
        receipt.pop("$schema")
        receipt.pop("title")
        for name in (
            "erddap-ais-source.schema.json",
            "noaa-archive-extract-source.schema.json",
        ):
            schema = json.loads((ROOT / "schemas/v1" / name).read_text())
            Draft202012Validator.check_schema(schema)
            self.assertEqual(schema["properties"]["rights_review"], receipt)
            self.assertNotIn("rights_review", schema["required"])
            self.assertIn("rights_status", schema["required"])
        from importlib.resources import files
        packaged = {
            path.name
            for path in files("harborlens").joinpath("schemas", "v1").iterdir()
            if path.name.endswith(".json")
        }
        self.assertNotIn("erddap-ais-source.schema.json", packaged)
        self.assertNotIn("noaa-archive-extract-source.schema.json", packaged)


if __name__ == "__main__":
    unittest.main()
