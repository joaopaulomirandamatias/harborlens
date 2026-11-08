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
