---
phase: 04-external-client-integration
plan: 01
subsystem: infra
tags: [mcp, claude-code, bearer-auth, streamable-http, template]

# Dependency graph
requires:
  - phase: 03-container-integration
    provides: run_docker.sh --remote ready-block that defined the JSON shape this template replicates
provides:
  - Claude Code .mcp.json template with env-var expansion for MARE_GATEWAY_TOKEN + MARE_GATEWAY_URL
  - Unit test locking template shape and rejecting banned transports (mcp-remote, SSE, MastraMCPClient)
affects: [04-external-client-integration, mastra-integration, end-user-onboarding]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "CC template uses ${VAR:-default} env-var expansion so the same file works across machines without editing"
    - "Banned tech list (mcp-remote CVE-2025-6514, SSE, MastraMCPClient) enforced in unit test"

key-files:
  created:
    - templates/claude-code/.mcp.json
    - mcp-gateway/tests/test_claude_code_template.py
  modified: []

key-decisions:
  - "Template URL uses ${MARE_GATEWAY_URL:-http://localhost:8080/mcp} with inline default so users can copy-paste without editing"
  - "Auth field uses ${MARE_GATEWAY_TOKEN} without default — intentional: forces users to set the token explicitly"
  - "uv run requires --extra dev to pick up pytest; noted for future test runs in CI"

patterns-established:
  - "Pattern: All Phase 4 client integration env vars use MARE_GATEWAY_* prefix (RESEARCH Pitfall 8 lock)"

requirements-completed: [CLI-01, CLI-03]

# Metrics
duration: 10min
completed: 2026-04-27
---

# Phase 4 Plan 01: Claude Code .mcp.json Template Summary

**Checked-in `.mcp.json` template at `templates/claude-code/` with `type:http` + `${MARE_GATEWAY_TOKEN}` env-var expansion; 8-test suite enforces shape and rejects banned transports**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-27T08:00:00Z
- **Completed:** 2026-04-27T08:06:35Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Created `templates/claude-code/.mcp.json` matching the Phase 3 `run_docker.sh` ready-block shape, using `${MARE_GATEWAY_URL:-http://localhost:8080/mcp}` for the URL and `Bearer ${MARE_GATEWAY_TOKEN}` for the Authorization header
- Added 8-test suite in `mcp-gateway/tests/test_claude_code_template.py` covering: file existence, valid JSON, `type==http`, exact Authorization value, exact URL value, and parametrized rejection of three banned tokens (mcp-remote, MastraMCPClient, `"sse"`)
- All tests green (8/8 passed via `uv run --extra dev pytest`)

## Task Commits

Each task was committed atomically:

1. **Task 1: Create templates/claude-code/.mcp.json** - `6279225` (feat)
2. **Task 2: Add unit test for CC template JSON shape** - `832cd43` (test)

**Plan metadata:** see final commit below

## Files Created/Modified

- `templates/claude-code/.mcp.json` - Claude Code MCP config template with Streamable HTTP transport and env-var expansion (D-10)
- `mcp-gateway/tests/test_claude_code_template.py` - Unit tests asserting JSON shape and banning deprecated transports (CLI-01, CLI-03)

## Decisions Made

- Template URL uses `${MARE_GATEWAY_URL:-http://localhost:8080/mcp}` with inline default; enables copy-paste without editing for default local deployments
- Authorization uses `Bearer ${MARE_GATEWAY_TOKEN}` without a default — intentional to force explicit token configuration (security: no accidental anonymous access)
- `uv run` requires `--extra dev` to include pytest; this matches pyproject.toml's `[dev]` optional-dependency group

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- `uv` not installed in worktree shell environment. Installed via `curl -LsSf https://astral.sh/uv/install.sh | sh` (Rule 3 - blocking). Tests then ran successfully.
- `uv run pytest` fails without `--extra dev` (pytest is a dev dependency, not a main dependency). Used `uv run --extra dev pytest` to resolve.

## User Setup Required

None - no external service configuration required. The template is a static file; users copy it and export `MARE_GATEWAY_TOKEN` and optionally `MARE_GATEWAY_URL` before starting Claude Code.

## Next Phase Readiness

- Claude Code template ready; users can connect to the container gateway using `export MARE_GATEWAY_TOKEN=<token from run_docker.sh --remote output>` then reference the template
- Mastra.ai integration (Plan 02) can proceed independently — template for that client is a separate file

---

## Threat Coverage

| Threat | Mitigation | Verified |
|--------|-----------|---------|
| T-04-T1 (token disclosure) | `${MARE_GATEWAY_TOKEN}` env-var expansion — no hardcoded token in template | `grep -qE 'Bearer [A-Za-z0-9_-]{16,}'` returns false |
| T-04-T2 (deprecated transport) | `test_template_no_banned_tech` parametrized test rejects mcp-remote, MastraMCPClient, "sse" | 3/3 parametrize cases PASSED |

## Self-Check: PASSED

- `templates/claude-code/.mcp.json` — FOUND
- `mcp-gateway/tests/test_claude_code_template.py` — FOUND
- Commit `6279225` — FOUND
- Commit `832cd43` — FOUND

---
*Phase: 04-external-client-integration*
*Completed: 2026-04-27*
