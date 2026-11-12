# Changelog

## [Unreleased]

### Changed (SPEC-001: synthetic-ID guard scans every tracked text file)
- Package version stays `0.2.0.dev16`. No pipeline output changes. `tests/test_synthetic_ids.py` reads every text file `git ls-files` tracks, including `src/`, `docs/`, `schemas/`, and `specs/`. A file with a NUL byte, or bytes that are not UTF-8, is binary: it is skipped and counted. Paths are classified relative to the repository root.
- A candidate is nine digits bounded by a non-digit. The pattern is `(?<!\d\.)(?<!\d)(\d{9})(?!\d)`. A run of ten or more digits does not match. A fractional part after a digit and a dot, such as `29.123456789`, does not match. A dot that is not part of a decimal still matches. The MID is the first three digits. The guard does not read digits 2–4 of a leading-0 or leading-9 form. The token fails when that MID is in 201–775, in any column (including `vessel_id`), in any JSON key or value, and in prose.
- A nine-digit run inside a hexadecimal run of 64 or more characters is a SHA-256 digest or a longer hex blob. A standalone nine-digit token in the same file still fails. The 256 MiB value is ignored only when it is the value assigned by a whole-word `mmap_size`. An f-string prefix (`f` or `F`, with an optional `r` on either side, single or triple quotes) whose first three digits are an assigned MID fails. File-exact exclusions remain the four `tests/fixtures/single_day_0.2.0.dev9/` goldens and `tests/synthetic_id_map.py`, each with a written reason. When `git` cannot be run, the coverage test skips. When the environment variable `CI` is `true`, that test fails instead of skipping.
- A former Marshall Islands-MID synthetic ID was removed from this changelog and from `docs/requirements/traceability.md`. The mapping table still holds that retired key because `tests/synthetic_id_map.py` is a file-exact exclusion. Git history is unchanged.
- Single-day `houston_clean.csv`, `stationary_candidates.csv`, and `stationary_candidates.geojson` on `tests/fixtures/synthetic_ais.csv` stay byte-identical to `0.2.0.dev15`: `4cd3986411530eef4296bcc2a964ab978f11925468bce8e67600c11c4aad1b75`, `69989a5c0f6f53961ca2ce3987ba06d3381a6f92490fd16773e709d824a3fc05`, `0e3127c834035c27546b209d024f3c9ba8b7ae9e249200abb8fa8dee010008d3`. The synthetic fixture label sheet stays byte-identical (SHA-256 `d5430083cd4e580b6d88140e95e0196de8fff8f7f0e742c8c181cb790ded1803`). `publication.py`, `release_verify.py`, `review_signatures.py`, `rights.py`, and `io_safe.py` are unchanged. No source is approved. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #88 (stays open). Refs #84 (stays open). Refs #9 (stays open).

### Security (SPEC-003: label-sheet formula neutralization)
- Package version `0.2.0.dev16` in `pyproject.toml`, `src/harborlens/__init__.py`, and `CITATION.cff`. `harborlens-label-sample` prefixes a text cell with one ASCII apostrophe when the first character is `=`, `+`, `-`, `@`, tab, or carriage return, or when the first character after leading Unicode whitespace is one of those triggers. Text columns are `vessel_type_mode`, `annotator_id`, `evidence_sources`, `notes`, and `adjudicator_id`. A field that contains a comma, quote, carriage return, or line feed is quoted on Python 3.10 and 3.12. Python 3.10's `csv.writer` leaves a bare carriage return when the row ends in a line feed, which would split the row.
- Contract columns are validated and written unchanged: `sample_id` (`S` plus four digits), `mmsi` and `observed_points` (unsigned integers), `centroid_lon` and `centroid_lat` (finite decimals, so `-95.1` is unchanged), `start_utc` and `end_utc` (ISO-8601 UTC), censoring flags, and the annotation enums. `true_start_utc` and `true_end_utc` use that timestamp contract. A failing value raises `AISInputError`. The CLI exits 2 and writes no sheet, no `.partial`, and no sampling manifest.
- The sampling key stays JSON (`<sheet>.sampling.json`). It is not a CSV. `harborlens-label-agreement` and `harborlens-evaluate` write JSON. On read, `_read_sheet` and `_read_labels` remove the apostrophe only on a text column, and only when the remainder matches the trigger rule, which recovers the logical value. An apostrophe that is not that prefix is kept. A logical value that already began with an apostrophe followed by a trigger is indistinguishable from a neutralized cell and is returned without the apostrophe. A leading apostrophe on a contract column raises `AISInputError` and is not converted to a number, timestamp, or enum.
- The label sheet for `tests/fixtures/synthetic_ais.csv` has no trigger text. Its bytes are unchanged (SHA-256 `d5430083cd4e580b6d88140e95e0196de8fff8f7f0e742c8c181cb790ded1803`). Single-day `houston_clean.csv`, `stationary_candidates.csv`, and `stationary_candidates.geojson` stay byte-identical to `0.2.0.dev15`: `4cd3986411530eef4296bcc2a964ab978f11925468bce8e67600c11c4aad1b75`, `69989a5c0f6f53961ca2ce3987ba06d3381a6f92490fd16773e709d824a3fc05`, `0e3127c834035c27546b209d024f3c9ba8b7ae9e249200abb8fa8dee010008d3`. That cleaned CSV is the file the release recount reads. `publication.py`, `release_verify.py`, `review_signatures.py`, `rights.py`, and `io_safe.py` are unchanged. The manifest differs in `code_version.package_version` and in `run_id`. The GovInfo LSA report's `harborlens_version` is `0.2.0.dev16` because that field copies the package version. Comparison behavior is unchanged. No source is approved. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #85 (stays open). Refs #9 (stays open).

### Changed (SPEC-003: evaluation warning)
- `harborlens-evaluate` `warning` is now `Metrics compare unvalidated stationary candidates with adjudicated labels from a stratified sample. Agreement with labels at any evidence level, including L3, is not validated performance while validation_status is unvalidated. Recall covers sampled movement intervals only, not stops the method never segmented.`
- The caveat strings are unchanged. For `synthetic`: `These labels are synthetic. They are not independent ground truth, and this report makes no accuracy claim.` For `unspecified`: `Label provenance is unspecified. These labels are not independent ground truth, and this report makes no accuracy claim.`
- No schema const and no golden file pinned the previous warning. `schemas/v1/evaluation-report.schema.json` types `warning` as a string. `tests/test_evaluation_harness.py` had required the substrings `not independent ground truth` and `L3` inside the warning. That assertion now requires the full sentence. The labeling `warning` is unchanged and does not use the word accuracy. Refs #86 (stays open). Refs #9 (stays open).

### Accepted limitation
- `evaluation-v0.1` reports are not readable since `0.2.0.dev14`. They are refused with `EvaluationReportError`, and no v0.1 reader is maintained.

### Changed (SPEC-001: synthetic vessel identifiers use unassigned MID 199)
- Package version `0.2.0.dev15` in `pyproject.toml`, `src/harborlens/__init__.py`, and `CITATION.cff`. Synthetic vessel identifiers move from assigned MIDs to unassigned MID 199, form `1990xxxxx`. The full 1:1 map is `SYNTHETIC_ID_MAP` in `tests/synthetic_id_map.py`. `tests/test_synthetic_ids.py` rejects a committed fixture MMSI, or a test vessel-id literal, whose MID is in 201–775.
- A former Marshall Islands-MID synthetic ID was found in the category table. That MID is allocated to the Republic of the Marshall Islands on the ITU Table of Maritime Identification Digits. It is migrated to `199090001`.
- `mmsi_category` is unchanged and `other` is the correct flag for an unassigned MID. The ITU MID block is 201–775. A leading digit `2`–`7` is `ship`. A leading digit `1` is `other`. Every migrated fixture row therefore changes from `ship` to `other`. On `tests/fixtures/synthetic_ais.csv`, `mmsi_categories` changes from `{"ship": 60}` to `{"other": 60}`. Observation counts do not change (`written` 60, one stationary candidate). A leading `7` whose MID is above 775 (MID 790) still classifies as `ship`; that path is covered by a classifier test and a pipeline test.
- The candidate `event_id` is SHA-256 of `mmsi|start|end|method_version|parameter_set`, truncated to 18 hex characters. The single-day candidate changes from `97804ba6c59f9497ed` to `f15a5a20540a9ec5b3`.
- Golden files for this package are `tests/fixtures/single_day_0.2.0.dev15/`. `tests/fixtures/single_day_0.2.0.dev9/` is the input of the mapping proof. The proof applies `SYNTHETIC_ID_MAP`, changes `ship` to `other` only on mapped rows, and recomputes `event_id`, `input_sha256`, `run_id`, and `package_version` with `hashlib`. Those projected bytes equal the dev15 goldens. Any other difference fails.
- SHA-256 of the single-day artifacts on `tests/fixtures/synthetic_ais.csv`:
  - `houston_clean.csv`: `82db41ec7542bd5d32ab865ee839295b1f7fb2c33ee9be79bc654e355b2fd3b1` → `4cd3986411530eef4296bcc2a964ab978f11925468bce8e67600c11c4aad1b75` (4423 → 4483 bytes)
  - `stationary_candidates.csv`: `b5f8bf7b6bb9c855f52d0d5b26a34123b1f7d3511c441fd4efcc905b59537cd7` → `69989a5c0f6f53961ca2ce3987ba06d3381a6f92490fd16773e709d824a3fc05` (440 → 441 bytes)
  - `stationary_candidates.geojson`: `7f063677040698bbfa0a42a139da5ecb5d292127fde4bdaf41d1ecfad367aa71` → `0e3127c834035c27546b209d024f3c9ba8b7ae9e249200abb8fa8dee010008d3` (1167 → 1168 bytes)
- The GovInfo LSA report's `harborlens_version` is `0.2.0.dev15` because that field copies the package version. Comparison behavior is unchanged. No source is approved. This change makes no accuracy claim. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #84 (stays open). Refs #9 (stays open).

### Changed (SPEC-003: unvalidated evaluation harness)
- Package version `0.2.0.dev14` in `pyproject.toml`, `src/harborlens/__init__.py`, and `CITATION.cff`. `harborlens-evaluate` writes `evaluation-v0.2`. `validation_status` is the const `unvalidated`. `--label-provenance` is `synthetic` or `unspecified`; the default, with no flag, is `unspecified`. Any other value exits 2 through `parser.error`, prints no traceback, and writes nothing.
- The report `caveat` is a fixed string. For `synthetic` it is `These labels are synthetic. They are not independent ground truth, and this report makes no accuracy claim.` For `unspecified` it is `Label provenance is unspecified. These labels are not independent ground truth, and this report makes no accuracy claim.` The existing `warning` text is unchanged.
- **Compatibility:** an `evaluation-v0.1` report is not readable. `read_evaluation_report` raises `EvaluationReportError` (a subclass of `AISInputError`) and the message names `evaluation-v0.1`. The file is not upgraded. `schemas/v1/evaluation-report.schema.json` rejects any `schema_version` other than `evaluation-v0.2` and any `validation_status` other than `unvalidated`. Those failures are `jsonschema.ValidationError`, a named error.
- The synthetic harness runs a generated AIS file through `harborlens`, `harborlens-label-sample` with seed `20241112`, an adjudicated sheet that has no vessel id, and `harborlens-evaluate --label-provenance synthetic`. Expected confusion counts, rates, Wilson intervals, timing MAE/median, and excluded `mixed` / `unknown` / unlabeled counts are computed in `tests/test_evaluation_harness.py` and are not taken from `binary_metrics` or `wilson`. Zero judged units leave rates null. A denominator of 1 uses the Wilson interval `[0.2065, 1.0]`. Censored true positives leave MAE and median null.
- Single-file cleaned CSV, candidate CSV, and candidate GeoJSON on `tests/fixtures/synthetic_ais.csv` stay byte-identical to `0.2.0.dev9`. SHA-256 prefixes: cleaned CSV `82db41ec`, candidate CSV `b5f8bf7b`, candidate GeoJSON `7f063677`. The manifest differs in `code_version.package_version` and in `run_id`. `src/harborlens/publication.py`, `release_verify.py`, `review_signatures.py`, `rights.py`, and `io_safe.py` are unchanged. The GovInfo LSA report's `harborlens_version` is `0.2.0.dev14` because that field copies the package version. Comparison behavior is unchanged. No source is approved. This harness makes no accuracy claim. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #9 (stays open). Refs #65 (stays open).

### Changed (SPEC-001, SPEC-002, SPEC-003, SPEC-004: timestamp parsing agrees on Python 3.10 and 3.12)
- Package version `0.2.0.dev13` in `pyproject.toml`, `src/harborlens/__init__.py`, and `CITATION.cff`. The timestamp and calendar parsers match an ASCII pattern and build `datetime` or `date` from the captured fields. They do not call `fromisoformat`, so Python 3.10 and 3.12 accept the same strings.
- `publication._review_moment` accepts ASCII `YYYY-MM-DDTHH:MM:SS` with no fraction or 1 to 6 fractional digits, then `Z` only. `+00:00` stays rejected, which is narrower than the rights-register clock. Seven fractional digits, a comma fraction, another offset, a lowercase `t` or `z`, a non-ASCII digit, hour 24, and a non-leap 29 February are denied on both interpreters. A canonical `Z` timestamp with no fraction, or with six fractional digits, still parses to the same instant. A staged release of that review is otherwise unchanged. Ordinary manifests change in `code_version.package_version` and in `run_id`, because `run_id` hashes `harborlens_version`.
- `ais.parse_time` accepts a NOAA naive clock (`T` or one ASCII space), `Z`, `+00:00`, `-00:00`, and other `±HH:MM` offsets converted to UTC. The fraction is absent or 1 to 6 digits. Leading and trailing ASCII whitespace is ignored. `censoring.parse_utc` uses that clock and requires `Z` or `±HH:MM`; it also strips ASCII whitespace. `erddap.utc`, `archive_extract.utc`, and `vintage._aware_time` use the same required-offset grammar and do not strip, so a surrounding space is rejected there. A space separator is observation-only.
- `harborlens-download-noaa --date` and `fr_timeline._date` accept only a real ASCII `YYYY-MM-DD` calendar date. ISO week dates (`2024-W01-1`) and `YYYYMMDD` are rejected on both interpreters. An invalid `--date` exits 2 with no traceback and does not open a network connection. 29 February is accepted in a leap year, including 2000, and rejected in 1900 and 2023.
- `vintage._calendar_date` and `cfr_anchorages._study_date` are unchanged. The multi-day ordered scan still parses timestamps this command wrote (no fraction, or six fractional digits, then `Z`) on the way into the segmenter.
- Single-file cleaned CSV, candidate CSV, and candidate GeoJSON on `tests/fixtures/synthetic_ais.csv` stay byte-identical to `0.2.0.dev9`. The GovInfo LSA report's `harborlens_version` is `0.2.0.dev13`. Comparison behavior is unchanged. No source is approved. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #78 (stays open).

### Changed (SPEC-002: multi-day parser errors and mapped-RSS portability)
- An unreadable multi-day input and a header missing a required column are `AISInputError` at the source (`sha256` wraps `OSError`, including `PermissionError`; `header_alias` no longer raises a bare `ValueError`). `harborlens-multiday` exits 2 with a short stderr line and no traceback. `main` does not catch a bare `ValueError`.
- When the command creates the output directory and the run then fails, that empty directory is removed. An output directory that already existed is left in place, including when its files already exist. Parent directories created because `mkdir` uses `parents=True` are left in place.
- The 1/3/7/14-day mapped-RSS checks and the mutated-pin mapping check call `skipTest` when `/proc/self/smaps` is absent. On Linux, a `None` probe result still fails, so the memory test still bites in CI. Refs #77 (stays open). Items 1 and 2 on that issue stay out of this slice.

### Changed (SPEC-002: multi-day memory bound, CLI errors, schema 1.1)
- Package version `0.2.0.dev12` in `pyproject.toml`, `src/harborlens/__init__.py`, and `CITATION.cff`. Multi-day manifests are `schema_version` `multi-day-1.1`. `resources.memory_bound` gains `soft_heap_limit_enforced`: true when `PRAGMA compile_options` lists `ENABLE_MEMORY_MANAGEMENT`, false when that list is readable and omits it, and `unknown` when the list cannot be read. The enforced pin remains cache 8192 KiB, `mmap_bytes` 0, and `temp_store` `FILE`. The 8 MiB soft heap limit is requested and is a bound only when `soft_heap_limit_enforced` is true.
- The 1/3/7/14-day measurement also asserts that the scratch database's resident mapping stays ≤ 1 MiB. The 14-day synthetic scratch file is about 4 MiB, so RSS growth stays inside 16 MiB even with mmap on. A run with a 256 MiB cache, soft heap 0, mmap on, and `temp_store=MEMORY` maps that file and exceeds the 1 MiB ceiling.
- `harborlens-multiday` exits 2, with a short stderr line and no traceback, when the file count is below 2 or above 16 and when the output files already exist. Existing outputs are left in place.
- A `multi-day-1.0` manifest without `memory_bound` does not validate as `multi-day-1.1`.
- Single-file cleaned CSV, candidate CSV, and candidate GeoJSON on `tests/fixtures/synthetic_ais.csv` stay byte-identical to `0.2.0.dev9` and to `0.2.0.dev11`. The single-file manifest changes in `code_version.package_version` and in `run_id`, because `run_id` hashes `harborlens_version`. The GovInfo LSA report's `harborlens_version` moves with the package. Comparison behavior is unchanged. The release path is unchanged. No source rights are granted. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #77 (stays open). Refs #5 (stays open).

### Security (SPEC-003: fail-closed rights-register parsing)
- A register that starts with a UTF-8 BOM is a named load error, `Rights register has a UTF-8 BOM`. The CLI exits 2, `rights_status` stays `review_required`, and the BOM is not stripped. `rights_status_for` returns `review_required`. `rights_receipt` reports `invalid_registry`. YAML is `Rights register is unreadable` and is not an approval.
- `reviewed_at_utc` must match an ASCII `YYYY-MM-DDTHH:MM:SS` timestamp with no fraction or 1 to 6 fractional digits, then `Z` or `+00:00`. The same pattern is in the schema. The clock is built from the captured fields, with the fraction padded to six digits. `fromisoformat` is not used, so Python 3.10 and 3.12 accept the same strings. Seven digits, another offset, a non-ASCII digit, and an impossible calendar time (including 29 February in a non-leap year and hour 24) do not grant.
- https URLs use an ASCII hostname. Punycode is accepted. IPv6 literals, raw IDN hostnames, userinfo, an uppercase scheme, and any whitespace, including a trailing path space or tab, fail in the schema and in the parser.
- A different case or surrounding whitespace on a status or purpose does not grant. Whitespace-only reviewer, attribution, URL, hash, or timestamp evidence does not grant. The five checked-in sources stay `review_required` for `research`, `public_aggregates`, and `commercial`.
- A repeated JSON object key at any depth is `Rights register has a duplicate key` (CLI exit 2). `json.loads` no longer keeps the last `rights_status` or `decision`. A document nested deeply enough to raise `RecursionError` (about 1000 objects on Python 3.10) is `Rights register is unreadable` (CLI exit 2). https ports must be 1-65535. A backslash, a C0 or C1 control, or DEL anywhere in a URL does not grant. Package version stays `0.2.0.dev11`.
- Package version `0.2.0.dev11`. Main already published `0.2.0.dev10` for the multi-day working set, so this merge re-bumps. The packaged `source-rights-register` schema bytes changed. Ordinary single-file manifests differ from `0.2.0.dev10` in `code_version.package_version` and `run_id`. Cleaned CSV, candidate CSV, and candidate GeoJSON stay byte-identical to `0.2.0.dev10`. The LSA report's `harborlens_version` is `0.2.0.dev11`. Comparison behavior is unchanged. No source is approved. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #67 (stays open). Refs #42 (stays open).

### Added (SPEC-003: ERDDAP and archive-extract sidecar schemas)
- `schemas/v1/erddap-ais-source.schema.json` and `schemas/v1/noaa-archive-extract-source.schema.json` describe the sidecars from `harborlens-fetch-erddap` and `harborlens-extract-noaa-archive`, including `rights_status` and the optional `rights_review` receipt. Adapters do not load them at runtime, so they are not packaged. The multi-day schema stays unpackaged as well. Synthetic tests validate writer output and keep the checked-in register at `review_required`. Refs #69 (stays open). Refs #42 (stays open).

### Changed (SPEC-002: fixed multi-day working set)
- Package version `0.2.0.dev10` in `pyproject.toml`, `src/harborlens/__init__.py`, and `CITATION.cff` on main. `harborlens-multiday` accepts 2 to 16 local files. Seventeen files fail closed and write nothing. `MAX_POINTS` stays 6,000,000, so about seven full Houston days still fit. This merge keeps that behavior and sets the package to `0.2.0.dev11`.
- SQLite page cache is 8192 KiB, the soft heap limit is 8 MiB, memory mapping is off, and temporary store is `FILE`. Those values are constants, not CLI flags. The run fails closed if SQLite does not report them. `PRAGMA shrink_memory` runs after each file and before the ordered scan. The scan uses an index on `(mmsi, epoch_us, id)`.
- Multi-day manifests gain `resources.memory_bound` (`policy=fixed-sqlite-heap-v1`, `grows_with_input_rows=false`). `schemas/v1/multi-day-run.schema.json` requires that object and allows 16 input files. Scratch disk may still grow up to `max_scratch_mib`. That schema is not packaged.
- Shuffled rows and late points are ordered on disk. There is no in-memory reorder buffer. An exact duplicate is stored once and keeps every source. The same timestamp with a different position splits the candidate. `Segmenter` rejects a descending timestamp.
- Single-file cleaned CSV, candidate CSV, and candidate GeoJSON on `tests/fixtures/synthetic_ais.csv` stay byte-identical to `0.2.0.dev9` and to `0.2.0.dev10`. The single-file manifest changes in `code_version.package_version` and in `run_id`, because `run_id` hashes `harborlens_version`. The GovInfo LSA report's `harborlens_version` moves with the package. The comparison behavior is unchanged. No source rights are granted. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #5 (stays open).
- The 256 MiB release-path recount is unchanged. A streamed recount (one read, incremental SHA-256, streamed row and MMSI recount, capped MMSI set) is proposed in the SPEC-002 design and is not implemented. Refs #70 (stays open).

### Security (SPEC-003: release summary rights_status is an allowlist)
- `harborlens-release-summary` denies a staged summary whose `rights_status` is missing, `None`, not a string, or outside `APPROVED_STATUSES` (`reviewed_public_domain_attribution_required`, `reviewed_permitted_with_conditions`). The denial is `ReleaseDenied` and the CLI exits 2 with no traceback and no file. A missing status no longer skips the `conditions_reviewed` requirement. Package version stays `0.2.0.dev9`. Successful release documents are unchanged. Refs #70 (stays open).

### Changed (SPEC-003: release-review tolerance, one summary evaluation, packaged schemas)
- Package version `0.2.0.dev9` in `pyproject.toml`, `src/harborlens/__init__.py`, and `CITATION.cff`. The installed wheel and sdist now contain `public-summary.schema.json`, `publication-review.schema.json`, and `release-verification-result.schema.json` under `harborlens/schemas/v1/`. `read_packaged_release_schema` loads those names with `importlib.resources` only. Any other name is refused. The GovInfo LSA schema stays unpackaged.
- Ordinary `harborlens` manifests stay byte-identical to `0.2.0.dev8` except `code_version.package_version` and `run_id`. `run_id` is the SHA-256 of settings that include `harborlens_version`, so that digest changes with the version string and no other main-gate field changes. The LSA report's `harborlens_version` is the same version string. A successful release document gains no fields; its `run_id` changes only when the manifest was produced by this version. Runs from `0.2.0.dev8` and `0.2.0.dev9` are not directly comparable. No source rights are granted. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #70 (stays open). Refs #42 (stays open).

### Added (SPEC-003: documented review clock and single release evaluation)
- `reviewed_at_utc` is documented as an RFC3339 UTC date-time accepted from 30 days before the checker clock through 5 minutes after it, inclusive. The 5 minutes are a fixed clock-skew allowance (`REVIEW_FUTURE_TOLERANCE`), not a configuration knob. `harborlens-release-summary` and `harborlens-verify-release` share `review_timestamp_is_current`. CLI help states the same window.
- `harborlens-release-summary` calls `prepare_summary` once per invocation, including one `rights_receipt`, and stages that summary. It does not build the summary again. README and `schemas/README.md` name the release CLIs and the three packaged schemas.
- The 256 MiB cleaned-CSV recount ceiling stays fixed. This change does not add a streaming reader. Refs #70 (stays open).

### Changed (SPEC-004: version the GovInfo LSA comparison artifact)
- Package version `0.2.0.dev8` in `pyproject.toml`, `src/harborlens/__init__.py`, and `CITATION.cff`. The LSA comparison is a new artifact with its own schema, so the version identifies the code that generated it. The report requires `harborlens_version`, copied from `harborlens.__version__`.
- Ordinary AIS manifests change because `run_id` hashes `harborlens_version` and `code_version.package_version` records it. Runs from `0.2.0.dev7` and `0.2.0.dev8` are not directly comparable. No source rights are granted. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #7 (stays open).
- Optional extra `lsa` requires `pypdf>=6.21.4,<7`. `6.21.4` is the first pypdf release that contains the fix for every entry the GitHub Advisory Database currently publishes for pypdf, including the denial-of-service advisories (infinite loops and large memory use). The highest patched version in that set is 6.21.4 (`GHSA-5849-834g-hvw5`, `GHSA-cggf-277g-3q54`, `GHSA-mfr5-77xh-9j7h`). The `dev` extra does not aggregate optional extras, so pypdf is not added there.
- `MAX_PDF_PAGES` is 299. pypdf `page_tree_maximum_entries` is set to 299 before the page tree is flattened. Copied page-dictionary keys are capped at 1024 because that counter is not a page count. Title 33 text is accumulated only until the Title 34 header, including text on that page before the header and excluding text before the Title 33 header. A larger file, or any exception from `PdfReader` construction, the page count, or `extract_text`, makes the CLI exit 2, write nothing, and print no traceback. A missing pypdf install says to install `harborlens[lsa]`.
- Downloaded bytes are pinned before parse. December 2023 is SHA-256 `c226121a7617f1b4578a0fcf79f58d4735696e0405c5522615699bdb5bab037d` (554882 bytes, 117 pages). January 2024 is SHA-256 `5ce3c08a45ed6853643a105690d332cbf9813400d4da391de794ef1237305348` (516462 bytes, 82 pages). A mismatch uses `hmac.compare_digest` and exits 2 with nothing written. The opener uses an empty `ProxyHandler` and does not honor `HTTPS_PROXY`. Redirects 301, 302, 303, 307, and 308 are built in this module and stay a GET to the same fixed URL, including on Python 3.10, whose urllib handler rejects 308. `http_error_308` uses that same handler. There is no wall-clock timeout around pypdf parsing; that is an accepted residual of this opt-in command. Package version stays `0.2.0.dev8`. Refs #7 (stays open).

### Added (SPEC-004: GovInfo December 2023 / January 2024 LSA index comparison)
- Opt-in `python -m harborlens.lsa_compare --fetch` can read the two fixed GovInfo monthly LSA PDFs. Import, ordinary `harborlens` runs, and the test suite make no network request. A fetch allows only those two HTTPS URLs; a redirect that changes the URL is refused. The timeout is 60 seconds, redirects stop at three, and each PDF is capped at 10 MiB. Extracted Title 33 text is capped at 500,000 characters.
- The report always sets `legal_effect_on_study_date` to `NOT_DETERMINED`, `rights_status` to `review_required`, and `ais_spatial_join_permitted` to false. It does not join AIS and it cannot express approval or certification. Digest comparisons use `hmac.compare_digest`.
- Schema `schemas/v1/govinfo-lsa-dec-jan-comparison.schema.json` is registered in `schemas/README.md`. It is not packaged: setuptools packages only `src/harborlens/schemas/v1/*.json` (the rights register). No console script was added. The removed real-source Actions workflow stays removed.
- Version `0.2.0.dev8` identifies this artifact. See the changed entry above. Pinned PDF bytes are not a legal determination. A stationary candidate is not a berth, anchorage, wait, or port call. Refs #7 (stays open).

### Security (SPEC-003: single-buffer recount and constant-time digest pins)
- `harborlens-release-summary` reads `houston_clean.csv` once into a bounded buffer (`MAX_CLEANED_RECOUNT_BYTES`, 256 MiB, the same output ceiling as archive extraction and track-context). SHA-256 of those exact bytes is compared with the manifest, and the retained-observation and MMSI-group recount uses the same buffer. There is no second open between the hash and the recount. A file larger than the ceiling is detected by reading ceiling + 1 bytes, then the command exits 2 and writes nothing.
- A manifest hash or `counts.written` / `events.vessels` value that does not match that buffer exits 2 and writes nothing. Recount tests that do not need a signature run without the optional `cryptography` extra.
- Pinned digest, hash, fingerprint and parameter-set comparisons use `hmac.compare_digest` on normalized lowercase hex or equal-typed bytes. A mismatched digest exits 2 and writes nothing.
- Package version `0.2.0.dev7`. Ordinary manifests change because `run_id` hashes `harborlens_version`, and `code_version.package_version` records it. The new oversize denial is an additional exit path. Runs from `0.2.0.dev6` and `0.2.0.dev7` are not directly comparable. No source rights are granted. A recounted cohort is not a berth, anchorage, wait, port call, or accuracy claim. Refs #70 (stays open). Refs #71 (stays open). Refs #42 (stays open).

### Added (SPEC-003: independent verifier known limitation)
- `docs/data/independent-release-verification.md` records that `harborlens-verify-release` does not recount the cleaned AIS CSV. The Ed25519 review attests the counts. Successful results keep `verification_scope=signed_release_and_pinned_rights_only`. A signed retained count inflated above the 100-observation and 10-group floors is not detectable without the CSV. Anyone holding `houston_clean.csv` must recount through the release path.

### Added (SPEC-003: independent signed-release verification)
- New offline, read-only `harborlens-verify-release` checks a staged aggregate without AIS input. It reuses `summary_sha256` (`allow_nan=False` canonical bytes) and `verify_review_signature`. The Ed25519 message is the domain separator `harborlens.publication-review.v1`, a newline, then the canonical review JSON. Signatures from `0.2.0.dev4`, which omit that separator, are rejected. Pinned SPKI fingerprints use `hmac.compare_digest`.
- Aggregate floors are the recounted publication floors: 100 retained observations and 10 MMSI groups. A large `observations_scanned` value copied from a manifest does not pass when the retained recount or the MMSI-group recount is below those floors. A date-only `reviewed_at_utc` is denied. A missing `cryptography` import exits 2 and writes nothing. Tests that need Ed25519 skip with `unittest.skipUnless` and a lazy import.
- Package version `0.2.0.dev6`. Ordinary manifests change because `run_id` hashes `harborlens_version`, and `code_version.package_version` records it. Runs from `0.2.0.dev5` and `0.2.0.dev6` are not directly comparable. No source rights are granted. A verified signature is not a berth, anchorage, wait, port call, or accuracy claim. Refs #42 (stays open). Refs #70 (stays open). Refs #71 (stays open).

### Security (SPEC-003: release-summary recount and signed-review format)
- **BREAKING:** The Ed25519 signed-review message is now the domain separator `harborlens.publication-review.v1`, a newline, then the canonical JSON of every field except `signature_b64` (sorted keys, compact separators, ASCII escaping, `allow_nan=False`, trailing newline). Signatures made for `0.2.0.dev4`, which signed that JSON only, are rejected. Re-sign with `review_message()`.
- Canonical release bytes also use `allow_nan=False`. NaN and Infinity fail closed (exit 2, nothing written) and cannot be hashed or staged.
- `harborlens-release-summary` recounts retained observations and distinct MMSI groups from the verified `houston_clean.csv` and applies the 100-observation and 10-group floors to that recount. If manifest `counts.written` or `events.vessels` disagrees, the command exits 2 and writes nothing.
- A date-only `reviewed_at_utc` (`2026-11-12` or `2026-11-12Z`) is a validation failure: exit 2, no traceback, nothing written.
- Pinned reviewer SPKI SHA-256 fingerprints are compared with `hmac.compare_digest`. The `release` and `dev` extras require `cryptography>=42.0.4`. Ed25519 tests skip with an explicit reason when that extra is absent. A missing `cryptography` import denies release (exit 2, nothing written).
- Package version `0.2.0.dev5`. Ordinary manifests change because `run_id` hashes `harborlens_version`, and `code_version.package_version` records it. Runs from `0.2.0.dev4` and `0.2.0.dev5` are not directly comparable. No source rights are granted. Refs #70. Refs #71. Refs #42 (stays open).

### Security (SPEC-003: cryptographically signed reviewer approval)
- Require Ed25519 signature verification for aggregate release staging, including independently pinned reviewer public-key fingerprint and identity. Unsigned, altered or mismatched review JSON fails closed; offline synthetic key/signature attack tests and updated schemas/docs. No real data rights are granted.
- Package version `0.2.0.dev4`. Actual staging requires `--trusted-reviewer-key`, `--trusted-reviewer-key-sha256` and `--trusted-reviewer-id`. The staged review object adds `signature_algorithm`, `public_key_sha256` and `signature_b64`. Ordinary manifests change because `run_id` hashes `harborlens_version` and `code_version.package_version` records it. Runs from `0.2.0.dev3` and `0.2.0.dev4` are not directly comparable.

### Added (SPEC-003: controlled aggregate publication)
- A new offline `harborlens-release-summary` command stages allowlisted, coarse research counts only after source/run hash checks, current purpose-specific source-rights verification and a recent human approval of the exact proposed summary digest. Pending sources and mismatched evidence fail without release output; no raw data, geofences or event-level exports are copied. Synthetic-only positive/negative/attack tests and JSON Schemas added; no source is approved in the checked-in register.
- Package version `0.2.0.dev3`. The command prints a JSON decision and exits 2 when release is denied. A successful non-dry run writes a new `public-summary-v0.1` file (`summary`, `summary_sha256`, `release_review`). Ordinary manifests also change: `run_id` hashes `harborlens_version`, and `code_version.package_version` records it. Runs from `0.2.0.dev2` and `0.2.0.dev3` are not directly comparable.

### Added (SPEC-003: source-rights adapter receipts)
- Optional per-purpose, exact-source-version source-rights registry lookups with SHA-256 receipts for NOAA ERDDAP, local daily archive extraction, NOAA anchorage polygons and USACE point catalog; defaults remain review_required. Receipts call `load_registry`, so a schema-invalid register is `invalid_registry` and is not granted. Synthetic-only source and schema regression tests; no license or vessel-event approval.
- Package version `0.2.0.dev2`. Adapter sidecars gain `rights_review`. A supplied register can change `rights_status` and the USACE `license_status`. Runs from `0.2.0.dev1` and `0.2.0.dev2` are not directly comparable because `run_id` includes the package version.
- `rights_receipt` reads the register once. The SHA-256 and the decision both come from that buffer after the packaged-schema check. The package version stays `0.2.0.dev2`.

### Added (SPEC-003: source rights register, #42)
- `docs/data/rights-register.json`: offline inventory of five official sources. **No source has been approved.** Every checked-in entry stays `rights_status=review_required`.
- Schema `source-rights-register` (`schemas/v1/source-rights-register.schema.json`). `load_registry` validates a register against that schema before any decision; a schema-invalid register is a load error and is not granted.
- `python -m harborlens.rights`: offline audit helper. Exit 0 only when `rights_status` is an approved status; exit 1 for any other status, including `review_required` and `use_restricted`; exit 2 when the register cannot be loaded, parsed or schema-validated. JSON stays on stdout, and a load failure includes an `error` field so it is distinct from pending. Optional adapter receipts are the entry above; with no reviewed register, acquisition metadata remains `review_required`.
- The schema copy used at runtime is `src/harborlens/schemas/v1/source-rights-register.schema.json`, byte-identical to `schemas/v1/source-rights-register.schema.json`, and is loaded with `importlib.resources` only. The helper does not search parent directories.
- Optional extra `rights` (`pip install 'harborlens[rights]'`) installs `jsonschema`. Core dependencies stay empty. If `jsonschema` is missing, the helper exits 2 and the JSON `error` names that extra. Validation is never skipped.
- Terms, evidence and source URLs must be `https` with a real host. `https://user@`, `https://.`, `https:// ` and `https://@` are rejected. The schema pattern requires a host.

### Changed (SPEC-003: transceiver class in the labeling sample, #65)
- `harborlens-label-sample` stratifies candidates by duration band × censoring × vessel group × transceiver class (`A`, `B`, `absent_or_unknown`) and negative movement intervals by vessel group × transceiver class. Missing, blank and any value other than A or B is `absent_or_unknown` and stays in the sample. On the recorded seven-day NOAA run, Class B was 7.4% of points and 32% of stationary candidates (`docs/data/noaa-real-data-rerun-2026-11-09.md`), so class coverage is no longer left to a proportional draw.
- When fewer units are requested than there are non-empty strata, full cross-cell coverage is impossible. `stratification.all_non_empty_strata_drawn` is then false. Every transceiver class present in the frame (`A`, `B`, `absent_or_unknown`) is still drawn when the request is at least as large as the number of those classes. The annotator sheet is unchanged and still blinded.
- **Migration:** sampling manifests move from `label-sample-v0.1` to `label-sample-v0.2` (new required `transceiver_class` on each key item, plus `stratification`). No labeling sheets have been collected; regenerate samples. v0.1 manifests do not validate against v0.2. `harborlens-evaluate` parses the stratum from the manifest `schema_version` rather than guessing the vessel group from field position, and the unit `kind` must match that stratum.
- Package version `0.2.0.dev1` (method unchanged, `stationary-v0.2`). Runs from `0.2.0.dev0` (the recorded NOAA week in `docs/data/noaa-real-data-rerun-2026-11-09.md`) and `0.2.0.dev1` are not directly comparable: `run_id` includes the package version, and the label-sample stratification changed. The previous sampling remains reproducible by running `0.2.0.dev0`.
- `harborlens-evaluate` reads stratum keys with the sampling manifest's `schema_version`. A `label-sample-v0.2` key must have that version's field count, a vessel group of `cargo`, `tanker`, `passenger`, `tug_or_service`, or `other_or_unknown`, and transceiver class `A`, `B`, or `absent_or_unknown`. A `label-sample-v0.1` key is accepted only when the manifest says so. The unit `kind` must match the stratum kind; a missing or mismatched kind raises `AISInputError` naming the `sample_id` instead of changing the confusion matrix. The CLI reports that error with a nonzero exit and no traceback. A damaged key raises the same error instead of being reported as a vessel group. Valid evaluation reports are unchanged, so the package version stays `0.2.0.dev1`.

### Added (SPEC-001: NOAA archive vintages, #36)
- `harborlens.vintages`: 2015–2023 daily ZIP layout and 2024–2026 csv2 zstd layout, with how each was verified. `harborlens-download-noaa` builds URLs from it and refuses unregistered years (it previously built a csv2 URL for 2019–2023).
- `harborlens-extract-noaa-archive` accepts single-CSV `.zip` archives, no longer hard-codes 2024, checks compression against the year, and records `source_vintage` in the sidecar.
- Ingestion and extraction count `missing_value` (empty required field, e.g. 2025 nulls) separately from `invalid`; manifest `counts` gain `missing_value`.
- The seven-day workflow resolves archive names through the registry.

### Added (SPEC-001: vessel attributes and MMSI QA flags, #39)
- Cleaned AIS keeps `cog_deg`, `heading_deg`, `length_m`, `width_m`, `draft_m`, `transceiver_class` (NOAA sentinels → empty) and an ITU-R M.585 `mmsi_category` flag; new columns are appended. Rows are never dropped by category; both manifests report `mmsi_categories`.
- Candidates carry `vessel_type`, `transceiver_class`, `length_m`, `draft_m` and `mmsi_category` for stratified evaluation; `read_candidates_csv` returns missing values as `None`.
- Schema migration: `ais-point`, `stationary-candidate`, both candidate feature schemas and both manifests require the new fields; regenerate earlier outputs. Older cleaned CSV files without the new columns still load.

### Changed (SPEC-003: contracts and run identity, #41)
- Package version `0.2.0.dev0` (method `stationary-v0.2`). Both manifests record `code_version`; the package version is part of `run_id` (the CI git commit is recorded as metadata only). Bump the version for any output-changing change (CONTRIBUTING).
- New `stationary-candidate-feature.schema.json` for single-file GeoJSON features and `harborlens.ais.read_candidates_csv` for typed CSV records; real CLI exports are now validated in tests.
- CI matrix on Python 3.10 and 3.12 (minimum and current).
- `CITATION.cff`.

### Changed (SPEC-001/SPEC-002: volume ceilings, #35)
- Ceilings sized for seven full Houston days from a synthetic 3.92-million-row benchmark (`docs/data/scale-benchmark-2026-11-09.md`, `tools/benchmark_multiday.py`): extraction 1,000,000 rows / 256 MiB; multi-day 6 million rows, 2,048 MiB scratch, 1,024 MiB default export; track-context 6 million rows, 100,000 candidates, 60,000 points per candidate; in-memory tools 6 million rows, checked while reading. All limits still fail closed.
- Manifests and the extraction sidecar record `limits`; the multi-day manifest records `resources.scratch_peak_bytes`. The export-phase scratch check now uses the configured scratch cap instead of four times the export cap.
- New manual workflow `noaa-week-integration.yml` for 2–7 consecutive full NOAA days (aggregate metrics only).

### Added (SPEC-003: evaluator, #9)
- `harborlens-evaluate`: confusion matrix, precision/recall/F1/specificity with Wilson 95% intervals, design-weighted precision, cohorts (evidence level, vessel group, censoring), candidate label composition and boundary MAE/median error for uncensored true positives; `mixed`/`unknown`/unlabeled units reported separately. Schemas `adjudicated-label`, `evaluation-report`. No real labels evaluated yet.

### Added (SPEC-003: labeling pilot tooling, #8)
- `docs/research/labeling-protocol.md`: label taxonomy, L2/L3 evidence levels, censoring and fragmentation rules, double annotation and adjudication.
- `harborlens-label-sample`: seeded, blinded, stratified sample of candidates and negative movement intervals from a verified run, with a sampling manifest holding the key.
- `harborlens-label-agreement`: validation of two annotators' sheets, Cohen's kappa, confusion matrix and disagreements. Agreement is not accuracy; no labels have been collected yet.
- Schemas `label-record`, `label-sample`, `label-agreement`.

### Changed (SPEC-002: shared segmentation engine, FR-022, #37; fixes #38)
- Both `harborlens` and `harborlens-multiday` now use one engine (`harborlens.segmentation`, method `stationary-v0.2`). The single-file command now also splits on vessel-type conflicts and implied jumps (>65 kn), as the multi-day command did; for the same input both commands emit identical candidates and diagnostics.
- Thresholds are configurable on both commands (`--max-sog-knots`, `--min-duration-minutes`, `--max-gap-minutes`, `--max-radius-m`, `--min-points`, `--max-jump-knots`) and recorded in `method_parameters`, in a `harborlens_method` GeoJSON member and as `parameter_set` on every candidate. `harborlens-track-context` reads them instead of hard-coding 0.5 kn / 15 min.
- Manifests report split reasons, `discarded_by_reason`, `candidates_per_mmsi` and (single-file) `unparsable_rows`.
- Multi-day ordering uses integer microseconds, so same-second fractional timestamps are no longer misordered (#38).
- **Migration:** method version `stationary-v0.1` / `stationary-multiday-v0.1` → `stationary-v0.2`; `event_id`, `run_id` and artifact hashes change, and earlier outputs do not validate against the updated schemas. Re-run the pipeline. No labels reference earlier event IDs.

### Added
- `harborlens-sensitivity`: descriptive threshold-grid report (`schemas/v1/sensitivity-report.schema.json`, `docs/research/threshold-sensitivity.md`). It does not select thresholds.

### Added (SPEC-002: analysis-window censoring, BR-019 / FR-021, #34)
- `left_censoring` / `right_censoring` on every stationary candidate (single-file and multi-day), `analysis_window` and `events.censoring` in both manifests, `--window-start/--window-end` CLI flags, and automatic use of verified extraction/ERDDAP sidecars.
- Manual NOAA workflows now publish aggregate censoring counts.

### Changed (schema migration)
- `schemas/v1` candidate, multi-day feature, run manifest and multi-day manifest now require the censoring fields. Outputs produced before this change do not validate against the updated schemas; re-run the pipeline to regenerate them. Segmentation, method versions and event IDs are unchanged; `run_id` changes only when a window is known.

### Added (SPEC-004 official Federal Register text triage)
- Fixed-list full-text source verification of four 2023 Federal Register Part 110 index documents; official metadata/bytes hashed, source links restricted and relevance flags non-certifying.

### Added (SPEC-004: official 2024 CFR anchorages)
- Source-pinned July 1, 2024 federal 33 CFR 110.197 Galveston anchorage DMS registry and fail-closed topology/datum inspection. A/B/C lack explicit NAD83 status; A East literal corner order fails Polygon validity. No guessed WGS84 geometry or operational classification.

### Added (SPEC-004 observed-track evidence)
- Local Shapely/SQLite full-track vs Polygon reference context with interval/cardinality checks, historic-vintage flags, source receipt hashes, strictly unverified statuses and synthetic/schema tests.

### Added (SPEC-004: NOAA Polygon reference)
- Opt-in NOAA designated anchorage polygon source, conservative candidate spatial-context overlay and synthetic geometry regression tests. No event confirmation.

### Added (SPEC-004: initial)
- Bounded opt-in official USACE point-feature reference import with output/source hashes, contracts and synthetic regression tests; no inferred berth polygons or port-event truth.

### Added
- SQLite-based multi-day AIS candidate reconstruction with source provenance, cross-midnight grouping and bounded local processing.
- Synthetic regression tests, multi-day JSON Schemas and schema validation in CI.
- A source-pinned NOAA 2024-01-02/03 engineering experiment and manual-only national-archive workflow.

### Limitations
- Historical candidate segments have no independently validated berth, anchorage, waiting-time or emissions interpretation.

### Recorded integration evidence (2026-11-09; previously filed under 0.1.0)

#### NOAA real-data re-run on `stationary-v0.2` (evidence)

- Daily, consecutive-day, track-context and first seven-full-day runs on NOAA 2024-01-02…08 archives. Earlier 1-day, 2-day and track-context counts reproduced exactly; censoring measured for the first time (76.5% of candidates edge-touching in a 6-hour window, 55.1% in 12 hours, 7.1% over seven days). Seven days: 3.95 million points, 15,937 unvalidated candidates, 741 MiB scratch peak, 47 MiB RSS, all within the #35 ceilings. Run locally from the workflow steps because Actions dispatch was unavailable to the agent. See docs/data/noaa-real-data-rerun-2026-11-09.md.

#### USACE facility point source integration (evidence)

- Initial bounded USACE Navigation Facilities POINT catalog query for Houston: 723 features and 536 Dock records; output SHA-256 and schema checks passed; no dated berth polygon or confirmed port-event status. See docs/data/usace-points-smoke-2026-11-09.md.

#### NOAA reference polygon integration (evidence)

- Source-pinned NOAA Designated Anchorage Areas real-data query and historical AIS candidate centroid overlay completed. Six current areas, 920 unvalidated candidates, 77 possible centroid overlaps; no historical anchorage or waiting truth established. See docs/data/noaa-anchorage-real-smoke-2026-11-09.md.

#### First authentic full-track Polygon geometric comparison

- NOAA 2024-01-02 historical AIS and six current NOAA reference polygons: 920 unvalidated candidate segments; 74 with all observed points within one polygon, 5 with partial point coverage and 841 without observed-point overlap. [Source-pinned evidence](docs/data/noaa-full-track-context-smoke-2026-11-09.md). Operational event and historical polygon validity remain unverified.

#### Added (SPEC-004: historical source-vintage screening)

- Offline NOAA ENC documentary date audit checks current polygon/source hashes and optional unverified ENC metadata; all outputs deny automatic historical certification and retain review_required rights.

#### NOAA historical geometry vintage source smoke

- Official current NOAA Anchorage Areas Polygon retrieval, source checksum and documentary January 2024 audit passed with non-certifying no_documentary_enc_evidence status. See docs/data/noaa-geometry-vintage-smoke-2026-11-09.md.

#### Source-verification evidence for Galveston/Bolivar Roads legal anchors

- GPO 2023/2024 annual CFR Title 33 full HTML checksums and all 16 regulatory corner pairs matched; legal scope remains annual-edition dated, A/B/C datum unspecified, A East literal ring flagged. See docs/data/cfr-2023-2024-source-verification.md.

#### Source-pinned 2023/2024 Federal Register Part 110 index screening

- Four Proposed Rule metadata entries returned from official FederalRegister.gov for the defined publication window; API page and report SHA-256 recorded. This is not a legal effect conclusion. See docs/data/fr-part110-real-index-2023-2024.md.

#### Federal Register original full-text evidence

- Official 2023 source-metadata and raw-text hashes verified for four Part 110 index hits; no direct section 110.197 or Houston/Galveston text mentions in the four. [Source report](docs/data/fr-2023-original-fulltext-evidence-2026-11-09.md). GPO LSA and exact January 2024 legal effect are still unverified.

Following [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [Semantic Versioning](https://semver.org/).

## [0.1.0] — 2026-11-08

### Added
- NOAA-style AIS input normalization, batch quality counters, input hash and stationary-candidate baseline.
- Synthetic fixture and regression tests; Python package CLI.
- SDD specification baseline, requirement IDs, JSON Schemas, architecture, security and research documentation.

### Limitations
- Tested only with fictional AIS data. No actual vessel, port waiting, berth, anchorage, emissions, real-world accuracy or commercial service is verified.
