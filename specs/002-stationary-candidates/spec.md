# SPEC-002: Stationary candidate inference and multi-day continuity

**Status:** IMPLEMENTED for preliminary multi-day historical reconstruction with a fixed SQLite cache, mmap off, and a file temp store. The soft heap limit is enforced only when the build lists `ENABLE_MEMORY_MANAGEMENT`. Real two-day engineering smoke passed; independent event truth is still unvalidated. **Created:** 2026-11-08; **Updated:** 2026-11-12.

## Problem / user story

A researcher must identify low-speed contiguous observations without overstating berth, anchorage or waiting status.

## Linked requirements

FR-005..007, FR-009, FR-021, FR-022; BR-001, BR-003, BR-007..008, BR-019

## Acceptance criteria

1. **Given** at least eight low-speed samples for >=30 minutes; **when** inference runs; **then** a stationary_candidate with unvalidated confidence and observed duration is emitted.
2. **Given** a gap beyond configured maximum; **when** inference runs; **then** segments split; a missing interval is not interpreted as continuous activity.
3. **Given** consecutive daily files with one event crossing midnight; **when** a future multi-day run executes; **then** one unbroken candidate is emitted with lineage to both files.
4. **Given** a candidate whose first observation is within `max_gap_minutes` of the analysis-window start (or last observation within `max_gap_minutes` of its end); **when** inference runs; **then** `left_censoring` (or `right_censoring`) is `censored` and the manifest counts it.
5. **Given** a candidate fully inside the window, farther than `max_gap_minutes` from both edges; **when** inference runs; **then** both flags are `not_censored`.
6. **Given** no verified sidecar and no declared window, partial sidecars across multi-day inputs, or a `--max-rows` truncated input; **when** inference runs; **then** censoring is `unknown`, never `not_censored`.
7. **Given** a sidecar that does not match the input bytes, a declaration that conflicts with the sidecar, or observations outside the declared window; **when** a run starts; **then** it fails without outputs.
8. **Given** one input processed by `harborlens` and by `harborlens-multiday` (split into daily files); **when** both run with the same thresholds; **then** they emit identical candidates and identical split/discard diagnostics.
9. **Given** non-default thresholds; **when** a run completes; **then** they appear in the manifest, the GeoJSON `harborlens_method` block and each candidate's `parameter_set`, change the `run_id`, and `harborlens-track-context` applies them in its completeness check.
10. **Given** a group rejected by any rule; **when** the run completes; **then** it is counted under `discarded_by_reason`.
11. **Given** synthetic multi-day inputs of 1, 3, 7, and 14 days with the same rows per day; **when** `harborlens-multiday` runs in a fresh process per size; **then** traced Python peak and process RSS stay inside the fixed ceilings in the design, scratch bytes may grow, and a low-speed track that crosses midnight is one `stationary_candidate` with `confidence_label=unvalidated`.
12. **Given** shuffled rows, a point filed in the wrong day's file, a same-timestamp position conflict, or an exact duplicate across files; **when** multi-day segmentation runs; **then** order is the disk order `(mmsi, epoch_us, insertion id)`, the conflict splits, the duplicate is stored once with both sources, and a descending timestamp fed straight to `Segmenter` fails closed.
13. **Given** the SQLite build's `PRAGMA compile_options`; **when** a multi-day run finishes; **then** `resources.memory_bound.soft_heap_limit_enforced` is true only if `ENABLE_MEMORY_MANAGEMENT` is listed, false if the list is readable without it, and `unknown` if the list cannot be read. Cache, mmap, and temp store still have to match the pin or the run fails closed.
14. **Given** synthetic inputs of 1, 3, 7, and 14 days; **when** the fixed pin is in force; **then** the resident mapping of the scratch database stays within the ceiling in the design. **Given** the same 14-day input with a 256 MiB cache, soft heap 0, mmap on, and `temp_store=MEMORY`; **when** that measurement runs; **then** the resident mapping exceeds the ceiling.
15. **Given** fewer than 2 files, more than 16 files, or an output directory that already contains the exports; **when** `harborlens-multiday` is invoked; **then** it writes a short message to stderr and exits 2, with no traceback and without replacing existing outputs.
16. **Given** a `multi-day-1.0` manifest without `memory_bound`; **when** it is checked against `schemas/v1/multi-day-run.schema.json`; **then** it is rejected and is not treated as `multi-day-1.1`.
17. **Given** an unreadable input or a header missing a required column; **when** `harborlens-multiday` runs; **then** it exits 2 with a short stderr line and no traceback. A directory this command created for that failed run is removed when it is empty. An output directory that already existed is left in place.
18. **Given** a host without `/proc/self/smaps`; **when** the mapped-RSS checks run; **then** they skip. **Given** Linux where that file exists and the probe returns None; **when** those checks run; **then** they fail.
19. **Given** `--window-start` and `--window-end`; **when** the window is parsed; **then** Python 3.10 and 3.12 both require uppercase `T`, `HH:MM:SS`, no fraction or 1 to 6 fractional digits, and `Z` or `±HH:MM`. A non-UTC offset is converted to UTC. A naive clock and a space separator are rejected. ASCII whitespace around the value is ignored.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
