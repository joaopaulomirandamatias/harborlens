# Multi-day Historical AIS Reconstruction — SPEC-002

**Status:** experimental; synthetic tests passed and initial authentic two-day NOAA engineering run completed. Event accuracy remains unvalidated. Findings are unvalidated stationary candidates, not verified waiting times, berth occupancy, or port calls.

## Why this matters

An AIS observation stream often crosses UTC midnight. Processing daily CSV files independently can split one continuous candidate into two events. HarborLens now offers a separate batch command to ingest two to seven **locally available geographic subsets**, deduplicate observations across file boundaries, perform an on-disk chronological sort by MMSI, and report any candidate that spans a date boundary.

Install and execute after obtaining authorized local data:

~~~bash
python -m pip install -e '.[noaa]'
harborlens-multiday --input data/houston-day-1.csv data/houston-day-2.csv --out results/houston-two-days
harborlens-verify --manifest results/houston-two-days/manifest.json
~~~

For national compressed NOAA archives, first use the existing opt-in daily download and archive-extraction steps. **The command above does not access the Internet or automatically download data.**

## Memory and disk architecture

- Temporary SQLite stores normalized points, source membership and candidate-group membership, and performs a deterministic sort by MMSI/time.
- Python holds running aggregates and one active low-speed candidate at a time; full per-vessel tracks are **not** accumulated in a Python list.
- The temporary directory is deleted after completion or a failed run.
- Defaults: at most 7 sources, 6 million input rows, 2,048 MiB SQLite scratch, 1,024 MiB exported files (ceiling 2,048). Exceeding a limit fails rather than silently truncating data. The manifest records the `limits` used and `resources.scratch_peak_bytes`.
- Output files are never overwritten; rerun to a new output directory for reproducibility.
- Measured on synthetic data ([scale benchmark](scale-benchmark-2026-11-09.md)): 3.92 million rows in 78 s, 47 MiB RSS, 628 MiB scratch peak (about 168 bytes per row). The two-day NOAA run measured 46 MiB RSS; a seven-day real run is pending.

## Output

The export directory contains canonical cleaned CSV, candidate CSV and GeoJSON with the same base filenames as the single-file pipeline, plus a versioned multi-day run manifest. The existing harborlens-verify command checks the three export checksums.

Additional event fields:
- source_files_json: JSON array of local filename@hash-prefix references for observations that contributed to the event.
- source_count: number of source files contributing to the candidate.
- crosses_utc_date: whether the observed start/end belong to different UTC dates.
- left_censoring / right_censoring: whether the candidate touches an analysis-window edge (BR-019). Windows come from each input's verified acquisition sidecar; if any input lacks one, censoring is `unknown`. Inputs without sidecars can share one explicit `--window-start/--window-end`.

Each result is labeled stationary_candidate and unvalidated. Source file SHA-256 proves which local bytes were used; it **does not** authenticate agency origin or grant redistribution rights. All source rights remain review_required.

## Handling ambiguity

- An exact point duplicate spanning input files is stored once but retains **both** source references.
- A gap greater than 15 minutes, conflicting transmitted vessel type, identical timestamp with incompatible position, implausible jump or movement resets the current low-speed episode.
- A candidate requires at least eight observations, 30 minutes, speed at most 0.5 knots and a maximum radial spread of 1,000 meters around its calculated centroid (BR-003 defaults; configurable with `--max-sog-knots`, `--min-duration-minutes`, `--max-gap-minutes`, `--max-radius-m`, `--min-points`, `--max-jump-knots`). The single-file `harborlens` command uses the same engine and rules (`stationary-v0.2`).
- The MMSI is a transmitted identifier, not an independently confirmed vessel identity.
- Counts of gaps, contradictory identity reports, timestamp conflicts and suspicious jumps are diagnostics—not ground-truth classification or an official traffic statistic.

## Remaining acceptance gates

1. Pass synthetic regression cases covering midnight, duplicate provenance, gaps, type conflicts, jumps and integrity verification.
2. Measure peak RAM, SQLite scratch and runtime on authorized NOAA consecutive-day geographic subsets.
3. Confirm source licenses, sampling/coverage, repeat observations and timezone boundaries for real daily archives.
4. Compare inferred candidates with independently verified port events and authoritative dated geometries before claiming anchorage, berth or waiting outcomes.
5. Maintain explicit uncertainty and NOT FOR NAVIGATION warnings in API and map work.

## First real two-day test

See the [2024-01-02/03 NOAA integration report](noaa-consecutive-days-smoke-2024-01-02-03.md) for exact source hashes, candidate counts, time and memory measurements, and scientific limitations.
