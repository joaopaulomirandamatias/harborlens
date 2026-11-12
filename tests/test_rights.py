"""Offline, synthetic tests for the fail-closed rights decision gate."""
import hashlib
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from importlib.resources import files
from unittest.mock import patch

from harborlens.rights import (
    APPROVED_STATUSES, PENDING, RESTRICTED, _MISSING_JSONSCHEMA,
    _UTF8_BOM_ERROR, _is_https_url, _valid_utc_time, load_registry,
    rights_receipt, rights_status_for,
)


class RightsGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rights.json"
        self.record = {
            "source_id": "noaa_pmel_erddap",
            "dataset_version": "AIS2024_AIS",
            "rights_status": "reviewed_public_domain_attribution_required",
            "decision": "reviewed",
            "reviewed_by": "Independent reviewer",
            "reviewed_at_utc": "2026-11-09T12:00:00Z",
            "source_url": "https://example.org/source",
            "terms_url": "https://example.org/terms",
            "evidence_url": "https://example.org/review",
            "terms_sha256": "a" * 64,
            "attribution": "Source agency and dataset.",
            "review_note": "Synthetic review record; not a real source approval.",
            "permitted_uses": {
                "research": "allowed",
                "public_aggregates": "allowed",
                "commercial": "prohibited",
            },
        }
        self.data = {"schema_version": 1, "sources": [self.record]}

    def tearDown(self):
        self.temp.cleanup()

    def write(self, data=None):
        self.path.write_text(json.dumps(self.data if data is None else data), encoding="utf-8")

    def status(self, purpose="research", version="AIS2024_AIS", source="noaa_pmel_erddap"):
        return rights_status_for(source, dataset_version=version,
                                 purpose=purpose, register_path=self.path)

    def test_matching_reviewed_record_is_used(self):
        self.write()
        self.assertEqual(self.status(), "reviewed_public_domain_attribution_required")
        self.assertEqual(self.status("public_aggregates"), "reviewed_public_domain_attribution_required")
        self.assertEqual(self.status("commercial"), RESTRICTED)

    def test_unknown_version_source_and_missing_register_fail_closed(self):
        self.assertEqual(self.status(), PENDING)
        self.write()
        self.assertEqual(self.status(version="AIS2025_AIS"), PENDING)
        self.assertEqual(self.status(source="other_source"), PENDING)

    def test_unreviewed_entries_cannot_grant_permission(self):
        self.record["decision"] = "pending"
        self.write()
        self.assertEqual(self.status(), PENDING)
        self.record["decision"] = "reviewed"
        self.record["rights_status"] = "review_required"
        self.write()
        self.assertEqual(self.status(), PENDING)

    def test_review_evidence_is_required(self):
        for key, bad in (
            ("reviewed_by", None),
            ("reviewed_at_utc", "2026-11-09T12:00:00"),
            ("terms_url", "http://example.org/terms"),
            ("evidence_url", ""),
            ("terms_sha256", "bad"),
            ("attribution", ""),
        ):
            copy = deepcopy(self.data)
            copy["sources"][0][key] = bad
            self.write(copy)
            self.assertEqual(self.status(), PENDING, key)

    def test_unreviewed_purpose_and_invalid_permission_fail_closed(self):
        self.record["permitted_uses"]["research"] = "unreviewed"
        self.write()
        self.assertEqual(self.status(), PENDING)
        self.record["permitted_uses"]["research"] = "unrestricted"
        self.write()
        self.assertEqual(self.status(), PENDING)
        with self.assertRaisesRegex(ValueError, "Unsupported use"):
            self.status("navigation")

    def test_duplicate_source_and_bad_json_fail_closed(self):
        self.data["sources"].append(deepcopy(self.record))
        self.write()
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            load_registry(self.path)
        self.assertEqual(self.status(), PENDING)
        self.path.write_text("{", encoding="utf-8")
        self.assertEqual(self.status(), PENDING)

    def test_large_registry_and_bad_version_fail_closed(self):
        self.write()
        self.path.write_bytes(b"x" * (256 * 1024 + 1))
        self.assertEqual(self.status(), PENDING)
        self.write({"schema_version": 99, "sources": [self.record]})
        self.assertEqual(self.status(), PENDING)

    def test_https_url_requires_scheme_and_host(self):
        self.write()
        load_registry(self.path)
        self.assertTrue(_is_https_url("https://example.org/terms"))
        self.assertEqual(self.status(), "reviewed_public_domain_attribution_required")
        bad_urls = (
            "https://",
            "https:///path",
            "http://host",
            "https://user@",
            "https://.",
            "https:// ",
            "https://@",
        )
        for bad in bad_urls:
            self.assertFalse(_is_https_url(bad), bad)
            for key in ("terms_url", "evidence_url"):
                copy = deepcopy(self.data)
                copy["sources"][0][key] = bad
                self.write(copy)
                with self.assertRaisesRegex(ValueError, "schema"):
                    load_registry(self.path)
                self.assertEqual(self.status(), PENDING, (key, bad))

    def test_schema_invalid_register_with_complete_evidence_is_not_granted(self):
        copy = deepcopy(self.data)
        copy["sources"][0]["unexpected_field"] = "complete evidence, unknown property"
        self.write(copy)
        with self.assertRaisesRegex(ValueError, "schema"):
            load_registry(self.path)
        self.assertEqual(self.status(), PENDING)

    def test_checked_in_register_loads_and_grants_nothing(self):
        path = Path(__file__).resolve().parents[1] / "docs/data/rights-register.json"
        registry = load_registry(path)
        self.assertEqual(len(registry["sources"]), 5)
        purposes = ("research", "public_aggregates", "commercial")
        for source in registry["sources"]:
            self.assertEqual(source["decision"], "pending", source["source_id"])
            self.assertEqual(source["rights_status"], PENDING, source["source_id"])
            self.assertEqual(
                set(source["permitted_uses"]), set(purposes), source["source_id"]
            )
            for purpose in purposes:
                self.assertEqual(
                    source["permitted_uses"][purpose], "unreviewed",
                    (source["source_id"], purpose),
                )
                status = rights_status_for(
                    source["source_id"], dataset_version=source["dataset_version"],
                    purpose=purpose, register_path=path,
                )
                self.assertEqual(status, PENDING, (source["source_id"], purpose))
                self.assertNotIn(status, APPROVED_STATUSES)

    def test_packaged_schema_matches_published_file(self):
        packaged = files("harborlens").joinpath(
            "schemas", "v1", "source-rights-register.schema.json"
        ).read_bytes()
        published = (
            Path(__file__).resolve().parents[1]
            / "schemas" / "v1" / "source-rights-register.schema.json"
        )
        self.assertEqual(packaged, published.read_bytes())

    def test_parent_directory_schema_is_never_consulted(self):
        import harborlens.rights as rights_mod
        foreign_dir = Path(rights_mod.__file__).resolve().parents[1] / "schemas" / "v1"
        target = foreign_dir / "source-rights-register.schema.json"
        created = []
        cursor = foreign_dir
        while not cursor.exists():
            created.append(cursor)
            cursor = cursor.parent
        for directory in reversed(created):
            directory.mkdir()
        target.write_text('{"type": "object"}\n', encoding="utf-8")
        try:
            copy = deepcopy(self.data)
            copy["sources"][0]["unexpected_field"] = "permissive parent schema must not grant this"
            self.write(copy)
            with self.assertRaisesRegex(ValueError, "schema"):
                load_registry(self.path)
            self.assertEqual(self.status(), PENDING)
            packaged = files("harborlens").joinpath(
                "schemas", "v1", "source-rights-register.schema.json"
            ).read_bytes()
            self.assertNotEqual(packaged, target.read_bytes())
        finally:
            if target.exists():
                target.unlink()
            for directory in created:
                try:
                    directory.rmdir()
                except OSError:
                    pass

    def test_receipt_reads_once_and_binds_hash_to_that_buffer(self):
        self.write()
        original = self.path.read_bytes()
        swapped_doc = deepcopy(self.data)
        swapped_doc["sources"][0]["dataset_version"] = "other-version"
        swapped = json.dumps(swapped_doc).encode("utf-8")
        reads = []
        real_read = Path.read_bytes
        real_text = Path.read_text

        def fake_read(path_self, *args, **kwargs):
            if Path(path_self) == self.path:
                reads.append(path_self)
                if len(reads) == 1:
                    self.path.write_bytes(swapped)
                    return original
                return real_read(path_self, *args, **kwargs)
            return real_read(path_self, *args, **kwargs)

        def fake_text(path_self, *args, **kwargs):
            if Path(path_self) == self.path:
                raise AssertionError("rights_receipt reopened the register as text")
            return real_text(path_self, *args, **kwargs)

        with patch.object(Path, "read_bytes", fake_read), patch.object(Path, "read_text", fake_text):
            receipt = rights_receipt(
                "noaa_pmel_erddap", dataset_version="AIS2024_AIS",
                purpose="research", register_path=self.path,
            )
        self.assertEqual(len(reads), 1)
        self.assertEqual(receipt["registry_sha256"], hashlib.sha256(original).hexdigest())
        self.assertNotEqual(receipt["registry_sha256"], hashlib.sha256(swapped).hexdigest())
        self.assertEqual(
            receipt["rights_status"], "reviewed_public_domain_attribution_required"
        )
        self.assertEqual(receipt["evaluation"], "reviewed_record")

    def test_missing_jsonschema_names_rights_extra(self):
        self.write()
        with patch("harborlens.rights._load_jsonschema", side_effect=ImportError("blocked")):
            with self.assertRaisesRegex(ValueError, r"pip install 'harborlens\[rights\]'"):
                load_registry(self.path)
            self.assertEqual(self.status(), PENDING)
        self.assertIn("pip install 'harborlens[rights]'", _MISSING_JSONSCHEMA)

    def test_utf8_bom_is_a_named_load_error_and_not_approved(self):
        self.write()
        payload = json.dumps(self.data).encode("utf-8")
        self.path.write_bytes(b"\xef\xbb\xbf" + payload)
        with self.assertRaisesRegex(ValueError, "UTF-8 BOM"):
            load_registry(self.path)
        self.assertEqual(self.status(), PENDING)
        self.assertNotIn(self.status(), APPROVED_STATUSES)
        receipt = rights_receipt(
            "noaa_pmel_erddap", dataset_version="AIS2024_AIS",
            purpose="research", register_path=self.path,
        )
        self.assertEqual(receipt["evaluation"], "invalid_registry")
        self.assertEqual(receipt["rights_status"], PENDING)
        self.assertIsNone(receipt["registry_sha256"])
        self.assertEqual(_UTF8_BOM_ERROR, "Rights register has a UTF-8 BOM")

    def test_yaml_register_fails_closed(self):
        self.path.write_text("schema_version: 1\nsources: []\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "unreadable"):
            load_registry(self.path)
        self.assertEqual(self.status(), PENDING)
        self.assertNotIn(self.status(), APPROVED_STATUSES)
        receipt = rights_receipt(
            "noaa_pmel_erddap", dataset_version="AIS2024_AIS",
            purpose="research", register_path=self.path,
        )
        self.assertEqual(receipt["evaluation"], "invalid_registry")
        self.assertEqual(receipt["rights_status"], PENDING)

    def test_case_and_whitespace_variants_do_not_grant(self):
        self.write()
        approved = "reviewed_public_domain_attribution_required"
        self.assertEqual(self.status(), approved)
        for value in (
            "Reviewed_Public_Domain_Attribution_Required",
            "REVIEWED_PUBLIC_DOMAIN_ATTRIBUTION_REQUIRED",
            " reviewed_public_domain_attribution_required",
            "reviewed_public_domain_attribution_required ",
            "reviewed_permitted_with_conditions ",
            "review_required",
            "use_restricted",
            "APPROVED",
        ):
            copy = deepcopy(self.data)
            copy["sources"][0]["rights_status"] = value
            self.write(copy)
            with self.assertRaisesRegex(ValueError, "schema"):
                load_registry(self.path)
            self.assertEqual(self.status(), PENDING, value)
            self.assertNotIn(self.status(), APPROVED_STATUSES)
        for purpose in (
            "Research", "RESEARCH", " research", "research ",
            "public_aggregates ", "Commercial", "research\n",
        ):
            with self.assertRaisesRegex(ValueError, "Unsupported use"):
                self.status(purpose)

    def test_whitespace_only_evidence_does_not_grant(self):
        for key in (
            "reviewed_by", "attribution", "evidence_url", "terms_url",
            "terms_sha256", "reviewed_at_utc",
        ):
            copy = deepcopy(self.data)
            copy["sources"][0][key] = "   "
            self.write(copy)
            with self.assertRaisesRegex(ValueError, "schema"):
                load_registry(self.path)
            self.assertEqual(self.status(), PENDING, key)
            self.assertNotIn(self.status(), APPROVED_STATUSES)
        copy = deepcopy(self.data)
        copy["sources"][0]["reviewed_by"] = "\t\n"
        copy["sources"][0]["attribution"] = " \t "
        self.write(copy)
        with self.assertRaisesRegex(ValueError, "schema"):
            load_registry(self.path)
        self.assertEqual(self.status(), PENDING)

    def test_trailing_whitespace_and_non_ascii_urls_do_not_grant(self):
        self.write()
        self.assertEqual(
            self.status(), "reviewed_public_domain_attribution_required"
        )
        rejected = (
            "https://example.org/terms ",
            "https://example.org/terms\t",
            "https://example.org/terms\n",
            " HTTPS://example.org/terms",
            "HTTPS://example.org/terms",
            "https://[2001:db8::1]/terms",
            "https://exämple.org/terms",
            "https://user@example.org/terms",
            "https://example.org.",
        )
        for url in rejected:
            self.assertFalse(_is_https_url(url), url)
            for key in ("terms_url", "evidence_url", "source_url"):
                copy = deepcopy(self.data)
                copy["sources"][0][key] = url
                self.write(copy)
                with self.assertRaisesRegex(ValueError, "schema"):
                    load_registry(self.path)
                self.assertEqual(self.status(), PENDING, (key, url))
                self.assertNotIn(self.status(), APPROVED_STATUSES)
        punycode = "https://xn--exmple-cua.org/terms"
        self.assertTrue(_is_https_url(punycode))
        copy = deepcopy(self.data)
        copy["sources"][0]["terms_url"] = punycode
        copy["sources"][0]["evidence_url"] = "https://xn--exmple-cua.org/review"
        self.write(copy)
        load_registry(self.path)
        self.assertEqual(
            self.status(), "reviewed_public_domain_attribution_required"
        )

    def test_reviewed_at_must_be_a_real_utc_timestamp(self):
        self.write()
        shape_rejected = (
            "not-a-dateZ",
            "Z",
            "2026-11-09Z",
            "2026-11-09T12:00:00Z ",
            "2026-11-09T12:00:00Z\n",
            "2026-11-09t12:00:00Z",
            "2026-11-09 12:00:00Z",
            "2026-11-09T12:00:00.1234567Z",
            "2026-11-09T12:00:00z",
            "2026-11-09T12:00:00+01:00",
            "2026-11-09T12:00:00-00:00",
            "2026-11-09T12:00:00+00:00:00",
            "２０２６-11-09T12:00:00Z",
            "2026-11-09T12:00:00.\u0661Z",
        )
        for value in shape_rejected:
            self.assertFalse(_valid_utc_time(value), value)
            copy = deepcopy(self.data)
            copy["sources"][0]["reviewed_at_utc"] = value
            self.write(copy)
            with self.assertRaisesRegex(ValueError, "schema"):
                load_registry(self.path)
            self.assertEqual(self.status(), PENDING, value)
            self.assertNotIn(self.status(), APPROVED_STATUSES)
        # The schema pattern is a shape. These match it and are still denied
        # because datetime() rejects the calendar fields. Hour 24 and a
        # non-leap 29 February are in that set. Leap day 2024 is not.
        for value in (
            "2026-02-31T12:00:00Z",
            "2026-02-29T12:00:00Z",
            "2026-02-29T12:00:00+00:00",
            "2026-11-09T24:00:00Z",
            "2026-11-09T24:00:00+00:00",
            "2026-11-09T25:00:00Z",
            "2026-11-09T12:60:00Z",
            "2026-11-09T12:00:60Z",
        ):
            self.assertFalse(_valid_utc_time(value), value)
            copy = deepcopy(self.data)
            copy["sources"][0]["reviewed_at_utc"] = value
            self.write(copy)
            load_registry(self.path)
            self.assertEqual(self.status(), PENDING, value)
            self.assertNotIn(self.status(), APPROVED_STATUSES)
        # Accepted fractions are none, or 1 to 6 ASCII digits, with Z or
        # +00:00. The fields are parsed directly, so 1 digit and 3 digits
        # grant on Python 3.10 and 3.12.
        for value in (
            "2026-11-09T12:00:00Z",
            "2026-11-09T12:00:00+00:00",
            "2026-11-09T12:00:00.1Z",
            "2026-11-09T12:00:00.1+00:00",
            "2026-11-09T12:00:00.123Z",
            "2026-11-09T12:00:00.123+00:00",
            "2026-11-09T12:00:00.123456Z",
            "2026-11-09T12:00:00.123456+00:00",
            "2024-02-29T00:00:00Z",
            "2024-02-29T23:59:59+00:00",
        ):
            self.assertTrue(_valid_utc_time(value), value)
            copy = deepcopy(self.data)
            copy["sources"][0]["reviewed_at_utc"] = value
            self.write(copy)
            load_registry(self.path)
            self.assertEqual(
                self.status(), "reviewed_public_domain_attribution_required", value
            )
        import inspect
        from harborlens import rights as rights_mod
        self.assertNotIn("fromisoformat", inspect.getsource(rights_mod._valid_utc_time))


if __name__ == "__main__":
    unittest.main()
