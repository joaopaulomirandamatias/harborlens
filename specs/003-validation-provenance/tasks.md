# SPEC-003: Implementation Work Items

**State:** PARTIAL — local provenance, labeling and evaluation tooling; no labels collected. Checking a task requires traceable PR/test evidence.

- [ ] Ingest and checksum authorized NOAA sample
- [x] Output-hash and local-verification implementation (merged in #18)
- [ ] Independently confirm source rights and dataset provenance before distribution. Partial inventory only (`docs/data/rights-register.json`, schema `source-rights-register`, `python -m harborlens.rights`): no source approved. Optional adapter receipts are listed below and do not approve a source. Refs #42 (stays open)
- [ ] Create annotation guide and >=100 pilot samples with negatives
- [ ] Implement metrics and confidence intervals
- [ ] Cross-validate independent period/port with permission

## Review gate

- [ ] Acceptance criteria demonstrated
- [ ] Schema and requirements matrix updated
- [ ] Positive, negative and boundary tests pass
- [ ] Source rights and security reviewed
- [ ] No unsupported accuracy, emissions or customer claims

## Labeling pilot tooling (issue #8)

- [x] Labeling protocol, label taxonomy and evidence levels (`docs/research/labeling-protocol.md`)
- [x] Seeded, blinded, stratified sampler with negatives and sampling manifest; agreement report; schemas and synthetic tests (`tests/test_labeling.py`)
- [x] Transceiver class stratum (`A`, `B`, `absent_or_unknown`) on `harborlens-label-sample`, schema `label-sample-v0.2`, synthetic positive/negative/boundary tests (`tests/test_labeling.py`, issue #65 code slice). Pilot annotation is still open.
- [ ] Draw the first pilot sample (≥100 units) from a source-pinned NOAA run, kept outside the public repository
- [ ] Two independent annotators label it; adjudicate disagreements; publish aggregate agreement only
- [ ] Evaluator against labels (#9)

## Evaluator (issue #9)

- [x] `harborlens-evaluate`, adjudicated-label and evaluation-report schemas, synthetic tests with hand-computed metrics (`tests/test_evaluation.py`)
- [ ] Evaluate the first adjudicated pilot (#8) and publish aggregate results only, with denominators and evidence basis
- [ ] Repeat on a different period or port (L4 replication)

## Source-rights adapter receipts (issue #42)

- [x] Integrate optional, conservative source-rights receipts for NOAA/USACE acquisition adapters with exact source/version/purpose and synthetic tests (pending independent PR review/CI).
- [ ] Obtain independent source-specific rights decisions and enforce them in export/publication workflows; registration alone is not permission.

## Aggregate-publication stage gate

- [x] Implement an opt-in, fail-closed summary-only staging command with live registry revalidation, source/run checksum chain, human release review and coarse suppression floors (pending PR CI and review).
- [x] Add synthetic attack-path tests, reviewed-release and summary schemas, and a publication-safety design note.
- [ ] Independent code/security review, real source-rights decisions and operational privacy governance before any public release.
- [ ] Separately address multi-day source lineage, signed approvals, organizational publication controls and third-party source authentication.

## Signed reviewer-attestation hardening

- [x] Add Ed25519 release approval verification, pinned SPKI fingerprint and expected reviewer ID; deny unsigned/mismatched claims (pending PR independent review and CI).
- [x] Add synthetic positive/negative cryptographic regression tests and updated JSON Schemas, CLI and signing documentation.
- [ ] Establish institution-controlled reviewer key custody, trust-root distribution, rotation and independent source-rights verification before real publication.

## Release-summary recount and signed-review format

- [x] Recount retained observations and MMSI groups from verified `houston_clean.csv`; deny when manifest `written` or `vessels` disagree; synthetic 99/100 and 9/10 boundary tests plus a tampered-count test (SPEC-003, FR-010, BR-015, BR-016, NFR-012).
- [x] Reject date-only `reviewed_at_utc` with exit 2, no traceback, and no release file.
- [x] Prefix Ed25519 review messages with `harborlens.publication-review.v1` and reject the previous signature bytes. Canonical release JSON rejects non-finite numbers.
- [x] Compare pinned SPKI fingerprints with `hmac.compare_digest`. Require `cryptography>=42.0.4` on the `release` and `dev` extras. Skip Ed25519 tests without that extra, and deny release when the import fails.
- [ ] Institution-controlled reviewer key custody, trust-root distribution, and a real source-rights approval remain external. Refs #42 (stays open).

## Independent aggregate-release verification

- [x] Add offline read-only `harborlens-verify-release` with pinned reviewer identity/SPKI fingerprint, pinned registry digest, explicit expected source/version/purpose, publisher canonical summary hash and strict field allowlist (SPEC-003, FR-010, BR-015, BR-016, NFR-013, NFR-019).
- [x] Verify the `0.2.0.dev5` signed-review format: domain separator `harborlens.publication-review.v1`, `allow_nan=False` canonical bytes shared with `summary_sha256` / `review_message`, and `hmac.compare_digest` fingerprints. Reject `0.2.0.dev4` signatures. Apply the recounted 100-observation and 10-group floors so a manifest scanned count cannot pass alone. Deny a date-only review timestamp and a missing `cryptography` import (exit 2, nothing written). Ed25519 tests use runtime keys, a lazy import, and `unittest.skipUnless`.
- [x] Exercise legitimate synthetic signed releases, producer interoperability after a cleaned-file recount, source/reviewer/report tampering, invalid/expired/date-only decisions, revoked rights, duplicate keys, weak aggregates, and dev4 signatures.
- [ ] Confirm CI and independent security/rights review; organize institutional trust distribution and revocation before any real publication. Refs #42 (stays open). Refs #70 (stays open). Refs #71 (stays open).
