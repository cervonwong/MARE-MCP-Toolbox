---
phase: 04-external-client-integration
plan: 05
subsystem: testing
tags: [e2e, pytest, mcp, httpx, subprocess, bearer-auth, resources]

# Dependency graph
requires:
  - phase: 02-mcp-gateway
    provides: FastMCP gateway with BearerAuthMiddleware, /healthz, /mcp mount, /upload
  - phase: 03-container-integration
    provides: MCP Resources (mare://cases/<case>/<artifact>), ARTIFACTS tuple, _safe_artifact_path
  - phase: 04-external-client-integration
    provides: Plan 04 (templates/mastra/ starter with stdout markers), Plan 03 (resources tool surface)
provides:
  - "E2E test suite under mcp-gateway/tests/e2e/ (10 tests across 3 test files)"
  - "Session-scoped fixtures: gateway_url, bearer_token, gateway_alive, mcp_client, unauthed_client"
  - "CLI-01 coverage: raw-MCP smoke + 401 auth-bypass tests"
  - "CLI-04 coverage: resources/list + resources/read + missing-artifact + traversal tests"
  - "CLI-02 coverage: mastra starter subprocess test with stdout marker assertions"
affects: [ci-pipeline, future-e2e-tests]

# Tech tracking
tech-stack:
  added: [httpx (e2e client), pytest (session-scoped fixtures)]
  patterns: ["env-driven skip semantics (pytest.skip on missing gateway/npm/sample)", "httpx.Client as raw MCP JSON-RPC client", "subprocess.run with shell=False + timeout for Node.js tests"]

key-files:
  created:
    - mcp-gateway/tests/e2e/__init__.py
    - mcp-gateway/tests/e2e/conftest.py
    - mcp-gateway/tests/e2e/test_claude_code_smoke.py
    - mcp-gateway/tests/e2e/test_resources.py
    - mcp-gateway/tests/e2e/test_mastra_starter.py
  modified: []

key-decisions:
  - "Session-scoped httpx.Client (not mcp Python SDK ClientSession) for raw JSON-RPC control over Streamable HTTP"
  - "gateway_url fixture strips /mcp suffix so tests append it explicitly — avoids double-/mcp/mcp on base_url"
  - "mastra test uses shutil.copytree into tmp_path to keep node_modules out of repo"

patterns-established:
  - "E2E fixtures resolve config from env first, then file fallback, then pytest.skip — never hard-fail"
  - "Auth-bypass tests use unauthed_client (no Authorization header) and wrong-bearer httpx.post — both assert 401"
  - "Path-traversal test posts encoded ../ in case slot — asserts error or 4xx, never 200 with foreign content"

requirements-completed: [CLI-01, CLI-02, CLI-04]

# Metrics
duration: 3min
completed: 2026-04-27
---

# Phase 4 Plan 5: E2E Test Suite Summary

**10 e2e tests across 3 files with session-scoped fixtures, skip-cleanly semantics, and auth/traversal coverage (CLI-01, CLI-02, CLI-04)**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-27T08:37:31Z
- **Completed:** 2026-04-27T08:41:24Z
- **Tasks:** 3
- **Files modified:** 5

## Accomplishments
- E2E test suite with 10 tests covering Claude Code raw-MCP smoke, MCP Resources flow, and mastra starter subprocess
- Auth-bypass coverage (missing + wrong bearer → 401) and path-traversal rejection (T-04-01, T-04-02)
- All tests skip cleanly when gateway/npm/sample unavailable — zero hard failures

## Task Commits

Each task was committed atomically:

1. **Task 1: Create tests/e2e/__init__.py + conftest.py** - `b95f9de` (feat)
2. **Task 2: Create test_claude_code_smoke.py + test_resources.py** - `af2d43c` (feat)
3. **Task 3: Create test_mastra_starter.py** - `11ac39c` (feat)

**Plan metadata:** pending (docs commit follows)

## Files Created/Modified
- `mcp-gateway/tests/e2e/__init__.py` - Empty package marker for pytest discovery
- `mcp-gateway/tests/e2e/conftest.py` - Session-scoped fixtures (gateway_url, bearer_token, gateway_alive, mcp_client, unauthed_client) with env/file/skip chain
- `mcp-gateway/tests/e2e/test_claude_code_smoke.py` - CLI-01 raw-MCP smoke (4 tests): initialize→tools/list, tools/call, missing-bearer-401, wrong-bearer-401
- `mcp-gateway/tests/e2e/test_resources.py` - CLI-04 resources flow (5 tests): mare:// URI scheme, MIME types, read content, missing-artifact error, traversal rejection
- `mcp-gateway/tests/e2e/test_mastra_starter.py` - CLI-02 mastra starter (1 test): npm install + npm start with stdout marker assertions

## Decisions Made
- Used raw httpx.Client (not mcp SDK ClientSession) for JSON-RPC control — the mcp SDK's ClientSession would obscure the wire format and make auth-bypass testing harder
- gateway_url fixture strips /mcp so tests append it explicitly — prevents double-mount path bugs
- mastra test copies template to tmp_path via shutil.copytree — keeps node_modules out of the repo tree and enables parallel runs

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- E2E test suite complete and verified (collects 10 tests, skips cleanly)
- Ready for Plan 06 (remaining phase 4 work)
- When gateway is running, full e2e suite validates auth, resources, and mastra client integration

---
*Phase: 04-external-client-integration*
*Completed: 2026-04-27*

## Self-Check: PASSED
