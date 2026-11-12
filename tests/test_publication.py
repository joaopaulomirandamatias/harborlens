"""Offline adversarial tests for a rights-gated aggregate release (SPEC-003).

All vessel observations and approval records in this test are synthetic.
"""
from __future__ import annotations

import builtins
import io
import contextlib
import csv
import hashlib
import base64

import zstandard
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator

from harborlens.ais import run
from harborlens.erddap import fetch_subset
from harborlens.archive_extract import extract_archive
from harborlens.provenance import checksum
from harborlens.publication import (
    ReleaseDenied, prepare_summary, release_summary, summary_sha256,
    main as release_main
)
from harborlens.rights import rights_receipt
from harborlens.review_signatures import (
    REVIEW_SIGNATURE_DOMAIN, public_key_fingerprint, review_message,
)


def _load_cryptography():
    """Import Ed25519 helpers when the optional extra is installed."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError:
        return None
    return serialization, Ed25519PrivateKey


_CRYPTOGRAPHY = _load_cryptography()


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


@unittest.skipUnless(
    _CRYPTOGRAPHY is not None,
    "optional cryptography extra is not installed",
)
class PublicationGateTests(unittest.TestCase):
    def setUp(self):
        serialization, Ed25519PrivateKey = _CRYPTOGRAPHY
        self.serialization = serialization
        self.Ed25519PrivateKey = Ed25519PrivateKey
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.registry = self.folder / "rights-register.json"
        self.source = self.folder / "acquired.csv"
        self.rundir = self.folder / "run"
        self.out = self.folder / "release.json"
        self.review = self.folder / "review.json"
        self.private_key = Ed25519PrivateKey.generate()  # synthetic test only
        self.trusted_key = self.folder / "trusted-reviewer.pem"
        self.trusted_key.write_bytes(self.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        _, self.trusted_key_sha256 = public_key_fingerprint(self.trusted_key)
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

    def sign_review(self, review):
        """Attach a valid signature over the canonical, pinned review claims."""
        review["signature_b64"] = ""
        review["signature_b64"] = base64.b64encode(
            self.private_key.sign(review_message(review))
        ).decode("ascii")
        return review

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
            "signature_algorithm": "Ed25519",
            "public_key_sha256": self.trusted_key_sha256,
        }
        self.sign_review(review)
        self.review.write_text(json.dumps(review), encoding="utf-8")
        return review

    def produce(self, purpose="public_aggregates"):
        return release_summary(
            self.rundir, self.source, self.registry, self.out, self.review,
            purpose=purpose, trusted_public_key=self.trusted_key,
            expected_public_key_sha256=self.trusted_key_sha256,
            expected_reviewer_id="sample-reviewer",
        )

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
        self.sign_review(review)
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

    def test_manifest_written_count_disagreement_is_denied(self):
        self.decide()
        manifest = self.rundir / "manifest.json"
        doc = json.loads(manifest.read_text())
        doc["counts"]["written"] = 6
        manifest.write_text(json.dumps(doc))
        with self.assertRaisesRegex(ReleaseDenied, "do not match"):
            prepare_summary(self.rundir, self.source, self.registry)
        self.assertFalse(self.out.exists())

    def test_receipt_rechecks_current_registry_without_reacquisition(self):
        self.decide()
        updated = rights_receipt("noaa_pmel_erddap", dataset_version="AIS2024_AIS",
                                 purpose="public_aggregates", register_path=self.registry)
        self.assertEqual(updated["evaluation"], "reviewed_record")
        self.assertEqual(prepare_summary(self.rundir, self.source, self.registry)
                         ["rights_registry_sha256"], updated["registry_sha256"])

    def test_review_schema_is_valid_and_enforced(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        review = self.approve(summary)
        schema = json.loads(
            (ROOT / "schemas/v1/publication-review.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema).validate(review)
        review["privacy_reviewed"] = False
        self.assertFalse(Draft202012Validator(schema).is_valid(review))

    def test_cli_denies_pending_source_and_dry_run_remains_local(self):
        cmd = [
            "--run", str(self.rundir), "--source-file", str(self.source),
            "--rights-register", str(self.registry), "--dry-run",
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as denied:
                release_main(cmd)
        self.assertEqual(denied.exception.code, 2)
        self.assertFalse(self.out.exists())
        self.decide()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            release_main(cmd)
        response = json.loads(output.getvalue())
        self.assertEqual(
            response["summary_sha256"],
            summary_sha256(prepare_summary(self.rundir, self.source, self.registry))
        )
        self.assertEqual(response["decision"], "requires_human_release_review")
        self.assertFalse(self.out.exists())

    def test_archive_source_chain_and_actual_release(self):
        header = (
            "mmsi,base_date_time,longitude,latitude,sog,cog,heading,"
            "vessel_name,imo,call_sign,vessel_type,status,length,width,draft,"
            "cargo,transceiver\n"
        )
        records = []
        for i in range(12):
            for minute in range(12):
                records.append(
                    f"{367800001+i},2024-06-10T00:{minute:02d}:00Z,"
                    f"{-95.20+i*.001:.4f},{29.70+i*.001:.4f},0.1,"
                    ",,,,,70,5,,,,,\n"
                )
        archive = self.folder / "ais-2024-06-10.csv.zst"
        archive.write_bytes(
            zstandard.ZstdCompressor().compress(
                (header + "".join(records)).encode()
            )
        )
        extracted = self.folder / "archive-extracted.csv"
        extract_archive(archive, extracted, START, END, rights_register=self.registry)
        archived_run = self.folder / "archive-run"
        run(extracted, archived_run)
        expected_version = (
            "2024/archive-sha256:" + hashlib.sha256(archive.read_bytes()).hexdigest()
        )
        registry = json.loads(self.registry.read_text())
        item = next(x for x in registry["sources"]
                    if x["source_id"] == "noaa_ocm_ais_daily")
        item.update({
            "dataset_version": expected_version,
            "decision": "reviewed",
            "rights_status": "reviewed_public_domain_attribution_required",
            "reviewed_by": "Synthetic approval fixture",
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "attribution": "Synthetic archive",
            "terms_sha256": "a" * 64,
            "terms_url": "https://example.test/terms",
            "evidence_url": "https://example.test/approval",
            "permitted_uses": {
                "research": "allowed",
                "public_aggregates": "allowed",
                "commercial": "prohibited",
            },
        })
        self.registry.write_text(json.dumps(registry))
        summary = prepare_summary(archived_run, extracted, self.registry)
        self.assertEqual(summary["source_id"], "noaa_ocm_ais_daily")
        self.assertEqual(summary["dataset_version"], expected_version)
        self.assertEqual(summary["counts"]["observations_retained"], 144)
        self.approve(summary)
        result = release_summary(
            archived_run, extracted, self.registry, self.out, self.review,
            trusted_public_key=self.trusted_key,
            expected_public_key_sha256=self.trusted_key_sha256,
            expected_reviewer_id="sample-reviewer",
        )
        self.assertEqual(result["summary"]["source_id"], "noaa_ocm_ais_daily")
        self.assertTrue(self.out.exists())

    def test_unsigned_or_modified_review_is_denied(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        review = self.approve(summary)
        unsigned = dict(review)
        unsigned.pop("signature_b64")
        self.review.write_text(json.dumps(unsigned), encoding="utf-8")
        with self.assertRaisesRegex(ReleaseDenied, "Independent release review"):
            self.produce()
        review["conditions_reviewed"] = not review["conditions_reviewed"]
        self.review.write_text(json.dumps(review), encoding="utf-8")
        with self.assertRaisesRegex(ReleaseDenied, "signature"):
            self.produce()
        self.assertFalse(self.out.exists())

    def test_wrong_key_fingerprint_and_identity_are_denied(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        self.approve(summary)
        with self.assertRaisesRegex(ReleaseDenied, "fingerprint"):
            release_summary(
                self.rundir, self.source, self.registry, self.out, self.review,
                trusted_public_key=self.trusted_key,
                expected_public_key_sha256="0" * 64,
                expected_reviewer_id="sample-reviewer",
            )
        with self.assertRaisesRegex(ReleaseDenied, "identity"):
            release_summary(
                self.rundir, self.source, self.registry, self.out, self.review,
                trusted_public_key=self.trusted_key,
                expected_public_key_sha256=self.trusted_key_sha256,
                expected_reviewer_id="someone-else",
            )
        alternate = self.Ed25519PrivateKey.generate()
        other_key = self.folder / "other.pem"
        other_key.write_bytes(alternate.public_key().public_bytes(
            encoding=self.serialization.Encoding.PEM,
            format=self.serialization.PublicFormat.SubjectPublicKeyInfo,
        ))
        with self.assertRaisesRegex(ReleaseDenied, "fingerprint"):
            release_summary(
                self.rundir, self.source, self.registry, self.out, self.review,
                trusted_public_key=other_key,
                expected_public_key_sha256=self.trusted_key_sha256,
                expected_reviewer_id="sample-reviewer",
            )
        self.assertFalse(self.out.exists())

    def test_cli_requires_pinned_key_for_actual_release(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        self.approve(summary)
        cmd = [
            "--run", str(self.rundir), "--source-file", str(self.source),
            "--rights-register", str(self.registry), "--review", str(self.review),
            "--out", str(self.out),
        ]
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as denied:
                release_main(cmd)
        self.assertEqual(denied.exception.code, 2)
        self.assertFalse(self.out.exists())
        cmd.extend([
            "--trusted-reviewer-key", str(self.trusted_key),
            "--trusted-reviewer-key-sha256", self.trusted_key_sha256,
            "--trusted-reviewer-id", "sample-reviewer",
        ])
        with contextlib.redirect_stdout(io.StringIO()):
            release_main(cmd)
        self.assertTrue(self.out.exists())

    def rewrite_cleaned(self, observations, groups, *,
                        manifest_written=None, manifest_vessels=None):
        """Replace the verified cleaned file with a synthetic recount fixture."""
        path = self.rundir / "houston_clean.csv"
        fieldnames = [
            "mmsi", "timestamp_utc", "lat", "lon", "sog_knots", "vessel_type",
            "nav_status", "cog_deg", "heading_deg", "length_m", "width_m",
            "draft_m", "transceiver_class", "mmsi_category",
        ]
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for index in range(observations):
                writer.writerow({
                    "mmsi": str(900000001 + (index % groups)),
                    "timestamp_utc": "2024-06-10T00:00:00Z",
                    "lat": "29.70",
                    "lon": "-95.20",
                    "sog_knots": "0.1",
                    "vessel_type": "70",
                    "nav_status": "5",
                    "cog_deg": "",
                    "heading_deg": "",
                    "length_m": "",
                    "width_m": "",
                    "draft_m": "",
                    "transceiver_class": "",
                    "mmsi_category": "ship",
                })
        manifest_path = self.rundir / "manifest.json"
        document = json.loads(manifest_path.read_text(encoding="utf-8"))
        document["artifacts"]["houston_clean.csv"] = {
            "sha256": checksum(path),
            "size_bytes": path.stat().st_size,
        }
        document["counts"]["written"] = (
            observations if manifest_written is None else manifest_written
        )
        document["events"]["vessels"] = (
            groups if manifest_vessels is None else manifest_vessels
        )
        if document["counts"]["total"] < document["counts"]["written"]:
            document["counts"]["total"] = document["counts"]["written"]
        document["events"]["stationary_candidates"] = 0
        manifest_path.write_text(json.dumps(document), encoding="utf-8")

    def release_command(self):
        return [
            "--run", str(self.rundir),
            "--source-file", str(self.source),
            "--rights-register", str(self.registry),
            "--review", str(self.review),
            "--out", str(self.out),
            "--trusted-reviewer-key", str(self.trusted_key),
            "--trusted-reviewer-key-sha256", self.trusted_key_sha256,
            "--trusted-reviewer-id", "sample-reviewer",
        ]

    def assert_cli_denied(self, pattern):
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as caught:
                release_main(self.release_command())
        self.assertEqual(caught.exception.code, 2)
        message = stderr.getvalue()
        self.assertNotIn("Traceback", message)
        self.assertIn("Release denied", message)
        self.assertRegex(message, pattern)
        self.assertFalse(self.out.exists())

    def test_recounted_100_observations_are_allowed(self):
        self.decide()
        self.rewrite_cleaned(100, 12)
        summary = prepare_summary(self.rundir, self.source, self.registry)
        self.assertEqual(summary["counts"]["observations_retained"], 100)
        self.assertEqual(summary["counts"]["unique_mmsi_groups"], 12)
        self.approve(summary)
        result = self.produce()
        self.assertEqual(result["summary"]["counts"]["observations_retained"], 100)
        schema = json.loads((ROOT / "schemas/v1/public-summary.schema.json").read_text())
        Draft202012Validator(schema).validate(result)
        exported = self.out.read_text(encoding="utf-8")
        self.assertNotIn("900000001", exported)

    def test_recounted_99_observations_are_denied(self):
        self.decide()
        self.rewrite_cleaned(99, 12)
        self.assert_cli_denied("Aggregate count")

    def test_recounted_10_mmsi_groups_are_allowed(self):
        self.decide()
        self.rewrite_cleaned(120, 10)
        summary = prepare_summary(self.rundir, self.source, self.registry)
        self.assertEqual(summary["counts"]["observations_retained"], 120)
        self.assertEqual(summary["counts"]["unique_mmsi_groups"], 10)
        self.approve(summary)
        result = self.produce()
        self.assertEqual(result["summary"]["counts"]["unique_mmsi_groups"], 10)
        self.assertTrue(self.out.exists())

    def test_recounted_9_mmsi_groups_are_denied(self):
        self.decide()
        self.rewrite_cleaned(120, 9)
        self.assert_cli_denied("Aggregate count")

    def test_tampered_manifest_counts_are_denied(self):
        self.decide()
        self.rewrite_cleaned(120, 12, manifest_written=1000, manifest_vessels=40)
        self.assert_cli_denied("do not match")

    def test_date_only_review_timestamp_exits_2(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        review = self.approve(summary)
        for stamp in ("2026-11-12", "2026-11-12Z"):
            if self.out.exists():
                self.out.unlink()
            review["reviewed_at_utc"] = stamp
            self.sign_review(review)
            self.review.write_text(json.dumps(review), encoding="utf-8")
            self.assert_cli_denied("date-time")

    def test_non_finite_number_fails_closed(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        self.approve(summary)
        poisoned = json.loads(json.dumps(summary))
        poisoned["counts"]["observations_retained"] = float("nan")
        with mock.patch("harborlens.publication.prepare_summary", return_value=poisoned):
            self.assert_cli_denied("non-finite")

    def test_legacy_signature_without_domain_separator_is_denied(self):
        self.decide()
        summary = prepare_summary(self.rundir, self.source, self.registry)
        review = self.approve(summary)
        claims = {name: value for name, value in review.items() if name != "signature_b64"}
        legacy = (json.dumps(claims, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
        self.assertFalse(legacy.startswith(REVIEW_SIGNATURE_DOMAIN.encode("ascii")))
        review["signature_b64"] = base64.b64encode(
            self.private_key.sign(legacy)
        ).decode("ascii")
        self.review.write_text(json.dumps(review), encoding="utf-8")
        self.assert_cli_denied("signature")


def _approve_registry(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    entry = next(item for item in data["sources"] if item["source_id"] == "noaa_pmel_erddap")
    entry.update({
        "decision": "reviewed",
        "rights_status": "reviewed_public_domain_attribution_required",
        "reviewed_by": "Synthetic approval fixture",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "attribution": "Source: synthetic NOAA example",
        "terms_sha256": "a" * 64,
        "terms_url": "https://example.test/terms",
        "evidence_url": "https://example.test/approval",
        "permitted_uses": {
            "research": "allowed",
            "public_aggregates": "allowed",
            "commercial": "prohibited",
        },
    })
    path.write_text(json.dumps(data), encoding="utf-8")


class MissingCryptographyReleaseTests(unittest.TestCase):
    """A missing Ed25519 library must deny release without writing a file."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.registry = self.folder / "rights-register.json"
        self.source = self.folder / "acquired.csv"
        self.rundir = self.folder / "run"
        self.out = self.folder / "release.json"
        self.review = self.folder / "review.json"
        self.key = self.folder / "trusted-reviewer.pem"
        self.key.write_bytes(b"not-a-key\n")
        self.registry.write_text(
            (ROOT / "docs/data/rights-register.json").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
        fetch_subset(START, END, BBOX, self.source,
                     opener=fake_erddap, rights_register=self.registry)
        run(self.source, self.rundir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_import_error_denies_release_without_writing(self):
        _approve_registry(self.registry)
        summary = prepare_summary(self.rundir, self.source, self.registry)
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
            "conditions_reviewed": False,
            "signature_algorithm": "Ed25519",
            "public_key_sha256": "a" * 64,
            "signature_b64": "A" * 86 + "==",
        }
        self.review.write_text(json.dumps(review), encoding="utf-8")
        real_import = builtins.__import__

        def blocked(name, *args, **kwargs):
            if name == "cryptography" or name.startswith("cryptography."):
                raise ImportError("cryptography is not installed")
            return real_import(name, *args, **kwargs)

        command = [
            "--run", str(self.rundir),
            "--source-file", str(self.source),
            "--rights-register", str(self.registry),
            "--review", str(self.review),
            "--out", str(self.out),
            "--trusted-reviewer-key", str(self.key),
            "--trusted-reviewer-key-sha256", "a" * 64,
            "--trusted-reviewer-id", "sample-reviewer",
        ]
        stderr = io.StringIO()
        with mock.patch("builtins.__import__", side_effect=blocked):
            with contextlib.redirect_stderr(stderr):
                with self.assertRaises(SystemExit) as caught:
                    release_main(command)
        self.assertEqual(caught.exception.code, 2)
        message = stderr.getvalue()
        self.assertNotIn("Traceback", message)
        self.assertIn("Release denied", message)
        self.assertIn("Install the release extra", message)
        self.assertFalse(self.out.exists())


if __name__ == "__main__":
    unittest.main()
