# SPEC-003 / Issue #42: Source rights review gate traceability

| Requirement | Increment delivered | Evidence | Remaining gate |
| --- | --- | --- | --- |
| FR-010: source provenance and rights | Version-scoped offline rights register and audit helper | `docs/data/rights-register.json`, `src/harborlens/rights.py`, `tests/test_rights.py` | Independent owner and legal/source review; automatic source-adapter use in a separate tested change |
| NFR-013: source confidentiality/reuse | No automatic grants; missing data and invalid register fail closed | `RightsGateTests.test_unknown_version_source_and_missing_register_fail_closed` and duplicate/invalid tests | Specific commercial redistribution terms and governance sign-off |
| NFR-019: use constraints | Explicit `research`, `public_aggregates` and `commercial` purposes; restricted use does not pass | `RightsGateTests.test_matching_reviewed_record_is_used` | Record real decisions and attribution per source |
| BR-015/BR-016: approval authority | Complete evidence + version match + reviewer metadata required for recorded decisions | `RightsGateTests.test_review_evidence_is_required` | Independent approval; a JSON record is NOT a cryptographic authorization or legal advice |

## Acceptance / status

- **Implemented:** conservative registry, offline audit helper, synthetic positive/negative/boundary tests, explicitly identified license evidence and unresolved source mismatch.
- **Not implemented:** independent human decision for any source, adapter integrations, commercial licensing determination, data redistribution or historical geometry certification.
- **Safety:** no event accuracy claims; no live navigation; no proprietary or raw data stored.
- **Validation:** run `python -m unittest tests.test_rights -v` in the project environment. PR CI is the authoritative integration check.
