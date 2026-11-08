# Requirement → Specification → Implementation → Test Traceability

| Requirement group | Spec | Current code or proposal | Evidence | State |
| --- | --- | --- | --- | --- |
| FR-001..004, FR-008; BR-002, BR-004..006 | SPEC-001 | `src/harborlens/ais.py`, `cli.py`, `download.py` | synthetic fixture and `tests/test_pipeline.py` | Implemented / synthetic only |
| FR-005..007, FR-009; BR-001, BR-003, BR-007..008 | SPEC-002 | `infer_candidates` | synthetic test; real multi-day test pending | Partial |
| FR-010, FR-013..014; NFR-012 | SPEC-003 | schemas and protocol | real independent labels pending | Proposed |
| FR-011..012, FR-015; BR-009..010 | SPEC-004 | geofence design | expert-reviewed zones pending | Proposed |
| FR-016; BR-014 | SPEC-005 | EPA methodology design | emissions validation pending | Proposed |
| FR-017..018 | SPEC-006 | future read-only API/map | contract and accessibility tests pending | Proposed |
| FR-019..020 | SPEC-007 | managed service hypothesis | buyers, security, license and SLA gates pending | Proposed |

No row marked **Partial** or **Proposed** is evidence of delivered functionality. Reference SPEC IDs in issues and PRs; update this matrix on every change.
