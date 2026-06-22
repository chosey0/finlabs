#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

command -v uv >/dev/null || { echo "uv is required" >&2; exit 1; }
command -v bun >/dev/null || { echo "bun is required" >&2; exit 1; }
test "$(bun --version)" = "1.3.3" || {
  echo "Bun 1.3.3 is required" >&2
  exit 1
}
test -f uv.lock || { echo "uv.lock is required" >&2; exit 1; }
test -f finlabs_intelligence/web/bun.lock || {
  echo "finlabs_intelligence/web/bun.lock is required" >&2
  exit 1
}

UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/finlabs-uv-cache}" uv sync --all-groups
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/finlabs-uv-cache}" uv run --all-groups python -m pytest -q
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/finlabs-uv-cache}" uv run --all-groups ruff check .
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/finlabs-uv-cache}" uv run --all-groups python -m compileall -q \
  finlabs_intelligence modules tests
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/finlabs-uv-cache}" uv run --all-groups python -m \
  finlabs_intelligence.api.export_openapi

(
  cd "$ROOT/finlabs_intelligence/web"
  BUN_INSTALL_CACHE_DIR="${BUN_INSTALL_CACHE_DIR:-/tmp/finlabs-bun-cache}" bun ci
  bun run generate:api
  bun run typecheck
  bun test
  bun run build
  bun run test:e2e
)

git diff --exit-code -- \
  finlabs_intelligence/api/openapi.json \
  finlabs_intelligence/web/src/api/generated
git diff --check
