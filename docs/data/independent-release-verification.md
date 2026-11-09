# Independently inspect a signed aggregate release (SPEC-003)

**Status:** experimental, offline report verification. **No raw AIS or live network access is needed.** The command verifies the consistency of signed statements under externally supplied trust anchors; it does **not** establish accurate vessel events, a legal license, anonymity, or authentic upstream observations.

## Why a separate verifier?

The local release command in PR #61 checks the original NOAA source, its acquisition receipt, the research run and the registry before it writes a small summary. PR #62 adds an Ed25519-signed reviewer decision. A third party receiving only the staged JSON should be able to check whether the file changed, whether a specified reviewer signed the precise summary and purpose, and whether a **separately trusted** rights-register snapshot permits that same purpose.

`harborlens-verify-release` implements that separate, read-only check. It does not import an AIS file, fetch NOAA services, rebuild port events, sign anything, or publish to the Internet.

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

The release must have the exact allowlisted structure of [the public-summary schema](../../schemas/v1/public-summary.schema.json). The verifier rejects duplicated JSON keys, non-finite values, unexpected payload fields, raw-record additions, invalid integer counts and false operational labels. It recomputes the canonical summary SHA-256; checks that the signed reviewer attestation binds to the same digest/purpose, is within 30 days and has all mandatory acknowledgments; verifies its Ed25519 signature with the pinned identity and key fingerprint; and re-evaluates the exact source/vintage/purpose under the independently pinned registry bytes.

The output contract is [release-verification-result.schema.json](../../schemas/v1/release-verification-result.schema.json).

## Threat model and limitations

| Threat | Enforced defense | Unsolved boundary |
| --- | --- | --- |
| Edited count, source, method or label | Strict allowlist, canonical summary SHA-256, signed exact digest | Cannot independently re-count missing original AIS |
| Self-signed malicious reviewer key | Out-of-band pinned SPKI hash and expected reviewer ID | External authority, key eligibility and revocation must be governed |
| Rights registry swapped or revoked | Separately pinned registry SHA-256 and live purpose/version lookup | Registry approval is still an assertion, not an audited legal opinion |
| Signed release reused for another purpose | Caller-specified purpose/source/version; optionally expected run and summary hashes | Same release replay in the same scope before expiry is possible |
| Low-count disclosure or injected record | Coarse fixed numeric summary, minimum cohort counts and no unapproved fields | Thresholds do not guarantee privacy or prevent linkage attacks |
| Edited signature or missing attestation | Ed25519 verification, exact signed-field contract and human review flags | No organizational dual-control, immutable audit store or policy engine |

**Independent technical review still required before production:** check trust-anchor distribution, registry review and revocation, source-provenance authenticity, disclosure/privacy analysis, review lifecycle, local file ownership and retention, race conditions between review and release, and the ability of other workflows to bypass this narrow command. This verifier is a supplementary control, not a universal data-loss-prevention system.

## Test evidence

`tests/test_release_verify.py` contains offline synthetic fixtures for correct verification, altered summary, wrong purpose/source/year, swapped key, stale review, rights revocation, malformed and duplicate-key JSON, unexpected raw fields, low-count exports and CLI scope. `tests/test_publication.py` also verifies interoperability using a report actually produced by `release_summary` from synthetic AIS.

Run `python -m unittest discover -s tests -v` with `.[noaa,dev,geo]`. No private key or real AIS is committed. The tests generate ephemeral Ed25519 keys that are not exported.

**NOT FOR NAVIGATION. No real dataset redistribution approval is implied.**
