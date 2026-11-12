#!/usr/bin/env bash
# Prove the release-gate schemas are inside the wheel and the sdist, and that
# a non-editable install loads those bytes with importlib.resources. A foreign
# schema under /tmp/schemas/v1 must not replace them.
set -euo pipefail

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
if command -v python >/dev/null 2>&1; then
  PY=python
else
  PY=python3
fi
BASE=/tmp/harborlens-release-schemas-$$
FOREIGN=/tmp/schemas/v1/public-summary.schema.json

cleanup() {
  rm -rf "$BASE"
  rm -f "$FOREIGN"
  rmdir /tmp/schemas/v1 /tmp/schemas 2>/dev/null || true
}
trap cleanup EXIT

rm -rf "$BASE"
mkdir -p "$BASE/dist" /tmp/schemas/v1
printf '%s\n' '{"type":"object"}' > "$FOREIGN"

"$PY" -m pip wheel --no-deps -w "$BASE/dist" "$ROOT"
"$PY" -m pip install --disable-pip-version-check build
"$PY" -m build --sdist --outdir "$BASE/dist" "$ROOT"

WHEEL=$(echo "$BASE/dist"/harborlens-*.whl)
SDIST=$(echo "$BASE/dist"/harborlens-*.tar.gz)
test -f "$WHEEL"
test -f "$SDIST"

"$PY" - "$WHEEL" "$SDIST" <<'PY'
import sys
import tarfile
import zipfile

wheel, sdist = sys.argv[1], sys.argv[2]
names = (
    "public-summary.schema.json",
    "publication-review.schema.json",
    "release-verification-result.schema.json",
    "source-rights-register.schema.json",
)
with zipfile.ZipFile(wheel) as archive:
    packaged = set(archive.namelist())
for name in names:
    wanted = f"harborlens/schemas/v1/{name}"
    if wanted not in packaged:
        raise SystemExit(f"wheel is missing {wanted}")
    print("wheel contains", wanted)
with tarfile.open(sdist) as archive:
    members = set(archive.getnames())
for name in names:
    matches = [item for item in members if item.endswith(f"src/harborlens/schemas/v1/{name}")]
    if len(matches) != 1:
        raise SystemExit(f"sdist missing packaged {name}: {matches}")
    print("sdist contains", matches[0])
PY

if ! "$PY" -m venv "$BASE/venv"; then
  rm -rf "$BASE/venv"
  "$PY" -m pip install virtualenv
  "$PY" -m virtualenv "$BASE/venv"
fi
"$BASE/venv/bin/pip" install "$WHEEL"

(
  cd /tmp
  "$BASE/venv/bin/python" - "$WHEEL" <<'PY'
import json
import sys
import zipfile

from harborlens.publication import (
    PACKAGED_RELEASE_SCHEMAS,
    read_packaged_release_schema,
)

wheel = sys.argv[1]
with zipfile.ZipFile(wheel) as archive:
    for name in PACKAGED_RELEASE_SCHEMAS:
        loaded = read_packaged_release_schema(name).encode("utf-8")
        packed = archive.read(f"harborlens/schemas/v1/{name}")
        if loaded != packed:
            raise SystemExit(f"installed schema differs from wheel: {name}")
        document = json.loads(loaded)
        if not str(document.get("$schema", "")).endswith("/2020-12/schema"):
            raise SystemExit(f"unexpected schema dialect: {name}")
        print("installed package loaded", name, len(loaded))
try:
    read_packaged_release_schema("../public-summary.schema.json")
except ValueError as exc:
    if "Unknown packaged schema" not in str(exc):
        raise
else:
    raise SystemExit("path name was accepted")
print("foreign parent schema was not required")
PY
)

echo "release schema wheel install check passed"
