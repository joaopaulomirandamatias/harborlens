#!/usr/bin/env bash
# Prove a non-editable wheel, installed outside the checkout, uses the schema
# shipped inside the package. A permissive schema at /tmp/schemas/v1 must not
# grant a register the published schema rejects. Core dependencies stay empty:
# without the rights extra the helper exits 2 and names that extra.
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if command -v python >/dev/null 2>&1; then
  PY=python
else
  PY=python3
fi
BASE=/tmp/harborlens-rights-outside-$$
FOREIGN=/tmp/schemas/v1/source-rights-register.schema.json

cleanup() {
  rm -rf "$BASE"
  rm -f "$FOREIGN"
  rmdir /tmp/schemas/v1 /tmp/schemas 2>/dev/null || true
}
trap cleanup EXIT

rm -rf "$BASE"
mkdir -p "$BASE/dist" "$BASE/run" /tmp/schemas/v1
printf '%s\n' '{"type":"object"}' > "$FOREIGN"

"$PY" -m pip wheel --no-deps -w "$BASE/dist" "$ROOT"
if ! "$PY" -m venv "$BASE/venv"; then
  rm -rf "$BASE/venv"
  "$PY" -m pip install virtualenv
  "$PY" -m virtualenv "$BASE/venv"
fi
WHEEL=$(echo "$BASE/dist"/harborlens-*.whl)
test -f "$WHEEL"

"$BASE/venv/bin/python" - "$WHEEL" <<'PY'
import sys
import zipfile
wheel = sys.argv[1]
with zipfile.ZipFile(wheel) as archive:
    names = archive.namelist()
wanted = "harborlens/schemas/v1/source-rights-register.schema.json"
if wanted not in names:
    raise SystemExit(f"wheel is missing {wanted}")
print("wheel contains", wanted)
PY

"$BASE/venv/bin/pip" install "$WHEEL"

set +e
"$BASE/venv/bin/python" -m harborlens.rights \
  --register "$ROOT/docs/data/rights-register.json" \
  --source-id noaa_pmel_erddap \
  --dataset-version AIS2024_AIS \
  --purpose research > "$BASE/run/missing.json"
code=$?
set -e
test "$code" -eq 2
"$BASE/venv/bin/python" - "$BASE/run/missing.json" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
message = data.get("error", "")
if "pip install 'harborlens[rights]'" not in message:
    raise SystemExit(f"missing extra hint: {message!r}")
if data.get("rights_status") != "review_required":
    raise SystemExit(data)
print("missing jsonschema exits 2")
PY

"$BASE/venv/bin/pip" install "${WHEEL}[rights]"

set +e
( cd /tmp && "$BASE/venv/bin/python" -m harborlens.rights \
  --register "$ROOT/docs/data/rights-register.json" \
  --source-id noaa_pmel_erddap \
  --dataset-version AIS2024_AIS \
  --purpose research > "$BASE/run/pending.json" )
code=$?
set -e
test "$code" -eq 1
"$BASE/venv/bin/python" - "$BASE/run/pending.json" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("rights_status") != "review_required" or "error" in data:
    raise SystemExit(data)
print("packaged schema accepts the checked-in register")
PY

"$BASE/venv/bin/python" - "$BASE/run/invalid.json" <<'PY'
import json
import sys
record = {
    "schema_version": 1,
    "sources": [{
        "source_id": "synthetic_source",
        "dataset_version": "v1",
        "source_url": "https://example.org/source",
        "terms_url": "https://example.org/terms",
        "rights_status": "reviewed_public_domain_attribution_required",
        "decision": "reviewed",
        "permitted_uses": {
            "research": "allowed",
            "public_aggregates": "prohibited",
            "commercial": "prohibited",
        },
        "attribution": "Synthetic agency.",
        "reviewed_by": "Independent reviewer",
        "reviewed_at_utc": "2026-11-09T12:00:00Z",
        "terms_sha256": "a" * 64,
        "evidence_url": "https://example.org/review",
        "review_note": "Synthetic review record; not a real approval.",
        "unexpected_field": "permissive parent schema must not grant this",
    }],
}
with open(sys.argv[1], "w", encoding="utf-8") as handle:
    json.dump(record, handle)
PY

set +e
( cd /tmp && "$BASE/venv/bin/python" -m harborlens.rights \
  --register "$BASE/run/invalid.json" \
  --source-id synthetic_source \
  --dataset-version v1 \
  --purpose research > "$BASE/run/invalid-out.json" )
code=$?
set -e
test "$code" -eq 2
"$BASE/venv/bin/python" - "$BASE/run/invalid-out.json" <<'PY'
import json
import sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
if data.get("rights_status") != "review_required" or "error" not in data:
    raise SystemExit(data)
print("parent schema was not consulted")
PY

echo "rights wheel install check passed"
