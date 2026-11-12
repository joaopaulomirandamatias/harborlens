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

`harborlens-label-sample` (`src/harborlens/labeling.py`) reads one run directory, requires its artifact hashes to verify and its candidates to carry the manifest's `parameter_set`, and draws a seeded sample. Candidates are stratified by duration band × censoring status × vessel group × transceiver class (`A`, `B`, `absent_or_unknown`); negatives are maximal movement intervals (SOG above the run's threshold, gaps within the run's limit, at least 30 minutes) that do not overlap candidates, stratified by vessel group × transceiver class (`label-sample-v0.2`, FR-013, #65). A missing, blank or other non-A/B class is `absent_or_unknown` and the unit is kept. Each non-empty stratum gets at least one unit and the rest is allocated proportionally when the requested count is at least the number of non-empty strata. When the request is smaller, full cross-cell coverage is impossible and `stratification.all_non_empty_strata_drawn` is false. Every transceiver class present in that frame is still drawn if the request is at least as large as the number of those classes. The sheet has identical columns for both kinds and does not show class, kind or event id; the key, frame counts, allocation, seed and sheet hash live in `<sheet>.sampling.json` (`schemas/v1/label-sample.schema.json`). `harborlens-evaluate` parses each stratum with the manifest's `schema_version`. `label-sample-v0.2` requires that field count, a vessel group in `VESSEL_GROUPS` (`cargo`, `tanker`, `passenger`, `tug_or_service`, `other_or_unknown`), and transceiver class `A`, `B`, or `absent_or_unknown`. A `label-sample-v0.1` key is accepted only when the manifest says `label-sample-v0.1`. A damaged key, or a unit `kind` that is missing or disagrees with the stratum kind, raises `AISInputError` naming the `sample_id` instead of being counted as a vessel group or changing the confusion matrix. The CLI reports that error with a nonzero exit and no traceback. A transceiver-class cohort in the evaluation report remains future work (#9).

`harborlens-label-agreement` validates two completed sheets (`schemas/v1/label-record.schema.json` rules, one pseudonymous annotator per sheet, identical sample ids, L3 requires an `operational_record` source) and writes raw agreement, Cohen's kappa, the confusion matrix, unknown counts, evidence levels, optional by-kind results and all disagreements (`schemas/v1/label-agreement.schema.json`). It never reports precision or recall.

## Evaluator (issue #9)

`harborlens-evaluate` (`src/harborlens/evaluation.py`) requires the run's artifacts to verify and the sampling manifest's run hash and `parameter_set` to match the run. Candidates are the method's stationary predictions and sampled movement intervals its moving predictions; `at_berth`, `at_anchor` and `other_stationary` are true stationary, `maneuvering` and `transit` true moving. `mixed`, `unknown` and unlabeled units are excluded from the confusion matrix and reported under `coverage.excluded`.

The report (`schemas/v1/evaluation-report.schema.json`) gives TP/FP/FN/TN with precision, recall, F1 and specificity, Wilson 95% intervals, a design-weighted precision (each candidate stratum weighted by frame size over judged units), cohorts by evidence level, vessel group and candidate censoring, the label composition of candidates (berth vs anchor vs other), and boundary errors (predicted minus adjudicated start, end and duration; MAE and median) for true positives whose candidates are uncensored and whose duration is assessable. Recall only covers sampled movement intervals, not stops the method never segmented. `evidence_basis` states whether any L2 label was used.

## Source rights register (issue #42, partial)

`docs/data/rights-register.json` is an engineering inventory, not a license grant. The published contract is `schemas/v1/source-rights-register.schema.json`. The same bytes are packaged at `src/harborlens/schemas/v1/source-rights-register.schema.json` and `load_registry` reads them with `importlib.resources` only, so a schema sitting next to a virtualenv cannot replace the contract. A schema-invalid file is not granted, even when the reviewer fields are complete. Terms and evidence URLs must use scheme `https` and a hostname that is non-empty, has no whitespace, and is not only dots. `jsonschema` is the optional `rights` extra (`pip install 'harborlens[rights]'`). If it is missing, validation fails closed (CLI exit 2) and is not skipped. Core dependencies stay empty.

`python -m harborlens.rights` prints JSON on stdout and exits 0 only for `reviewed_public_domain_attribution_required` or `reviewed_permitted_with_conditions`, 1 for every other status (`review_required`, `use_restricted`), and 2 on load, parse or schema failure. Exit 2 adds an `error` field. `rights_status_for` still returns `review_required` when the register cannot be read, so library callers fail closed. Checked-in sources stay `review_required`. Optional adapter receipts are described below. Refs #42 (stays open).

## Incremental design: source-rights decisions in acquisition receipts

The optional `rights_receipt` function reads a bounded local registry once, validates that buffer with the same checks as `load_registry` (packaged schema via `importlib.resources` only; no parent-directory lookup), and fingerprints those same bytes. The path is not opened again. NOAA ERDDAP binds to `AIS2024_AIS`; local archives bind to their source-file digest; mutable USACE and NOAA polygon query results bind to canonical output hashes. No registry, or a missing, unmatched, malformed, or schema-invalid decision, yields `review_required`. This is audit metadata only, not export authorization. Historical validity, event truth and license verification remain independent controls. See `docs/data/rights-adapter-integration.md`.

## Aggregate-only publication staging (new, optional)

`harborlens-release-summary` verifies single-file run artifact SHA-256, source CSV SHA-256 against both the run and acquisition sidecar, exact source/version identity, completeness and conservative batch-size floors. Rights are evaluated *again* against the current registry for the requested public-aggregate or commercial purpose; the historical acquisition receipt never grants permission by itself. A deterministic proposed summary contains only a closed set of research-diagnostic counts and hashes. The local review must attest privacy, rights and scientific limitations for the **exact canonical summary fingerprint** within 30 days; license conditions need an extra attestation. Output is staged atomically, without overwriting, and is not uploaded anywhere. See `docs/data/aggregate-publication-gate.md` and `tests/test_publication.py`.

This local command is intentionally **not** a universal DLP mechanism: existing research CLIs still create local detailed artifacts, and independent legal and privacy review is required. Reviewer signatures for this command are specified below; source authentication is not yet implemented. Dataset scope is NOAA single-file AIS only, not dated geofences or multi-day labeling datasets.

## Signed release-review hardening (SPEC-003 incremental)

The local aggregate publication command now requires an Ed25519-signed review covering the canonical review claims, including the summary digest, purpose, reviewer ID, timestamp, human assertions, signature algorithm and the public-key fingerprint. The publisher independently provides the reviewer public key, its canonical SPKI-DER SHA-256 fingerprint and expected reviewer identity. The signature is verified before any output is staged, using the optional `cryptography` release dependency (`>=42.0.4`); missing/invalid/mismatched keys, a modified review or unsigned content fail closed. No private keys are generated, stored or imported by production HarborLens. See `docs/data/signed-release-review.md`. The local caller still controls trust inputs, so institutional trust-root distribution, dual control and signing-key custody remain external requirements.

## Release-summary recount and signed-review format (SPEC-003)

`harborlens-release-summary` recounts retained observations and distinct MMSI groups from the verified `houston_clean.csv` and applies the 100-observation and 10-group floors to that recount. Manifest `counts.written` and `events.vessels` must match; a disagreement exits 2 and writes nothing. Scanned `counts.total` is not in the cleaned file. It must still be at least 100 and at least the retained recount, and it cannot satisfy the floor alone. A date-only `reviewed_at_utc` (`2026-11-12` or `2026-11-12Z`, which parses to a naive datetime) is a validation failure: exit 2, no traceback, nothing written. Canonical release JSON uses `allow_nan=False`, so NaN and Infinity fail closed before any write.

The Ed25519 message is the domain separator `harborlens.publication-review.v1` plus a newline, then the canonical review JSON. Signatures from `0.2.0.dev4` are rejected. Pinned SPKI SHA-256 fingerprints are compared with `hmac.compare_digest`. Tests that need `cryptography` use `unittest.skipUnless` and a lazy import; a mocked `ImportError` on the release path becomes `ReviewSignatureError`, then `ReleaseDenied`, exit 2, and no file. Package version `0.2.0.dev5` is part of `run_id`. Refs #70. Refs #71. Refs #42 (stays open).

## Independent release verification (incremental)

`harborlens-verify-release` (`src/harborlens/release_verify.py`) accepts one staged aggregate JSON and externally pinned reviewer/rights evidence. It is read-only and requires no AIS source data. It reuses `publication.summary_sha256` and `review_signatures.verify_review_signature` rather than a second canonicalization. The summary digest is the publisher's `allow_nan=False` canonical bytes. The signature message is the `harborlens.publication-review.v1` domain separator plus the canonical review JSON; a `0.2.0.dev4` body-only signature is rejected. Fingerprints use `hmac.compare_digest` inside that shared verifier. Aggregate floors are `MIN_OBSERVATIONS` (100) and `MIN_VESSELS` (10), the same floors the publisher applies to a recount of `houston_clean.csv`. `observations_scanned` is the manifest total and cannot satisfy the floor by itself. A date-only `reviewed_at_utc` is rejected by the publisher's `_review_moment`. A missing `cryptography` import exits 2 and writes nothing.

The command rejects duplicate JSON keys and unknown fields, checks numerical conservation, review attestation and recency, then resolves the exact source/version/purpose against a registry whose SHA-256 must match a distinct expected digest. Optional externally known run and summary hashes reduce substitution risk. Output distinguishes **verified signed statements** from **unverified real-data claims**. The original AIS observations and the publisher's upstream checksum chain cannot be corroborated without the raw artifacts, and this command does not recount `houston_clean.csv` itself. See `docs/data/independent-release-verification.md` and `tests/test_release_verify.py`. Trust bootstrap, revocation, privacy review and enterprise DLP remain outside this command. Package version `0.2.0.dev6` is part of `run_id`. Refs #42 (stays open).
