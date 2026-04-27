#!/usr/bin/env bash
set -euo pipefail
HERE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"

# Shared trap: ensure container is torn down even if a sub-script aborts mid-flight.
REPO_ROOT="$(cd -- "$HERE/../../.." && pwd -P)"
cleanup() {
  ( cd "$REPO_ROOT" && \
    docker compose -f compose.yaml -f compose.remote.yaml down --remove-orphans >/dev/null 2>&1 || true; \
    docker compose -f compose.yaml down --remove-orphans >/dev/null 2>&1 || true; )
}
trap cleanup EXIT

echo "═══ smoke-local.sh ═══"
bash "$HERE/smoke-local.sh"

echo
echo "═══ smoke-remote.sh ═══"
bash "$HERE/smoke-remote.sh"

echo
echo "[smoke] all green"
