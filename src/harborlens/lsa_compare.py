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
import hashlib
import hmac
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MONTHS = ("2023-12", "2024-01")
FIXED_GOVINFO_URLS = {
    "2023-12": "https://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf",
    "2024-01": "https://www.govinfo.gov/content/pkg/LSA-2024-01/pdf/LSA-2024-01.pdf",
}
EXPECTED_PART110_PROPOSAL_PAGES = ("47837", "89644", "89646", "89648")
MAX_SOURCE_BYTES = 10 * 1048576
MAX_TITLE33_CHARS = 500_000
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

    def redirect_request(self, request, fp, code, message, headers, newurl):
        if code not in (301, 302, 303, 307, 308):
            raise LSAComparisonError("GovInfo redirect status is not allowed")
        current = getattr(request, "full_url", None)
        if newurl != current:
            raise LSAComparisonError("GovInfo source redirect may not change the fixed URL")
        _require_fixed_govinfo_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


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


def _extract_title33(reader):
    page_count = len(reader.pages)
    if not (25 < page_count < 300):
        raise LSAComparisonError("Unexpected source PDF page count")
    pages = [page.extract_text() or "" for page in reader.pages]
    starts = [index for index, body in enumerate(pages)
              if re.search(r"TITLE\s*33\s*[-—]?\s*NAVIGATION", body, re.I)]
    if not starts:
        raise LSAComparisonError("Cannot establish Title 33 start in extracted PDF")
    start = starts[0]
    ends = [index for index in range(start + 1, len(pages))
            if re.search(r"TITLE\s*34\s*[-—]?\s*EDUCATION", pages[index], re.I)]
    if not ends:
        raise LSAComparisonError("Cannot establish Title 33 end in extracted PDF")
    end = ends[0]
    content = "\n".join(pages[start:end])
    if len(content) < 300:
        raise LSAComparisonError("Title 33 extracted content is unexpectedly short")
    if len(content) > MAX_TITLE33_CHARS:
        raise LSAComparisonError("Title 33 extracted content exceeds the size cap")
    return content, start + 1, end


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
            "Install optional dependency: pip install 'pypdf>=5,<7'"
        ) from exc
    return PdfReader(io.BytesIO(content), strict=True)


def compare_official_lsa(opener=None, reader_factory=None, *, allow_network: bool = False):
    """Collect two source receipts while refusing to infer a legal result.

    ``allow_network`` defaults to false. Tests pass an in-memory opener and
    never set this flag. The CLI sets it only after ``--fetch``.
    """
    if opener is None:
        if not allow_network:
            raise LSAComparisonError(
                "Network fetch is opt-in; pass --fetch or allow_network=True"
            )
        opener = build_opener(_GovInfoRedirects()).open
    if reader_factory is None:
        reader_factory = _pdf_reader
    documents = {}
    for month in MONTHS:
        url, raw = _fetch_source(opener, month)
        try:
            reader = reader_factory(raw)
            scoped, first_page, last_page = _extract_title33(reader)
        except LSAComparisonError:
            raise
        except Exception as exc:
            raise LSAComparisonError("Could not parse the complete official LSA PDF") from exc
        proposal = _proposed_part110_pages(scoped)
        if proposal != EXPECTED_PART110_PROPOSAL_PAGES:
            raise LSAComparisonError("Proposed Part 110 page citations changed: manual review required")
        pdf_sha = hashlib.sha256(raw).hexdigest()
        text_sha = hashlib.sha256(scoped.encode("utf-8")).hexdigest()
        if not digests_equal(pdf_sha, hashlib.sha256(raw).hexdigest()):
            raise LSAComparisonError("PDF digest check failed")
        if not digests_equal(text_sha, hashlib.sha256(scoped.encode("utf-8")).hexdigest()):
            raise LSAComparisonError("Title 33 digest check failed")
        documents[month] = {
            "official_pdf_url": url,
            "official_pdf_sha256": pdf_sha,
            "pdf_page_count": len(reader.pages),
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


def save_report(output: Path, opener=None, reader_factory=None, *, allow_network: bool = False):
    output = Path(output)
    if output.suffix.lower() != ".json" or output.exists():
        raise LSAComparisonError("Output must be a new .json report")
    report = compare_official_lsa(opener, reader_factory, allow_network=allow_network)
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


def main(argv=None):
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
    report = save_report(args.out, allow_network=True)
    print(json.dumps({
        "source_months": report["source_months"],
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
