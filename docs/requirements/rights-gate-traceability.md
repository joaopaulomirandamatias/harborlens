# SPEC-003 / Issue #42: Source rights review gate traceability

| Requirement | Increment delivered | Evidence | Remaining gate |
| --- | --- | --- | --- |
| FR-010: source provenance and rights | Version-scoped offline rights register, published schema and audit helper. BOM, timestamp shape, and URL shape fail closed. ERDDAP and archive-extract sidecars have published schemas | `docs/data/rights-register.json`, `schemas/v1/source-rights-register.schema.json`, `schemas/v1/erddap-ais-source.schema.json`, `schemas/v1/noaa-archive-extract-source.schema.json`, `src/harborlens/rights.py`, `tests/test_rights.py`, `tests/test_rights_cli.py`, `tests/test_rights_schema.py`, `tests/test_rights_adapters.py` | Independent owner and legal/source review. Optional adapter receipts are not an approval. The main requirements matrix lists this gate on its own FR-010 row |
| NFR-013: source confidentiality/reuse | No automatic grants; missing data, schema-invalid registers and invalid URLs fail closed. CLI exit 0 only for an approved status, exit 1 for pending/restricted, exit 2 for load/parse/schema errors (JSON `error` field). The schema is package data loaded with `importlib.resources`. Missing `jsonschema` exits 2 and names `pip install 'harborlens[rights]'` | `RightsGateTests.test_unknown_version_source_and_missing_register_fail_closed`, `test_schema_invalid_register_with_complete_evidence_is_not_granted`, `test_https_url_requires_scheme_and_host`, `test_parent_directory_schema_is_never_consulted`, `test_packaged_schema_matches_published_file`, `test_missing_jsonschema_names_rights_extra`, `RightsCLITests.test_exit_codes_and_json_shape`, `test_missing_jsonschema_error_names_rights_extra`, `tools/check_rights_wheel_install.sh` | Specific commercial redistribution terms and governance sign-off |
| NFR-019: use constraints | Explicit `research`, `public_aggregates` and `commercial` purposes; restricted use exits 1 and does not pass | `RightsGateTests.test_matching_reviewed_record_is_used`, `RightsCLITests.test_exit_codes_and_json_shape` | Record real decisions and attribution per source |
| BR-015/BR-016: approval authority | Complete evidence + version match + schema validation + https host + reviewer metadata required before a recorded grant | `RightsGateTests.test_review_evidence_is_required`, `test_checked_in_register_loads_and_grants_nothing` | Independent approval; a JSON record is NOT a cryptographic authorization or legal advice. No checked-in source is approved. Optional receipts do not grant redistribution |

## Acceptance / status

- **Implemented:** conservative registry, published schema enforced by `load_registry`, offline audit helper with fail-closed exit codes, synthetic positive/negative/boundary tests (including host-less `https` URLs and a schema-invalid register that still carries complete evidence), explicitly identified license evidence and unresolved source mismatch.
- **Not implemented:** independent human decision for any source, commercial licensing determination, data redistribution or historical geometry certification. No source has been approved.
- **Parsing (FR-010, NFR-013, NFR-019, BR-015, BR-016):** a UTF-8 BOM is a named load error and is not an approval. `reviewed_at_utc` must match the schema timestamp pattern and be a real UTC time. ASCII https URLs only; punycode works; IPv6 literals, raw IDN, userinfo, and trailing whitespace do not. Evidence: `RightsGateTests.test_utf8_bom_is_a_named_load_error_and_not_approved`, `test_yaml_register_fails_closed`, `test_case_and_whitespace_variants_do_not_grant`, `test_whitespace_only_evidence_does_not_grant`, `test_trailing_whitespace_and_non_ascii_urls_do_not_grant`, `test_reviewed_at_must_be_a_real_utc_timestamp`, `test_checked_in_register_loads_and_grants_nothing` (5 sources × 3 purposes). Refs #67 (stays open). Refs #42 (stays open).
- **Sidecar schemas (FR-010, NFR-010):** `erddap-ais-source.schema.json` and `noaa-archive-extract-source.schema.json` are published and are not packaged. `RightsAdapterTests.test_official_register_does_not_grant_adapter_rights` validates the official-register sidecars and keeps every adapter at `review_required`. Refs #69 (stays open).
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

## Independent signed-release verification (SPEC-003)

- **FR-010 / BR-015, BR-016 / NFR-013, NFR-019:** `harborlens-verify-release` re-evaluates source rights under an externally pinned registry fingerprint, validates the domain-separated Ed25519 review (`harborlens.publication-review.v1`, `allow_nan=False`, `hmac.compare_digest`) against an independently pinned key and identity, and applies the recounted 100-observation and 10-group floors. A manifest scanned count cannot satisfy those floors alone. A `0.2.0.dev4` signature, a date-only timestamp, and a missing `cryptography` import fail closed (exit 2, nothing written). The check does not read AIS.
- **Evidence:** `src/harborlens/release_verify.py`, `tests/test_release_verify.py`, `schemas/v1/release-verification-result.schema.json`, `docs/data/independent-release-verification.md`, and the producer interoperability test in `tests/test_publication.py`.
- **Residual:** upstream AIS truth, independent legal permission, privacy risk, revocation, trusted key registry, authentic rights-register signer, and organization-wide release enforcement remain open. Refs #42 (stays open). Refs #70 (stays open). Refs #71 (stays open).

## Single-buffer recount and constant-time pins (SPEC-003)

- **FR-010 / BR-015 / BR-016 / NFR-012 / NFR-013 / NFR-019:** `harborlens-release-summary` reads `houston_clean.csv` once. The manifest SHA-256 check and the retained-observation / MMSI-group recount use that buffer. The read stops at 256 MiB + 1 byte. A larger file, a stale manifest hash, a stale count, or a mismatched pinned digest exits 2 and writes nothing. Comparisons use `hmac.compare_digest`. `rights_receipt` does not compare two digests; the rights-register pin is compared in `release_verify.py`.
- **Known limitation:** `harborlens-verify-release` does not recount the CSV. The Ed25519 review attests the counts. `verification_scope` stays `signed_release_and_pinned_rights_only`. A signed retained count inflated above the 100/10 floors is not detectable without the file. Anyone holding `houston_clean.csv` must recount on the release path.
- **Evidence:** `src/harborlens/publication.py`, `src/harborlens/release_verify.py`, `src/harborlens/provenance.py`, `tests/test_publication.py`, `tests/test_provenance.py`, `docs/data/independent-release-verification.md`. Package `0.2.0.dev7` is part of `run_id`. No source is approved. Refs #70 (stays open). Refs #71 (stays open). Refs #42 (stays open).

## Review-clock tolerance, single evaluation, and packaged release schemas (SPEC-003)

- **FR-010 / NFR-010 / NFR-012 / NFR-013 / NFR-019 / BR-015 / BR-016:** `reviewed_at_utc` must be an RFC3339 UTC date-time inside a fixed window: not older than 30 days and not more than 5 minutes ahead of the checker clock. The 5 minutes are clock skew, not a setting. `harborlens-release-summary` calls `prepare_summary` once and stages that summary. `rights_receipt` therefore runs once on that path. `public-summary.schema.json`, `publication-review.schema.json`, and `release-verification-result.schema.json` ship in the wheel and sdist and load with `importlib.resources` only.
- **Evidence:** `tests/test_publication.py`, `tests/test_release_verify.py`, `tests/test_packaged_release_schemas.py`, `tools/check_release_schema_wheel_install.sh`, `README.md`, `schemas/README.md`. That slice identified runs as `0.2.0.dev9`. The current package is `0.2.0.dev12`; `run_id` still hashes the package version. The release path is unchanged in this slice. No source is approved. Refs #70 (stays open). Refs #42 (stays open).
