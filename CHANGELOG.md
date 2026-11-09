# Changelog

## [Unreleased]

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
