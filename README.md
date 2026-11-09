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

## Official USACE facility reference points (SPEC-004)

The opt-in [USACE Navigation Facilities point catalog](docs/data/usace-geography.md) retrieves bounded public reference **points**, not dated berthing or anchorage polygons. A proximity or point overlay cannot establish berth, anchorage waiting or verified port calls.

### First real official USACE facility reference-point sample

A bounded USACE-associated FeatureServer query produced 723 POINT records in the Houston research rectangle, including 536 with type Dock. These are reference points, not historical berth polygons or verified AIS events. See [real engineering report](docs/data/usace-points-smoke-2026-11-09.md).

## NOAA designated anchorage polygons

The opt-in [NOAA polygon source and conservative AIS centroid overlay](docs/data/noaa-anchorages.md) provide reference-only spatial context. Historical validity and confirmed berth/anchorage/waiting status are NOT established.

### Verified NOAA anchorage polygon API integration (current reference only)

An isolated engineering smoke retrieved 6 current NOAA Anchorage Area polygons and compared their geometries to 920 historical provisional AIS candidate centroids: 77 possible single overlaps and 843 no overlaps. No historical or operational validity is established. See [combined integration report](docs/data/noaa-anchorage-real-smoke-2026-11-09.md).

## Full observed-track geospatial evidence (SPEC-004)

A new local [full-track polygon evidence tool](docs/data/full-track-zone-evidence.md) checks each historical candidate against all cleaned AIS points in its time window, rather than its centroid alone. The source must have an integrity-matched polygon receipt. Every result remains unvalidated and historically unverified.

### First authentic full observed-track comparison

A bounded official NOAA 2024 AIS vs current NOAA anchorage Polygon smoke processed 920 unvalidated candidate episodes. Of these, 74 had every **observed** AIS point within a single Polygon, 5 had partial point coverage and 841 had no recorded-point overlap. The previous centroid-only baseline had 77 overlaps. Neither method confirms anchorage, waiting or the polygon's 2024 historical authority. See [full-track source-pinned engineering report](docs/data/noaa-full-track-context-smoke-2026-11-09.md).

## Historical NOAA ENC geometry vintage audit

The [offline NOAA geometry-vintage audit](docs/data/geometry-vintage-audit.md) checks source hashes and flags ENC edition/issue date contradictions. It explicitly does not confirm that the current anchorage polygons matched 2024 or that any vessel was waiting or anchored.

### Official NOAA vintage-audit smoke (historically unverified)

An isolated live NOAA current polygon query and offline date audit passed, but no archival 2024 ENC documentation was supplied. The output correctly retains geometry validity=not_verified and rights=review_required. See [source-pinned integration report](docs/data/noaa-geometry-vintage-smoke-2026-11-09.md).

## Government-dated 2024 USCG regulatory anchorages (source transcription audit)

The [2024 Federal CFR §110.197 legal-coordinate source audit](docs/data/cfr-2024-galveston-anchorage-audit.md) transcribes the four Galveston/Bolivar Roads anchorage areas and performs conservative datum/topology checks. **It never emits automatically usable WGS84 GIS polygons**, because A/B/C lack an explicit NAD83 datum and A East has an invalid literal vertex sequence. The 2024 edition dates to July 1; January 2 historical applicability requires separate verification. No AIS operational-event classification.

### Two official annual CFR editions compared

The legal-coordinate registry was checked directly against official Government Publishing Office 2023 and 2024 annual Title 33 source HTML. All 16 DMS coordinate pairs were present in both. A/B/C datum and A East topology blockers remain unresolved, as does exact January 2, 2024 legal applicability. See the [2023/2024 source verification report](docs/data/cfr-2023-2024-source-verification.md).

## Federal Register timeline source-index screen

The opt-in [Part 110 historical Federal Register index screen](docs/data/fr-part110-timeline.md) discovers publications between annual CFR editions and records URLs, hashes and manual-review requirements. This is a documentary triage tool, **not** proof that a CFR section remained unchanged on any historical date, and it authorizes no AIS geospatial joins.
