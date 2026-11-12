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
- [x] Run `noaa-week-integration` on seven consecutive full days and publish aggregate results ([2026-11-09 re-run](../../docs/data/noaa-real-data-rerun-2026-11-09.md))

## Vessel attributes and MMSI QA (issue #39)

- [x] Keep COG, heading, length, width, draft and transceiver class with sentinels as missing; ITU-R M.585 `mmsi_category` flag with per-run counts; candidate cohort attributes (`tests/test_vessel_attributes.py`)
- [x] Inspect category and attribute coverage on a real NOAA run (for example the share of Class B and of `leading_zero_ambiguous` MMSIs) ([2026-11-09 re-run](../../docs/data/noaa-real-data-rerun-2026-11-09.md))

## Archive vintages (issue #36)

- [x] Vintage registry (2015–2023 ZIP, 2024–2026 csv2 zstd), registry-driven downloader that refuses unknown years, ZIP extraction, `missing_value` vs `invalid` counters, `source_vintage` in the sidecar (`tests/test_vintages.py`)
- [ ] Manual smoke for one 2019–2023 day and one 2025 day; record headers, counts and hashes

## Synthetic identifier guard

- [x] Scan every git-tracked text file for a nine-digit token whose first three digits are an assigned MID in 201–775. File-exact exclusions and context exclusions each carry a written reason. A decimal fraction and a run of 10 or more digits do not match. Package stays `0.2.0.dev16`. Refs #88 (stays open). Refs #84 (stays open).
- [x] Prefix free-text AIS cells in `houston_clean.csv` and stationary-candidate CSVs with the shared neutralizer. Numeric columns and MMSI stay unchanged. On `tests/fixtures/synthetic_ais.csv` the three artifacts stay the `0.2.0.dev15` bytes. Package `0.2.0.dev17`. Refs #90 (stays open). Refs #85 (stays open).
- [x] Treat invisible format characters before a trigger as ignorable using one fixed frozenset, `IGNORABLE`, so Python 3.10 and 3.12 write the same bytes. Keep the apostrophe rule. On `tests/fixtures/synthetic_ais.csv` the three artifacts stay the `0.2.0.dev15` bytes. Package `0.2.0.dev19`. Evidence: `tests/test_csv_safe.py`, `tests/test_csv_formula_diff.py`. Refs #90 (stays open). Refs #85 (stays open).

## Timestamp parity (issue #78)

- [x] Parse NOAA observation timestamps and `harborlens-download-noaa --date` without `fromisoformat`, with the same acceptance on Python 3.10 and 3.12 (`tests/test_timeparse.py`, FR-002, NFR-003, NFR-004). Refs #78 (stays open).
