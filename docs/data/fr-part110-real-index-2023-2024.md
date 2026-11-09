# Federal Register Part 110 Publication Index — July 2023 to January 2024

**Evidence date:** 2026-11-09 UTC.  
**Official API integration:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42660580421  
**Purpose:** Indexed federal rulemaking-document discovery only; NOT a conclusive legal effective-date assessment or approved AIS geofence.

## Query and source fingerprints

- Provider: Office of the Federal Register, public API at https://www.federalregister.gov/api/v1/documents.json
- Filters: CFR title 33 and part 110; publication dates 2023-07-01 through 2024-01-02 inclusive; all document types.
- Pagination: 1 complete page, 4 indexed results.
- API response SHA-256: 8fca3dac28d9d2f49fc40c36ff78d7f6b0ad2b7b4e231e2543023f3585acf602
- Locally produced timeline JSON SHA-256: 804d2adabe58ed685013e8a3f476904fdb0e7240904739dc6ca082977c2cd99e

## Official index output

| Document number | Published | Indexed document type | Effective date in API |
| --- | --- | --- | --- |
| 2023-15652 | 2023-07-25 | Proposed Rule | null |
| 2023-28652 | 2023-12-28 | Proposed Rule | null |
| 2023-28654 | 2023-12-28 | Proposed Rule | null |
| 2023-28656 | 2023-12-28 | Proposed Rule | null |

All four entries are proposals according to the API metadata. There was **no final-rule type returned within this exact indexed query**, but this is not proof that §110.197 was unamended or legally unchanged on 2024-01-02. A rule published earlier with a delayed effective date or a document not cross-indexed to Part 110 could be missed.

The 2023-15652 document concerns Hudson River, New York, rather than Galveston, but it remains in the evidence inventory to preserve the complete Part 110 query result. The three December documents require individual full-text review.

## Related engineering evidence and outstanding legal gates

The source-pinned [official annual 2023/2024 CFR comparison](cfr-2023-2024-source-verification.md) independently found the sixteen printed DMS corner pairs in both editions. That agreement is useful but still does not rule out intervening amendments and effective dates.

- Legal effective state of 33 CFR §110.197 on 2024-01-02: NOT DETERMINED.
- Intervening amendments excluded: NO.
- Automatic AIS join with printed legal polygons: BLOCKED.
- Historical WGS84 legal anchorage geometry: NOT VERIFIED.
- Confirmed maritime events inferred: NONE.
- Federal Register integration workflow: MANUAL ONLY.
- No original AIS records or source polygon coordinates committed or uploaded.

**Next:** read the official full texts of all four indexed documents; cross-check GPO List of CFR Sections Affected (LSA), publication/effective dates and any relevant corrections; resolve missing A/B/C geodetic datum and A East invalid literal ring via Coast Guard materials and reviewer. Only independently reviewed, date-appropriate geometries may be considered for AIS spatial context, never automatic waiting/berthing confirmation.

**NOT FOR NAVIGATION. NOT A LEGAL OPINION OR CONFIRMED PORT OPERATION EVIDENCE.**

## Original full-text evidence

The [official original-text inspection report](fr-2023-original-fulltext-evidence-2026-11-09.md) includes original URLs and SHA-256 for all four 2023 documents, with negative direct 110.197 and Houston/Galveston text hits. An API index with complete pages and texts still does not replace GPO LSA or authoritative legal effective-date review.
