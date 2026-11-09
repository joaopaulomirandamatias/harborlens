# Full-text Verification of Four Official 2023 Federal Register Part 110 Documents

**Evidence date:** 2026-11-09 UTC.  
**Verified GitHub Actions run:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42668693954  
**Scope:** source and keyword triage only. No legal certification, no operative January 2024 geofence, and no validated vessel event.

## Official documents and original source integrity

All four indexed documents were retrieved directly from the **FederalRegister.gov official document metadata API and original raw published text URLs**, with strict host/date/document-number validation and response size limits. The source text itself is not committed to this repository.

| Document | Published | Original subject / area | Does text mention 33 CFR 110.197? | Does text mention Houston / Galveston? | Raw-text SHA-256 |
| --- | --- | --- | --- | --- | --- |
| [2023-15652](https://www.federalregister.gov/documents/full_text/text/2023/07/25/2023-15652.txt) | 2023-07-25 | Hudson River, New York; withdrawal text signal | No | No | 854eabd3e5eba0f91749682c8cb0f78c21b83441c5a29a9fc8e98aad470e206f |
| [2023-28652](https://www.federalregister.gov/documents/full_text/text/2023/12/28/2023-28652.txt) | 2023-12-28 | Port Westward, Columbia River, OR/WA | No | No | 617c4aeefc3678039410ed4a04fa6f8ad60296a90271bc20d88fca0566af9c46 |
| [2023-28654](https://www.federalregister.gov/documents/full_text/text/2023/12/28/2023-28654.txt) | 2023-12-28 | Crims Island, Columbia River, OR/WA | No | No | 6e603bd7b7fee42c60252d7072a90b59eb31a5e2683a41223a6b5e3f8a5a2619 |
| [2023-28656](https://www.federalregister.gov/documents/full_text/text/2023/12/28/2023-28656.txt) | 2023-12-28 | Rice Island, Columbia River, OR/WA | No | No | a56191800aff12551c8870a060c9a09f5061f06e40aa16fb225c2e47ed097754 |

Original API metadata SHA-256 checksums, in the same document order:
- 2023-15652: 30f15e7299cc02dc61ce0115b8bdefccdf46578696daa190b69834b8a42702b4
- 2023-28652: 491a05fd07453ee27877ccd050b0d680ef618001870ff992a4675146f0920dd8
- 2023-28654: d599eea37c5450aa30df01ab5b0c64f84d0c8cac09ce106fdc2d3c68e16342e1
- 2023-28656: 3d85bd3959d91bb4447e3bcf859cc726ff2fd09fbcce6763fc24c5112a6770f7

The locally generated JSON full-text audit report SHA-256 was e900b56dbc14634759934e633341156919d9b039adf9eddcbcf7e12598cac063.

## What the scan demonstrates

The exact four documents from the prior 33 CFR Part 110 index were accessible as original published text; each metadata record matched its expected document number and publication date; each response was cryptographically fingerprinted. None of the four contained a direct 110.197 number match or a Houston/Galveston/Bolivar Roads keyword signal under the deterministic configured text scan.

The first document was indexed by the Federal Register API as a Proposed Rule, while its published text includes a **withdrawal signal**, demonstrating why index categories alone should not be equated with legal action. Three December documents concern proposed Columbia River areas.

## What the scan does not demonstrate

- A negative text keyword search does NOT prove there were no amendments effective at 33 CFR 110.197 on January 2, 2024.
- The Part 110 API index itself is not proof of exhaustive historical publication coverage.
- The **List of CFR Sections Affected (LSA)** has not been independently checked against a full official section-level change record for the covered period.
- Some documents may have been published before July 1, 2023 but become effective later; effective date must be checked separately.
- A/B/C horizontal datum, A East printed ring topology, and January 2024 authoritative WGS84 geofences remain unresolved.
- No actual AIS waiting, anchor occupancy, berth or port calls are validated by legal texts.

## Versioned tool and operational safeguards

The opt-in HarborLens full-text command is named harborlens-fr-fulltext and writes an **original-source SHA-256 and non-certifying keyword triage report**. The report must retain section legal state NOT_DETERMINED, LSA review false and AIS geofence approval false. The exact four source URLs are fixed and only allowed official HTTPS paths are followed. No real AIS, raw Federal Register source files or source charts have been committed as project artifacts.

The official-source integration workflow is **manual-only**, to avoid unnecessary repeated external queries during ordinary code changes.

## Next acceptance gates

1. Inspect the official GovInfo December 2023 LSA for Title 33 plus any interim Federal Register corrections/effective dates through January 2, 2024.
2. Record which section-level entries specifically name 110.197; distinguish proposed versus final/amending status and retain official document citations.
3. Reconcile 2023/2024 annual CFR texts with the complete source/effective date timeline under a qualified reviewer.
4. Resolve source datum for A/B/C and A East published-corner topology, then prepare a separate reviewed historically dated Polygon registry before any AIS overlay.
5. Validate operational event classes independently; regulation geography alone never proves a ship anchored or waited.

**NOT FOR NAVIGATION. NOT AN OFFICIAL LEGAL OR PORT PERFORMANCE DETERMINATION.**
