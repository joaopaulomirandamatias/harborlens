# SPEC-003: Implementation Work Items

**State:** PARTIAL — local provenance, labeling and evaluation tooling; no labels collected. Checking a task requires traceable PR/test evidence.

- [ ] Ingest and checksum authorized NOAA sample
- [x] Output-hash and local-verification implementation (merged in #18)
- [ ] Independently confirm source rights and dataset provenance before distribution
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
