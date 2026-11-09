# SPEC-003: Independent event validation and data lineage

**Status:** PARTIAL — local provenance, labeling and evaluation tooling; no labels collected · **Created:** 2026-11-08; **Updated:** 2026-11-09.

## Problem / user story

A third party needs to reproduce each metric and assess error against independent real-world labels.

## Linked requirements

FR-010, FR-013..014; BR-012..013; NFR-010, NFR-012

## Acceptance criteria

1. **Given** a source snapshot and derived run; **when** an analyst requests provenance; **then** dataset URL/version, hash, method, parameters, rights, exclusions and output fingerprints are shown.
2. **Given** expert-labeled positive, negative and unknown cases; **when** validation runs; **then** confusion matrix, precision/recall/F1, MAE and coverage by cohort are reported.
3. **Given** only aggregated BTS metrics exist; **when** a comparative report is produced; **then** the document states aggregate trend validation cannot prove individual event truth.
4. **Given** a verified run; **when** a labeling sample is drawn with a seed; **then** the same seed reproduces the same blinded sheet, every non-empty stratum (duration band × censoring × vessel group, plus negative movement intervals) is represented, and the candidate/negative key exists only in the sampling manifest.
5. **Given** two completed sheets from different annotators; **when** agreement is computed; **then** raw agreement, Cohen's kappa (seven labels and collapsed classes), the inter-annotator confusion matrix and every disagreement are reported, `unknown` labels are counted separately, and the report states that agreement is not accuracy.
6. **Given** an adjudicated label file for a sample drawn from a verified run; **when** `harborlens-evaluate` runs; **then** TP/FP/FN/TN, precision, recall, F1 and specificity with Wilson 95% intervals, a stratum-weighted precision, cohort metrics (evidence level, vessel group, censoring) and boundary MAE/median error for uncensored true positives are reported; `mixed`, `unknown` and unlabeled units are counted separately and never as correct; and the report states whether any L2 labels were used.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.

## Incremental acceptance: human-reviewed, aggregate-only local release (FR-010 / BR-015..016)

7. **Given** an acquisition receipt with source/version/source-file hash and a verified single-file run; **when** publication of a coarse aggregate is requested; **then** the exporter independently checks current per-purpose source rights and produces no release if rights are pending, prohibited or mismatched.
8. **Given** reviewed rights and a privacy/science assessment of an exact proposed summary digest; **when** local release staging runs; **then** only the allowlisted numeric summary and audit evidence are written, with no raw AIS, MMSI identifiers, positions, timestamps or individual event details; an absent/stale/mismatched human decision fails closed.
9. **Given** corrupt source/manifest/sidecar evidence, truncated output or too-small cohorts; **when** the release is requested; **then** no output is written. This is **not** general-purpose output-export enforcement or proof of anonymity.

10. **Given** an otherwise valid approval JSON; **when** publication is attempted without a valid Ed25519 signature from the out-of-band pinned reviewer key and expected identity; **then** the release is denied. Altered signed claims, changed trust key, expired review or missing cryptographic dependencies also fail closed. A locally supplied trust root is not the same as enterprise-enforced reviewer authorization.

11. **Given** a staged signed aggregate release but no original AIS files; **when** an independent reviewer supplies a trusted reviewer key/fingerprint/identity, an independently pinned rights-register snapshot and the expected study scope; **then** the verifier must check exact release structure, canonical summary hash, Ed25519 signature, review recency and acknowledgments, rights status for the same source/version/purpose, and aggregate lower bounds; invalid/ambiguous evidence must fail closed, while the result must explicitly deny proving historical AIS observations or legal permission.
