# Real-Data Validation Protocol (Not Yet Executed)

**Evidence ladder:** L0 = deterministic synthetic software tests (done). L1 = authentic NOAA ingestion and source quality (pending). L2 = expert-labeled event inference (pending). L3 = independent terminal/port operational ground truth (pending). L4 = a different port/period replication (pending).

1. Acquire 3–7 consecutive NOAA AIS days using permissible methods with URLs, checksum, format/vintage, coverage and license; then sample multiple seasons for generalization.
2. Audit gaps, duplicates, invalid MMSI/coordinates, suspicious speeds, time ordering and geographic coverage. Retain negative and unknown samples.
3. Construct dated berth/anchorage geometry from documented USACE/NOAA data with human review; a facility point is NOT sufficient by itself.
4. Pilot at least 100 stratified annotated candidate/negative intervals following the [labeling protocol](labeling-protocol.md) (`harborlens-label-sample`, `harborlens-label-agreement`); double-label a subset and report agreement. One hundred cases is an initial sampling objective, not a statistical guarantee.
5. Compare labels with `harborlens-evaluate` (precision, recall, F1, duration MAE/median absolute error, false positives and unknown share by vessel type, location and period; prevent leakage across ship/time splits). The current command is a reproducibility harness: the report is `evaluation-v0.2`, `validation_status` stays `unvalidated`, and the caveat states that no accuracy claim is made. Real-event use of this step is still pending.
6. Compare aggregated patterns with BTS and Port Houston only where scope, units and denominators match; never claim aggregate comparison validates specific vessel calls.
7. Report assumptions, unknowns, alternate explanations, dataset rights and error bounds. Stop at `stationary_candidate` if independent labels, coverage or geometry cannot justify stronger status.

No actual AIS real-event precision, savings, emissions or port performance metrics have been validated.
