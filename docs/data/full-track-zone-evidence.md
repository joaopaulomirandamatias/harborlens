# Full observed AIS track vs NOAA Polygon spatial evidence (SPEC-004)

**Research-only, historically unverified. NOT FOR NAVIGATION.**

## Why the centroid alone is insufficient

A stationary candidate's *centroid* may fall inside a polygon even when a substantial share of observed AIS points lies outside. The new full-track context command uses **all cleaned observations corresponding to each candidate's MMSI and time interval**, rather than asserting that the centroid describes every observation.

The algorithm reads the already-generated cleaned AIS CSV and candidate GeoJSON, validates the exact number of observations and interval boundaries, sorts AIS observations using local temporary SQLite, and performs Shapely Point/Polygon intersection with holes and overlapping zones. All source data remain local. It neither downloads AIS nor changes vessel-state labels.

## Usage with existing outputs

Run on a machine with the geographic extra installed:

~~~bash
python -m pip install -e '.[geo,dev]'
harborlens-track-context \
  --cleaned results/noaa-multiday/houston_clean.csv \
  --candidates results/noaa-multiday/stationary_candidates.geojson \
  --polygons data/houston-noaa-anchorage-areas.geojson \
  --out results/noaa-multiday/full-track-context.geojson
~~~

The NOAA polygon source receipt must be present adjacent to the polygon GeoJSON (same filename with '.source.json' suffix). Its output SHA-256 must match the polygon bytes, and it must explicitly identify historical validity as 'not_verified', geometry review as 'unreviewed', and data rights as 'review_required'. An analyst may point to a separate receipt with --polygon-receipt.

## Status taxonomy

Every candidate retains 'stationary_candidate' and 'confidence_label=unvalidated'. The additional 'full_track_zone_evidence' object can have these **descriptive spatial-observation statuses only**:

- all_observed_points_within_one_polygon: all available interval points fall inside a single source polygon.
- partial_observed_point_overlap: some observed points fall inside exactly one polygon; others lie outside.
- multiple_zone_evidence_ambiguous: observations intersect more than one supplied polygon (possibly overlapping areas).
- no_observed_point_overlap: no supplied polygon contains an observed point.
- incomplete_track_unknown: the observed count, first/last timestamps, speed or gap check does not match the original candidate.
- outside_declared_vintage_unknown: an optional user-declared source validity interval does not cover the candidate.

Even the first status **does not** mean that the vessel was officially anchored, awaiting a berth, inside a legally designated anchorage in the historical year, or that the vessel's entire *continuous* route was within the polygon. It means *only* that the available discrete AIS points fall within a geometrical source reference.

Current NOAA spatial snapshots are not automatically historically applicable to AIS observations from 2024. No official historical source dates were verified in the prior spatial integration. If a source receipt has optional effective_from_utc/effective_to_utc declarations, the tool reports inside_unreviewed_declared_vintage or outside_declared_vintage; it NEVER upgrades an unreviewed declaration to authoritative.

## Source and integrity safeguards

- Strict local file bounds: no more than 1.5 million cleaned AIS rows, 20,000 candidate events, 500 source polygons and 10,000 observations per event.
- Maximum 768 MiB temporary SQLite database and 48 MiB output. SQLite is deleted after execution. These limits are engineering controls, not a certified public-upload sandbox.
- SHA-256 hashes of cleaned AIS, candidate input, polygon input, NOAA source receipt and annotated output.
- No automatic download, raw-AIS upload, live tracking, navigation, berth estimation or government endorsement.
- The output is GeoJSON plus a separate local JSON receipt with aggregate counters. Input files are not overwritten.
- Full observed-track coverage can be limited by AIS reception gaps, mismatched source snapshots, identification errors or multiple independent polygons; the tool preserves ambiguity.

## Next gates

1. Verify with multiple authentic historical NOAA daily files and record source hashes, candidate counts and overlap distributions, without exporting raw vessel positions.
2. Assess geometry source date/scale/revision and obtain historical 2024 evidence independent of the current NOAA layer.
3. Independently evaluate against labeled operational records (issues #8 and #9), including precision, false positives, unknown proportion and timing errors.
4. Build a reference UI only after source/date limitations and the event's 'unvalidated' state are prominent in output contracts.

## First official-source engineering benchmark

The [2026-11-09 NOAA full-track overlay report](noaa-full-track-context-smoke-2026-11-09.md) records 920 real historical unvalidated candidate episodes, a comparison of 77 centroid-only overlaps versus 74 all-observed-point overlaps, 5 partial coverage cases and 841 no-overlap cases. All inputs/outputs were source-pinned by SHA-256. This is a geometric calculation and not evidence of confirmed historical anchoring.
