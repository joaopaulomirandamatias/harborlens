# NOAA Anchorage Area Polygons and AIS Centroid Overlap — Real Integration

**Evidence date:** 2026-11-09 UTC.  
**Combined integration run:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42579525370  
**Purpose:** Engineering verification of geospatial interoperability, NOT official or historical vessel-event classification.

## Source snapshots

**Current polygon reference:** NOAA [OceanReports Designated Anchorage Areas MapServer layer 0](https://maps.coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer/0). This official NOAA service returned 6 features under the Houston research rectangle, including four Polygon and two MultiPolygon geometries. Source object IDs were selected by bounded envelope query and fetched in a separate batch; geometry topology, schema and output hashes were validated. Source geometry SHA-256: acf45bc820518092d20905a9acf8ae364c24d9e95534d9232ad16f7793d8ca01.

**Historical AIS source:** original NOAA Marine Cadastre [2024-01-02 nationwide daily AIS file](https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-01-02.csv.zst), geographically filtered to Houston west -95.70 / south 29.10 / east -94.20 / north 30.10, time 00:00–06:00 UTC. Original daily archive SHA-256: 43bf674d62fddb69251f891fa2e3d92bcc98b3e764298130a5827b3be62d382d. The extracted subset fingerprint was 7d799ae8511a7e427cc6a6e2094834762558ad7963e391c4315c50fb0df5b1bd.

**Candidate context input SHA-256:** 7a3d3db7447782dbf54a3107821bb89d71362cad84c592b14e8d80aebe3912c1.  
**Annotated context output SHA-256:** 19a5343b8af39fd1dbf080830de6664f0bced462abc9b290174ceb548be43dca.  
**Source usage rights:** review_required.  
**Historical polygon validity for AIS 2024:** not_verified.  
**Source review status:** unreviewed.  
**Raw data policy:** no AIS messages or source polygon coordinates were committed to Git or uploaded as GitHub artifacts.

## Observed engineering metrics

| Quantity | Value |
| --- | ---: |
| Current NOAA anchorage area geometries retrieved | 6 |
| Polygon geometries | 4 |
| MultiPolygon geometries | 2 |
| Historical low-speed AIS candidate segments | 920 |
| Candidate centroids with one possible polygon overlap | 77 |
| Candidate centroids within multiple polygons | 0 |
| Candidate centroids without mapped polygon overlap | 843 |
| Polygon/candidate/output file integrity verification | PASS |
| GitHub Actions end-to-end workflow | SUCCESS |

The number 77 indicates spatial overlap between the **centroid** of a provisional AIS stationary candidate and a **current, undated-for-2024** NOAA reference polygon. It does not mean 77 actual anchoring vessels or officially designated 2024 anchorage operations. The 843 without overlaps are not evidence that the vessels were not anchored: the selected polygon set and current geography may be incomplete, and the centroid is not the complete trajectory.

## What was implemented

- A bounded NOAA official polygon layer reader (fixed service URL, source IDs, batches, topology checks, source receipts).
- A separate offline GeoJSON centroid/Polygon overlay preserving unknown and ambiguous cases.
- All AIS events keep confidence_label=unvalidated; the overlay adds only possible_spatial_overlap, ambiguous_multiple_polygons or no_polygon_overlap_observed.
- The historical validity remains not_verified and source rights remain review_required for every overlap.
- The integration workflow is manually triggered only, avoiding repeated national AIS downloads during regular CI.

## Unresolved scientific/operational questions

1. Can a 2024-dated authoritative source confirm which anchorage-area boundaries existed in the historical AIS sample period? The current NOAA response does not prove that.
2. Are any reported polygons geospatially duplicated or generalized across chart scales?
3. Do full vessel tracks (not only their centroids) stay consistently within the relevant polygons, accounting for sampling gaps?
4. Can independent port/terminal events or other ground truth validate an actual anchorage, waiting or berth event?
5. Are source-specific use and redistribution terms adequately reviewed for a public release and commercial derivative work?

## Next delivery gates

- Date/version-aware authoritative polygon registry and transparent spatial evidence quality tiers.
- Robust full-track overlap and uncertainty-aware inference with no forced operational state.
- Ground-truth independent evaluation and error metrics before any official port performance reporting.
- Continue keeping issue #7 open until historical polygon evidence and external event validation are complete.

**NOT FOR NAVIGATION. NO VERIFIED ANCHORAGE, WAITING, BERTH OCCUPANCY OR EMISSIONS CLAIM.**
