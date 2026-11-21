"""HarborLens local output integrity and provenance checks.

Byte hashes establish file consistency only; they do not certify dataset
authenticity, rights, or actual vessel behavior.
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import unicodedata
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlsplit

from harborlens import __version__
from harborlens.cli_usage import add_version_argument, escape_error_text, escape_error_text
from harborlens.io_safe import AISInputError

FILES = ("houston_clean.csv", "stationary_candidates.csv", "stationary_candidates.geojson")

class ManifestFormatError(ValueError):
    """``manifest.json`` is not a HarborLens artifact manifest."""

def checksum(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def digests_equal(left, right):
    """Compare a digest, fingerprint or pin without an early content mismatch.

    Hex strings are compared in lowercase. Byte strings are compared as raw
    bytes. The two sides must be the same kind and the same length; anything
    else is unequal. ``hmac.compare_digest`` covers the equal-length content.
    """
    try:
        if isinstance(left, str) and isinstance(right, str):
            left, right = left.lower(), right.lower()
            if len(left) != len(right):
                return False
            return hmac.compare_digest(left, right)
        if isinstance(left, (bytes, bytearray)) and isinstance(right, (bytes, bytearray)):
            left, right = bytes(left), bytes(right)
            if len(left) != len(right):
                return False
            return hmac.compare_digest(left, right)
    except (TypeError, ValueError):
        return False
    return False

def code_version():
    """Package version (part of run identity) and, in CI, the git commit (metadata only).

    The commit comes from ``GITHUB_SHA`` or ``HARBORLENS_GIT_COMMIT`` when it is a
    40-hex SHA; it is recorded but not hashed into run IDs, so identical code gives
    identical run IDs locally and in CI. Bump the package version on any change
    that can alter outputs.
    """
    commit = os.environ.get("HARBORLENS_GIT_COMMIT") or os.environ.get("GITHUB_SHA") or ""
    return {"package_version": __version__,
            "git_commit": commit if re.fullmatch(r"[0-9a-f]{40}", commit) else None}


_SOURCE_URL_MESSAGE = (
    "source URL must be http or https, must name a host, and must not include credentials"
)


# Default_Ignorable code points that are not already rejected as category Cc
# or Cf, from Unicode 15.0.0 DerivedCoreProperties, plus U+180F (unassigned
# on Unicode 13, Mn on Unicode 15) and U+2800 (braille blank, a blank
# lookalike that is not Default_Ignorable). Combining marks in general,
# such as U+0300 and U+0301, are not in this set and stay accepted.
# Membership is a table lookup, not a runtime property scan.
_SOURCE_URL_IGNORABLE_RANGES = (
    (0x034F, 0x034F),       # combining grapheme joiner
    (0x115F, 0x1160),       # Hangul choseong/jungseong fillers
    (0x17B4, 0x17B5),       # Khmer inherent vowels
    (0x180B, 0x180F),       # Mongolian free variation selectors, including four
    (0x2065, 0x2065),       # reserved default-ignorable
    (0x2800, 0x2800),       # braille blank
    (0x3164, 0x3164),       # Hangul filler
    (0xFE00, 0xFE0F),       # variation selectors
    (0xFFA0, 0xFFA0),       # halfwidth Hangul filler
    (0xFFF0, 0xFFF8),       # reserved default-ignorable
    (0xE0000, 0xE0000),     # reserved default-ignorable
    (0xE0002, 0xE001F),     # reserved default-ignorable
    (0xE0080, 0xE00FF),     # reserved default-ignorable
    (0xE0100, 0xE01EF),     # variation selectors supplement
    (0xE01F0, 0xE0FFF),     # reserved default-ignorable
)
_SOURCE_URL_IGNORABLE = frozenset(
    chr(code)
    for start, end in _SOURCE_URL_IGNORABLE_RANGES
    for code in range(start, end + 1)
)


def _raw_source_url_forbidden(value):
    """True when ``value`` has whitespace, a control, a format character, or an ignorable.

    Checked on the raw string. ``urlsplit`` removes tab, CR, and LF before
    it parses, so a check after the split would see a different value.
    Category Cc is C0, DEL, and C1. Category Cf includes bidi controls such
    as U+202E and zero-width characters. Variation selectors and U+034F are
    the fixed set ``_SOURCE_URL_IGNORABLE``, not a category Mn scan.
    """
    for character in value:
        if (character.isspace() or character in _SOURCE_URL_IGNORABLE
                or unicodedata.category(character) in ("Cc", "Cf")):
            return True
    return False


# Exact query or fragment names, compared case-insensitively after '-' and
# '_' are treated as the same character. ``x-amz-`` / ``x_amz_`` is a prefix.
# This is a heuristic: names not on the list are kept.
_CREDENTIAL_PARAMETER_NAMES = frozenset({
    "token",
    "access_token",
    "api_key",
    "apikey",
    "secret",
    "client_secret",
    "private_token",
    "id_token",
    "refresh_token",
    "password",
    "passwd",
    "pwd",
    "sig",
    "signature",
    "auth",
    "authorization",
    "session",
    "jwt",
    "key",
    "x_goog_signature",
    "x_goog_credential",
    "access_key",
    "secret_key",
    "api_token",
    "session_id",
    "x_api_key",
    "oauth_token",
    "private_key",
    "csrf",
})


def _credential_label(name):
    """Normalized parameter name when it is on the heuristic, else None.

    The label is the name only. The parameter value is never included.
    """
    lowered = name.lower()
    normalized = lowered.replace("-", "_")
    if normalized in _CREDENTIAL_PARAMETER_NAMES or normalized.startswith("x_amz_"):
        return normalized
    return None


def _parameter_pairs(text):
    """Query or fragment pairs. ``&`` and ``;`` are both separators."""
    if not text:
        return []
    return parse_qsl(text.replace(";", "&"), keep_blank_values=True, separator="&")


def _decoded_parameter_names(name):
    """The name ``parse_qsl`` returned, then one further percent-decode.

    ``parse_qsl`` already decoded once. A second ``unquote`` catches a
    double-encoded name (``%2574oken`` becomes ``token``). A third encoding
    is not decoded again.
    """
    yield name
    again = unquote(name)
    if again != name:
        yield again


def _credential_parameter_name(parts):
    """The first denylisted query or fragment name, or None.

    The returned text is escaped and capped. It is never the parameter value.
    """
    for text in (parts.query, parts.fragment):
        for name, _value in _parameter_pairs(text):
            for decoded in _decoded_parameter_names(name):
                label = _credential_label(decoded)
                if label:
                    shown = escape_error_text(label)
                    if len(shown) > 80:
                        shown = shown[:80] + "..."
                    return shown
    return None


def require_declared_source_url(source_url):
    """Accept a missing URL or an HTTP(S) URL with a host and no userinfo.

    ``None`` means ``--source-url`` was omitted. The same ``AISInputError``
    is raised, and the URL is not included in the message, when:

    - the raw value contains whitespace, a control (C0, DEL, C1), or a
      format character (category Cf, including U+202E and zero-width
      characters), including characters ``urlsplit`` would remove;
    - ``.port`` raises ``ValueError`` (a non-integer port, or a port outside
      0..65535) — that read sits inside the ``ValueError`` guard — or the
      port is 0;
    - the scheme is not ``http`` or ``https``, there is no host, or a
      username or password is present;
    - the raw value contains a character in the fixed set
      ``_SOURCE_URL_IGNORABLE`` (U+FE00–U+FE0F, U+E0100–U+E01EF,
      U+180B–U+180D, U+034F), including U+FE0F;
    - a query or fragment parameter name, after one percent-decode and
      again after a second decode, and after ``-`` and ``_`` are treated
      as the same character, is on the credential heuristic (any case),
      or starts with ``x-amz-`` / ``x_amz_``. ``&`` and ``;`` both separate
      parameters.

    An omitted port and an empty port (``http://example.org:``, where
    ``.port`` is ``None``) are accepted. Port 1 and port 65535 are the
    inclusive bounds. Port 0 is rejected, the same rule as the rights
    register.

    The parameter-name check is a heuristic, the same idea as rejecting
    ``user:pass@``. ``http://example.org:443/path?q=1`` stays accepted.
    A value of ``token`` (``?q=token``) stays accepted. The list is not a
    complete secret detector. ``rights_status`` stays ``review_required``.
    """
    if source_url is None:
        return
    if not isinstance(source_url, str) or _raw_source_url_forbidden(source_url):
        raise AISInputError(_SOURCE_URL_MESSAGE)
    try:
        parts = urlsplit(source_url)
        # Reading these raises ``ValueError`` for an unbalanced IPv6 bracket
        # such as ``http://[::1`` or ``http://[``. ``.port`` raises
        # ``ValueError`` for a non-integer port and for a port outside
        # 0..65535, such as ``:abc`` or ``:65536``.
        username = parts.username
        password = parts.password
        port = parts.port
        _host = parts.hostname
    except ValueError:
        raise AISInputError(_SOURCE_URL_MESSAGE) from None
    # ``.port`` already rejected values outside 0..65535. Port 0 is inside
    # that range and is not a server port. The rights register uses 1..65535.
    if port is not None and not 1 <= port <= 65535:
        raise AISInputError(_SOURCE_URL_MESSAGE)
    if (parts.scheme not in ("https", "http") or not parts.netloc
            or username or password):
        raise AISInputError(_SOURCE_URL_MESSAGE)
    credential = _credential_parameter_name(parts)
    if credential:
        raise AISInputError(f"{_SOURCE_URL_MESSAGE} (parameter '{credential}')")


def add_provenance(folder, manifest, source_url=None):
    require_declared_source_url(source_url)
    settings = {"input_sha256": manifest["input_sha256"], "bbox_lon_lat": manifest["bbox_lon_lat"],
                "method_parameters": manifest["method_parameters"],
                "method_version": manifest["method_parameters"].get("method_version", "stationary-v0.1"),
                "harborlens_version": __version__}
    window = manifest.get("analysis_window") or {}
    if window.get("status") == "known":
        # A known window changes censoring outputs, so it is part of run identity.
        # Runs without a window keep the legacy run_id derivation.
        settings["analysis_window"] = [[b["start_utc"], b["end_utc"]] for b in window["blocks"]]
    manifest["run_id"] = hashlib.sha256(json.dumps(settings, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest["provenance_schema_version"] = "1.1"
    manifest["code_version"] = code_version()
    manifest["source_metadata"] = {"source_url": source_url, "metadata_origin": "user_declared",
                                   "rights_status": "review_required"}
    manifest["artifacts"] = {
        name: {"sha256": checksum(Path(folder) / name), "size_bytes": (Path(folder) / name).stat().st_size}
        for name in FILES
    }
    manifest["provenance_warning"] = "Integrity hashes do not establish source authenticity, data rights or verified events."
    return manifest

def verify_manifest(path, preloaded=None):
    """Check artifact SHA-256 and size against the manifest.

    ``preloaded`` maps an artifact name to bytes already read by the caller.
    Those names are hashed from that buffer and are not opened again, so a
    release recount can share one read with this check.
    """
    path = Path(path)
    preloaded = {} if preloaded is None else preloaded
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestFormatError("Invalid artifact manifest") from exc
    try:
        record = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ManifestFormatError("Invalid artifact manifest") from exc
    items = record.get("artifacts") if isinstance(record, dict) else None
    if not isinstance(items, dict) or set(items) != set(FILES):
        raise ManifestFormatError("Invalid artifact manifest")
    results = {}
    for name in FILES:
        expected = items[name]
        if not isinstance(expected, dict) or not isinstance(expected.get("sha256"), str):
            raise ManifestFormatError("Invalid artifact hash entry")
        if name in preloaded:
            raw = preloaded[name]
            if not isinstance(raw, (bytes, bytearray)):
                raise ManifestFormatError("Invalid preloaded artifact bytes")
            actual = hashlib.sha256(bytes(raw)).hexdigest()
            size = len(raw)
        else:
            file = path.parent / name
            try:
                is_file = file.is_file()
            except OSError:
                results[name] = "unreadable"
                continue
            if not is_file:
                results[name] = "missing"
                continue
            try:
                actual = checksum(file)
                size = file.stat().st_size
            except OSError:
                results[name] = "unreadable"
                continue
        if digests_equal(actual, expected["sha256"]) and size == expected.get("size_bytes"):
            results[name] = "verified"
        else:
            results[name] = "mismatch"
    return {"ok": all(x == "verified" for x in results.values()), "artifacts": results}

def main():
    parser = argparse.ArgumentParser(
        description=(
            "Verify SHA-256 and sizes of a HarborLens run against manifest.json. "
            "This checks local bytes only; it does not prove source authenticity, "
            "data rights, or verified events."
        )
    )
    add_version_argument(parser)
    parser.add_argument(
        "--manifest", required=True, type=Path,
        help="path to the manifest.json written by harborlens (required)",
    )
    args = parser.parse_args()
    try:
        result = verify_manifest(args.manifest)
    except ManifestFormatError:
        parser.error(escape_error_text(
            f"manifest '{args.manifest}' is not a valid HarborLens manifest"
        ))
    except OSError as exc:
        detail = exc.strerror if exc.strerror else type(exc).__name__
        parser.error(escape_error_text(
            f"cannot read manifest '{args.manifest}' ({detail}). "
            "Give --manifest the manifest.json written by harborlens."
        ))
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        raise SystemExit(1)
