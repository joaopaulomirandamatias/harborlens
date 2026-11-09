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
- **Validation:** run `python -m unittest discover -s tests -p 'test_rights.py' -v` in the project environment. PR CI is the authoritative integration check.

## Follow-on integration: source rights receipts (dependent on #55)

- **FR-010, NFR-013/NFR-019, BR-015/BR-016:** Four NOAA/USACE adapters now emit version/purpose-bound `rights_review` provenance using the local registry. Exact dataset IDs or output/input SHA-256 digests prevent broad year/catalog assertions from being automatically reused across mutable snapshots.
- **Verification:** `tests/test_rights_adapters.py` covers synthetic matching, mismatching, invalid registry, prohibited purpose, hash evidence, and new versioned receipt schema. Existing acquisition tests remain applicable.
- **Residual gates:** PR review and CI; independent actual reviewer/terms; explicit enforcement at export/publication boundaries; independently verified dated geometry. No confirmed events or authorized distribution.

## Aggregate release gate (SPEC-003; stacked on #55 → #60)

- **FR-010 / BR-015 / BR-016 / NFR-013 / NFR-019:** one opt-in release command recomputes rights against the **current** local registry; source and run SHA-256 linkage, no-truncation checks, summary-only allowlist and exact-digest human review are required.
- **Evidence:** `src/harborlens/publication.py`, `tests/test_publication.py`, `schemas/v1/public-summary.schema.json`, `schemas/v1/publication-review.schema.json`.
- **Not delivered:** true legal approval, independent human privacy review of production content, source authenticity, anti-bypass policy for all local outputs, enterprise DLP or historical event validation.

## Signed review hardening (SPEC-003; stacked after #61)

- **BR-015/BR-016, NFR-013/NFR-019:** release staging now demands signature verification against a reviewer public key whose SHA-256 fingerprint and identity are specified independently; unsigned/altered decisions are denied.
- **Evidence:** `src/harborlens/review_signatures.py`, `tests/test_review_signatures.py`, extended `tests/test_publication.py`, review/release schemas and `docs/data/signed-release-review.md`.
- **External governance still required:** secure private-key custody, pin-distribution, key revocation and authoritative rights/legal/privacy decisions; no certified operational claims.

## Independent signed-release verification (SPEC-003; stacked after #62)

- **FR-010 / BR-015, BR-016 / NFR-013, NFR-019:** the verifier re-evaluates source rights under an externally pinned registry fingerprint, validates signed human review against independently pinned key/identity, and recomputes the allowlisted aggregate digest without AIS data.
- **Evidence:** `src/harborlens/release_verify.py`, `tests/test_release_verify.py`, `schemas/v1/release-verification-result.schema.json`, `docs/data/independent-release-verification.md`, and real-producer synthetic interoperability test in `tests/test_publication.py`.
- **Residual:** upstream AIS truth, independent legal permission, privacy risk, revocation, trusted key registry, authentic rights-register signer, and organization-wide release enforcement remain open.
