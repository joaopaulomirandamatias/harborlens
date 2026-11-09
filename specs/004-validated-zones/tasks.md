# SPEC-004: Implementation Work Items

**State:** PROPOSED. Checking a task requires traceable PR/test evidence.

- [x] Review USACE/NTAD point source and current dataset metadata
- [ ] Obtain authoritative dated polygon geometry; the current facility POINT catalog is not sufficient
- [ ] Implement transparent spatial rules and unknown state
- [ ] Measure precision and timing errors with external events

## Review gate

- [ ] Acceptance criteria demonstrated
- [ ] Schema and requirements matrix updated
- [ ] Positive, negative and boundary tests pass
- [ ] Source rights and security reviewed
- [ ] No unsupported accuracy, emissions or customer claims

- [x] Add bounded USACE point importer, source metadata, schemas and offline tests (pending PR review).
- [ ] Run controlled live official Houston query, record only aggregate evidence, confirm source validity and rights.

- [x] Perform a bounded official Houston USACE point acquisition, three-page query, output SHA-256 and metadata schema validation (2026-11-09; source-pinned report).
- [ ] Obtain historically valid authoritative berth/anchorage polygons from NOAA/USACE, with source attribution and reviewer approval.

- [x] Implement bounded NOAA designated anchorage Polygon import and synthetic tests (PR review pending).
- [x] Implement centroid spatial overlap with holes, boundaries, ambiguity and unknown semantics (PR review pending).
- [ ] Verify historically dated geometry, source terms and independent operational event labels.

- [x] Perform controlled NOAA polygon real-source retrieval and synthetic-to-real centroid overlay; see [engineering evidence](../../docs/data/noaa-anchorage-real-smoke-2026-11-09.md).
- [ ] Independently verify historical 2024 anchorage geometry and source-specific rights.
- [ ] Extend centroid-only overlay to full trajectories with uncertainty flags, then independently evaluate operational labels.

- [x] Add local bounded full-observed-track polygon context and explicit unknowns, receipt verification and synthetic regression tests (pending CI and PR review).
- [ ] Benchmark on authentic NOAA historical AIS and assess all-points vs centroid difference, including coverage and source vintage limitations.
- [ ] Verify independent historical geometry with authoritative source/reviewer before operational inference.

- [x] Run initial official NOAA historical AIS/full-track geometry comparison and record aggregate results and hashes (2026-11-09).
- [ ] Verify historical January 2024 geofence validity and source-specific redistribution rights.
- [ ] Obtain independent maritime event labels and evaluate actual classification error rates.

- [x] Implement bounded offline source-pinned NOAA ENC documentary edition/issue screening, source hash checks, and synthetic tests (under PR review).
- [ ] Acquire genuinely historical 2024 ENC/anchorage polygon revisions; verify actual source, geometry, attribution and rights.
- [ ] Add independent event-label evidence and classify only when a reviewed historical polygon is available.

- [x] Run a bounded real NOAA current source-vintage audit and verify the unreviewed January 2024 status; see [integration report](../../docs/data/noaa-geometry-vintage-smoke-2026-11-09.md).
- [ ] Obtain actual historical January 2024 ENC/anchorage source and establish polygon-version equivalence independently.
