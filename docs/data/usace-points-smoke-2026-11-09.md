# Houston USACE Navigation Facilities — Real Source Integration

**Evidence date:** 2026-11-09 UTC.  
**Successful GitHub Actions run:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42578053891

**Scope:** Real current official facility reference POINTS, not historical berth polygons, validated waiting vessels or port operations.

## Source and reproducibility

- Provider: U.S. Army Corps of Engineers (USACE), hosted through USDOT/BTS National Transportation Atlas Database.
- Catalog: https://catalog.data.gov/dataset/docks (data last updated September 30, 2026).
- Fixed FeatureServer layer: https://services7.arcgis.com/n1YM8pTrFmm7L4hs/ArcGIS/rest/services/Docks/FeatureServer/0
- Research bounding box: west -95.70, south 29.10, east -94.20, north 30.10. Output EPSG:4326; source service metadata EPSG:4269.
- ArcGIS query: envelope intersection, 250 records per page, maximum 2,000 results, OBJECTID ordering; 3 requests were completed.
- SHA-256 of generated GeoJSON: ef082fd04e7e95de3368002e129ac122c79d919a65befa6c672c89f4ad3e0d27.
- Source use status: review_required. The public-domain catalog marking is evidence for further rights review, not an implicit contractual approval.
- Raw facility GeoJSON and attributes were NOT committed or uploaded to public build artifacts.

## Aggregate results

| Engineering measurement | Observed |
| --- | ---: |
| Facility reference points returned | 723 |
| Validated Point geometries | 723 |
| FAC_TYPE: Dock | 536 |
| Milepoint | 133 |
| Unspecified type | 24 |
| Junction | 12 |
| Open Water | 7 |
| Fleeting Area | 7 |
| Other types | 4 |
| Query pages | 3 |
| GeoJSON schema check | PASS |
| Provenance metadata schema check | PASS |
| Local output SHA-256 | PASS |

These are records in the queried rectangle and dataset snapshot, not an official census of currently operative berths or anchored vessels.

## Limitations

1. The service contains Point geometries, not certified polygons of dock footprints or anchorage areas. Being close to a Point does not establish a vessel's berthing or waiting state.
2. The retrieved service is a current 2026 snapshot. It is not confirmed historical 2024 geometry; using these points alongside 2024 AIS does not prove that the facilities existed at the earlier date.
3. Facility type and name metadata come from the source dataset; no maritime event classification or precision analysis was performed.
4. This is neither a navigational service nor an official USACE port occupancy report. Do not infer emissions, economic costs or causal delays.
5. No independent geofence review or labeled validation dataset exists for this output.

## Next development gates

- Locate NOAA ENC Direct-to-GIS authoritative Polygon features for anchorage/berth areas; verify exact S-57 layer, release date, topology and data terms.
- Implement a local versioned Polygon/MultiPolygon loader with effective dates, reviewer evidence and conservative unknown-state behavior.
- Compare candidate centroids/segments against reviewed polygons only as provisional spatial context, not verified port event status.
- Add spatial boundary, hole, overlap and source-date mismatch regression tests.
- Keep issue #7 open until dated polygon validation and source rights review are completed.

**NOT FOR NAVIGATION. NOT VERIFIED WAITING, BERTHING OR PORT CALLS.**
