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

## Source rights register (issue #42, partial)

`docs/data/rights-register.json` is an engineering inventory, not a license grant. The published contract is `schemas/v1/source-rights-register.schema.json`. `harborlens.rights.load_registry` rejects registers that fail that schema, so complete reviewer fields cannot grant a schema-invalid file. Terms and evidence URLs must use scheme `https` and a non-empty host (`urllib.parse`).

`python -m harborlens.rights` prints JSON on stdout and exits 0 only for `reviewed_public_domain_attribution_required` or `reviewed_permitted_with_conditions`, 1 for every other status (`review_required`, `use_restricted`), and 2 on load, parse or schema failure. Exit 2 adds an `error` field. `rights_status_for` still returns `review_required` when the register cannot be read, so library callers fail closed. Checked-in sources stay `review_required`. Acquisition adapters do not read the gate. Issue #42 remains open.
