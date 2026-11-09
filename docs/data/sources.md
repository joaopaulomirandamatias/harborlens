# Official Data Sources and Rights

| Source | Use | Restrictions / evidence limits |
| --- | --- | --- |
| [NOAA Marine Cadastre AIS](https://marinecadastre.gov/ais/) | AIS timestamps, positions, headings, transmitted speed and status | Historical coverage varies; confirm file schema, rights and permitted redistribution; not live |
| [NOAA AccessAIS](https://coast.noaa.gov/digitalcoast/tools/ais.html) | Optional AOI extraction | Availability not guaranteed; fallback to published archive |
| [NOAA AIS Data Dictionary](https://coast.noaa.gov/data/marinecadastre/ais/data-dictionary.pdf) | Historical schema aliases | Inspect actual version; documentation may cover specific vintages |
| [USACE WCSC](https://www.iwr.usace.army.mil/About/Technical-Centers/WCSC-Waterborne-Commerce-Statistics-Center/) | Facilities, docks, statistics | Points are not validated berth polygons |
| [BTS Ports](https://www.bts.gov/ports) | Aggregate berthing and volume benchmarks | Cannot validate each inferred event |
| [Port Houston statistics](https://porthouston.com/about/our-port/statistics/) | Published regional context | Scope may not match the whole Houston Ship Channel |
| [EPA Port Emissions Inventory Guidance](https://www.epa.gov/state-and-local-transportation/port-emissions-inventory-guidance) | Reference for planned emissions scenarios | Needs vessel engine/fuel/power factors and independent review |
| [NOAA CO-OPS API](https://api.tidesandcurrents.noaa.gov/api/dev) | Optional water and weather covariates | Respect station datum, quality flags, data vintage |

Every future download records agency, source URL, downloaded-at UTC, dataset version, file SHA-256, geographic/temporal coverage, permitted use and restrictions. Do not commit real or licensed AIS datasets, customer data or prohibited enrichments. A public HTTP endpoint does not automatically grant commercial redistribution rights.

Houston research rectangle W=-95.70 S=29.10 E=-94.20 N=30.10 is NOT an official maritime zone. Choose source-specific data quality and rights review before any commercial deployment.

## Optional PMEL geographic AIS subset

The [PMEL AIS2024_AIS dataset](https://data.pmel.noaa.gov/pmel/erddap/info/AIS2024_AIS/index.html) supports bounded time/geographic queries and lists a CC0-1.0 dedication for that dataset. The explicit `harborlens-fetch-erddap` tool can attempt bounded 2024 downloads; source usage rights remain marked `review_required`. See [NOAA ERDDAP adapter](noaa-erddap.md). A real PMEL test returned sparse records (one observation per MMSI in tested windows); see the ERDDAP guide. Event truth was not validated.

## High-frequency historical tracks (to be validated)

The [official NOAA daily Zstandard index for 2024](https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/index.html) exposes nationwide daily archives. Use the [bounded archive extractor](noaa-archive-extraction.md) to select a Houston time window, preserving source hashes and rights status. The PMEL ERDDAP subset was operational in November 2026 but preliminary runs returned at most one observation per MMSI in tested time ranges, so its results are not sufficient to support dwell-time inference. One original NOAA daily file was processed successfully for a six-hour Houston subset, but continuity across days, coverage completeness and operational event truth remain unvalidated. See [integration evidence](noaa-real-data-smoke-2024-01-02.md).

## Source-pinned consecutive-day verification

Two authentic NOAA 2024 daily archives were processed in an isolated runner; see [the two-day integration report](noaa-consecutive-days-smoke-2024-01-02-03.md). 564 inferred candidate episodes crossed UTC midnight, but no anchorage/berth/waiting status has been independently verified. Source rights remain review_required; no raw data are committed to Git.
