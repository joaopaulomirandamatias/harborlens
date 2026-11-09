# SPEC-004: Dated facilities, anchorages and event classification

**Status:** PARTIAL — USACE point adapter, NOAA current polygon/centroid and full-track context, and CFR/Federal Register source audits merged; historical dated polygons and independent event labels pending. **Created:** 2026-11-08.

## Problem / user story

Analysts need to know whether a candidate is in a verifiable berth or anchorage without treating facility points as polygons.

## Linked requirements

FR-011..012, FR-015; BR-007..011

## Acceptance criteria

1. **Given** USACE facility coordinate without verified polygon; **when** the classifier is invoked; **then** it refuses to assert a verified berth.
2. **Given** dated valid geofence and candidate trajectory; **when** classification is requested; **then** it records zone version, evidence and confidence alongside any unknown/conflict.
3. **Given** coverage gaps or outside verified geometry; **when** classification runs; **then** unknown is emitted rather than a default berth or anchor state.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.

## SPEC-004 reference polygon integration result

An authentic current NOAA Anchorage Area polygon query succeeded, and an unvalidated centroid overlay against historical NOAA AIS completed. This implements reference-only spatial context, **not dated historical polygons or verified operational berth/anchorage classifications**. See the [engineering report](../../docs/data/noaa-anchorage-real-smoke-2026-11-09.md).

## Additional documentary date audit

A conservative, offline tool now records NOAA polygon source/receipt SHA-256 and optionally unverified ENC edition/last-issue metadata. Reports can flag charts published after the study but never approve historic polygon geometry or vessel operational state. Actual 2024 archival geometry and independent event validation remain open.
