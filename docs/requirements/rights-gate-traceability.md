# SPEC-003 / Issue #42: Source rights review gate traceability

| Requirement | Increment delivered | Evidence | Remaining gate |
| --- | --- | --- | --- |
| FR-010: source provenance and rights | Version-scoped offline rights register, published schema and audit helper | `docs/data/rights-register.json`, `schemas/v1/source-rights-register.schema.json`, `src/harborlens/rights.py`, `tests/test_rights.py`, `tests/test_rights_cli.py`, `tests/test_rights_schema.py` | Independent owner and legal/source review. Optional adapter receipts are the follow-on below and are not an approval. The main requirements matrix does not yet list this gate under FR-010 (follow-up) |
| NFR-013: source confidentiality/reuse | No automatic grants; missing data, schema-invalid registers and invalid URLs fail closed. CLI exit 0 only for an approved status, exit 1 for pending/restricted, exit 2 for load/parse/schema errors (JSON `error` field). The schema is package data loaded with `importlib.resources`. Missing `jsonschema` exits 2 and names `pip install 'harborlens[rights]'` | `RightsGateTests.test_unknown_version_source_and_missing_register_fail_closed`, `test_schema_invalid_register_with_complete_evidence_is_not_granted`, `test_https_url_requires_scheme_and_host`, `test_parent_directory_schema_is_never_consulted`, `test_packaged_schema_matches_published_file`, `test_missing_jsonschema_names_rights_extra`, `RightsCLITests.test_exit_codes_and_json_shape`, `test_missing_jsonschema_error_names_rights_extra`, `tools/check_rights_wheel_install.sh` | Specific commercial redistribution terms and governance sign-off |
| NFR-019: use constraints | Explicit `research`, `public_aggregates` and `commercial` purposes; restricted use exits 1 and does not pass | `RightsGateTests.test_matching_reviewed_record_is_used`, `RightsCLITests.test_exit_codes_and_json_shape` | Record real decisions and attribution per source |
| BR-015/BR-016: approval authority | Complete evidence + version match + schema validation + https host + reviewer metadata required before a recorded grant | `RightsGateTests.test_review_evidence_is_required`, `test_checked_in_register_loads_and_grants_nothing` | Independent approval; a JSON record is NOT a cryptographic authorization or legal advice. No checked-in source is approved. Optional receipts do not grant redistribution |

## Acceptance / status

- **Implemented:** conservative registry, published schema enforced by `load_registry`, offline audit helper with fail-closed exit codes, synthetic positive/negative/boundary tests (including host-less `https` URLs and a schema-invalid register that still carries complete evidence), explicitly identified license evidence and unresolved source mismatch.
- **Not implemented:** independent human decision for any source, commercial licensing determination, data redistribution or historical geometry certification. No source has been approved.
- **Safety:** no event accuracy claims; no live navigation; no proprietary or raw data stored.
- **Validation:** run `python -m unittest discover -s tests -p 'test_rights.py' -v` in the project environment. PR CI is the authoritative integration check.

## Follow-on integration: source rights receipts

- **FR-010, NFR-013/NFR-019, BR-015/BR-016:** Four NOAA/USACE adapters now emit version/purpose-bound `rights_review` provenance. `rights_receipt` reads the register once and validates that buffer with the packaged schema (`importlib.resources` only). The SHA-256 and the decision come from that buffer. Exact dataset IDs or output/input SHA-256 digests prevent broad year/catalog assertions from being reused across mutable snapshots. A schema-invalid register is `invalid_registry` and `review_required`.
- **Verification:** `tests/test_rights_adapters.py` covers synthetic matching, mismatching, invalid registry, prohibited purpose, hash evidence, and the receipt schema. Existing acquisition tests remain applicable.
- **Residual gates:** independent reviewer and terms decisions; explicit enforcement at export/publication boundaries; independently verified dated geometry. No confirmed events or authorized distribution. Refs #42 (stays open).

## Aggregate release gate (SPEC-003)

- **FR-010 / BR-015 / BR-016 / NFR-013 / NFR-019:** one opt-in release command recomputes rights against the **current** local registry; source and run SHA-256 linkage, no-truncation checks, summary-only allowlist and exact-digest human review are required.
- **Evidence:** `src/harborlens/publication.py`, `tests/test_publication.py`, `schemas/v1/public-summary.schema.json`, `schemas/v1/publication-review.schema.json`.
- **Not delivered:** true legal approval, independent human privacy review of production content, source authenticity, anti-bypass policy for all local outputs, enterprise DLP or historical event validation.

## Signed review hardening (SPEC-003)

- **BR-015/BR-016, NFR-013/NFR-019:** release staging now demands signature verification against a reviewer public key whose SHA-256 fingerprint and identity are specified independently; unsigned/altered decisions are denied.
- **Evidence:** `src/harborlens/review_signatures.py`, `tests/test_review_signatures.py`, extended `tests/test_publication.py`, review/release schemas and `docs/data/signed-release-review.md`.
- **External governance still required:** secure private-key custody, pin-distribution, key revocation and authoritative rights/legal/privacy decisions; no certified operational claims.

## Release-summary recount and signed-review format (SPEC-003)

- **FR-010 / BR-015 / BR-016 / NFR-012 / NFR-013 / NFR-019:** retained observations and MMSI groups are recounted from verified `houston_clean.csv`. Disagreement with manifest `written` or `vessels`, a recount below 100 observations or 10 groups, a date-only review timestamp, a non-finite canonical number, a signature without the `harborlens.publication-review.v1` domain separator, or a missing `cryptography` import exits 2 and writes nothing. Fingerprints use `hmac.compare_digest`. The `cryptography` floor is `>=42.0.4`.
- **Evidence:** `src/harborlens/publication.py`, `src/harborlens/review_signatures.py`, `tests/test_publication.py` (99/100 observations, 9/10 MMSI groups, tampered manifest counts, date-only timestamp, non-finite number, legacy signature, mocked `ImportError`), `tests/test_review_signatures.py` (legacy signature rejected; tests skip without the extra).
- **Not delivered:** a real source-rights approval, anonymity, or any berth, anchorage, port-call, or accuracy claim. Refs #70. Refs #71. Refs #42 (stays open).
