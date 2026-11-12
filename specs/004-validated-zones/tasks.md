# SPEC-004: Implementation Work Items

**State:** PARTIAL — reference geometry and regulatory source audits; no validated classification. Checking a task requires traceable PR/test evidence.

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

- [x] Add bounded USACE point importer, source metadata, schemas and offline tests (merged in #24).
- [ ] Run controlled live official Houston query, record only aggregate evidence, confirm source validity and rights.

- [x] Perform a bounded official Houston USACE point acquisition, three-page query, output SHA-256 and metadata schema validation (2026-11-09; source-pinned report).
- [ ] Obtain historically valid authoritative berth/anchorage polygons from NOAA/USACE, with source attribution and reviewer approval.

- [x] Implement bounded NOAA designated anchorage Polygon import and synthetic tests (merged in #27).
- [x] Implement centroid spatial overlap with holes, boundaries, ambiguity and unknown semantics (merged in #27).
- [ ] Verify historically dated geometry, source terms and independent operational event labels.

- [x] Perform controlled NOAA polygon real-source retrieval and synthetic-to-real centroid overlay; see [engineering evidence](../../docs/data/noaa-anchorage-real-smoke-2026-11-09.md).
- [ ] Independently verify historical 2024 anchorage geometry and source-specific rights.
- [ ] Extend centroid-only overlay to full trajectories with uncertainty flags, then independently evaluate operational labels.

- [x] Add local bounded full-observed-track polygon context and explicit unknowns, receipt verification and synthetic regression tests (merged in #29).
- [ ] Benchmark on authentic NOAA historical AIS and assess all-points vs centroid difference, including coverage and source vintage limitations.
- [ ] Verify independent historical geometry with authoritative source/reviewer before operational inference.

- [x] Run initial official NOAA historical AIS/full-track geometry comparison and record aggregate results and hashes (2026-11-09).
- [ ] Verify historical January 2024 geofence validity and source-specific redistribution rights.
- [ ] Obtain independent maritime event labels and evaluate actual classification error rates.

- [x] Implement bounded offline source-pinned NOAA ENC documentary edition/issue screening, source hash checks, and synthetic tests (merged in #31).
- [ ] Acquire genuinely historical 2024 ENC/anchorage polygon revisions; verify actual source, geometry, attribution and rights.
- [ ] Add independent event-label evidence and classify only when a reviewed historical polygon is available.

- [x] Run a bounded real NOAA current source-vintage audit and verify the unreviewed January 2024 status; see [integration report](../../docs/data/noaa-geometry-vintage-smoke-2026-11-09.md).
- [ ] Obtain actual historical January 2024 ENC/anchorage source and establish polygon-version equivalence independently.

- [x] Discover official July 1, 2024 GPO CFR §110.197 legal boundary coordinates and 33 CFR 110.1(d) datum caveat; add DMS transcription, topology/datum audit and synthetic tests (merged in #33).
- [ ] Check precise January 2, 2024 effective regulations against historical CFR/Federal Register/LSA, not just the July edition.
- [ ] Resolve A/B/C coordinate datum from authoritative sources and A East polygon vertex order with review evidence; do not auto-repair.
- [ ] Publish only reviewed, temporally appropriate WGS84 geometries before AIS matching.

- [x] Retrieve official GPO 2023 and 2024 annual CFR 33 Section 110.197 and compare all 16 anchor DMS pairs, recording downloaded-source SHA-256 (2026-11-09).
- [ ] Verify exact January 2, 2024 effective legal timeline using Federal Register/LSA and source date corrections.
- [ ] Resolve A/B/C datum and A East literal self-intersection using agency-approved geometry or original exhibits.

- [x] Add opt-in bounded FederalRegister.gov 33 CFR Part 110 publication-index screen with simulated pagination/host/source tests (merged in #44).
- [ ] Read exact official Part 110 documents and GPO LSA for 2023-07-01 through 2024-01-02 before any legal-effect conclusion.

- [x] Run live official FederalRegister.gov 33 CFR Part 110 publication-index query for 2023-07-01 to 2024-01-02, hash the source response and register four proposals (initial engineering screen).
- [ ] Read exact official text/effective dates for identified documents and reconcile original GPO LSA/FR before certifying January 2 legal effect.

- [x] Add fixed official full-text inspection for four 2023 Part 110 indexed documents with SHA-256, location/section search signals and source/redirect safeguards (pending PR CI).
- [ ] Review GPO monthly LSA Title 33 and full FR effective-date/section amendments before concluding historical 2024-01-02 legal text.

- [x] Verify the original FederalRegister.gov source text for all four July–December 2023 index entries, preserving metadata/raw text hashes and explicit region/110.197 keyword findings; see [engineering evidence](../../docs/data/fr-2023-original-fulltext-evidence-2026-11-09.md).
- [x] Add an opt-in bounded GovInfo December 2023 and January 2024 LSA Title 33 index comparison (`lsa_compare.py`) with offline synthetic tests, fixed HTTPS URLs, size and timeout caps, `rights_status=review_required`, and schema-enforced `legal_effect_on_study_date=NOT_DETERMINED` (draft PR #53). This does not complete official PDF reproduction or January 2, 2024 legal-effect review.
- [ ] Complete official GPO December 2023 LSA Title 33 section-level coverage and remaining effective-date verification before concluding January 2, 2024 legal status.
- [x] Parse Federal Register window dates as ASCII `YYYY-MM-DD` only, and geometry-vintage study timestamps as `YYYY-MM-DDTHH:MM:SS` with `Z` or `±HH:MM`, identically on Python 3.10 and 3.12 (`tests/test_timeparse.py`). This does not determine legal effect. Refs #78 (stays open).
- [x] `harborlens-fr-timeline` exits 2 with no traceback and no network call when `--start` or `--end` is not a real ASCII `YYYY-MM-DD` date. A start date after the end date stays the window error from `initial_url`. Package `0.2.0.dev18`. Evidence: `tests/test_fr_timeline.py`. This does not determine legal effect. Found during the #78/#81 review. Refs #82 (stays open).
