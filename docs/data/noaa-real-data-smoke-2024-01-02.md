# First real NOAA daily AIS ingestion — Houston, 2024-01-02

**Evidence date:** 2026-11-09 UTC. **Status:** real historical data were acquired and processed; no validated port-call, waiting-time, emissions or commercial conclusion is claimed.

## Reproducible sources and execution

- **Source:** [NOAA Marine Cadastre 2024 daily Zstandard index](https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/index.html), archive `ais-2024-01-02.csv.zst`.
- **Exact archive URL:** https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/ais-2024-01-02.csv.zst
- **Geographic filter:** lon -95.70 to -94.20; lat 29.10 to 30.10 (WGS84 research rectangle, not official port limits).
- **Time filter:** 2024-01-02, 00:00–06:00 UTC.
- **GitHub Actions successful run:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42572913769
- **Archive SHA-256:** `43bf674d62fddb69251f891fa2e3d92bcc98b3e764298130a5827b3be62d382d`
- **Selected CSV SHA-256:** `7d799ae8511a7e427cc6a6e2094834762558ad7963e391c4315c50fb0df5b1bd`
- **Run ID:** `9ca87026e937372d41b0bea683fa0334e0f5b77d350e68497ecdf132cd3619bd`
- **Source rights:** `review_required`, not automatically approved by successful download.
- **Data sharing:** neither the national archive nor individual observations were committed or uploaded as CI artifacts.

## Aggregate engineering results

| Metric | Observed value |
| --- | ---: |
| Nationwide AIS rows scanned | 7,292,731 |
| Records selected by region and time | 138,758 |
| Extracted CSV size (bytes) | 14,505,386 |
| Downstream invalid records | 20 |
| Downstream exact duplicates | 1 |
| Normalized accepted points | 138,737 |
| Distinct MMSIs | 740 |
| MMSIs with two or more observations in the raw selected subset | 737 |
| Maximum number of observations for one MMSI | 343 |
| Low-speed stationary *candidate segments* | 920 |
| SHA-256 export verification | PASSED |

The 920 candidates can include multiple segments belonging to the same MMSI. They are not a count of waiting vessels or confirmed berth occupancy. The current algorithm has **no independently assessed precision, recall, duration error or causality**.

## Why the daily archive was necessary

Two earlier NOAA PMEL ERDDAP 2024 samples were successfully fetched and ingested:

- One-hour Houston subset: 26 observations, 26 distinct MMSIs, zero with repeated positions.
- Six-hour Houston subset: 195 observations, 195 distinct MMSIs, zero with repeated positions.

That specific ERDDAP query representation was too sparse for within-vessel temporal inference. This does not imply NOAA itself lacks coverage. The original daily archive provided repeated AIS observations for 737 of 740 MMSIs in the selected six hours.

## Next engineering validation gates

1. Validate source file format, terms of use and allowed distribution for each actual NOAA archive vintage.
2. Process **consecutive daily archives** and verify no artificial event breaks at midnight (issue #5).
3. Audit missing intervals, MMSI reuse, time ordering, duplicate behavior and quantiles of AIS sampling rate.
4. Compare aggregates and coverage by vessel class and geography; do not treat this as a statistically representative week.
5. Introduce authoritative dated facility/anchorage geofences (issue #7), then separately labeled positive/negative reference events (issues #8/#9).
6. Keep `stationary_candidate` and `confidence_label=unvalidated` until independent event truth is available.

## Operations policy

The workflow `.github/workflows/noaa-daily-integration.yml` is **manual-only** once merged into the default branch. It performs a substantial national archive download, a full daily scan and ephemeral local processing. It publishes aggregate QA to job logs/summary without uploading raw records. Run it deliberately to limit GitHub Actions usage and network/storage costs.

## Censoring caveat (added with BR-019)

This run predates the analysis-window censoring flags. Candidates that touch the edges of the extracted window have durations that are only lower bounds, and their number was not measured here. Re-running the manual workflow records `left_censoring`/`right_censoring` and run-level counts from the extraction sidecar.

**NOT FOR NAVIGATION; NOT AN OFFICIAL PORT PERFORMANCE OR EMISSIONS INVENTORY.**
