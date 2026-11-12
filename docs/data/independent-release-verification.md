# Independently inspect a signed aggregate release (SPEC-003)

**Status:** experimental, offline report verification. **No raw AIS or live network access is needed.** The command verifies the consistency of signed statements under externally supplied trust anchors; it does **not** establish accurate vessel events, a legal license, anonymity, or authentic upstream observations.

## Why a separate verifier?

`harborlens-release-summary` checks the original NOAA source, its acquisition receipt, the research run, a recount of `houston_clean.csv`, and the registry before it writes a small summary. The review is an Ed25519 signature over the domain separator `harborlens.publication-review.v1` plus the canonical review JSON. A third party receiving only the staged JSON should be able to check whether the file changed, whether a specified reviewer signed the precise summary and purpose, and whether a **separately trusted** rights-register snapshot permits that same purpose.

`harborlens-verify-release` implements that separate, read-only check. It does not import an AIS file, fetch NOAA services, rebuild port events, sign anything, or publish to the Internet. It calls `summary_sha256` and `verify_review_signature`, so the canonical bytes and the fingerprint comparison (`hmac.compare_digest`) are the publisher's. A signature from `0.2.0.dev4` that omits the domain separator is rejected.

## Independent trust requirements

Before inspecting an untrusted release, acquire these **independently of the release itself**:

1. A reviewed rights-register JSON snapshot **and its SHA-256 fingerprint from an authenticated governance channel**. Do not accept the fingerprint printed inside the untrusted release as your independent trust anchor.
2. An authorized reviewer's public Ed25519 key, its **DER SubjectPublicKeyInfo SHA-256 fingerprint**, and expected reviewer ID, all from a separately governed trust registry. A key that accompanies the report without out-of-band verification is insufficient.
3. The intended `purpose`, `source_id` and `dataset_version` of the study. An expected `run_id` and `summary_sha256` from the request/approval record are strongly recommended.

The checked-in `docs/data/rights-register.json` contains **no approved source**, so it will not verify a real public/commercial release. Synthetic approved registry entries exist **only in tests**.

## Offline usage

```bash
python -m pip install -e '.[release]'

harborlens-verify-release \
  --release local/public-summary.json \
  --rights-register trusted/approved-rights-register.json \
  --expected-rights-register-sha256 VERIFIED_64_HEX_REGISTRY_DIGEST \
  --trusted-reviewer-key trusted/reviewer-public.pem \
  --trusted-reviewer-key-sha256 VERIFIED_64_HEX_SPKI_DIGEST \
  --trusted-reviewer-id approved-reviewer \
  --purpose public_aggregates \
  --source-id noaa_pmel_erddap \
  --dataset-version AIS2024_AIS \
  --run-id VERIFIED_64_HEX_RUN_ID \
  --expected-summary-sha256 VERIFIED_64_HEX_SUMMARY_DIGEST
```

The final two flags are optional when external scope references are unavailable; the report's signed claims are still checked, but the verification is weaker against substitution of a different, otherwise valid report. Every successful result has `verified: true` and **`verification_scope: signed_release_and_pinned_rights_only`**. It reports file and summary hashes, source/version, purpose and reviewer identity with an explicit warning that original AIS truth and source authenticity were not checked. Any failed check exits with code 2 and emits no success record.

The release must have the exact allowlisted structure of [the public-summary schema](../../schemas/v1/public-summary.schema.json). The verifier rejects duplicated JSON keys, non-finite values, unexpected payload fields, raw-record additions, invalid integer counts, date-only review timestamps, and false operational labels. It recomputes the canonical summary SHA-256 with `allow_nan=False`; checks that the signed reviewer attestation binds to the same digest/purpose, is an RFC3339 UTC date-time not older than 30 days and not more than 5 minutes ahead of the checker clock, and has all mandatory acknowledgments; verifies its Ed25519 signature with the pinned identity and key fingerprint; and re-evaluates the exact source/vintage/purpose under the independently pinned registry bytes. The 5 minutes are the same fixed clock-skew allowance `harborlens-release-summary` uses (`review_timestamp_is_current`). They are not a configuration knob. Retained observations must be at least 100 and MMSI groups at least 10, the same floors `harborlens-release-summary` applies to a recount of `houston_clean.csv`. A larger scanned count copied from a manifest does not pass by itself. This command does not re-read that CSV; without the original file it cannot detect an inflated count that still meets the floors.

The output contract is [release-verification-result.schema.json](../../schemas/v1/release-verification-result.schema.json). That file, `public-summary.schema.json`, and `publication-review.schema.json` are byte-identical copies under `src/harborlens/schemas/v1/` and load from the installed package with `importlib.resources`.

## Threat model and limitations

| Threat | Enforced defense | Unsolved boundary |
| --- | --- | --- |
| Edited count, source, method or label | Strict allowlist, publisher canonical summary SHA-256, signed exact digest, recounted 100/10 floors | Cannot independently re-count missing original AIS; a manifest scanned count is not trusted alone, but an inflated retained count above the floor is not detectable without the CSV |
| Self-signed malicious reviewer key | Out-of-band pinned SPKI hash and expected reviewer ID | External authority, key eligibility and revocation must be governed |
| Rights registry swapped or revoked | Separately pinned registry SHA-256 and live purpose/version lookup | Registry approval is still an assertion, not an audited legal opinion |
| Signed release reused for another purpose | Caller-specified purpose/source/version; optionally expected run and summary hashes | Same release replay in the same scope before expiry is possible |
| Low-count disclosure or injected record | Coarse fixed numeric summary, minimum cohort counts and no unapproved fields | Thresholds do not guarantee privacy or prevent linkage attacks |
| Edited signature or missing attestation | Domain-separated Ed25519 verification, `hmac.compare_digest` fingerprints, exact signed-field contract and human review flags. `0.2.0.dev4` signatures and a missing `cryptography` install fail closed | No organizational dual-control, immutable audit store or policy engine |

**Independent technical review still required before production:** check trust-anchor distribution, registry review and revocation, source-provenance authenticity, disclosure/privacy analysis, review lifecycle, local file ownership and retention, race conditions between review and release, and the ability of other workflows to bypass this narrow command. This verifier is a supplementary control, not a universal data-loss-prevention system.

## Known limitation

`harborlens-verify-release` does not recount the cleaned AIS CSV. The Ed25519 review attests the counts as checked by the reviewer on the release path. Every successful result has `verification_scope=signed_release_and_pinned_rights_only`. A signed retained count inflated above the 100-observation and 10-MMSI-group floors is not detectable by this verifier without the CSV. Anyone holding `houston_clean.csv` must recount through the release path (`harborlens-release-summary`). That path reads the file once, checks SHA-256 of those bytes against the manifest, and recounts from the same buffer. The buffer is capped at 256 MiB.

A later slice can recount a longer cleaned CSV without holding the file: one read, an incremental SHA-256 over those chunks, and a streamed row and MMSI recount of the same chunks, with the distinct-MMSI set capped. That proposal is in the SPEC-002 design. This command and `harborlens-release-summary` do not implement it. Refs #70 (stays open).

## Test evidence

`tests/test_release_verify.py` contains offline synthetic fixtures for correct verification, a byte-identical canonical message with `review_message`, rejection of a `0.2.0.dev4` signature, altered summary, wrong purpose/source/year, swapped key, stale and date-only review, rights revocation, malformed and duplicate-key JSON, unexpected raw fields, low-count exports (including a high scanned count with a retained count below the recounted floor), CLI scope, and a missing `cryptography` import (exit 2, nothing written). `tests/test_publication.py` verifies interoperability using a report produced by `release_summary` from synthetic AIS after the cleaned-file recount. Ed25519 tests generate keys at runtime and skip with `unittest.skipUnless` when the extra is absent. Recount, stale-manifest, single-open and size-ceiling tests do not need a signature and are not skipped when `cryptography` is absent. A mismatched summary digest exits 2.

Run `python -m unittest discover -s tests -v` with `.[noaa,dev,geo,rights]`. No private key or real AIS is committed. The `release` and `dev` extras require `cryptography>=42.0.4`.

**NOT FOR NAVIGATION. No real dataset redistribution approval is implied.**
