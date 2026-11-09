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

- [x] Develop bounded NOAA PMEL ERDDAP client and mocked tests (merged in #19).
- [ ] Demonstrate actual NOAA API response and ingestion with source SHA, data QA and a reproduction log.

- [x] Implement streaming date/area filter for a local daily NOAA zstd archive, with synthetic compressed tests (merged in #20).
- [ ] Execute at least one original NOAA daily file under a bounded integration runner and inspect continuous MMSI tracks.

## Volume ceilings (issue #35)

- [x] Extraction ceiling raised to 1,000,000 rows / 256 MiB from measured Houston volumes; limits recorded in the sidecar; full-day test
- [ ] Run `noaa-week-integration` on seven consecutive full days and publish aggregate results

## Vessel attributes and MMSI QA (issue #39)

- [x] Keep COG, heading, length, width, draft and transceiver class with sentinels as missing; ITU-R M.585 `mmsi_category` flag with per-run counts; candidate cohort attributes (`tests/test_vessel_attributes.py`)
- [ ] Inspect category and attribute coverage on a real NOAA run (for example the share of Class B and of `leading_zero_ambiguous` MMSIs)

## Archive vintages (issue #36)

- [x] Vintage registry (2015–2023 ZIP, 2024–2026 csv2 zstd), registry-driven downloader that refuses unknown years, ZIP extraction, `missing_value` vs `invalid` counters, `source_vintage` in the sidecar (`tests/test_vintages.py`)
- [ ] Manual smoke for one 2019–2023 day and one 2025 day; record headers, counts and hashes
