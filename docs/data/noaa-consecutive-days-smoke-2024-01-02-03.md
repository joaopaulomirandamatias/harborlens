# Consecutive NOAA Daily AIS Archives — Houston Multi-Day Integration

**Evidence date:** 2026-11-09 UTC.  
**Successful run:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42575153803  
**Scope:** reproducible engineering ingestion and resource benchmark, NOT verified waiting times, port calls or emissions.

## Source and geographic scope

Two original nationwide NOAA Marine Cadastre AIS archives were downloaded inside an ephemeral GitHub Actions job, with research area west -95.70, south 29.10, east -94.20, north 30.10 (WGS84).

| Original NOAA archive | UTC selection | Original archive SHA-256 | Houston subset SHA-256 | Rows selected |
| --- | --- | --- | --- | ---: |
| [2024-01-02](https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-01-02.csv.zst) | 18:00–23:59:59 | 43bf674d62fddb69251f891fa2e3d92bcc98b3e764298130a5827b3be62d382d | 6e14223ab43e424be2c7a5d90e19114887b880dcf40e5812eb5ba7e362cef17d | 145,918 |
| [2024-01-03](https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-01-03.csv.zst) | 00:00–05:59:59 | 875bc3159ef4f4b5d62e65de8f319ef72dcb47384d8e04b95145a17cd3ad742a | 9dc4e9e669eeab9ed9c34ecf6d687408efc1baf74278b51f71e1d426eaadc0ee | 140,808 |

No real AIS individual observations, national archives or selected CSV files were committed to Git or uploaded as GitHub artifacts. Source redistribution and downstream commercial usage rights remain **review_required**.

## Engineering metrics

| Quantity | Result |
| --- | ---: |
| Selected records across two days | 286,726 |
| Normalized accepted points | 286,696 |
| Distinct MMSIs | 797 |
| Unvalidated stationary candidate segments | 1,569 |
| Unvalidated candidates spanning UTC midnight | 564 |
| Gap-triggered splits | 616 |
| Cross-file exact duplicate observations | 0 |
| Reported identity/type conflict splits | 0 |
| Same-timestamp conflict splits | 0 |
| Implausible jump splits | 0 |
| Local run SHA-256 ID | 36c9edb52378e3e6ca13dba537c758fc24dff14b48d48904ccf77f9b22ab6bbe |
| Multi-day processing elapsed time | 5.4 seconds |
| Peak resident memory of multi-day process | 47,096 KiB (approximately 46 MiB) |
| Three output checksum verifications | PASS |

The 30-point difference between input and accepted observations represents filtering/deduplication combined; this published aggregate summary does not provide the exact rejection-category breakdown. The SQLite scratch-disk peak was not independently measured. Memory and elapsed time are for the multi-day function alone, excluding downloads, original nationwide decompression/extraction, workflow setup and independent hash checks.

**564 does not mean 564 different vessels waiting.** These are inferred low-speed candidate episodes crossing midnight, with no independent label verification or port-zone classification. An MMSI may have multiple candidates, and each MMSI may be unreliable as a permanent vessel identity.

## Reproducibility and method

The historical two-file processing used the source fingerprints above, the temporary SQLite sorting and deduplication pipeline in HarborLens, and stationary-multiday-v0.1 method thresholds (speed <=0.5 knots; >=8 points; >=30 minutes; <=15-minute gaps; <=1,000-meter radial spread). Each output records the contributing file references and unvalidated status. All three output files passed local SHA-256 integrity verification.

## What this proves, and what remains

**Established:** authorized access to historical archived NOAA files in the isolated test; genuine two-day geographic extraction; handling of observations across the UTC date boundary; successful checksums; measurable bounded process memory on this one experiment.

**Not established:** AIS completeness or error statistics across seasons, accuracy of berth/anchor/wait labels, external ground truth, official geofence validity, economic savings, emissions, or permissions to redistribute source datasets commercially.

## Next gates

1. Complete NOAA source-specific data-use review and archive coverage assessment.
2. Measure actual scratch-disk consumption, repeat across multiple periods, and characterize AIS sampling gaps and possible identity changes.
3. Bring in dated authoritative port zones from USACE/NOAA rather than inferring berth polygons from facility points.
4. Create independently reviewed positive/negative event reference labels and report classification precision/recall and time errors.
5. Keep the nationwide archive workflow **manual-only** to avoid uncontrolled data transfer or GitHub Actions consumption.

## Censoring caveat (added with BR-019)

This run predates the analysis-window censoring flags. Candidates that touch the edges of the extracted window have durations that are only lower bounds, and their number was not measured here. Re-running the manual workflow records `left_censoring`/`right_censoring` and run-level counts from the extraction sidecar.

**NOT FOR NAVIGATION. NOT AN OFFICIAL PORT PERFORMANCE OR ENVIRONMENTAL INVENTORY.**
