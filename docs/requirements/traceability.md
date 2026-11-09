# Requirement → Specification → Implementation → Test Traceability

| Requirement group | Spec | Current code or proposal | Evidence | State |
| --- | --- | --- | --- | --- |
| FR-001..004, FR-008; BR-002, BR-004..006 | SPEC-001 | `src/harborlens/ais.py`, `cli.py`, `download.py` | synthetic regression tests plus [isolated real NOAA daily ingestion smoke](../data/noaa-real-data-smoke-2024-01-02.md); no event truth | Implemented / initial real ingestion proven, completeness pending |
| FR-005..007, FR-009; BR-001, BR-003, BR-007..008 | SPEC-002 | `infer_candidates` and `src/harborlens/multiday.py` (under PR review) | synthetic midnight/gap/conflict tests; real consecutive-day evaluation pending | Partial; real event validity unknown |
| FR-010, FR-013..014; NFR-012 | SPEC-003 | local output hashes and CLI on feature branch; independent labels pending | synthetic checksum tests awaiting CI | Partial after merge |
| FR-011..012, FR-015; BR-009..010 | SPEC-004 | geofence design | expert-reviewed zones pending | Proposed |
| FR-016; BR-014 | SPEC-005 | EPA methodology design | emissions validation pending | Proposed |
| FR-017..018 | SPEC-006 | future read-only API/map | contract and accessibility tests pending | Proposed |
| FR-019..020 | SPEC-007 | managed service hypothesis | buyers, security, license and SLA gates pending | Proposed |

No row marked **Partial** or **Proposed** is evidence of delivered functionality. Reference SPEC IDs in issues and PRs; update this matrix on every change.
