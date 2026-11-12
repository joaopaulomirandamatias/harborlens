# SPEC-004: Technical Design

**State:** PARTIAL — reference geometry and regulatory source audits; no validated classification

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

## 2024 CFR anchorage legal source QA (new implementation)

The official July 1, 2024 annual federal 33 CFR 110.197 explicitly lists DMS corners for four Galveston/Bolivar Roads regulated Anchorage Areas A/B/C/A East. The separate offline standard-library + Shapely legal-source QA stores unmodified DMS tokens, derived numeric coordinates in the **source datum**, a deterministic source-transcription fingerprint, year-specific CFR source reference and fail-closed datum/topology blockers. Section 110.1(d) explicitly warns against assuming NAD83 without source labeling; A/B/C do not label it. A East explicitly says NAD83 but its published vertex order creates an invalid literal Polygon, requiring authoritative review. No GeoJSON and no AIS joining is permitted.

## GovInfo December 2023 / January 2024 LSA index comparison

`lsa_compare.py` is an opt-in source screen for two fixed HTTPS GovInfo monthly LSA PDFs (2023-12 and 2024-01). It does not run from the ordinary `harborlens` command and it does not open a socket unless the process is started with `--fetch`. A redirect that changes that URL is refused. Downloads are capped at 10 MiB and 60 seconds, with at most three redirects. Extracted Title 33 text is used only to count a section token and to read one Part 110 proposed-rule page list. The JSON result is schema-constrained to `legal_effect_on_study_date=NOT_DETERMINED`, `rights_status=review_required`, and `ais_spatial_join_permitted=false`. SHA-256 values are recorded, and any comparison of those digests uses `hmac.compare_digest`. The tool does not join AIS and does not emit a berth, anchorage, wait, port call, or geometry approval. A live PDF hash is not part of this change. Optional `pypdf` (`harborlens[lsa]`, `pypdf>=6.21.4,<7`) is imported only on the fetch path when the caller does not supply a reader. Downloaded bytes must match the pinned SHA-256 and size before that import parses them. `MAX_PDF_PAGES` is 299 and is passed as pypdf `page_tree_maximum_entries` before the page tree is flattened. Copied page-dictionary keys are capped at 1024. Title 33 extraction keeps same-page text before the Title 34 header and drops text before the Title 33 header. Parser failures exit 2 and write nothing. There is no separate wall-clock timeout around parsing. The report records `harborlens_version`. Package `0.2.0.dev9` identifies that artifact. The comparison behavior is unchanged from `0.2.0.dev8`; the version string moved with the package.
