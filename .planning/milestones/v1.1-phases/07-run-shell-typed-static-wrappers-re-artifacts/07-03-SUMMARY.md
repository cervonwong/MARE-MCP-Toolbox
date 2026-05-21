---
phase: 07-run-shell-typed-static-wrappers-re-artifacts
plan: 03
subsystem: collision-detection
tags: [collision-check, lifespan, sysexits, ex-config, fast-mcp, tdd, wave-1]

# Dependency graph
requires:
  - phase: 07-run-shell-typed-static-wrappers-re-artifacts (Wave 0 / 07-01)
    provides: tests/test_collision_check.py RED-stub (3 functions) + ModuleNotFoundError target
  - phase: 02-mcp-gateway
    provides: tools/backend_passthrough.py pattern (session_state.PINNED_BACKEND.tool_cache access; await mcp.list_tools()); session_state singleton
provides:
  - mcp_gateway.tools.collision_check.assert_no_collisions(mcp: FastMCP) async function
  - SystemExit(78) (EX_CONFIG per sysexits.h) on collision; structured error log via logger 'mcp_gateway.collision_check'
  - Empty backend / PINNED_BACKEND is None → returns cleanly
  - Sorted collision name list in error message (deterministic across runs)
affects: [07-08-PLAN]  # Wave 3 wires this into app.py::lifespan + updates tools/__init__.py + backend_passthrough.py comment

# Tech tracking
tech-stack:
  added: []  # stdlib (logging, sys) + existing mcp.server.fastmcp.FastMCP + existing session_state
  patterns:
    - "Module exports a single async function (assert_no_collisions) with NO register() — invoked directly by lifespan, not via @mcp.tool()"
    - "Public-API-only access to FastMCP (await mcp.list_tools()); no private _tool_manager / _mcp_server reads — enforced by acceptance grep"
    - "sys.exit(_EX_CONFIG) over raise RuntimeError to defeat Starlette/uvicorn lifespan exception translation (D-13a)"
    - "Module-level constant _EX_CONFIG = 78 documents sysexits.h(3) source for operator runbook grep"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/tools/collision_check.py
  modified:
    - mcp-gateway/tests/test_collision_check.py  # collision tool names switched from Phase-7-Wave-2 (run_xxd/run_file/run_die) to v1.0 surface (get_artifact / init_case / decompile) so tests are self-contained against Wave 1 gateway

key-decisions:
  - "Implemented verbatim from 07-03-PLAN action block (D-11..D-15 + D-13a); zero Python-side deviation."
  - "Updated test fixture collision names from `run_xxd`/`run_file`/`run_die` (Phase 7 Wave 2 tools, not yet registered) to `get_artifact`/`init_case`/`decompile` (existing v1.0 gateway-native tools). Rationale: D-12 explicitly requires the check to protect ALL gateway-native tools, not just `run_*` — so testing against v1.0 surface is MORE faithful to the design intent, AND makes the tests self-contained (no Wave 2 module-registration prerequisite)."

patterns-established:
  - "Wave-1-without-Wave-2 self-sufficiency: when a Wave 0 RED-stub assumes Wave 2 module surface (here: `run_xxd` etc. as gateway tools), the Wave 1 plan that delivers the depended-on module is free to retarget the test fixtures to whatever surface IS already registered at Wave 1 — the contract under test (collision-detection mechanism) is unchanged; only the test's collision-instance names change."

requirements-completed: []
# NOTE: STATIC-10 is the requirement in the plan frontmatter; per Phase 7 SUMMARY
# convention established in 07-01/02, requirement-marking is deferred to plan
# 07-08 (final Phase 7 plan). This plan delivers the implementation module that
# Wave 3 wires into app.py::lifespan; STATIC-10 flips to satisfied only after
# that wiring + image rebuild.

# Metrics
duration: ~12min
completed: 2026-05-13
---

# Phase 7 Plan 03: tools/collision_check.py Module Summary

**Wave 1 Plan B: created `tools/collision_check.py` (~67 LoC including module docstring) exporting `assert_no_collisions(mcp: FastMCP)` async function. Uses public `mcp.list_tools()` + `session_state.PINNED_BACKEND.tool_cache` to detect overlap; logs sorted collision names + backend label and calls `sys.exit(78)` (EX_CONFIG). All 3 Wave-0 RED tests in `test_collision_check.py` flip to GREEN. Test fixtures retargeted from not-yet-registered Phase 7 `run_*` tool names to existing v1.0 gateway-native tool names (`get_artifact`, `init_case`, `decompile`) so tests are self-contained against Wave 1's gateway surface — collision-detection contract unchanged, only the instance names change.**

## Performance

- **Duration:** ~12 minutes (longer than 07-02's 80s because of the Wave 0 test-fixture retarget analysis)
- **Started:** 2026-05-13T04:20:10Z
- **Completed:** 2026-05-13T04:32:00Z (approximate)
- **Tasks:** 1 (RED state was already in place from 07-01 Wave 0; GREEN commit + test-fixture retarget bundled in a single atomic commit `47e2e6a`)
- **Files created:** 1 (`tools/collision_check.py`)
- **Files modified:** 1 (`tests/test_collision_check.py` — fixture names only)

## Accomplishments

- **GREEN phase commit (47e2e6a):** Created `mcp-gateway/src/mcp_gateway/tools/collision_check.py` (67 lines including docstring; ~40 LoC excluding the module/function docstrings) with:
  - Module docstring documenting D-11..D-15 + D-13a invocation-site contract (lifespan AFTER register_all_tools AND AFTER PinnedBackend tool_cache population).
  - Stdlib-only imports: `logging`, `sys`. MCP-only public import: `from mcp.server.fastmcp import FastMCP`. Internal: `from .. import session_state`.
  - Module-level constant `_EX_CONFIG = 78` referencing sysexits.h(3).
  - Module-level logger `log = logging.getLogger("mcp_gateway.collision_check")` to match the caplog level filter in test 3.
  - `async def assert_no_collisions(mcp: FastMCP) -> None`: awaits `mcp.list_tools()`, reads `session_state.PINNED_BACKEND.tool_cache` via `getattr(..., "tool_cache", {})` (None-safe), computes `sorted(gateway_names & backend_names)`, returns cleanly on empty collision, else logs structured `FATAL: ...` message and calls `sys.exit(_EX_CONFIG)`.
  - NO `register(mcp)` function — confirmed by acceptance grep `grep -c "^def register" = 0`. Wave 3 wires this directly into `app.py::lifespan`.
- **Test-fixture retarget (same commit 47e2e6a):** Updated `tests/test_collision_check.py` so the colliding tool names in tests 2 and 3 are now v1.0 gateway-native names that the Wave-1 gateway surface DOES register:
  - Test 2: `run_xxd` → `get_artifact`.
  - Test 3: `run_xxd`, `run_file`, `run_die` → `init_case`, `get_artifact`, `decompile`. Alphabetical sort verification updated accordingly (decompile < get_artifact < init_case).
  - Test docstrings extended to document why the retarget was made (Wave-1-without-Wave-2 self-sufficiency).

## Task Commits

| Step | Description | Commit |
|------|-------------|--------|
| 1 (GREEN + test retarget) | Add `tools/collision_check.py` with `assert_no_collisions` for Phase 7 STATIC-10 | `47e2e6a` |

REFACTOR phase: not needed — paste-ready action block from 07-03-PLAN.md produced clean code; the test-fixture retarget is the only deviation and it's documented inline in test docstrings.

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/tools/collision_check.py` (NEW, 67 lines):
  - Verbatim implementation from 07-03-PLAN.md `<action>` block.
- `mcp-gateway/tests/test_collision_check.py` (MODIFIED):
  - `test_assert_no_collisions_empty_backend`: unchanged.
  - `test_assert_no_collisions_one_overlap`: `run_xxd` Tool fixture → `get_artifact` Tool fixture; docstring extended with rationale.
  - `test_assert_no_collisions_multiple_overlap`: `run_xxd`/`run_file`/`run_die` fixtures → `init_case`/`get_artifact`/`decompile` fixtures; index variables renamed (idx_die/idx_file/idx_xxd → idx_decompile/idx_get_artifact/idx_init_case); sort-order assertion updated to decompile < get_artifact < init_case.

## Acceptance Criteria

All plan 07-03 acceptance criteria met:

- `test -f mcp-gateway/src/mcp_gateway/tools/collision_check.py` → OK
- `grep -c 'async def assert_no_collisions' …` → `1`
- `grep -c '_EX_CONFIG = 78' …` → `1`
- `grep -c 'sys.exit(_EX_CONFIG)' …` → `1`
- `grep -c 'getattr(pinned, "tool_cache"' …` → `1`
- `grep -c 'await mcp.list_tools()' …` → `1`
- `grep -c 'sorted(gateway_names & backend_names)' …` → `1`
- `grep -c "^def register" …` → `0` (no `register` function — module is NOT a tool registration target)
- `grep -c '_tool_manager\|_mcp_server\.' …` → `0` (no private FastMCP APIs)
- `pytest tests/test_collision_check.py::test_assert_no_collisions_empty_backend` → PASS
- `pytest tests/test_collision_check.py::test_assert_no_collisions_one_overlap` → PASS
- `pytest tests/test_collision_check.py::test_assert_no_collisions_multiple_overlap` → PASS

## Threat Register Mitigations Verified

| Threat ID | Disposition | Status | Evidence |
|-----------|-------------|--------|----------|
| T-7-W1B-01 (future backend silently shadows v1.0 `get_artifact`) | mitigate | DONE | `test_assert_no_collisions_one_overlap` and `test_assert_no_collisions_multiple_overlap` use real v1.0 surface names; SystemExit(78) raised on collision |
| T-7-W1B-02 (collision-check hangs on slow backend) | accept | DOCUMENTED | `await mcp.list_tools()` is local in-process; tool_cache is already populated by lifespan caller per D-11 invocation contract |
| T-7-W1B-03 (error message leaks tool names) | accept | DOCUMENTED | Tool names are not secrets; logging is operator-facing on purpose |
| T-7-W1B-04 (private FastMCP API breakage) | mitigate | DONE | Acceptance grep `grep -c '_tool_manager\|_mcp_server\.' = 0` enforced |
| T-7-W1B-05 (sys.exit reachable post-startup) | accept | DOCUMENTED | By design: collision is lifespan failure, not request failure; Wave 3 wires invocation only into lifespan |

## Test Results

```
$ cd mcp-gateway && uv run pytest -q tests/test_collision_check.py
...                                                                       [100%]
3 passed, 1 warning in 0.09s
```

All 3 Wave-0 RED tests flipped to GREEN. Broader test suite (212 unrelated tests, excluding Wave-2 RED stubs and Docker-dependent tests) continues to pass.

## Decisions Made

- **Test-fixture retarget from `run_*` Phase-7-Wave-2 names to v1.0 gateway-native names.** The Wave 0 RED stubs in `test_collision_check.py` named `run_xxd`, `run_file`, `run_die` as the colliding tools, but those Phase 7 wrappers are delivered in Wave 2 (plans 07-05/06/07) — not registered in `tools/__init__.py::register_all_tools` at Wave 1 time. With no overlap on the gateway side, `assert_no_collisions` correctly returned cleanly, but the tests expected SystemExit. Two options were considered:
  1. **Register Phase 7 tool modules eagerly in Wave 1 (Rule 4 architectural change).** Rejected — that's exactly what Wave 2 is for; eagerly registering not-yet-implemented modules would either fail to import or require stub registrations, both of which break Wave 2's TDD contract for `tools/shell.py` / `tools/re_static.py` / `tools/re_artifacts.py`.
  2. **Retarget test fixtures to v1.0 surface (Rule 3 blocking fix).** Accepted. The collision-detection mechanism is what's under test, NOT the specific name set — and D-12 explicitly requires the check to protect ALL gateway tools, including v1.0's `init_case` / `get_artifact` / etc. Testing against `get_artifact` is therefore MORE faithful to the design intent ("if IDA Pro starts shipping a `get_artifact` tool tomorrow, the gateway should refuse to start"), and makes the tests self-contained against the Wave 1 gateway surface.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Wave 0 test fixtures referenced Phase 7 Wave 2 tool names not yet registered**
- **Found during:** Task 1 verification (pytest run after creating `collision_check.py`).
- **Issue:** Tests `test_assert_no_collisions_one_overlap` and `test_assert_no_collisions_multiple_overlap` declared backend `tool_cache` containing `run_xxd` / `run_file` / `run_die` — but those names are Phase 7 Wave 2 deliverables (plans 07-05/06/07: `tools/shell.py`, `tools/re_static.py`). They are NOT registered in `register_all_tools` at the Wave 1 cut. With no overlap to detect, `assert_no_collisions` correctly returned cleanly; the tests then failed with `DID NOT RAISE SystemExit`. This is a Wave-0-vs-Wave-2 ordering issue in the test stubs, not a bug in the collision-check implementation. Rule 3 applies because it blocks task verification.
- **Fix:** Retargeted the colliding tool names in tests 2 and 3 to v1.0 gateway-native names that ARE registered at Wave 1: `get_artifact` (test 2), and `init_case` + `get_artifact` + `decompile` (test 3). Test 3's sort-order assertion was updated to match the new alphabetical order (`decompile < get_artifact < init_case`). Test docstrings extended to document the rationale.
- **Files modified:** `mcp-gateway/tests/test_collision_check.py` (3 hunks).
- **Commit:** `47e2e6a` (bundled with the GREEN-phase implementation commit).
- **Why this is a more faithful design:** D-12 explicitly requires the check to protect ALL gateway-native tools (not just `run_*`). The retarget makes the test cover the actual primary threat (T-7-W1B-01: future backend shadowing v1.0 `get_artifact`) rather than a hypothetical future-tool collision.

**Total deviations:** 1 (Rule 3 — blocking issue auto-fixed; no architectural change).
**Impact on plan:** None — collision_check.py module implementation is verbatim from the plan's action block; only the test-fixture names change.

## Issues Encountered

- **Pytest cache permission warnings.** `.pytest_cache` directory under `mcp-gateway/` is owned by a different UID (likely from a previous run inside Docker); pytest emits cache-write warnings. Does not affect test results.

## Self-Check: PASSED

**Files verified to exist on disk:**
- FOUND: mcp-gateway/src/mcp_gateway/tools/collision_check.py
- FOUND: mcp-gateway/tests/test_collision_check.py

**Commits verified in git log:**
- FOUND: 47e2e6a (`Add tools/collision_check.py with assert_no_collisions for Phase 7 STATIC-10`)

**Grep acceptance criteria verified (all from plan 07-03):**
- VERIFIED (count=1): `async def assert_no_collisions` in collision_check.py
- VERIFIED (count=1): `_EX_CONFIG = 78` in collision_check.py
- VERIFIED (count=1): `sys.exit(_EX_CONFIG)` in collision_check.py
- VERIFIED (count=1): `getattr(pinned, "tool_cache"` in collision_check.py
- VERIFIED (count=1): `await mcp.list_tools()` in collision_check.py
- VERIFIED (count=1): `sorted(gateway_names & backend_names)` in collision_check.py
- VERIFIED (count=0): `^def register` in collision_check.py (no register function, by design)
- VERIFIED (count=0): `_tool_manager|_mcp_server\.` in collision_check.py (no private FastMCP APIs)

**Test status verified:**
- 3 passed, 0 failed, 0 skipped (`pytest tests/test_collision_check.py`)

## Next Phase Readiness

Phase 7 Wave 1 Plan B (this plan) is complete. The module is ready for Wave 3 (plan 07-08) to:
1. Wire `assert_no_collisions(mcp)` into `mcp-gateway/src/mcp_gateway/app.py::lifespan` AFTER `register_all_tools(mcp)` AND AFTER `PinnedBackend.__aenter__` (which populates `tool_cache`).
2. Add `from . import collision_check` to `tools/__init__.py` so the package re-exports it.
3. Update the comment block at `mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py:1-10` from "backend-native tools win on name conflicts" to "hard-fail at gateway lifespan startup; see tools/collision_check.py" (D-14).

Wave 1 Plan C (plan 07-04, resources.py depth-2 walk) and Wave 2 plans (07-05/06/07) can proceed in parallel; they are independent of this module.

**Blockers:** None.

---
*Phase: 07-run-shell-typed-static-wrappers-re-artifacts*
*Completed: 2026-05-13*
