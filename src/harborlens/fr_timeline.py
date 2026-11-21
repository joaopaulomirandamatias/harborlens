"""Conservative U.S. Federal Register Part 110 publication-index audit (SPEC-004).

Lists indexed documents published in a bounded historical window. The index
alone cannot prove exact-day CFR legal effect, document text, or geometries.
Opt-in HTTPS only; no automatic regulatory decisions or AIS spatial joins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit, parse_qs
from urllib.request import Request, urlopen

from harborlens.timeparse import parse_calendar_date

API = "https://www.federalregister.gov/api/v1/documents.json"
MAX_PAGES = 10
MAX_RECORDS = 300
MAX_BYTES = 2 * 1048576
MAX_WINDOW_DAYS = 370
EARLIEST_PUBLICATION = date(1994, 1, 1)

# One line each. The span rule keeps the historical 370-day sentence.
# The other three rules used to share that sentence, which is wrong for them.
MSG_START_AFTER_END = "Start date must be on or before the end date"
MSG_END_AFTER_TODAY = "End date must be on or before today"
MSG_START_BEFORE_1994 = "Start date must be on or after 1994-01-01"
MSG_WINDOW_SPAN = "Use a historical publication window of at most 370 days"


class FederalRegisterAuditError(ValueError):
    """Missing, malformed, truncated or out-of-scope Federal Register evidence."""


def _date(value):
    """Accept ASCII ``YYYY-MM-DD`` only.

    An ISO week date such as ``2024-W01-1`` is ten characters and is a real
    day on Python 3.11+, so a length check is not the grammar. ``YYYYMMDD``
    is also rejected. 29 February is accepted only in a leap year.
    """
    try:
        return parse_calendar_date(value)
    except ValueError as exc:
        raise FederalRegisterAuditError("Date must be YYYY-MM-DD") from exc


def _today():
    """Local calendar day for the publication window.

    Tests replace this. Production uses ``date.today()``.
    """
    return date.today()


def validate_window(start, end, today=None):
    """Apply the four publication-window rules. No network.

    Order is start after end, end after today, start before 1994-01-01,
    then a span of more than 370 days. The first broken rule wins.
    ``today`` defaults to ``_today()``. A span of exactly 370 days, a start
    equal to the end, an end equal to today, and a start equal to
    1994-01-01 all pass.
    """
    a, b = _date(start), _date(end)
    if today is None:
        today = _today()
    if a > b:
        raise FederalRegisterAuditError(MSG_START_AFTER_END)
    if b > today:
        raise FederalRegisterAuditError(MSG_END_AFTER_TODAY)
    if a < EARLIEST_PUBLICATION:
        raise FederalRegisterAuditError(MSG_START_BEFORE_1994)
    if (b - a).days > MAX_WINDOW_DAYS:
        raise FederalRegisterAuditError(MSG_WINDOW_SPAN)
    return a, b


def initial_url(start, end, per_page=100, today=None):
    # Defense in depth: ``main`` checks the window before any Request.
    # Building this URL checks the same rules again and does not open a socket.
    validate_window(start, end, today)
    if not (1 <= per_page <= 100):
        raise FederalRegisterAuditError("Page size must be between 1 and 100")
    return API + "?" + urlencode({
        "conditions[cfr][title]": "33",
        "conditions[cfr][part]": "110",
        "conditions[publication_date][gte]": start,
        "conditions[publication_date][lte]": end,
        "per_page": per_page,
        "order": "oldest",
    })


def _validate_page_url(url):
    u = urlsplit(url)
    if (u.scheme != "https" or u.netloc != "www.federalregister.gov"
            or u.path != "/api/v1/documents.json" or u.username or u.password or u.fragment):
        raise FederalRegisterAuditError("Federal Register pagination must stay on the fixed official API")
    arguments = parse_qs(u.query)
    if arguments.get("conditions[cfr][title]") != ["33"] or arguments.get("conditions[cfr][part]") != ["110"]:
        raise FederalRegisterAuditError("Pagination must retain the requested 33 CFR Part 110 scope")
    if not arguments.get("conditions[publication_date][gte]") or not arguments.get("conditions[publication_date][lte]"):
        raise FederalRegisterAuditError("Pagination must retain date filters")
    return url


def _fetch(opener, url):
    _validate_page_url(url)
    request = Request(url, headers={
        "User-Agent": "HarborLens-open-research/0.1",
        "Accept": "application/json",
    })
    with opener(request, timeout=45) as response:
        declared = getattr(response, "headers", {}).get("Content-Length")
        if declared is not None and int(declared) > MAX_BYTES:
            raise FederalRegisterAuditError("Response exceeds download byte limit")
        raw = response.read(MAX_BYTES+1)
        if len(raw) > MAX_BYTES:
            raise FederalRegisterAuditError("Response exceeds download byte limit")
    try:
        obj = json.loads(raw)
    except (ValueError, UnicodeError) as exc:
        raise FederalRegisterAuditError("Official API response is not valid JSON") from exc
    if not isinstance(obj, dict) or not isinstance(obj.get("results"), list):
        raise FederalRegisterAuditError("Official API response lacks a results array")
    return obj, hashlib.sha256(raw).hexdigest()


def _doc_record(item, start, end):
    if not isinstance(item, dict):
        raise FederalRegisterAuditError("Malformed document index entry")
    number = item.get("document_number")
    title = item.get("title")
    published = item.get("publication_date")
    if not isinstance(number, str) or not number or not isinstance(title, str):
        raise FederalRegisterAuditError("Missing Federal Register document number/title")
    if not (start <= _date(published) <= end):
        raise FederalRegisterAuditError("Document publication date falls outside requested window")
    official = item.get("html_url")
    if official is not None and (not isinstance(official, str) or not official.startswith("https://www.federalregister.gov/")):
        raise FederalRegisterAuditError("Unexpected document link outside official publication host")
    return {
        "document_number": number,
        "publication_date": published,
        "effective_on": item.get("effective_on"),
        "type": item.get("type"),
        "title": title,
        "html_url": official,
        "cfr_references": item.get("cfr_references"),
        "abstract": (item.get("abstract") or "")[:1500],
        "review_status": "requires_manual_section_and_effective_date_review",
    }


def scan_part110(start="2023-07-01", end="2024-01-02", opener=None, per_page=100):
    """Scan a bounded Part 110 publication index; no claims about absent rules."""
    a, b = _date(start), _date(end)
    url = initial_url(start, end, per_page)
    client = opener or urlopen
    records, pages, seen_urls, ids = [], [], set(), set()
    expected_count = None
    while url:
        if len(pages) >= MAX_PAGES or url in seen_urls:
            raise FederalRegisterAuditError("Pagination loop or page limit exceeded")
        seen_urls.add(url)
        item, sha = _fetch(client, url)
        count = item.get("count")
        if not isinstance(count, int) or count < 0 or count > MAX_RECORDS:
            raise FederalRegisterAuditError("Unbounded or malformed Federal Register total count")
        if expected_count is None:
            expected_count = count
        if expected_count != count:
            raise FederalRegisterAuditError("Total count changed during index scan")
        page_records = item["results"]
        for doc in page_records:
            entry = _doc_record(doc, a, b)
            if entry["document_number"] in ids:
                raise FederalRegisterAuditError("Repeated Federal Register document number across pages")
            records.append(entry)
            ids.add(entry["document_number"])
            if len(records) > MAX_RECORDS:
                raise FederalRegisterAuditError("Index result cap exceeded")
        pages.append({"url": url, "response_sha256": sha, "records": len(page_records)})
        nxt = item.get("next_page_url")
        if nxt is not None and not isinstance(nxt, str):
            raise FederalRegisterAuditError("Invalid next_page_url")
        url = _validate_page_url(nxt) if nxt else None
    if len(records) != expected_count:
        raise FederalRegisterAuditError("Incomplete paginated index; no legal conclusion may be drawn")
    records.sort(key=lambda row: (row["publication_date"], row["document_number"]))
    return {
        "schema_version": "fr-part110-index-audit-v1",
        "source_api": API,
        "cfr_scope": "33 CFR Part 110",
        "requested_publication_window": {"from": start, "through": end},
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "count": len(records),
        "query_pages": pages,
        "documents": records,
        "index_pagination_complete": True,
        "cfr_section_110_197_effective_state": "NOT_DETERMINED",
        "intervening_amendments_excluded": False,
        "no_result_interpretation": "No indexed document is not proof of no actual legal changes.",
        "mandatory_follow_up": [
            "Review each indexed document official text for 33 CFR 110.197 and effective dates.",
            "Cross-check official GPO List of CFR Sections Affected and Federal Register source records.",
            "Confirm agency/court effective dates and any corrections before any historical legal conclusions.",
        ],
        "ais_spatial_join_permitted": False,
        "warning": "Official publication-index search only, not legal certification or historical WGS84 geofence validity.",
    }


def save_scan(out, start="2023-07-01", end="2024-01-02", opener=None):
    out = Path(out)
    if out.suffix.lower() != ".json" or out.exists():
        raise FederalRegisterAuditError("Output must be a new .json file")
    report = scan_part110(start, end, opener)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(out.name+".partial")
    try:
        with tmp.open("x", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
        os.replace(tmp, out)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return report


def main():
    parser = argparse.ArgumentParser(description="Screen official FR 33 CFR Part 110 publication index; no legal conclusions")
    parser.add_argument("--start", default="2023-07-01",
                   help="YYYY-MM-DD calendar date; week dates and YYYYMMDD are rejected")
    parser.add_argument("--end", default="2024-01-02", help="YYYY-MM-DD calendar date")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    # Calendar text and the four window rules exit 2 here, before save_scan
    # builds a Request or calls urlopen. Catch only FederalRegisterAuditError.
    # A bare ValueError and KeyboardInterrupt propagate.
    try:
        validate_window(args.start, args.end)
    except FederalRegisterAuditError as exc:
        parser.error(str(exc))
    result = save_scan(args.out, args.start, args.end)
    print(json.dumps({
        "documents_for_review": result["count"],
        "query_pages": len(result["query_pages"]),
        "section_110_197_legal_state": "NOT_DETERMINED",
        "ais_spatial_join_permitted": False,
    }, indent=2))


if __name__ == "__main__":
    main()
