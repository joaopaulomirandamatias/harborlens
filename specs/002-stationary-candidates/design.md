# SPEC-002: Technical Design

**State:** IMPLEMENTED — real one- and two-day NOAA smokes; event validity unmeasured

## Architecture and approach

Single-file runs sort one cleaned file in memory under `MAX_IN_MEMORY_ROWS`. Multi-day runs stream each file into temporary SQLite, order by `(mmsi, epoch_us, id)` on disk, and segment one candidate at a time. The SQLite working set is a fixed bound (below). Conflicting vessel type, gaps, and timestamp ties stay `unknown` or a split; they are not filled in.

## Interfaces and contracts

- Python 3.10+; all timestamps RFC 3339 UTC, coordinates WGS84 lon/lat, units explicit.
- Version all public JSON payloads under `schemas/v1`; record method/version/parameters and data vintage.
- Use `unknown` or `unvalidated` when there is no independent evidence.
- No network, private integration or cloud dependency without explicit authorization and data license review.

## Decisions and tradeoffs

Refer to `docs/architecture/adr/`; prefer deterministic batch analysis, visible uncertainty and independent reproducibility over premature complex infrastructure. Schema-breaking changes require a migration note and regression tests.

## SQLite multi-day implementation (merged in #22)

The new separate command uses a temporary disk-backed SQLite observation index sorted by MMSI/time. Cross-file duplicate points retain both local-source fingerprints, and low-speed group membership is stored on disk. The emitted event is only a stationary candidate; explicit split diagnostics track gaps, identity conflicts, improbable jumps, collisions and spatial drift. Limits fail closed; processing time and process RSS were measured for one authentic two-day sample; event ground truth remains unmeasured.

## Analysis-window censoring (BR-019, issue #34)

`src/harborlens/censoring.py` is shared by both pipelines. The window comes from a verified acquisition sidecar (`harborlens-extract-noaa-archive` or `harborlens-fetch-erddap`, matched by SHA-256 of the input bytes) or from explicit `--window-start/--window-end`. Multi-day runs use per-input sidecars only when every input has one; windows separated by no more than `max_gap_minutes` merge into one block because segmentation can bridge them, and larger separations are reported as `internal_gaps`. A candidate is censored on a side when its observed start/end lies within `max_gap_minutes` of its block edge (rule `window-edge-v1`). Segmentation, method versions and event IDs are unchanged; a known window is added to `run_id`, while runs without a window keep the previous `run_id` derivation. Censoring describes observation coverage only and never upgrades a candidate to an operational event.

## Shared segmentation engine (issue #37, method `stationary-v0.2`)

`src/harborlens/segmentation.py` owns the split rules (timestamp conflict, gap, vessel-type conflict, implied jump, spatial drift from the first point), discard rules (too few points, too short, radius exceeded), diagnostics and candidate identity. `harborlens` feeds it rows from memory (`MemoryStore`, one group at a time); `harborlens-multiday` feeds it rows from SQLite ordered by `mmsi, epoch_us, id` and keeps group members on disk. Ordering by integer microseconds instead of ISO text fixes the same-second fractional-timestamp misordering (#38).

Thresholds live in `SegmentationParams` (defaults equal BR-003), are exposed as CLI flags on both commands, and are written to the manifest (`method_parameters`), to a `harborlens_method` foreign member on the candidate GeoJSON and, as a 12-hex `parameter_set` fingerprint, to every candidate. `event_id` hashes MMSI, start, end, method version and `parameter_set`. `harborlens-track-context` reads `harborlens_method` instead of hard-coding 0.5 kn/15 min, and falls back to the v0.1 defaults only for older files.

Compared with v0.1, the single-file command now also splits on vessel-type conflicts and implied jumps, as the multi-day command already did. Candidate IDs therefore change for both commands; no labels reference them yet (#8).

`harborlens-sensitivity` re-runs the engine over a bounded grid (at most 64 settings) on one cleaned file and reports counts, split and discard reasons and duration quantiles (all and uncensored). It is descriptive: it does not select thresholds.

## Fixed multi-day working set (FR-009, NFR-004, NFR-007, BR-005, BR-007, BR-008)

`harborlens-multiday` accepts 2 to 16 distinct local files (`MAX_FILES`). The count is 16 so a 14-day synthetic measurement fits, with one file of headroom for the rejection boundary. It is not a claim that 14 full Houston days fit. `MAX_POINTS` stays 6,000,000, about seven full days at the ~560,000 rows/day used to size the cap. A larger input fails closed and writes nothing.

The working set is **fixed**, not a CLI flag. A flag would let a caller raise the bound and hide growth.

| Control | Value | Enforced? |
| --- | --- | --- |
| `PRAGMA cache_size` | `-8192` (8192 KiB) | Yes. This is the page cache. The run fails closed if the read-back is not 8192 KiB. |
| `PRAGMA mmap_size` | 0 | Yes. Scratch pages are not mapped into the process, so RSS does not track the file. The run fails closed if the read-back is not 0. |
| `PRAGMA temp_store` | `FILE` | Yes. Sorts and temporary b-trees use the scratch file, which may grow until `max_scratch_mib` (2048). The run fails closed if the read-back is not `FILE`. |
| `PRAGMA soft_heap_limit` | 8388608 bytes requested | Only when `PRAGMA compile_options` lists `ENABLE_MEMORY_MANAGEMENT` (`SQLITE_ENABLE_MEMORY_MANAGEMENT`). Otherwise the pragma can echo 8388608 and still be a no-op. The manifest field `soft_heap_limit_enforced` is `true`, `false`, or `unknown`. An 8 MiB heap bound is claimed only when that field is `true`. |

`read_memory_bound` reads those values from the connection. `require_pinned_working_set` checks the three enforced controls, and checks the soft heap number only when enforcement is `true`. `run_multiday` reads the connection again after setup, so replacing the pragma helper cannot leave a 256 MiB cache or an in-memory temp store in place. `PRAGMA shrink_memory` runs after each file and before the ordered scan. The scan uses `observations_by_vessel_time` on `(mmsi, epoch_us, id)`. Python keeps counters, the open candidate, and at most 16 source records. Group membership stays in SQLite and is streamed when the centroid radius is checked.

The manifest is `schema_version=multi-day-1.1` and records `resources.memory_bound` (`policy=fixed-sqlite-heap-v1`, `grows_with_input_rows=false`, plus `soft_heap_limit_enforced`). `schemas/v1/multi-day-run.schema.json` requires that object. A `multi-day-1.0` manifest has no `memory_bound` and is not rewritten or accepted as 1.1. `input_files.maxItems` is 16. A wrong file count or an existing output is a short stderr line and CLI exit 2, with no traceback.

**Out-of-order input.** Late points and shuffled rows are accepted. They are ordered on disk by `(mmsi, epoch microseconds, insertion id)`. There is no Python reorder buffer whose size follows lateness. Insertion id follows the inputs after their paths are sorted, then file order, so ties are deterministic (NFR-004). An exact duplicate (MMSI, timestamp, coordinates rounded to 6 decimal digits; BR-005) is stored once and keeps every source file. The same timestamp with a different position is not a duplicate: `Segmenter` treats a non-positive gap as `timestamp_conflicts` and splits (BR-007). A gap of exactly `max_gap_minutes` stays one candidate; a longer gap splits. `Segmenter.feed` still rejects a descending `(mmsi, timestamp)` with `Segmenter input is not sorted by MMSI and time` if a caller bypasses the sort. Point, scratch, export, and file-count caps fail closed and leave no output files.

**Measurable acceptance (synthetic, CI).** `tests/test_multiday_bounded.py` builds 4 fictional MMSIs at one low-speed point every 4 minutes (1440 rows/day) and runs 1, 3, 7, and 14 days in separate processes. One day is two half-day files because the command requires two inputs; the row count is still one day. The test asserts:

- tracemalloc peak during `run_multiday` ≤ 16 MiB on every size
- traced peak at 14 days minus traced peak at 1 day ≤ 1 MiB
- `resource.getrusage` peak RSS ≤ 192 MiB on every size
- RSS at 14 days minus RSS at 1 day ≤ 16 MiB
- accepted rows scale 1:3:7:14, scratch bytes do not decrease as days increase, and each size emits 4 `stationary_candidate` rows with `confidence_label=unvalidated`
- the manifest's live read-back has cache 8192 KiB, `mmap_bytes` 0, and `temp_store` `FILE`. The 14-day scratch file is only about 4 MiB, so RSS does not fail a removed pin. A connection with a 256 MiB cache, soft heap 0, mmap on, and `temp_store=MEMORY` fails `require_pinned_working_set` on that read-back, and `run_multiday` writes no manifest. On GitHub-hosted runners a 400,000-row RSS comparison of those two pins differed by only about 6 MiB, so the test does not assert RSS for that mutation.

A run that kept every row in a Python list would move the traced peak by more than 1 MiB. Scratch disk is allowed to grow. The traced ceiling is a margin over a Python 3.12 measurement (peak about 8.2 MiB, growth about 66 KiB). Absolute RSS on that machine varied from about 22 MiB to about 90 MiB across process starts, while 14-day RSS minus 1-day RSS stayed under 5 MiB, so the RSS ceiling is 192 MiB and the scaling check is the 16 MiB growth cap. These figures are not a capacity claim for a national daily archive. Real-data RSS remains the manual NOAA workflow.

Single-file `harborlens` is unchanged: it still sorts one cleaned file in memory under `MAX_IN_MEMORY_ROWS`. Its cleaned CSV, candidate CSV, and candidate GeoJSON on `tests/fixtures/synthetic_ais.csv` stay byte-identical to package `0.2.0.dev9`. The manifest differs in `code_version.package_version` and `run_id`, because `run_id` hashes `harborlens_version`.

## Proposal: streamed recount past the 256 MiB release ceiling (issue #70, not implemented)

`harborlens-release-summary` reads `houston_clean.csv` once into a buffer capped at `MAX_CLEANED_RECOUNT_BYTES` (256 MiB). SHA-256 of that buffer is compared with the manifest, and the retained-observation and MMSI-group recount uses the same bytes. That single buffer is the TOCTOU control. The synthetic seven-day cleaned CSV is 226.6 MiB, so a longer window does not fit. Issue #70 keeps the ceiling fixed and asks for a design before the first real-source release of a longer window.

This multi-day pipeline shows the shape of that design. It does not change `publication.py`, `release_verify.py`, or the 256 MiB constant.

A later slice can keep one read and drop the resident copy of the whole file:

1. Open `houston_clean.csv` once. Read fixed-size chunks (1 MiB is enough). A second open stays forbidden.
2. Update one `hashlib.sha256` with each chunk, including a partial trailing chunk. The digest is over the same bytes the recount sees.
3. Parse CSV from that stream. Carry at most one incomplete line, bounded by the existing CSV field cap (`MAX_CSV_FIELD_CHARS`). Count retained rows and distinct MMSI groups from the parsed rows.
4. Compare the finished digest to the manifest with `hmac.compare_digest`. Compare the recounted `written` and `vessels` values to the manifest. A mismatch exits 2 and writes nothing, as it does today.
5. Bound the MMSI set. It grows with distinct groups, not with rows. A fixed cap (for example 100,000 groups) fails closed. Houston-scale extracts are hundreds to low thousands of groups, so the cap is a resource limit, not a filter that drops vessels from a normal run.
6. Leave `harborlens-verify-release` as it is: `verification_scope=signed_release_and_pinned_rights_only`. It does not hold the CSV. A signed count above the 100/10 floors remains undetectable there until a separate decision says the verifier must stream the file too.

Peak memory of that recount is one chunk, one partial line, and the MMSI set, independent of file length. The 256 MiB ceiling can then become a fail-closed guard on a hostile stream only if a later change still wants one, or it can be retired once the streamed path has its own tests. That choice belongs to the #70 slice. This change does not make it.
