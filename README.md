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

## Official facility point references (SPEC-004)

The optional [USACE Navigation Facilities point catalog](docs/data/usace-geography.md) provides a bounded, source-pinned Houston facility reference dataset. **These are points, not dated berth or anchorage polygons.** They are not sufficient to verify stationary candidates as waiting, berthing or port calls.
