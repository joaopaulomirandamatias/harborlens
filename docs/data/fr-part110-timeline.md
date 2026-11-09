# Official Federal Register Part 110 Index: Historical Change Screening

**SPEC-004 · Discovery aid only — not a legal determination or geographic authorization.**

## Purpose

Although official [2023](https://www.govinfo.gov/content/pkg/CFR-2023-title33-vol1/html/CFR-2023-title33-vol1.htm) and [2024](https://www.govinfo.gov/content/pkg/CFR-2024-title33-vol1/html/CFR-2024-title33-vol1.htm) annual CFR editions reproduce the same sixteen corner-coordinate pairs under 33 CFR 110.197, annual texts alone cannot prove there were no intervening Federal Register amendments effective on January 2, 2024. The [U.S. Government Publishing Office guidance](https://www.govinfo.gov/features/searching-fr) explains searches by CFR citation and section; the official Federal Register API indexes rulemaking publications for specific CFR title/part and dates.

The opt-in CLI retrieves an index of **documents affecting 33 CFR Part 110** between July 1, 2023 and January 2, 2024. It does not narrow results to only documents with "Galveston" in the title. Human review must determine whether a document amended §110.197 and verify legal effective dates and corrections in the official PDF/FR and monthly LSA.

## Reproducible command (network opt-in)

~~~bash
python -m pip install -e '.[dev]'
harborlens-fr-timeline \
  --start 2023-07-01 \
  --end 2024-01-02 \
  --out results/fr-part110-2023-to-2024.json
~~~

The CLI uses the fixed FederalRegister.gov public API with bounded query time, total results, page length and response size. It preserves source API query URLs and per-page SHA-256 fingerprints as part of a structured source evidence report. Only the official Federal Register index metadata and short abstracts are included; no bulk full texts are uploaded. Automated tests mock every network response.

## Interpretive limitations

- A retrieved entry is a **document candidate for review**, not automatically a relevant legal amendment to the exact section.
- A result of zero indexed documents is **not proof** there was no amendment or that geography was legally valid.
- A complete paginated API response is **not a complete audit of publication text**: indexing may omit document cross-references or later effective rules.
- Publication date is NOT the same as effective date or date of legal enforcement.
- An AIS study dated January 2, 2024 requires exact historical edition review, LSA (List of CFR Sections Affected), Federal Register amendments and any relevant corrections.
- The four CFR area coordinates are still **not** approved WGS84 polygons: A/B/C datum and A East vertex-order topology remain unresolved in [the official-source comparison](cfr-2023-2024-source-verification.md).
- No AIS spatial join, official anchorage, berth occupancy, vessel waiting claim or navigation use is permitted by the tool.

**Next engineering step:** review and cite each candidate official rule text, check the monthly LSA, and preserve the exact source/effective-date evidence before a qualified reviewer authorizes historic legal conclusions.

## First official live index scan (2026-11-09)

The [source-pinned research report](fr-part110-real-index-2023-2024.md) logs four Proposed Rule index entries returned for the study window, one official response-page hash and the JSON output hash. A fully returned search page is not a full legal timeline or verification of 33 CFR 110.197 on January 2, 2024.

## Original document verification

The [full-text triage guide](fr-2023-fulltext-triage.md) verifies the original official text files for the four index hits. GPO monthly LSA and exact legal effective-date review remain separate requirements; a matching keyword or a nonmatching text is never a legal conclusion.
