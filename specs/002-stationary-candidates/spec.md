# SPEC-002: Stationary candidate inference and multi-day continuity

**Status:** PARTIAL — SYNTHETIC ONLY · **Created:** 2026-11-08.

## Problem / user story

A researcher must identify low-speed contiguous observations without overstating berth, anchorage or waiting status.

## Linked requirements

FR-005..007, FR-009; BR-001, BR-003, BR-007..008

## Acceptance criteria

1. **Given** at least eight low-speed samples for >=30 minutes; **when** inference runs; **then** a stationary_candidate with unvalidated confidence and observed duration is emitted.
2. **Given** a gap beyond configured maximum; **when** inference runs; **then** segments split; a missing interval is not interpreted as continuous activity.
3. **Given** consecutive daily files with one event crossing midnight; **when** a future multi-day run executes; **then** one unbroken candidate is emitted with lineage to both files.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
