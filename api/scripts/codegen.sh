#!/usr/bin/env bash
# Regenerate every artefact downstream of openapi.yaml.
# Run from anywhere: the script always cd's to its own directory first.
set -euo pipefail

cd "$(dirname "$0")"            # cwd: api/scripts/
SPEC=../openapi.yaml
ROOT=../..
SERVER="$ROOT/server"
WEB_CLIENT="$ROOT/web-client"

echo "==> Linting $SPEC"
npx --yes --prefix . @redocly/cli lint "$SPEC"

echo "==> Generating Pydantic v2 models -> $SERVER/app/api/generated/models.py"
mkdir -p "$SERVER/app/api/generated"
if command -v uv >/dev/null 2>&1; then
  ( cd "$SERVER" \
    && uv run datamodel-codegen \
         --input ../api/openapi.yaml \
         --input-file-type openapi \
         --output app/api/generated/models.py \
         --output-model-type pydantic_v2.BaseModel \
         --use-annotated \
         --target-python-version 3.11 \
         --disable-timestamp
  )
else
  echo "  (uv not available — install from https://docs.astral.sh/uv/ and re-run)"
  exit 1
fi

echo "==> Generating TypeScript types -> $WEB_CLIENT/src/api.ts"
npx --yes --prefix . openapi-typescript "$SPEC" -o "$WEB_CLIENT/src/api.ts"

echo "✓ Codegen complete. Review with: git diff -- $SERVER/app/api/generated $WEB_CLIENT/src/api.ts"
