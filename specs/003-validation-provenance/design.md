# SPEC-003: Technical Design

**State:** PARTIAL — local provenance, labeling and evaluation tooling; no labels collected

## Architecture and approach

Versioned source snapshot schema, label guide, stratified evaluation, provenance graph and immutable run references. No current real-event labels.

## Interfaces and contracts

- Python 3.10+; all timestamps RFC 3339 UTC, coordinates WGS84 lon/lat, units explicit.
- Version all public JSON payloads under `schemas/v1`; record method/version/parameters and data vintage.
- Use `unknown` or `unvalidated` when there is no independent evidence.
- No network, private integration or cloud dependency without explicit authorization and data license review.

## Decisions and tradeoffs

Refer to `docs/architecture/adr/`; prefer deterministic batch analysis, visible uncertainty and independent reproducibility over premature complex infrastructure. Schema-breaking changes require a migration note and regression tests.

## Labeling pilot tooling (issue #8)

`docs/research/labeling-protocol.md` defines the seven labels (`at_berth`, `at_anchor`, `other_stationary`, `maneuvering`, `transit`, `mixed`, `unknown`), evidence levels (L2 expert review of AIS; L3 independent operational record), censoring and fragmentation rules, double annotation and adjudication.

`harborlens-label-sample` (`src/harborlens/labeling.py`) reads one run directory, requires its artifact hashes to verify and its candidates to carry the manifest's `parameter_set`, and draws a seeded sample. Candidates are stratified by duration band × censoring status × vessel group; negatives are maximal movement intervals (SOG above the run's threshold, gaps within the run's limit, at least 30 minutes) that do not overlap candidates, stratified by vessel group. Each non-empty stratum gets at least one unit and the rest is allocated proportionally. The sheet has identical columns for both kinds; the key, frame counts, allocation, seed and sheet hash live in `<sheet>.sampling.json` (`schemas/v1/label-sample.schema.json`).

`harborlens-label-agreement` validates two completed sheets (`schemas/v1/label-record.schema.json` rules, one pseudonymous annotator per sheet, identical sample ids, L3 requires an `operational_record` source) and writes raw agreement, Cohen's kappa, the confusion matrix, unknown counts, evidence levels, optional by-kind results and all disagreements (`schemas/v1/label-agreement.schema.json`). It never reports precision or recall.

## Evaluator (issue #9)

`harborlens-evaluate` (`src/harborlens/evaluation.py`) requires the run's artifacts to verify and the sampling manifest's run hash and `parameter_set` to match the run. Candidates are the method's stationary predictions and sampled movement intervals its moving predictions; `at_berth`, `at_anchor` and `other_stationary` are true stationary, `maneuvering` and `transit` true moving. `mixed`, `unknown` and unlabeled units are excluded from the confusion matrix and reported under `coverage.excluded`.

The report (`schemas/v1/evaluation-report.schema.json`) gives TP/FP/FN/TN with precision, recall, F1 and specificity, Wilson 95% intervals, a design-weighted precision (each candidate stratum weighted by frame size over judged units), cohorts by evidence level, vessel group and candidate censoring, the label composition of candidates (berth vs anchor vs other), and boundary errors (predicted minus adjudicated start, end and duration; MAE and median) for true positives whose candidates are uncensored and whose duration is assessable. Recall only covers sampled movement intervals, not stops the method never segmented. `evidence_basis` states whether any L2 label was used.

## Incremental design: source-rights decisions in acquisition receipts

The optional `rights_receipt` function reads a bounded local registry once, checks a source/version/purpose-specific reviewer assertion, and fingerprints the exact bytes evaluated. NOAA ERDDAP binds to `AIS2024_AIS`; local archives bind to their source-file digest; mutable USACE and NOAA polygon query results bind to canonical output hashes. No registry or a missing/unmatched/malformed decision yields `review_required`. This is audit metadata only, not export authorization. Historical validity, event truth and license verification remain independent controls. See `docs/data/rights-adapter-integration.md`.

## Aggregate-only publication staging (new, optional)

`harborlens-release-summary` verifies single-file run artifact SHA-256, source CSV SHA-256 against both the run and acquisition sidecar, exact source/version identity, completeness and conservative batch-size floors. Rights are evaluated *again* against the current registry for the requested public-aggregate or commercial purpose; the historical acquisition receipt never grants permission by itself. A deterministic proposed summary contains only a closed set of research-diagnostic counts and hashes. The local review must attest privacy, rights and scientific limitations for the **exact canonical summary fingerprint** within 30 days; license conditions need an extra attestation. Output is staged atomically, without overwriting, and is not uploaded anywhere. See `docs/data/aggregate-publication-gate.md` and `tests/test_publication.py`.

This local command is intentionally **not** a universal DLP mechanism: existing research CLIs still create local detailed artifacts, independent legal and privacy review is required, and signatures/source authentication are not yet implemented. Dataset scope is NOAA single-file AIS only, not dated geofences or multi-day labeling datasets.
