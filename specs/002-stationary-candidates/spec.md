# SPEC-002: Stationary candidate inference and multi-day continuity

**Status:** IMPLEMENTED for preliminary multi-day historical reconstruction; real two-day engineering smoke passed, independent event truth still unvalidated. **Created:** 2026-11-08; **Updated:** 2026-11-09.

## Problem / user story

A researcher must identify low-speed contiguous observations without overstating berth, anchorage or waiting status.

## Linked requirements

FR-005..007, FR-009, FR-021; BR-001, BR-003, BR-007..008, BR-019

## Acceptance criteria

1. **Given** at least eight low-speed samples for >=30 minutes; **when** inference runs; **then** a stationary_candidate with unvalidated confidence and observed duration is emitted.
2. **Given** a gap beyond configured maximum; **when** inference runs; **then** segments split; a missing interval is not interpreted as continuous activity.
3. **Given** consecutive daily files with one event crossing midnight; **when** a future multi-day run executes; **then** one unbroken candidate is emitted with lineage to both files.
4. **Given** a candidate whose first observation is within `max_gap_minutes` of the analysis-window start (or last observation within `max_gap_minutes` of its end); **when** inference runs; **then** `left_censoring` (or `right_censoring`) is `censored` and the manifest counts it.
5. **Given** a candidate fully inside the window, farther than `max_gap_minutes` from both edges; **when** inference runs; **then** both flags are `not_censored`.
6. **Given** no verified sidecar and no declared window, partial sidecars across multi-day inputs, or a `--max-rows` truncated input; **when** inference runs; **then** censoring is `unknown`, never `not_censored`.
7. **Given** a sidecar that does not match the input bytes, a declaration that conflicts with the sidecar, or observations outside the declared window; **when** a run starts; **then** it fails without outputs.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
