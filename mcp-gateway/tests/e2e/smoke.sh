#!/usr/bin/env bash
# Phase 2 smoke: GW-01 (healthz + initialize + tools/list), GW-02 (15-25 tool count), GW-04 (bearer).
# Usage (from project root, after `docker compose up -d`):
#   bash mcp-gateway/tests/e2e/smoke.sh
# Env: GATEWAY_URL (default http://127.0.0.1:8080), TOKEN_FILE (default auto-detect)
set -euo pipefail

GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:8080}"

# Token discovery: prefer host-bound path under the project root, fall back to /agent (inside container).
if [ -f "./.mcp-gateway-token" ]; then
  TOKEN_FILE="./.mcp-gateway-token"
elif [ -f "/agent/.mcp-gateway-token" ]; then
  TOKEN_FILE="/agent/.mcp-gateway-token"
else
  echo "[smoke] ERROR: token file not found (tried ./.mcp-gateway-token and /agent/.mcp-gateway-token)" >&2
  exit 2
fi

TOK="$(cat "${TOKEN_FILE}" | tr -d '[:space:]')"
if [ -z "${TOK}" ]; then
  echo "[smoke] ERROR: token file ${TOKEN_FILE} is empty" >&2
  exit 2
fi

# 1) /healthz (no auth)
echo "[smoke] GET ${GATEWAY_URL}/healthz"
HEALTH_JSON="$(curl -fsS "${GATEWAY_URL}/healthz")"
echo "${HEALTH_JSON}" | grep -q '"ok":[[:space:]]*true' || {
  echo "[smoke] FAIL: /healthz did not return {ok: true}: ${HEALTH_JSON}" >&2
  exit 1
}
echo "[smoke] /healthz OK"

# 2) MCP initialize
INIT_PAYLOAD='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"smoke.sh","version":"1"}}}'

INIT_RESP="$(curl -fsSL -X POST "${GATEWAY_URL}/mcp" \
  -H "Authorization: Bearer ${TOK}" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "${INIT_PAYLOAD}")"
echo "${INIT_RESP}" | grep -q '"serverInfo"' || {
  echo "[smoke] FAIL: initialize did not include serverInfo: ${INIT_RESP}" >&2
  exit 1
}
echo "[smoke] /mcp initialize OK"

# 3) tools/list
LIST_PAYLOAD='{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
LIST_RESP="$(curl -fsSL -X POST "${GATEWAY_URL}/mcp" \
  -H "Authorization: Bearer ${TOK}" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "${LIST_PAYLOAD}")"

# Count tools + extract names
# D-02 revised: 15-25 is the gateway-native budget. Total may be larger once Plan 03's
# pass-through registers the backend's native tools too — so we check a lower bound
# only and verify specific names to prove D-07 pass-through is wired.
if command -v jq >/dev/null 2>&1; then
  TOOL_COUNT="$(echo "${LIST_RESP}" | jq '.result.tools | length')"
  TOOL_NAMES="$(echo "${LIST_RESP}" | jq -r '.result.tools[].name')"
else
  TOOL_COUNT="$(echo "${LIST_RESP}" | grep -oE '"name"[[:space:]]*:' | wc -l)"
  TOOL_NAMES="$(echo "${LIST_RESP}" | grep -oE '"name"[[:space:]]*:[[:space:]]*"[^"]+"' | sed -E 's/.*"([^"]+)"$/\1/')"
fi

if [ "${TOOL_COUNT}" -lt 15 ]; then
  echo "[smoke] FAIL: tool count ${TOOL_COUNT} below the 15 native floor" >&2
  echo "${LIST_RESP}" >&2
  exit 1
fi

# Gateway-native floor: expect the 19 Plan 02 tools. Check a couple of canaries.
echo "${TOOL_NAMES}" | grep -qx "get_active_backend" || {
  echo "[smoke] FAIL: native tool 'get_active_backend' missing from tools/list" >&2
  exit 1
}
echo "${TOOL_NAMES}" | grep -qx "run_triage" || {
  echo "[smoke] FAIL: native tool 'run_triage' missing from tools/list" >&2
  exit 1
}
echo "${TOOL_NAMES}" | grep -qx "collect_strings" || {
  echo "[smoke] FAIL: native tool 'collect_strings' missing from tools/list" >&2
  exit 1
}
echo "[smoke] get_active_backend present OK"

# Ask the gateway which backend is pinned. If "none" (MCP_GATEWAY_SKIP_BACKEND=1 path),
# skip the backend-native tool check. Otherwise, verify at least one known backend-native
# tool is in the list (D-07 pass-through wiring).
CALL_BACKEND_PAYLOAD='{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_active_backend","arguments":{}}}'
BACKEND_RESP="$(curl -fsSL -X POST "${GATEWAY_URL}/mcp" \
  -H "Authorization: Bearer ${TOK}" \
  -H "Accept: application/json, text/event-stream" \
  -H "Content-Type: application/json" \
  -d "${CALL_BACKEND_PAYLOAD}")"
# The backend value is nested inside an escaped-JSON `text` content block, e.g.
#   "text":"{\n  \"backend\": \"ghidra\"\n}"
# so we extract by looking for `\"backend\":` (escaped) OR fall back to a plain match.
if command -v jq >/dev/null 2>&1; then
  ACTIVE_BACKEND="$(echo "${BACKEND_RESP}" | jq -r '.result.content[0].text' 2>/dev/null | jq -r '.backend // empty' 2>/dev/null)"
else
  # Match either the escaped-quote form (\"backend\": \"name\") or the plain form ("backend": "name").
  ACTIVE_BACKEND="$(echo "${BACKEND_RESP}" | grep -oE '\\"backend\\"[[:space:]]*:[[:space:]]*\\"[a-z]+\\"' | head -1 | sed -E 's/.*\\"([a-z]+)\\"$/\1/')"
  if [ -z "${ACTIVE_BACKEND}" ]; then
    ACTIVE_BACKEND="$(echo "${BACKEND_RESP}" | grep -oE '"backend"[[:space:]]*:[[:space:]]*"[a-z]+"' | tail -1 | sed -E 's/.*"([a-z]+)"$/\1/')"
  fi
fi
ACTIVE_BACKEND="${ACTIVE_BACKEND:-none}"

NATIVE_FLOOR=22  # Plan 02 gateway-native surface (21) + get_active_backend (Plan 05)
BACKEND_COUNT=$((TOOL_COUNT - NATIVE_FLOOR))
if [ "${BACKEND_COUNT}" -lt 0 ]; then BACKEND_COUNT=0; fi

echo "[smoke] /mcp tools/list OK — ${TOOL_COUNT} tools (native=${NATIVE_FLOOR}, backend=${BACKEND_COUNT}, active=${ACTIVE_BACKEND})"

case "${ACTIVE_BACKEND}" in
  ghidra)
    echo "${TOOL_NAMES}" | grep -qx "program.open" || {
      echo "[smoke] FAIL: ghidra backend active but native tool 'program.open' missing from tools/list" >&2
      exit 1
    }
    echo "[smoke] backend-native pass-through OK (ghidra: program.open)"
    ;;
  ida)
    echo "${TOOL_NAMES}" | grep -qx "lookup_funcs" || {
      echo "[smoke] FAIL: ida backend active but native tool 'lookup_funcs' missing from tools/list" >&2
      exit 1
    }
    echo "[smoke] backend-native pass-through OK (ida: lookup_funcs)"
    ;;
  bn)
    # BN tool names vary with the vendored backend; verify at least one stable
    # disassembly wrapper remains visible.
    DISASM_FOUND=0
    for t in decompile list_functions get_xrefs; do
      if echo "${TOOL_NAMES}" | grep -qx "${t}"; then
        DISASM_FOUND=$((DISASM_FOUND + 1))
      fi
    done
    if [ "${DISASM_FOUND}" -lt 1 ]; then
      echo "[smoke] FAIL: ${ACTIVE_BACKEND} backend active but no unified disasm tools (decompile/list_functions/get_xrefs) registered" >&2
      exit 1
    fi
    echo "[smoke] backend disasm tools present OK (${DISASM_FOUND}/3 unified tools registered, backend=${ACTIVE_BACKEND})"
    ;;
  none|"")
    echo "[smoke] no backend pinned (MCP_GATEWAY_SKIP_BACKEND=1?) — skipping backend-native tool check"
    ;;
  *)
    echo "[smoke] FAIL: unknown backend value from get_active_backend: '${ACTIVE_BACKEND}'" >&2
    exit 1
    ;;
esac

# 4) GW-04 regression: unauth POST to /mcp must be 401
# Hit the canonical /mcp/ path directly so the bearer middleware (not the trailing-slash
# redirect at /mcp) determines the status code.
UNAUTH_CODE="$(curl -s -o /dev/null -w '%{http_code}' -X POST "${GATEWAY_URL}/mcp/" -H "Content-Type: application/json" -d "${INIT_PAYLOAD}")"
if [ "${UNAUTH_CODE}" != "401" ]; then
  echo "[smoke] FAIL: unauth POST /mcp/ returned ${UNAUTH_CODE}, expected 401" >&2
  exit 1
fi
echo "[smoke] /mcp unauth -> 401 OK"

echo "[smoke] ALL CHECKS PASSED"
