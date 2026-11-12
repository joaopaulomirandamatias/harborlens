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
- [x] Signed reviewer approvals for aggregate release (Ed25519, pinned SPKI fingerprint, `hmac.compare_digest` on pinned digests). Evidence: `src/harborlens/review_signatures.py`, `src/harborlens/publication.py`, `src/harborlens/release_verify.py`, `tests/test_review_signatures.py`. Institutional key custody remains open.
- [ ] Separately address multi-day source lineage, organizational publication controls and third-party source authentication.

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

## Single-buffer recount, size ceiling and constant-time pins

- [x] Read `houston_clean.csv` once into a bounded buffer, hash those bytes, compare them to the manifest, and recount from the same bytes. No second open (SPEC-003, FR-010, NFR-012).
- [x] Deny a cleaned file above `MAX_CLEANED_RECOUNT_BYTES` (256 MiB, the archive-extraction and track-context output ceiling). The read asks for ceiling + 1 bytes. Exit 2, nothing written.
- [x] Boundary tests for a stale manifest hash, stale counts at the 100-observation and 10-group boundaries, one open, and the size ceiling at exact size and one byte over. Recount tests that do not need a signature are not gated on `cryptography`.
- [x] Compare pinned digests, hashes, fingerprints and parameter-set pins with `hmac.compare_digest` on normalized lowercase hex or equal-typed bytes. A mismatched digest exits 2.
- [x] Document that `harborlens-verify-release` does not recount the cleaned CSV. Refs #70 (stays open). Refs #71 (stays open). Refs #42 (stays open).

## Release-summary residuals: tolerance, single evaluation, docs, packaged schemas

- [x] Document the fixed 5-minute future clock-skew allowance and the 30-day maximum age for `reviewed_at_utc` in the CLI help, CLI docs, and SPEC-003. The allowance is not a configuration knob (SPEC-003, FR-010, BR-015, BR-016).
- [x] `harborlens-release-summary` calls `prepare_summary` / `rights_receipt` once and stages that summary. Synthetic call-count test on the dry-run and staging paths.
- [x] README and `schemas/README.md` name `harborlens-release-summary`, `harborlens-verify-release`, and the public-summary, publication-review, and release-verification-result schemas.
- [x] Package those three schemas in the wheel and sdist. Load them with `importlib.resources` only. Refuse any other name. A schema next to the package is not consulted. The GovInfo LSA schema stays unpackaged.
- [x] Deny a release summary whose `rights_status` is missing, `None`, not a string, or outside the approved-status allowlist (`ReleaseDenied`, CLI exit 2, nothing written). Absolute paths, backslashes, percent-encoding, uppercase names, NUL bytes, `..` segments, and trailing whitespace are refused by the schema loader before any filesystem read. CLI review-window edges use a frozen clock: exactly 30 days old and exactly 5 minutes ahead are accepted; one second outside either edge is rejected.
- [ ] Institution-controlled reviewer key custody, a real source-rights approval, and a streaming recount for a cleaned CSV above the fixed 256 MiB ceiling remain external. This list does not add a streaming reader. Refs #70 (stays open). Refs #42 (stays open).

## Rights-register parsing and sidecar schemas

- [x] Name a UTF-8 BOM as a load error and do not treat that file as an approved status (SPEC-003, FR-010, NFR-013, BR-015, BR-016). YAML, case and whitespace variants, and whitespace-only evidence fail closed.
- [x] Align `reviewed_at_utc` in `source-rights-register.schema.json` with `_valid_utc_time`: ASCII `YYYY-MM-DDTHH:MM:SS` with no fraction or 1 to 6 digits, then `Z` or `+00:00`. The clock is built from the captured fields. A non-calendar shape stays `review_required`.
- [x] Reject trailing whitespace, IPv6 literals, and raw IDN hostnames in the schema pattern and the parser. Punycode stays accepted. Document that restriction.
- [x] Record the rights register as its own FR-010 row in `docs/requirements/traceability.md` and document `source-rights-register` in `schemas/README.md`.
- [x] Publish `erddap-ais-source` and `noaa-archive-extract-source` schemas, including optional `rights_review`, and keep the checked-in register at `review_required` for every adapter (NFR-010). Those schemas stay unpackaged.
- [x] CI already runs the rights wheel step with `actions/checkout@v7` and `actions/setup-python@v7`, the same pins as the rest of `.github/workflows/ci.yml`. No workflow edit was required.
- [ ] Independent source-rights approval remains external. Refs #42 (stays open). Refs #67 (stays open). Refs #69 (stays open). Issue #68 stays open because one sample digest cannot pass on both Python 3.10 and 3.12 while `random.sample` differs.
