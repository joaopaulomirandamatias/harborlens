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

The new separate command uses a temporary disk-backed SQLite observation index sorted by MMSI/time. Cross-file duplicate points retain both local-source fingerprints, and low-speed group membership is stored on disk. The emitted event is only a stationary candidate; explicit split diagnostics track gaps, identity conflicts, improbable jumps, collisions and spatial drift. Limits fail closed; no real multi-day performance or event ground truth has yet been measured.
