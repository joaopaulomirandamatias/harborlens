# Ed25519-signed reviewer attestations (SPEC-003)

**Scope:** experimental offline aggregate release, not a general-purpose publication service. A signed review is cryptographic evidence that a configured key signed specific claims, **not** proof of a legally authorized reviewer or valid upstream data licensing.

## Trust and key custody

1. An independent release approver holds an Ed25519 private key outside the Git repository, CI, application server, data directory, and published artifacts; a managed HSM is preferred. Never share, upload, print or commit the private key.
2. The publisher receives the public key, the reviewer's approved identifier, and the independently verified SHA-256 fingerprint of its **DER SubjectPublicKeyInfo** encoding through a separate trusted administration process. Do not accept a fingerprint supplied only alongside the signature to be checked.
3. The publisher pins all three on every actual staging operation: `--trusted-reviewer-key`, `--trusted-reviewer-key-sha256`, and `--trusted-reviewer-id`. A self-provided or swapped public key must not be considered independent approval.
4. Organization-level reviewer eligibility, key revocation, trusted-key distribution, rotation, incident response, and protection of rights-registry entries remain external controls. A reviewer signature is insufficient when those controls are missing.

## Workflow

First, verify actual source-specific rights and run the `harborlens-release-summary --dry-run` command described in [aggregate publication gate](aggregate-publication-gate.md). The current checked-in rights register has no approved source, so it **blocks** even dry runs until a genuine source review is registered.

After an independent human privacy/rights/science review, prepare a JSON decision containing the fields from [`schemas/v1/publication-review.schema.json`](../../schemas/v1/publication-review.schema.json). Set `signature_algorithm` to `Ed25519`, `public_key_sha256` to the independently pinned public-key fingerprint, and `signature_b64` temporarily to an empty string before signing. All other fields, including purpose, review timestamp, reviewer ID, exact summary digest, and conditional-license attestation, must be final.

The signature covers a fixed domain separator and then the canonical UTF-8/ASCII JSON of **all fields except `signature_b64`**. The separator is the ASCII line `harborlens.publication-review.v1` followed by a newline. The JSON uses sorted keys, compact separators, ASCII escaping, rejects non-finite numbers (`allow_nan=False`), and ends with one newline. **BREAKING:** signatures made for HarborLens `0.2.0.dev4` covered the JSON body only and are rejected. There is no signing API, key generation service, or automatic human-approval step in HarborLens. Sign with `review_message()` so the domain separator is included.

An external offline signer can use the following illustrative Python operation **only after an authorized human has approved the final contents**:

```python
import base64
import json
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from harborlens.review_signatures import review_message, public_key_fingerprint

review_path = Path('private/approved-review.json')
key_path = Path('private/reviewer-private.pem')  # never commit or transmit
public_path = Path('private/reviewer-public.pem')
review = json.loads(review_path.read_text(encoding='utf-8'))
review['signature_algorithm'] = 'Ed25519'
_, review['public_key_sha256'] = public_key_fingerprint(public_path)
review['signature_b64'] = ''
private_key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
review['signature_b64'] = base64.b64encode(
    private_key.sign(review_message(review))
).decode('ascii')
review_path.write_text(json.dumps(review, indent=2) + '\n', encoding='utf-8')
```

An unencrypted private-key file is **only an illustration for an isolated local test environment**; production signers should use encrypted keys or hardware-backed signing. Never run signing scripts in a shared CI environment or a repository checkout with untrusted code. Prefer a dedicated approved signing implementation and independent verifier.

To stage a *local* aggregate, provide the review plus the out-of-band pinned public key/identity:

```bash
harborlens-release-summary --run results/houston-single \
  --source-file data/houston-acquired.csv \
  --rights-register private/approved-rights-register.json \
  --purpose public_aggregates \
  --review private/approved-review.json \
  --trusted-reviewer-key private/reviewer-public.pem \
  --trusted-reviewer-key-sha256 <64-hex-SPKI-fingerprint> \
  --trusted-reviewer-id approved-reviewer \
  --out private/release/public-summary.json
```

The signing key is not needed by the publisher; only the public key is. The source-rights register and local run remain separately verified as in PRs #55–#61. The command never uploads the release.

## Failure behavior and known limitations

- Missing `cryptography` dependency (`cryptography>=42.0.4`), unsigned review, a `0.2.0.dev4` signature without the domain separator, bad base64, non-Ed25519 key, altered purpose or summary, wrong reviewer ID, mismatched public-key fingerprint, a date-only timestamp, a timestamp older than 30 days, a timestamp more than 5 minutes ahead of the checker clock, a non-finite number in the canonical document, or a revoked/not-authorized signer (as established by external policy) must **not** authorize publication. The 5 minutes are a fixed clock-skew allowance, not a configuration knob. The code enforces the cryptographic and data checks, including fingerprint comparison with `hmac.compare_digest`, while external policy must enforce revocation and eligibility. A missing `cryptography` install is a validation failure (exit 2, nothing written), including when the import fails at release time.
- A locally controlled administrator can replace both the trust configuration and a rights registry; the code does not prevent that. A production publication system must enforce independent configuration ownership, signed source-rights decisions, audit retention and role separation.
- Replaying a valid approval for the **same** summary and purpose is allowed while `reviewed_at_utc` is not older than 30 days and not more than 5 minutes ahead of the checker clock. There is no global nonce/revocation service yet. Publications are still subject to no-overwrite local file creation. The CLI calls `prepare_summary` once and stages that result.
- Aggregate suppression floors are preliminary safeguards, not proof of anonymity. No raw AIS, verified event, berth, waiting time, geofence certification or navigation claim is granted.

**NOT FOR NAVIGATION. No real-source release is approved by this implementation.**

## Independent verification after staging

A recipient can run [`harborlens-verify-release`](independent-release-verification.md) on the locally staged report, with reviewer public-key information and an authorized rights-register snapshot **obtained independently** of that report. The verifier reuses `summary_sha256` and `verify_review_signature`. The checked message is the `harborlens.publication-review.v1` domain separator plus canonical JSON (`allow_nan=False`). A `0.2.0.dev4` signature that covers only the JSON body is rejected. Fingerprints use `hmac.compare_digest`. Aggregate floors are the recounted 100-observation and 10-group floors: a large scanned count copied from a manifest does not pass when retained observations or MMSI groups are below those floors. A date-only review timestamp and a missing `cryptography` install fail closed (exit 2, nothing written). This verifies the signed claims and pinned source-rights decision, but not original AIS truth, licensing legality, or anonymity. It does not recount `houston_clean.csv`; see the known limitation in [independent release verification](independent-release-verification.md). No data upload is performed.
