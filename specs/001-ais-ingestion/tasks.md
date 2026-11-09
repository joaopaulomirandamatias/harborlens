# SPEC-001: Implementation Work Items

**State:** IMPLEMENTED — SYNTHETIC ONLY. Checking a task requires traceable PR/test evidence.

- [ ] Preserve synthetic unit tests and CLI smoke test
- [x] Add malformed input, ZIP expansion and finite-number tests; full memory benchmarks remain pending
- [ ] Implement output hashes and rights metadata
- [ ] Run a real NOAA archive or ERDDAP query after dataset rights review

## Review gate

- [ ] Acceptance criteria demonstrated
- [ ] Schema and requirements matrix updated
- [ ] Positive, negative and boundary tests pass
- [ ] Source rights and security reviewed
- [ ] No unsupported accuracy, emissions or customer claims

## Official subset adapter

- [x] Develop bounded NOAA PMEL ERDDAP client and mocked tests (on PR branch; review/CI pending).
- [ ] Demonstrate actual NOAA API response and ingestion with source SHA, data QA and a reproduction log.
