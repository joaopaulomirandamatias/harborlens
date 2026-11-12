# HarborLens USA

**Pre-alpha research code. Synthetic regression tests and a historical NOAA ingestion smoke. NOT FOR NAVIGATION.**

HarborLens explores auditable AIS ingest and provisional low-speed stationary candidates in the Houston–Galveston area. A candidate is **not** a verified berth, anchorage, queue, port call, or emissions claim.

## Status at a glance

| Area | State | Evidence |
| --- | --- | --- |
| Ingestion and provenance (SPEC-001) | Implemented | Synthetic tests; source-pinned NOAA 2024 smokes; 2015–2023 and 2025+ layouts documentary only |
| Stationary candidates (SPEC-002) | Implemented, unvalidated | One shared engine (`stationary-v0.2`), censoring flags, synthetic 7-day scale benchmark; real two-day smoke |
| Validation tooling (SPEC-003) | Partial | Labeling protocol, blinded sampler, agreement and evaluation CLIs; **no labels collected, no accuracy measured** |
| Zones and regulatory sources (SPEC-004) | Partial | USACE points, current NOAA polygons, CFR/Federal Register audits; no reviewed dated polygons |
| Emissions, API/map, managed service (SPEC-005–007) | Proposed | Not built |

Status per requirement: [functional requirements](docs/requirements/functional.md) and [traceability](docs/requirements/traceability.md).

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
harborlens --input tests/fixtures/synthetic_ais.csv --out results
```

The offline source-rights helper is `python -m harborlens.rights`. Schema checks need the optional extra, not a core dependency:

```bash
python -m pip install -e '.[rights]'
```

Without `jsonschema`, the helper exits 2 and does not grant a decision. No checked-in source is approved. See [the rights register](docs/data/rights-register.md).

## Aggregate release gate (SPEC-003)

`harborlens-release-summary` stages a coarse allowlisted count summary only after the current purpose-specific rights decision and a signed human review of that exact summary. `harborlens-verify-release` re-checks the staged file without reading AIS. Neither command approves a source. A stationary candidate in the underlying run is not a berth, anchorage, wait, port call, or accuracy claim. The checked-in rights register keeps every source at `review_required`, so this gate denies a real release.

`reviewed_at_utc` must be an RFC3339 UTC date-time. It is accepted only when it is not older than 30 days and not more than 5 minutes ahead of the checker clock. Those 5 minutes are a fixed clock-skew allowance, not a configuration knob. A date-only value is rejected.

The contracts are [public-summary](schemas/v1/public-summary.schema.json), [publication-review](schemas/v1/publication-review.schema.json), and [release-verification-result](schemas/v1/release-verification-result.schema.json). The same bytes ship in the wheel and sdist under `harborlens/schemas/v1/` and load with `importlib.resources` (`read_packaged_release_schema`). See [the publication gate](docs/data/aggregate-publication-gate.md) and [schemas/README.md](schemas/README.md).

[Specification-driven process](docs/engineering/spec-driven-development.md) · [Requirements](docs/requirements/functional.md) · [Open-source versus paid scope](docs/product/open-core.md). No real-world AIS accuracy or commercial product is claimed.

Sources: [NOAA AIS](https://marinecadastre.gov/ais/), [USACE](https://www.iwr.usace.army.mil/About/Technical-Centers/WCSC-Waterborne-Commerce-Statistics-Center/), [BTS](https://www.bts.gov/ports), [EPA emissions guidance](https://www.epa.gov/state-and-local-transportation/port-emissions-inventory-guidance).

## Optional small NOAA AIS2024 subset

A bounded, explicit NOAA PMEL ERDDAP client is documented in [NOAA subset acquisition](docs/data/noaa-erddap.md). It is intended to avoid unnecessary national-sized downloads; its limited real-server responses were verified in November 2026, but were too sparse to infer continuous trajectories. Never commit authentic AIS observations or call the provisional stationary candidates verified port calls.

## Reproducible daily NOAA extraction

For temporal trajectories use authorized daily historical compressed archives rather than assuming a PMEL ERDDAP query yields multiple points per MMSI. The opt-in [daily archive extractor](docs/data/noaa-archive-extraction.md) streams a source archive and writes only a bounded geographic/time subset with source hashes. A one-day national archive has now been processed successfully in an isolated research workflow; the detected candidate events are **not** externally validated. See [real-data integration results](docs/data/noaa-real-data-smoke-2024-01-02.md).

## Experimental multi-day AIS candidates

A separate local tool can reconstruct provisional low-speed candidate segments across UTC midnight from two to sixteen existing historic AIS subsets, using an ephemeral SQLite sort and per-file input lineage. The SQLite cache and soft heap limit are fixed. No automatic downloads. See [multi-day engineering guide](docs/data/multiday.md). No real multi-day accuracy or official berth/waiting claims are established.

## First real consecutive-day engineering run

An isolated GitHub Actions run successfully processed two authentic NOAA daily archives around UTC midnight. The tool reported 564 unvalidated cross-midnight candidate episodes among 286,696 cleaned points, with roughly 46 MiB process RSS and a 5.4-second multi-day stage. These are software results, not independently confirmed waiting vessels. See [the source-pinned engineering report](docs/data/noaa-consecutive-days-smoke-2024-01-02-03.md).

A 2026-11-09 re-run on the `stationary-v0.2` engine reproduced those counts, measured analysis-window censoring for the first time (76.5% of candidates in a six-hour window have lower-bound durations, 7.1% over seven days) and processed seven full Houston days: 3.95 million points, 15,937 unvalidated candidates, 741 MiB scratch and under 50 MiB RSS. See [the re-run report](docs/data/noaa-real-data-rerun-2026-11-09.md).

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

### Verified Federal Register Part 110 historical index scan

An official-source index query for 2023-07-01 through 2024-01-02 returned four Proposed Rule metadata entries, not a proven effective change to section 110.197. The complete source query page and result JSON were SHA-256 fingerprinted. The [real source scan report](docs/data/fr-part110-real-index-2023-2024.md) retains mandatory official FR/LSA review and historical datum/geometry gates.

## Official Part 110 publication full-text triage

After the Part 110 index screen, the optional [official full-text source audit](docs/data/fr-2023-fulltext-triage.md) verifies original FederalRegister.gov metadata and raw published documents for four 2023 proposals/withdrawals, retaining source SHA-256 and explicit human-review requirements. No legal-effect or historical GIS approval is inferred.

### Verified original 2023 Federal Register full texts

A controlled official-source inspection obtained and checksummed all four original Federal Register 2023 Part 110 full texts. None of the four contained a direct 110.197 text match or Houston/Galveston/Bolivar reference; the Hudson entry included a withdrawal text signal. This **does not** certify historical January 2024 legal effect or an unchanged CFR. See the [source-pinned evidence report](docs/data/fr-2023-original-fulltext-evidence-2026-11-09.md).
