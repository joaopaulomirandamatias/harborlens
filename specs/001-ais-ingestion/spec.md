# SPEC-001: AIS ingestion, normalization and provenance

**Status:** IMPLEMENTED — SYNTHETIC ONLY · **Created:** 2026-11-08.

## Problem / user story

A researcher needs a source-pinned local AIS batch with reliable input field normalization and explicit quality exclusions.

## Linked requirements

FR-001..004, FR-008; NFR-002..006; BR-002, BR-004..006

## Acceptance criteria

1. **Given** a valid NOAA-style CSV; **when** the CLI runs; **then** normalized UTC observations, bbox and exact-dedup counts, SHA-256 and outputs are generated.
2. **Given** invalid, duplicate and out-of-zone rows; **when** ingest runs; **then** each exclusion type is reported separately and invalid rows do not enter cleaned output.
3. **Given** unsupported or malformed data; **when** a batch is requested; **then** a clear error or rejection is produced; no fabricated event is returned.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
