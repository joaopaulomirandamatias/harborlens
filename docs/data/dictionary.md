# Canonical Data Dictionary

| Entity | Fields | Meaning |
| --- | --- | --- |
| Clean AIS point | mmsi, timestamp_utc, lat, lon, sog_knots, vessel_type, nav_status | Transmitted observation; not verified vessel identity |
| Stationary candidate | event_id, mmsi, start_utc, end_utc, duration_min, point_count, centroid_lon, centroid_lat, maximum_distance_m, type, method_version, parameter_set, confidence_label, left_censoring, right_censoring | Low-speed contiguous AIS sequence, not confirmed anchorage or berth. `left_censoring`/`right_censoring` ∈ {censored, not_censored, unknown} (BR-019); `censored` means `duration_min` is a lower bound |
| Run manifest | input_file, input_sha256, bbox_lon_lat, counts, events (split reasons, `discarded_by_reason`, `candidates_per_mmsi`, `censoring` counts), method_parameters (thresholds, `method_version`, `parameter_set`), analysis_window, input_truncated | Provenance and QA counters for current prototype. `analysis_window` records window blocks, how each was declared, internal gaps and the observed time range |
| Source snapshot (planned) | source_id, agency, url, dataset_version, retrieved_at_utc, file_sha256, license_status | Origin and rights for future data lineage |

Time is RFC 3339 UTC; positions are decimal WGS84 degrees with longitude first in GeoJSON; SOG is knots, distance meters, duration minutes. Identifier MMSI is not a stable guaranteed vessel identity. All candidate confidence is **unvalidated** pending expert labeling and official event comparison.

In `stationary_candidates.csv`, `duration_min`, `centroid_lon`, `centroid_lat` and `maximum_distance_m` are decimals and `point_count` is an integer; `harborlens.ais.read_candidates_csv` returns typed records. Manifests carry `code_version` (`package_version`, which is part of `run_id`, and `git_commit` when known from CI).

`method_version` is `stationary-v0.2` for both commands. `parameter_set` is a 12-hex fingerprint of the method version and thresholds; candidate GeoJSON files also carry the full thresholds in a top-level `harborlens_method` member. A threshold-sensitivity report (`schemas/v1/sensitivity-report.schema.json`) lists counts per setting and is descriptive only.
