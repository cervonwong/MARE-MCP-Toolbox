---
phase: 04-external-client-integration
plan: 02
subsystem: infra
tags: [bash, shell, mcp-gateway, cli, run_docker]

# Dependency graph
requires:
  - phase: 03-container-integration
    provides: "run_docker.sh --remote mode with ready-block (D-07) and token file at workspace/.mcp-gateway-token"
provides:
  - "print_ready_block() shell function extracted from --remote ready-block heredoc"
  - "--print-config flag: re-renders the gateway connection block from the token file without starting the container"
  - "Subprocess test suite for both --print-config success and missing-token failure paths"
affects: [04-external-client-integration, claude-code-client-onboarding, mastra-ai-client]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shell function extraction: reusable print_ready_block(token, host_bind, host_port) called from both --remote and --print-config"
    - "Early exit mode: --print-config dispatched immediately after HOST_PWD is set, before buildx/compose chain"
    - "Staged-script testing: shutil.copy2 run_docker.sh into tmp_path with sibling workspace/ so HOST_PWD lands in tmp_path"

key-files:
  created:
    - mcp-gateway/tests/test_print_config.py
  modified:
    - run_docker.sh

key-decisions:
  - "Place --print-config handler immediately after HOST_PWD is set (before buildx), not with the mode-dispatch block, so the flag short-circuits before any docker calls"
  - "Function signature print_ready_block(token, host_bind, host_port) with 3 positional args covers both --remote (env vars already exported) and --print-config (env var defaults via :-)"

patterns-established:
  - "Pattern: staged-script subprocess test — copy script into tmp_path, create sibling workspace/ dir, override HOST_PWD implicitly via SCRIPT_DIR"

requirements-completed: [CLI-01]

# Metrics
duration: 20min
completed: 2026-04-27
---

# Phase 4 Plan 02: --print-config Flag Summary

**`print_ready_block()` shell function extracted from `--remote` ready-block; new `--print-config` flag reads `workspace/.mcp-gateway-token` and re-renders the Claude Code connection block without touching Docker**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-04-27T08:00:00Z
- **Completed:** 2026-04-27T08:20:00Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Extracted the gateway ready-block heredoc (D-07) into a reusable `print_ready_block(token, host_bind, host_port)` shell function
- Added `--print-config` flag that short-circuits before any Docker/buildx invocations, reads the token file, and calls the function
- Both `--remote` post-up and `--print-config` now call the same function — single source of truth for the connection block shape
- Subprocess-based pytest suite verifies all three paths: help text, missing-token error, and success with token in output

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor run_docker.sh — extract print_ready_block() and add --print-config flag** - `be71723` (feat)
2. **Task 2: Add unit test for --print-config (success + missing-token paths)** - `6cfac7c` (test)

## Files Created/Modified

- `run_docker.sh` - Added `--print-config` case to flag parser, `print_ready_block()` function after flag parser, early-exit handler after `HOST_PWD` assignment, replaced `--remote` heredoc block with single function call
- `mcp-gateway/tests/test_print_config.py` - Subprocess tests: `test_help_documents_print_config`, `test_print_config_missing_token_exits_nonzero`, `test_print_config_with_token_emits_ready_block`

## Decisions Made

- Placed the `--print-config` mode handler immediately after `HOST_PWD="$SCRIPT_DIR/workspace"` (line ~86) rather than in the mode-dispatch block near the end of the script. This ensures the flag exits before triggering buildx, MCP repo cloning, or any docker calls — the intent is zero side effects.
- Function signature takes 3 positional args so both call sites can pass explicit values: `--remote` passes exported env vars, `--print-config` passes `${MCP_GATEWAY_HOST_BIND:-0.0.0.0}` defaults.

## Deviations from Plan

None - plan executed exactly as written, with one minor structural clarification: the plan said to place the `--print-config` handler "BEFORE the local-mode `if [[ "$MODE" == "local" ]]` block" but placing it there would still run buildx/BN/IDA setup first. Moved it to immediately after `HOST_PWD` is set instead, which is the correct interpretation of "no container action" — verified the plan author's research (Pattern 6) confirms this intent.

## Issues Encountered

- The worktree was initialized from an old branch (`3e97b07`, pre-Phase 3) rather than the Phase 4 base. After `git reset --soft 03d6b64f`, the working tree still reflected the old branch's file state. Resolved by restoring `run_docker.sh` from the target base commit before making changes, and committing only `run_docker.sh` (staged individually) to avoid including unrelated working-tree differences.

## Next Phase Readiness

- `./run_docker.sh --print-config` is fully functional: reads token, renders ready-block, exits 0; or errors and exits 1 if no token file
- Other Phase 4 plans can rely on this flag for Claude Code onboarding documentation
- No blockers

---
*Phase: 04-external-client-integration*
*Completed: 2026-04-27*
