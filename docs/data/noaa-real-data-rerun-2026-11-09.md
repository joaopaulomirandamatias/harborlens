# NOAA Real-Data Re-Run After `stationary-v0.2` — Censoring, Ceilings and a Full Week

**Evidence date:** 2026-11-09 UTC.
**Code:** `main` at `f0aae8e` (package `0.2.0.dev0`, method `stationary-v0.2`, `parameter_set` `dc3727719ee7`).
**Scope:** engineering evidence for SPEC-001/SPEC-002 (FR-021, BR-019, NFR-002), NOT verified waiting times, berths, anchorages, port calls or emissions. Every candidate below is `unvalidated`.

## How it was run

The four manual workflows could not be dispatched from the agent session (the GitHub integration has no Actions write permission). They were run instead inside an ephemeral Claude Code cloud container (Python 3.12.3, 4 vCPU, 15 GiB RAM) by executing each workflow's `run:` steps verbatim from the committed YAML, with three deliberate differences:

- the `pip install` steps were replaced by one virtual environment with `.[noaa,geo,dev]` installed from the same commit;
- each daily archive was downloaded once with the real `harborlens-download-noaa` CLI (official URL from `harborlens.vintages`) and hard-linked into each run, still enforcing the step's `--max-mib`;
- `GITHUB_STEP_SUMMARY` pointed to a local file and `HARBORLENS_GIT_COMMIT` was not set, so manifests record `git_commit: null`; the commit is the one stated above.

No raw AIS, national archive or selected CSV was committed, uploaded or kept after the session. Source redistribution and commercial reuse rights remain **review_required** (#42).

## Original NOAA archives

All seven 2024 archives were detected as `lowercase_snake_case` (`marinecadastre_csv2_zst_v1`). The 2024-01-02 and 2024-01-03 archive hashes are identical to the ones recorded by the earlier GitHub Actions runs.

| UTC day | Archive bytes | Archive SHA-256 | Rows scanned | Houston rows (full day) | Missing / invalid at extraction |
| --- | ---: | --- | ---: | ---: | --- |
| 2024-01-02 | 198,321,651 | `43bf674d62fddb69251f891fa2e3d92bcc98b3e764298130a5827b3be62d382d` | 7,292,731 | 568,913 | 0 / 0 |
| 2024-01-03 | 199,607,153 | `875bc3159ef4f4b5d62e65de8f319ef72dcb47384d8e04b95145a17cd3ad742a` | 7,287,525 | 573,177 | 0 / 0 |
| 2024-01-04 | 193,400,480 | `eb992aa170212de05cacd560fb051c98a22c0bf9dc369fd769914472a124fd5d` | 7,081,849 | 562,303 | 0 / 0 |
| 2024-01-05 | 202,017,016 | `d38ea2cde286afc3ef59d00352c964cad9e8ad8af28e56105ea78122b0fccbf3` | 7,393,444 | 559,529 | 0 / 0 |
| 2024-01-06 | 200,133,602 | `9379bc811da981e586b65d9caed6ae584602ec96fa0e57cfa3e9e3a49d5d1845` | 7,284,090 | 561,674 | 0 / 0 |
| 2024-01-07 | 195,559,568 | `7cc88eebafb1a85867bd2f8c72e6640fe1a4f7876083ae0c71a044c7070bca5f` | 7,240,044 | 571,639 | 0 / 0 |
| 2024-01-08 | 192,560,479 | `8918e3f1d065de1c6600e09e7e1c27a1879d3b6b6205e6b9446e87947ca03ab4` | 7,206,401 | 554,071 | 0 / 0 |

## Results by workflow

### 1. Daily (`noaa-daily-integration`, 2024-01-02 00:00–06:00 UTC)

Subset SHA-256 `7d799ae8…df5b1bd` and 138,758 records, 740 MMSIs and **920** candidates, all identical to the [earlier daily report](noaa-real-data-smoke-2024-01-02.md). New: censoring is now measured.

| BR-019 censoring (`window-edge-v1`) | Candidates |
| --- | ---: |
| Left-censored | 528 |
| Right-censored | 566 |
| Both sides censored | 390 |
| Uncensored | 216 |
| Unknown | 0 |

704 of 920 candidates (76.5%) touch an edge of the six-hour window, so their `duration_min` is only a lower bound. Only 216 have both boundaries observed.

### 2. Consecutive days (`noaa-consecutive-integration`, 2024-01-02 18:00 → 2024-01-03 06:00 UTC)

Subset hashes, 286,726 records, 797 MMSIs, **1,569** candidates and **564** crossing UTC midnight are all identical to the [earlier consecutive report](noaa-consecutive-days-smoke-2024-01-02-03.md), so the shared `stationary-v0.2` engine and integer-microsecond ordering (#37, #38) did not change real-data results here. The two inputs merged into one analysis block (`2024-01-02T18:00:00Z`–`2024-01-03T05:59:59Z`). Censoring: 531 left, 558 right, 225 both, 705 uncensored, 0 unknown, so 864 of 1,569 (55.1%) are edge-touching. Run time 12.3 s, peak RSS 45 MiB.

### 3. Track context (`noaa-track-context-integration`, 2024-01-02 00:00–06:00 UTC)

Identical to the [earlier full-track report](noaa-full-track-context-smoke-2026-11-09.md): 920 candidates, 6 current NOAA anchorage polygons; centroid overlap 77 single / 0 multiple / 843 none; full observed track 74 all points in one polygon / 5 partial / 841 none. Output integrity PASS. Historical polygon validity: `not_verified`; verified operational events: 0. The receipt now records the candidate method read from the `harborlens_method` block.

### 4. Seven full days (`noaa-week-integration`, 2024-01-02 → 2024-01-08, first run)

| Quantity | Result |
| --- | ---: |
| Selected records | 3,951,306 |
| Accepted points | 3,950,845 |
| Missing value / invalid / duplicates | 374 / 0 / 87 |
| Distinct MMSIs | 1,286 |
| Unvalidated stationary candidates | **15,937** |
| Candidates crossing UTC midnight | 2,750 |
| Censoring: left / right / both / uncensored / unknown | 528 / 607 / 1 / 14,803 / 0 |
| Discarded groups: too few points / too short / radius exceeded | 31,480 / 6,950 / 1 |
| Gap splits / implausible jumps / timestamp conflicts / spatial splits | 10,621 / 27 / 1 / 1 |
| MMSIs with more than one candidate; max candidates for one MMSI | 1,001; 93 |
| Analysis window | one block, 2024-01-02T00:00:00Z – 2024-01-08T23:59:59Z |
| Multi-day run time / peak RSS | 192.5 s / 47 MiB |
| SQLite scratch peak | 741.2 MiB |
| `run_id` | `c2fa672099a542f02105c46d14341f350370fb9446073e6c3a004cf0fffa1195` |

`harborlens-verify` passed for every run.

#### Vessel attributes and MMSI QA flags over the seven days (#39)

| Quantity | Points | MMSIs | Candidates |
| --- | ---: | ---: | ---: |
| Total | 3,950,845 | 1,286 | 15,937 |
| `mmsi_category` = `ship` | 3,950,842 | 1,283 | 15,937 |
| `ais_sart` / `epirb_ais` | 2 / 1 | 2 / 1 | 0 / 0 |
| Transceiver Class A | 3,659,642 (92.6%) | 985 (76.6%) | 10,839 (68.0%) |
| Transceiver Class B | 291,203 (7.4%) | 301 (23.4%) | 5,098 (32.0%) |

No `aid_to_navigation`, `placeholder` or `leading_zero_ambiguous` MMSI appeared in this Houston subset. Share of points with a transmitted value: length 99.6%, COG 90.3%, draft 80.3%, heading 66.9%.

Class B transceivers carry 7.4% of the points but 32% of the candidates, consistent with many small craft at rest. Class should be a stratum in the labeling sample (#8), and per-cohort results in the evaluator (#9) should report it separately rather than pool it with Class A.

## What this establishes

- **Censoring (#34, BR-019):** the share of candidates with lower-bound durations depends strongly on window length: 76.5% for a 6-hour window, 55.1% for a 12-hour window and 7.1% (1,134 of 15,937 have at least one censored side; left and right counts overlap in `both_censored`) for seven full days. No candidate was `unknown`, because every input carried a verified extraction sidecar. Duration metrics on short windows must use only uncensored candidates, as the evaluator already does.
- **Volume ceilings (#35):** a full Houston day is 554,071–573,177 rows (57% of the 1,000,000 per-day extraction ceiling). Seven days are 3.95 million points (66% of `MAX_POINTS` = 6,000,000), and the scratch peak was 741 MiB (36% of 2,048 MiB). That is about 197 bytes of scratch per point, above the 168 bytes measured on synthetic rows but still within the ceiling. Peak memory stayed below 50 MiB.
- **Single engine (#37, #38):** the 1-day, 2-day and track-context results are unchanged from the pre-v0.2 runs, so the refactor introduced no real-data regression on these inputs.

## What this does NOT establish

Event validity, precision/recall or timing error (no labels yet, #8/#9); whether any candidate is a berth, anchorage, wait or port call; whether MMSI is a stable identity (1,001 MMSIs have several candidates and one has 93, which needs review in the labeling sample); historical polygon validity; data rights for redistribution (#42); behaviour on 2015–2023 ZIP archives (not run here).

**NOT FOR NAVIGATION. NOT AN OFFICIAL PORT PERFORMANCE OR ENVIRONMENTAL INVENTORY.**
