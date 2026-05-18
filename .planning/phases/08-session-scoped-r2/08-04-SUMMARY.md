---
phase: 08-session-scoped-r2
plan: 04
subsystem: integration
tags: [lifespan, register-tools, expanded-case-subdirs, session-registry, wiring]

# Dependency graph
requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    provides: EXPANDED_CASE_SUBDIRS catalog (extended here with "r2-sessions"), confine_to + ensure_subdir
  - phase: 07-run-shell-typed-static-wrappers-re-artifacts
    provides: register_all_tools pattern (D-16) + collision_check.assert_no_collisions (D-11) + depth-2 resource walker that auto-exposes r2-sessions/<sid>-transcript.log
  - phase: 08-session-scoped-r2 (Plan 02)
    provides: SessionRegistry async-context-manager primitive + MAX_SESSIONS, SESSION_IDLE_S, REAPER_INTERVAL_S module constants (D-14 single-source-of-truth)
  - phase: 08-session-scoped-r2 (Plan 03)
    provides: tools/r2_sessions.py with register(mcp) wiring 4 MCP tools (open_r2_session, r2_cmd, close_r2_session, list_sessions)
provides:
  - mcp-gateway/src/mcp_gateway/artifacts_io.py — EXPANDED_CASE_SUBDIRS extended to 10 entries (last = "r2-sessions")
  - mcp-gateway/src/mcp_gateway/session_state.py — SESSION_REGISTRY: Optional[SessionRegistry] = None slot + GW-V2-03 caveat update (SESS-05 cross-bearer-token sharing)
  - mcp-gateway/src/mcp_gateway/tools/__init__.py — r2_sessions imported in the local-import tuple + r2_sessions.register(mcp) called BEFORE backend_passthrough.register(mcp)
  - mcp-gateway/src/mcp_gateway/app.py — SessionRegistry block in BOTH lifespan branches (with-backend and SKIP_BACKEND=1), placed INSIDE PinnedBackend AND AFTER assert_no_collisions, constructed from sessions module constants (NOT os.environ re-read)
affects: [08-05-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "D-14 single-source-of-truth: app.py imports validated MAX_SESSIONS, SESSION_IDLE_S, REAPER_INTERVAL_S from sessions module (which read+sanity-checked them at import) instead of re-reading os.environ at lifespan time. Avoids parallel-source-of-truth + bypass of RuntimeError sanity check."
    - "Nested async-context-manager unwind LIFO order: SessionRegistry inside PinnedBackend means r2 processes are killpg'd BEFORE backend ClientSession is torn down — no zombie r2 survives container teardown (threat T-08-04-02)."
    - "_build_registry() closure inside lifespan keeps the param-binding logic in one place across both branches (DRY); both branches call the same factory."

key-files:
  created:
    - .planning/phases/08-session-scoped-r2/08-04-SUMMARY.md
  modified:
    - mcp-gateway/src/mcp_gateway/artifacts_io.py
    - mcp-gateway/src/mcp_gateway/session_state.py
    - mcp-gateway/src/mcp_gateway/tools/__init__.py
    - mcp-gateway/src/mcp_gateway/app.py
    - mcp-gateway/tests/test_resources_phase7.py
    - mcp-gateway/tests/test_tool_list.py

key-decisions:
  - "Followed Plan 04 verbatim — paste-ready code blocks from <action> used unchanged; both diff hunks land as designed; D-14 single-source-of-truth invariant preserved (no env-var re-reads in app.py)."
  - "Fixed Rule 1 bug in pre-existing Plan 01 test_r2_sessions_transcript_exposed: case_dir name 'alpha' did not match CASE_NAME_RE=^\\d{3}-.+ so _list_cases() returned [] and the walker never saw the seeded transcript. Renamed to '304-r2sess' to match the regex consistently with sibling tests (300-depth2, 301-deep, 302-hidden, 303-cap)."
  - "Rule 2 update to test_tool_list.EXPECTED_TOOLS: added the 4 new r2-session tools (open_r2_session, r2_cmd, close_r2_session, list_sessions) so test_no_unexpected_tools recognises the new surface. Total expected tool count goes from 39 (Phase 7) to 43 (Phase 8)."

patterns-established:
  - "Phase 8 SessionRegistry slot uses TYPE_CHECKING import for SessionRegistry to avoid runtime circular import (sessions.py is the primitive; session_state.py is even more primitive — only stdlib + typing at runtime)"
  - "Lifespan branches share a _build_registry() closure so both with-backend and SKIP_BACKEND=1 paths get IDENTICAL parameter sourcing (no drift risk)"

requirements-completed: [SESS-04, SESS-05]

# Metrics
duration: 6min
completed: 2026-05-18
---

# Phase 8 Plan 04: Integration Wiring Summary

Delivered the 4 tiny extensions that turn Plans 02 (sessions.py) + 03 (tools/r2_sessions.py) into a live surface on a running gateway. Starting the gateway now boots the SessionRegistry inside `app.py::lifespan` (both branches), exposes the four r2-session MCP tools through `register_all_tools`, and on shutdown LIFO-unwinds the registry BEFORE the PinnedBackend — killing every r2 process so no zombies survive teardown.

## Performance

- **Duration:** ~6 min
- **Started:** 2026-05-18T09:51:12Z (orchestrator handoff)
- **Tasks:** 2
- **Files modified:** 4 source + 2 tests (test fixes)
- **Files created:** 1 (this SUMMARY)

## Diff Hunk Summaries

| File | Lines added | Lines removed | Change |
|------|-------------|---------------|--------|
| `mcp-gateway/src/mcp_gateway/artifacts_io.py` | +2 | 0 | Append `"r2-sessions"` to EXPANDED_CASE_SUBDIRS (10 entries) + Phase 8 D-26 comment |
| `mcp-gateway/src/mcp_gateway/session_state.py` | +7 | 0 | Add SESSION_REGISTRY slot + TYPE_CHECKING import + GW-V2-03 caveat extension (SESS-05 cross-bearer-token sharing) |
| `mcp-gateway/src/mcp_gateway/tools/__init__.py` | +9 | 0 | Add `r2_sessions` to local-import tuple + `r2_sessions.register(mcp)` before `backend_passthrough.register(mcp)` + Phase 8 docstring section |
| `mcp-gateway/src/mcp_gateway/app.py` | +50 | 17 | Add `from .sessions import SessionRegistry, MAX_SESSIONS, SESSION_IDLE_S, REAPER_INTERVAL_S`; rewrite both lifespan branches with `_build_registry()` closure + nested `async with` around `mcp.session_manager.run()` + finally pair |

Test fixes (Rule 1 / Rule 2 deviations):

| File | Lines added | Lines removed | Change |
|------|-------------|---------------|--------|
| `mcp-gateway/tests/test_resources_phase7.py` | +2 | 1 | Rule 1 — Fix Plan 01 case-name bug: "alpha" did not match CASE_NAME_RE; renamed to "304-r2sess" to match sibling tests (300-depth2, 301-deep, 302-hidden, 303-cap) |
| `mcp-gateway/tests/test_tool_list.py` | +6 | 0 | Rule 2 — Add 4 new r2-session tools to EXPECTED_TOOLS so `test_no_unexpected_tools` recognises the expanded Phase 8 surface (39 → 43 tools) |

## Task Commits

- **Task 1: Extend artifacts_io.EXPANDED_CASE_SUBDIRS + session_state SESSION_REGISTRY slot** — `cd82a7b` `Add r2-sessions to EXPANDED_CASE_SUBDIRS and SESSION_REGISTRY slot for Phase 8 (D-07, D-26)`
- **Task 2: Wire r2_sessions into register_all_tools + app.py lifespan** — `3d4f027` `Wire r2_sessions tool + SessionRegistry lifespan block for Phase 8 (D-05, D-14, D-24)`

## Lifespan Ordering Proof (D-24)

Annotated `grep -n` over `app.py` for the 5 markers (`PinnedBackend`, `assert_no_collisions`, `SessionRegistry`, `session_manager.run`, `SESSION_REGISTRY`):

```
 19: from .backend.client import PinnedBackend                # import only
 21: from .tools.collision_check import assert_no_collisions  # import only
 23:     SessionRegistry,                                     # import only
 70: (docstring mention)
 72: (docstring mention)
 93: # D-14 + D-24: SessionRegistry parameters …             # comment
 97: def _build_registry() -> SessionRegistry:                # closure
 98:     return SessionRegistry(                              # constructed from sessions constants
110:                await assert_no_collisions(mcp)           # ① no-backend branch — collision check
111: # Phase 8 D-24: SessionRegistry also active on no-backend path …
114:                    session_state.SESSION_REGISTRY = registry  # ② set on entry
116:                        async with mcp.session_manager.run():  # ③ serve
124:                        session_state.SESSION_REGISTRY = None  # ④ reset in finally
130:        async with PinnedBackend(backend_name) as pinned:      # ⓐ with-backend branch
135: # PinnedBackend.__aenter__ has populated tool_cache …
138:                await assert_no_collisions(mcp)                # ⓑ collision check
139: # Phase 8 D-24: SessionRegistry block lives INSIDE the …
142: # BEFORE PinnedBackend's __aexit__ fires (LIFO unwind) …
145:                    session_state.SESSION_REGISTRY = registry  # ⓒ set on entry
147:                        async with mcp.session_manager.run():  # ⓓ serve
161:                        session_state.SESSION_REGISTRY = None  # ⓔ reset in finally
```

**Required D-24 ordering:** `PinnedBackend → assert_no_collisions → _build_registry/SessionRegistry → mcp.session_manager.run() → yield`. Both branches satisfy this — verified programmatically by `awk` ordering check (4 "ok" emissions = 2 branches × 2 ordering pairs).

## D-14 Single-Source-of-Truth Proof

```
$ grep -c "MCP_GATEWAY_MAX_SESSIONS\|MCP_GATEWAY_SESSION_IDLE_S\|MCP_GATEWAY_REAPER_INTERVAL_S" mcp-gateway/src/mcp_gateway/app.py
0
```

Zero matches — `app.py` reads NONE of the three env vars directly. All three module-constants are imported from `mcp_gateway.sessions` (Plan 02), which reads + sanity-checks them ONCE at import time (RuntimeError on bad parses or negative values per D-14). This is the single source of truth that threat T-08-04-06 (bypassing D-14 via parallel env reads) mitigates.

## Test-Flip Table

| Test | Before this plan | After this plan | Source Plan |
|------|------------------|-----------------|-------------|
| `test_expanded_case_subdirs_contains_r2_sessions` | RED (assertion: "r2-sessions" not in catalog) | **GREEN** (D-26 catalog extended) | Plan 01 |
| `test_expanded_case_subdirs_catalog` (augmented) | RED (catalog mismatched expected set) | **GREEN** (10 entries, including r2-sessions) | Plan 01 + this plan |
| `test_r2_sessions_transcript_exposed` | RED (case "alpha" did not match CASE_NAME_RE; walker found 0 resources) | **GREEN** (case "304-r2sess" matches, walker exposes the transcript at depth 2) | Plan 01 (bug-fix via this plan's Rule 1 deviation) |
| `test_no_unexpected_tools` | unintentionally RED (4 new tools registered, EXPECTED_TOOLS lacked them) | **GREEN** (EXPECTED_TOOLS extended by Rule 2) | Phase 7 test (Plan 04 contract addition) |
| `test_all_expected_tools_present` | already GREEN | **GREEN** (still covers all v1.0 + Phase 7 tools; now also asserts Phase 8 tools present) | Phase 7 test |
| `test_tool_count_in_range` | GREEN (39 tools, within 35-50) | **GREEN** (43 tools, within 35-50) | Phase 7 test |

`pytest tests/` → **248 passed, 44 skipped, 1 failed** — the 1 failure is `tests/test_acl_available.py::test_setfacl_on_path` (pre-existing host environment failure: `setfacl` is not on the executor host; container Kali image provides it). This is out-of-scope per scope boundary and is tracked already in STATE.md decisions.

## Build Sanity

```
$ cd mcp-gateway && MCP_GATEWAY_SKIP_BACKEND=1 MCP_GATEWAY_TOKEN_FILE=/tmp/mcp-gateway-token .venv/bin/python -c "from mcp_gateway.app import build_app; app = build_app(); print('app built ok')"
[gateway] MCP_GATEWAY_SKIP_BACKEND=1 -- backend detection bypassed (test mode)
[resources] registered mare://cases/<case>/<artifact> (13 depth-1 artifact slots × dynamic case set; Phase 7 D-26: + depth-2 walk over 10 EXPANDED_CASE_SUBDIRS, capped at MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES=1024, depth=2)
app built ok
```

The resources log line confirms the walker now sees the 10-entry EXPANDED_CASE_SUBDIRS (vs. 9 before this plan).

```
$ cd mcp-gateway && .venv/bin/python -c "from mcp_gateway.app import build_app; from mcp_gateway import session_state; assert hasattr(session_state, 'SESSION_REGISTRY')"
$ echo $?
0
```

## D-XX Coverage Table

| Decision | Implementation in this plan |
|---------|-----------------------------|
| D-05 | `r2_sessions` added to local-import tuple in `tools/__init__.py::register_all_tools` + `r2_sessions.register(mcp)` invoked before `backend_passthrough.register(mcp)` (matches Phase 7 D-16 convention) |
| D-07 | `session_state.SESSION_REGISTRY: Optional["SessionRegistry"] = None` slot with `TYPE_CHECKING` import; GW-V2-03 caveat extended to mention SESS-05 cross-bearer-token sharing |
| D-14 | Lifespan imports + uses validated `MAX_SESSIONS`, `SESSION_IDLE_S`, `REAPER_INTERVAL_S` module constants from `mcp_gateway.sessions` — NOT `os.environ.get(...)` re-reads (negative-grep proves 0 matches) |
| D-24 | SessionRegistry block in BOTH lifespan branches: INSIDE `PinnedBackend` block, AFTER `assert_no_collisions(mcp)`, AROUND `mcp.session_manager.run()`; `session_state.SESSION_REGISTRY` set on entry and reset to None in finally; identical structure in no-backend branch (no PinnedBackend wrap) |
| D-25 | No new collision check needed — Phase 7's `assert_no_collisions(mcp)` already covers ALL gateway-native tool names; the new r2-session tools are picked up automatically by the existing check |
| D-26 | `EXPANDED_CASE_SUBDIRS` grew to 10 entries (last = "r2-sessions"); Phase 7 D-26 depth-2 walker automatically exposes `mare://cases/<case>/r2-sessions/<sid>-transcript.log` (proven by `test_r2_sessions_transcript_exposed` GREEN) |

## Decisions Made

1. Followed Plan 04 verbatim — both diff hunks pasted exactly as written; D-14 single-source-of-truth invariant preserved; ordering invariants from D-24 satisfied in both branches.
2. (Rule 1) Bug-fix the pre-existing Plan 01 walker test by renaming the seed-case from "alpha" to "304-r2sess" so it matches `CASE_NAME_RE = ^\d{3}-.+` — this is consistent with every other test in the same file.
3. (Rule 2) Extend `EXPECTED_TOOLS` in `test_tool_list.py` to include the 4 newly-registered r2-session tools — without this the post-D-05 surface would unintentionally trip `test_no_unexpected_tools`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed Plan 01 walker test using non-matching case_dir name**

- **Found during:** Task 2 verification
- **Issue:** `test_r2_sessions_transcript_exposed` (added by Plan 01 commit `7e10c35`) seeded a case named `"alpha"`. But `_list_cases()` in `tools/resources.py` filters by `CASE_NAME_RE = re.compile(r"^\d{3}-.+")`, so "alpha" was never enumerated and the depth-2 walker had zero cases to walk → resources list was empty → assertion failed.
- **Fix:** Renamed the seed-case to `"304-r2sess"` (continues the numbering sequence used by the file's sibling tests: 300-depth2, 301-deep, 302-hidden, 303-cap). Added an inline comment explaining the regex requirement.
- **Files modified:** `mcp-gateway/tests/test_resources_phase7.py`
- **Commit:** `3d4f027`

**2. [Rule 2 - Missing critical functionality] Updated EXPECTED_TOOLS to include Phase 8 tools**

- **Found during:** Task 2 verification
- **Issue:** Registering the 4 new r2-session tools is the explicit goal of this plan, but `test_no_unexpected_tools` would (correctly per the test contract) flag them as unexpected because `EXPECTED_TOOLS` had only the v1.0 + Phase 7 tools. Without this update, the test surface would be inconsistent with the implementation surface this plan ships.
- **Fix:** Added the 4 r2-session tool names to `EXPECTED_TOOLS` and updated the module docstring to document the Phase 8 expansion (43 tools total). Did NOT change the 35-50 count range — 43 is comfortably inside it.
- **Files modified:** `mcp-gateway/tests/test_tool_list.py`
- **Commit:** `3d4f027`

## Authentication Gates

None — no external service interaction during this plan.

## Memory / Import Sanity

```
$ cd mcp-gateway && .venv/bin/python -c "from mcp_gateway.artifacts_io import EXPANDED_CASE_SUBDIRS; print(len(EXPANDED_CASE_SUBDIRS), EXPANDED_CASE_SUBDIRS[-1])"
10 r2-sessions

$ cd mcp-gateway && .venv/bin/python -c "from mcp_gateway import session_state; print(session_state.SESSION_REGISTRY)"
None

$ cd mcp-gateway && .venv/bin/python -c "from mcp_gateway.tools import register_all_tools; print(register_all_tools)"
<function register_all_tools at 0x...>

$ cd mcp-gateway && MCP_GATEWAY_SKIP_BACKEND=1 MCP_GATEWAY_TOKEN_FILE=/tmp/mcp-gateway-token .venv/bin/python -c "from mcp_gateway.app import build_app; build_app(); print('ok')"
[gateway] MCP_GATEWAY_SKIP_BACKEND=1 -- backend detection bypassed (test mode)
[resources] registered mare://cases/<case>/<artifact> (13 depth-1 artifact slots × dynamic case set; Phase 7 D-26: + depth-2 walk over 10 EXPANDED_CASE_SUBDIRS, capped at MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES=1024, depth=2)
ok
```

## Issues Encountered

The one Plan 01 walker-test bug (case name "alpha" not matching `CASE_NAME_RE`) was caught immediately by Task 2 verification. Pre-existing host-only failure on `test_setfacl_on_path` remains (executor host lacks `setfacl`; tracked in STATE.md, fixed inside container).

## User Setup Required

None — no external service configuration required. All target tests pass on this executor host; container image runs them too (with r2 binary available for the 12 currently-skipped integration tests).

## Next Phase Readiness

- **Plan 05 (integration test bodies):** All wiring is now live — `session_state.SESSION_REGISTRY` is populated for the duration of every lifespan; the 4 MCP tools are registered + visible via `list_tools()`; the depth-2 walker exposes `r2-sessions/<sid>-transcript.log`. Plan 05's behavioural test bodies (reaper kill, cap reject, lifespan teardown kills all, hung-cmd kills session, cancel propagates to killpg, aaa-aflj persists, format=json, transcript captures 3 cmds, etc.) can now exercise the live integrated surface inside a Starlette `LifespanContext` test.
- No blockers; no decisions deferred.

## Self-Check: PASSED

- `mcp-gateway/src/mcp_gateway/artifacts_io.py` — FOUND (EXPANDED_CASE_SUBDIRS has 10 entries; last = "r2-sessions")
- `mcp-gateway/src/mcp_gateway/session_state.py` — FOUND (SESSION_REGISTRY slot + TYPE_CHECKING import + SESS-05 caveat)
- `mcp-gateway/src/mcp_gateway/tools/__init__.py` — FOUND (r2_sessions in local-import tuple + `r2_sessions.register(mcp)` before `backend_passthrough.register(mcp)`)
- `mcp-gateway/src/mcp_gateway/app.py` — FOUND (SessionRegistry block in both branches, sourced from sessions module constants)
- Commit `cd82a7b` — FOUND (Task 1)
- Commit `3d4f027` — FOUND (Task 2)
- All 3 target integration tests GREEN: `test_expanded_case_subdirs_contains_r2_sessions`, `test_expanded_case_subdirs_catalog`, `test_r2_sessions_transcript_exposed`
- All `test_tool_list.py` tests GREEN
- `build_app()` imports + invokes cleanly under `MCP_GATEWAY_SKIP_BACKEND=1`
- D-14 negative grep: 0 env-var re-reads in `app.py` (single source of truth preserved)
- Ordering check: `awk '/assert_no_collisions/.../SessionRegistry|_build_registry/' ` prints `ok` ≥ 2 times (4 in practice, 2 per branch)

---
*Phase: 08-session-scoped-r2*
*Completed: 2026-05-18*
