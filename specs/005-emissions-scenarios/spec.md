# SPEC-005: EPA-based emissions scenarios and sensitivity

**Status:** PROPOSED · **Created:** 2026-11-08.

## Problem / user story

Environmental analysts need transparent hypothetical emission estimates with all assumptions and uncertainty visible.

## Linked requirements

FR-016; BR-014..015; NFR-020

## Acceptance criteria

1. **Given** validated duration and authorized EPA factors; **when** a scenario runs; **then** units, mode, engine/load/fuel assumptions, ranges and factor vintage are reported.
2. **Given** essential engine/load information is missing; **when** a scenario is requested; **then** the tool does not fabricate a measured emissions value.
3. **Given** a baseline and an intervention scenario; **when** a comparison runs; **then** the output is explicitly hypothetical, not an observed causal reduction.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.
