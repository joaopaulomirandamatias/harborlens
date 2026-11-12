# Changelog

## [Unreleased]

### Added (SPEC-003: controlled aggregate publication)
- A new offline `harborlens-release-summary` command stages allowlisted, coarse research counts only after source/run hash checks, current purpose-specific source-rights verification and a recent human approval of the exact proposed summary digest. Pending sources and mismatched evidence fail without release output; no raw data, geofences or event-level exports are copied. Synthetic-only positive/negative/attack tests and JSON Schemas added; no source is approved in the checked-in register.

### Added (SPEC-003: source-rights adapter receipts)
- Optional per-purpose, exact-source-version source-rights registry lookups with SHA-256 receipts for NOAA ERDDAP, local daily archive extraction, NOAA anchorage polygons and USACE point catalog; defaults remain review_required. Receipts call `load_registry`, so a schema-invalid register is `invalid_registry` and is not granted. Synthetic-only source and schema regression tests; no license or vessel-event approval.
- Package version `0.2.0.dev2`. Adapter sidecars gain `rights_review`. A supplied register can change `rights_status` and the USACE `license_status`. Runs from `0.2.0.dev1` and `0.2.0.dev2` are not directly comparable because `run_id` includes the package version.
- `rights_receipt` reads the register once. The SHA-256 and the decision both come from that buffer after the packaged-schema check. The package version stays `0.2.0.dev2`.

### Added (SPEC-003: source rights register, #42)
- `docs/data/rights-register.json`: offline inventory of five official sources. **No source has been approved.** Every checked-in entry stays `rights_status=review_required`.
- Schema `source-rights-register` (`schemas/v1/source-rights-register.schema.json`). `load_registry` validates a register against that schema before any decision; a schema-invalid register is a load error and is not granted.
- `python -m harborlens.rights`: offline audit helper. Exit 0 only when `rights_status` is an approved status; exit 1 for any other status, including `review_required` and `use_restricted`; exit 2 when the register cannot be loaded, parsed or schema-validated. JSON stays on stdout, and a load failure includes an `error` field so it is distinct from pending. Optional adapter receipts are the entry above; with no reviewed register, acquisition metadata remains `review_required`.
- The schema copy used at runtime is `src/harborlens/schemas/v1/source-rights-register.schema.json`, byte-identical to `schemas/v1/source-rights-register.schema.json`, and is loaded with `importlib.resources` only. The helper does not search parent directories.
- Optional extra `rights` (`pip install 'harborlens[rights]'`) installs `jsonschema`. Core dependencies stay empty. If `jsonschema` is missing, the helper exits 2 and the JSON `error` names that extra. Validation is never skipped.
- Terms, evidence and source URLs must be `https` with a real host. `https://user@`, `https://.`, `https:// ` and `https://@` are rejected. The schema pattern requires a host.

### Changed (SPEC-003: transceiver class in the labeling sample, #65)
- `harborlens-label-sample` stratifies candidates by duration band × censoring × vessel group × transceiver class (`A`, `B`, `absent_or_unknown`) and negative movement intervals by vessel group × transceiver class. Missing, blank and any value other than A or B is `absent_or_unknown` and stays in the sample. On the recorded seven-day NOAA run, Class B was 7.4% of points and 32% of stationary candidates (`docs/data/noaa-real-data-rerun-2026-11-09.md`), so class coverage is no longer left to a proportional draw.
- When fewer units are requested than there are non-empty strata, full cross-cell coverage is impossible. `stratification.all_non_empty_strata_drawn` is then false. Every transceiver class present in the frame (`A`, `B`, `absent_or_unknown`) is still drawn when the request is at least as large as the number of those classes. The annotator sheet is unchanged and still blinded.
- **Migration:** sampling manifests move from `label-sample-v0.1` to `label-sample-v0.2` (new required `transceiver_class` on each key item, plus `stratification`). No labeling sheets have been collected; regenerate samples. v0.1 manifests do not validate against v0.2. `harborlens-evaluate` parses the stratum from the manifest `schema_version` rather than guessing the vessel group from field position, and the unit `kind` must match that stratum.
- Package version `0.2.0.dev1` (method unchanged, `stationary-v0.2`). Runs from `0.2.0.dev0` (the recorded NOAA week in `docs/data/noaa-real-data-rerun-2026-11-09.md`) and `0.2.0.dev1` are not directly comparable: `run_id` includes the package version, and the label-sample stratification changed. The previous sampling remains reproducible by running `0.2.0.dev0`.
- `harborlens-evaluate` reads stratum keys with the sampling manifest's `schema_version`. A `label-sample-v0.2` key must have that version's field count, a vessel group of `cargo`, `tanker`, `passenger`, `tug_or_service`, or `other_or_unknown`, and transceiver class `A`, `B`, or `absent_or_unknown`. A `label-sample-v0.1` key is accepted only when the manifest says so. The unit `kind` must match the stratum kind; a missing or mismatched kind raises `AISInputError` naming the `sample_id` instead of changing the confusion matrix. The CLI reports that error with a nonzero exit and no traceback. A damaged key raises the same error instead of being reported as a vessel group. Valid evaluation reports are unchanged, so the package version stays `0.2.0.dev1`.

### Added (SPEC-001: NOAA archive vintages, #36)
- `harborlens.vintages`: 2015–2023 daily ZIP layout and 2024–2026 csv2 zstd layout, with how each was verified. `harborlens-download-noaa` builds URLs from it and refuses unregistered years (it previously built a csv2 URL for 2019–2023).
- `harborlens-extract-noaa-archive` accepts single-CSV `.zip` archives, no longer hard-codes 2024, checks compression against the year, and records `source_vintage` in the sidecar.
- Ingestion and extraction count `missing_value` (empty required field, e.g. 2025 nulls) separately from `invalid`; manifest `counts` gain `missing_value`.
- The seven-day workflow resolves archive names through the registry.

### Added (SPEC-001: vessel attributes and MMSI QA flags, #39)
- Cleaned AIS keeps `cog_deg`, `heading_deg`, `length_m`, `width_m`, `draft_m`, `transceiver_class` (NOAA sentinels → empty) and an ITU-R M.585 `mmsi_category` flag; new columns are appended. Rows are never dropped by category; both manifests report `mmsi_categories`.
- Candidates carry `vessel_type`, `transceiver_class`, `length_m`, `draft_m` and `mmsi_category` for stratified evaluation; `read_candidates_csv` returns missing values as `None`.
- Schema migration: `ais-point`, `stationary-candidate`, both candidate feature schemas and both manifests require the new fields; regenerate earlier outputs. Older cleaned CSV files without the new columns still load.

### Changed (SPEC-003: contracts and run identity, #41)
- Package version `0.2.0.dev0` (method `stationary-v0.2`). Both manifests record `code_version`; the package version is part of `run_id` (the CI git commit is recorded as metadata only). Bump the version for any output-changing change (CONTRIBUTING).
- New `stationary-candidate-feature.schema.json` for single-file GeoJSON features and `harborlens.ais.read_candidates_csv` for typed CSV records; real CLI exports are now validated in tests.
- CI matrix on Python 3.10 and 3.12 (minimum and current).
- `CITATION.cff`.

### Changed (SPEC-001/SPEC-002: volume ceilings, #35)
- Ceilings sized for seven full Houston days from a synthetic 3.92-million-row benchmark (`docs/data/scale-benchmark-2026-11-09.md`, `tools/benchmark_multiday.py`): extraction 1,000,000 rows / 256 MiB; multi-day 6 million rows, 2,048 MiB scratch, 1,024 MiB default export; track-context 6 million rows, 100,000 candidates, 60,000 points per candidate; in-memory tools 6 million rows, checked while reading. All limits still fail closed.
- Manifests and the extraction sidecar record `limits`; the multi-day manifest records `resources.scratch_peak_bytes`. The export-phase scratch check now uses the configured scratch cap instead of four times the export cap.
- New manual workflow `noaa-week-integration.yml` for 2–7 consecutive full NOAA days (aggregate metrics only).

### Added (SPEC-003: evaluator, #9)
- `harborlens-evaluate`: confusion matrix, precision/recall/F1/specificity with Wilson 95% intervals, design-weighted precision, cohorts (evidence level, vessel group, censoring), candidate label composition and boundary MAE/median error for uncensored true positives; `mixed`/`unknown`/unlabeled units reported separately. Schemas `adjudicated-label`, `evaluation-report`. No real labels evaluated yet.

### Added (SPEC-003: labeling pilot tooling, #8)
- `docs/research/labeling-protocol.md`: label taxonomy, L2/L3 evidence levels, censoring and fragmentation rules, double annotation and adjudication.
- `harborlens-label-sample`: seeded, blinded, stratified sample of candidates and negative movement intervals from a verified run, with a sampling manifest holding the key.
- `harborlens-label-agreement`: validation of two annotators' sheets, Cohen's kappa, confusion matrix and disagreements. Agreement is not accuracy; no labels have been collected yet.
- Schemas `label-record`, `label-sample`, `label-agreement`.

### Changed (SPEC-002: shared segmentation engine, FR-022, #37; fixes #38)
- Both `harborlens` and `harborlens-multiday` now use one engine (`harborlens.segmentation`, method `stationary-v0.2`). The single-file command now also splits on vessel-type conflicts and implied jumps (>65 kn), as the multi-day command did; for the same input both commands emit identical candidates and diagnostics.
- Thresholds are configurable on both commands (`--max-sog-knots`, `--min-duration-minutes`, `--max-gap-minutes`, `--max-radius-m`, `--min-points`, `--max-jump-knots`) and recorded in `method_parameters`, in a `harborlens_method` GeoJSON member and as `parameter_set` on every candidate. `harborlens-track-context` reads them instead of hard-coding 0.5 kn / 15 min.
- Manifests report split reasons, `discarded_by_reason`, `candidates_per_mmsi` and (single-file) `unparsable_rows`.
- Multi-day ordering uses integer microseconds, so same-second fractional timestamps are no longer misordered (#38).
- **Migration:** method version `stationary-v0.1` / `stationary-multiday-v0.1` → `stationary-v0.2`; `event_id`, `run_id` and artifact hashes change, and earlier outputs do not validate against the updated schemas. Re-run the pipeline. No labels reference earlier event IDs.

### Added
- `harborlens-sensitivity`: descriptive threshold-grid report (`schemas/v1/sensitivity-report.schema.json`, `docs/research/threshold-sensitivity.md`). It does not select thresholds.

### Added (SPEC-002: analysis-window censoring, BR-019 / FR-021, #34)
- `left_censoring` / `right_censoring` on every stationary candidate (single-file and multi-day), `analysis_window` and `events.censoring` in both manifests, `--window-start/--window-end` CLI flags, and automatic use of verified extraction/ERDDAP sidecars.
- Manual NOAA workflows now publish aggregate censoring counts.

### Changed (schema migration)
- `schemas/v1` candidate, multi-day feature, run manifest and multi-day manifest now require the censoring fields. Outputs produced before this change do not validate against the updated schemas; re-run the pipeline to regenerate them. Segmentation, method versions and event IDs are unchanged; `run_id` changes only when a window is known.

### Added (SPEC-004 official Federal Register text triage)
- Fixed-list full-text source verification of four 2023 Federal Register Part 110 index documents; official metadata/bytes hashed, source links restricted and relevance flags non-certifying.

### Added (SPEC-004: official 2024 CFR anchorages)
- Source-pinned July 1, 2024 federal 33 CFR 110.197 Galveston anchorage DMS registry and fail-closed topology/datum inspection. A/B/C lack explicit NAD83 status; A East literal corner order fails Polygon validity. No guessed WGS84 geometry or operational classification.

### Added (SPEC-004 observed-track evidence)
- Local Shapely/SQLite full-track vs Polygon reference context with interval/cardinality checks, historic-vintage flags, source receipt hashes, strictly unverified statuses and synthetic/schema tests.

### Added (SPEC-004: NOAA Polygon reference)
- Opt-in NOAA designated anchorage polygon source, conservative candidate spatial-context overlay and synthetic geometry regression tests. No event confirmation.

### Added (SPEC-004: initial)
- Bounded opt-in official USACE point-feature reference import with output/source hashes, contracts and synthetic regression tests; no inferred berth polygons or port-event truth.

### Added
- SQLite-based multi-day AIS candidate reconstruction with source provenance, cross-midnight grouping and bounded local processing.
- Synthetic regression tests, multi-day JSON Schemas and schema validation in CI.
- A source-pinned NOAA 2024-01-02/03 engineering experiment and manual-only national-archive workflow.

### Limitations
- Historical candidate segments have no independently validated berth, anchorage, waiting-time or emissions interpretation.

### Recorded integration evidence (2026-11-09; previously filed under 0.1.0)

#### NOAA real-data re-run on `stationary-v0.2` (evidence)

- Daily, consecutive-day, track-context and first seven-full-day runs on NOAA 2024-01-02…08 archives. Earlier 1-day, 2-day and track-context counts reproduced exactly; censoring measured for the first time (76.5% of candidates edge-touching in a 6-hour window, 55.1% in 12 hours, 7.1% over seven days). Seven days: 3.95 million points, 15,937 unvalidated candidates, 741 MiB scratch peak, 47 MiB RSS, all within the #35 ceilings. Run locally from the workflow steps because Actions dispatch was unavailable to the agent. See docs/data/noaa-real-data-rerun-2026-11-09.md.

#### USACE facility point source integration (evidence)

- Initial bounded USACE Navigation Facilities POINT catalog query for Houston: 723 features and 536 Dock records; output SHA-256 and schema checks passed; no dated berth polygon or confirmed port-event status. See docs/data/usace-points-smoke-2026-11-09.md.

#### NOAA reference polygon integration (evidence)

- Source-pinned NOAA Designated Anchorage Areas real-data query and historical AIS candidate centroid overlay completed. Six current areas, 920 unvalidated candidates, 77 possible centroid overlaps; no historical anchorage or waiting truth established. See docs/data/noaa-anchorage-real-smoke-2026-11-09.md.

#### First authentic full-track Polygon geometric comparison

- NOAA 2024-01-02 historical AIS and six current NOAA reference polygons: 920 unvalidated candidate segments; 74 with all observed points within one polygon, 5 with partial point coverage and 841 without observed-point overlap. [Source-pinned evidence](docs/data/noaa-full-track-context-smoke-2026-11-09.md). Operational event and historical polygon validity remain unverified.

#### Added (SPEC-004: historical source-vintage screening)

- Offline NOAA ENC documentary date audit checks current polygon/source hashes and optional unverified ENC metadata; all outputs deny automatic historical certification and retain review_required rights.

#### NOAA historical geometry vintage source smoke

- Official current NOAA Anchorage Areas Polygon retrieval, source checksum and documentary January 2024 audit passed with non-certifying no_documentary_enc_evidence status. See docs/data/noaa-geometry-vintage-smoke-2026-11-09.md.

#### Source-verification evidence for Galveston/Bolivar Roads legal anchors

- GPO 2023/2024 annual CFR Title 33 full HTML checksums and all 16 regulatory corner pairs matched; legal scope remains annual-edition dated, A/B/C datum unspecified, A East literal ring flagged. See docs/data/cfr-2023-2024-source-verification.md.

#### Source-pinned 2023/2024 Federal Register Part 110 index screening

- Four Proposed Rule metadata entries returned from official FederalRegister.gov for the defined publication window; API page and report SHA-256 recorded. This is not a legal effect conclusion. See docs/data/fr-part110-real-index-2023-2024.md.

#### Federal Register original full-text evidence

- Official 2023 source-metadata and raw-text hashes verified for four Part 110 index hits; no direct section 110.197 or Houston/Galveston text mentions in the four. [Source report](docs/data/fr-2023-original-fulltext-evidence-2026-11-09.md). GPO LSA and exact January 2024 legal effect are still unverified.

Following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-11-08

### Added
- NOAA-style AIS input normalization, batch quality counters, input hash and stationary-candidate baseline.
- Synthetic fixture and regression tests; Python package CLI.
- SDD specification baseline, requirement IDs, JSON Schemas, architecture, security and research documentation.

### Limitations
- Tested only with fictional AIS data. No actual vessel, port waiting, berth, anchorage, emissions, real-world accuracy or commercial service is verified.
