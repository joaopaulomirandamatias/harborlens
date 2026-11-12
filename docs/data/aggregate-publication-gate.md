# Rights-gated, aggregate-only publication staging (SPEC-003)

**State:** experimental local release control. This does **not** modify normal HarborLens research outputs, copy raw AIS, publish on the Internet, or replace a real data-governance system. The registered sources currently have no approved redistribution decisions, so the checked-in register **always denies** staging.

## What the gate does

`harborlens-release-summary` is a deliberately narrow **new** command. It accepts a previously verified single-file HarborLens run, its original source CSV with adjacent `.source.json` acquisition receipt, a local rights register, and a purpose. It never accepts an arbitrary JSON report to publish.

The command verifies the local run's artifact hashes, its exact input CSV SHA-256, the acquisition sidecar's output checksum, stable NOAA source identity/version, input completeness, diagnostic consistency, and the current version/purpose-specific rights register decision. Unknown, prohibited, missing, oversized, malformed or unmatched evidence **denies publication without writing a release file**.

The only emitted payload is an explicit allowlist: scanned/retained observations, distinct MMSI **group count** (not identifiers), stationary **candidate** count, run/method identity, source-version and evidence hashes, purpose and fixed scientific cautions. It contains no rows, MMSI values, positions, time series, candidate IDs, free-text labels, or berth/waiting claims. A preliminary suppression floor requires at least **100 scanned and retained observations and 10 distinct MMSI groups**; this is **not a demonstration of anonymity**. Additional privacy screening remains necessary even after meeting the floor.

Retained observations and distinct MMSI groups are **recounted from one read of `houston_clean.csv`**. That read is at most 256 MiB plus one byte (`MAX_CLEANED_RECOUNT_BYTES`, the same output ceiling as archive extraction and track-context). SHA-256 of those exact bytes is compared with the manifest, and the recount uses the same buffer. The file is not opened a second time for the recount. A larger file exits 2 and writes nothing. The release decision uses the recounted values. If the manifest hash, `counts.written`, or `events.vessels` disagrees with that buffer, the command exits 2 and writes nothing. `counts.total` counts scanned input rows, including rows that were not retained, so it is not in the cleaned file. It must still be at least 100 and at least the retained recount, and it cannot by itself satisfy the floor. A date-only `reviewed_at_utc` (`2026-11-12` or `2026-11-12Z`) is rejected the same way: exit 2, no traceback, nothing written. The timestamp must be ASCII `YYYY-MM-DDTHH:MM:SS` with no fraction or 1 to 6 fractional digits, then `Z`, such as `2026-11-12T00:00:00Z`. `+00:00` is rejected. The parser builds the clock from those fields, so Python 3.10 and 3.12 agree. NaN and Infinity cannot enter the canonical release bytes; that input is denied and nothing is written.

The gate currently supports single-file **NOAA PMEL ERDDAP AIS2024_AIS** and a provenance-matched local **NOAA daily archive extraction**, **not** arbitrary independent inputs, non-AIS sources, multi-day derived runs, or raw GeoJSON downloads. Future connectors must add their own independently tested provenance links and suppression rules.

## Two-step, cryptographically signed reviewer release

After independently reviewing and recording the precise source rights, run the command with `--dry-run` to get the SHA-256 fingerprint of its proposed summary. This dry run **also requires an approved purpose-specific rights record**.

```bash
harborlens-release-summary --run results/houston-single \
  --source-file data/houston-acquired.csv \
  --rights-register docs/data/rights-register.json \
  --purpose public_aggregates --dry-run
```

Create a **signed local** review JSON from the exact proposed summary fingerprint; replace all illustrative placeholders with actual decisions. The fixture below is an example of **format**, not authorization:

```json
{
  "schema_version": 1,
  "decision": "approved",
  "summary_sha256": "64-lowercase-hex-digits-from-the-dry-run",
  "purpose": "public_aggregates",
  "reviewer_id": "independent-reviewer-id",
  "reviewed_at_utc": "2026-11-09T00:00:00Z",
  "privacy_reviewed": true,
  "source_rights_reviewed": true,
  "scientific_limitations_reviewed": true,
  "conditions_reviewed": false,
  "signature_algorithm": "Ed25519",
  "public_key_sha256": "externally-pinned-64-hex-key-fingerprint",
  "signature_b64": "Ed25519-signature-over-canonical-review"
}
```

The reviewer must check **data rights, privacy, scientific limitations and any special license conditions**. Fields in the example are placeholders, not a valid signature. The review must be signed offline using a reviewer-controlled Ed25519 private key; see [signed review and trust-root procedure](signed-release-review.md). The publisher independently pins the reviewer's public-key fingerprint and identity. The Ed25519-signed reviewer decision must match the exact summary digest/purpose, expected public-key fingerprint, and reviewer identity. `reviewed_at_utc` must be ASCII `YYYY-MM-DDTHH:MM:SS` with no fraction or 1 to 6 fractional digits, then `Z`. `+00:00` is rejected. It is accepted when it is not older than 30 days and not more than 5 minutes ahead of the checker clock, inclusive. Those 5 minutes are a fixed clock-skew allowance, not a configuration knob. A timestamp further ahead is denied as in the future. A date-only value is denied. An altered registry or output manifest produces a different digest and requires another review. The command evaluates `prepare_summary` once per invocation and stages that same summary.

To **stage a local release only**, supply that review JSON:

```bash
harborlens-release-summary --run results/houston-single \
  --source-file data/houston-acquired.csv \
  --rights-register docs/data/rights-register.json \
  --purpose public_aggregates --review private/release-review.json \
  --trusted-reviewer-key private/reviewer-public.pem \
  --trusted-reviewer-key-sha256 64-hex-fingerprint-from-independent-channel \
  --trusted-reviewer-id independent-reviewer-id \
  --out private/release/public-summary.json
```

The command writes a single non-overwriting JSON file with `summary`, `summary_sha256` and `release_review`, on the **local machine only**. It never uploads or commits the file to GitHub, Notion or any provider. Directory/file access, externally pinned reviewer trust roots, protection of signing keys, audit retention, exact upstream license authentication, key management and organizational DLP still require a deployment-specific design.

## Security and scientific guarantees / non-guarantees

| Concern | Implemented guard | Limitation |
| --- | --- | --- |
| Unsanctioned reuse | Fresh, reviewed source-version and purpose match | Registry entries/reviews are local assertions, not signed/legal attestations |
| Provenance integrity | Input/source/output digests and run artifact verification | SHA-256 of local files does not prove upstream origin |
| Unauthorized disclosure | Fixed allowlist, no raw AIS, numeric suppression floors | Can still be sensitive in particular contexts; privacy review required |
| False event claims | Explicit candidate-only and non-navigation warnings | No independent labels or real-event validation |
| Accidental overwrite | Atomic local file staging, no clobber | Not an enforcement boundary against users manually copying other files |

**Important:** `harborlens`, `harborlens-multiday` and existing acquisition adapters still export their own local research artifacts; this new command governs **only releases made through it**. It does not pretend to prevent manual copies or all other CLI outputs.

**Validation:** `python -m unittest discover -s tests -v`, in a checkout with `pip install -e '.[noaa,dev,geo]'`. New tests are synthetic-only; no network access or real AIS is needed. Reference schemas: `schemas/v1/publication-review.schema.json`, `schemas/v1/public-summary.schema.json`. The same bytes are packaged at `src/harborlens/schemas/v1/` and load with `importlib.resources` (`read_packaged_release_schema`). `schemas/v1/release-verification-result.schema.json` is packaged the same way.

**NOT FOR NAVIGATION.**
