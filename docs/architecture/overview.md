# Architecture — Current and Target

**Current (implemented; real-data use limited to source-pinned engineering smokes):** offline Python CLIs, no SaaS, live feed, UI or HTTP endpoint.

```mermaid
flowchart LR
  NOAA[NOAA daily archives<br/>2015-2023 ZIP / 2024+ zstd] --> X[Bounded extraction<br/>+ hashed sidecar with window and vintage]
  X --> QA[Normalize, QA, MMSI category flags]
  QA --> C[Cleaned AIS]
  C --> E[Shared segmentation engine<br/>stationary-v0.2]
  E --> K[Unvalidated candidates<br/>+ censoring + parameter_set]
  QA --> M[Manifest: hashes, limits,<br/>code_version, run_id]
  K --> M
  K --> Z[Spatial context: centroid / full track<br/>vs NOAA polygons]
  USACE[USACE facility points] --> Z
  CFR[33 CFR 110.197 + Federal Register audits] -. reviewed WGS84 polygons pending .-> Z
  K --> L[Blinded stratified labeling sample]
  L --> A[Annotator agreement]
  L --> V[Evaluation vs adjudicated labels]
  K --> T[Threshold sensitivity, descriptive]
  EPA[EPA factors] -. later .-> S[Emission scenario model]
```

Every candidate stays `stationary_candidate` with `confidence_label=unvalidated`; spatial context, censoring flags and evaluation tooling never turn it into a verified berth, anchorage, wait or port call. Real labels have not been collected yet.

**Future open core:** source snapshot ledger, multi-day streaming partition, dated USACE geometries, uncertainty-aware classifier, independent evaluation, reference read-only API and historical map.

**Optional managed commercial layer:** scheduled and licensed feeds, customer-private TOS/PCS integrations, tenant-aware access, reports, uptime, billing and support. Must be separately approved after buyer and real-data gates.

Principles: UTC, EPSG:4326 lon/lat, explicitly versioned rules, `unknown` as a first-class state, external data licenses tracked per source. See ADRs.
