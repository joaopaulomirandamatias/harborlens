"""Guard for synthetic vessel identifiers (SPEC-001, FR-001, FR-002, BR-008, BR-016).

Committed synthetic MMSIs use unassigned MID 199, form ``1990xxxxx``.
The guard fails when a nine-digit token's MID is in the assigned range 201-775.

The scan reads every text file ``git ls-files`` tracks, plus untracked files
that are not gitignored, so a planted negative uses the same path. Paths are
classified relative to the repository root. Before the token scan, the text
is normalized with fixed sets: U+005F between ASCII digits is removed,
``DIGIT_SPLITTERS`` (zero-width and other invisible format characters) are
removed wherever they sit, and a ``\\u`` escape of four hex digits is decoded
only when the code point is an ASCII digit, a splitter, or U+005F. A UTF-16
or UTF-32 BOM is decoded and scanned. A file that is not UTF-8 and has no
NUL is decoded as ISO-8859-1 after those splitter bytes are removed. A NUL
byte with no UTF-16 or UTF-32 BOM is skipped with reason ``nul-byte``. A
tracked file in that state fails the coverage test.

A candidate is nine digits bounded by a non-digit. A run of eight digits
does not match, because it is shorter than nine. A run of ten or more
digits does not match. Nine digits are a decimal fraction only when a digit
precedes the dot (``29.123456789``). A dot that is not part of a decimal
(``id.`` before nine digits) still matches. The MID is the first three
digits. The previous guard did not read digits 2-4 of a leading-0 or
leading-9 form, and this guard does not either.

The repository scan applies that rule to the raw text. It is not limited to
an ``mmsi`` column, a ``vessel_id`` column, or a JSON key named ``mmsi``.
A notebook and a module under ``src/`` use the same rule. Those negative
tests write the plant in a temporary directory inside the work tree, so
``git ls-files --others`` sees it, and remove the directory when the test
ends. The identifier is assembled from digit parts, so this file has no
nine-digit assigned-MID literal.

Exclusions are file-exact or context-based. Each one has a written reason.

* ``tests/fixtures/single_day_0.2.0.dev9/`` is the package 0.2.0.dev9 golden.
  It is kept as the input of the mapping proof: the proof substitutes legacy
  ids in those bytes and compares them with ``single_day_0.2.0.dev15``.
  Each of those files is excluded by its exact path. A new file in that
  directory is scanned. The directory still contains MID 367.
* ``tests/synthetic_id_map.py`` is the mapping table. Its keys are the retired
  identifiers, including one former Marshall Islands MID. The same identifiers
  anywhere else still fail the guard.
* A nine-digit run inside a hexadecimal run of exactly 64 characters is a
  SHA-256 digest, not a vessel id. That includes a run of nine digits at
  either edge of those 64 characters. A longer run excludes a nine-digit
  span only when the span is strictly inside the run. A span that starts
  or ends a longer run is an identifier glued on with no separator, and
  it still fails. A standalone token in the same file still fails.
* The value assigned by a whole-word ``mmap_size`` is ignored. In
  ``tests/multiday_memory_probe.py`` that value is a 256 MiB byte count
  (``PRAGMA mmap_size=`` or ``mmap_size =``). The character before
  ``mmap_size`` must be in ``MMAP_PREFIX``. Only U+0020 and U+0009 may
  sit around the ``=``. Only the token that starts immediately after that
  spacing is ignored. A newline does not carry the exclusion. The same
  digits anywhere else fail.
* ``tests/synthetic_id_map.py`` is excluded by exact path, and its rule
  tuple and the assigned-MID tokens in that file are pinned. A new
  assigned-MID literal there fails the pin. Every value is ``1990xxxxx``.

The byte-identity proof starts from the dev9 goldens, applies
``SYNTHETIC_ID_MAP``, then recomputes only the ID-derived fields with
``hashlib``. It does not call the pipeline. ``mmsi_category`` changes from
``ship`` to ``other`` only on rows whose identifier was mapped.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from synthetic_id_map import SYNTHETIC_ID_MAP, SYNTHETIC_ID_RULES

ROOT = Path(__file__).resolve().parents[1]
DEV9 = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev9"
DEV15 = ROOT / "tests" / "fixtures" / "single_day_0.2.0.dev15"
FR_EVIDENCE = ROOT / "docs" / "data" / "fr-2023-original-fulltext-evidence-2026-11-09.md"
MAP_SOURCE = ROOT / "tests" / "synthetic_id_map.py"

ASSIGNED_MID_LOW = 201
ASSIGNED_MID_HIGH = 775
# Nine digits, not part of a longer digit run. A decimal fraction is nine
# digits after a digit and a dot (``(?<!\d\.)``). Any other dot still matches.
TOKEN_9 = re.compile(r"(?<!\d\.)(?<!\d)(\d{9})(?!\d)")
# An f-string whose literal digit prefix selects an assigned MID has no
# nine-digit token until runtime. Covers f/F, fr/rf in either case, and
# single or triple quotes. A raw string with no f is not a match.
FSTRING_PREFIX = re.compile(
    r"""(?<![A-Za-z0-9_])(?:[fF][rR]?|[rR][fF])(?P<quote>'''|\"\"\"|['\"])(?P<prefix>\d{3,8})\{"""
)
# SHA-256 is 64 hex characters. A longer run is not this exclusion.
SHA256_HEX_LENGTH = 64
HEX_BLOB = re.compile(r"[0-9a-fA-F]{64,}")
# ASCII digits. Membership is a table lookup, not ``str.isdigit``.
ASCII_DIGITS = frozenset("0123456789")
# PEP 515 numeric separator. U+005F only. U+FF3F is not in this set.
DIGIT_UNDERSCORES = frozenset("_")
# Invisible format characters that can sit between digits. The same format
# characters ``csv_safe.IGNORABLE`` names, without its whitespace. Membership
# is a table lookup. Do not call ``unicodedata.category``.
DIGIT_SPLITTERS = frozenset(
    "\ufeff\u200b\u200c\u200d\u200e\u200f"
    "\u2060\u2061\u2062\u2063\u2064"
    "\u206a\u206b\u206c\u206d\u206e\u206f"
    "\u00ad\u180e"
    "\u061c"
    "\u202a\u202b\u202c\u202d\u202e"
    "\u2066\u2067\u2068\u2069"
)
# ``\u`` plus four hex digits is decoded only for these code points.
_ESCAPE_CODEPOINTS = ASCII_DIGITS | DIGIT_SPLITTERS | DIGIT_UNDERSCORES
UNICODE_ESCAPE = re.compile(r"\\u([0-9a-fA-F]{4})")
# Space and tab. A newline, CR, vertical tab, and form feed are not included.
MMAP_HORIZONTAL_SPACE = frozenset(" \t")
UTF32_LE_BOM = b"\xff\xfe\x00\x00"
UTF32_BE_BOM = b"\x00\x00\xfe\xff"
UTF16_LE_BOM = b"\xff\xfe"
UTF16_BE_BOM = b"\xfe\xff"
BINARY_SKIP_REASONS = frozenset({"nul-byte"})
UNDECODABLE_BOM = "undecodable-bom"
# SHA-256 of ``repr(SYNTHETIC_ID_RULES)`` and of the sorted ``text_hits`` of
# ``tests/synthetic_id_map.py``. A new rule or a new assigned-MID literal
# changes one of these. The digests are not the identifiers.
SYNTHETIC_ID_RULES_SHA256 = "4f6c26654d87b3609570f13fd21bd81e93fd48032d537a39e421b80253a83d66"
SYNTHETIC_ID_MAP_HITS_SHA256 = "cc8bf798b6833e5d9ea1cb2fd98b18ede51574d3bc4b48f9d48ec0ad7c744d8f"
SYNTHETIC_ID_MAP_SIZE = 940
SYNTHETIC_ID_MAP_HIT_COUNT = 23
FORBIDDEN_PREFIXES = ("111", "970", "972", "974", "98", "99", "0")

# Exact relative path, reason. A directory prefix is not an exclusion.
# The dev9 names are the files ``git ls-files`` lists in that directory.
EXCLUSIONS = (
    (
        "tests/fixtures/single_day_0.2.0.dev9/houston_clean.csv",
        "Historical cleaned CSV for package 0.2.0.dev9. Retained as a mapping-proof "
        "input so legacy MID 367 identifiers can be substituted and compared with "
        "tests/fixtures/single_day_0.2.0.dev15. It is not a current vessel-id source.",
    ),
    (
        "tests/fixtures/single_day_0.2.0.dev9/stationary_candidates.csv",
        "Historical candidate CSV for package 0.2.0.dev9. Retained as a mapping-proof "
        "input. Its MMSI column still contains legacy MID 367 identifiers. It is not "
        "a current vessel-id source.",
    ),
    (
        "tests/fixtures/single_day_0.2.0.dev9/stationary_candidates.geojson",
        "Historical candidate GeoJSON for package 0.2.0.dev9. Retained as a mapping-proof "
        "input. Its mmsi properties still contain legacy MID 367 identifiers. It is not "
        "a current vessel-id source.",
    ),
    (
        "tests/fixtures/single_day_0.2.0.dev9/manifest.json",
        "Historical run manifest for package 0.2.0.dev9. Retained as a mapping-proof "
        "input beside the other three golden files. It is not a current vessel-id source.",
    ),
    (
        "tests/synthetic_id_map.py",
        "Mapping table. Legacy identifiers appear only as the keys this change "
        "retires, including one former Marshall Islands MID. Every key is an "
        "assigned MID and every value is 1990xxxxx. The same legacy identifier "
        "outside this file still fails the guard. The file is excluded by its "
        "exact path so the proof can keep those keys.",
    ),
)
EXCLUSION_PATHS = {path for path, _reason in EXCLUSIONS}

# Context exclusions. These are not path allowlists. The same digits outside
# the context still fail. Each entry is (name, reason).
CONTEXT_EXCLUSIONS = (
    (
        "hex-run-64-or-longer",
        "A nine-digit run inside a hexadecimal run of exactly 64 characters "
        "is a SHA-256 digest, not a vessel identifier. Nine digits at either "
        "edge of those 64 characters stay inside the digest. A longer run "
        "excludes a nine-digit span only when that span is strictly inside "
        "the run. A span that starts or ends a longer run is an identifier "
        "glued on with no separator and still fails. A standalone nine-digit "
        "token in the same file still fails.",
    ),
    (
        "mmap-size-assignment",
        "The nine-digit value assigned by a whole-word mmap_size is a byte "
        "count. Only U+0020 and U+0009 may sit around the equals sign, and "
        "only the token that starts immediately after that spacing is "
        "ignored. A newline, CR, vertical tab, or form feed does not carry "
        "the exclusion. In tests/multiday_memory_probe.py that value is "
        "256 MiB. The same digits in not_mmap_size, earlier on the line, or "
        "in any other assignment still fail.",
    ),
)

# Files harborlens-verify hashes, and the cleaned CSV the release recount reads.
VERIFY_ARTIFACTS = (
    "houston_clean.csv",
    "stationary_candidates.csv",
    "stationary_candidates.geojson",
)
# Characters that may sit immediately before ``mmap_size`` and still open
# the exclusion. A letter, digit, underscore, or any character outside this
# set does not. The set is ASCII and does not consult the Unicode database.
MMAP_PREFIX = frozenset(
    " \t\n\r\f\v"
    "\"'`()[]{}.,:;=+-*/%&|^~<>!?#@\\"
)


def _splitter_utf8_sequences():
    """UTF-8 byte sequences of ``DIGIT_SPLITTERS``, longest first."""
    sequences = []
    for character in DIGIT_SPLITTERS:
        encoded = character.encode("utf-8")
        if len(encoded) > 1:
            sequences.append(encoded)
    sequences.sort(key=len, reverse=True)
    return tuple(sequences)


SPLITTER_UTF8 = _splitter_utf8_sequences()


def mid_is_assigned(mid):
    """True when ``mid`` is in the assigned MID block 201-775 inclusive."""
    return ASSIGNED_MID_LOW <= int(mid) <= ASSIGNED_MID_HIGH


def _assigned_nine(value):
    text = str(value).strip()
    if re.fullmatch(r"\d{9}", text) and mid_is_assigned(text[:3]):
        return text
    return None


def csv_mmsi_hits(text):
    """Nine-digit assigned-MID values in a column named MMSI.

    The repository scan does not use this helper. It calls ``text_hits`` on
    the raw file, so a ``vessel_id`` column is visible there.
    """
    hits = []
    try:
        rows = csv.reader(io.StringIO(text))
        header = next(rows, None)
    except csv.Error:
        return hits
    if not header:
        return hits
    indexes = [i for i, name in enumerate(header) if name.strip().lower() == "mmsi"]
    if not indexes:
        return hits
    for row in rows:
        for index in indexes:
            if index >= len(row):
                continue
            found = _assigned_nine(row[index])
            if found:
                hits.append(found)
    return hits


def json_mmsi_hits(text):
    """Nine-digit assigned-MID values of a key named mmsi.

    The repository scan does not use this helper. ``text_hits`` sees every
    JSON key and value.
    """
    try:
        document = json.loads(text)
    except json.JSONDecodeError:
        return []
    hits = []

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if str(key).lower() == "mmsi":
                    found = _assigned_nine(value)
                    if found:
                        hits.append(found)
                else:
                    walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(document)
    return hits


def normalize_identifier_text(text):
    """Collapse the fixed obfuscations, then return the text to scan.

    A ``\\u`` escape of four hex digits is decoded only when the code point
    is an ASCII digit, a member of ``DIGIT_SPLITTERS``, or U+005F. ``\\U``
    and ``\\x`` stay as written. Splitter characters are then removed
    wherever they sit. U+005F is removed only when both neighbors are ASCII
    digits. A consecutive underscore, U+FF3F, and a space stay in place.
    """

    def replace_escape(match):
        character = chr(int(match.group(1), 16))
        if character in _ESCAPE_CODEPOINTS:
            return character
        return match.group(0)

    text = UNICODE_ESCAPE.sub(replace_escape, text)
    if any(character in DIGIT_SPLITTERS for character in text):
        text = "".join(
            character for character in text if character not in DIGIT_SPLITTERS
        )
    if any(character in DIGIT_UNDERSCORES for character in text):
        kept = []
        size = len(text)
        for index, character in enumerate(text):
            if (
                character in DIGIT_UNDERSCORES
                and 0 < index < size - 1
                and text[index - 1] in ASCII_DIGITS
                and text[index + 1] in ASCII_DIGITS
            ):
                continue
            kept.append(character)
        text = "".join(kept)
    return text


def _mmap_assignment_ends(text):
    """Indexes of a token that starts immediately after ``mmap_size =``.

    The character before ``mmap_size`` must be absent or in ``MMAP_PREFIX``.
    Only characters in ``MMAP_HORIZONTAL_SPACE`` may sit around ``=``.
    A newline, CR, vertical tab, or form feed ends the spacing, so the
    token on the next line is not an excluded value.
    """
    ends = set()
    needle = "mmap_size"
    width = len(needle)
    size = len(text)
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            return ends
        if index > 0 and text[index - 1] not in MMAP_PREFIX:
            start = index + width
            continue
        cursor = index + width
        while cursor < size and text[cursor] in MMAP_HORIZONTAL_SPACE:
            cursor += 1
        if cursor < size and text[cursor] == "=":
            cursor += 1
            while cursor < size and text[cursor] in MMAP_HORIZONTAL_SPACE:
                cursor += 1
            ends.add(cursor)
        start = index + width


def _excluded_hex_span(text, start, end):
    """True when a nine-digit span is inside the hex-run exclusion.

    A run of exactly 64 hexadecimal characters is a SHA-256 digest. A
    nine-digit run at either edge of those 64 is still inside the digest.
    A longer run keeps that exclusion only for a nine-digit span that is
    strictly inside the run. A nine-digit span that starts or ends a run
    longer than 64 is an identifier glued to the run with no separator,
    and it is not excluded. A run of 63 or fewer is not excluded.
    """
    for match in HEX_BLOB.finditer(text):
        if not (match.start() <= start and end <= match.end()):
            continue
        length = len(match.group())
        if length == SHA256_HEX_LENGTH:
            return True
        if length > SHA256_HEX_LENGTH and start > match.start() and end < match.end():
            return True
        return False
    return False


def text_hits(text):
    """Assigned-MID tokens in any text.

    The MID is the first three digits. A leading-0 or leading-9 form does not
    move the MID to digits 2-4; the previous guard did not do that.

    ``normalize_identifier_text`` runs first. A nine-digit token inside a
    hex run of exactly 64 characters is not a vessel id
    (``hex-run-64-or-longer``). A longer run excludes a token only when
    the token is strictly inside that run. A token that starts or ends a
    longer run is an identifier glued on with no separator, and it fails.
    The token that starts immediately after a whole-word ``mmap_size``
    assignment is a byte count (``mmap-size-assignment``). The spacing
    around ``=`` is ``MMAP_HORIZONTAL_SPACE`` only. The same digits outside
    that value are a hit. An f-string prefix whose first three digits are
    an assigned MID is a hit even when the format field completes the nine
    digits at runtime. The prefix may be ``f`` or ``F``, with an optional
    ``r`` on either side, and the quote may be single or triple.
    """
    text = normalize_identifier_text(text)
    hits = []
    mmap_values = _mmap_assignment_ends(text)
    for match in TOKEN_9.finditer(text):
        token = match.group(1)
        if _excluded_hex_span(text, match.start(), match.end()):
            continue
        if match.start() in mmap_values:
            continue
        if mid_is_assigned(token[:3]):
            hits.append(token)
    for match in FSTRING_PREFIX.finditer(text):
        prefix = match.group("prefix")
        if mid_is_assigned(prefix[:3]):
            hits.append(prefix + "{...}")
    return hits


def python_source_hits(text):
    """Earlier name for ``text_hits``. The repository scan calls ``text_hits``."""
    return text_hits(text)


def relative_posix(path, root=ROOT):
    """Path relative to the repository root, with ``/`` separators.

    ``Path.parts[0]`` on an absolute path is ``/``. Classification uses this
    string, not the absolute parts.
    """
    return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()


def path_is_excluded(path, root=ROOT):
    """True only when the relative path is one exact exclusion entry."""
    return relative_posix(path, root) in EXCLUSION_PATHS


class GitUnavailable(RuntimeError):
    """``git ls-files`` could not be run.

    The coverage test calls ``skipTest`` with this message when the
    environment variable ``CI`` is not the string ``true``. When ``CI`` is
    ``true`` that test fails instead of skipping.
    """


def _git_ls_files(root, others=False):
    """Tracked paths, or untracked paths that are not gitignored.

    Paths are relative to ``root``. ``git`` is invoked with ``-C`` so the
    result does not depend on the process working directory.
    """
    command = ["git", "-C", str(root), "ls-files", "-z"]
    if others:
        command.extend(["--others", "--exclude-standard"])
    try:
        listed = subprocess.check_output(command, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise GitUnavailable("git executable was not found") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        message = detail or f"git ls-files exited {exc.returncode}"
        raise GitUnavailable(message) from exc
    return [item.decode("utf-8") for item in listed.split(b"\0") if item]


def read_tracked_text(path):
    """Return ``(text, kind)``.

    ``utf-32`` is checked before ``utf-16`` because a UTF-32 LE BOM starts
    with the UTF-16 LE BOM. A BOM that does not decode returns
    ``(None, "undecodable-bom")`` and the scan records a hit. A NUL byte
    with no such BOM returns ``(None, "nul-byte")`` and the scan skips the
    file. Bytes that are not UTF-8 and contain no NUL are decoded as
    ISO-8859-1 after the UTF-8 sequences in ``SPLITTER_UTF8`` are removed,
    so an ASCII digit run split by those bytes is still visible.
    """
    data = Path(path).read_bytes()
    if data.startswith(UTF32_LE_BOM) or data.startswith(UTF32_BE_BOM):
        try:
            return data.decode("utf-32"), "utf-32"
        except UnicodeDecodeError:
            return None, UNDECODABLE_BOM
    if data.startswith(UTF16_LE_BOM) or data.startswith(UTF16_BE_BOM):
        try:
            return data.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            return None, UNDECODABLE_BOM
    if b"\0" in data:
        return None, "nul-byte"
    try:
        return data.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        cleaned = data
        for sequence in SPLITTER_UTF8:
            if sequence in cleaned:
                cleaned = cleaned.replace(sequence, b"")
        return cleaned.decode("latin-1"), "latin-1"


def extension_key(relative):
    """Lowercase suffix, or ``<none>`` when the tracked name has no suffix."""
    suffix = Path(relative).suffix.lower()
    return suffix if suffix else "<none>"


def scan_repository(root=ROOT):
    """Scan every tracked text file, plus untracked files git does not ignore.

    ``git ls-files`` supplies the tracked set. ``git ls-files --others
    --exclude-standard`` adds a file a test just wrote, so a planted negative
    uses this function. File-exact exclusions are skipped before the read.
    A ``nul-byte`` file is skipped and recorded under ``binaries`` and
    ``binary_reasons``. An undecodable BOM is a hit, not a skip.

    Returns ``(hits, coverage)``. ``hits`` are ``(relative path, token)``.
    ``coverage`` has ``visited`` (text files searched), ``binaries``,
    ``binary_reasons``, and ``tracked``. Every path is relative to ``root``.
    """
    root = Path(root)
    tracked = _git_ls_files(root)
    extras = _git_ls_files(root, others=True)
    hits = []
    visited = []
    binaries = []
    binary_reasons = {}
    for relative in dict.fromkeys([*tracked, *extras]):
        if relative in EXCLUSION_PATHS:
            continue
        path = root / relative
        if not path.is_file():
            continue
        text, kind = read_tracked_text(path)
        if kind == "nul-byte":
            binaries.append(relative)
            binary_reasons[relative] = kind
            continue
        if text is None:
            hits.append((relative, kind))
            continue
        visited.append(relative)
        for hit in text_hits(text):
            hits.append((relative, hit))
    return hits, {
        "visited": visited,
        "binaries": binaries,
        "binary_reasons": binary_reasons,
        "tracked": tracked,
    }


def substitute_legacy_ids(data, mapping=None):
    """Replace legacy synthetic ids as whole tokens. No other bytes change."""
    mapping = SYNTHETIC_ID_MAP if mapping is None else mapping
    text = data.decode("utf-8")
    for legacy, modern in sorted(mapping.items(), key=lambda item: len(item[0]), reverse=True):
        text = re.sub(rf"(?<!\d){legacy}(?!\d)", modern, text)
    return text.encode("utf-8")


def mapped_mmsi_images(mapping=None):
    mapping = SYNTHETIC_ID_MAP if mapping is None else mapping
    return set(mapping.values())


def package_version_text():
    """Package version string.

    Defined as ``__version__`` in ``src/harborlens/__init__.py``.
    ``harborlens.provenance.code_version`` copies it into
    ``code_version.package_version``. Read as text so this proof does not
    import the package.
    """
    source = (ROOT / "src" / "harborlens" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', source, re.MULTILINE)
    if match is None:
        raise AssertionError("package version is not defined")
    return match.group(1)


def event_id_digest(mmsi, start, end, method_version, parameter_set):
    """First 18 hex characters of SHA-256(mmsi|start|end|method|parameter_set).

    Defined in ``harborlens.segmentation`` where ``Segmenter`` builds
    ``event_id`` (the ``hashlib.sha256`` call on that joined string).
    """
    payload = f"{mmsi}|{start}|{end}|{method_version}|{parameter_set}".encode()
    return hashlib.sha256(payload).hexdigest()[:18]


def input_sha256_digest(path):
    """SHA-256 of the input file bytes.

    Defined as ``harborlens.ais.sha256``, stored on the manifest as
    ``input_sha256`` by ``ingest``.
    """
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run_id_digest(manifest, version):
    """SHA-256 of the canonical run-identity JSON.

    Defined in ``harborlens.provenance.add_provenance``. The hashed object is
    ``input_sha256``, ``bbox_lon_lat``, ``method_parameters``,
    ``method_version``, and ``harborlens_version``. A known analysis window
    adds ``analysis_window`` as ``[start_utc, end_utc]`` pairs. An unknown
    window is not hashed. Encoding is ``sort_keys`` and ``separators=(",", ":")``.
    """
    settings = {
        "input_sha256": manifest["input_sha256"],
        "bbox_lon_lat": manifest["bbox_lon_lat"],
        "method_parameters": manifest["method_parameters"],
        "method_version": manifest["method_parameters"].get("method_version", "stationary-v0.1"),
        "harborlens_version": version,
    }
    window = manifest.get("analysis_window") or {}
    if window.get("status") == "known":
        settings["analysis_window"] = [[block["start_utc"], block["end_utc"]] for block in window["blocks"]]
    encoded = json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _line_ending(line):
    if line.endswith("\r\n"):
        return "\r\n"
    if line.endswith("\n"):
        return "\n"
    return ""


def _flip_mapped_category(body, mmsi, category, images):
    """Change a trailing ``ship`` category to ``other`` only for a mapped id."""
    if mmsi in images and category == "ship" and body.endswith("ship"):
        return body[:-len("ship")] + "other"
    return body


def project_cleaned_csv(data, mapping=None):
    """Map ids, then set ``mmsi_category`` from ``ship`` to ``other`` on those rows.

    ``ingest`` writes ``mmsi_category(mmsi)`` on each cleaned row
    (``harborlens.ais``). MID 199 is ``other`` because the first digit is not
    in ``2``–``7`` (``harborlens.vessel.mmsi_category``).
    """
    images = mapped_mmsi_images(mapping)
    text = substitute_legacy_ids(data, mapping).decode("utf-8")
    lines = text.splitlines(keepends=True)
    projected = [lines[0]]
    for line in lines[1:]:
        if not line.strip():
            projected.append(line)
            continue
        ending = _line_ending(line)
        body = line[:-len(ending)] if ending else line
        row = next(csv.reader([body]))
        body = _flip_mapped_category(body, row[0], row[-1], images)
        projected.append(body + ending)
    return "".join(projected).encode("utf-8")


def project_candidates_csv(data, mapping=None):
    """Map ids, recompute ``event_id``, and flip ``ship`` to ``other`` on those rows."""
    images = mapped_mmsi_images(mapping)
    text = substitute_legacy_ids(data, mapping).decode("utf-8")
    lines = text.splitlines(keepends=True)
    header = next(csv.reader([lines[0].strip("\r\n")]))
    index = {name: position for position, name in enumerate(header)}
    projected = [lines[0]]
    for line in lines[1:]:
        if not line.strip():
            projected.append(line)
            continue
        ending = _line_ending(line)
        body = line[:-len(ending)] if ending else line
        row = next(csv.reader([body]))
        mmsi = row[index["mmsi"]]
        if mmsi in images:
            old_id = row[index["event_id"]]
            new_id = event_id_digest(
                mmsi, row[index["start_utc"]], row[index["end_utc"]],
                row[index["method_version"]], row[index["parameter_set"]],
            )
            if body.startswith(old_id):
                body = new_id + body[len(old_id):]
            body = _flip_mapped_category(body, mmsi, row[index["mmsi_category"]], images)
        projected.append(body + ending)
    return "".join(projected).encode("utf-8")


def project_candidates_geojson(data, mapping=None):
    """Map ids, recompute ``event_id``, and flip ``ship`` to ``other`` on those features.

    Serialization is ``json.dumps(..., indent=2)``, the writer in
    ``harborlens.ais.write_events``.
    """
    images = mapped_mmsi_images(mapping)
    document = json.loads(substitute_legacy_ids(data, mapping).decode("utf-8"))
    for feature in document["features"]:
        props = feature["properties"]
        if props.get("mmsi") not in images:
            continue
        props["event_id"] = event_id_digest(
            props["mmsi"], props["start_utc"], props["end_utc"],
            props["method_version"], props["parameter_set"],
        )
        if props.get("mmsi_category") == "ship":
            props["mmsi_category"] = "other"
    return json.dumps(document, indent=2).encode("utf-8")


def category_counts(cleaned):
    """Category histogram in first-seen order.

    ``ingest`` increments ``mmsi_categories`` once per written row
    (``harborlens.ais``).
    """
    counts = {}
    for row in csv.DictReader(io.StringIO(cleaned.decode("utf-8"))):
        category = row["mmsi_category"]
        counts[category] = counts.get(category, 0) + 1
    return counts


def project_manifest(data, artifacts, version=None):
    """Map ids, then recompute the ID-derived manifest fields.

    ``input_sha256`` is the fixture digest (``ais.sha256``).
    ``code_version.package_version`` is ``__version__`` unless ``version``
    is passed. A pin of ``0.2.0.dev15`` reproduces that golden manifest.
    The live version changes ``package_version`` and ``run_id`` only.
    ``mmsi_categories`` is the cleaned-row histogram after the ship-to-other
    flip on mapped rows. ``run_id`` is ``run_id_digest``. Artifact ``sha256``
    and ``size_bytes`` are SHA-256 and length of the projected artifact bytes,
    the check ``harborlens.provenance.add_provenance`` stores and
    ``verify_manifest`` repeats. The manifest text is ``json.dumps`` with
    indent 2 plus a trailing newline, matching the committed golden.
    """
    manifest = json.loads(substitute_legacy_ids(data).decode("utf-8"))
    if version is None:
        version = package_version_text()
    manifest["input_sha256"] = input_sha256_digest(ROOT / "tests" / "fixtures" / "synthetic_ais.csv")
    manifest["code_version"]["package_version"] = version
    manifest["mmsi_categories"] = category_counts(artifacts["houston_clean.csv"])
    manifest["run_id"] = run_id_digest(manifest, version)
    for name in VERIFY_ARTIFACTS:
        body = artifacts[name]
        manifest["artifacts"][name] = {
            "sha256": hashlib.sha256(body).hexdigest(),
            "size_bytes": len(body),
        }
    return (json.dumps(manifest, indent=2) + "\n").encode("utf-8")


def project_dev9(mapping=None, source=DEV9, version=None):
    """dev9 goldens after the mapping and the ID-derived recomputation.

    ``mapping`` defaults to ``SYNTHETIC_ID_MAP``. ``source`` defaults to the
    committed golden directory. Callers that pass another directory must not
    point it at the committed files when they intend to mutate bytes.
    ``version`` defaults to ``__version__``. Pass ``0.2.0.dev15`` to reproduce
    the committed golden manifest.
    """
    source = Path(source)
    artifacts = {
        "houston_clean.csv": project_cleaned_csv(
            (source / "houston_clean.csv").read_bytes(), mapping
        ),
        "stationary_candidates.csv": project_candidates_csv(
            (source / "stationary_candidates.csv").read_bytes(), mapping
        ),
        "stationary_candidates.geojson": project_candidates_geojson(
            (source / "stationary_candidates.geojson").read_bytes(), mapping
        ),
    }
    artifacts["manifest.json"] = project_manifest(
        (source / "manifest.json").read_bytes(), artifacts, version=version
    )
    return artifacts


def independent_verify(files):
    """Hash and size check from ``harborlens.provenance.verify_manifest``.

    Computed here with ``hashlib`` only. ``ok`` is true when every artifact
    digest and byte length matches the manifest entry.
    """
    manifest = json.loads(files["manifest.json"].decode("utf-8"))
    results = {}
    for name in VERIFY_ARTIFACTS:
        body = files[name]
        expected = manifest["artifacts"][name]
        digest = hashlib.sha256(body).hexdigest()
        if digest == expected["sha256"] and len(body) == expected["size_bytes"]:
            results[name] = "verified"
        else:
            results[name] = "mismatch"
    return {"ok": all(item == "verified" for item in results.values()), "artifacts": results}


def _csv_diffs(before, after):
    left = list(csv.DictReader(io.StringIO(before.decode("utf-8"))))
    right = list(csv.DictReader(io.StringIO(after.decode("utf-8"))))
    lines = []
    if len(left) != len(right):
        lines.append(f"row count {len(left)} -> {len(right)}")
    grouped = {}
    for index, (old, new) in enumerate(zip(left, right), start=1):
        for key in list(dict.fromkeys([*old.keys(), *new.keys()])):
            if old.get(key) != new.get(key):
                grouped.setdefault((key, old.get(key), new.get(key)), []).append(index)
    for (key, old, new), rows in grouped.items():
        if len(rows) > 3:
            lines.append(f"{key}: {old!r} -> {new!r} on {len(rows)} rows (first row {rows[0]})")
        else:
            lines.append(f"{key}: {old!r} -> {new!r} on rows {rows}")
    if not lines and before != after:
        lines.append("parsed rows match; raw bytes still differ")
    return lines, len(left), len(right)


def _json_diffs(before, after, prefix=""):
    lines = []

    def walk(old, new, path):
        if isinstance(old, dict) and isinstance(new, dict):
            for key in list(dict.fromkeys([*old.keys(), *new.keys()])):
                child = f"{path}.{key}" if path else key
                if key not in old:
                    lines.append(f"{child}: <missing> -> {new[key]!r}")
                elif key not in new:
                    lines.append(f"{child}: {old[key]!r} -> <missing>")
                else:
                    walk(old[key], new[key], child)
        elif isinstance(old, list) and isinstance(new, list):
            if len(old) != len(new):
                lines.append(f"{path} length {len(old)} -> {len(new)}")
            for index, (left, right) in enumerate(zip(old, new)):
                walk(left, right, f"{path}[{index}]")
        elif old != new:
            lines.append(f"{path}: {old!r} -> {new!r}")

    walk(json.loads(before.decode("utf-8")), json.loads(after.decode("utf-8")), prefix)
    if not lines and before != after:
        lines.append("parsed JSON matches; raw bytes still differ")
    return lines


def golden_projection_report(projected):
    """Field-level diff when the projected dev9 bytes are not dev15."""
    report = []
    for name in ("houston_clean.csv", "stationary_candidates.csv",
                 "stationary_candidates.geojson", "manifest.json"):
        before = projected[name]
        after = (DEV15 / name).read_bytes()
        if before == after:
            report.append(f"{name}: byte-identical")
            continue
        if name.endswith(".csv"):
            detail, old_rows, new_rows = _csv_diffs(before, after)
            report.append(f"{name}: NOT byte-identical ({old_rows} projected rows, {new_rows} dev15 rows)")
        else:
            detail = _json_diffs(before, after)
            report.append(f"{name}: NOT byte-identical")
        report.extend(f"  {line}" for line in detail)
    return report


class MidBoundaryTests(unittest.TestCase):
    def test_assigned_range_boundaries(self):
        self.assertFalse(mid_is_assigned(199))
        self.assertFalse(mid_is_assigned(200))
        self.assertTrue(mid_is_assigned(201))
        self.assertTrue(mid_is_assigned(775))
        self.assertFalse(mid_is_assigned(776))

    def test_constructed_mmsi_boundaries_in_a_column(self):
        def column(mid):
            return f"MMSI,BaseDateTime\n{mid:03d}000001,2024-01-02T00:00:00Z\n"

        self.assertEqual(csv_mmsi_hits(column(199)), [])
        self.assertEqual(csv_mmsi_hits(column(200)), [])
        self.assertEqual(csv_mmsi_hits(column(201)), ["201" + "000001"])
        self.assertEqual(csv_mmsi_hits(column(775)), ["775" + "000001"])
        self.assertEqual(csv_mmsi_hits(column(776)), [])

    def test_unassigned_1990_prefix_passes_and_planted_assigned_mid_fails(self):
        allowed = "199" + "080001"
        self.assertEqual(csv_mmsi_hits(f"MMSI\n{allowed}\n"), [])
        self.assertEqual(python_source_hits(f'mmsi="{allowed}"'), [])
        planted = "367" + "000001"
        self.assertEqual(csv_mmsi_hits("mmsi\n" + planted + "\n"), [planted])
        self.assertEqual(python_source_hits(f'mmsi="{planted}"'), [planted])
        self.assertEqual(json_mmsi_hits(json.dumps({"mmsi": planted})), [planted])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "planted.csv"
            path.write_text("MMSI,LAT\n" + planted + ",29.73\n", encoding="utf-8")
            self.assertEqual(csv_mmsi_hits(path.read_text(encoding="utf-8")), [planted])
            clean = Path(folder) / "clean.csv"
            clean.write_text("MMSI,LAT\n" + allowed + ",29.73\n", encoding="utf-8")
            self.assertEqual(csv_mmsi_hits(clean.read_text(encoding="utf-8")), [])


class MappingTableTests(unittest.TestCase):
    def test_rules_are_a_one_to_one_mid_199_map(self):
        images = list(SYNTHETIC_ID_MAP.values())
        self.assertEqual(len(images), len(set(images)))
        self.assertEqual(len(SYNTHETIC_ID_MAP), len(images))
        for legacy, modern in SYNTHETIC_ID_MAP.items():
            self.assertEqual(len(legacy), 9)
            self.assertEqual(len(modern), 9)
            self.assertTrue(modern.startswith("1990"), modern)
            self.assertTrue(mid_is_assigned(legacy[:3]), legacy)
            self.assertFalse(mid_is_assigned(modern[:3]), modern)
            for prefix in FORBIDDEN_PREFIXES:
                self.assertFalse(modern.startswith(prefix), modern)
        # The constant the proof and the PR table use is this expanded map.
        # The fixture block is the rule whose image starts at 199080001.
        self.assertGreaterEqual(len(SYNTHETIC_ID_RULES), 8)
        fixture_rule = next(rule for rule in SYNTHETIC_ID_RULES if rule[2] == 199080001)
        self.assertEqual(SYNTHETIC_ID_MAP[str(fixture_rule[0])], "199080001")

    def test_rules_and_file_hits_match_the_pin(self):
        """The excluded map file cannot hide a new assigned-MID literal.

        The rule tuple and the tokens ``text_hits`` reports for that file
        are pinned by SHA-256. Every nine-digit hit is a key. Every value
        is ``1990`` plus five digits. Every f-string prefix is a prefix of
        a key.
        """
        rules_digest = hashlib.sha256(repr(SYNTHETIC_ID_RULES).encode()).hexdigest()
        self.assertEqual(rules_digest, SYNTHETIC_ID_RULES_SHA256)
        self.assertEqual(len(SYNTHETIC_ID_MAP), SYNTHETIC_ID_MAP_SIZE)
        source = MAP_SOURCE.read_text(encoding="utf-8")
        found = text_hits(source)
        self.assertEqual(len(found), SYNTHETIC_ID_MAP_HIT_COUNT)
        digest = hashlib.sha256("\n".join(sorted(found)).encode()).hexdigest()
        self.assertEqual(digest, SYNTHETIC_ID_MAP_HITS_SHA256)
        for hit in found:
            if hit.isdigit():
                self.assertIn(hit, SYNTHETIC_ID_MAP, hit)
                self.assertTrue(mid_is_assigned(hit[:3]), hit)
            else:
                prefix = hit.split("{", 1)[0]
                self.assertTrue(
                    any(key.startswith(prefix) for key in SYNTHETIC_ID_MAP),
                    hit,
                )
        for modern in SYNTHETIC_ID_MAP.values():
            self.assertRegex(modern, r"\A1990[0-9]{5}\Z")
            self.assertFalse(mid_is_assigned(modern[:3]), modern)

    def test_extra_assigned_literal_in_the_map_source_fails_the_pin(self):
        source = MAP_SOURCE.read_text(encoding="utf-8")
        extra_token = "366" + "123456"
        self.assertNotIn(extra_token, SYNTHETIC_ID_MAP)
        forged = text_hits(source + "\n# " + extra_token + "\n")
        self.assertIn(extra_token, forged)
        digest = hashlib.sha256("\n".join(sorted(forged)).encode()).hexdigest()
        self.assertNotEqual(digest, SYNTHETIC_ID_MAP_HITS_SHA256)

    def test_a_shorter_rule_tuple_does_not_match_the_pin(self):
        short = SYNTHETIC_ID_RULES[:-1]
        self.assertNotEqual(len(short), len(SYNTHETIC_ID_RULES))
        digest = hashlib.sha256(repr(short).encode()).hexdigest()
        self.assertNotEqual(digest, SYNTHETIC_ID_RULES_SHA256)
        self.assertNotEqual(len(SYNTHETIC_ID_MAP) - 1, SYNTHETIC_ID_MAP_SIZE)

    def test_exclusions_record_a_reason(self):
        for path, reason in EXCLUSIONS:
            self.assertTrue(path.strip())
            self.assertTrue((ROOT / path).is_file(), path)
            self.assertGreater(len(reason.split()), 8, path)
        for name, reason in CONTEXT_EXCLUSIONS:
            self.assertTrue(name.strip())
            self.assertGreater(len(reason.split()), 8, name)


class TokenRuleTests(unittest.TestCase):
    """Nine-digit boundaries. The MID is the first three digits only."""

    def test_ten_digit_run_does_not_fire(self):
        ten = "367" + "123456" + "7"
        self.assertEqual(len(ten), 10)
        self.assertEqual(text_hits(ten), [])
        self.assertEqual(text_hits(f"id {ten} next"), [])
        bare = "367" + "123456"
        self.assertEqual(text_hits(bare), [bare])
        self.assertEqual(text_hits(f"{ten} {bare}"), [bare])

    def test_eight_digit_run_does_not_fire(self):
        """Eight digits are shorter than a token. Nine digits still match."""
        eight = "367" + "12345"
        nine = eight + "6"
        ten = nine + "7"
        self.assertEqual((len(eight), len(nine), len(ten)), (8, 9, 10))
        self.assertTrue(mid_is_assigned(int(eight[:3])))
        self.assertEqual(text_hits(eight), [])
        self.assertEqual(text_hits("id " + eight + " next"), [])
        self.assertEqual(text_hits(nine), [nine])
        self.assertEqual(text_hits(ten), [])
        self.assertEqual(text_hits(" ".join((eight, nine, ten))), [nine])

    def test_decimal_fraction_does_not_fire(self):
        planted = "367" + "123456"
        self.assertEqual(text_hits("29.123456789"), [])
        self.assertEqual(text_hits("-29.123456789"), [])
        self.assertEqual(text_hits("1." + planted), [])
        self.assertEqual(text_hits("29." + planted), [])
        self.assertEqual(text_hits("lat 29.123456789 lon"), [])
        self.assertEqual(text_hits(planted + ".12"), [planted])
        self.assertEqual(text_hits("29.123456789 " + planted), [planted])

    def test_dot_without_a_preceding_digit_still_fires(self):
        planted = "367" + "123456"
        samples = (
            "id." + planted,
            "vessel." + planted,
            "..." + planted,
            "https://example.com/id." + planted,
            "foo/bar." + planted,
        )
        for sample in samples:
            self.assertEqual(text_hits(sample), [planted], sample)

    def test_fstring_prefix_variants_with_an_assigned_mid_fire(self):
        mid = "367"
        self.assertTrue(mid_is_assigned(int(mid)))
        openers = (
            "f'", 'f"', "F'", 'F"',
            "fr'", 'fr"', "Fr'", 'Fr"', "fR'", 'fR"', "FR'", 'FR"',
            "rf'", 'rf"', "Rf'", 'Rf"', "rF'", 'rF"', "RF'", 'RF"',
            'f"""', "f'''", 'F"""', "F'''",
            'fr"""', "fr'''", 'rf"""', "RF'''",
        )
        expected = mid + "{...}"
        for opener in openers:
            text = opener + mid + "{n}"
            self.assertIn(expected, text_hits(text), opener)
        self.assertEqual(text_hits('"' + mid + '{n}"'), [])
        self.assertEqual(text_hits("r'" + mid + "{n}'"), [])
        self.assertEqual(text_hits('f"199{n}"'), [])

    def test_leading_zero_and_leading_nine_do_not_use_digits_2_to_4(self):
        group = "0" + "367" + "12345"
        leading_nine = "9" + "367" + "12345"
        self.assertEqual(len(group), 9)
        self.assertEqual(len(leading_nine), 9)
        self.assertEqual(text_hits(group), [])
        self.assertEqual(text_hits(leading_nine), [])

    def test_hex_run_of_64_is_ignored_and_a_shorter_run_is_not(self):
        planted = "367" + "123456"
        digest = ("ab" * 20) + planted + ("cd" * 15)
        self.assertGreaterEqual(len(digest), 64)
        self.assertEqual(text_hits(digest), [])
        self.assertEqual(text_hits(digest.upper()), [])
        self.assertEqual(text_hits(digest + "\n" + planted + "\n"), [planted])
        short = ("ab" * 27) + planted
        self.assertEqual(len(short), 63)
        self.assertEqual(text_hits(short), [planted])


class GuardScanTests(unittest.TestCase):
    def test_repository_has_no_assigned_mid_outside_the_exclusions(self):
        hits, coverage = scan_repository()
        self.assertEqual(hits, [])
        self.assertGreater(len(coverage["visited"]), 0)

    def test_dev9_golden_would_fail_without_its_exclusion(self):
        hits = []
        for path in sorted(DEV9.iterdir()):
            hits.extend(text_hits(path.read_text(encoding="utf-8")))
        legacy_fixture = str(next(rule[0] for rule in SYNTHETIC_ID_RULES if rule[2] == 199080001))
        self.assertIn(legacy_fixture, hits)
        self.assertTrue(path_is_excluded(DEV9 / "houston_clean.csv"))

    def test_mapping_table_would_fail_without_its_exclusion(self):
        hits = python_source_hits(MAP_SOURCE.read_text(encoding="utf-8"))
        self.assertTrue(hits)
        self.assertTrue(all(mid_is_assigned(hit[:3]) for hit in hits if hit.isdigit()))
        self.assertTrue(path_is_excluded(MAP_SOURCE))

    def test_mmap_size_byte_count_is_contextual_and_an_mmsi_still_fails(self):
        token = str(256 * 1024 * 1024)
        probe = (ROOT / "tests" / "multiday_memory_probe.py").read_text(encoding="utf-8")
        self.assertIn(token, probe)
        self.assertNotIn(token, python_source_hits(probe))
        self.assertEqual(
            python_source_hits(f'db.execute("PRAGMA mmap_size={token}")'),
            [],
        )
        self.assertEqual(python_source_hits(f"mmap_size = {token}\n"), [])
        # The assigned value is exempt. These three are not that value.
        other = "367" + "123456"
        self.assertEqual(text_hits("not_mmap_size = " + other), [other])
        self.assertEqual(text_hits("mmsi = " + other + "; mmap_size = 0"), [other])
        self.assertEqual(text_hits(other + "  # mmap_size = 1"), [other])
        # Same digits, not an mmap_size assignment: the guard fails.
        self.assertEqual(python_source_hits(f'mmsi = "{token}"\n'), [token])
        self.assertEqual(python_source_hits(f"value = {token}\n"), [token])
        self.assertEqual(csv_mmsi_hits(f"MMSI\n{token}\n"), [token])
        self.assertEqual(json_mmsi_hits(json.dumps({"mmsi": token})), [token])
        self.assertEqual(json_mmsi_hits(json.dumps({"properties": {"mmsi": token}})), [token])

    def test_hex_digest_is_ignored_and_a_standalone_mmsi_in_the_same_file_fails(self):
        text = FR_EVIDENCE.read_text(encoding="utf-8")
        self.assertFalse(path_is_excluded(FR_EVIDENCE))
        self.assertNotIn("mmsi", text.lower())
        raw_hits = []
        for match in TOKEN_9.finditer(text):
            token = match.group(1)
            if mid_is_assigned(token[:3]):
                self.assertTrue(_excluded_hex_span(text, match.start(), match.end()), token)
                raw_hits.append(token)
        self.assertTrue(raw_hits)
        self.assertEqual(text_hits(text), [])
        planted = "367" + "123456"
        combined = text + "\n" + planted + "\n"
        self.assertEqual(text_hits(combined), [planted])
        extra = ROOT / "docs" / "data" / "_qa_hex_and_standalone.md"
        relative = extra.relative_to(ROOT).as_posix()
        extra.write_text(combined, encoding="utf-8")
        try:
            hits, coverage = scan_repository()
            self.assertIn(relative, coverage["visited"])
            self.assertEqual(
                [item for item in hits if item[0] == relative],
                [(relative, planted)],
            )
        finally:
            extra.unlink(missing_ok=True)
        self.assertIn("SHA-256", dict(CONTEXT_EXCLUSIONS)["hex-run-64-or-longer"])

    def test_retired_marshall_islands_id_is_redacted_outside_the_map(self):
        retired = "538" + "001234"
        changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        trace = (ROOT / "docs" / "requirements" / "traceability.md").read_text(encoding="utf-8")
        phrase = "former Marshall Islands-MID synthetic ID"
        self.assertNotIn(retired, changelog)
        self.assertNotIn(retired, trace)
        self.assertIn(phrase, changelog)
        self.assertIn(phrase, trace)
        self.assertIn(retired, MAP_SOURCE.read_text(encoding="utf-8"))
        self.assertTrue(path_is_excluded(MAP_SOURCE))


def assert_tracked_coverage(test, coverage):
    """Visited text files equal tracked files minus binaries minus exclusions.

    Paths are relative to the repository root. Untracked planted files are
    scanned by the same function and are not part of this total.
    """
    tracked = coverage["tracked"]
    tracked_set = set(tracked)
    test.assertTrue(EXCLUSION_PATHS <= tracked_set)
    visited_tracked = [path for path in coverage["visited"] if path in tracked_set]
    binaries_tracked = [path for path in coverage["binaries"] if path in tracked_set]
    test.assertFalse(set(visited_tracked) & EXCLUSION_PATHS)
    test.assertFalse(set(binaries_tracked) & EXCLUSION_PATHS)
    test.assertFalse(set(visited_tracked) & set(binaries_tracked))
    by_ext = Counter(extension_key(path) for path in visited_tracked)
    total = sum(by_ext.values())
    expected = len(tracked) - len(binaries_tracked) - len(EXCLUSION_PATHS)
    detail = ", ".join(f"{key}={by_ext[key]}" for key in sorted(by_ext))
    test.assertGreater(total, 0, detail)
    test.assertEqual(total, expected, detail)
    test.assertEqual(
        len(visited_tracked) + len(binaries_tracked) + len(EXCLUSION_PATHS),
        len(tracked),
        detail,
    )
    reasons = coverage["binary_reasons"]
    for path in binaries_tracked:
        test.assertEqual(reasons[path], "nul-byte", path)
        test.assertIn(reasons[path], BINARY_SKIP_REASONS)
    skipped = ", ".join(f"{path} ({reasons[path]})" for path in binaries_tracked)
    test.assertEqual(binaries_tracked, [], "a tracked file was skipped: " + skipped)
    for path in coverage["visited"]:
        test.assertFalse(path.startswith("/"), path)
        test.assertNotIn("\\", path)
    tops = {path.split("/", 1)[0] for path in visited_tracked}
    for name in ("src", "docs", "schemas", "specs", "tests", "tools"):
        test.assertIn(name, tops, sorted(tops))
    for suffix in (
        ".py", ".md", ".json", ".csv", ".geojson", ".yml", ".yaml",
        ".toml", ".cff", ".sh", "<none>",
    ):
        test.assertGreater(by_ext[suffix], 0, detail)
    return by_ext


def run_coverage_check(test):
    """Run the coverage meta-test.

    When git cannot be run, skip unless the environment variable ``CI`` is
    the string ``true``. In that case the test fails.
    """
    try:
        _hits, coverage = scan_repository()
    except GitUnavailable as exc:
        reason = f"git is unavailable: {exc}"
        if os.environ.get("CI") == "true":
            test.fail(reason)
        test.skipTest(reason)
    return assert_tracked_coverage(test, coverage)


class GuardCoverageTests(unittest.TestCase):
    """The repository scan must cover every tracked text file."""

    def test_visited_text_files_equal_git_ls_files_minus_binaries_and_exclusions(self):
        run_coverage_check(self)

    def test_missing_git_skips_outside_ci_and_fails_when_ci_is_true(self):
        def boom(*_args, **_kwargs):
            raise GitUnavailable("git executable was not found")

        module = __import__(__name__)
        with mock.patch.dict(os.environ, {"CI": "false"}):
            with mock.patch.object(module, "scan_repository", side_effect=boom):
                with self.assertRaises(unittest.SkipTest) as skipped:
                    run_coverage_check(self)
        self.assertIn("git is unavailable", str(skipped.exception))
        self.assertIn("git executable was not found", str(skipped.exception))

        with mock.patch.dict(os.environ, {"CI": "true"}):
            with mock.patch.object(module, "scan_repository", side_effect=boom):
                with self.assertRaises(AssertionError) as failed:
                    run_coverage_check(self)
        self.assertIn("git is unavailable", str(failed.exception))
        self.assertIn("git executable was not found", str(failed.exception))

    def test_paths_are_classified_from_the_repository_root(self):
        absolute = (ROOT / "src" / "harborlens" / "ais.py").resolve()
        self.assertNotEqual(absolute.parts[0], "src")
        self.assertTrue(relative_posix(absolute).startswith("src/"))

    def _assert_planted(self, relative, text, planted):
        path = ROOT / relative
        self.assertFalse(path.exists(), relative)
        path.write_text(text, encoding="utf-8")
        try:
            hits, coverage = scan_repository()
            self.assertIn(relative, coverage["visited"])
            self.assertEqual(
                [item for item in hits if item[0] == relative],
                [(relative, planted)],
            )
        finally:
            path.unlink(missing_ok=True)

    def _scan_temp_file(self, parent, name, text):
        """Write ``name`` under a temporary directory inside ``parent``.

        ``parent`` is inside the repository. ``git ls-files`` does not see a
        directory outside the work tree, so the plant has to live here for
        the scan to read it. The directory is removed when this method
        returns. The caller asserts on the path and the hits.
        """
        with tempfile.TemporaryDirectory(dir=parent) as folder:
            path = Path(folder) / name
            path.write_text(text, encoding="utf-8")
            relative = relative_posix(path)
            hits, coverage = scan_repository()
            matched = [item for item in hits if item[0] == relative]
            return relative, matched, coverage

    def test_planted_assigned_mid_inside_tests_is_reported(self):
        planted = "367" + "123456"
        self._assert_planted(
            "tests/_qa_planted_assigned_mid.py",
            f'mmsi = "{planted}"\n',
            planted,
        )

    def test_planted_markdown_line_outside_tests_is_reported(self):
        planted = "367" + "123456"
        ten = planted + "7"
        text = (
            f"A ten-digit run {ten} does not match.\n"
            "A decimal fraction 29.123456789 does not match.\n"
            f"A decimal fraction 29.{planted} does not match.\n"
            f"A prose identifier {planted} matches.\n"
        )
        self._assert_planted("docs/_qa_planted_assigned_mid.md", text, planted)

    def test_planted_csv_vessel_id_column_is_reported(self):
        planted = "367" + "123456"
        table = f"vessel_id,lat\n{planted},29.73\n"
        self.assertEqual(csv_mmsi_hits(table), [])
        self.assertEqual(text_hits(table), [planted])
        self._assert_planted("tests/_qa_planted_vessel_id.csv", table, planted)

    def test_planted_json_value_outside_an_mmsi_key_is_reported(self):
        planted = "367" + "123456"
        body = json.dumps({"note": planted})
        self.assertEqual(json_mmsi_hits(body), [])
        self.assertEqual(text_hits(body), [planted])
        self._assert_planted("schemas/_qa_planted_value.json", body, planted)

    def test_planted_notebook_cell_is_reported(self):
        planted = "367" + "123456"
        notebook = json.dumps(
            {
                "nbformat": 4,
                "nbformat_minor": 5,
                "metadata": {},
                "cells": [
                    {
                        "cell_type": "markdown",
                        "metadata": {},
                        "source": ["Synthetic plant " + planted + "\n"],
                    }
                ],
            }
        )
        self.assertEqual(json_mmsi_hits(notebook), [])
        self.assertEqual(text_hits(notebook), [planted])
        relative, matched, coverage = self._scan_temp_file(
            ROOT / "docs", "_qa_planted.ipynb", notebook
        )
        self.assertTrue(relative.startswith("docs/"))
        self.assertTrue(relative.endswith("/_qa_planted.ipynb"))
        self.assertNotIn(relative, coverage["tracked"])
        self.assertIn(relative, coverage["visited"])
        self.assertEqual(matched, [(relative, planted)])

    def test_planted_src_module_is_reported(self):
        planted = "367" + "123456"
        source = 'mmsi = "' + planted + '"\n'
        self.assertEqual(text_hits(source), [planted])
        relative, matched, coverage = self._scan_temp_file(
            ROOT / "src", "_qa_planted_assigned_mid.py", source
        )
        self.assertTrue(relative.startswith("src/"))
        self.assertTrue(relative.endswith("/_qa_planted_assigned_mid.py"))
        self.assertNotIn(relative, coverage["tracked"])
        self.assertIn(relative, coverage["visited"])
        self.assertEqual(matched, [(relative, planted)])

    def test_sha256_eight_and_ten_digit_runs_pass_the_scan(self):
        """A 64-hex digest, an 8-digit run, and a 10-digit run are not tokens.

        The digest is the SHA-256 length and contains a nine-digit
        assigned-MID run. That run stays inside the hex blob. The same file
        fails when a standalone nine-digit token is added beside it.
        """
        nine = "367" + "123456"
        eight = nine[:8]
        ten = nine + "7"
        digest = ("ab" * 20) + nine + ("cd" * 7) + "e"
        self.assertEqual(len(digest), 64)
        self.assertEqual((len(eight), len(ten)), (8, 10))
        self.assertRegex(digest, r"^[0-9a-f]{64}$")
        self.assertIn(nine, digest)
        passing = digest + "\n" + eight + "\n" + ten + "\n"
        self.assertEqual(text_hits(passing), [])
        relative, matched, coverage = self._scan_temp_file(
            ROOT / "docs", "_qa_boundary.md", passing
        )
        self.assertIn(relative, coverage["visited"])
        self.assertEqual(matched, [])
        failing = passing + nine + "\n"
        self.assertEqual(text_hits(failing), [nine])
        relative, matched, coverage = self._scan_temp_file(
            ROOT / "docs", "_qa_boundary.md", failing
        )
        self.assertIn(relative, coverage["visited"])
        self.assertEqual(matched, [(relative, nine)])

    def test_binary_file_is_skipped_and_counted(self):
        planted = "367" + "123456"
        extra = ROOT / "tests" / "_qa_binary_with_mmsi.bin"
        relative = extra.relative_to(ROOT).as_posix()
        extra.write_bytes(planted.encode("ascii") + b"\0" + planted.encode("ascii"))
        try:
            hits, coverage = scan_repository()
            self.assertIn(relative, coverage["binaries"])
            self.assertEqual(coverage["binary_reasons"][relative], "nul-byte")
            self.assertIn(coverage["binary_reasons"][relative], BINARY_SKIP_REASONS)
            self.assertNotIn(relative, coverage["visited"])
            self.assertNotIn(relative, coverage["tracked"])
            self.assertFalse(any(path == relative for path, _token in hits))
        finally:
            extra.unlink(missing_ok=True)

    def test_unexpected_file_in_dev9_is_not_excluded(self):
        planted = "367" + "123456"
        extra = DEV9 / "_qa_not_a_golden.py"
        relative = extra.relative_to(ROOT).as_posix()
        self.assertNotIn(relative, EXCLUSION_PATHS)
        self.assertFalse(path_is_excluded(extra))
        for name in (
            "houston_clean.csv",
            "stationary_candidates.csv",
            "stationary_candidates.geojson",
            "manifest.json",
        ):
            self.assertTrue(path_is_excluded(DEV9 / name), name)
        extra.write_text(f'mmsi = "{planted}"\n', encoding="utf-8")
        try:
            hits, coverage = scan_repository()
            self.assertIn(relative, coverage["visited"])
            self.assertIn((relative, planted), hits)
        finally:
            extra.unlink(missing_ok=True)


class GoldenSubstitutionProofTests(unittest.TestCase):
    """Projected dev9 artifacts must be byte-identical to dev15.

    The projection applies ``SYNTHETIC_ID_MAP``, flips ``ship`` to ``other``
    only on mapped rows, and recomputes ``event_id``, ``input_sha256``,
    ``run_id``, and ``package_version`` with ``hashlib``. It does not import
    or call the pipeline. Any other difference fails.

    Pinning the version to ``0.2.0.dev15`` reproduces the golden manifest.
    The live package version changes ``package_version`` and ``run_id`` only.
    ``harborlens-verify`` checks the three artifact hashes. The release
    recount reads ``houston_clean.csv``. Those bytes stay the dev15 bytes.
    """

    def test_dev15_manifest_verifies_its_own_artifacts(self):
        files = {name: (DEV15 / name).read_bytes() for name in (*VERIFY_ARTIFACTS, "manifest.json")}
        result = independent_verify(files)
        self.assertTrue(result["ok"], result)
        self.assertEqual(set(result["artifacts"]), set(VERIFY_ARTIFACTS))

    def test_dev9_projection_is_byte_identical_to_dev15(self):
        pinned = project_dev9(version="0.2.0.dev15")
        mismatches = [
            name for name, body in pinned.items()
            if body != (DEV15 / name).read_bytes()
        ]
        self.assertEqual(mismatches, [], "\n".join(golden_projection_report(pinned)))
        live = project_dev9()
        for name in VERIFY_ARTIFACTS:
            self.assertEqual(live[name], (DEV15 / name).read_bytes(), name)
        live_manifest = json.loads(live["manifest.json"])
        golden_manifest = json.loads((DEV15 / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(live_manifest["code_version"]["package_version"], package_version_text())
        self.assertEqual(live_manifest["code_version"]["package_version"], "0.2.0.dev23")
        self.assertNotEqual(live_manifest["run_id"], golden_manifest["run_id"])
        golden_manifest["code_version"]["package_version"] = "0.2.0.dev23"
        golden_manifest["run_id"] = live_manifest["run_id"]
        self.assertEqual(live_manifest, golden_manifest)

    def test_release_verify_path_projection_is_byte_identical(self):
        """Verify artifacts and the release recount input stay the dev15 bytes."""
        projected = project_dev9()
        dev15 = {
            name: (DEV15 / name).read_bytes()
            for name in (*VERIFY_ARTIFACTS, "manifest.json")
        }
        mismatches = [name for name in VERIFY_ARTIFACTS if projected[name] != dev15[name]]
        cleaned_differs = projected["houston_clean.csv"] != dev15["houston_clean.csv"]
        projected_verify = independent_verify(projected)
        current_verify = independent_verify(dev15)
        pinned = project_dev9(version="0.2.0.dev15")
        report = "\n".join(golden_projection_report(pinned))
        report += (
            f"\nindependent verify(projected)={projected_verify}"
            f"\nindependent verify(dev15)={current_verify}"
            f"\nrelease recount input differs={cleaned_differs}"
        )
        self.assertEqual(mismatches, [], report)
        self.assertFalse(cleaned_differs, report)
        self.assertEqual(pinned["manifest.json"], dev15["manifest.json"], report)
        self.assertNotEqual(projected["manifest.json"], dev15["manifest.json"])
        self.assertTrue(projected_verify["ok"], report)
        self.assertTrue(current_verify["ok"], report)


class ProofMutationTests(unittest.TestCase):
    """The proof fails when a golden, an unmapped category, or the map changes.

    Copies stay in memory or in a temporary directory. Committed fixtures
    are only read.
    """

    def test_one_changed_golden_byte_fails(self):
        committed = (DEV15 / "houston_clean.csv").read_bytes()
        projected = project_dev9(version="0.2.0.dev15")
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            for name in projected:
                data = bytearray((DEV15 / name).read_bytes())
                if name == "houston_clean.csv":
                    data[20] ^= 0x01
                (dest / name).write_bytes(bytes(data))
            mismatches = [
                name for name in projected
                if projected[name] != (dest / name).read_bytes()
            ]
        self.assertEqual(mismatches, ["houston_clean.csv"])
        self.assertEqual((DEV15 / "houston_clean.csv").read_bytes(), committed)

    def test_flipping_an_unmapped_row_category_fails(self):
        unmapped = "790" + "000001"
        self.assertNotIn(unmapped, SYNTHETIC_ID_MAP.values())
        source = (DEV9 / "houston_clean.csv").read_bytes()
        extra = (
            unmapped + ",2024-01-02T00:00:00Z,29.73,-95.16,0.1,70,5,,,,,,,ship\r\n"
        ).encode("utf-8")
        projected = project_cleaned_csv(source + extra)
        unmapped_lines = [
            line for line in projected.decode("utf-8").splitlines()
            if line.startswith(unmapped + ",")
        ]
        self.assertEqual(len(unmapped_lines), 1)
        self.assertTrue(unmapped_lines[0].endswith("ship"))
        lines = []
        for line in projected.decode("utf-8").splitlines(keepends=True):
            if line.startswith(unmapped + ",") and line.rstrip("\r\n").endswith("ship"):
                ending = "\r\n" if line.endswith("\r\n") else "\n"
                line = line[: -len("ship") - len(ending)] + "other" + ending
            lines.append(line)
        flipped = "".join(lines).encode("utf-8")
        self.assertNotEqual(projected, flipped)
        self.assertTrue(flipped.decode("utf-8").splitlines()[-1].endswith("other"))

    def test_altered_map_entry_fails(self):
        legacy = next(
            key for key, value in SYNTHETIC_ID_MAP.items() if value == "199080001"
        )
        altered = dict(SYNTHETIC_ID_MAP)
        altered[legacy] = "199080099"
        self.assertEqual(SYNTHETIC_ID_MAP[legacy], "199080001")
        projected = project_dev9(mapping=altered)
        self.assertNotEqual(
            projected["houston_clean.csv"],
            (DEV15 / "houston_clean.csv").read_bytes(),
        )
        self.assertEqual(SYNTHETIC_ID_MAP[legacy], "199080001")


def unicode_escapes(digits):
    """``\\u`` escapes for each ASCII digit. The source has no joined token."""
    return "".join("\\u%04x" % ord(character) for character in digits)


def scan_temp_bytes(parent, name, data):
    """Write ``data`` under a temporary directory inside ``parent`` and scan.

    The directory is removed before this function returns. ``parent`` is
    inside the work tree so ``git ls-files --others`` sees the file.
    """
    with tempfile.TemporaryDirectory(dir=parent) as folder:
        path = Path(folder) / name
        path.write_bytes(data)
        relative = relative_posix(path)
        hits, coverage = scan_repository()
        matched = [item for item in hits if item[0] == relative]
        return relative, matched, coverage


class DeferredGuardTests(unittest.TestCase):
    """P3 gaps from issue #88 and the review of PR #102.

    Each case has a hit, a miss, and a length or character-set boundary.
    Plants are built from digit parts. This file has no nine-digit
    assigned-MID literal.
    """

    def test_underscore_grouped_assigned_mid_is_a_hit(self):
        expected = "367" + "123456"
        samples = (
            "367" + "_" + "123" + "_" + "456",
            "367" + "_" + "123456",
            "3" + "_" + "67123456",
            "36712345" + "_" + "6",
            "_".join(expected),
            'f"' + "367" + "_" + "12" + '{n}"',
        )
        self.assertEqual(text_hits(samples[0]), [expected])
        self.assertEqual(text_hits(samples[1]), [expected])
        self.assertEqual(text_hits(samples[2]), [expected])
        self.assertEqual(text_hits(samples[3]), [expected])
        self.assertEqual(text_hits(samples[4]), [expected])
        self.assertEqual(text_hits(samples[5]), ["36712{...}"])

    def test_underscore_grouped_unassigned_mid_is_not_a_hit(self):
        allowed = "199" + "080001"
        self.assertEqual(text_hits("199" + "_" + "080" + "_" + "001"), [])
        self.assertEqual(text_hits("_".join(allowed)), [])
        self.assertEqual(text_hits('f"' + "199" + "_" + "08" + '{n}"'), [])

    def test_underscore_length_and_character_boundaries(self):
        expected = "367" + "123456"
        self.assertEqual(text_hits("_".join("367" + "12345")), [])
        self.assertEqual(text_hits("_".join(expected)), [expected])
        self.assertEqual(text_hits("_".join(expected + "7")), [])
        self.assertEqual(text_hits("367" + "__" + "123456"), [])
        self.assertEqual(text_hits("367" + "\uff3f" + "123456"), [])
        self.assertEqual(text_hits("367" + " " + "123456"), [])
        self.assertEqual(text_hits("29." + "367" + "_" + "123456"), [])
        self.assertEqual(text_hits("id." + "367" + "_" + "123456"), [expected])
        self.assertEqual(text_hits("_" + expected), [expected])
        self.assertEqual(text_hits('f"' + "367" + "__" + "12" + '{n}"'), [])

    def test_each_splitter_joins_an_assigned_mid(self):
        expected = "367" + "123456"
        left, right = expected[:3], expected[3:]
        self.assertGreater(len(DIGIT_SPLITTERS), 0)
        for splitter in sorted(DIGIT_SPLITTERS):
            self.assertEqual(
                text_hits(left + splitter + right),
                [expected],
                hex(ord(splitter)),
            )
            escaped = "\\u%04x" % ord(splitter)
            self.assertEqual(text_hits(left + escaped + right), [expected], escaped)

    def test_splitter_between_an_unassigned_mid_is_not_a_hit(self):
        allowed = "199" + "080001"
        self.assertEqual(text_hits(allowed[:3] + "\u200b" + allowed[3:]), [])
        self.assertEqual(text_hits(allowed[:3] + "\\ufeff" + allowed[3:]), [])

    def test_splitter_length_and_whitespace_boundaries(self):
        expected = "367" + "123456"
        self.assertEqual(text_hits(expected[:3] + "\u200b" + "12345"), [])
        self.assertEqual(text_hits(expected[:3] + "\u200b" + expected[3:]), [expected])
        self.assertEqual(text_hits(expected[:3] + "\ufeff" + expected[3:] + "7"), [])
        self.assertEqual(text_hits(expected[:3] + " " + expected[3:]), [])
        self.assertEqual(text_hits(expected[:3] + "\n" + expected[3:]), [])
        self.assertEqual(text_hits(expected[:3] + "\t" + expected[3:]), [])
        self.assertEqual(text_hits("\u200b" + "12345"), [])
        self.assertEqual(text_hits(expected[:3] + "\u200b"), [])

    def test_unicode_escape_digits_match_when_the_mid_is_assigned(self):
        planted = "367" + "123456"
        self.assertEqual(text_hits(unicode_escapes(planted)), [planted])
        self.assertEqual(text_hits("\\u0033" + "67123456"), [planted])
        self.assertEqual(text_hits("367" + "\\u005f" + "123456"), [planted])

    def test_unicode_escape_unassigned_mid_is_not_a_hit(self):
        self.assertEqual(text_hits(unicode_escapes("199" + "080001")), [])
        self.assertEqual(text_hits("\\u0031" + "99080001"), [])

    def test_unicode_escape_length_and_other_escape_forms(self):
        planted = "367" + "123456"
        self.assertEqual(text_hits(unicode_escapes("367" + "12345")), [])
        self.assertEqual(text_hits(unicode_escapes(planted)), [planted])
        self.assertEqual(text_hits(unicode_escapes(planted + "7")), [])
        self.assertEqual(text_hits("\\u0033" + "6712345"), [])
        self.assertEqual(text_hits("\\u0033" + "67123456" + "7"), [])
        self.assertEqual(text_hits("\\U00000033" + "67123456"), [])
        self.assertEqual(text_hits("\\x33" + "67123456"), [])
        self.assertEqual(text_hits("\\u0041" + planted), [])
        self.assertEqual(text_hits("\\u003" + "67123456"), [])

    def test_utf16_le_and_be_bom_assigned_mid_is_reported(self):
        planted = "367" + "123456"
        for bom, encoded, parent in (
            (UTF16_LE_BOM, planted.encode("utf-16-le"), ROOT / "tests"),
            (UTF16_BE_BOM, planted.encode("utf-16-be"), ROOT / "docs"),
        ):
            data = bom + encoded
            self.assertFalse(data.startswith(UTF32_LE_BOM))
            relative, matched, coverage = scan_temp_bytes(parent, "plant.txt", data)
            self.assertEqual(matched, [(relative, planted)])
            self.assertIn(relative, coverage["visited"])
            self.assertNotIn(relative, coverage["binaries"])

    def test_utf16_bom_unassigned_mid_is_not_a_hit(self):
        allowed = "199" + "080001"
        data = UTF16_LE_BOM + allowed.encode("utf-16-le")
        relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", data)
        self.assertEqual(matched, [])
        self.assertIn(relative, coverage["visited"])
        self.assertNotIn(relative, coverage["binaries"])

    def test_utf16_bom_length_boundaries_and_a_missing_bom(self):
        eight = UTF16_LE_BOM + ("367" + "12345").encode("utf-16-le")
        ten = UTF16_BE_BOM + ("367" + "1234567").encode("utf-16-be")
        for data in (eight, ten):
            relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", data)
            self.assertEqual(matched, [])
            self.assertIn(relative, coverage["visited"])
        planted = "367" + "123456"
        naked = planted.encode("utf-16-le")
        self.assertFalse(naked.startswith(UTF16_LE_BOM))
        self.assertIn(b"\0", naked)
        relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", naked)
        self.assertEqual(matched, [])
        self.assertIn(relative, coverage["binaries"])
        self.assertEqual(coverage["binary_reasons"][relative], "nul-byte")
        self.assertNotIn(relative, coverage["visited"])
        self.assertNotIn(relative, coverage["tracked"])

    def test_utf32_bom_is_decoded_ahead_of_utf16(self):
        planted = "367" + "123456"
        le = UTF32_LE_BOM + planted.encode("utf-32-le")
        be = UTF32_BE_BOM + planted.encode("utf-32-be")
        self.assertNotEqual(le.decode("utf-16"), planted)
        relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", le)
        self.assertEqual(matched, [(relative, planted)])
        self.assertIn(relative, coverage["visited"])
        relative, matched, coverage = scan_temp_bytes(ROOT / "src", "plant.txt", be)
        self.assertEqual(matched, [(relative, planted)])
        self.assertTrue(relative.startswith("src/"))

    def test_utf32_bom_unassigned_and_short_runs_are_not_hits(self):
        samples = (
            UTF32_BE_BOM + ("199" + "080001").encode("utf-32-be"),
            UTF32_LE_BOM + ("367" + "12345").encode("utf-32-le"),
            UTF32_LE_BOM + ("367" + "1234567").encode("utf-32-le"),
            UTF16_LE_BOM,
        )
        for data in samples:
            relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", data)
            self.assertEqual(matched, [])
            self.assertIn(relative, coverage["visited"])

    def test_truncated_utf16_bom_fails_closed(self):
        data = UTF16_LE_BOM + b"A"
        relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", data)
        self.assertEqual(matched, [(relative, UNDECODABLE_BOM)])
        self.assertNotIn(relative, coverage["binaries"])
        self.assertNotIn(relative, coverage["visited"])

    def test_non_utf8_assigned_mid_is_scanned(self):
        planted = "367" + "123456"
        data = planted.encode("ascii") + b"\xff"
        relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", data)
        self.assertEqual(matched, [(relative, planted)])
        self.assertIn(relative, coverage["visited"])
        self.assertNotIn(relative, coverage["binaries"])

    def test_non_utf8_unassigned_mid_is_not_a_hit(self):
        data = ("199" + "080001").encode("ascii") + b"\xff"
        relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", data)
        self.assertEqual(matched, [])
        self.assertIn(relative, coverage["visited"])

    def test_non_utf8_length_and_splitter_byte_boundaries(self):
        planted = "367" + "123456"
        for body in ("367" + "12345", planted + "7"):
            data = body.encode("ascii") + b"\xff"
            relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", data)
            self.assertEqual(matched, [])
            self.assertIn(relative, coverage["visited"])
        split = (
            planted[:3].encode("ascii")
            + "\u200b".encode("utf-8")
            + planted[3:].encode("ascii")
            + b"\xff"
        )
        relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", split)
        self.assertEqual(matched, [(relative, planted)])
        spaced = (
            planted[:3].encode("ascii")
            + b" "
            + planted[3:].encode("ascii")
            + b"\xff"
        )
        relative, matched, coverage = scan_temp_bytes(ROOT / "tests", "plant.txt", spaced)
        self.assertEqual(matched, [])
        self.assertIn(relative, coverage["visited"])

    def test_identifier_glued_to_a_sha256_run_is_a_hit(self):
        planted = "367" + "123456"
        digest = "ab" * 32
        self.assertEqual(len(digest), SHA256_HEX_LENGTH)
        self.assertEqual(text_hits(planted + digest), [planted])
        self.assertEqual(text_hits(digest + planted), [planted])
        self.assertEqual(text_hits(digest + "\n" + planted), [planted])

    def test_unassigned_identifier_glued_to_a_sha256_run_is_not_a_hit(self):
        allowed = "199" + "080001"
        digest = "ab" * 32
        self.assertEqual(text_hits(allowed + digest), [])
        self.assertEqual(text_hits(digest + allowed), [])

    def test_sha256_exclusion_is_exactly_64_characters(self):
        planted = "367" + "123456"
        exact = planted + ("ab" * 27) + "c"
        exact_end = ("ab" * 27) + "c" + planted
        self.assertEqual(len(exact), SHA256_HEX_LENGTH)
        self.assertEqual(len(exact_end), SHA256_HEX_LENGTH)
        self.assertEqual(text_hits(exact), [])
        self.assertEqual(text_hits(exact_end), [])
        sixty_five = ("ab" * 28) + planted
        sixty_three = ("ab" * 27) + planted
        self.assertEqual((len(sixty_five), len(sixty_three)), (65, 63))
        self.assertEqual(text_hits(sixty_five), [planted])
        self.assertEqual(text_hits(sixty_three), [planted])
        interior = "ab" + planted + ("cd" * 28)
        self.assertGreater(len(interior), SHA256_HEX_LENGTH)
        self.assertEqual(text_hits(interior), [])
        self.assertEqual(text_hits(planted[:8] + ("ab" * 32)), [])
        self.assertEqual(text_hits(planted + "7" + ("ab" * 32)), [])

    def test_mmap_size_exclusion_does_not_cross_a_newline(self):
        token = str(256 * 1024 * 1024)
        planted = "367" + "123456"
        self.assertEqual(text_hits("mmap_size =\n" + planted), [planted])
        self.assertEqual(text_hits("mmap_size =\r\n" + planted), [planted])
        self.assertEqual(text_hits("mmap_size =\r" + planted), [planted])
        self.assertEqual(text_hits("mmap_size = \n" + planted), [planted])
        self.assertEqual(text_hits("mmap_size =\n" + token), [token])
        self.assertEqual(text_hits("mmap_size =\v" + token), [token])
        self.assertEqual(text_hits("mmap_size =\f" + token), [token])
        allowed = "199" + "080001"
        self.assertEqual(text_hits("mmap_size =\n" + allowed), [])

    def test_mmap_size_same_line_space_and_tab_stay_excluded(self):
        token = str(256 * 1024 * 1024)
        self.assertEqual(text_hits("mmap_size = " + token), [])
        self.assertEqual(text_hits("mmap_size\t=\t" + token), [])
        self.assertEqual(text_hits("mmap_size=" + token), [])
        self.assertEqual(text_hits('db.execute("PRAGMA mmap_size=' + token + '")'), [])
        self.assertEqual(text_hits(".mmap_size = " + token), [])
        planted = "367" + "123456"
        self.assertEqual(text_hits("\u00e9mmap_size = " + planted), [planted])
        self.assertEqual(text_hits("not_mmap_size = " + planted), [planted])
        probe = (ROOT / "tests" / "multiday_memory_probe.py").read_text(encoding="utf-8")
        self.assertNotIn(token, text_hits(probe))


if __name__ == "__main__":
    unittest.main()
