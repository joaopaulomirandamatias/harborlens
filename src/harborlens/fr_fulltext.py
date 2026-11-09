"""Bounded official Federal Register full-text triage for 2023 Part 110.

Metadata and original government text are fetched only on explicit invocation.
A text search does NOT establish applicability, final-rule effect, completeness,
historical polygon datum, or permission to perform AIS spatial joins.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen, build_opener, HTTPRedirectHandler

DOCUMENTS = (
    ("2023-15652", "2023-07-25"),
    ("2023-28652", "2023-12-28"),
    ("2023-28654", "2023-12-28"),
    ("2023-28656", "2023-12-28"),
)
MAX_METADATA = 256 * 1024
MAX_TEXT = 2 * 1048576


class FullTextAuditError(ValueError):
    """Official source text cannot be fully and safely assessed."""


def _validate(url: str, number: str, published: str, kind: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.netloc != "www.federalregister.gov" or parts.username or parts.password or parts.fragment:
        raise FullTextAuditError("Source must stay on official Federal Register HTTPS host")
    if kind == "meta":
        expected = f"/api/v1/documents/{number}.json"
    else:
        expected = f"/documents/full_text/text/{published.replace('-', '/')}/{number}.txt"
    if parts.path != expected or parts.query:
        raise FullTextAuditError("Source path does not match the expected document/date")
    return url


class _OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, file_pointer, code, message, headers, newurl):
        host = urlsplit(newurl)
        if host.scheme != "https" or host.netloc != "www.federalregister.gov":
            raise FullTextAuditError("Cross-host redirect is forbidden for source audit")
        return super().redirect_request(request, file_pointer, code, message, headers, newurl)


def _fetch(opener, url, limit):
    request=Request(url,headers={"Accept":"application/json, text/plain", "User-Agent":"HarborLens-source-audit/0.1"})
    with opener(request,timeout=45) as response:
        declared=getattr(response,"headers",{}).get("Content-Length")
        if declared is not None and int(declared)>limit:
            raise FullTextAuditError("Official source response exceeds size cap")
        data=response.read(limit+1)
    if not data or len(data)>limit:
        raise FullTextAuditError("Official source response empty or oversized")
    return data, hashlib.sha256(data).hexdigest()


def inspect_documents(opener=None):
    """Scan exactly four source-pinned published records, no external links followed."""
    client = opener or build_opener(_OfficialRedirects()).open
    records=[]
    for number,published in DOCUMENTS:
        metadata_url=_validate(f"https://www.federalregister.gov/api/v1/documents/{number}.json",number,published,"meta")
        raw_meta,meta_sha=_fetch(client,metadata_url,MAX_METADATA)
        try:
            meta=json.loads(raw_meta.decode("utf-8"))
        except (ValueError,UnicodeError) as exc:
            raise FullTextAuditError("Official document metadata was not valid JSON") from exc
        if not isinstance(meta,dict) or meta.get("document_number")!=number or meta.get("publication_date")!=published:
            raise FullTextAuditError("Official document metadata ID/date mismatch")
        raw_url=meta.get("raw_text_url")
        if not isinstance(raw_url,str):
            raise FullTextAuditError("Official document lacks raw_text_url")
        _validate(raw_url,number,published,"text")
        raw,source_sha=_fetch(client,raw_url,MAX_TEXT)
        try:
            text=raw.decode("utf-8-sig")
        except UnicodeError as exc:
            raise FullTextAuditError("Official text was not valid UTF-8") from exc
        normalized=" ".join(text.split())
        if len(normalized)<300:
            raise FullTextAuditError("Official document text unexpectedly short")
        # Text matching is a search-assistance signal, not statutory interpretation.
        section_hits=bool(re.search(r"(?<!\d)110\s*\.\s*197(?!\d)",normalized))
        region_hits={
            "galveston_or_houston": bool(re.search(r"\b(Galveston|Houston|Bolivar\s+Roads)\b",normalized,re.I)),
            "columbia_river": bool(re.search(r"\bColumbia\s+River\b",normalized,re.I)),
            "hudson_river": bool(re.search(r"\bHudson\s+River\b",normalized,re.I)),
        }
        title=meta.get("title")
        if not isinstance(title,str) or not title:
            raise FullTextAuditError("Official document has no title")
        record={
            "document_number":number,
            "publication_date":published,
            "official_metadata_url":metadata_url,
            "official_raw_text_url":raw_url,
            "official_html_url":meta.get("html_url"),
            "metadata_sha256":meta_sha,
            "raw_text_sha256":source_sha,
            "text_characters":len(normalized),
            "title":title,
            "indexed_document_type":meta.get("type"),
            "indexed_effective_date":meta.get("effective_on"),
            "text_mentions_110_197":section_hits,
            "location_text_signals":region_hits,
            "text_mentions_withdrawal":bool(re.search(r"\bwithdra(w|wal|wn)\b",normalized,re.I)),
            "review_status":"human_review_full_text_and_legal_effect_required",
        }
        records.append(record)
    return {
        "schema_version":"fr-2023-official-text-audit-v1",
        "sources":"Official FederalRegister.gov document API and raw published text",
        "retrieved_at_utc":datetime.now(timezone.utc).isoformat().replace("+00:00","Z"),
        "document_count":len(records),
        "documents":records,
        "full_text_fetch_complete":True,
        "lsa_full_review_complete":False,
        "section_110_197_historical_effect":"NOT_DETERMINED",
        "ais_geofence_approval":False,
        "warning":"Keyword search is not legal effect, an exhaustive LSA check, geographic approval or verified vessel status.",
    }


def save_review(path,opener=None):
    path=Path(path)
    if path.suffix.lower()!=".json" or path.exists():
        raise FullTextAuditError("Output must be a new .json file")
    result=inspect_documents(opener)
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+".partial")
    try:
        with temp.open("x",encoding="utf-8") as stream:
            json.dump(result,stream,indent=2)
        os.replace(temp,path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    return result


def main():
    parser=argparse.ArgumentParser(description="Triage four official 2023 Federal Register Part 110 full texts")
    parser.add_argument("--out",type=Path,required=True)
    args=parser.parse_args()
    result=save_review(args.out)
    print(json.dumps({
        "documents_fetched":result["document_count"],
        "section_110_197_mentions":sum(d["text_mentions_110_197"] for d in result["documents"]),
        "historical_legal_status":result["section_110_197_historical_effect"],
        "lsa_review_complete":False,
    },indent=2))


if __name__=="__main__":
    main()
