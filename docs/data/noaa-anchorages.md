# NOAA Designated Anchorage Polygons and Historical AIS Spatial Context

**SPEC-004 — experimental and research-only. NOT FOR NAVIGATION.**

## Sources

[NOAA OceanReports Designated Anchorage Areas](https://maps.coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer/0) provides a polygon feature layer. NOAA [ENC Direct to GIS](https://www.nauticalcharts.noaa.gov/data/gis-data-and-services.html) publishes separate S-57 maritime features. These are different from the USACE facility POINT dataset.

The adapter queries a fixed NOAA layer by geographic envelope, lists source object IDs, and retrieves bounded batches of GeoJSON features. It validates Polygon/MultiPolygon topology using Shapely and stores a source receipt with exact URLs and SHA-256. No data are downloaded without an explicit command.

## Manual acquisition

~~~bash
python -m pip install -e '.[noaa,dev,geo]'
harborlens-fetch-noaa-anchorages --bbox -95.7 29.1 -94.2 30.1 --out data/houston-anchorages.geojson
~~~

The output is a current geospatial reference, NOT an official historical 2024 boundary. Source rights and version applicability remain unverified.

## Conservative spatial overlay

~~~bash
harborlens-zone-context --candidates results/noaa-multiday/stationary_candidates.geojson --polygons data/houston-anchorages.geojson --out results/noaa-multiday/anchorage-context.geojson
~~~

The command processes existing local files offline and checks candidate centroid containment using polygons and holes. It reports possible_spatial_overlap, ambiguous_multiple_polygons or no_polygon_overlap_observed. All inputs must be unvalidated stationary-candidate points; a USACE facility point layer is rejected as a zone.

Every result retains confidence_label=unvalidated and historical_validity=not_verified, and is never reported as confirmed anchoring, waiting, berth occupancy or a port call. An overlap of a centroid cannot verify the full trajectory, time or actual operational state.

## Remaining gates

- Validate live NOAA polygon service responses and the applicable access/redistribution terms.
- Verify authoritative historical boundaries and source revision for the 2024 study period.
- Analyze full track/zone spatial correspondence and conflicts, not just candidate centroids.
- Obtain independent terminal/port reference labels before any operational interpretation.
- No source GeoJSON or private AIS dataset is committed to the public repository.

## First real NOAA Polygon and historical AIS context integration

The [2026-11-09 source-pinned engineering report](noaa-anchorage-real-smoke-2026-11-09.md) records 6 current NOAA geometries, 920 historical unvalidated candidate centroids, 77 possible overlaps and 843 without observed overlaps. The comparison is purely geometrical and is NOT proof of any 2024 berth, anchoring or waiting event.

## Full observed-track context (additional CLI)

The separate [full-track evidence command](full-track-zone-evidence.md) checks all cleaned AIS observations associated with each stationary candidate rather than only the centroid. Even an all-points overlap remains spatial context only, not a confirmed operational event or historically authoritative 2024 geofence.

## Full observed-track comparison with current NOAA polygons

The [real source-pinned comparison](noaa-full-track-context-smoke-2026-11-09.md) demonstrates the limitations of centroid-only spatial context. Historical validity and event truth remain explicitly NOT VERIFIED.

## Additional version evidence gate

The [NOAA ENC date-audit guide](geometry-vintage-audit.md) describes a separate local command for source-edition/issue metadata conflicts. Source dates are not evidence the current polygon matches its historical 2024 footprint.
