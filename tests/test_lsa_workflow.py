"""Offline checks for the manual GovInfo LSA workflow (SPEC-004, NFR-006).

The tests read workflow text. They do not download a PDF or call pip.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

from harborlens.lsa_compare import (
    MAX_PDF_PAGE_DICTIONARY_ENTRIES,
    MAX_PDF_PAGES,
    PINNED_LSA_PDFS,
)

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
HASH_LINE = re.compile(r"^    --hash=sha256:[0-9a-f]{64}(?: \\)?$")
PYPDF_7_1_1_HASHES = (
    "04c5680d4b4cfa04ab505b09393fc949860c34a4dad6565284d11a2f5c3ce8b1",
    "2eff4e2fc5fb22a6d6711e6f1166cdc9ab5765d90cd0d77dfea3f4aa91a27b1d",
)
PYPDF_REQUIREMENT_LINES = (
    "--require-hashes",
    "pypdf==7.1.1 \\",
    "    --hash=sha256:04c5680d4b4cfa04ab505b09393fc949860c34a4dad6565284d11a2f5c3ce8b1 \\",
    "    --hash=sha256:2eff4e2fc5fb22a6d6711e6f1166cdc9ab5765d90cd0d77dfea3f4aa91a27b1d",
)
CHECKOUT_SHA = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
SETUP_PYTHON_SHA = "actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0"
CHECKOUT_LINE = f"- uses: {CHECKOUT_SHA} # v7.0.1"
SETUP_PYTHON_LINE = f"- uses: {SETUP_PYTHON_SHA} # v7.1.0"
PYTHON_312_ONLY = "valid only for Python 3.12"
PAGE_TREE_LIMITS = (
    "with apply_configuration("
    f"page_tree_maximum_entries={MAX_PDF_PAGES}, "
    f"page_tree_maximum_page_entries={MAX_PDF_PAGE_DICTIONARY_ENTRIES}):"
)
WORKFLOWS = ROOT / ".github" / "workflows"


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


def active_requirement_lines(text: str) -> list[str]:
    return [
        line
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def python_312_lock_is_explicit(workflow: str, requirements: str) -> bool:
    """The lock is documented as Python 3.12-only and the job pins that minor version."""
    if PYTHON_312_ONLY not in workflow or PYTHON_312_ONLY not in requirements:
        return False
    versions = re.findall(r"python-version:\s*(\S+)", workflow)
    return versions == ["'3.12'"]


def permission_lines(text: str) -> list[str] | None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line != "permissions:":
            continue
        block = []
        for nxt in lines[index + 1:]:
            if nxt.startswith("  "):
                block.append(nxt)
            elif nxt == "":
                continue
            else:
                break
        return block
    return None


def reader_construction_is_limited(text: str) -> bool:
    """``PdfReader`` is reached only through ``inspect`` inside the page-tree limits."""
    if text.count("PdfReader(") != 1 or PAGE_TREE_LIMITS not in text:
        return False
    inspect_at = text.find("def inspect(")
    reader_at = text.find("PdfReader(")
    limit_at = text.find(PAGE_TREE_LIMITS)
    if min(inspect_at, reader_at, limit_at) < 0:
        return False
    if not (inspect_at < reader_at < limit_at):
        return False
    window = text[limit_at:limit_at + 180]
    return "inspect(" in window and "page_tree_maximum_entries=298" not in text and (
        "page_tree_maximum_entries=300" not in text
    )


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
        active_lines = active_requirement_lines(requirements)
        self.assertEqual(active_lines, list(PYPDF_REQUIREMENT_LINES))
        hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", requirements)
        self.assertEqual(hashes, list(PYPDF_7_1_1_HASHES))
        for line in active_lines:
            if line.lstrip().startswith("--hash="):
                self.assertRegex(line, HASH_LINE)
        self.assertNotIn(">=", "\n".join(active_lines))
        self.assertNotIn("pypdf>", "\n".join(active_lines))

    def test_requirement_hashes_reject_other_values_and_shapes(self):
        other = list(PYPDF_REQUIREMENT_LINES)
        other[2] = "    --hash=sha256:" + ("ab" * 32) + " \\"
        self.assertNotEqual(other, list(PYPDF_REQUIREMENT_LINES))
        self.assertEqual(len(other[2].split("sha256:", 1)[1].split()[0]), 64)
        short = "    --hash=sha256:" + ("a" * 63)
        long = "    --hash=sha256:" + ("a" * 65)
        upper = "    --hash=sha256:" + ("A" * 64)
        sha512 = "    --hash=sha512:" + ("a" * 64)
        for line in (short, long, upper, sha512):
            self.assertIsNone(HASH_LINE.fullmatch(line), line)
        self.assertIsNotNone(HASH_LINE.fullmatch(PYPDF_REQUIREMENT_LINES[2]))
        self.assertIsNotNone(HASH_LINE.fullmatch(PYPDF_REQUIREMENT_LINES[3]))

    def test_lock_file_is_valid_only_for_python_312(self):
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertTrue(python_312_lock_is_explicit(self.text, requirements))
        self.assertIn("typing_extensions", requirements)
        self.assertIn('python_version < "3.11"', requirements)
        self.assertIn("Require Python 3.12 for the hashed pypdf lock", self.text)
        resolved_only = "# Resolved on Python 3.12.3 from PyPI for pypdf==7.1.1\n"
        self.assertFalse(python_312_lock_is_explicit(self.text, resolved_only))
        for other in ("'3.10'", "'3.11'", "'3.12.0'", "'3.13'", '"3.12"'):
            drifted = self.text.replace("python-version: '3.12'", f"python-version: {other}", 1)
            self.assertFalse(python_312_lock_is_explicit(drifted, requirements), other)
        doubled = self.text.replace(
            "python-version: '3.12'",
            "python-version: '3.12'\n          python-version: '3.10'",
            1,
        )
        self.assertFalse(python_312_lock_is_explicit(doubled, requirements))

    def test_pdf_reader_uses_the_page_tree_limits(self):
        self.assertEqual(MAX_PDF_PAGES, 299)
        self.assertEqual(MAX_PDF_PAGE_DICTIONARY_ENTRIES, 1024)
        self.assertTrue(reader_construction_is_limited(self.text))
        self.assertIn(PAGE_TREE_LIMITS, self.text)
        bare = (
            "def inspect(raw, url):\n"
            "    document=PdfReader(io.BytesIO(raw),strict=True)\n"
            "    return {}\n"
        )
        self.assertFalse(reader_construction_is_limited(bare))
        for replacement in ("=298", "=300"):
            drifted = self.text.replace(
                f"page_tree_maximum_entries={MAX_PDF_PAGES}",
                f"page_tree_maximum_entries{replacement}",
                1,
            )
            self.assertFalse(reader_construction_is_limited(drifted), replacement)
        for replacement in ("=1023", "=1025"):
            drifted = self.text.replace(
                f"page_tree_maximum_page_entries={MAX_PDF_PAGE_DICTIONARY_ENTRIES}",
                f"page_tree_maximum_page_entries{replacement}",
                1,
            )
            self.assertFalse(reader_construction_is_limited(drifted), replacement)

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


class AllWorkflowPinTests(unittest.TestCase):
    def test_every_workflow_matches_the_lsa_pin_and_read_permission(self):
        paths = sorted(WORKFLOWS.glob("*.yml"))
        names = [path.name for path in paths]
        self.assertIn("govinfo-lsa-2023-title33.yml", names)
        self.assertIn("ci.yml", names)
        self.assertGreaterEqual(len(paths), 2)
        for path in paths:
            text = path.read_text(encoding="utf-8")
            self.assertEqual(uses_refs(text), [CHECKOUT_SHA, SETUP_PYTHON_SHA], path.name)
            self.assertIn(CHECKOUT_LINE, text, path.name)
            self.assertIn(SETUP_PYTHON_LINE, text, path.name)
            for ref in uses_refs(text):
                self.assertRegex(ref, ACTION_REF, path.name)
            self.assertEqual(permission_lines(text), ["  contents: read"], path.name)
            self.assertNotIn("contents: write", text, path.name)
            self.assertIsNone(re.search(r"@[vV]\d+", text), path.name)

    def test_extra_permission_and_wrong_sha_are_rejected(self):
        pinned = (
            "permissions:\n"
            "  contents: read\n"
            "jobs:\n"
            "  test:\n"
            "    steps:\n"
            f"      {CHECKOUT_LINE}\n"
            f"      {SETUP_PYTHON_LINE}\n"
        )
        self.assertEqual(permission_lines(pinned), ["  contents: read"])
        self.assertEqual(uses_refs(pinned), [CHECKOUT_SHA, SETUP_PYTHON_SHA])
        write = pinned.replace("  contents: read", "  contents: write", 1)
        self.assertNotEqual(permission_lines(write), ["  contents: read"])
        extra = pinned.replace(
            "  contents: read\n",
            "  contents: read\n  pull-requests: write\n",
            1,
        )
        self.assertEqual(
            permission_lines(extra),
            ["  contents: read", "  pull-requests: write"],
        )
        self.assertIsNone(permission_lines("jobs:\n  test:\n"))
        wrong = "actions/checkout@" + ("a" * 40)
        self.assertRegex(wrong, ACTION_REF)
        self.assertNotEqual(wrong, CHECKOUT_SHA)
        self.assertIsNone(ACTION_REF.fullmatch("actions/checkout@" + ("a" * 39)))
        self.assertIsNone(ACTION_REF.fullmatch("actions/checkout@" + ("a" * 41)))
        self.assertIsNone(ACTION_REF.fullmatch("actions/checkout@" + ("A" * 40)))


if __name__ == "__main__":
    unittest.main()
