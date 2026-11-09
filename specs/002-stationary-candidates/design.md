# SPEC-002: Technical Design

**State:** PARTIAL — SYNTHETIC ONLY

## Architecture and approach

Current memory-based per-MMSI sorter and deterministic rules; multi-day streaming partition, conflicting MMSI identity and unknown state need implementation.

## Interfaces and contracts

- Python 3.10+; all timestamps RFC 3339 UTC, coordinates WGS84 lon/lat, units explicit.
- Version all public JSON payloads under `schemas/v1`; record method/version/parameters and data vintage.
- Use `unknown` or `unvalidated` when there is no independent evidence.
- No network, private integration or cloud dependency without explicit authorization and data license review.

## Decisions and tradeoffs

Refer to `docs/architecture/adr/`; prefer deterministic batch analysis, visible uncertainty and independent reproducibility over premature complex infrastructure. Schema-breaking changes require a migration note and regression tests.

## SQLite multi-day implementation (in review)

The new separate command uses a temporary disk-backed SQLite observation index sorted by MMSI/time. Cross-file duplicate points retain both local-source fingerprints, and low-speed group membership is stored on disk. The emitted event is only a stationary candidate; explicit split diagnostics track gaps, identity conflicts, improbable jumps, collisions and spatial drift. Limits fail closed; processing time and process RSS were measured for one authentic two-day sample; event ground truth remains unmeasured.

## Analysis-window censoring (BR-019, issue #34)

`src/harborlens/censoring.py` is shared by both pipelines. The window comes from a verified acquisition sidecar (`harborlens-extract-noaa-archive` or `harborlens-fetch-erddap`, matched by SHA-256 of the input bytes) or from explicit `--window-start/--window-end`. Multi-day runs use per-input sidecars only when every input has one; windows separated by no more than `max_gap_minutes` merge into one block because segmentation can bridge them, and larger separations are reported as `internal_gaps`. A candidate is censored on a side when its observed start/end lies within `max_gap_minutes` of its block edge (rule `window-edge-v1`). Segmentation, method versions and event IDs are unchanged; a known window is added to `run_id`, while runs without a window keep the previous `run_id` derivation. Censoring describes observation coverage only and never upgrades a candidate to an operational event.
