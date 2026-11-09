# HarborLens USA

**Pre-alpha research code. Synthetic regression tests and a historical NOAA ingestion smoke. NOT FOR NAVIGATION.**

HarborLens explores auditable AIS ingest and provisional low-speed stationary candidates in the Houston–Galveston area. A candidate is **not** a verified berth, anchorage, queue, port call, or emissions claim.

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
harborlens --input tests/fixtures/synthetic_ais.csv --out results
```

[Specification-driven process](docs/engineering/spec-driven-development.md) · [Requirements](docs/requirements/functional.md) · [Open-source versus paid scope](docs/product/open-core.md). No real-world AIS accuracy or commercial product is claimed.

Sources: [NOAA AIS](https://marinecadastre.gov/ais/), [USACE](https://www.iwr.usace.army.mil/About/Technical-Centers/WCSC-Waterborne-Commerce-Statistics-Center/), [BTS](https://www.bts.gov/ports), [EPA emissions guidance](https://www.epa.gov/state-and-local-transportation/port-emissions-inventory-guidance).

## Optional small NOAA AIS2024 subset

A bounded, explicit NOAA PMEL ERDDAP client is documented in [NOAA subset acquisition](docs/data/noaa-erddap.md). It is intended to avoid unnecessary national-sized downloads; its limited real-server responses were verified in November 2026, but were too sparse to infer continuous trajectories. Never commit authentic AIS observations or call the provisional stationary candidates verified port calls.

## Reproducible daily NOAA extraction

For temporal trajectories use authorized daily historical compressed archives rather than assuming a PMEL ERDDAP query yields multiple points per MMSI. The opt-in [daily archive extractor](docs/data/noaa-archive-extraction.md) streams a source archive and writes only a bounded geographic/time subset with source hashes. A one-day national archive has now been processed successfully in an isolated research workflow; the detected candidate events are **not** externally validated. See [real-data integration results](docs/data/noaa-real-data-smoke-2024-01-02.md).

## Experimental multi-day AIS candidates

A separate local tool can reconstruct provisional low-speed candidate segments across UTC midnight from two or more existing historic AIS subsets, using an ephemeral SQLite sort and per-file input lineage. No automatic downloads. See [multi-day engineering guide](docs/data/multiday.md). No real multi-day accuracy or official berth/waiting claims are established.

## First real consecutive-day engineering run

An isolated GitHub Actions run successfully processed two authentic NOAA daily archives around UTC midnight. The tool reported 564 unvalidated cross-midnight candidate episodes among 286,696 cleaned points, with roughly 46 MiB process RSS and a 5.4-second multi-day stage. These are software results, not independently confirmed waiting vessels. See [the source-pinned engineering report](docs/data/noaa-consecutive-days-smoke-2024-01-02-03.md).
