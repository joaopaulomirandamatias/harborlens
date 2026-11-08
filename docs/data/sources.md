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
