# Functional Requirements

**P0** = current research baseline; **P1** = validated open-source target; **P2** = possible commercial target. **Synthetic implementation** means only fixture behavior has been tested.

| ID | Priority | Requirement | Status | Spec |
| --- | --- | --- | --- | --- |
| FR-001 | P0 | Ingest NOAA-style UTF-8 CSV, gzip/ZIP, and optional zstd formats | Synthetic implementation | SPEC-001 |
| FR-002 | P0 | Normalize AIS timestamps to UTC and reject invalid MMSI, coordinate and speed values | Synthetic implementation | SPEC-001 |
| FR-003 | P0 | Use an explicit WGS84 bounding box; count invalid, duplicate and out-of-zone records separately | Synthetic implementation | SPEC-001 |
| FR-004 | P0 | Generate SHA-256 source file fingerprint and record quality counters plus method parameters | Synthetic implementation | SPEC-001 |
| FR-005 | P0 | Infer only candidate low-speed stationary segments with duration/centroid and unvalidated flag | Synthetic implementation | SPEC-002 |
| FR-006 | P0 | Export cleaned AIS CSV, candidate CSV, candidate GeoJSON and JSON manifest | Synthetic implementation | SPEC-001 |
| FR-007 | P0 | Prohibit claiming an inferred candidate as verified berth, anchorage, waiting or port call | Synthetic implementation | SPEC-002 |
| FR-008 | P0 | Expose optional AOI/row limits; perform no network access on installation or ordinary CLI execution | Synthetic implementation | SPEC-001 |
| FR-009 | P1 | Join consecutive days without corrupting event continuity; track conflicting MMSI and gaps | Implemented in initial two-day research pipeline; real event accuracy requires independent validation | SPEC-002 |
| FR-010 | P1 | Publish source snapshots with URL, dataset/vintage, file hash, rights and output fingerprints | Proposed | SPEC-003 |
| FR-011 | P1 | Load externally verified dated geofences for facilities and anchorage areas | Partial: bounded USACE facility point adapter, with dated polygon validation still pending | SPEC-004 |
| FR-012 | P1 | Assign unknown rather than false berth/anchor states; require external event validation for authoritative labels | Proposed | SPEC-004 |
| FR-013 | P1 | Assess predicted events against documented independent positive and negative labels | Proposed | SPEC-003 |
| FR-014 | P1 | Produce reproducible metrics with denominators, version, coverage, error and unknown percentage | Proposed | SPEC-003 |
| FR-015 | P1 | Aggregate candidate/validated metrics by port zone, period and vessel category without misleading scope | Proposed | SPEC-004 |
| FR-016 | P1 | Estimate transparent EPA-method scenarios including factors, units and uncertainty; never imply measured savings | Proposed | SPEC-005 |
| FR-017 | P1 | Expose optional read-only historical API contract with schema versions and provenance | Proposed | SPEC-006 |
| FR-018 | P1 | Provide accessible reference map with explicit state/uncertainty and not-for-navigation warnings | Proposed | SPEC-006 |
| FR-019 | P2 | Support optional commercial tenant isolation, SSO, permission rules and private data integration | Commercial hypothesis | SPEC-007 |
| FR-020 | P2 | Support optional managed refresh, reporting, monitoring, SLA and billing after customer validation | Commercial hypothesis | SPEC-007 |
| FR-021 | P0 | Record the analysis window and flag left/right window-edge censoring per candidate, with run-level counts and internal-gap reporting | Synthetic implementation | SPEC-002 |
| FR-022 | P0 | Use one segmentation engine for single-file and multi-day runs, with configurable thresholds recorded per candidate and run, diagnostics by split/discard reason, and descriptive threshold-sensitivity reports | Synthetic implementation | SPEC-002 |

Proposed behavior MUST NOT be advertised as implemented. A requirement is accepted only with a reviewed spec, source rights and reproducible tests.
