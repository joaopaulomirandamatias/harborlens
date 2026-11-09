# Official 2023-12 vs 2024-01 GPO LSA Title 33 Source Comparison

**SPEC-004 | Implementation status: synthetic regression tests complete; official two-PDF reproducibility run pending.** This file is an engineering procedure, not a certificate that 33 CFR 110.197 was legally unchanged on January 2, 2024.

## Why compare these two issues?

The [December 2023 List of CFR Sections Affected (LSA)](https://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf) records changes through December 29, 2023. The cumulative [January 2024 LSA](https://www.govinfo.gov/content/pkg/LSA-2024-01/pdf/LSA-2024-01.pdf) extends the Title 33 change index through January 31, 2024. The target HarborLens study date, January 2, 2024, lies between these two cumulative editions.

The January 2024 official Title 33 text index lists **33 CFR Part 110** under *Proposed Rules* with FR pages 47837, 89644, 89646, and 89648; the earlier December LSA source screen reported the same four references. In the available extracted January Title 33 text, no direct 110.197 amended-section entry appears. These are negative *index-level observations*, not an exhaustive legal-effect determination.

The official 2023/2024 GPO annual CFR source text and the [Federal Register original-document triage](fr-2023-original-fulltext-evidence-2026-11-09.md) establish independent sources to reconcile. That prior document triage found four documents whose text concerned the Hudson and Columbia rivers, not Galveston.

## New reproducible offline/regression-tested code

Run explicitly from an installed HarborLens checkout:

~~~bash
python -m pip install -e .
python -m pip install 'pypdf>=5,<7'
python -m harborlens.lsa_compare --out results/lsa-2023-12-versus-2024-01.json
~~~

The code makes fixed, opt-in HTTPS requests to GovInfo for exactly the two monthly PDF URLs, limits the bytes and number of pages, requires a recognizable Title 33 / Title 34 section boundary, and refuses ambiguous Part 110 dotted-leader entries. It reports:

- SHA-256 of each original downloaded PDF;
- Title 33 physical PDF page range and extracted-text SHA-256;
- count of direct 110.197 text occurrences;
- Part 110 Proposed Rules FR-page references in both issues;
- mandatory legal-effect NOT_DETERMINED, historical-WGS84-geometry not approved, and AIS spatial joins forbidden.

No original source PDF, AIS records or nautical chart polygons should be committed or uploaded. A positive match of the four proposed-rule references does **not** imply those proposals became operative final amendments.

## Current validation evidence and limits

The module has synthetic tests for official-source boundedness, source section discovery, page-reference drift, missing/ambiguous sections, forged result approval and output overwrite prevention. The production PDF reader is an optional dependency; no PDF is needed to run normal AIS tests.

An initial experimental GitHub workflow for real source reproduction failed before scheduling a job. A shorter second version also failed before job execution. **These failures are not successful source verification**; the unverified workflow has been excluded from the merge. No new official PDF SHA-256 or live PDF parsing result is claimed by this change.

The official current eCFR/NOAA nautical geometry remains a separate data type from regulatory section text. Further source review must examine the official January 2024 Federal Register early dates, amendments already published but effective later, the December/January LSA source pages and any Coast Guard corrections.

## Remaining issue #7 gates

1. Execute the source-pinned Dec/Jan GovInfo PDF comparison in a verified environment and preserve source hash, page range and no-approval results.
2. Independently review original Federal Register legal effective-date records, including rules published before the search window with later effective dates.
3. Resolve A/B/C geodetic datum ambiguity under 33 CFR 110.1(d) and A East printed-ring topology through Coast Guard exhibits or qualified review.
4. Only after a documented, legally date-valid WGS84 geometry is approved, compare historical AIS spatial evidence — **never** treat the presence of a vessel inside a polygon as proof of anchoring or waiting.

**NOT FOR NAVIGATION. NO VERIFIED 2024 REGULATORY GEOMETRY OR MARITIME OPERATIONAL CLASSIFICATION.**
