# Requirement → Specification → Implementation → Test Traceability

| Requirement group | Spec | Current code or proposal | Evidence | State |
| --- | --- | --- | --- | --- |
| FR-001..004, FR-008; BR-002, BR-004..006 | SPEC-001 | `src/harborlens/ais.py`, `cli.py`, `download.py` | synthetic regression tests plus [isolated real NOAA daily ingestion smoke](../data/noaa-real-data-smoke-2024-01-02.md); no event truth | Implemented / initial real ingestion proven, completeness pending |
| FR-005..007, FR-009, FR-021, FR-022; BR-001, BR-003, BR-007..008, BR-019 | SPEC-002 | `segmentation.py` (shared engine), `ais.py`, `multiday.py`, `censoring.py` | synthetic engine, censoring and multi-day tests; [real two-day NOAA smoke](../data/noaa-consecutive-days-smoke-2024-01-02-03.md); [seven-day re-run with censoring](../data/noaa-real-data-rerun-2026-11-09.md) | Implemented; real event validity unknown |
| FR-010, FR-013..014; NFR-012 | SPEC-003 | `provenance.py` (`harborlens-verify`, `code_version`), `labeling.py`, `evaluation.py` | synthetic checksum, contract, labeling and evaluation tests | Partial: tooling implemented; no labels collected |
| FR-011..012, FR-015; BR-009..010 | SPEC-004 | `usace.py`, `noaa_anchorages.py`, `zone_context.py`, `track_context.py`, `vintage.py`, `cfr_anchorages.py`, `fr_timeline.py`, `fr_fulltext.py` | synthetic and schema tests plus source-pinned real-source smokes; no reviewed dated polygons or labels | Partial: reference geometry and source audits only |
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

### SPEC-004: Full-track spatial evidence increment

The experimental full-observed-track overlay, its source receipts, schema and synthetic tests are tracked under the current SPEC-004 work. It compares discrete AIS observations against unreviewed NOAA polygons and preserves unknown/ambiguous states; this is NOT independently validated berth/anchorage/waiting classification.

### Real NOAA full-track polygon source engineering (SPEC-004)

The [historical AIS full observed-track integration](../data/noaa-full-track-context-smoke-2026-11-09.md) records a source-pinned centroid versus full-points comparison with bounded SQLite/Shapely processing and conservative status labels. This does NOT complete FR-011/FR-012 historical geometry or validated event requirements.

### NOAA ENC documentary vintage (SPEC-004)

A conservative offline [vintage audit](../data/geometry-vintage-audit.md) reports edition/issue date conflicts for a historical AIS time interval. It preserves historic geometry and operational event validity as not_verified regardless of user-provided dates; actual old geometry source files are not yet obtained.

### NOAA geometry-vintage real source integration

An isolated [official NOAA current-polygon vintage smoke](../data/noaa-geometry-vintage-smoke-2026-11-09.md) passed source hash and report schema checks but correctly retained no_documentary_enc_evidence, historical_geometry_validity=not_verified and rights=review_required for January 2024. Actual historical geofence validation remains pending.

### 2024 federal anchorage source transcription (SPEC-004)

The official annual July 1, 2024 [33 CFR §110.197](../data/cfr-2024-galveston-anchorage-audit.md) supplies DMS corner coordinates for four Galveston/Bolivar Roads regulatory anchorages. An offline, schema-tested audit checks datum/topology and **blocks** GIS/AIS use of unverified rings. Historical status on January 2 and qualified source/geometry review are separate gates. This does not meet FR-011/012 authoritative AIS classification.

### Official 2023/2024 regulatory coordinate consistency

A [GPO official-source engineering scan](../data/cfr-2023-2024-source-verification.md) independently retrieved both annual Title 33 source documents and matched 16/16 DMS coordinate pairs from 33 CFR 110.197. This does not resolve WGS84 datum conversions, A East topology or exact January 2024 legal effect; spatial joins remain blocked.

### Official Federal Register Part 110 index evidence

The bounded [2023-07-01 to 2024-01-02 source query](../data/fr-part110-real-index-2023-2024.md) returned four proposed-rule index entries. Full official FR/LSA text/effective-date verification is still required; no legal or operational event status was upgraded.

### Official Federal Register full-text document triage (SPEC-004)

The source-pinned [2023 original document triage](../data/fr-2023-fulltext-triage.md) retrieves four official text records, records SHA-256 and location/target-section keyword signals, and always requires human legal-effect/LSA review. No historic geographic source or maritime activity is certified.

### Official full-text source and relevance verification (SPEC-004)

The four previously indexed 2023 Federal Register Part 110 document texts were fetched and hashed from original government URLs. All four had no direct 110.197/Houston/Galveston text hits, but this source-tied triage remains *non-certifying*; see [real-source evidence](../data/fr-2023-original-fulltext-evidence-2026-11-09.md). Legal effective-date and GPO LSA review still outstanding.

### SPEC-002: analysis-window censoring (BR-019, FR-021)

`src/harborlens/censoring.py`, `ais.py` and `multiday.py` emit `left_censoring`/`right_censoring` per candidate plus `analysis_window` and `events.censoring` in both manifests. Evidence: synthetic tests in `tests/test_censoring.py` (edges, interior, unknown, sidecars, conflicts, truncation, internal gaps, schemas, CLI). Real-data censored shares have not been measured yet; the existing NOAA reports predate this rule.

### SPEC-002: shared segmentation engine (FR-022, BR-003, #37; fixes #38)

`src/harborlens/segmentation.py` is used by `ais.py` and `multiday.py`; `track_context.py` reads the candidates' `harborlens_method` block; `sensitivity.py` provides descriptive grids. Evidence: `tests/test_segmentation_engine.py` (single-file vs multi-day equivalence on a scenario that exercises every split and discard rule, non-default thresholds, parameter validation, track-context propagation, sensitivity schema). On the same scenario the previous code produced diverging candidates (vessel-type conflict ignored by the single-file command; a same-second fractional-timestamp candidate lost by the multi-day command).

### SPEC-003: labeling pilot tooling (FR-013 partial, #8)

`docs/research/labeling-protocol.md`, `src/harborlens/labeling.py` (`harborlens-label-sample`, `harborlens-label-agreement`) and the `label-record`, `label-sample` and `label-agreement` schemas. Evidence: `tests/test_labeling.py` (reproducibility, blinding, stratum coverage, negatives not overlapping candidates, integrity and overwrite refusal, allocation, kappa against a hand-computed value, invalid-sheet rejection, schema conformance). No labels have been collected; agreement is not accuracy.

### SPEC-003: transceiver class in the labeling sample (FR-013, NFR-004, NFR-010, NFR-020, BR-012, BR-016, #65)

`harborlens-label-sample` stratifies candidates by duration band × censoring × vessel group × transceiver class (`A`, `B`, `absent_or_unknown`) and negative movement intervals by vessel group × transceiver class. Missing, blank and any other value is `absent_or_unknown` and is kept (NFR-020). Sampling stays seeded (NFR-004). When the requested count is smaller than the number of non-empty strata, full cross-cell coverage is impossible and `stratification.all_non_empty_strata_drawn` is false; every transceiver class present in the frame is still drawn when the request is at least the number of those classes. The manifest is `label-sample-v0.2` (`schemas/v1/label-sample.schema.json`). The annotator sheet stays blinded; sheets still contain MMSI and stay out of this repository (BR-016). Evidence: `tests/test_labeling.py` (every non-empty class appears, empty class omitted, a one-item class is drawn once, a short request sets `all_non_empty_strata_drawn` false while covering every present class, invalid and missing classes map to `absent_or_unknown` and are not dropped, seeded repeat, schema). No labels have been collected. A sampled unit is not a berth, anchorage, wait or port call (BR-001). Package `0.2.0.dev1` is part of `run_id`. Runs from `0.2.0.dev0` and `0.2.0.dev1` are not directly comparable; the `0.2.0.dev0` sampling remains reproducible by running that version. Segmentation thresholds are unchanged.

### SPEC-003: evaluator (FR-013, FR-014 partial, #9)

`src/harborlens/evaluation.py` (`harborlens-evaluate`) with `adjudicated-label` and `evaluation-report` schemas. Stratum keys are parsed with the sampling manifest's `schema_version` (`label-sample-v0.2` field count, canonical vessel group, and `A` / `B` / `absent_or_unknown`; `label-sample-v0.1` only when the manifest says so). A damaged key raises `AISInputError` with the `sample_id` instead of becoming a vessel-group cohort (NFR-020). Evidence: `tests/test_evaluation.py` (confusion counts against a constructed truth, unknown and unlabeled exclusion, boundary errors on uncensored true positives, design-weighted precision and L3 basis, lineage and input validation, a v0.2 key ending in `A` rejected with the sample id, hand-computed precision/recall/F1/specificity and a Wilson reference interval) and `tests/test_labeling.py` (explicit v0.1 acceptance, arity, unknown group, unknown class, missing and mismatched schema version). No real labels have been evaluated.

### NFR-007 / FR-008 / FR-009: volume ceilings (#35)

Ceilings in `archive_extract.py`, `multiday.py`, `track_context.py` and `ais.load_cleaned` were set from the synthetic [scale benchmark](../data/scale-benchmark-2026-11-09.md) (3.92 million rows: 78 s, 47 MiB RSS, 628 MiB scratch). Limits and the scratch peak are recorded in manifests and sidecars. Evidence: `tests/test_volume_caps.py`, `tools/benchmark_multiday.py`. NFR-007 for real data still requires the manual seven-day NOAA workflow.

### SPEC-003 / NFR-002, NFR-003, NFR-010, NFR-012: contracts and run identity (#41)

`tests/test_contracts.py` validates real CLI exports against `run-manifest`, `stationary-candidate` (CSV via `read_candidates_csv`) and the new `stationary-candidate-feature` schema; `run_id` includes the package version (`code_version` in both manifests; git commit recorded as metadata in CI). CI runs on Python 3.10 and 3.12; the suite was also run locally on 3.10, 3.12 and 3.13. `CITATION.cff` added.

### SPEC-001 / FR-002, FR-015, BR-008: vessel attributes and MMSI QA flags (#39)

`src/harborlens/vessel.py` (ITU-R M.585 categories, sentinel normalization, per-candidate attribute summary) used by `ais.py`, `multiday.py` and the shared engine. Evidence: `tests/test_vessel_attributes.py` (category table, sentinels, 2024 NOAA header, non-ship identifiers flagged not dropped, attribute equivalence across pipelines, legacy cleaned files). Schemas `ais-point`, candidate record/features and both manifests updated.

### SPEC-001 / FR-001, FR-002: NOAA archive vintages (#36)

`src/harborlens/vintages.py` drives `download.py`, `archive_extract.py` and the seven-day workflow; ingestion separates `missing_value` from `invalid`. Evidence: `tests/test_vintages.py` (registry and refusal, downloader URLs with a mocked network, legacy ZIP extraction through the pipeline, compression/year mismatch, nulls counted as missing). Layout verification for 2015–2023 and 2025–2026 is documentary; no archive of those years has been downloaded by this project yet.
