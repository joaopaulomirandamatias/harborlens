"""Offline checks for the manual GovInfo LSA workflow (SPEC-004, NFR-006).

The tests read workflow text. They do not download a PDF or call pip.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from harborlens.lsa_compare import PINNED_LSA_PDFS

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "govinfo-lsa-2023-title33.yml"
REQUIREMENTS = ROOT / ".github" / "requirements" / "lsa-workflow.txt"
CHANGELOG = ROOT / "CHANGELOG.md"
COMPARISON = ROOT / "docs" / "data" / "govinfo-lsa-dec-jan-comparison.md"
DESIGN = ROOT / "specs" / "004-validated-zones" / "design.md"
THREAT_MODEL = ROOT / "docs" / "security" / "threat-model.md"
TRACEABILITY = ROOT / "docs" / "requirements" / "traceability.md"
SMOKE = ROOT / "docs" / "data" / "govinfo-lsa-2023-title33-source-smoke.md"

DECEMBER_PDF_SHA256 = "c226121a7617f1b4578a0fcf79f58d4735696e0405c5522615699bdb5bab037d"
PYPDF_7_1_1_ADVISORIES = (
    "GHSA-5chg-c4f3-fw2p",
    "GHSA-7f8r-xhw3-553h",
    "GHSA-cqpq-3wwr-f5p2",
    "GHSA-j9r2-rv26-5qv2",
    "GHSA-p3v2-r3fx-qpm6",
)
ACTION_REF = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+@[0-9a-f]{40}$")
STEP_START = re.compile(r"^ +- (?:name:|uses:)")


def uses_refs(text: str) -> list[str]:
    """Return each ``uses:`` value with a trailing ``# version`` comment removed."""
    refs = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("- uses:") or stripped.startswith("uses:"):
            value = stripped.split(":", 1)[1].strip()
            value = value.split("#", 1)[0].strip()
            refs.append(value)
    return refs


def named_steps(text: str) -> list[tuple[str, str]]:
    """Return ``(name, body)`` for steps that declare ``name:``."""
    lines = text.splitlines()
    steps: list[tuple[str, str]] = []
    name = None
    body: list[str] = []
    for line in lines:
        if STEP_START.match(line):
            if name is not None:
                steps.append((name, "\n".join(body)))
            name = None
            body = []
            stripped = line.strip()
            if stripped.startswith("- name:"):
                name = stripped.split(":", 1)[1].strip()
            continue
        if name is not None:
            body.append(line)
    if name is not None:
        steps.append((name, "\n".join(body)))
    return steps


def pip_install_lines(text: str) -> list[str]:
    return [line for line in text.splitlines() if "pip install" in line]


class LsaWorkflowPinTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")

    def test_every_uses_is_pinned_to_a_commit_sha(self):
        refs = uses_refs(self.text)
        self.assertEqual(
            refs,
            [
                "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0",
            ],
        )
        for ref in refs:
            self.assertRegex(ref, ACTION_REF)
        self.assertIn(
            "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1",
            self.text,
        )
        self.assertIn(
            "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0",
            self.text,
        )

    def test_floating_action_ref_is_rejected(self):
        floating = "jobs:\n  inspect:\n    steps:\n      - uses: actions/checkout@v7\n"
        refs = uses_refs(floating)
        self.assertEqual(refs, ["actions/checkout@v7"])
        self.assertIsNone(ACTION_REF.fullmatch(refs[0]))
        short = "actions/checkout@3d3c42e5"
        self.assertIsNone(ACTION_REF.fullmatch(short))

    def test_pip_install_uses_require_hashes(self):
        lines = pip_install_lines(self.text)
        self.assertEqual(len(lines), 1)
        self.assertIn("--require-hashes", lines[0])
        self.assertIn(".github/requirements/lsa-workflow.txt", lines[0])
        self.assertNotIn("pypdf>=", lines[0])
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertIn("--require-hashes", requirements)
        self.assertIn("pypdf==7.1.1", requirements)
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", requirements)
        self.assertEqual(len(hashes), 2)
        active = "\n".join(
            line
            for line in requirements.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        )
        self.assertNotIn(">=", active)
        self.assertNotIn("pypdf>", active)

    def test_requirements_without_require_hashes_fail_the_check(self):
        loose = "        run: python -m pip install 'pypdf>=7.1.1,<8'\n"
        lines = pip_install_lines(loose)
        self.assertTrue(lines)
        self.assertNotIn("--require-hashes", lines[0])

    def test_sha256_check_step_references_the_full_december_pin(self):
        pin = PINNED_LSA_PDFS["2023-12"]["sha256"]
        self.assertEqual(pin, DECEMBER_PDF_SHA256)
        self.assertEqual(len(pin), 64)
        smoke = SMOKE.read_text(encoding="utf-8")
        self.assertIn(pin, smoke)
        steps = dict(named_steps(self.text))
        self.assertIn("Check December 2023 LSA PDF SHA-256", steps)
        body = steps["Check December 2023 LSA PDF SHA-256"]
        self.assertIn(pin, body)
        self.assertIn("hmac.compare_digest", body)
        self.assertNotIn(pin[:8] + "'", body)
        prefix_only = "      - name: Check December 2023 LSA PDF SHA-256\n        run: echo c226121a\n"
        prefix_body = dict(named_steps(prefix_only))["Check December 2023 LSA PDF SHA-256"]
        self.assertNotIn(pin, prefix_body)

    def test_dispatch_output_and_permissions_stay(self):
        self.assertIn("workflow_dispatch:", self.text)
        self.assertNotIn("\n  push:", self.text)
        self.assertNotIn("\n  pull_request:", self.text)
        self.assertIn("python-version: '3.12'", self.text)
        self.assertRegex(self.text, r"(?m)^permissions:\n  contents: read\n")
        self.assertIn(
            "https://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf",
            self.text,
        )
        for key in (
            "official_source",
            "official_pdf_sha256",
            "pdf_pages",
            "title33_page_range_zero_based",
            "title33_extracted_text_sha256",
            "target_110_197_direct_text_occurrences",
            "title33_110_entry_samples",
            "lsa_scope",
            "full_legal_effect_review_complete",
            "legal_status_for_2024_01_02",
            "authorized_ais_joins",
        ):
            self.assertIn(key, self.text)
        self.assertIn("'legal_status_for_2024_01_02':'NOT_DETERMINED'", self.text)
        self.assertIn("'authorized_ais_joins':0", self.text)


class PypdfAdvisoryDocTests(unittest.TestCase):
    def test_named_docs_list_the_advisories_patched_in_7_1_1(self):
        unreleased = CHANGELOG.read_text(encoding="utf-8").split("## [Unreleased]", 1)[1]
        unreleased = unreleased.split("\n## ", 1)[0]
        documents = {
            "CHANGELOG.md": unreleased,
            "docs/data/govinfo-lsa-dec-jan-comparison.md": COMPARISON.read_text(encoding="utf-8"),
            "specs/004-validated-zones/design.md": DESIGN.read_text(encoding="utf-8"),
            "docs/security/threat-model.md": THREAT_MODEL.read_text(encoding="utf-8"),
            "docs/requirements/traceability.md": TRACEABILITY.read_text(encoding="utf-8"),
        }
        for name, text in documents.items():
            for advisory in PYPDF_7_1_1_ADVISORIES:
                self.assertIn(advisory, text, name)
            self.assertIn("GHSA-fhff-j4m8-439h", text, name)
            self.assertNotIn("all three repository advisories", text, name)
        self.assertIn("CWE-407", unreleased)
        self.assertIn("GHSA-cqpq-3wwr-f5p2", unreleased)


if __name__ == "__main__":
    unittest.main()
