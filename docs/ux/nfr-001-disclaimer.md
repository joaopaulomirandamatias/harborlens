# Proposal: NFR-001 notices on run artifacts

**Status:** proposal only (no Python, schema, CI, or golden change in this branch). **Placement decision (21 November 2026, America/Belem):** the notice goes in `manifest.json` / stdout and in candidate GeoJSON. CSV tables stay untouched. Implementation still needs a later PR and a package-version bump, because writing the notice into `manifest.json` or GeoJSON changes `run_id` and hashes.

**Requirement:** NFR-001 (P0) — *All outputs MUST display NOT FOR NAVIGATION and pre-alpha status* (`docs/requirements/non-functional.md`).

**Observed gap (UX diagnosis v1, 21 November 2026, America/Belem):** a synthetic `harborlens` run writes `houston_clean.csv`, `stationary_candidates.csv`, `stationary_candidates.geojson`, and `manifest.json`. None of those files currently contains the phrases `NOT FOR NAVIGATION` or `pre-alpha`. The README and some CLI `description` strings do. `events.warning` and `provenance_warning` use different wording.

**Exact notice text** (English, one constant, to be reused everywhere this proposal is accepted):

```
NOT FOR NAVIGATION. Pre-alpha research output. A stationary candidate is not a berth, anchorage, wait, port call, or emissions claim.
```

Both required phrases appear in that sentence (`NOT FOR NAVIGATION` and `Pre-alpha`). Do not add accuracy, official-berth, or rights-grant language.

## Where the notice should go

The run directory is the unit of output. The notice should be machine-readable in the JSON documents that already describe the run, and discoverable next to the CSVs, without breaking CSV readers or formula hygiene.

### 1. `manifest.json` (required) — and stdout

The CLI prints the same object it writes to `manifest.json`. Add a single new required string property:

- **Name:** `safety_notice`
- **Type:** string
- **Const / exact value:** the notice text above
- **Schema:** `schemas/v1/run-manifest.schema.json` today has `"additionalProperties": false`, so the property must be added to `required` and `properties` in the same change. That is a contract change (`provenance_schema_version` or an equivalent documented bump, plus package version).

`events.warning` and `provenance_warning` may stay as they are (they carry more specific QA and integrity caveats). They do not replace `safety_notice`.

### 2. `stationary_candidates.geojson` (required)

The FeatureCollection already has a top-level `harborlens_method` object. Add a sibling top-level string:

- **Name:** `safety_notice`
- **Const / exact value:** the same notice text
- **Not** a per-feature property (that would repeat the string on every candidate and is easier to strip in a GIS export without noticing)

There is today a per-feature schema (`schemas/v1/stationary-candidate-feature.schema.json`) but not a dedicated FeatureCollection schema. The implementation slice should add or extend a collection-level contract so `safety_notice` and `harborlens_method` are required at the collection root. The same field should appear on multi-day candidate GeoJSON (`schemas/v1/multi-day-candidate-feature.schema.json` and its collection), so both CLIs stay consistent.

### 3. CSV files (`houston_clean.csv`, `stationary_candidates.csv`) — decided: do not modify the table

**Decision:** do not insert a `#` comment line, a preamble row, or a constant `safety_notice` column. The CSV body stays a plain table.

Reasons:

- `#` comment lines are not part of the current CSV readers (`csv.DictReader` / `CsvDictWriter` paths). A leading `#` would break ingestion of a cleaned file and every golden SHA-256 (`tests/fixtures/single_day_*`, formula goldens cited in `CHANGELOG.md`).
- A constant column on every row bloats files, invites spreadsheet confusion, and still would not appear in tools that show only a geometry layer.
- NFR-001 can be met for the **run** by the manifest (always written beside the CSVs, and listed as the verification entry point) plus the GeoJSON notice for GIS users, together with the documentation that `houston_clean.csv` is a canonical name in the same directory as `manifest.json`.

The data dictionary should state: *The NFR-001 safety notice for a CSV artifact is the `safety_notice` field of the sibling `manifest.json`. The CSV body has no preamble.*

### Alternatives (not adopted)

| Alternative | Effect | Why it was not adopted |
| --- | --- | --- |
| A. `#` first line in each CSV | Visible in a text editor and in some spreadsheets | Requires every reader to skip comments; changes all goldens; some tools treat `#` as data |
| B. Constant `safety_notice` column | Visible as a column | Noisy; every row repeats the same cell; still a golden/schema change |
| C. Extra `NOTICE.txt` (or `SAFETY.txt`) in the run directory, hashed in `manifest.artifacts` | Plain-text file with the exact notice, easy to open | Changes the artifact set that `harborlens-verify` expects (`FILES` in `src/harborlens/provenance.py`). Stronger literal reading of “all outputs”, but a larger compatibility break. Not adopted. |

These alternatives remain historical options only. They are not in scope for the implementation PR unless a later, explicit decision reopens them.

## What this slice does not do

- No Python, schema, golden, or CI change lands with this proposal.
- Label sheets, rights receipts, release summaries, and other command outputs are out of scope here. A later slice can reuse the same `safety_notice` constant.
- The README already carries the pre-alpha / NOT FOR NAVIGATION banner; that stays.

## Acceptance criteria (for the future implementation PR, not this docs branch)

Given the exact notice text above, when a maintainer implements this proposal under the recorded placement decision:

1. Given `harborlens --input tests/fixtures/synthetic_ais.csv --out results` exits 0, when `results/manifest.json` is read, then `safety_notice` is present and byte-for-byte equal to the notice text (same for the JSON printed to stdout).
2. Given that run, when `results/stationary_candidates.geojson` is read, then the FeatureCollection root has `safety_notice` equal to the same text, and each feature does not need a copy of the field.
3. Given that run, when `results/houston_clean.csv` and `results/stationary_candidates.csv` are hashed, then they remain a CSV table without a `#` preamble, without a notice column, and with the same columns as today (goldens for those CSVs stay byte-identical in this respect).
4. Given `python -c` or a schema validator on the written manifest and GeoJSON, then the updated schemas accept the files and reject a manifest that omits `safety_notice`.
5. Given `harborlens-verify --manifest results/manifest.json`, then exit 0 and `"ok": true` after the contract change.
6. A `rg -F 'NOT FOR NAVIGATION' results/manifest.json results/stationary_candidates.geojson` matches, and `rg -F 'Pre-alpha' ` on the same files matches.
7. Changelog, package version, dictionary, and traceability for NFR-001 are updated in the same PR. No text describes the candidates as verified berths, anchorages, or port calls.

## Decision recorded

On 21 November 2026 (America/Belem), João adopted the recommended default:

- Put `safety_notice` on `manifest.json` and on the JSON printed to stdout, with the exact notice text above.
- Put the same `safety_notice` on the candidate GeoJSON FeatureCollection root (single-file and multi-day).
- Leave `houston_clean.csv` and `stationary_candidates.csv` untouched. The NFR-001 notice for those tables is the sibling `manifest.json`.
- Do not add `NOTICE.txt`, a `#` CSV preamble, or a `safety_notice` column.

This branch still does not implement the notice in code. A later implementation PR should follow this decision, bump the package version, and update schemas, goldens that include the manifest or GeoJSON, the data dictionary, and NFR-001 traceability.
