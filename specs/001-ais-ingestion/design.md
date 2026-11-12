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

The guard in `tests/test_synthetic_ids.py` scans every text file `git ls-files` tracks. The MID is the first three digits of a nine-digit token bounded by a non-digit. The token pattern is `(?<!\d\.)(?<!\d)(\d{9})(?!\d)`: a longer digit run is not a token, and nine digits are a decimal fraction only when a digit precedes the dot. A hexadecimal run of 64 or more characters is not a token. Only the value that starts immediately after a whole-word `mmap_size` assignment is not a token. An f-string prefix (`f`/`F`, optional `r` on either side, single or triple quotes) whose first three digits are an assigned MID is a token. File-exact exclusions are the four package `0.2.0.dev9` goldens and `tests/synthetic_id_map.py`. Digits 2–4 of a leading-0 or leading-9 form are not read. That scan does not change pipeline bytes. Refs #88 (stays open). Refs #84 (stays open).

## CSV formula hygiene (FR-002, NFR-006)

`src/harborlens/csv_safe.py` prefixes `vessel_type` and `nav_status` on `houston_clean.csv`, and `vessel_type` on stationary-candidate CSVs, when the cell matches `^'*<ignorable>*<trigger>`. The reader used by `load_cleaned`, `read_candidates_csv`, and the release recount removes exactly one apostrophe when the cell matches `^'+<ignorable>*<trigger>`. Numeric fields and MMSI are not prefixed. `source_files_json` is a JSON array. GeoJSON keeps the logical string. Package `0.2.0.dev17`. On `tests/fixtures/synthetic_ais.csv` the three artifacts stay the `0.2.0.dev15` bytes. Refs #90 (stays open). Refs #85 (stays open).

Package `0.2.0.dev19` replaces the runtime whitespace test with one fixed frozenset, `IGNORABLE`. It contains the 29 whitespace characters the previous rule accepted, plus U+FEFF, U+200B, U+200C, U+200D, U+200E, U+200F, U+2060–U+2064, U+206A–U+206F, U+00AD, U+180E, and the invisible bidi controls U+061C, U+202A–U+202E, and U+2066–U+2069. The same main-fixture bytes stay in place. Formula goldens for the extended synthetic fixture are `tests/fixtures/single_day_0.2.0.dev19_formula/`. The dev17 formula goldens stay on disk. Refs #90 (stays open). Refs #85 (stays open).

## Timestamp and download-date grammar (NFR-003, NFR-004, FR-002)

`ais.parse_time` and `harborlens-download-noaa --date` do not call `fromisoformat`. Observation timestamps are ASCII `YYYY-MM-DD`, then `T` or one space, then `HH:MM:SS`, with no fraction or 1 to 6 fractional digits. A missing offset is UTC. `Z` and `±HH:MM` are accepted, and a non-UTC offset is converted to UTC. `--date` is a real `YYYY-MM-DD` calendar date only. Week dates and `YYYYMMDD` are rejected, and a rejected date exits 2 before any network call. Evidence: `tests/test_timeparse.py`. Package `0.2.0.dev13`.
