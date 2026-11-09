Schemas are **JSON Schema Draft 2020-12**, versioned by major directory. AIS point, stationary candidate and run manifest represent current prototype formats (CSV must be type-coerced to validate). Source snapshot is a proposed future contract. A new product or API must not claim schema conformance until serialized-output tests pass. Every event currently has confidence=unvalidated.

The SPEC-004 track-zone-evidence and track-zone-context-receipt contracts cover an **unverified geometric observation report**, never independently confirmed anchorage or berth/waiting events. Source receipt hashes are verified locally; authoritative source dates and reuse rights are NOT inferred.

SPEC-004 historical geometry documentary contracts: noaa-enc-documentary-evidence.schema.json and geometry-vintage-audit.schema.json. Both deliberately lack any status that could automatically approve historic polygons or operational maritime events.

The fr-official-text-triage.schema.json contract preserves source hashes and mandatory legal status NOT_DETERMINED for four official Federal Register Part 110 texts; keyword matching does not certify a section amendment or historical anchorage perimeter.

Serialized-output tests (`tests/test_contracts.py`) validate the real CLI exports: the run manifest as written, `stationary_candidates.csv` read back with `harborlens.ais.read_candidates_csv` (typed `duration_min`, `point_count`, `centroid_lon`, `centroid_lat`, `maximum_distance_m`) against `stationary-candidate.schema.json`, and each single-file GeoJSON Feature against `stationary-candidate-feature.schema.json`. Manifests carry `code_version`; the package version is part of `run_id`.
