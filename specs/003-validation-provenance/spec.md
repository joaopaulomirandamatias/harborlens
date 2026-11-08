# SPEC-003: Independent event validation and data lineage

**Status:** PROPOSED · **Created:** 2026-11-08.

## Problem / user story

A third party needs to reproduce each metric and assess error against independent real-world labels.

## Linked requirements

FR-010, FR-013..014; BR-012..013; NFR-010, NFR-012

## Acceptance criteria

1. **Given** a source snapshot and derived run; **when** an analyst requests provenance; **then** dataset URL/version, hash, method, parameters, rights, exclusions and output fingerprints are shown.
2. **Given** expert-labeled positive, negative and unknown cases; **when** validation runs; **then** confusion matrix, precision/recall/F1, MAE and coverage by cohort are reported.
3. **Given** only aggregated BTS metrics exist; **when** a comparative report is produced; **then** the document states aggregate trend validation cannot prove individual event truth.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
