# SPEC-003: Independent event validation and data lineage

**Status:** PARTIAL — local provenance, labeling and evaluation tooling; no labels collected · **Created:** 2026-11-08; **Updated:** 2026-11-12.

## Problem / user story

A third party needs to reproduce each metric and assess error against independent real-world labels.

## Linked requirements

FR-010, FR-013..014; BR-012..013; NFR-010, NFR-012

## Acceptance criteria

1. **Given** a source snapshot and derived run; **when** an analyst requests provenance; **then** dataset URL/version, hash, method, parameters, rights, exclusions and output fingerprints are shown.
2. **Given** expert-labeled positive, negative and unknown cases; **when** validation runs; **then** confusion matrix, precision/recall/F1, MAE and coverage by cohort are reported.
3. **Given** only aggregated BTS metrics exist; **when** a comparative report is produced; **then** the document states aggregate trend validation cannot prove individual event truth.
4. **Given** a verified run; **when** a labeling sample is drawn with a seed; **then** the same seed reproduces the same blinded sheet, every non-empty stratum (duration band × censoring × vessel group × transceiver class `A` / `B` / `absent_or_unknown`, plus negative movement intervals stratified by vessel group × transceiver class) is represented when the requested count covers those strata, every transceiver class present in the frame is still represented when the requested count is smaller than the number of strata but at least as large as the number of classes, missing or invalid transceiver values stay in `absent_or_unknown` rather than being dropped, and the candidate/negative key exists only in the sampling manifest.
5. **Given** two completed sheets from different annotators; **when** agreement is computed; **then** raw agreement, Cohen's kappa (seven labels and collapsed classes), the inter-annotator confusion matrix and every disagreement are reported, `unknown` labels are counted separately, and the report states that agreement is not accuracy.
6. **Given** an adjudicated label file for a sample drawn from a verified run; **when** `harborlens-evaluate` runs; **then** TP/FP/FN/TN, precision, recall, F1 and specificity with Wilson 95% intervals, a stratum-weighted precision, cohort metrics (evidence level, vessel group, censoring) and boundary MAE/median error for uncensored true positives are reported; `mixed`, `unknown` and unlabeled units are counted separately and never as correct; and the report states whether any L2 labels were used.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
