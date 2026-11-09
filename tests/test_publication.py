"""Offline adversarial tests for a rights-gated aggregate release (SPEC-003).

All vessel observations and approval records in this test are synthetic.
"""
from __future__ import annotations

import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jsonschema import Draft202012Validator

from harborlens.ais import run
from harborlens.erddap import fetch_subset
from harborlens.publication import (
    ReleaseDenied, prepare_summary, release_summary, summary_sha256
)
from harborlens.rights import rights_receipt


ROOT = Path(__file__).resolve().parents[1]
START = "2024-06-10T00:00:00Z"
END = "2024-06-10T01:00:00Z"
BBOX = (-95.7, 29.1, -94.2, 30.1)


class MockResponse(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.headers = {"Content-Length": str(len(payload))}


def fake_erddap(req, timeout):
    rows = ["MMSI,time,Lat,Lon,SOG,VesselType,Status",
            ",UTC,degrees_north,degrees_east,knots,,"]
    for i in range(12):
        mmsi = 367800001 + i
        for minute in range(12):
            rows.append(
                f"{mmsi},2024-06-10T00:{minute:02d}:00Z,"
                f"{29.70 + i * .001:.4f},{-95.20 + i * .001:.4f},0.1,70,5"
            )
    return MockResponse(("\n".join(rows) + "\n").encode())


class PublicationGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.registry = self.folder / "rights-register.json"
        self.source = self.folder / "acquired.csv"
        self.rundir = self.folder / "run"
        self.out = self.folder / "release.json"
        self.review = self.folder / "review.json"
        self.registry.write_text(
            (ROOT / "docs/data/rights-register.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        fetch_subset(START, END, BBOX, self.source,
                     opener=fake_erddap, rights_register=self.registry)
        self.manifest = run(self.source, self.rundir)

    def tearDown(self):
        self.tmp.cleanup()

    def decide(self, public="allowed", commercial="prohibited", restricted=False):
        data = json.loads(self.registry.read_text(encoding="utf-8"))
        entry = next(s for s in data["sources"]
                     if s["source_id"] == "noaa_pmel_erddap")
        entry.update({
            "decision": "reviewed",
            "rights_status": (
                "reviewed_permitted_with_conditions"
                if restricted else "reviewed_public_domain_attribution_required"
            ),
            "reviewed_by": "Synthetic approval fixture",
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "attribution": "Source: synthetic NOAA example",
            "terms_sha256": "a" * 64,
            "terms_url": "https://example.test/terms",
            "evidence_url": "https://example.test/approval",
            "permitted_uses": {
                "research": "allowed",
                "public_aggregates": public,
                "commercial": commercial,
            },
        })
        self.registry.write_text(json.dumps(data), encoding="utf-8")

    def approve(self, summary, *, conditions=False):
        review = {
            "schema_version": 1,
            "decision": "approved",
            "summary_sha256": summary_sha256(summary),
            "purpose": summary["purpose"],
            "reviewer_id": "sample-reviewer",
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "privacy_reviewed": True,
            "source_rights_reviewed": True,
            "scientific_limitations_reviewed": True,
            "conditions_reviewed": conditions,
        }
        self.review.write_text(json.dumps(review), encoding="utf-8")
        return review

    def produce(self, purpose="public_aggregates"):
        return release_summary(self.rundir, self.source, self.registry,
                               self.out, self.review, purpose=purpose)

    def test_checked_in_pending_registry_blocks_publication(self):
        with self.assertRaisesRegex(ReleaseDenied, "rights decision"):
            prepare_summary(self.rundir, self.source, self.registry)
        self.assertFalse(self.out.exists())

    def test_allowed_summary_with_matching_attestation(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        self.assertEqual(summary["counts"]["observations_retained"], 144)
        self.assertEqual(summary["counts"]["unique_mmsi_groups"], 12)
        self.assertEqual(summary["source_id"], "noaa_pmel_erddap")
        self.assertEqual(summary["rights_status"],
                         "reviewed_public_domain_attribution_required")
        self.approve(summary)
        result = self.produce()
        self.assertEqual(result, json.loads(self.out.read_text(encoding="utf-8")))
        schema = json.loads((ROOT / "schemas/v1/public-summary.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(result)
        self.assertEqual(result["summary_sha256"], summary_sha256(result["summary"]))
        exported = self.out.read_text(encoding="utf-8")
        self.assertNotIn("367800001", exported)
        self.assertNotIn("2024-06-10T00:", exported)
        self.assertNotIn("-95.2", exported)
        self.assertNotIn("centroid_lon", exported)
        self.assertNotIn("event_id", exported)

    def test_no_review_file_blocks_even_when_rights_allowed(self):
        self.decide()
        with self.assertRaises(ReleaseDenied):
            self.produce()
        self.assertFalse(self.out.exists())

    def test_commercial_prohibition_is_never_approved(self):
        self.decide()
        with self.assertRaisesRegex(ReleaseDenied, "rights decision"):
            prepare_summary(self.rundir, self.source, self.registry,
                            purpose="commercial")
        self.assertFalse(self.out.exists())

    def test_current_pending_overrides_claims_in_acquisition_receipt(self):
        sidecar = self.source.with_name(self.source.name + ".source.json")
        doc = json.loads(sidecar.read_text())
        doc["rights_status"] = "reviewed_public_domain_attribution_required"
        doc["rights_review"]["rights_status"] = doc["rights_status"]
        doc["rights_review"]["evaluation"] = "reviewed_record"
        sidecar.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ReleaseDenied, "rights decision"):
            prepare_summary(self.rundir, self.source, self.registry)

    def test_source_and_analysis_integrity_are_checked(self):
        self.decide()
        with self.source.open("a", encoding="utf-8") as file:
            file.write("extra,row,from,wrong,source\n")
        with self.assertRaisesRegex(ReleaseDenied, "do not match"):
            prepare_summary(self.rundir, self.source, self.registry)

    def test_analysis_output_tampering_is_blocked(self):
        self.decide()
        with (self.rundir / "stationary_candidates.csv").open("a") as file:
            file.write("tampered\n")
        with self.assertRaisesRegex(ReleaseDenied, "Run artifact checksums"):
            prepare_summary(self.rundir, self.source, self.registry)

    def test_acquisition_identity_change_is_blocked(self):
        self.decide()
        sidecar = self.source.with_name(self.source.name + ".source.json")
        meta = json.loads(sidecar.read_text())
        meta["rights_review"]["dataset_version"] = "AIS2023_AIS"
        sidecar.write_text(json.dumps(meta))
        with self.assertRaisesRegex(ReleaseDenied, "identity/version"):
            prepare_summary(self.rundir, self.source, self.registry)

    def test_modified_registry_requires_new_human_review(self):
        self.decide()
        original = prepare_summary(self.rundir, self.source, self.registry)
        self.approve(original)
        raw = json.loads(self.registry.read_text())
        raw["purpose"] = "Different registry bytes and provenance"
        self.registry.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ReleaseDenied, "Independent release review"):
            self.produce()
        self.assertFalse(self.out.exists())

    def test_mismatched_or_incomplete_human_review_denied(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        review = self.approve(summary)
        review["summary_sha256"] = "b" * 64
        self.review.write_text(json.dumps(review))
        with self.assertRaises(ReleaseDenied):
            self.produce()
        review["summary_sha256"] = summary_sha256(summary)
        review["privacy_reviewed"] = False
        self.review.write_text(json.dumps(review))
        with self.assertRaises(ReleaseDenied):
            self.produce()
        self.assertFalse(self.out.exists())

    def test_review_must_be_recent(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        review = self.approve(summary)
        review["reviewed_at_utc"] = (
            datetime.now(timezone.utc) - timedelta(days=32)
        ).isoformat().replace("+00:00", "Z")
        self.review.write_text(json.dumps(review))
        with self.assertRaisesRegex(ReleaseDenied, "stale"):
            self.produce()

    def test_license_conditions_need_explicit_review(self):
        self.decide(restricted=True)
        summary = prepare_summary(self.rundir, self.source, self.registry)
        review = self.approve(summary, conditions=False)
        with self.assertRaisesRegex(ReleaseDenied, "conditions"):
            self.produce()
        review["conditions_reviewed"] = True
        self.review.write_text(json.dumps(review))
        self.assertEqual(self.produce()["summary"]["rights_status"],
                         "reviewed_permitted_with_conditions")

    def test_publication_is_not_overwritten(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        self.approve(summary)
        self.produce()
        saved = self.out.read_bytes()
        with self.assertRaisesRegex(ReleaseDenied, "new JSON file"):
            self.produce()
        self.assertEqual(self.out.read_bytes(), saved)

    def test_small_sample_is_not_exported(self):
        self.decide()
        manifest = self.rundir / "manifest.json"
        doc = json.loads(manifest.read_text())
        doc["counts"]["written"] = 6
        manifest.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ReleaseDenied, "Aggregate count"):
            prepare_summary(self.rundir, self.source, self.registry)

    def test_receipt_rechecks_current_registry_without_reacquisition(self):
        self.decide()
        updated = rights_receipt("noaa_pmel_erddap", dataset_version="AIS2024_AIS",
                                 purpose="public_aggregates", register_path=self.registry)
        self.assertEqual(updated["evaluation"], "reviewed_record")
        self.assertEqual(prepare_summary(self.rundir, self.source, self.registry)
                         ["rights_registry_sha256"], updated["registry_sha256"])


if __name__ == "__main__":
    unittest.main()
