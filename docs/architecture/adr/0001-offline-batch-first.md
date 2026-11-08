# ADR 0001-offline-batch-first: Offline batch before real-time infrastructure

**Status:** Accepted  
**Date:** 2026-11-08

## Context

Historical NOAA AIS permits reproducible science but not a current operational feed.

## Decision

Use stdlib-compatible Python CLI plus synthetic tests first; no Kafka, Kubernetes or autonomous vessel actions.

## Consequences and alternatives

Low initial cost and clear research state; large-file scaling and multi-day continuity remain open. Alternatives must be revisited when new empirical results or customer requirements justify added complexity.
