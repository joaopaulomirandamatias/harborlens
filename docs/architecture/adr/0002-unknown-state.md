# ADR 0002-unknown-state: Explicit unvalidated and unknown states

**Status:** Accepted  
**Date:** 2026-11-08

## Context

Low speed alone does not prove an anchorage, berth, queue or port call.

## Decision

Emit only stationary_candidate with confidence_label=unvalidated until authoritative zones and labels exist.

## Consequences and alternatives

Preserves scientific integrity; requires later independent event validation. Alternatives must be revisited when new empirical results or customer requirements justify added complexity.
