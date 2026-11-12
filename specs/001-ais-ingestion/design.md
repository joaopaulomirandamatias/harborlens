# SPEC-001: Technical Design

**State:** IMPLEMENTED — SYNTHETIC ONLY

## Architecture and approach

Current implementation: Python standard-library CSV/gzip/ZIP, optional zstandard, SHA-256 source hash, local file manifests. Future: per-file source-snapshot metadata, bounded decompression and streaming QA.

## Interfaces and contracts

- Python 3.10+; all timestamps RFC 3339 UTC, coordinates WGS84 lon/lat, units explicit.
- Version all public JSON payloads under `schemas/v1`; record method/version/parameters and data vintage.
- Use `unknown` or `unvalidated` when there is no independent evidence.
- No network, private integration or cloud dependency without explicit authorization and data license review.

## Decisions and tradeoffs

Refer to `docs/architecture/adr/`; prefer deterministic batch analysis, visible uncertainty and independent reproducibility over premature complex infrastructure. Schema-breaking changes require a migration note and regression tests.

## SPEC-001 input protection (proposed change)

Bounded readers check compressed bytes, ZIP entries, expansion ratio, decompressed data cap, header shape, malformed rows and finite numeric payloads. These are defensive CLI controls, not a secure user-upload service. Test synthetic adversarial examples first. Large real-data stress and streaming-memory benchmarks remain outstanding.

## Synthetic vessel identifiers (FR-001, FR-002, BR-008, BR-016)

Committed synthetic MMSIs use unassigned MID 199 in the form `1990xxxxx`. Assigned MIDs 201–775 are not used for those identifiers. `mmsi_category` returns `other` when the first digit is `1` and `ship` when the first digit is `2` through `7`, so moving a fixture from MID 367 to MID 199 changes that QA flag from `ship` to `other`. The candidate `event_id` is a SHA-256 of the MMSI, the time bounds, the method version, and the parameter set, so the identifier change also changes `event_id`. A stationary candidate remains unvalidated. It is not a berth, anchorage, wait, port call, or safety signal. Package `0.2.0.dev15`.

The guard in `tests/test_synthetic_ids.py` scans every text file `git ls-files` tracks. The MID is the first three digits of a nine-digit token that is bounded by a non-digit and not preceded by `.`. A longer digit run is not a token. A hexadecimal run of 64 or more characters is not a token. A line that assigns `mmap_size` is not a token. File-exact exclusions are the four package `0.2.0.dev9` goldens and `tests/synthetic_id_map.py`. Digits 2–4 of a leading-0 or leading-9 form are not read. Package stays `0.2.0.dev16` for this scan: it does not change pipeline bytes. Refs #88 (stays open). Refs #84 (stays open).

## Timestamp and download-date grammar (NFR-003, NFR-004, FR-002)

`ais.parse_time` and `harborlens-download-noaa --date` do not call `fromisoformat`. Observation timestamps are ASCII `YYYY-MM-DD`, then `T` or one space, then `HH:MM:SS`, with no fraction or 1 to 6 fractional digits. A missing offset is UTC. `Z` and `±HH:MM` are accepted, and a non-UTC offset is converted to UTC. `--date` is a real `YYYY-MM-DD` calendar date only. Week dates and `YYYYMMDD` are rejected, and a rejected date exits 2 before any network call. Evidence: `tests/test_timeparse.py`. Package `0.2.0.dev13`.
