# NOAA PMEL ERDDAP historical AIS subset adapter

**State:** experimental, opt-in, mock-tested. No verified real NOAA observations have yet been processed.

The official [PMEL AIS2024_AIS metadata](https://data.pmel.noaa.gov/pmel/erddap/info/AIS2024_AIS/index.html) lists AIS variables, time coverage for 2024, and the CC0-1.0 dedication for that dataset. Its [tabledap documentation](https://data.pmel.noaa.gov/pmel/erddap/tabledap/documentation.html) defines geographic/time constraints and explains that the CSV format includes a units row.

Use on a workstation with authorized Internet access:

~~~bash
harborlens-fetch-erddap --start 2024-06-10T00:00:00Z --end 2024-06-10T01:00:00Z --bbox -95.7 29.1 -94.2 30.1 --out data/houston.csv --max-mib 8
harborlens --input data/houston.csv --out results/houston --source-url https://data.pmel.noaa.gov/pmel/erddap/tabledap/AIS2024_AIS.html
harborlens-verify --manifest results/houston/manifest.json
~~~

The client uses a fixed NOAA host, validates that a single query covers no more than six hours in 2024, enforces a byte cap, and writes a sidecar file named houston.csv.source.json with exact request URL, source and normalized hashes, requested bounds, row count and rights_status=review_required. The sidecar is **not** proof of data accuracy, legal approval, or a government endorsement.

The download is explicitly invoked: installation, standard tests and the AIS pipeline do not make network calls. The project does not include any redistributed real AIS observations.

A failed/no-result ERDDAP request is not proof that Houston had no vessels. If ERDDAP is inaccessible, use an official, authorized NOAA archived daily CSV with documented source, date, SHA-256 and rights instead; do not fabricate or silently substitute observations.

**Issue #3 remains open** until the first real sample is successfully acquired, processed, quality-checked and independently reproduced. The existing stationary inference is provisional and cannot distinguish berths from anchorage waiting.
