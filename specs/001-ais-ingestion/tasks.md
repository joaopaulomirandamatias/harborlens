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
- [x] Plant an assigned-MID token in a temporary notebook and in a temporary module under `src/`, and expect the guard to fail. A run of eight digits does not match. A 64-character SHA-256 hex run that contains a nine-digit assigned-MID run does not match. Package stays `0.2.0.dev21`. Evidence: `tests/test_synthetic_ids.py`. Refs #88 (stays open). Refs #84 (stays open).
- [x] Close the deferred synthetic-ID guard gaps with fixed sets: underscore-grouped digits, `DIGIT_SPLITTERS`, `\u` escapes of ASCII digits and those splitters, UTF-16 and UTF-32 BOMs, ISO-8859-1 for other non-UTF-8 files, a pinned `tests/synthetic_id_map.py` key set, a SHA-256 exclusion that does not hide an identifier glued to either end of a longer hex run, and an `mmap_size` exclusion that does not cross a newline. A tracked NUL byte without a UTF-16 or UTF-32 BOM fails the coverage test. Package stays `0.2.0.dev23`. Evidence: `tests/test_synthetic_ids.py`. Refs #88 (stays open). Refs #84 (stays open).
- [x] Prefix free-text AIS cells in `houston_clean.csv` and stationary-candidate CSVs with the shared neutralizer. Numeric columns and MMSI stay unchanged. On `tests/fixtures/synthetic_ais.csv` the three artifacts stay the `0.2.0.dev15` bytes. Package `0.2.0.dev17`. Refs #90 (stays open). Refs #85 (stays open).
- [x] Treat invisible format characters before a trigger as ignorable using one fixed frozenset, `IGNORABLE`, so Python 3.10 and 3.12 write the same bytes. Keep the apostrophe rule. On `tests/fixtures/synthetic_ais.csv` the three artifacts stay the `0.2.0.dev15` bytes. Package `0.2.0.dev19`. Evidence: `tests/test_csv_safe.py`, `tests/test_csv_formula_diff.py`. Refs #90 (stays open). Refs #85 (stays open).

## Timestamp parity (issue #78)

- [x] Parse NOAA observation timestamps and `harborlens-download-noaa --date` without `fromisoformat`, with the same acceptance on Python 3.10 and 3.12 (`tests/test_timeparse.py`, FR-002, NFR-003, NFR-004). Refs #78 (stays open).
- [x] `harborlens-fr-timeline` exits 2, with the `FederalRegisterAuditError` message and no traceback, when `--start` or `--end` is not a real ASCII `YYYY-MM-DD` date. No network client is created. Package `0.2.0.dev18` left a start date after the end date as the window error from `initial_url`. Evidence: `tests/test_fr_timeline.py`. Found during the #78/#81 review. Refs #82 (stays open).
- [x] `harborlens` exits 2, with one `error:` line and no traceback, when `--input` is missing, empty, or lacks a required column (`mmsi`, `timestamp`, `lat`, `lon`, `sog`, first missing name in that order). `--debug` adds the traceback and still exits 2. `--version` / `-V` and `--help` exit 0. Every console script answers `--version` with `{prog} {package_version}`. `harborlens-verify` exits 2 only when the manifest cannot be read; a hash mismatch stays exit 1 with `{"ok": false}`. Package `0.2.0.dev21`. Evidence: `tests/test_cli_contract.py`. Refs #94 (stays open). Refs #82 (stays open).
- [x] `harborlens --source-url` exits 2, with one `error:` line and no traceback, when the value is empty, has no host, is not `http` or `https`, includes credentials, or has an unbalanced IPv6 bracket (`http://[::1`, `http://[`). The check runs before any output file is written. `http://example.org` and `https://example.org/ais.csv` are accepted and stay `review_required`. Package stays `0.2.0.dev22`. Evidence: `tests/test_provenance.py`, `tests/test_cli_contract.py`. Refs #94 (stays open). Refs #82 (stays open).
- [x] The same exit rejects whitespace or a C0, DEL, or C1 control in the raw `--source-url` before `urlsplit` strips tab, CR, and LF, a space in the host, and a port that is not an integer from 1 through 65535. Port 0 is rejected. Port 1, port 65535, and an empty port stay accepted. A format character (category Cf) is rejected. A query or fragment name on the credential heuristic (`token`, `access_token`, `api_key`, `secret`, `password`, `sig`, `signature`, `auth`, and `x-amz-*`) is rejected. `?q=1` stays accepted. The list is a heuristic. The URL is not copied into the error. Package `0.2.0.dev23` because a non-ASCII digit MMSI is no longer written. Evidence: `tests/test_provenance.py`, `tests/test_cli_contract.py`. Refs #94 (stays open).
- [x] `harborlens-fr-timeline` exits 2, with that rule's own message and no traceback, when a real calendar window breaks one rule. The first true rule wins: start after end (`2024-01-02` then `2023-07-01`), start before 1994-01-01 (`1993-12-31` then `1994-01-02`), end after the UTC today frozen at 2026-11-21 (`2026-11-01` then `2026-11-22`), or a span of 371 days (`2025-01-01` then `2026-01-07`). No `Request` is built and `urlopen` is not called. A span of 370 days (`2025-01-01` then `2026-01-06`), start equal to end, end equal to that frozen today, and start equal to 1994-01-01 pass. The clock is UTC, not the local date. `initial_url` checks the same rules. An existing output and a download failure also exit 2. Package `0.2.0.dev20`. Evidence: `tests/test_fr_timeline.py`. Refs #94 (stays open). Refs #82 (stays open).
