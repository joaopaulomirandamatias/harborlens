"""Output contracts and run identity (SPEC-003, issue #41). Synthetic AIS only."""
import json
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft202012Validator, FormatChecker

import harborlens
import harborlens.multiday as multiday
import harborlens.provenance as provenance
from harborlens.ais import read_candidates_csv, run
from harborlens.provenance import code_version

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "schemas" / "v1"
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic_ais.csv"


def validator(name):
    schema = json.loads((SCHEMAS / name).read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_real_cli_exports_validate_against_published_schemas(self):
        manifest = run(FIXTURE, self.root / "out")
        validator("run-manifest.schema.json").validate(manifest)
        records = read_candidates_csv(self.root / "out" / "stationary_candidates.csv")
        self.assertEqual(len(records), 1)
        for record in records:
            validator("stationary-candidate.schema.json").validate(record)
        geo = json.loads((self.root / "out" / "stationary_candidates.geojson").read_text())
        for feature in geo["features"]:
            validator("stationary-candidate-feature.schema.json").validate(feature)

    def test_package_version_is_part_of_run_identity(self):
        first = run(FIXTURE, self.root / "a")
        with mock.patch.object(provenance, "__version__", "9.9.9"):
            second = run(FIXTURE, self.root / "b")
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(first["code_version"]["package_version"], harborlens.__version__)

    def test_multiday_run_id_includes_package_version(self):
        a, b = self.root / "d1.csv", self.root / "d2.csv"
        lines = FIXTURE.read_text().splitlines()
        a.write_text("\n".join(lines[:30]) + "\n")
        b.write_text("\n".join([lines[0]] + lines[30:]) + "\n")
        first = multiday.run_multiday([a, b], self.root / "m1")
        with mock.patch.object(multiday, "__version__", "9.9.9"):
            second = multiday.run_multiday([a, b], self.root / "m2")
        self.assertNotEqual(first["run_id"], second["run_id"])
        validator("multi-day-run.schema.json").validate(first)

    def test_git_commit_is_metadata_not_identity(self):
        sha = "0123456789abcdef0123456789abcdef01234567"
        with mock.patch.dict(os.environ, {"HARBORLENS_GIT_COMMIT": sha}):
            self.assertEqual(code_version()["git_commit"], sha)
            tagged = run(FIXTURE, self.root / "c")
        with mock.patch.dict(os.environ, {"HARBORLENS_GIT_COMMIT": "not-a-sha", "GITHUB_SHA": ""}):
            self.assertIsNone(code_version()["git_commit"])
            untagged = run(FIXTURE, self.root / "d")
        self.assertEqual(tagged["run_id"], untagged["run_id"])

    def test_version_metadata_is_consistent(self):
        # Plain-text parsing: tomllib needs Python 3.11 and PyYAML is not a dependency.
        pyproject = (ROOT / "pyproject.toml").read_text()
        citation = (ROOT / "CITATION.cff").read_text(encoding="utf-8")

        def field(text, key, sep):
            match = re.search(rf'^{re.escape(key)}\s*{sep}\s*"?([^"\n]+)"?\s*$', text, re.M)
            return match.group(1) if match else None

        self.assertEqual(field(pyproject, "version", "="), harborlens.__version__)
        self.assertEqual(field(citation, "cff-version", ":"), "1.2.0")
        self.assertEqual(field(citation, "version", ":"), harborlens.__version__)
        self.assertEqual(field(citation, "license", ":"), field(pyproject, "license", "="))
        self.assertRegex(citation, r"(?m)^authors:\n  - given-names: ")


if __name__ == "__main__":
    unittest.main()
