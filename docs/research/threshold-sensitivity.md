# Threshold Sensitivity (Descriptive)

**SPEC-002 / FR-022. Research-only. NOT FOR NAVIGATION.**

The BR-003 thresholds are research hypotheses. `harborlens-sensitivity` shows how strongly the candidate set depends on them, using the same engine as the pipelines:

~~~bash
harborlens --input data/houston-2024-01-02.csv --out results/houston
harborlens-sensitivity --cleaned results/houston/houston_clean.csv \
  --out results/houston/sensitivity.json \
  --max-sog-knots 0.3 0.5 1.0 --max-gap-minutes 10 15 30 \
  --window-start 2024-01-02T00:00:00Z --window-end 2024-01-02T06:00:00Z
~~~

Each setting reports candidate counts, split reasons (gap, timestamp conflict, vessel-type conflict, implied jump, spatial drift), discard reasons, candidates per MMSI, censoring counts and duration quantiles for all and for uncensored candidates. At most 64 settings are evaluated; the output must be a new file.

## How to read it

- Large changes in `gap_splits`, `moving_points` or `candidates_per_mmsi` between settings indicate fragmentation: one physical stop reported as several candidates.
- Duration quantiles for uncensored candidates are the only ones comparable across window lengths (BR-019).
- **Do not pick thresholds from these counts.** A setting that yields more or longer candidates is not more correct. Threshold selection requires independently labelled positive and negative events and the evaluation in SPEC-003 (#8, #9).

The report schema is `schemas/v1/sensitivity-report.schema.json`.
