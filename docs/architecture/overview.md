# Architecture — Current and Target

**Current (implemented / synthetic):** an offline Python CLI with canonical CSV normalization, provisional stationary segmentation, CSV/GeoJSON event export and SHA-256 input provenance. No private data, SaaS, live feed, UI or HTTP endpoint.

```mermaid
flowchart LR
  NOAA[NOAA-style historical CSV] --> QA[Normalize and quality-check]
  QA --> C[Cleaned AIS observations]
  C --> E[Stationary candidate inference]
  E --> CSV[CSV + GeoJSON candidates]
  QA --> M[SHA-256 + quality manifest]
  E --> M
  USACE[USACE dated facilities] -. later .-> G[Verified geofence registry]
  G -. later .-> E2[Validatable berth/anchorage classifier]
  BTS[BTS aggregates] -. comparison only .-> V[External validation reports]
  E2 -. later .-> V
  EPA[EPA factors] -. later .-> S[Emission scenario model]
```

**Future open core:** source snapshot ledger, multi-day streaming partition, dated USACE geometries, uncertainty-aware classifier, independent evaluation, reference read-only API and historical map.

**Optional managed commercial layer:** scheduled and licensed feeds, customer-private TOS/PCS integrations, tenant-aware access, reports, uptime, billing and support. Must be separately approved after buyer and real-data gates.

Principles: UTC, EPSG:4326 lon/lat, explicitly versioned rules, `unknown` as a first-class state, external data licenses tracked per source. See ADRs.
