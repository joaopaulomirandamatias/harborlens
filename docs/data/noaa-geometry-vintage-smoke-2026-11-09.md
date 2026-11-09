# NOAA Current Anchorage Geometry Vintage Screening — Historical AIS January 2024

**Evidence date:** 2026-11-09 UTC.  
**Successful integration:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42650275784

This is a conservative software/source-integrity demonstration, **not proof of the anchorage polygons' historical validity, port events or operational states**.

## Official references and study window

- Source: NOAA OceanReports Designated Anchorage Areas ArcGIS MapServer Layer 0, https://maps.coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer/0
- Original source polygon data fetched ephemerally from the NOAA service: 2026-11-09T16:00:21Z, recorded within the source receipt.
- Study window investigated: 2024-01-02 00:00–06:00 UTC.
- Polygon GeoJSON SHA-256: acf45bc820518092d20905a9acf8ae364c24d9e95534d9232ad16f7793d8ca01.
- Associated source receipt SHA-256: 393c89f3b4b2088745d445bd04a0d501fc82e0c77c28fd23f8212c6218e33ea9.
- Historic documentary evidence file: **none**. No edition or issue date from an authenticated January 2024 ENC revision was supplied.
- Rights review: review_required. Original polygon source files were not committed or uploaded to GitHub.

## Verified engineering outcome

| Check | Result |
| --- | --- |
| Fixed official NOAA polygon layer accessible | PASS |
| Bounded source download completed | PASS |
| Polygon file SHA-256 vs NOAA receipt | PASS |
| Source receipt hash recorded | PASS |
| Audit output JSON Schema 2020-12 validated | PASS |
| Study period | 2024-01-02 00:00–06:00 UTC |
| Documentary date assessment | no_documentary_enc_evidence |
| Historical polygon validity | not_verified |
| Maritime operational event validation | not_verified |
| Source reuse rights | review_required |

The software was explicitly designed to fail closed: a date or hash does not upgrade the current NOAA reference polygons to an authoritative 2024 geofence.

## Primary NOAA interpretation

The official [NOAA ENC Dates documentation](https://charts.noaa.gov/ENCs/ENCDates.html) distinguishes the base cell Update Application Date and update Issue Date. The [ENC Downloader](https://charts.noaa.gov/ENCs/ENCs.shtml) distributes current chart data. Neither the current chart catalog nor these publication dates alone establishes the historical presence or exact topology of a particular Anchorage Area polygon in January 2024. The OceanReports dataset is separate from individual S-57 chart cell editions; do not assume a one-to-one historical source match.

## Remaining engineering gates

1. Locate independent, date-compatible source material for January 2024 Houston anchorage areas, including an actual ENC base/update cell or other authoritative archival geometry and source/file checksums.
2. Confirm the archived chart feature classes, revision dates, chart scale and polygon topology correspond to the current NOAA OceanReports reference features, with no invented provenance links.
3. Complete source-specific usage, attribution and redistribution policy review.
4. Run a repeatable historic-to-current geometry comparison with explicit mismatch/unknown results and independent technical review.
5. Obtain independently labeled vessel/terminal events before interpreting AIS stationary candidate overlaps as real anchoring, waiting, berth use or port calls.

**No actual historical archived ENC geometry was acquired or verified in this test. NOT FOR NAVIGATION. NO CONFIRMED HISTORICAL ANCHORAGE OR VESSEL STATES.**
