"""Offline checks for the manual GovInfo LSA workflow (SPEC-004, NFR-006).

The tests read workflow text. They do not download a PDF or call pip.
"""

from __future__ import annotations

import builtins
import re
import shlex
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
GUARD_MESSAGE = "lsa-workflow.txt is valid only for Python 3.12"
EXPECTED_GUARD_RUN = (
    "python -c \"import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) "
    "else 'lsa-workflow.txt is valid only for Python 3.12')\""
)
GUARD_VERSIONS = ((3, 10), (3, 11), (3, 12), (3, 13))
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


_KEY_LINE = re.compile(r"^([A-Za-z0-9_-]+)\s*:(.*)$")
_BLOCK_MARK = re.compile(r"^([|>])([+-]?)(\d+)?$")
# Any of these keys means the step is not a guard. `if: always()` and
# `continue-on-error: false` are included on purpose: a step that can be
# skipped, or whose failure can be ignored, does not enforce the pin.
_GUARD_DISABLERS = ("if", "continue-on-error", "shell")
_SECRET_REFERENCE = re.compile(r"secrets\s*\.|GITHUB_TOKEN")


def _read_steps(lines: list[str], start: int, base: int) -> tuple[list[str], int]:
    step_column = base + 2
    end = len(lines)
    for index in range(start + 1, len(lines)):
        raw = lines[index]
        if raw.strip() == "":
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent <= base and not raw.lstrip().startswith("#"):
            end = index
            break
    block = lines[start + 1:end]
    steps: list[str] = []
    current: list[str] = []
    pending: list[str] = []
    step_start = " " * step_column + "- "
    for line in block:
        if line.startswith(step_start):
            if current:
                steps.append("".join(current))
            current = pending + [line]
            pending = []
        elif current:
            current.append(line)
        else:
            pending.append(line)
    if current:
        steps.append("".join(current))
    return steps, end


def iter_job_step_blocks(text: str) -> list[list[str]]:
    """Return one step-chunk list for every ``steps:`` block, in file order."""
    lines = text.splitlines(keepends=True)
    jobs: list[list[str]] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s+)steps:\s*$", lines[index].rstrip("\n"))
        if not match:
            index += 1
            continue
        steps, index = _read_steps(lines, index, len(match.group(1)))
        jobs.append(steps)
    return jobs


def split_job_steps(text: str) -> list[str]:
    """Return every job's step chunks, in file order."""
    steps: list[str] = []
    for job in iter_job_step_blocks(text):
        steps.extend(job)
    return steps


def join_shell_continuations(text: str) -> str:
    """Join lines that end in a backslash, the way a shell would."""
    merged: list[str] = []
    buffer = ""
    continued = False
    for line in text.split("\n"):
        piece = line.lstrip() if continued else line
        buffer = buffer + piece
        if buffer.rstrip().endswith("\\"):
            buffer = buffer.rstrip()[:-1].rstrip() + " "
            continued = True
            continue
        merged.append(buffer)
        buffer = ""
        continued = False
    if buffer:
        merged.append(buffer)
    return "\n".join(merged)


def decode_block(marker: str, raw_lines: list[str]) -> str:
    """Decode a ``|`` or ``>`` scalar, then join backslash continuations."""
    style = marker[0]
    indents = [len(line) - len(line.lstrip(" ")) for line in raw_lines if line.strip()]
    strip_at = min(indents) if indents else 0
    dedented: list[str] = []
    for line in raw_lines:
        if line.strip() == "":
            dedented.append("")
        elif len(line) >= strip_at:
            dedented.append(line[strip_at:])
        else:
            dedented.append(line.lstrip(" "))
    text = join_shell_continuations("\n".join(dedented))
    if style == ">":
        text = re.sub(r"[ \t]*\n[ \t]*", " ", text).strip()
    return text


def parse_step_keys(chunk: str) -> dict[str, str]:
    """Return the step's own keys. Folded and literal ``run`` values are decoded."""
    lines = chunk.splitlines()
    if not lines:
        return {}
    dashed = re.match(r"^(\s*)-\s+(.*)$", lines[0])
    if not dashed:
        return {}
    key_indent = len(dashed.group(1)) + 2
    logical: list[tuple[int | None, str]] = [(key_indent, dashed.group(2))]
    for line in lines[1:]:
        if line.strip() == "":
            logical.append((None, ""))
        else:
            logical.append((len(line) - len(line.lstrip(" ")), line))
    keys: dict[str, str] = {}
    index = 0
    while index < len(logical):
        indent, raw = logical[index]
        if indent != key_indent:
            index += 1
            continue
        matched = _KEY_LINE.match(raw.strip())
        if not matched:
            index += 1
            continue
        key = matched.group(1)
        rest = matched.group(2).strip()
        index += 1
        block: list[str] = []
        if rest == "" or _BLOCK_MARK.match(rest):
            while index < len(logical):
                nxt_indent, nxt_raw = logical[index]
                if nxt_indent is None or nxt_indent > key_indent:
                    block.append(nxt_raw)
                    index += 1
                    continue
                break
        if _BLOCK_MARK.match(rest):
            keys[key] = decode_block(rest, block)
        elif rest == "":
            keys[key] = "\n".join(block)
        else:
            keys[key] = rest
    return keys


def step_scalar(chunk: str, key: str) -> str | None:
    """Return one step key, including a decoded block or folded scalar."""
    return parse_step_keys(chunk).get(key)


def step_runs_pip(chunk: str) -> bool:
    run = step_scalar(chunk, "run") or ""
    return bool(re.search(r"(^|[^\w])pip([^\w]|$)", run))


def workflow_references_a_secret(text: str) -> bool:
    """True when the workflow text names ``secrets.*`` or ``GITHUB_TOKEN``."""
    return _SECRET_REFERENCE.search(text) is not None


def pypdf_7_1_1_hashes_are_bound(text: str) -> bool:
    """The active pin is ``pypdf==7.1.1`` and those two hashes belong to it.

    A comment that still says ``pypdf==7.1.1`` does not count. Changing the
    requirement line to another version and leaving the hashes in place fails.
    """
    active = active_requirement_lines(text)
    if active != list(PYPDF_REQUIREMENT_LINES):
        return False
    version_lines = [line for line in active if line.lstrip().startswith("pypdf==")]
    if version_lines != ["pypdf==7.1.1 \\"]:
        return False
    hashes = re.findall(r"--hash=sha256:([0-9a-f]{64})", "\n".join(active))
    return hashes == list(PYPDF_7_1_1_HASHES)


def guard_step_is_enforcing(chunk: str) -> bool:
    """A guard counts only when its command is exact and the step cannot skip it.

    Rejecting every ``if:`` and every ``continue-on-error:`` key is
    intentional, including ``if: always()`` and ``continue-on-error: false``.
    """
    keys = parse_step_keys(chunk)
    if any(key in keys for key in _GUARD_DISABLERS):
        return False
    run = keys.get("run")
    if run != EXPECTED_GUARD_RUN:
        return False
    code = python_c_source(run)
    return bool(code and guard_accepts_only_python_312(code))


def python_c_source(run: str) -> str | None:
    try:
        parts = shlex.split(run.strip())
    except ValueError:
        return None
    if len(parts) == 3 and parts[0] in {"python", "python3"} and parts[1] == "-c":
        return parts[2]
    return None


def execute_guard(code: str, version: tuple[int, int]) -> object:
    """Run the extracted ``python -c`` source with a fake ``sys.version_info``.

    Returns the ``SystemExit`` code, or ``None`` when the source returns.
    """
    fake_version = version + (0, "final", 0)

    class _FakeSys:
        version_info = fake_version

    fake_sys = _FakeSys()
    real_import = builtins.__import__

    def hooked(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "sys" and level == 0:
            return fake_sys
        return real_import(name, globals, locals, fromlist, level)

    builtins.__import__ = hooked
    try:
        try:
            exec(compile(code, "<workflow-guard>", "exec"), {"__name__": "__main__"})
        except SystemExit as exc:
            return exc.code
        return None
    finally:
        builtins.__import__ = real_import


def guard_accepts_only_python_312(code: str) -> bool:
    if "version_info" not in code:
        return False
    results = {version: execute_guard(code, version) for version in GUARD_VERSIONS}
    if results[(3, 12)] != 0:
        return False
    for version in ((3, 10), (3, 11), (3, 13)):
        outcome = results[version]
        if outcome == 0 or outcome is None:
            return False
        if not isinstance(outcome, str) or GUARD_MESSAGE not in outcome:
            return False
    return True


def python_312_guard_before_pip(text: str) -> bool:
    """Every job that runs pip has an unmodified 3.12 guard before that pip step."""
    saw_pip = False
    for steps in iter_job_step_blocks(text):
        pip_indexes = [index for index, step in enumerate(steps) if step_runs_pip(step)]
        if not pip_indexes:
            continue
        saw_pip = True
        if not any(guard_step_is_enforcing(step) for step in steps[:pip_indexes[0]]):
            return False
    return saw_pip


def permissions_are_contents_read_only(text: str) -> bool:
    """Permissions stay ``contents: read``. ``pull_request_target`` and ``workflow_run`` are rejected."""
    if re.search(r"(?m)^[ \t]*pull_request_target\s*:", text):
        return False
    if re.search(r"(?m)^[ \t]*workflow_run\s*:", text):
        return False
    if "write-all" in text:
        return False
    blocks: list[str] = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        match = re.match(r"^([ \t]*)permissions\s*:(.*)$", lines[index])
        if not match:
            index += 1
            continue
        indent = len(match.group(1))
        inline = match.group(2).strip()
        if inline:
            blocks.append(inline)
            index += 1
            continue
        body: list[str] = []
        index += 1
        while index < len(lines):
            nxt = lines[index]
            if nxt.strip() == "":
                index += 1
                continue
            nxt_indent = len(nxt) - len(nxt.lstrip(" "))
            if nxt_indent <= indent:
                break
            body.append(nxt.strip())
            index += 1
        blocks.append("\n".join(body))
    return blocks == ["contents: read"]


def checkout_drops_credentials(text: str) -> bool:
    steps = split_job_steps(text)
    checkouts = [step for step in steps if "actions/checkout@" in step]
    if len(checkouts) != 1:
        return False
    return bool(re.search(r"(?m)^\s*persist-credentials:\s*false\s*$", checkouts[0]))


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
        self.assertTrue(pypdf_7_1_1_hashes_are_bound(requirements))
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
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertTrue(pypdf_7_1_1_hashes_are_bound(requirements))
        bumped = requirements.replace("pypdf==7.1.1 \\", "pypdf==7.1.2 \\", 1)
        self.assertIn("pypdf==7.1.1", bumped)
        self.assertNotIn("pypdf==7.1.2 \\", requirements)
        self.assertFalse(pypdf_7_1_1_hashes_are_bound(bumped))
        flipped = requirements.replace(PYPDF_7_1_1_HASHES[0], "ab" * 32, 1)
        self.assertIn("pypdf==7.1.1 \\", flipped)
        self.assertFalse(pypdf_7_1_1_hashes_are_bound(flipped))

    def test_lock_file_is_valid_only_for_python_312(self):
        requirements = REQUIREMENTS.read_text(encoding="utf-8")
        self.assertTrue(python_312_lock_is_explicit(self.text, requirements))
        self.assertIn("typing_extensions", requirements)
        self.assertIn('python_version < "3.11"', requirements)
        self.assertTrue(python_312_guard_before_pip(self.text))
        guard = next(
            step for step in split_job_steps(self.text)
            if step_scalar(step, "run") == EXPECTED_GUARD_RUN
        )
        pip_steps = [step for step in split_job_steps(self.text) if step_runs_pip(step)]
        self.assertEqual(step_scalar(guard, "run"), EXPECTED_GUARD_RUN)
        self.assertLess(
            split_job_steps(self.text).index(guard),
            split_job_steps(self.text).index(pip_steps[0]),
        )
        code = python_c_source(EXPECTED_GUARD_RUN)
        self.assertIsNotNone(code)
        assert code is not None
        self.assertEqual(execute_guard(code, (3, 12)), 0)
        for version in ((3, 10), (3, 11), (3, 13)):
            outcome = execute_guard(code, version)
            self.assertIsInstance(outcome, str, version)
            self.assertIn(GUARD_MESSAGE, outcome)
            self.assertNotEqual(outcome, 0)
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

    def test_python_312_guard_rejects_the_qa_mutations(self):
        steps = split_job_steps(self.text)
        guard_at = next(
            index for index, step in enumerate(steps)
            if step_scalar(step, "run") == EXPECTED_GUARD_RUN
        )
        pip_at = next(index for index, step in enumerate(steps) if step_runs_pip(step))
        self.assertLess(guard_at, pip_at)

        def render(order: list[str]) -> str:
            # Rebuild only the steps block by swapping chunks inside the original text.
            original = "".join(steps)
            return self.text.replace(original, "".join(order), 1)

        moved = steps[:]
        moved[guard_at], moved[pip_at] = moved[pip_at], moved[guard_at]
        self.assertFalse(python_312_guard_before_pip(render(moved)))

        def replace_run(new_run: str) -> str:
            old = step_scalar(steps[guard_at], "run")
            assert old is not None
            return self.text.replace(old, new_run, 1)

        self.assertFalse(python_312_guard_before_pip(replace_run("pass")))
        self.assertFalse(python_312_guard_before_pip(replace_run("true")))
        self.assertFalse(python_312_guard_before_pip(replace_run(
            EXPECTED_GUARD_RUN.replace("== (3, 12)", "== (3, 13)")
        )))
        self.assertFalse(python_312_guard_before_pip(replace_run(
            EXPECTED_GUARD_RUN.replace("== (3, 12)", ">= (3, 12)")
        )))
        self.assertFalse(python_312_guard_before_pip(replace_run(
            "python -c \"import sys; raise SystemExit(1)\""
        )))

    def test_guard_step_rejects_skip_and_custom_shell(self):
        steps = split_job_steps(self.text)
        guard = next(step for step in steps if step_scalar(step, "run") == EXPECTED_GUARD_RUN)
        keys = parse_step_keys(guard)
        self.assertNotIn("if", keys)
        self.assertNotIn("continue-on-error", keys)
        self.assertNotIn("shell", keys)
        self.assertTrue(guard_step_is_enforcing(guard))

        def with_key(line: str) -> str:
            addition = "        " + line + "\n"
            updated = guard if guard.endswith("\n") else guard + "\n"
            return self.text.replace(guard, updated + addition, 1)

        self.assertFalse(python_312_guard_before_pip(with_key("continue-on-error: true")))
        self.assertFalse(python_312_guard_before_pip(with_key("if: false")))
        self.assertFalse(python_312_guard_before_pip(with_key("if: ${{ false }}")))
        self.assertFalse(python_312_guard_before_pip(
            with_key('shell: bash --noprofile --norc -c "true"')
        ))
        self.assertFalse(python_312_guard_before_pip(
            with_key("shell: bash --noprofile --norc {0} || true")
        ))

    def test_folded_pip_and_a_second_job_fail_the_guard(self):
        folded = (
            "      - name: Early unguarded pip\n"
            "        run: |\n"
            "          python -m pip \\\n"
            "            install pypdf\n"
        )
        folded_flow = (
            "      - name: Early unguarded pip\n"
            "        run: >\n"
            "          python -m pip \\\n"
            "            install pypdf\n"
        )
        self.assertTrue(step_runs_pip(folded))
        self.assertTrue(step_runs_pip(folded_flow))
        self.assertNotIn("pip install", folded)
        guard_header = "      - name: Require Python 3.12 for the hashed pypdf lock\n"
        self.assertFalse(python_312_guard_before_pip(self.text.replace(guard_header, folded + guard_header, 1)))
        self.assertFalse(python_312_guard_before_pip(self.text.replace(guard_header, folded_flow + guard_header, 1)))
        second_job = (
            "\n"
            "  other:\n"
            "    runs-on: ubuntu-latest\n"
            "    steps:\n"
            "      - name: Unguarded install\n"
            "        run: |\n"
            "          python -m pip \\\n"
            "            install pypdf\n"
        )
        self.assertFalse(python_312_guard_before_pip(self.text.rstrip() + second_job))
        self.assertEqual(len(iter_job_step_blocks(self.text.rstrip() + second_job)), 2)

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
    def test_ci_matrix_includes_python_3_10_3_12_and_3_14(self):
        ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        self.assertIn("python-version: ['3.10', '3.12', '3.14']", ci)

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
            self.assertTrue(permissions_are_contents_read_only(text), path.name)
            self.assertTrue(checkout_drops_credentials(text), path.name)
            self.assertNotIn("contents: write", text, path.name)
            self.assertNotIn("write-all", text, path.name)
            self.assertNotIn("pull_request_target", text, path.name)
            self.assertNotIn("workflow_run", text, path.name)
            self.assertFalse(workflow_references_a_secret(text), path.name)
            self.assertIsNone(re.search(r"@[vV]\d+", text), path.name)

    def test_secrets_and_github_token_are_rejected(self):
        ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        lsa = WORKFLOW.read_text(encoding="utf-8")
        self.assertFalse(workflow_references_a_secret(ci))
        self.assertFalse(workflow_references_a_secret(lsa))
        self.assertFalse(workflow_references_a_secret("permissions:\n  contents: read\n"))
        secret = ci.replace(
            "permissions:\n  contents: read\n",
            "permissions:\n  contents: read\n\nenv:\n  TOKEN: ${{ secrets.FOO }}\n",
            1,
        )
        self.assertTrue(workflow_references_a_secret(secret))
        self.assertTrue(workflow_references_a_secret("TOKEN: ${{ secrets.GITHUB_TOKEN }}\n"))
        self.assertTrue(workflow_references_a_secret("env:\n  GH_TOKEN: ${GITHUB_TOKEN}\n"))
        self.assertTrue(workflow_references_a_secret(lsa + "\n  TOKEN: ${{ secrets.BAR }}\n"))

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
        self.assertTrue(permissions_are_contents_read_only(pinned))
        self.assertFalse(permissions_are_contents_read_only(write))
        self.assertFalse(permissions_are_contents_read_only(extra))
        job_write = pinned.replace(
            "  test:\n",
            "  test:\n    permissions: write-all\n",
            1,
        )
        self.assertFalse(permissions_are_contents_read_only(job_write))
        targeted = "on:\n  pull_request_target:\n" + pinned
        self.assertFalse(permissions_are_contents_read_only(targeted))
        workflow_run = "on:\n  workflow_run:\n" + pinned
        self.assertFalse(permissions_are_contents_read_only(workflow_run))
        ci = (WORKFLOWS / "ci.yml").read_text(encoding="utf-8")
        lsa = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("pull_request:", ci)
        self.assertNotIn("workflow_run:", ci)
        self.assertNotIn("workflow_run:", lsa)
        self.assertTrue(permissions_are_contents_read_only(ci))
        self.assertTrue(permissions_are_contents_read_only(lsa))
        self.assertFalse(permissions_are_contents_read_only(
            ci.replace("  pull_request:\n", "  pull_request:\n  workflow_run:\n", 1)
        ))
        self.assertFalse(permissions_are_contents_read_only(
            lsa.replace("  workflow_dispatch:\n", "  workflow_dispatch:\n  workflow_run:\n", 1)
        ))
        dropped = pinned.replace(
            f"      {CHECKOUT_LINE}\n",
            f"      {CHECKOUT_LINE}\n        with:\n          persist-credentials: false\n",
            1,
        )
        self.assertTrue(checkout_drops_credentials(dropped))
        self.assertFalse(checkout_drops_credentials(pinned))


if __name__ == "__main__":
    unittest.main()
