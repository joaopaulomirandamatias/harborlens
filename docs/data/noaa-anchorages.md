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
