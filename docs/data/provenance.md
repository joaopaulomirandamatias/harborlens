# Local File Provenance (research feature)

The `harborlens` CLI writes SHA-256 digests for its input and three output files. An optional `--source-url` is a user-declared value, **not** an authenticated government claim. Data rights always remain `review_required`.

```bash
harborlens --input tests/fixtures/synthetic_ais.csv --out results
harborlens-verify --manifest results/manifest.json
```

The run ID is reproducible for the same input SHA-256, bounding box and method parameters. It does not sign or authenticate a dataset. The verification command checks only fixed output filenames in the manifest folder to avoid following arbitrary paths. Changes to the manifest itself are not detectable without an external trusted record.

`harborlens-verify --version` prints the program name and the package version and does not require `--manifest`. A missing or unreadable manifest exits 2 with one error line and no traceback. A manifest that is present, with a missing artifact or a hash that does not match, exits 1 and prints `{"ok": false}`. That JSON is the verification result. It is not a usage error.

**Not implemented:** signed evidence, immutable storage, independently verified NOAA provenance, data licenses, authentic event evaluation or accuracy metrics. This feature is intended for local integrity comparisons only.
