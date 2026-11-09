# Canonical Data Dictionary

| Entity | Fields | Meaning |
| --- | --- | --- |
| Clean AIS point | mmsi, timestamp_utc, lat, lon, sog_knots, vessel_type, nav_status | Transmitted observation; not verified vessel identity |
| Stationary candidate | event_id, mmsi, start_utc, end_utc, duration_min, point_count, centroid_lon, centroid_lat, maximum_distance_m, type, method_version, confidence_label, left_censoring, right_censoring | Low-speed contiguous AIS sequence, not confirmed anchorage or berth. `left_censoring`/`right_censoring` ∈ {censored, not_censored, unknown} (BR-019); `censored` means `duration_min` is a lower bound |
| Run manifest | input_file, input_sha256, bbox_lon_lat, counts, events (including `censoring` counts), method_parameters, analysis_window, input_truncated | Provenance and QA counters for current prototype. `analysis_window` records window blocks, how each was declared, internal gaps and the observed time range |
| Source snapshot (planned) | source_id, agency, url, dataset_version, retrieved_at_utc, file_sha256, license_status | Origin and rights for future data lineage |

Time is RFC 3339 UTC; positions are decimal WGS84 degrees with longitude first in GeoJSON; SOG is knots, distance meters, duration minutes. Identifier MMSI is not a stable guaranteed vessel identity. All candidate confidence is **unvalidated** pending expert labeling and official event comparison.
