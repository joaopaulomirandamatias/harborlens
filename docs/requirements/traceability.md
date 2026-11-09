# Requirement → Specification → Implementation → Test Traceability

| Requirement group | Spec | Current code or proposal | Evidence | State |
| --- | --- | --- | --- | --- |
| FR-001..004, FR-008; BR-002, BR-004..006 | SPEC-001 | `src/harborlens/ais.py`, `cli.py`, `download.py` | synthetic regression tests plus [isolated real NOAA daily ingestion smoke](../data/noaa-real-data-smoke-2024-01-02.md); no event truth | Implemented / initial real ingestion proven, completeness pending |
| FR-005..007, FR-009; BR-001, BR-003, BR-007..008 | SPEC-002 | `infer_candidates` and `src/harborlens/multiday.py` (under PR review) | synthetic midnight/gap/conflict tests; real consecutive-day evaluation pending | Partial; real event validity unknown |
| FR-010, FR-013..014; NFR-012 | SPEC-003 | local output hashes and CLI on feature branch; independent labels pending | synthetic checksum tests awaiting CI | Partial after merge |
| FR-011..012, FR-015; BR-009..010 | SPEC-004 | `usace.py` POINT reference adapter plus planned dated polygon import | synthetic ArcGIS response and JSON Schema tests; no independent berth polygons or labels | Partial: reference points only |
| FR-016; BR-014 | SPEC-005 | EPA methodology design | emissions validation pending | Proposed |
| FR-017..018 | SPEC-006 | future read-only API/map | contract and accessibility tests pending | Proposed |
| FR-019..020 | SPEC-007 | managed service hypothesis | buyers, security, license and SLA gates pending | Proposed |

No row marked **Partial** or **Proposed** is evidence of delivered functionality. Reference SPEC IDs in issues and PRs; update this matrix on every change.

### SPEC-004 official point-source integration

A bounded real USACE FeatureServer acquisition passed with 723 reference points and matching source/GeoJSON schemas; see [source-pinned report](../data/usace-points-smoke-2026-11-09.md). This does not satisfy dated Polygon or independent event validation requirements.

### NOAA polygons for SPEC-004

Current Polygon reference import and unverified centroid overlap supplement the USACE point catalog; historical and event validity remain pending.

### Real NOAA designated Anchorage Area context

The [2026-11-09 official-source integration](../data/noaa-anchorage-real-smoke-2026-11-09.md) confirmed Polygon/MultiPolygon source acquisition and provisional historical AIS centroid overlap. Date compatibility, legal rights and operational event status are explicitly not validated.
