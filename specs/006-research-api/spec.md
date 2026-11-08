# SPEC-006: Research read-only API and historical map

**Status:** PROPOSED · **Created:** 2026-11-08.

## Problem / user story

Researchers need accessible reproducible historical candidate events and QA provenance, never a live navigation feed.

## Linked requirements

FR-017..018; NFR-010, NFR-016; BR-001, BR-015..016

## Acceptance criteria

1. **Given** existing run with candidates; **when** GET list is requested; **then** versioned response marks unvalidated events and includes method lineage.
2. **Given** a run is missing; **when** the API is queried; **then** 404 is returned without leaking internal filesystem or customer data.
3. **Given** a visual map of results; **when** a researcher opens it; **then** a time label, data gaps and NOT FOR NAVIGATION notice are visible.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
