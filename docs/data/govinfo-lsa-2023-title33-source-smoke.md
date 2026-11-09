# Official December 2023 GPO List of CFR Sections Affected — Title 33 Screen

**Evidence date:** 2026-11-09 UTC.  
**Isolated successful source run:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42669885527  
**Purpose:** Confirm a bounded official historical LSA source and inspect the Title 33 change index. **NOT a conclusive determination that 33 CFR 110.197 was unchanged or in effect on January 2, 2024.**

## Primary official document

- **GPO monthly LSA:** https://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf
- **Exact downloaded PDF SHA-256:** c226121a7617f1b4578a0fcf79f58d4735696e0405c5522615699bdb5bab037d
- **PDF pages:** 117.
- **CFR Title 33 section:** PDF pages **79–81** (zero-based page indices 78–80).
- **Extracted Title 33 text SHA-256 (pypdf):** 8f0e63f8f76493c2bf891a5dfc8a0fff736f1c04910ca2a20b40199ad001ef63
- **Coverage according to source:** changes **July 3 through December 29, 2023** in Title 33, part of the monthly list of sections affected.
- Source was retrieved inside an ephemeral GitHub Actions job. Only aggregate findings and hashes were printed; the raw source PDF was not committed or uploaded.

## Observations (source-screening, not an opinion on legal status)

| LSA text check, confined to Title 33 | Observed value |
| --- | --- |
| Direct occurrences of **110.197** | **0** |
| Proposed Rules reference for **Part 110** | **110 — 47837, 89644, 89646, 89648** |
| Evidence of no amendments effective on January 2, 2024 | **NOT ESTABLISHED** |
| Authorized HarborLens WGS84 regulatory polygons | **NONE** |
| Validated anchorage / waiting / berthing events | **NONE** |

The lack of a literal 110.197 reference in the extracted Title 33 section is a useful *negative search finding*, not a guarantee of exhaustive legal coverage. The proposed-rule entry is recorded in the appropriate proposed-rules portion of the source; it does not imply that four final rules modified Houston/Galveston.

## Relationship to the previous official-source screens

- [2023/2024 annual CFR GPO comparison](cfr-2023-2024-source-verification.md): all 16 printed DMS coordinate pairs for §110.197 match in both annual editions.
- [Federal Register Part 110 publication index](fr-part110-real-index-2023-2024.md): four candidate proposed-rule records in the bounded period.
- [Four original official Federal Register texts](fr-2023-original-fulltext-evidence-2026-11-09.md): no direct 110.197 or Houston/Galveston text hit in those four originals.
- This official LSA screen adds independent publication-level context, but does not certify the effective legal status on **2024-01-02**.

## Why the historical date still needs review

The December monthly LSA runs through **December 29**, while our target observation date is **January 2**. An exact legal audit must also account for applicable Federal Register publications or effective-date actions in the gap, rules published outside this period but effective later, section-level indexing limits and agency clarifications. It should review relevant original 88 FR pages and the December LSA against the printed CFR and any necessary 2024 early-January Reader Aids.

**Independent GIS blockers also remain:** Anchoring areas A/B/C have unspecified source datum under 33 CFR 110.1(d). A East has a non-simple literal vertex order in its printed DMS corner list. Neither may automatically be promoted to navigation-grade WGS84 polygons. Historical source/date evidence is not evidence that a vessel actually anchored or waited.

## Reproducibility notes

The manual-only GitHub Actions workflow uses the fixed GPO official PDF URL, limits the retrieved file size, asserts PDF signature, extracts text with pypdf, locates the Title 33 section between the Title 33 and Title 34 headings, records document and scoped-text SHA-256, and searches literal section references and proposed-rule entries. The workflow is intended as a reproducible engineering source screen, not a general PDF-to-law interpretation engine. PDF textual extraction is itself a potential source of false negatives; human review of the source pages remains necessary.

**Next:** manual verification of the original official page references 47837, 89644, 89646, 89648 and the early-January 2024 publication/effective-date gap, plus original geodetic/geometry resolution.

**NOT FOR NAVIGATION. NO CERTIFIED REGULATORY GEOMETRY OR VESSEL OPERATIONS.**
