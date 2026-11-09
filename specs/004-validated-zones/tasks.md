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
