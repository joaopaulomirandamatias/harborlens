# SPEC-001: Implementation Work Items

**State:** IMPLEMENTED — SYNTHETIC ONLY. Checking a task requires traceable PR/test evidence.

- [ ] Preserve synthetic unit tests and CLI smoke test
- [x] Add malformed input, ZIP expansion and finite-number tests; full memory benchmarks remain pending
- [ ] Implement output hashes and rights metadata
- [ ] Run a real NOAA archive or ERDDAP query after dataset rights review

## Review gate

- [ ] Acceptance criteria demonstrated
- [ ] Schema and requirements matrix updated
- [ ] Positive, negative and boundary tests pass
- [ ] Source rights and security reviewed
- [ ] No unsupported accuracy, emissions or customer claims

## Official subset adapter

- [x] Develop bounded NOAA PMEL ERDDAP client and mocked tests (on PR branch; review/CI pending).
- [ ] Demonstrate actual NOAA API response and ingestion with source SHA, data QA and a reproduction log.

- [x] Implement streaming date/area filter for a local daily NOAA zstd archive, with synthetic compressed tests (PR review/CI pending).
- [ ] Execute at least one original NOAA daily file under a bounded integration runner and inspect continuous MMSI tracks.

## Volume ceilings (issue #35)

- [x] Extraction ceiling raised to 1,000,000 rows / 256 MiB from measured Houston volumes; limits recorded in the sidecar; full-day test
- [ ] Run `noaa-week-integration` on seven consecutive full days and publish aggregate results
