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
    PENDING, RESTRICTED, _MISSING_JSONSCHEMA, _is_https_url, load_registry,
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
        self.assertTrue(registry["sources"])
        for source in registry["sources"]:
            for purpose in ("research", "public_aggregates", "commercial"):
                status = rights_status_for(
                    source["source_id"], dataset_version=source["dataset_version"],
                    purpose=purpose, register_path=path,
                )
                self.assertEqual(status, PENDING, (source["source_id"], purpose))

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


if __name__ == "__main__":
    unittest.main()
