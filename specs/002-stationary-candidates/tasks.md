# SPEC-002: Implementation Work Items

**State:** IMPLEMENTED — real one- and two-day NOAA smokes; event validity unmeasured. The enforced multi-day pin is the SQLite page cache, no memory map, and a file temp store (2026-11-12). A soft heap limit is requested and enforced only when SQLite says so. Checking a task requires traceable PR/test evidence.

- [x] Preserve existing single-file regression tests; add multi-day cases (synthetic CI verified)
- [x] Implement SQLite-based multi-file sorting and midnight candidate continuity (PR under review)
- [ ] Measure memory cost on authorized real AIS
- [ ] Add conflict identity and comprehensive unknown cases

## Review gate

- [ ] Acceptance criteria demonstrated
- [ ] Schema and requirements matrix updated
- [ ] Positive, negative and boundary tests pass
- [ ] Source rights and security reviewed
- [ ] No unsupported accuracy, emissions or customer claims

- [x] Benchmark source ingestion and scratch disk/memory usage on two authorized consecutive NOAA daily subsets. Measured on seven consecutive full days instead ([2026-11-09 re-run](../../docs/data/noaa-real-data-rerun-2026-11-09.md))
- [ ] Validate source-data rights and real boundary/coverage independently.

- [x] Run one source-pinned consecutive-day NOAA engineering smoke and record process runtime/peak RSS, in the [real-data report](../../docs/data/noaa-consecutive-days-smoke-2024-01-02-03.md).
- [ ] Complete source usage review, multi-period sampling assessment, scratch disk peak benchmark, and independent event-label validation.

## Analysis-window censoring (issue #34)

- [x] Shared censoring module, sidecar verification, explicit window flags, schema updates and synthetic regression tests (`tests/test_censoring.py`)
- [x] Re-run the manual NOAA daily and consecutive-day workflows to measure censored shares on real data ([2026-11-09 re-run](../../docs/data/noaa-real-data-rerun-2026-11-09.md))
- [ ] Apply BR-019 in future duration metrics (SPEC-003 evaluator, #9)

## Shared segmentation engine (issue #37)

- [x] One engine for both CLIs, configurable thresholds, `parameter_set` per candidate, diagnostics by reason, track-context parameter propagation (`tests/test_segmentation_engine.py`)
- [x] Integer-microsecond ordering in multi-day runs (#38)
- [x] Descriptive `harborlens-sensitivity` grid report and schema
- [x] Re-run one source-pinned NOAA smoke with `stationary-v0.2` and record the effect of the unified rules ([2026-11-09 re-run](../../docs/data/noaa-real-data-rerun-2026-11-09.md))
- [ ] Use the sensitivity grid on real data only to describe fragmentation; select thresholds only after labels exist (#8, #9)

## Volume ceilings (issue #35)

- [x] Multi-day, track-context and in-memory ceilings sized from a synthetic 3.92-million-row benchmark ([report](../../docs/data/scale-benchmark-2026-11-09.md)); scratch peak recorded in the manifest; export-phase scratch check uses the configured scratch cap
- [x] Confirm resource use on seven real NOAA days (NFR-007) ([2026-11-09 re-run](../../docs/data/noaa-real-data-rerun-2026-11-09.md))

## Fixed working set for multi-day segmentation (issue #5)

- [x] Pin the enforced controls: SQLite cache (8192 KiB), `mmap_size=0`, and `temp_store=FILE`. Request an 8 MiB soft heap and record whether `ENABLE_MEMORY_MANAGEMENT` makes it enforced (`soft_heap_limit_enforced`). Manifest schema is `multi-day-1.1`. A 1.0 manifest is not treated as 1.1. Wrong file count and existing outputs exit 2 (`tests/test_multiday_bounded.py`).
- [x] Order late and shuffled points on disk by `(mmsi, epoch_us, insertion id)`. Exact duplicates keep both sources (BR-005). A same-timestamp position conflict splits (BR-007). A gap of exactly 15 minutes stays one candidate; 16 minutes splits. `Segmenter` rejects a descending timestamp.
- [x] Measure traced peak and process RSS on synthetic 1, 3, 7, and 14 day inputs in subprocesses. Assert the ceilings in the design. Scratch may grow. Candidates stay `unvalidated`.
- [x] Show single-file cleaned CSV, candidate CSV, and candidate GeoJSON on `tests/fixtures/synthetic_ais.csv` are byte-identical to package `0.2.0.dev9` (`tests/fixtures/single_day_0.2.0.dev9/`). Manifest differs in package version and `run_id` only.
- [ ] Stream the release-path recount past 256 MiB. Proposal only, in the SPEC-002 design. `publication.py` and `release_verify.py` are unchanged. Refs #70 (stays open).
- [ ] Measure this working set on another authorized seasonal NOAA sample. The 2026-11-09 seven-day run predates the soft-heap pin.
