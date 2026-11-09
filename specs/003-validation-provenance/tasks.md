# SPEC-003: Implementation Work Items

**State:** PROPOSED. Checking a task requires traceable PR/test evidence.

- [ ] Ingest and checksum authorized NOAA sample
- [ ] Review and merge output-hash and local-verification implementation (PR pending)
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

- [x] Add optional, fail-closed source-rights receipts to the four NOAA/USACE acquisition adapters, with exact source/version/purpose and synthetic tests (implementation pending independent PR review/CI).
- [ ] Verify real source-specific rights decisions and implement release/export enforcement separately; registration alone is not a license grant.
