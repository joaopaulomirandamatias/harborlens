# Historical AIS Full Observed Track versus Current NOAA Anchorage Polygons

**Evidence date:** 2026-11-09 UTC.  
**Successful isolated integration:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42644667083  
**Status:** Technical demonstration of source-pinned spatial observation calculations. No independent historical vessel-event or geofence validity assessment has been made.

## Input sources and study bounds

- **Historical AIS**: Official NOAA Marine Cadastre nationwide daily Zstandard archive for 2024-01-02, source https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-01-02.csv.zst, selected Houston WGS84 research rectangle (-95.70, 29.10, -94.20, 30.10) and 00:00–06:00 UTC.
- **Current polygon source**: NOAA OceanReports Designated Anchorage Areas, https://maps.coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer/0. Six reference geometries were returned. Their suitability as **January 2024** geofences was **not established**.
- **NOAA AIS original archive SHA-256**: 43bf674d62fddb69251f891fa2e3d92bcc98b3e764298130a5827b3be62d382d
- **Selected Houston AIS CSV SHA-256**: 7d799ae8511a7e427cc6a6e2094834762558ad7963e391c4315c50fb0df5b1bd
- **Cleaned AIS SHA-256**: f09fdd17f6609428573aac19aa083b39eba094ae9e59cac307fa53e506063987
- **Candidate GeoJSON SHA-256**: 7a3d3db7447782dbf54a3107821bb89d71362cad84c592b14e8d80aebe3912c1
- **NOAA polygon GeoJSON SHA-256**: acf45bc820518092d20905a9acf8ae364c24d9e95534d9232ad16f7793d8ca01
- **Polygon source receipt SHA-256**: f034bf822480e109c42f3d6b0c5edb7ca4a8f72e2edbca0c46bf053f80eeff68
- **Full observed-track overlay SHA-256**: 85b4a1201960d69c32ab1d15252b782ed31fe1537c205e0efca9c2841c8afb13
- **Source rights**: review_required. No actual AIS positions, MMSIs or raw polygon coordinates were committed or uploaded as artifacts.

## Measured aggregate results

| Category | Number |
| --- | ---: |
| Historical stationary candidate episodes (not verified maritime events) | 920 |
| NOAA current reference polygons | 6 |
| **Previous centroid-only**: exactly one Polygon covers centroid | 77 |
| Previous centroid-only: more than one polygon covers centroid | 0 |
| Previous centroid-only: no provided polygon covers centroid | 843 |
| **Full observed-track**: all recorded points covered by one polygon | 74 |
| Full observed-track: some points covered and some outside | 5 |
| Full observed-track: no recorded point covered by supplied polygons | 841 |
| Full observed-track: multiple-zone evidence ambiguous | 0 |
| Full observed-track: incomplete/unknown due to count/gap conflicts | 0 |
| Full observed-track: confirmed maritime events | 0 |
| Candidate counts reconciled and local output hashes verified | PASS |

The two approaches are not directly subtractable case-by-case from aggregate totals: a centroid can fall outside a polygon even if some track positions fall inside, and vice versa. Differences here demonstrate why using every discrete observation is more informative than simply comparing one centroid.

A status of all_observed_points_within_one_polygon means **all available AIS messages** for the candidate are spatially covered by one polygon, not that unobserved parts of the vessel path remained inside, that the polygon was officially valid in 2024, or that the ship was legally or operationally anchored.

## Implementation and reproducibility

The implementation uses the offline harborlens-track-context CLI with the previously emitted cleaned AIS CSV, stationary candidates GeoJSON, and NOAA polygon GeoJSON plus its matching source receipt. It indexes AIS observations by MMSI and integer-microsecond UTC in a bounded temporary SQLite database, verifies expected candidate cardinality and time boundaries, and checks every observed coordinate using a Shapely Polygon/MultiPolygon spatial index.

Output status families explicitly separate full observed-point coverage, partial coverage, no observed coverage, overlaps and incomplete evidence. Source dates can be tested against optional **user-declared** effective date ranges, but these do not create authoritative historical validation. All output retains confidence_label=unvalidated, historical_validity=not_verified and review_required rights.

## Reproducibility and safety controls

The integration ran in an ephemeral GitHub Actions runner. The workflow will be manual-only in the default branch and no real AIS data or polygon source files are committed or uploaded as artifacts. The results are **not for navigation**, are not an official port occupancy report, and provide no confirmed berth, anchorage, waiting, congestion or emission values.

## Remaining gates

1. Acquire independently supported **historical January 2024** polygon revisions or corroborating authoritative records and document geometry/source dates.
2. Assess AIS coverage, gaps and segmentation uncertainty across multiple periods and validate historical applicability of geometry.
3. Record independently labeled operational events, positive and negative examples, and evaluate actual classification errors before upgrading a provisional event to any verified operational class.
4. Benchmark end-to-end resource usage (download, extraction, SQLite disk and memory) under multiple data volumes and source records.
5. Keep issue #7 open while source rights, dated polygon provenance and operational event truth remain unresolved.

## Censoring caveat (added with BR-019)

This run predates the analysis-window censoring flags. Candidates that touch the edges of the extracted window have durations that are only lower bounds, and their number was not measured here. Re-running the manual workflow records `left_censoring`/`right_censoring` and run-level counts from the extraction sidecar.

**NOT FOR NAVIGATION. NOT VERIFIED ANCHORAGE, BERTHING, VESSEL WAITING OR PORT CALLS.**
