# SPEC-001: AIS ingestion, normalization and provenance

**Status:** IMPLEMENTED — synthetic regression tests and one initial real NOAA archive ingestion smoke; event labels unvalidated · **Created:** 2026-11-08; **Updated:** 2026-11-12.

## Problem / user story

A researcher needs a source-pinned local AIS batch with reliable input field normalization and explicit quality exclusions.

## Linked requirements

FR-001..004, FR-008; NFR-002..006; BR-002, BR-004..006

## Acceptance criteria

1. **Given** a valid NOAA-style CSV; **when** the CLI runs; **then** normalized UTC observations, bbox and exact-dedup counts, SHA-256 and outputs are generated.
2. **Given** invalid, duplicate and out-of-zone rows; **when** ingest runs; **then** each exclusion type is reported separately and invalid rows do not enter cleaned output.
3. **Given** unsupported or malformed data; **when** a batch is requested; **then** a clear error or rejection is produced; no fabricated event is returned.
4. **Given** a NOAA-style timestamp on Python 3.10 or 3.12; **when** it is parsed; **then** both interpreters accept `YYYY-MM-DD`, an uppercase `T` or one space, `HH:MM:SS`, no fraction or 1 to 6 fractional digits, and an optional `Z` or `±HH:MM`. A missing offset means UTC. A non-UTC offset is converted to UTC. Seven fractional digits, a comma fraction, `+HHMM`, a non-ASCII digit, hour 24, a non-leap 29 February, and trailing junk are rejected on both.
5. **Given** `harborlens-download-noaa --date`; **when** the value is not a real ASCII `YYYY-MM-DD` date, including an ISO week date or `YYYYMMDD`; **then** the command exits 2, writes nothing, and does not open a network connection. 29 February is accepted only in a leap year.
6. **Given** the files `git ls-files` tracks; **when** `tests/test_synthetic_ids.py` runs; **then** no nine-digit token whose first three digits are an MID in 201–775 remains outside a file-exact exclusion or a documented context exclusion (a hexadecimal run of 64 or more characters, or the value assigned by a whole-word `mmap_size`). A run of ten or more digits does not match. Nine digits after a digit and a dot are a decimal fraction and do not match. A dot that is not part of a decimal still matches.
7. **Given** a free-text AIS cell (`vessel_type` or `nav_status`, including a fullwidth trigger or U+FEFF or U+200B before a trigger) that matches `^'*<ignorable>*<trigger>`; **when** `harborlens` or `harborlens-multiday` writes `houston_clean.csv` or a stationary-candidate CSV; **then** the cell is prefixed with one apostrophe and the reader recovers the logical text by removing exactly one apostrophe only when the cell matches `^'+<ignorable>*<trigger>`. Numeric columns, including a negative longitude, and MMSI are not prefixed. `source_files_json` stays a JSON array. GeoJSON is not neutralized. On `tests/fixtures/synthetic_ais.csv` the three pipeline artifacts stay byte-identical to package `0.2.0.dev15`.
8. **Given** `harborlens-fr-timeline --start` or `--end`; **when** the value is not a real ASCII `YYYY-MM-DD` date, including an ISO week date, `YYYYMMDD`, non-ASCII digits, or an impossible calendar day; **then** the command exits 2, prints the `FederalRegisterAuditError` message, prints no traceback, and does not open a network connection (FR-002, FR-011, NFR-003, NFR-004, NFR-009, NFR-010, NFR-015). A start date after the end date remains the existing window error from `initial_url` and is not turned into exit 2. Valid dates follow the existing scan. This does not approve a berth, anchorage, wait, or port call (BR-009, BR-018).

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
