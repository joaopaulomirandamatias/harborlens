# Changelog

## [Unreleased]

### Added (SPEC-004 observed-track evidence)
- Local Shapely/SQLite full-track vs Polygon reference context with interval/cardinality checks, historic-vintage flags, source receipt hashes, strictly unverified statuses and synthetic/schema tests.


### Added (SPEC-004: NOAA Polygon reference)
- Opt-in NOAA designated anchorage polygon source, conservative candidate spatial-context overlay and synthetic geometry regression tests. No event confirmation.


### Added (SPEC-004: initial)
- Bounded opt-in official USACE point-feature reference import with output/source hashes, contracts and synthetic regression tests; no inferred berth polygons or port-event truth.


### Added
- SQLite-based multi-day AIS candidate reconstruction with source provenance, cross-midnight grouping and bounded local processing.
- Synthetic regression tests, multi-day JSON Schemas and schema validation in CI.
- A source-pinned NOAA 2024-01-02/03 engineering experiment and manual-only national-archive workflow.

### Limitations
- Historical candidate segments have no independently validated berth, anchorage, waiting-time or emissions interpretation.


Following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-11-08

### Added
- NOAA-style AIS input normalization, batch quality counters, input hash and stationary-candidate baseline.
- Synthetic fixture and regression tests; Python package CLI.
- SDD specification baseline, requirement IDs, JSON Schemas, architecture, security and research documentation.

### Limitations
- Tested only with fictional AIS data. No actual vessel, port waiting, berth, anchorage, emissions, real-world accuracy or commercial service is verified.

### Verified geospatial source integration

- Initial bounded USACE Navigation Facilities POINT catalog query for Houston: 723 features and 536 Dock records; output SHA-256 and schema checks passed; no dated berth polygon or confirmed port-event status. See docs/data/usace-points-smoke-2026-11-09.md.

### Verified engineering integration of NOAA reference polygons

- Source-pinned NOAA Designated Anchorage Areas real-data query and historical AIS candidate centroid overlay completed. Six current areas, 920 unvalidated candidates, 77 possible centroid overlaps; no historical anchorage or waiting truth established. See docs/data/noaa-anchorage-real-smoke-2026-11-09.md.

### First authentic full-track Polygon geometric comparison

- NOAA 2024-01-02 historical AIS and six current NOAA reference polygons: 920 unvalidated candidate segments; 74 with all observed points within one polygon, 5 with partial point coverage and 841 without observed-point overlap. [Source-pinned evidence](docs/data/noaa-full-track-context-smoke-2026-11-09.md). Operational event and historical polygon validity remain unverified.

### Added (SPEC-004: historical source-vintage screening)

- Offline NOAA ENC documentary date audit checks current polygon/source hashes and optional unverified ENC metadata; all outputs deny automatic historical certification and retain review_required rights.
