#!/usr/bin/env bash
# smoke-remote.sh -- Phase 3 INF-01 + INF-02 end-to-end test.
# Verifies:
#   - ./run_docker.sh --remote launches detached gateway
#   - token file populated; print block contains Bearer token + JSON snippet
#   - host port published (Publishers >= 1)
#   - in-container gateway bound to 0.0.0.0
#   - /mcp without auth is rejected (not 200)
#   - /healthz reachable
#   - idempotent re-run reprints same token
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source "$(dirname -- "${BASH_SOURCE[0]}")/lib_assert.sh"

cleanup() {
  docker compose -f compose.yaml -f compose.remote.yaml down --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Pre-clean: ensure no other state lingering.
docker compose -f compose.yaml down --remove-orphans >/dev/null 2>&1 || true
docker compose -f compose.yaml -f compose.remote.yaml down --remove-orphans >/dev/null 2>&1 || true

echo "[smoke] starting remote mode..."

OUT=$(mktemp)
./run_docker.sh --remote >"$OUT" 2>&1 || {
  echo "[fail] run_docker.sh --remote exited non-zero"
  cat "$OUT"
  exit 1
}

cat "$OUT"
echo

TOKEN_FILE="workspace/.mcp-gateway-token"
if [[ ! -s "$TOKEN_FILE" ]]; then
  echo "[fail] no token file at $TOKEN_FILE"
  exit 1
fi
TOKEN=$(< "$TOKEN_FILE"); TOKEN="${TOKEN%$'\n'}"
if [[ -z "$TOKEN" ]]; then
  echo "[fail] token file empty"
  exit 1
fi

# D-07: print block must contain bearer token and ready-to-paste artifacts.
output=$(<"$OUT")
assert_contains "$output" "Bearer $TOKEN" "D-07: Bearer token printed"
assert_contains "$output" "type" "D-07: .mcp.json snippet contains 'type' key"
assert_contains "$output" "http://" "D-07: URL printed"
assert_contains "$output" "docker compose down" "D-07: teardown hint printed"
assert_contains "$output" "curl" "D-07: curl example printed"

# INF-02: host port published.
if command -v jq >/dev/null 2>&1; then
  pubs=$(docker compose -f compose.yaml -f compose.remote.yaml ps --format json kali 2>/dev/null \
    | jq -r '[.[]?.Publishers // [] | .[]] | length' 2>/dev/null || echo 0)
else
  pubs=$(docker compose -f compose.yaml -f compose.remote.yaml ps --format json kali 2>/dev/null \
    | grep -o '"PublishedPort"' | wc -l || echo 0)
fi
pubs="${pubs:-0}"
if [[ "$pubs" -lt 1 ]]; then
  echo "[fail] no host port published (Publishers=$pubs)"
  exit 1
fi
echo "[pass] INF-02: host port published (Publishers=$pubs)"

# INF-01: in-container gateway bound to 0.0.0.0 (not 127.0.0.1).
if ! docker compose -f compose.yaml -f compose.remote.yaml logs kali 2>&1 \
    | grep -E "\[gateway\] starting on 0\.0\.0\.0:" >/dev/null; then
  echo "[fail] gateway not bound to 0.0.0.0 in remote mode"
  docker compose -f compose.yaml -f compose.remote.yaml logs kali 2>&1 | tail -40
  exit 1
fi
echo "[pass] INF-01: gateway log shows bind to 0.0.0.0"

# Bearer auth enforcement: /mcp without auth should NOT return 200.
HTTP=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/mcp || echo 000)
if [[ "$HTTP" == "200" ]]; then
  echo "[fail] /mcp without auth returned 200 -- bearer auth NOT enforced"
  exit 1
fi
echo "[pass] /mcp without auth returned $HTTP (not 200)"

# /healthz reachable (Phase 2 D-17 makes /healthz open).
HTTP=$(curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/healthz || echo 000)
if [[ ! "$HTTP" =~ ^(200|204)$ ]]; then
  echo "[fail] /healthz returned $HTTP (expected 200/204)"
  exit 1
fi
echo "[pass] /healthz reachable ($HTTP)"

# D-09 / Idempotence: re-run --remote, same token reprinted, container not restarted.
echo "[smoke] verifying idempotent re-run..."
OUT2=$(mktemp)
./run_docker.sh --remote >"$OUT2" 2>&1 || {
  echo "[fail] idempotent re-run exited non-zero"
  cat "$OUT2"
  exit 1
}
TOKEN2=$(< "$TOKEN_FILE"); TOKEN2="${TOKEN2%$'\n'}"
assert_eq "$TOKEN2" "$TOKEN" "Idempotent re-run: token unchanged"
assert_contains "$(<"$OUT2")" "Bearer $TOKEN" "Idempotent re-run: token reprinted"

echo
echo "[smoke] remote-mode green (INF-01 + INF-02)"
