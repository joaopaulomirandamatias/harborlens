# SPEC-003: Source-rights receipts in NOAA and USACE adapters

**Status:** experimental, offline decision lookup only. This is not an authorization service or a legal opinion. The checked-in registry contains **zero approved sources**. No source data or private files are committed by this integration.

## Scope and contracts

Four existing acquisition functions now accept optional `rights_register` and `rights_purpose` arguments; their CLIs expose `--rights-register <local-file>` and `--rights-purpose research|public_aggregates|commercial`. Default behavior is backward compatible: no register is loaded, downloads remain explicitly opt-in, existing source sidecar keys stay intact, and the rights status remains `review_required`.

Each new sidecar contains an additional `rights_review` receipt, validated by [`schemas/v1/source-rights-receipt.schema.json`](../../schemas/v1/source-rights-receipt.schema.json). The ERDDAP sidecar also validates against [`schemas/v1/erddap-ais-source.schema.json`](../../schemas/v1/erddap-ais-source.schema.json), and the archive-extract sidecar against [`schemas/v1/noaa-archive-extract-source.schema.json`](../../schemas/v1/noaa-archive-extract-source.schema.json). Those two documents are research contracts. They are not packaged and the adapters do not load them at runtime. `rights_review` is optional in each schema. The receipt fields are:

- `schema_version` and fixed source ID
- `dataset_version` used for **exact** rights-record matching
- `purpose` (one of the three allowed uses)
- `registry_sha256` of **the same bounded local bytes** evaluated, or null if absent/invalid
- `evaluation`: `not_supplied`, `invalid_registry`, `pending_or_unmatched`, or `reviewed_record`
- `rights_status`: `review_required`, `reviewed_public_domain_attribution_required`, `reviewed_permitted_with_conditions`, or `use_restricted`

`reviewed_record` identifies a syntactically complete reviewer assertion that already passed `load_registry`. It is **not** external authentication or a grant of data rights; verification of the terms snapshot and named reviewer remains a separate human gate.

`rights_receipt` reads the register file once. That buffer is parsed and checked with the same validation as `load_registry`, and the SHA-256 and the decision both come from it. The path is not opened again. The schema is `src/harborlens/schemas/v1/source-rights-register.schema.json`, loaded with `importlib.resources` only; parent directories are not searched. A missing, unreadable, oversized, BOM-prefixed, or schema-invalid buffer yields `evaluation=invalid_registry` and `rights_status=review_required`. `jsonschema` is the `rights` extra; if it is missing, the receipt fails closed the same way.

| Adapter | Fixed source ID | Version identity |
| --- | --- | --- |
| `harborlens-fetch-erddap` | `noaa_pmel_erddap` | `AIS2024_AIS` (exact official dataset ID) |
| `harborlens-extract-noaa-archive` | `noaa_ocm_ais_daily` | `2024/archive-sha256:<local archive digest>` (prevents applying year-only decisions to an arbitrary local file) |
| `harborlens-fetch-usace` | `usace_ntad_navigation_facilities` | `output-sha256:<canonical exported POINT GeoJSON digest>` |
| `harborlens-fetch-noaa-anchorages` | `noaa_oceanreports_anchorages` | `output-sha256:<canonical exported polygon GeoJSON digest>` |

For a mutable geometry service, a catalog date or `current_unversioned` entry **cannot** match a newly fetched output. A reviewer would have to register the exact output fingerprint, as well as validating the upstream source/terms and limitations. An output hash records the result obtained; it is not itself evidence that the geometry was valid historically.

## How to use

```bash
harborlens-fetch-erddap \
  --start 2024-01-02T00:00:00Z --end 2024-01-02T01:00:00Z \
  --out data/houston.csv \
  --rights-register docs/data/rights-register.json --rights-purpose research

harborlens-fetch-usace \
  --out data/houston-facilities.geojson \
  --rights-register docs/data/rights-register.json --rights-purpose public_aggregates

harborlens-fetch-noaa-anchorages \
  --out data/houston-anchorages.geojson \
  --rights-register docs/data/rights-register.json --rights-purpose research

harborlens-extract-noaa-archive \
  --input data/ais-2024-01-02.csv.zst --out data/houston-2024-01-02.csv \
  --start 2024-01-02T00:00:00Z --end 2024-01-02T01:00:00Z \
  --rights-register docs/data/rights-register.json --rights-purpose research
```

These examples are **opt-in acquisitions**; they do not confirm access availability or license status. All statuses will be `review_required` with the checked-in register. The `rights_review` object is stored next to the preexisting provenance in `.source.json`, and the existing `license_status` key for USACE is preserved.

## Reproduction, regressions and remaining gates

1. Run `python -m unittest discover -s tests -v` using `pip install -e '.[noaa,dev,geo,rights]'`. The synthetic adapter suite verifies exact-source-version matches, restrictions, invalid or absent registers, sidecar JSON Schema compatibility, and unchanged historical-geometry disclaimers. It never contacts external sources.
2. Before interpreting anything beyond `review_required`, independently verify the source's identity, applicable version, official terms, redistribution scope, reviewer, attribution and legal conditions. A synthetic "reviewed" fixture proves only a branch in code.
3. Future release/publication workflows must separately enforce the approved purpose. **This adapter receipt is metadata, not a security boundary on exporting, publishing, or commercially using records.**
4. No assertion is made about historical 2024 berth geometry, vessel waiting, event ground truth, navigational safety or government endorsement.

**No silent change to acquisition semantics. No navigation use.**
