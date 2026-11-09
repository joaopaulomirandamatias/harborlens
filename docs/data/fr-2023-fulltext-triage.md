# Official Federal Register Full-Text Triage — Four 2023 Part 110 Documents

**SPEC-004 | Research-only document triage. No legal conclusion or vessel-event verification.**

## Purpose

The [Federal Register Part 110 index](fr-part110-real-index-2023-2024.md) returned four documents from July 1, 2023 through January 2, 2024. The index is not sufficient to determine whether **33 CFR 110.197 (Galveston/Bolivar Roads)** was amended during that period. An index can show a document under Part 110 even when it concerns a different waterway.

The new optional full-text triage client retrieves each **official FederalRegister.gov metadata JSON** and its **original raw published text**, never a third-party mirror. No data or text is automatically downloaded on install or through the AIS analysis commands. It preserves the original metadata and raw-text SHA-256 checksums in a versioned JSON report; source text is not copied into Git.

## Included document identifiers

- 2023-15652 — Anchorage Grounds, Hudson River; Yonkers, NY to Kingston, NY. The original describes withdrawal of an advance notice of proposed rulemaking. The API indexes it as Proposed Rule.
- 2023-28652 — Port Westward Anchorage, Columbia River, Oregon and Washington; proposal.
- 2023-28654 — Crims Island Anchorage, Columbia River, Oregon and Washington; proposal.
- 2023-28656 — Rice Island Anchorage, Columbia River, Oregon and Washington; proposal.

These four titles point outside Galveston/Houston. The code nevertheless searches the official text for the literal target section number and for locality signals. A keyword match is an investigation prompt, **not** proof of a final or effective rule. A text with no keywords is NOT proof that no regulation changed.

## Explicit command

~~~bash
python -m pip install -e '.[dev]'
harborlens-fr-fulltext --out results/fr-2023-official-text-review.json
~~~

The client allows exactly the four previously indexed document IDs. The metadata URL, text URL, publication date and file paths must match a tightly validated HTTPS FederalRegister.gov pattern, with cross-host redirects forbidden and response byte limits. Any missing, inconsistent, oversized or malformed response fails the entire run without producing a partial report.

The report contains document numbers, publication dates, indexed types, official URLs, exact byte hashes, short metadata titles and keyword flags; **not the bulk government documents or invented legal decisions**. The [JSON Schema](../../schemas/v1/fr-official-text-triage.schema.json) enforces no automatic approval.

## Mandatory next verification

The [Government Publishing Office List of CFR Sections Affected (LSA)](https://www.govinfo.gov/help/lsa) is published monthly and records section-level changes, including proposed/final classifications and Federal Register pages. A complete legal timeline must additionally examine the official 2023-12 LSA (Title 33) and any coverage gap through January 2, 2024, alongside original Federal Register publications and effective-date rules.

The four documents' results cannot substitute for an actual historical legal revision audit, source datum determination, expert reconstruction of the A East polygon, or independent vessel/terminal events. HarborLens continues to block historical AIS-to-regulatory-polygon joins.

**NOT FOR NAVIGATION. NOT LEGAL CERTIFICATION.**
