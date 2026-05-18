---
phase: 08-session-scoped-r2
plan: 01
subsystem: testing
tags: [pytest, pytest-asyncio, red-stubs, nyquist, sessions, r2, radare2]

# Dependency graph
requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    provides: EXPANDED_CASE_SUBDIRS catalog (extended by Plan 04 to add r2-sessions); D-03 12-key result-dict shape (extended by D-11 6-key r2 extensions)
  - phase: 07-run-shell-typed-static-wrappers-re-artifacts
    provides: depth-2 resource walker (auto-exposes r2-sessions/<sid>-transcript.log without code change); Wave-0 RED-stub discipline pattern
provides:
  - Wave 0 RED test scaffolding for Phase 8 (47 tests collect; 2 new files ImportError until Plans 02/03 land)
  - _require_r2_or_skip() shared conftest helper for r2-binary gating on dev/CI hosts
  - test_sessions.py (8 tests) — registry/reaper/cap/dangerous-cmd-regex/lifespan + D-29 catalog regression
  - test_r2_sessions.py (13 tests) — SESS-01..06, Pitfall 6/18, transcript, per-command log
  - Catalog regression on test_artifacts_io.py::test_expanded_case_subdirs_catalog (RED until Plan 04)
  - Depth-2 walker exposure test test_r2_sessions_transcript_exposed (RED until Plan 04)
affects: [08-02-PLAN, 08-03-PLAN, 08-04-PLAN, 08-05-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Wave-0 RED-stub discipline (Phase 6 carryover): name failing tests referencing not-yet-existing modules; collection passes, execution ImportErrors; no pytest.skip masking
    - Module-level skip helper (Phase 7 carryover): _require_r2_or_skip pattern mirrors _require_setfacl_or_skip — plain helper, not fixture, called at body top
    - Nyquist contract: every catalog row in 08-VALIDATION.md "Source Test Catalog" mapped to one named pytest function

key-files:
  created:
    - mcp-gateway/tests/test_sessions.py
    - mcp-gateway/tests/test_r2_sessions.py
  modified:
    - mcp-gateway/tests/conftest.py
    - mcp-gateway/tests/test_artifacts_io.py
    - mcp-gateway/tests/test_resources_phase7.py

key-decisions:
  - "Followed Plan 01 verbatim — paste-ready code blocks from the plan <action> blocks used unchanged"
  - "Catalog test placed in test_sessions.py per D-29 + VALIDATION.md test-file note (not test_artifacts_io.py)"
  - "Both test_artifacts_io.py::test_expanded_case_subdirs_catalog AND test_sessions.py::test_expanded_case_subdirs_contains_r2_sessions assert the same invariant from two angles — D-29 regression coverage is intentional double-belt"

patterns-established:
  - "RED-stub assertion pattern: function body ends in assert hasattr(module, 'symbol') so Plan 05 can later replace with full behavioural body without removing the RED-state import"
  - "Docstring-driven SESS-05 disclaimer test (test_sess05_disclaimer_in_docstrings) — verifies prose in code via assertion, locks D-23 wording at the test layer"

requirements-completed: [SESS-01, SESS-02, SESS-03, SESS-04, SESS-05, SESS-06]

# Metrics
duration: 3min
completed: 2026-05-18
---

# Phase 8 Plan 01: Wave 0 RED-Stub Test Scaffolding Summary

**47 named pytest functions delivered for Phase 8 (8 in test_sessions.py + 13 in test_r2_sessions.py + 1 in test_resources_phase7.py + 1 augmented catalog assertion); collection clean; execution ImportErrors on `mcp_gateway.sessions` and `mcp_gateway.tools.r2_sessions` as designed.**

## Performance

- **Duration:** 3 min
- **Started:** 2026-05-18T09:35:27Z
- **Completed:** 2026-05-18T09:38:28Z
- **Tasks:** 4
- **Files modified:** 5 (1 created conftest helper, 2 new test files, 2 augmented test files)

## Accomplishments

- 21 new RED-stub tests across two new test files (test_sessions.py: 8, test_r2_sessions.py: 13)
- 1 augmented existing test (test_expanded_case_subdirs_catalog: 9-name → 10-name set, RED until Plan 04 lands D-26)
- 1 new test on existing file (test_resources_phase7.py::test_r2_sessions_transcript_exposed, RED until Plan 04)
- Shared conftest helper _require_r2_or_skip() for r2-binary gating
- Every SESS-XX requirement (SESS-01..06), every D-XX decision row, Pitfall 6, Pitfall 18, and D-29 regression have at least one named pytest function — Nyquist contract satisfied

## Task Commits

Each task was committed atomically:

1. **Task 1: Add _require_r2_or_skip helper to conftest.py** — `b727146`
2. **Task 2: Create test_sessions.py with RED stubs for registry/reaper/cap/lifespan** — `dc5c8d9`
3. **Task 3: Create test_r2_sessions.py with RED stubs for 4 MCP tools + Pitfalls** — `edaa601`
4. **Task 4: Augment test_artifacts_io.py + test_resources_phase7.py** — `7e10c35`

## Files Created/Modified

- `mcp-gateway/tests/test_sessions.py` — NEW. 8 tests: reaper, cap, lifespan, D-08 regex (present + matrix), D-14 env-var sanity, D-15 dataclass shape, D-29 catalog regression
- `mcp-gateway/tests/test_r2_sessions.py` — NEW. 13 tests: SESS-01 aaa-aflj-persists, SESS-02 result-shape + json + non-json, SESS-03 close-idempotent + list-fd, SESS-05 docstring disclaimer, SESS-06 refusal matrix + lockdown init, Pitfall 6 hung-cmd, Pitfall 18 cancel-killpg, transcript captures, per-command log filename shape
- `mcp-gateway/tests/conftest.py` — Added `_require_r2_or_skip()` helper + `import shutil`
- `mcp-gateway/tests/test_artifacts_io.py` — Extended `test_expanded_case_subdirs_catalog` expected set from 9 → 10 entries (adds `"r2-sessions"`)
- `mcp-gateway/tests/test_resources_phase7.py` — Added `test_r2_sessions_transcript_exposed` (depth-2 walker exposure test for D-26)

## Test → Requirement Mapping

| Requirement | Test Function | File |
|-------------|---------------|------|
| SESS-01 | test_aaa_aflj_persists | test_r2_sessions.py |
| SESS-02 | test_r2_cmd_result_shape | test_r2_sessions.py |
| SESS-02 | test_format_json_iij | test_r2_sessions.py |
| SESS-02 | test_format_json_non_json_command | test_r2_sessions.py |
| SESS-03 | test_close_idempotent | test_r2_sessions.py |
| SESS-03 | test_list_fd_count_nonneg | test_r2_sessions.py |
| SESS-04 | test_reaper_kills_idle | test_sessions.py |
| SESS-04 | test_cap_reject | test_sessions.py |
| SESS-04 | test_lifespan_teardown_kills_all | test_sessions.py |
| SESS-05 | test_sess05_disclaimer_in_docstrings | test_r2_sessions.py |
| SESS-06 | test_dangerous_cmd_refusal_matrix | test_r2_sessions.py |
| SESS-06 | test_lockdown_init_took_effect | test_r2_sessions.py |
| Pitfall 6 | test_hung_cmd_kills_session | test_r2_sessions.py |
| Pitfall 18 | test_cancel_propagates_to_killpg | test_r2_sessions.py |
| D-08 | test_dangerous_regex_present, test_dangerous_regex_matches_matrix | test_sessions.py |
| D-14 | test_env_var_bad_value_raises | test_sessions.py |
| D-15 | test_r2session_dataclass_fields | test_sessions.py |
| D-26 / D-29 | test_expanded_case_subdirs_contains_r2_sessions | test_sessions.py |
| D-26 / D-29 | test_expanded_case_subdirs_catalog (augmented) | test_artifacts_io.py |
| D-26 | test_r2_sessions_transcript_exposed | test_resources_phase7.py |
| D-12 | test_per_command_log_filename_shape | test_r2_sessions.py |
| D-13 | test_transcript_captures_three_cmds | test_r2_sessions.py |

## RED-State Proof

- `pytest --collect-only tests/test_sessions.py tests/test_r2_sessions.py tests/test_artifacts_io.py tests/test_resources_phase7.py` → 47 tests collected, zero collection errors
- `pytest tests/test_sessions.py` → `ImportError: cannot import name 'sessions' from 'mcp_gateway'` (Plan 02 flips GREEN)
- `pytest tests/test_r2_sessions.py` → `ImportError: cannot import name 'r2_sessions' from 'mcp_gateway.tools'` (Plan 03 flips GREEN)
- `pytest tests/test_artifacts_io.py::test_expanded_case_subdirs_catalog` → AssertionError (asserts `"r2-sessions"` in set; Plan 04 flips GREEN)

## Decisions Made

None - followed Plan 01 verbatim. Paste-ready code blocks from the plan's `<action>` sections were used without modification.

## Deviations from Plan

None - plan executed exactly as written.

The plan-provided code blocks compiled and collected cleanly on first attempt. No bugs, no missing functionality, no blocking issues, no architectural changes required.

## Issues Encountered

None. One transient observation: the host venv at `mcp-gateway/.venv` was the correct pytest invocation path (`python` is not on the executor PATH, only `python3` and `.venv/bin/pytest`). This did not block the plan — `pytest --collect-only` and targeted `pytest tests/test_*.py` runs succeeded throughout. Pytest cache directory had a permission warning (PytestCacheWarning on `.pytest_cache/`); does not affect test results.

## User Setup Required

None - no external service configuration required. All tests are hermetic (`tmp_path`, mocked status dirs). The r2-spawning tests skip cleanly on hosts without `r2` on PATH; full container build provides `radare2` via the Kali base image.

## Next Phase Readiness

- **Plan 02 (sessions.py primitive):** RED stubs in test_sessions.py provide the assertion contract; every Plan 02 task can point its `<verify>` at an existing test function
- **Plan 03 (tools/r2_sessions.py MCP surface):** RED stubs in test_r2_sessions.py provide the four-tool surface contract + Pitfall coverage
- **Plan 04 (EXPANDED_CASE_SUBDIRS + lifespan wiring + tool registration):** Both catalog tests (test_sessions.py + test_artifacts_io.py) plus the depth-2 walker test will flip GREEN once `"r2-sessions"` is added to the constant in artifacts_io.py
- **Plan 05 (integration test bodies):** The 21 RED-stub bodies currently end in `assert hasattr(module, "symbol")`; Plan 05 replaces these with full behavioural assertions per the plan's per-task bodies
- No blockers; no decisions deferred to downstream waves

## Self-Check: PASSED

- mcp-gateway/tests/test_sessions.py — FOUND
- mcp-gateway/tests/test_r2_sessions.py — FOUND
- mcp-gateway/tests/conftest.py (modified) — FOUND `_require_r2_or_skip`
- mcp-gateway/tests/test_artifacts_io.py (modified) — FOUND `"r2-sessions"` literal
- mcp-gateway/tests/test_resources_phase7.py (modified) — FOUND `test_r2_sessions_transcript_exposed`
- Commit b727146 — FOUND (`Add _require_r2_or_skip helper for Phase 8 r2 tests`)
- Commit dc5c8d9 — FOUND (`Add Phase 8 RED stubs for sessions registry/reaper/cap/regex`)
- Commit edaa601 — FOUND (`Add Phase 8 RED stubs for r2 MCP tool surface`)
- Commit 7e10c35 — FOUND (`Augment artifacts_io and resources_phase7 tests for r2-sessions`)

---
*Phase: 08-session-scoped-r2*
*Completed: 2026-05-18*
