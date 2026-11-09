# SPEC-003: Technical Design

**State:** PROPOSED

## Architecture and approach

Versioned source snapshot schema, label guide, stratified evaluation, provenance graph and immutable run references. No current real-event labels.

## Interfaces and contracts

- Python 3.10+; all timestamps RFC 3339 UTC, coordinates WGS84 lon/lat, units explicit.
- Version all public JSON payloads under `schemas/v1`; record method/version/parameters and data vintage.
- Use `unknown` or `unvalidated` when there is no independent evidence.
- No network, private integration or cloud dependency without explicit authorization and data license review.

## Decisions and tradeoffs

Refer to `docs/architecture/adr/`; prefer deterministic batch analysis, visible uncertainty and independent reproducibility over premature complex infrastructure. Schema-breaking changes require a migration note and regression tests.

## Incremental design: source-rights decisions in acquisition receipts

The optional `rights_receipt` function reads a bounded local registry once, checks a source/version/purpose-specific reviewer assertion, and fingerprints the very bytes evaluated. NOAA ERDDAP binds to `AIS2024_AIS`; local archives bind to the source-file digest; mutable USACE and NOAA polygon query results bind to canonical output hashes. No registry or a missing/unmatched/malformed decision yields `review_required`. This is audit metadata only, not export authorization. Historical validity, event truth and license verification remain independent controls. See `docs/data/rights-adapter-integration.md`.
