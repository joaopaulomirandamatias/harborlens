# HarborLens USA

**Pre-alpha research code. Synthetic regression tests and a historical NOAA ingestion smoke. NOT FOR NAVIGATION.**

HarborLens explores auditable AIS ingest and provisional low-speed stationary candidates in the Houston–Galveston area. A candidate is **not** a verified berth, anchorage, queue, port call, or emissions claim.

## Status at a glance

| Area | State | Evidence |
| --- | --- | --- |
| Ingestion and provenance (SPEC-001) | Implemented | Synthetic tests; source-pinned NOAA 2024 smokes; 2015–2023 and 2025+ layouts documentary only |
| Stationary candidates (SPEC-002) | Implemented, unvalidated | One shared engine (`stationary-v0.2`), censoring flags, synthetic 7-day scale benchmark; real two-day smoke |
| Validation tooling (SPEC-003) | Partial | Labeling protocol, blinded sampler, agreement CLI, and a synthetic evaluation harness (`evaluation-v0.2`, `validation_status` `unvalidated`); **no labels collected, no accuracy claim** |
| Zones and regulatory sources (SPEC-004) | Partial | USACE points, current NOAA polygons, CFR/Federal Register audits; no reviewed dated polygons |
| Emissions, API/map, managed service (SPEC-005–007) | Proposed | Not built |

Status per requirement: [functional requirements](docs/requirements/functional.md) and [traceability](docs/requirements/traceability.md).

## Quick start

```bash
python -m pip install -e .
harborlens --input tests/fixtures/synthetic_ais.csv --out results
harborlens-verify --manifest results/manifest.json
```

This writes four files in `results/`:

- `houston_clean.csv` — cleaned AIS points. The filename is canonical (it stays `houston_clean.csv` even if you change `--bbox`).
- `stationary_candidates.csv` and `stationary_candidates.geojson` — unvalidated low-speed candidates. A candidate is **not** a berth, anchorage, wait, or port call.
- `manifest.json` — QA counts, method thresholds, SHA-256 of the artifacts, and `run_id`. The same document is printed to stdout.

On this synthetic fixture, `analysis_window.status` is `unknown` and the single candidate is `left_censoring` / `right_censoring` `unknown`, because no acquisition sidecar declared a window. That is expected. `mmsi_category` is `other` for the fixture's unassigned MID 199 identifiers.

`harborlens-verify` checks local bytes against the manifest. It does not prove source authenticity, data rights, or verified events.

Offline tests:

```bash
python -m unittest discover -s tests -v
```

Optional extras are documented with the commands that need them (for example `.[rights]` below). The default bounding box is Houston–Galveston (`-95.7 29.1 -94.2 30.1`). Threshold defaults and the full flag list are in `harborlens --help`.

## Command map

Twenty console scripts ship in the package. Two further tools are invoked as modules. There is no unified `harborlens <subcommand>` entry point and no map or HTTP API (SPEC-006 is proposed only).

### First run

| Command | Purpose |
| --- | --- |
| `harborlens` | Ingest a local AIS CSV and write unvalidated stationary candidates plus a manifest |
| `harborlens-verify` | Verify SHA-256 and sizes of that run's artifacts against `manifest.json` |

### Multi-day reconstruction and sensitivity

| Command | Purpose |
| --- | --- |
| `harborlens-multiday` | Rebuild provisional candidates across UTC midnight from 2–16 local AIS subsets |
| `harborlens-sensitivity` | Descriptive threshold sensitivity on a cleaned run; not an accuracy claim |

### Opt-in data acquisition

| Command | Purpose |
| --- | --- |
| `harborlens-download-noaa` | Experimental download of one official NOAA daily AIS archive, with a size cap |
| `harborlens-fetch-erddap` | Bounded historical NOAA PMEL AIS2024 subset (often too sparse for tracks) |
| `harborlens-extract-noaa-archive` | Extract a Houston geographic/time subset from a local daily NOAA archive |

### Zones and regulatory context (SPEC-004)

| Command | Purpose |
| --- | --- |
| `harborlens-fetch-usace` | Bounded USACE Navigation Facilities **points** — not berth polygons |
| `harborlens-fetch-noaa-anchorages` | Current NOAA anchorage polygons for research context only |
| `harborlens-zone-context` | Unverified centroid-in-polygon context for candidates |
| `harborlens-track-context` | Full observed-track versus polygon evidence; still unverified |
| `harborlens-geometry-vintage` | Offline NOAA geometry-vintage audit; no historical validity approval |
| `harborlens-cfr-anchorage-audit` | 2024 CFR §110.197 coordinate transcription audit; no GIS polygons for AIS joins |
| `harborlens-fr-timeline` | Federal Register 33 CFR Part 110 index screen; no legal-effect conclusion |
| `harborlens-fr-fulltext` | Official 2023 Part 110 full-text triage |
| `python -m harborlens.lsa_compare` | Compare official 2023-12 / 2024-01 Title 33 LSA source indexes (no console script) |

### Labeling and evaluation (SPEC-003)

| Command | Purpose |
| --- | --- |
| `harborlens-label-sample` | Blinded, stratified labeling sheet from one verified run |
| `harborlens-label-agreement` | Inter-annotator agreement for two completed sheets |
| `harborlens-evaluate` | Compare a verified run with adjudicated labels (`evaluation-v0.2`, always `unvalidated`; no accuracy claim) |

### Rights and aggregate release (SPEC-003)

| Command | Purpose |
| --- | --- |
| `python -m harborlens.rights` | Offline, fail-closed source-rights audit; not legal advice (no console script) |
| `harborlens-release-summary` | Rights-gated coarse count summary only after a signed human review |
| `harborlens-verify-release` | Re-check a staged aggregate release without reading AIS |

Run any command with `--help`. None of these tools is for navigation.

## Synthetic evaluation harness (SPEC-003)

`harborlens-evaluate` compares one verified run with an adjudicated label file. The report schema is `evaluation-v0.2`. `validation_status` is `unvalidated`. `--label-provenance` accepts `synthetic` or `unspecified`; with no flag the value is `unspecified`, and any other value exits 2 without writing a file. The `caveat` states that the labels are not independent ground truth and that the report makes no accuracy claim. When provenance is unspecified, the caveat says the label provenance is unspecified. The `warning` says that agreement with labels at any evidence level, including L3, is not validated performance while `validation_status` is `unvalidated`. `mixed`, `unknown`, and unlabeled units stay in `coverage.excluded`. An `evaluation-v0.1` report is not readable: `read_evaluation_report` raises `EvaluationReportError`, and no v0.1 reader is maintained. The test exercise uses synthetic vessel ids only and does not commit a label sheet. No real labels have been collected. A stationary candidate is not a berth, anchorage, wait, or port call.

`harborlens-label-sample` writes one CSV. Text cells whose first character, or first character after leading whitespace, is `=`, `+`, `-`, `@`, tab, or carriage return are prefixed with an apostrophe. Numeric, timestamp, and enum cells are validated and written unchanged, including a negative longitude such as `-95.1`. A failed check exits 2 and writes nothing. Readers remove that apostrophe only on text columns. The sampling key is JSON, not a CSV.

The offline source-rights helper is `python -m harborlens.rights`. Schema checks need the optional extra, not a core dependency:

```bash
python -m pip install -e '.[rights]'
```

Without `jsonschema`, the helper exits 2 and does not grant a decision. No checked-in source is approved. See [the rights register](docs/data/rights-register.md).

## Aggregate release gate (SPEC-003)

`harborlens-release-summary` stages a coarse allowlisted count summary only after the current purpose-specific rights decision and a signed human review of that exact summary. `harborlens-verify-release` re-checks the staged file without reading AIS. Neither command approves a source. A stationary candidate in the underlying run is not a berth, anchorage, wait, port call, or accuracy claim. The checked-in rights register keeps every source at `review_required`, so this gate denies a real release.

`reviewed_at_utc` must be ASCII `YYYY-MM-DDTHH:MM:SS` with no fraction or 1 to 6 fractional digits, then `Z`. `+00:00` is rejected. The parser builds that clock from the matched fields, so Python 3.10 and 3.12 agree. It is accepted only when it is not older than 30 days and not more than 5 minutes ahead of the checker clock. Those 5 minutes are a fixed clock-skew allowance, not a configuration knob. A date-only value is rejected.

The contracts are [public-summary](schemas/v1/public-summary.schema.json), [publication-review](schemas/v1/publication-review.schema.json), and [release-verification-result](schemas/v1/release-verification-result.schema.json). The same bytes ship in the wheel and sdist under `harborlens/schemas/v1/` and load with `importlib.resources` (`read_packaged_release_schema`). See [the publication gate](docs/data/aggregate-publication-gate.md) and [schemas/README.md](schemas/README.md).

## Documentation

- [Data dictionary](docs/data/dictionary.md) — field meanings for cleaned points, candidates, and the run manifest
- [Docs index](docs/README.md)
- [Verified integration evidence](docs/data/integration-evidence.md) — NOAA, USACE, CFR, and Federal Register smokes previously kept in this README (content preserved, not deleted)
- [NFR-001 disclaimer proposal](docs/ux/nfr-001-disclaimer.md) — proposed placement of the NOT FOR NAVIGATION / pre-alpha notice on run artifacts (proposal only; no code change in this slice)
- [Specification-driven process](docs/engineering/spec-driven-development.md) · [Requirements](docs/requirements/functional.md) · [Traceability](docs/requirements/traceability.md) · [Open-source versus paid scope](docs/product/open-core.md)

No real-world AIS accuracy or commercial product is claimed.

Sources: [NOAA AIS](https://marinecadastre.gov/ais/), [USACE](https://www.iwr.usace.army.mil/About/Technical-Centers/WCSC-Waterborne-Commerce-Statistics-Center/), [BTS](https://www.bts.gov/ports), [EPA emissions guidance](https://www.epa.gov/state-and-local-transportation/port-emissions-inventory-guidance).
