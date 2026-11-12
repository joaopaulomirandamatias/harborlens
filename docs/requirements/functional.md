# Functional Requirements

**P0** = current research baseline; **P1** = validated open-source target; **P2** = possible commercial target. **Synthetic implementation** means only fixture behavior has been tested.

| ID | Priority | Requirement | Status | Spec |
| --- | --- | --- | --- | --- |
| FR-001 | P0 | Ingest NOAA-style UTF-8 CSV, gzip/ZIP, and optional zstd formats | Synthetic implementation | SPEC-001 |
| FR-002 | P0 | Normalize AIS timestamps to UTC and reject invalid MMSI, coordinate and speed values. Naive NOAA clocks, `Z`, and `±HH:MM` use one ASCII grammar on Python 3.10 and 3.12 (`tests/test_timeparse.py`) | Synthetic implementation | SPEC-001 |
| FR-003 | P0 | Use an explicit WGS84 bounding box; count invalid, duplicate and out-of-zone records separately | Synthetic implementation | SPEC-001 |
| FR-004 | P0 | Generate SHA-256 source file fingerprint and record quality counters plus method parameters | Synthetic implementation | SPEC-001 |
| FR-005 | P0 | Infer only candidate low-speed stationary segments with duration/centroid and unvalidated flag | Synthetic implementation | SPEC-002 |
| FR-006 | P0 | Export cleaned AIS CSV, candidate CSV, candidate GeoJSON and JSON manifest | Synthetic implementation | SPEC-001 |
| FR-007 | P0 | Prohibit claiming an inferred candidate as verified berth, anchorage, waiting or port call | Synthetic implementation | SPEC-002 |
| FR-008 | P0 | Expose optional AOI/row limits; perform no network access on installation or ordinary CLI execution | Synthetic implementation | SPEC-001 |
| FR-009 | P1 | Join consecutive days without corrupting event continuity; track conflicting MMSI and gaps | Implemented for 2–16 local files with a fixed SQLite working set. An unreadable file or a missing required column exits 2 with no traceback. Real event accuracy requires independent validation | SPEC-002 |
| FR-010 | P1 | Publish source snapshots with URL, dataset/vintage, file hash, rights and output fingerprints | Partial: local output hashes and `harborlens-verify` (#18), hashed acquisition sidecars with vintage (#19, #20), `code_version` in manifests, rights-gated aggregate staging (one `prepare_summary` per CLI invocation; review timestamps from 30 days old through 5 minutes of clock skew, not configurable), release-gate schemas packaged for `importlib.resources`, read-only `harborlens-verify-release` for a domain-separated signed review, and a fail-closed rights register (UTF-8 BOM, non-timestamp review clock, trailing-whitespace URL, IPv6 literal, and raw IDN stay unapproved; punycode remains accepted). ERDDAP and archive-extract sidecars have published schemas. No source is approved. Refs #42 (stays open). Refs #67 (stays open). Refs #69 (stays open). Refs #70 (stays open) | SPEC-003 |
| FR-011 | P1 | Load externally verified dated geofences for facilities and anchorage areas | Partial: USACE facility points, current NOAA anchorage polygons and audited 33 CFR 110.197 coordinates; no reviewed dated WGS84 polygon yet | SPEC-004 |
| FR-012 | P1 | Assign unknown rather than false berth/anchor states; require external event validation for authoritative labels | Proposed | SPEC-004 |
| FR-013 | P1 | Assess predicted events against documented independent positive and negative labels | Partial: labeling protocol, blinded stratified sampler including transceiver class (`A`, `B`, `absent_or_unknown`), agreement tooling, shared CSV formula neutralization (label sheet and AIS text cells), and a synthetic `harborlens-evaluate` harness (`evaluation-v0.2`, `validation_status` `unvalidated`); no real labels collected yet | SPEC-003 |
| FR-014 | P1 | Produce reproducible metrics with denominators, version, coverage, error and unknown percentage | Partial: `evaluation-v0.2` harness with denominators, Wilson intervals, coverage exclusions, a caveat that no accuracy claim is made, and a warning that agreement at any evidence level, including L3, is not validated performance while `validation_status` is `unvalidated`; no real labels evaluated | SPEC-003 |
| FR-015 | P1 | Aggregate candidate/validated metrics by port zone, period and vessel category without misleading scope | Proposed | SPEC-004 |
| FR-016 | P1 | Estimate transparent EPA-method scenarios including factors, units and uncertainty; never imply measured savings | Proposed | SPEC-005 |
| FR-017 | P1 | Expose optional read-only historical API contract with schema versions and provenance | Proposed | SPEC-006 |
| FR-018 | P1 | Provide accessible reference map with explicit state/uncertainty and not-for-navigation warnings | Proposed | SPEC-006 |
| FR-019 | P2 | Support optional commercial tenant isolation, SSO, permission rules and private data integration | Commercial hypothesis | SPEC-007 |
| FR-020 | P2 | Support optional managed refresh, reporting, monitoring, SLA and billing after customer validation | Commercial hypothesis | SPEC-007 |
| FR-021 | P0 | Record the analysis window and flag left/right window-edge censoring per candidate, with run-level counts and internal-gap reporting | Synthetic implementation | SPEC-002 |
| FR-022 | P0 | Use one segmentation engine for single-file and multi-day runs, with configurable thresholds recorded per candidate and run, diagnostics by split/discard reason, and descriptive threshold-sensitivity reports | Synthetic implementation | SPEC-002 |

Proposed behavior MUST NOT be advertised as implemented. A requirement is accepted only with a reviewed spec, source rights and reproducible tests.
