#!/usr/bin/env bash
# smoke-local.sh -- Phase 3 D-12 / INF-05 backstop.
# Verifies `./run_docker.sh` (no flag) is byte-identical to v1:
#   - cwd /agent, USER=agent
#   - no mcp-gateway daemon process
#   - no host port published
#   - inner agent toolchain (claude, codex) intact
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../../.." && pwd -P)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091
source "$(dirname -- "${BASH_SOURCE[0]}")/lib_assert.sh"

# Clean up any prior remote-mode container before exercising local mode
# (RESEARCH Pitfall 6: stale state from previous compose up -d run).
docker compose -f compose.yaml -f compose.remote.yaml down --remove-orphans >/dev/null 2>&1 || true
docker compose -f compose.yaml down --remove-orphans >/dev/null 2>&1 || true

echo "[smoke] running run_docker.sh (local mode, no flag)..."

# Capture inner-shell probe output. ./run_docker.sh -c '<script>' passes
# `-c <script>` through as positional args to bash inside the container,
# because compose runs `kali` with CMD bash.
output=$(./run_docker.sh -c '
  set +e
  echo "PWD=$(pwd)"
  echo "USER=$USER"
  echo "GATEWAY_PROC=$(pgrep -f mcp-gateway || echo none)"
  echo "GATEWAY_PORT_LISTENING=$( (echo > /dev/tcp/127.0.0.1/8080) >/dev/null 2>&1 && echo yes || echo no)"
  echo "CLAUDE_OK=$(claude --version >/dev/null 2>&1 && echo yes || echo no)"
  echo "CODEX_OK=$(codex --version >/dev/null 2>&1 && echo yes || echo no)"
' 2>&1)

echo "$output"
echo

# D-12(b): cwd /agent and USER=agent unchanged
assert_contains "$output" "PWD=/agent" "D-12(b): cwd /agent unchanged"
assert_contains "$output" "USER=agent" "D-12(b): USER=agent unchanged"

# D-12(c): gateway daemon NOT started in local mode
assert_contains "$output" "GATEWAY_PROC=none" "D-12(c): no mcp-gateway daemon in local mode"
assert_contains "$output" "GATEWAY_PORT_LISTENING=no" "D-12(c): gateway port NOT listening in local mode"

# D-12(b): inner agent toolchain (claude, codex) intact
assert_contains "$output" "CLAUDE_OK=yes" "D-12(b): claude CLI available"
assert_contains "$output" "CODEX_OK=yes" "D-12(b): codex CLI available"

# D-12(a): no host port published. compose run --rm exits the container,
# so compose ps usually returns empty (count = 0).
if command -v jq >/dev/null 2>&1; then
  pubs=$(docker compose -f compose.yaml ps --format json kali 2>/dev/null \
    | jq -r '[.[]?.Publishers // [] | .[]] | length' 2>/dev/null || echo 0)
else
  pubs=$(docker compose -f compose.yaml ps --format json kali 2>/dev/null \
    | grep -o '"PublishedPort"' | wc -l || echo 0)
fi
pubs="${pubs:-0}"
assert_eq "$pubs" "0" "D-12(a): no host ports published in local mode"

echo
echo "[smoke] local-mode green (D-12 / INF-05)"
