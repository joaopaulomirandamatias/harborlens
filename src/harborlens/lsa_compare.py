"""Reproducible GovInfo LSA Title 33 comparison; never legal certification.

Compares the December 2023 and January 2024 monthly LSA publications only
when the caller opts in. The LSA is an index, not a day-specific legal
opinion. Matching index rows do not authorize geometry or AIS use.

Importing this module, ordinary ``harborlens`` runs, and the test suite do
not open a socket. A process must pass ``--fetch`` (or ``allow_network=True``)
before any GovInfo request. Digest comparisons use ``hmac.compare_digest``.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import hmac
import io
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from harborlens import __version__

MONTHS = ("2023-12", "2024-01")
FIXED_GOVINFO_URLS = {
    "2023-12": "https://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf",
    "2024-01": "https://www.govinfo.gov/content/pkg/LSA-2024-01/pdf/LSA-2024-01.pdf",
}
EXPECTED_PART110_PROPOSAL_PAGES = ("47837", "89644", "89646", "89648")
# Independently measured GovInfo bytes. A mismatch is refused before pypdf runs.
PINNED_LSA_PDFS = {
    "2023-12": {
        "sha256": "c226121a7617f1b4578a0fcf79f58d4735696e0405c5522615699bdb5bab037d",
        "size_bytes": 554882,
        "page_count": 117,
    },
    "2024-01": {
        "sha256": "5ce3c08a45ed6853643a105690d332cbf9813400d4da391de794ef1237305348",
        "size_bytes": 516462,
        "page_count": 82,
    },
}
MAX_SOURCE_BYTES = 10 * 1048576
MAX_TITLE33_CHARS = 500_000
# Inclusive page ceiling. pypdf counts page-tree nodes with
# page_tree_maximum_entries, so that limit is MAX_PDF_PAGES and a larger
# tree fails before the whole tree is flattened. page_tree_maximum_page_entries
# counts copied dictionary keys, not pages; the pinned December PDF needs 586.
MIN_PDF_PAGES = 26
MAX_PDF_PAGES = 299
MAX_PDF_PAGE_DICTIONARY_ENTRIES = 1024
TITLE33_HEADER = re.compile(r"TITLE\s*33\s*[-—]?\s*NAVIGATION", re.I)
TITLE34_HEADER = re.compile(r"TITLE\s*34\s*[-—]?\s*EDUCATION", re.I)
TIMEOUT_SECONDS = 60
MAX_REDIRECTS = 3
RIGHTS_STATUS = "review_required"
LEGAL_EFFECT = "NOT_DETERMINED"


class LSAComparisonError(ValueError):
    """Official historical-source evidence is missing, oversized or ambiguous."""


def digests_equal(left: object, right: object) -> bool:
    """Compare SHA-256 hex digests with ``hmac.compare_digest``.

    Length and alphabet are checked first. The hex values themselves are
    compared only when both sides are 64 lowercase-compatible hex characters.
    """
    if not isinstance(left, str) or not isinstance(right, str):
        return False
    normalized_left = left.lower()
    normalized_right = right.lower()
    if len(normalized_left) != 64 or len(normalized_right) != 64:
        return False
    alphabet = "0123456789abcdef"
    if any(character not in alphabet for character in normalized_left + normalized_right):
        return False
    return hmac.compare_digest(normalized_left, normalized_right)


def _require_fixed_govinfo_url(url: str) -> str:
    if url not in FIXED_GOVINFO_URLS.values():
        raise LSAComparisonError("GovInfo source must be one of the two fixed HTTPS URLs")
    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != "www.govinfo.gov"
        or parts.username
        or parts.password
        or parts.port not in (None, 443)
        or parts.query
        or parts.fragment
        or parts.netloc != "www.govinfo.gov"
    ):
        raise LSAComparisonError("GovInfo source must be one of the two fixed HTTPS URLs")
    return url


class _GovInfoRedirects(HTTPRedirectHandler):
    """Refuse every redirect that leaves the exact requested GovInfo URL."""

    max_redirections = MAX_REDIRECTS
    max_repeats = MAX_REDIRECTS

    def redirect_request(self, request, fp, code, message, headers, newurl):
        if code not in (301, 302, 303, 307, 308):
            raise LSAComparisonError("GovInfo redirect status is not allowed")
        current = getattr(request, "full_url", None)
        if newurl != current:
            raise LSAComparisonError("GovInfo source redirect may not change the fixed URL")
        _require_fixed_govinfo_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)

    def http_error_302(self, req, fp, code, msg, headers):
        location = None
        if headers is not None:
            getter = getattr(headers, "get", None)
            if getter is not None:
                location = getter("location") or getter("uri")
            elif "location" in headers:
                location = headers["location"]
            elif "uri" in headers:
                location = headers["uri"]
        if not location:
            raise LSAComparisonError("GovInfo redirect is missing Location")
        try:
            return super().http_error_302(req, fp, code, msg, headers)
        except LSAComparisonError:
            raise
        except HTTPError as exc:
            raise LSAComparisonError("GovInfo redirect limit exceeded") from exc

    http_error_301 = http_error_303 = http_error_307 = http_error_308 = http_error_302


def _build_govinfo_opener():
    """Open GovInfo directly. An empty ProxyHandler ignores HTTPS_PROXY."""
    return build_opener(ProxyHandler({}), _GovInfoRedirects())


def _source_url(month: str) -> str:
    try:
        return _require_fixed_govinfo_url(FIXED_GOVINFO_URLS[month])
    except KeyError as exc:
        raise LSAComparisonError("Unsupported historical monthly LSA source") from exc


def _declared_length(value: object) -> int:
    text = str(value).strip()
    if not text.isdecimal():
        raise LSAComparisonError("Official LSA Content-Length is not an integer")
    size = int(text)
    if size > MAX_SOURCE_BYTES:
        raise LSAComparisonError("Official LSA exceeds size cap")
    return size


def _fetch_source(opener, month: str):
    url = _source_url(month)
    request = Request(url, headers={
        "User-Agent": "HarborLens-GovInfo-Source-Audit/0.1",
        "Accept": "application/pdf",
    })
    if request.get_method() != "GET" or request.data:
        raise LSAComparisonError("GovInfo source request must be a GET with no body")
    try:
        with opener(request, timeout=TIMEOUT_SECONDS) as response:
            declared = getattr(response, "headers", {}).get("Content-Length")
            if declared is not None:
                _declared_length(declared)
            raw = response.read(MAX_SOURCE_BYTES + 1)
    except LSAComparisonError:
        raise
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise LSAComparisonError("Official LSA fetch failed inside the fixed-URL bounds") from exc
    if not raw.startswith(b"%PDF-") or len(raw) > MAX_SOURCE_BYTES:
        raise LSAComparisonError("Official LSA is missing, invalid or oversized")
    return url, raw


def _parser_failure(exc: Exception) -> LSAComparisonError:
    """Hide parser internals. Callers exit 2 and write nothing."""
    if not isinstance(exc, Exception):
        raise exc
    return LSAComparisonError("Could not parse the complete official LSA PDF")


def _page_text(page) -> str:
    try:
        text = page.extract_text()
    except LSAComparisonError:
        raise
    except Exception as exc:
        raise _parser_failure(exc) from exc
    if text is None:
        return ""
    if not isinstance(text, str):
        raise LSAComparisonError("Could not parse the complete official LSA PDF")
    return text


def _extract_title33(reader):
    """Keep Title 33 text, including a same-page prefix before the Title 34 header.

    The start page contributes only the text from the Title 33 header onward.
    Extraction stops at the Title 34 header and does not read later pages.
    The character ceiling is applied as text is accepted, not after a full extract.
    """
    try:
        page_count = len(reader.pages)
    except LSAComparisonError:
        raise
    except Exception as exc:
        raise _parser_failure(exc) from exc
    if isinstance(page_count, bool) or not isinstance(page_count, int):
        raise LSAComparisonError("Could not parse the complete official LSA PDF")
    if page_count > MAX_PDF_PAGES:
        raise LSAComparisonError("Official LSA exceeds the page ceiling")
    if page_count < MIN_PDF_PAGES:
        raise LSAComparisonError("Unexpected source PDF page count")
    parts: list[str] = []
    used = 0
    start_page = None

    def _accept(fragment: str) -> None:
        nonlocal used
        if not fragment:
            return
        extra = len(fragment) if not parts else len(fragment) + 1
        if used + extra > MAX_TITLE33_CHARS:
            raise LSAComparisonError("Title 33 extracted content exceeds the size cap")
        parts.append(fragment)
        used += extra

    for index in range(page_count):
        text = _page_text(reader.pages[index])
        if start_page is None:
            match = TITLE33_HEADER.search(text)
            if match is None:
                continue
            start_page = index + 1
            text = text[match.start():]
        end = TITLE34_HEADER.search(text)
        if end is not None:
            _accept(text[:end.start()])
            content = "\n".join(parts)
            if len(content) < 300:
                raise LSAComparisonError("Title 33 extracted content is unexpectedly short")
            return content, start_page, index + 1, page_count
        _accept(text)
    if start_page is None:
        raise LSAComparisonError("Cannot establish Title 33 start in extracted PDF")
    raise LSAComparisonError("Cannot establish Title 33 end in extracted PDF")


def _proposed_part110_pages(text: str) -> tuple[str, ...]:
    sections = list(re.finditer(r"Proposed\s+Rules\s*:", text, re.I))
    if not sections:
        raise LSAComparisonError("Title 33 proposed rules region not found")
    proposed = text[sections[-1].end():]
    # Keep each dotted-leader line bounded; never span following Part rows.
    matches = re.findall(
        r"(?m)^[ \t]*110[ \t]*\.{2,}[ \t]*(\d{4,6}(?:[ \t]*,[ \t]*\d{4,6})*)[ \t]*$",
        proposed,
    )
    if len(matches) != 1:
        raise LSAComparisonError("Part 110 proposed-rule page entry is missing or ambiguous")
    return tuple(re.findall(r"\d{4,6}", matches[0]))


def _pdf_reader(content: bytes):
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise LSAComparisonError(
            "Install optional dependency: pip install 'harborlens[lsa]'"
        ) from exc
    try:
        return PdfReader(io.BytesIO(content), strict=True)
    except LSAComparisonError:
        raise
    except Exception as exc:
        raise _parser_failure(exc) from exc


def _require_pinned_pdf(month: str, raw: bytes) -> str:
    """Refuse unexpected bytes before any PDF parser runs."""
    pin = PINNED_LSA_PDFS[month]
    if len(raw) != pin["size_bytes"]:
        raise LSAComparisonError("Official LSA bytes do not match the pinned source")
    digest = hashlib.sha256(raw).hexdigest()
    if not digests_equal(digest, pin["sha256"]):
        raise LSAComparisonError("Official LSA bytes do not match the pinned source")
    return digest


@contextlib.contextmanager
def _quiet_pypdf_logs():
    """Keep font and xref notices off the CLI stream. Errors still propagate."""
    logger = logging.getLogger("pypdf")
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield
    finally:
        logger.setLevel(previous)


def _parse_with_page_tree_limit(raw: bytes, reader_factory):
    """Flatten at most MAX_PDF_PAGES page-tree nodes when using pypdf."""
    if reader_factory is _pdf_reader:
        try:
            from pypdf import apply_configuration
        except ImportError as exc:
            raise LSAComparisonError(
                "Install optional dependency: pip install 'harborlens[lsa]'"
            ) from exc
        context = apply_configuration(
            page_tree_maximum_entries=MAX_PDF_PAGES,
            page_tree_maximum_page_entries=MAX_PDF_PAGE_DICTIONARY_ENTRIES,
        )
    else:
        context = contextlib.nullcontext()
    try:
        with _quiet_pypdf_logs(), context:
            reader = reader_factory(raw)
            return _extract_title33(reader)
    except LSAComparisonError:
        raise
    except Exception as exc:
        raise LSAComparisonError("Could not parse the complete official LSA PDF") from exc


def compare_official_lsa(
    opener=None,
    reader_factory=None,
    *,
    allow_network: bool = False,
    enforce_source_pins: bool | None = None,
):
    """Collect two source receipts while refusing to infer a legal result.

    ``allow_network`` defaults to false. Tests pass an in-memory opener and
    never set this flag. The CLI sets it only after ``--fetch``.

    Source pins are enforced for the real pypdf reader. A byte or size mismatch
    is refused before that reader is called. There is no wall-clock timeout
    around pypdf parsing; that residual is accepted for this opt-in command.
    """
    if enforce_source_pins is None:
        enforce_source_pins = reader_factory is None
    if opener is None:
        if not allow_network:
            raise LSAComparisonError(
                "Network fetch is opt-in; pass --fetch or allow_network=True"
            )
        opener = _build_govinfo_opener().open
    if reader_factory is None:
        reader_factory = _pdf_reader
    documents = {}
    for month in MONTHS:
        url, raw = _fetch_source(opener, month)
        if enforce_source_pins:
            pdf_sha = _require_pinned_pdf(month, raw)
        else:
            pdf_sha = hashlib.sha256(raw).hexdigest()
        scoped, first_page, last_page, page_count = _parse_with_page_tree_limit(raw, reader_factory)
        if enforce_source_pins and page_count != PINNED_LSA_PDFS[month]["page_count"]:
            raise LSAComparisonError("Official LSA page count does not match the pinned source")
        proposal = _proposed_part110_pages(scoped)
        if proposal != EXPECTED_PART110_PROPOSAL_PAGES:
            raise LSAComparisonError("Proposed Part 110 page citations changed: manual review required")
        text_sha = hashlib.sha256(scoped.encode("utf-8")).hexdigest()
        if not digests_equal(pdf_sha, hashlib.sha256(raw).hexdigest()):
            raise LSAComparisonError("PDF digest check failed")
        if not digests_equal(text_sha, hashlib.sha256(scoped.encode("utf-8")).hexdigest()):
            raise LSAComparisonError("Title 33 digest check failed")
        documents[month] = {
            "official_pdf_url": url,
            "official_pdf_sha256": pdf_sha,
            "official_pdf_size_bytes": len(raw),
            "pdf_page_count": page_count,
            "title33_pdf_pages_1based": [first_page, last_page],
            "title33_extracted_text_sha256": text_sha,
            "target_110_197_direct_occurrences": len(re.findall(
                r"(?<!\d)110\s*\.\s*197(?!\d)", scoped
            )),
            "part110_proposed_fr_pages": list(proposal),
            "rights_status": RIGHTS_STATUS,
        }
    return {
        "schema_version": "govinfo-lsa-dec-jan-v1",
        "harborlens_version": __version__,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_months": list(MONTHS),
        "documents": documents,
        "proposed_part110_pages_match": True,
        "study_target": "33 CFR 110.197 on 2024-01-02",
        "legal_effect_on_study_date": LEGAL_EFFECT,
        "intervening_amendments_excluded": False,
        "historical_wgs84_geometry_approved": False,
        "ais_spatial_join_permitted": False,
        "rights_status": RIGHTS_STATUS,
        "mandatory_follow_up": (
            "Cross-check original Federal Register/LSA and effective-date history with qualified reviewers; "
            "a cumulative LSA and an absent direct section entry cannot prove unchanged legal status."
        ),
    }


def save_report(
    output: Path,
    opener=None,
    reader_factory=None,
    *,
    allow_network: bool = False,
    enforce_source_pins: bool | None = None,
):
    output = Path(output)
    if output.suffix.lower() != ".json" or output.exists():
        raise LSAComparisonError("Output must be a new .json report")
    report = compare_official_lsa(
        opener,
        reader_factory,
        allow_network=allow_network,
        enforce_source_pins=enforce_source_pins,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_name(output.name + ".partial")
    try:
        with temp.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, indent=2)
        os.replace(temp, output)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return report


def main(argv=None, *, opener=None, reader_factory=None, enforce_source_pins: bool | None = None):
    parser = argparse.ArgumentParser(
        description="Compare official 2023-12/2024-01 Title 33 LSA source indexes"
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--fetch",
        action="store_true",
        help="Opt in to bounded HTTPS downloads of the two fixed GovInfo LSA PDFs",
    )
    args = parser.parse_args(argv)
    if not args.fetch:
        parser.error("network fetch is disabled; pass --fetch to opt in to the two fixed GovInfo URLs")
    try:
        report = save_report(
            args.out,
            opener=opener,
            reader_factory=reader_factory,
            allow_network=opener is None,
            enforce_source_pins=enforce_source_pins,
        )
    except LSAComparisonError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from None
    print(json.dumps({
        "source_months": report["source_months"],
        "harborlens_version": report["harborlens_version"],
        "official_pdf_sha256": {
            key: value["official_pdf_sha256"] for key, value in report["documents"].items()
        },
        "source_index_consistent": report["proposed_part110_pages_match"],
        "legal_effect_on_study_date": report["legal_effect_on_study_date"],
        "rights_status": report["rights_status"],
        "ais_spatial_join_permitted": False,
    }, indent=2))


if __name__ == "__main__":
    main()
