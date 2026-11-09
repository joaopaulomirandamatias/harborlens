# USACE Navigation Facilities: Point Catalog (SPEC-004)

**Status:** Experimental, opt-in reference-point adapter. **Not a berth/anchorage polygon and not for navigation.** No operational vessel event is verified by these coordinates.

## Official sources and semantics

- [USACE WCSC Navigation Infrastructure](https://www.iwr.usace.army.mil/About/Technical-Centers/WCSC-Waterborne-Commerce-Statistics-Center/WCSC-Navigation-Infrastructure/) describes docks, anchorages and other navigation infrastructure.
- [USDOT/BTS NTAD Navigation Facilities public-domain catalog](https://catalog.data.gov/dataset/docks), updated September 30, 2026, describes data supplied by USACE.
- [Hosted USACE Navigation Facilities ArcGIS FeatureServer](https://services7.arcgis.com/n1YM8pTrFmm7L4hs/ArcGIS/rest/services/Docks/FeatureServer/0) is **point geometry** in NAD83 (EPSG:4269), requested as longitude/latitude in WGS84 (EPSG:4326).
- [USACE Navigation Facilities spreadsheet, September 2026](https://iwrlibrary.sec.usace.army.mil/resource?documentId=571ab18a-e904-468a-93a7-0a910bd4bdb7) is an alternative tabular source.
- [NOAA ENC Direct to GIS](https://www.nauticalcharts.noaa.gov/data/gis-data-and-services.html) is a *different* source for S-57 feature geometry and potential polygon boundaries, subject to verification of the exact layer, date and restrictions.

**Critical distinction:** a facility POINT can indicate the reported location of a dock, anchorage-related point or other navigation feature. It **cannot** establish physical berth boundaries, anchorages, operational occupancy or a historical 2024 facility state. The service's current snapshot must not be retroactively presented as a verified January 2024 geometry.

## Opt-in reproducible query

~~~bash
python -m pip install -e '.[dev]'
harborlens-fetch-usace --bbox -95.70 29.10 -94.20 30.10 \
  --out data/houston-usace-facilities.geojson --page-size 250 \
  --max-features 2000
~~~

This command makes explicit HTTP requests only to the fixed official ArcGIS FeatureServer URL. It applies a geographical bounding envelope server-side and then checks the returned WGS84 coordinates locally. A page is limited to 500 results and the full local output to 2,000 facilities. **Pagination limit, duplicate source identifiers, malformed geometry, invalid JSON, no results and an unexpected polygon are errors.** No silent truncation.

Two local outputs:
- \`houston-usace-facilities.geojson\`: POINT-only FeatureCollection; properties carry the upstream identifiers, names, type/port attributes and explicit \`facility_status=reference_point_only\`, \`event_verification=not_verified\`.
- \`houston-usace-facilities.geojson.source.json\`: source and exact query URLs, output SHA-256, count, retrieval time, EPSG:4326 and rights state \`review_required\`.

The adapter does not require dependencies outside Python's standard library; tests use synthetic ArcGIS JSON responses and do not access the network. **Do not commit actual downloaded facility data** until redistribution and attribution requirements are reviewed. This is public-data enrichment, not a licensed commercial feed.

## How to use with HarborLens candidates

Treat these locations as **background/reference points only** on a future map. The next distinct step is to import independently documented, dated anchorages and berth polygons from suitable NOAA/USACE geometry and apply point-in-polygon containment to unvalidated stationary candidates, preserving unknown/ambiguous outputs. Candidate proximity must not automatically be called "berth", "anchorage waiting", or "port call."

## Remaining gates

- Run a controlled real Houston point fetch and publish **aggregate-only** counts, hashes and schema observations.
- Confirm the live source version and legal attribution; compare to current USACE spreadsheet.
- Obtain suitable authoritative dated polygon datasets, not point-to-circle approximations, and document historical validity and topology.
- Add independent operational reference labels before making any confirmed waiting/berth claims.
- Keep \`rights_status=review_required\` until source-specific terms and attribution are reviewed.

**NOT FOR NAVIGATION. NOT A SAFETY, PORT CONTROL OR GOVERNMENT ENDORSEMENT TOOL.**
