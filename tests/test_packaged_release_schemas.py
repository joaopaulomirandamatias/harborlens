"""Release-gate schemas shipped inside the package (SPEC-003).

The loader uses ``importlib.resources`` only. A schema placed next to the
package must not replace the shipped contract. These tests do not need
``cryptography`` or ``pypdf``.
"""
from __future__ import annotations

import json
import unittest
from importlib.resources import files
from pathlib import Path
from unittest import mock

from harborlens.publication import (
    PACKAGED_RELEASE_SCHEMAS,
    read_packaged_release_schema,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "schemas" / "v1"


class PackagedReleaseSchemaTests(unittest.TestCase):
    def test_packaged_bytes_match_published_files(self):
        names = [
            path.name
            for path in files("harborlens").joinpath("schemas", "v1").iterdir()
            if path.name.endswith(".json")
        ]
        self.assertEqual(
            sorted(names),
            sorted((*PACKAGED_RELEASE_SCHEMAS, "source-rights-register.schema.json")),
        )
        for name in PACKAGED_RELEASE_SCHEMAS:
            loaded = read_packaged_release_schema(name)
            published = (PUBLISHED / name).read_text(encoding="utf-8")
            self.assertEqual(loaded, published)
            document = json.loads(loaded)
            self.assertEqual(
                document["$schema"],
                "https://json-schema.org/draft/2020-12/schema",
            )
            self.assertNotIn("berth", json.dumps(document).lower())

    def test_unknown_names_are_refused(self):
        for name in (
            "source-rights-register.schema.json",
            "govinfo-lsa-dec-jan-comparison.schema.json",
            "../source-rights-register.schema.json",
            "public-summary.schema.json/../../secrets",
            "",
            "public-summary.schema.json ",
        ):
            with self.assertRaisesRegex(ValueError, "Unknown packaged schema"):
                read_packaged_release_schema(name)

    def test_disguised_names_raise_without_touching_the_filesystem(self):
        names = (
            "/etc/passwd",
            "/tmp/public-summary.schema.json",
            "C:\\schemas\\public-summary.schema.json",
            "public-summary.schema.json\\..\\secrets",
            "%2e%2e/%2e%2e/public-summary.schema.json",
            "public-summary%2eschema%2ejson",
            "PUBLIC-SUMMARY.SCHEMA.JSON",
            "Public-Summary.schema.json",
            "public-summary.schema.json\x00",
            "public-summary.schema.json\x00.json",
            "..",
            "../public-summary.schema.json",
            "v1/../public-summary.schema.json",
            "schemas/../../public-summary.schema.json",
            "public-summary.schema.json ",
            " public-summary.schema.json",
            "public-summary.schema.json\n",
            "public-summary.schema.json\t",
        )
        with mock.patch("harborlens.publication.files") as packaged, \
                mock.patch("builtins.open") as opened:
            for name in names:
                with self.assertRaisesRegex(ValueError, "Unknown packaged schema"):
                    read_packaged_release_schema(name)
            packaged.assert_not_called()
            opened.assert_not_called()

    def test_parent_directory_schema_is_never_consulted(self):
        import harborlens.publication as publication

        foreign_dir = Path(publication.__file__).resolve().parents[1] / "schemas" / "v1"
        target = foreign_dir / "public-summary.schema.json"
        created = []
        cursor = foreign_dir
        while not cursor.exists():
            created.append(cursor)
            cursor = cursor.parent
        for directory in reversed(created):
            directory.mkdir()
        target.write_text('{"type":"object"}\n', encoding="utf-8")
        try:
            loaded = read_packaged_release_schema("public-summary.schema.json")
            self.assertNotEqual(loaded, target.read_text(encoding="utf-8"))
            self.assertIn("public-summary-v0.1", loaded)
        finally:
            if target.exists():
                target.unlink()
            for directory in created:
                try:
                    directory.rmdir()
                except OSError:
                    pass
