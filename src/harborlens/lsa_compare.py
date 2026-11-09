"""Reproducible GovInfo LSA Title 33 comparison; never legal certification.

Compares monthly LSA publications for December 2023 and January 2024,
extracts the bounded Title 33 section, and records original PDF and scoped
text SHA-256. The LSA is an index, not an exhaustive day-specific legal
opinion; even matching entries do not authorize nautical geometry or AIS use.
Network access occurs only on explicit CLI invocation.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

MONTHS = ("2023-12", "2024-01")
EXPECTED_PART110_PROPOSAL_PAGES = ("47837", "89644", "89646", "89648")
MAX_SOURCE_BYTES = 10 * 1048576


class LSAComparisonError(ValueError):
    """Official historical-source evidence is missing, oversized or ambiguous."""


class _GovInfoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        parsed = urlsplit(newurl)
        if parsed.scheme != "https" or parsed.netloc != "www.govinfo.gov":
            raise LSAComparisonError("GovInfo source redirect may not change host")
        return super().redirect_request(request, fp, code, message, headers, newurl)


def _source_url(month: str) -> str:
    if month not in MONTHS:
        raise LSAComparisonError("Unsupported historical monthly LSA source")
    return f"https://www.govinfo.gov/content/pkg/LSA-{month}/pdf/LSA-{month}.pdf"


def _fetch_source(opener, month: str):
    url = _source_url(month)
    request = Request(url, headers={
        "User-Agent": "HarborLens-GovInfo-Source-Audit/0.1",
        "Accept": "application/pdf",
    })
    with opener(request, timeout=60) as response:
        declared = getattr(response, "headers", {}).get("Content-Length")
        if declared is not None and int(declared) > MAX_SOURCE_BYTES:
            raise LSAComparisonError("Official LSA exceeds size cap")
        raw = response.read(MAX_SOURCE_BYTES + 1)
    if not raw.startswith(b"%PDF-") or len(raw) > MAX_SOURCE_BYTES:
        raise LSAComparisonError("Official LSA is missing, invalid or oversized")
    return url, raw


def _extract_title33(reader):
    if not (25 < len(reader.pages) < 300):
        raise LSAComparisonError("Unexpected source PDF page count")
    pages = [p.extract_text() or "" for p in reader.pages]
    starts = [i for i, body in enumerate(pages)
              if re.search(r"TITLE\s*33\s*[-—]?\s*NAVIGATION", body, re.I)]
    if not starts:
        raise LSAComparisonError("Cannot establish Title 33 start in extracted PDF")
    start = starts[0]
    ends = [i for i in range(start + 1, len(pages))
            if re.search(r"TITLE\s*34\s*[-—]?\s*EDUCATION", pages[i], re.I)]
    if not ends:
        raise LSAComparisonError("Cannot establish Title 33 end in extracted PDF")
    end = ends[0]
    content = "\n".join(pages[start:end])
    if len(content) < 300:
        raise LSAComparisonError("Title 33 extracted content is unexpectedly short")
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


def compare_official_lsa(opener=None, reader_factory=None):
    """Collect two source receipts while refusing to infer a legal result."""
    client = opener or build_opener(_GovInfoRedirects()).open
    if reader_factory is None:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise LSAComparisonError(
                "Install optional dependency: pip install 'pypdf>=5,<7'"
            ) from exc
        reader_factory = lambda content: PdfReader(io.BytesIO(content), strict=True)
    documents = {}
    for month in MONTHS:
        url, raw = _fetch_source(client, month)
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
        documents[month] = {
            "official_pdf_url": url,
            "official_pdf_sha256": hashlib.sha256(raw).hexdigest(),
            "pdf_page_count": len(reader.pages),
            "title33_pdf_pages_1based": [first_page, last_page],
            "title33_extracted_text_sha256": hashlib.sha256(scoped.encode("utf-8")).hexdigest(),
            "target_110_197_direct_occurrences": len(re.findall(
                r"(?<!\d)110\s*\.\s*197(?!\d)", scoped
            )),
            "part110_proposed_fr_pages": list(proposal),
        }
    return {
        "schema_version": "govinfo-lsa-dec-jan-v1",
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source_months": list(MONTHS),
        "documents": documents,
        "proposed_part110_pages_match": True,
        "study_target": "33 CFR 110.197 on 2024-01-02",
        "legal_effect_on_study_date": "NOT_DETERMINED",
        "intervening_amendments_excluded": False,
        "historical_wgs84_geometry_approved": False,
        "ais_spatial_join_permitted": False,
        "mandatory_follow_up": (
            "Cross-check original Federal Register/LSA and effective-date history with qualified reviewers; "
            "a cumulative LSA and an absent direct section entry cannot prove unchanged legal status."
        ),
    }


def save_report(output: Path, opener=None, reader_factory=None):
    output = Path(output)
    if output.suffix.lower() != ".json" or output.exists():
        raise LSAComparisonError("Output must be a new .json report")
    report = compare_official_lsa(opener, reader_factory)
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


def main():
    parser = argparse.ArgumentParser(description="Compare official 2023-12/2024-01 Title 33 LSA source indexes")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    report = save_report(args.out)
    print(json.dumps({
        "source_months": report["source_months"],
        "official_pdf_sha256": {k: v["official_pdf_sha256"] for k,v in report["documents"].items()},
        "source_index_consistent": report["proposed_part110_pages_match"],
        "legal_effect_on_study_date": report["legal_effect_on_study_date"],
        "ais_spatial_join_permitted": False,
    }, indent=2))


if __name__ == "__main__":
    main()
