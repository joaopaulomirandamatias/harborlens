# NOAA daily AIS archive extraction — SPEC-001

**Status:** experimental open-source functionality with synthetic regression tests and one successful real NOAA daily archive ingestion smoke. Event classification remains unvalidated. See [integration evidence](noaa-real-data-smoke-2024-01-02.md).

NOAA Marine Cadastre publishes [historical daily Zstandard AIS archives](https://noaaocm.blob.core.windows.net/ais/csv2/csv2024/index.html). For example, the index lists a nationwide compressed archive for 2024-01-02, roughly 189 MiB. Because it contains all US waters, the original archive is not appropriate to commit to Git or to use directly in port-specific benchmarks.

## Opt-in example (requires network and disk capacity)

~~~bash
python -m pip install -e '.[noaa]'
harborlens-download-noaa --date 2024-01-02 --directory data --max-mib 300
harborlens-extract-noaa-archive --input data/ais-2024-01-02.csv.zst --out data/houston-2024-01-02.csv --start 2024-01-02T00:00:00Z --end 2024-01-02T06:00:00Z --bbox -95.7 29.1 -94.2 30.1 --max-rows 250000 --max-output-mib 64
harborlens --input data/houston-2024-01-02.csv --out results/houston-2024-01-02
harborlens-verify --manifest results/houston-2024-01-02/manifest.json
~~~

The extractor scans the **complete daily file** and fails rather than silently truncating if the row or output size cap is reached. Compressed source size is limited to 512 MiB and decompression to 8 GiB. The output includes a sidecar with source and selected CSV hashes, bbox/time selection and QA counters. No raw authentic AIS data will be committed, uploaded as CI artifacts or embedded in job logs.

The bbox is a Houston research rectangle, not an official port/anchorage geometry. A single day is insufficient to characterize annual waiting patterns, and a stationary candidate is not equivalent to berth occupancy, queueing or validated port calls.

**Caveats:** Source authorization must be confirmed for the actual file; the local path and official-looking filename do not prove that the bytes came from NOAA. The daily archive contains large volumes of records and may require temporary storage and run time. Real data execution remains gated on an isolated integration workflow, without giving public users automatic download access.

## Full UTC days (#35)

One full day in the Houston research rectangle is about 560,000 rows (~59 MiB). The extractor's ceilings are 1,000,000 matched rows and 256 MiB of output (defaults 1,000,000 and 128 MiB); both still fail closed. The sidecar records the `limits` used.

~~~bash
harborlens-extract-noaa-archive --input data/ais-2024-01-02.csv.zst --out data/houston-2024-01-02.csv \
  --start 2024-01-02T00:00:00Z --end 2024-01-02T23:59:59Z --bbox -95.7 29.1 -94.2 30.1 \
  --max-rows 1000000 --max-output-mib 256
~~~

The manual workflow `.github/workflows/noaa-week-integration.yml` downloads, extracts and deletes one archive at a time for 2–7 consecutive full days, then runs `harborlens-multiday` and publishes aggregate metrics only.

## Archive vintages (#36)

`harborlens.vintages` maps each year to one layout; years outside it are refused rather than guessed.

| Years | Layout | Download | Header | Missing values | How the layout was established |
| --- | --- | --- | --- | --- | --- |
| 2015–2023 | `marinecadastre_zip_daily_v1` | `coast.noaa.gov/htdata/CMSP/AISDataHandler/{year}/AIS_{year}_{MM}_{DD}.zip` | `MMSI,BaseDateTime,LAT,LON,…,TransceiverClass` | sentinels (COG 360, heading 511, 0 dimensions) | pattern documented for 2022 files and the 2023 index; not yet downloaded by this project |
| 2024–2026 | `marinecadastre_csv2_zst_v1` | `noaaocm.blob.core.windows.net/ais/csv2/csv{year}/ais-{date}.csv.zst` | lowercase (`mmsi,base_date_time,longitude,latitude,…,transceiver`) | nulls | 2024 downloaded and hashed in source-pinned runs; 2025–2026 follow the published index, not yet downloaded |

`harborlens-extract-noaa-archive` accepts both `.zip` (single CSV member, bounded by the `io_safe` ZIP checks) and `.csv.zst`, checks that the compression matches the year's layout, and records `source_vintage` (layout, detected header style, missing-value convention, verification note) in the sidecar. Column lookup is by name, so the 2025 longitude/latitude order swap does not matter. Rows with an empty required field are counted as `missing_value`, separately from malformed `invalid` rows, both in extraction and in ingestion. Before relying on a newly enabled year, run one manual integration smoke and record its header and counts.
