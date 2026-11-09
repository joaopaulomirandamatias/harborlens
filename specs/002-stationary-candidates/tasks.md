# SPEC-002: Implementation Work Items

**State:** PARTIAL — SYNTHETIC ONLY. Checking a task requires traceable PR/test evidence.

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

- [ ] Benchmark source ingestion and scratch disk/memory usage on two authorized consecutive NOAA daily subsets.
- [ ] Validate source-data rights and real boundary/coverage independently.

- [x] Run one source-pinned consecutive-day NOAA engineering smoke and record process runtime/peak RSS, in the [real-data report](../../docs/data/noaa-consecutive-days-smoke-2024-01-02-03.md).
- [ ] Complete source usage review, multi-period sampling assessment, scratch disk peak benchmark, and independent event-label validation.

## Analysis-window censoring (issue #34)

- [x] Shared censoring module, sidecar verification, explicit window flags, schema updates and synthetic regression tests (`tests/test_censoring.py`)
- [ ] Re-run the manual NOAA daily and consecutive-day workflows to measure censored shares on real data
- [ ] Apply BR-019 in future duration metrics (SPEC-003 evaluator, #9)
