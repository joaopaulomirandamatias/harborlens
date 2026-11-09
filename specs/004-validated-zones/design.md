# SPEC-004: Technical Design

**State:** PROPOSED

## Architecture and approach

Use versioned EPSG:4326 polygons with source/validity dates; spatial joins and expert review; subsequent independent event validation. Not for navigation.

## Interfaces and contracts

- Python 3.10+; all timestamps RFC 3339 UTC, coordinates WGS84 lon/lat, units explicit.
- Version all public JSON payloads under `schemas/v1`; record method/version/parameters and data vintage.
- Use `unknown` or `unvalidated` when there is no independent evidence.
- No network, private integration or cloud dependency without explicit authorization and data license review.

## Decisions and tradeoffs

Refer to `docs/architecture/adr/`; prefer deterministic batch analysis, visible uncertainty and independent reproducibility over premature complex infrastructure. Schema-breaking changes require a migration note and regression tests.

## Initial implementation: facility point reference catalog

Use a fixed USACE-hosted ArcGIS FeatureServer Layer 0 query, with WGS84 output, strict geographical filtering, deterministic pagination, a maximum number of features and a JSON sidecar carrying the request URLs, retrieval time, SHA-256 and rights status. These are POINT references, not polygons; nearest-point calculations do not establish berth occupancy. Dated authoritative polygon import and independent event validation will be separate changes.

## Proposed NOAA Polygon context

An opt-in source-pinned NOAA polygon feature importer uses bounded ArcGIS object IDs and validates Shapely topology. A separate local overlay maps only unvalidated candidate centroids and reports ambiguous or provisional context. NOAA current source geometry is not verified for 2024 operational activity.

## Full observed-track context (SPEC-004 incremental implementation)

The next research slice stores canonical cleaned AIS rows in an ephemeral, indexed SQLite database and queries each candidate by MMSI and timestamp. It checks observed cardinality, start/end times, speed and gaps, then uses a Shapely STRtree to test all observed points against source Polygon/MultiPolygon geometry (including holes). The status is solely geometric and explicitly preserves no-data, overlapping and source-date ambiguity. Polygon-receipt SHA-256 must match the source geometry file; only historically unreviewed metadata are supported. No full-truth berth or anchor claim is enabled.

## NOAA ENC documentary date screening (incremental)

The geometry vintage audit is deliberately separate from spatial inference. It checks an unreviewed NOAA polygon receipt and optional self-declared ENC edition, issue date, document hash and cell ID. Even a date-compatible publication stays historically not_verified, because the source polygon may not derive from that cell/edition. The CLI has no network activity and cannot upgrade data rights or event status.
