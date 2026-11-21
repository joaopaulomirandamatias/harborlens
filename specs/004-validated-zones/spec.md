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
4. **Given** a Federal Register window date or a geometry-vintage study timestamp on Python 3.10 or 3.12; **when** it is parsed; **then** the date is a real ASCII `YYYY-MM-DD` (week dates and `YYYYMMDD` rejected; 29 February only in a leap year) and the study timestamp is `YYYY-MM-DDTHH:MM:SS` with `Z` or `±HH:MM` and no fraction or 1 to 6 fractional digits. A non-UTC offset is converted to UTC. A naive study timestamp is rejected. An invalid `harborlens-fr-timeline` `--start` or `--end` exits 2 with the `FederalRegisterAuditError` message and no traceback, and does not open a network connection. A start date after the end date remains the existing window error. This does not approve a berth, anchorage, wait, or port call.

## Non-goals and safety

No operational navigation, autonomous control, live vessel tracking, regulatory certification, unverified berth or waiting-time claims, or unauthorized licensed data redistribution. A synthetic fixture is not independent validation.

## Definition of Done

Accepted and reviewed requirements, passing boundary/negative tests, documented source rights, updated JSON schema and traceability, explicit uncertainty and reproducible evidence attached to the linked issue/PR.

## SPEC-004 reference polygon integration result

An authentic current NOAA Anchorage Area polygon query succeeded, and an unvalidated centroid overlay against historical NOAA AIS completed. This implements reference-only spatial context, **not dated historical polygons or verified operational berth/anchorage classifications**. See the [engineering report](../../docs/data/noaa-anchorage-real-smoke-2026-11-09.md).

## Additional documentary date audit

A conservative, offline tool now records NOAA polygon source/receipt SHA-256 and optionally unverified ENC edition/last-issue metadata. Reports can flag charts published after the study but never approve historic polygon geometry or vessel operational state. Actual 2024 archival geometry and independent event validation remain open.

## GovInfo LSA index screen (not a classification result)

An opt-in comparison of the December 2023 and January 2024 GovInfo LSA Title 33 indexes is described in [the engineering note](../../docs/data/govinfo-lsa-dec-jan-comparison.md). It does not satisfy the acceptance criteria above: it loads no geofence, it does not classify a candidate, and legal effect on 2024-01-02 stays `NOT_DETERMINED`.
