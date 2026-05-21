---
phase: 09-background-job-system
plan: 03
subsystem: jobs-lifespan-wiring
tags: [jobs, lifespan, wiring, integration]
dependency_graph:
  requires:
    - mcp_gateway.jobs (Plan 01 — BackgroundJobRegistry + MAX_JOBS_INFLIGHT/JOB_CANCEL_GRACE_S/MAX_COMPLETED_JOBS constants)
    - mcp_gateway.tools.jobs (Plan 02 — register(mcp) entry point)
    - mcp_gateway.sessions.SessionRegistry (Phase 8 — outer nesting layer per D-25)
  provides:
    - mcp_gateway.session_state.JOB_REGISTRY (module-level Optional slot)
    - app.py::lifespan::_build_job_registry (D-24 module-constant builder)
    - LIFO nesting (PinnedBackend > SessionRegistry > BackgroundJobRegistry > session_manager) in both lifespan branches
    - 4 new gateway-native MCP tools registered (start_tool_job, get_tool_job, cancel_tool_job, list_tool_jobs)
  affects:
    - Plan 04 (tests/jobs end-to-end exercises): now has a real wired registry to import-and-attach against (or mock-spawn under)

tech_stack:
  added: []  # zero new deps
  patterns:
    - "Phase 8 D-24 nested-async-with template (SessionRegistry-inside-PinnedBackend) extended one level deeper"
    - "Module-attribute access via `session_state.JOB_REGISTRY` (mirrors SESSION_REGISTRY pattern)"
    - "D-24 module-constant import (no os.environ re-reads in app.py)"

key_files:
  created: []
  modified:
    - mcp-gateway/src/mcp_gateway/session_state.py (+8 / -1 — JOB_REGISTRY slot + GW-V2-03 doc-extension paragraph + TYPE_CHECKING import)
    - mcp-gateway/src/mcp_gateway/app.py (+30 / -10 — jobs import block + _build_job_registry helper + nested async-with in both branches)
    - mcp-gateway/src/mcp_gateway/tools/__init__.py (+8 / -1 — jobs import in tuple + jobs.register(mcp) BEFORE backend_passthrough + Phase 9 docstring block)
    - mcp-gateway/tests/test_tool_list.py (+5 / -2 — Phase 9 EXPECTED_TOOLS rows + module-docstring 43→47 bump)

decisions:
  - "D-25 LIFO nesting applied verbatim: in both lifespan branches the BackgroundJobRegistry async-with is nested INSIDE the SessionRegistry async-with; teardown order on shutdown is jobs → r2 sessions → backend (Phase 11 r2-orchestrating jobs must complete cancel BEFORE r2 sessions die)"
  - "D-24 module-constant invariant preserved: _build_job_registry imports MAX_JOBS_INFLIGHT/JOB_CANCEL_GRACE_S/MAX_COMPLETED_JOBS from jobs.py — zero os.environ.get calls added to app.py beyond pre-existing log strings (host/port/token-file)"
  - "Tools registration order: jobs.register(mcp) placed BEFORE backend_passthrough.register(mcp) — matches Phase 7/8 ordering so collision check sees gateway-native tools first"
  - "Rule 1 deviation applied to tests/test_tool_list.py to keep collision/tool_list acceptance criterion green — Phase 9 raises EXPECTED_TOOLS from 43 to 47 (still inside the 35-50 invariant). Phase 7-08 SUMMARY established this same precedent for the Phase 7 surface bump."

metrics:
  duration: ~3 min
  completed: "2026-05-19T01:43:00Z"
  tasks: 1
  files_touched: 4
  loc_added: ~51
---

# Phase 09 Plan 03: Lifespan Wiring + Tool Registration Summary

**One-liner:** Three surgical edits + one test bump — `JOB_REGISTRY` slot added to `session_state.py`, `BackgroundJobRegistry` async-context-manager nested INSIDE `SessionRegistry` in BOTH `app.py::lifespan` branches per D-25, and `jobs.register(mcp)` wired into `tools/__init__.py` BEFORE backend_passthrough, raising the gateway-native tool count from 43 (Phase 8) to 47 (Phase 9).

## What Was Built

### Task 1 — Three-file surgical wiring + one test update

#### Edit 1 — `session_state.py` (+8 LoC)

- Added `JOB_REGISTRY: Optional["BackgroundJobRegistry"] = None` module slot
- Added `from .jobs import BackgroundJobRegistry` under `TYPE_CHECKING`
- Extended module docstring with the Phase 9 D-07 paragraph documenting the "jobs shared across bearer-token clients" caveat (mirror of Phase 8 SESS-05 SESSION_REGISTRY caveat). The D-26 disclaimer text itself lives in `tools/jobs.py` per Plan 02.

#### Edit 2 — `app.py` (+30 / -10 LoC, lifespan rewiring)

- Added imports: `BackgroundJobRegistry, MAX_JOBS_INFLIGHT, JOB_CANCEL_GRACE_S, MAX_COMPLETED_JOBS` from `.jobs` (D-24 module-constant single source of truth)
- Added `_build_job_registry()` helper inside `lifespan` (immediately after `_build_registry`)
- **No-backend branch:** Wrapped the existing `mcp.session_manager.run()` inner block with a new `async with _build_job_registry() as job_registry` block; set `session_state.JOB_REGISTRY = job_registry` on entry, `None` in `finally`. Comment cites D-25 LIFO unwind order.
- **Pinned-backend branch:** Same nested-async-with structure inserted between `SessionRegistry` and `mcp.session_manager.run()`. Comment cites Phase 11's r2-orchestrating jobs use-case as the rationale for jobs-inside-sessions ordering.

Final nesting hierarchy in both lifespan branches:

```
PinnedBackend (pinned-backend branch only)
  └── SessionRegistry (Phase 8)
        └── BackgroundJobRegistry (Phase 9 — this plan)
              └── mcp.session_manager.run() (FastMCP transport)
```

Shutdown unwinds LIFO: `mcp.session_manager.__aexit__` → `BackgroundJobRegistry.__aexit__` (cancels in-flight jobs) → `SessionRegistry.__aexit__` (kills r2 sessions) → `PinnedBackend.__aexit__` (tears down disassembler MCP).

#### Edit 3 — `tools/__init__.py` (+8 / -1 LoC)

- Added `jobs,` to the in-function import tuple (with Phase 9 D-05 comment)
- Added `jobs.register(mcp)` call BEFORE `backend_passthrough.register(mcp)` — matches Phase 7/8 ordering convention so gateway-native tools register before the catch-all pass-through
- Extended `register_all_tools` docstring with the Phase 9 D-05 additions block (analogous to Phase 7 D-16 and Phase 8 D-05 blocks already present)

#### Edit 4 (Rule 1 deviation) — `tests/test_tool_list.py` (+5 / -2 LoC)

- Bumped EXPECTED_TOOLS from 43 names to 47 by adding the four Phase 9 names: `start_tool_job`, `get_tool_job`, `cancel_tool_job`, `list_tool_jobs`
- Updated module-level docstring with the Phase 9 D-05 row
- Tool count still inside the `35 <= n <= 50` Phase 7/8/9 invariant (47 fits)

## Deviations from Plan

### Rule 1 - Test expectation update

**1. [Rule 1 - Test-expectation bump] EXPECTED_TOOLS in test_tool_list.py needed 4 new Phase 9 names**

- **Found during:** Task 1 verification — `pytest -k 'collision or tool_list'` failed `test_no_unexpected_tools` with `unexpected tools registered: {'cancel_tool_job', 'get_tool_job', 'start_tool_job', 'list_tool_jobs'}` because Plan 02 already registered those handlers at module import.
- **Issue:** Without the bump, the plan's own acceptance criterion `cd mcp-gateway && pytest tests/ -x -k 'collision or tool_list' --tb=short` exits 0 cannot be met.
- **Fix:** Added the four Phase 9 names to EXPECTED_TOOLS plus the analogous docstring rows. Phase 7-08 SUMMARY established this same Rule 1 precedent ("GW-02 tool-count invariant bumped 15-25 -> 35-50 in test_tool_list.py with explicit D-16 rationale").
- **Files modified:** `mcp-gateway/tests/test_tool_list.py`
- **Commit:** 35f3294 (folded into Task 1 commit)
- **Rationale:** This is a test-data update, not a semantic test change. The test still asserts "the registered surface exactly matches the expected set". The plan's `<files_modified>` frontmatter lists only the three source files but the threat model row T-09-09 explicitly states "Plan 04 test_tool_list.py bumps EXPECTED count" — given collision-check acceptance is gated on this passing in Plan 03, the bump landed here. Plan 04 will continue to own the broader end-to-end test additions.

No other deviations. The verbatim plan `<action>` block was applied unmodified for all three core file edits (paste-ready code from the plan worked first try).

## Threat Model Disposition

| Threat ID | Disposition | Mitigation In This Plan |
|-----------|-------------|-------------------------|
| T-09-06 (R/DoS — stale subprocess after disconnect/shutdown) | mitigate | D-25 LIFO unwind enforced by physical nesting: in both lifespan branches the line `async with _build_registry() as registry:` precedes `async with _build_job_registry() as job_registry:`, and the `finally: session_state.JOB_REGISTRY = None` precedes the `finally: session_state.SESSION_REGISTRY = None`. Verified by source-grep below. SC-6 test covered in Plan 04 (`test_lifespan_integration.py`). |
| T-09-08 (T — env-var re-read in lifespan bypasses D-13 validation) | mitigate | D-24 invariant: `_build_job_registry` imports only `MAX_JOBS_INFLIGHT`, `JOB_CANCEL_GRACE_S`, `MAX_COMPLETED_JOBS` from `jobs.py` module-level constants (read once at import with sanity-check in jobs.py per Plan 01). Negative grep: `grep -n 'os.environ' app.py` returns ONLY the pre-existing log strings for `MCP_GATEWAY_HOST/PORT/TOKEN_FILE` — zero new env reads from Plan 03. |
| T-09-09 (T — tool-name collision with backend-native) | mitigate | `assert_no_collisions(mcp)` runs at lifespan startup AFTER `PinnedBackend.__aenter__` (so backend tool_cache is populated) AND BEFORE `_build_registry`/`_build_job_registry` (so a collision exits the process cleanly with EX_CONFIG=78 instead of a half-started server). New 4 Phase 9 names raise gateway-native count 43 → 47 — collision check covers them automatically (its iteration source is `mcp._tool_manager._tools`). Plan 04's `test_tool_list.py` already bumped to EXPECTED=47. |

## Commits

| Step | Description | Commit |
|------|-------------|--------|
| Task 1 | Wire Phase 9 BackgroundJobRegistry into gateway lifespan and tools surface (3 source files + 1 test) | 35f3294 |

## Verification

### Plan acceptance criteria

- `python -c "from mcp_gateway import session_state; assert session_state.JOB_REGISTRY is None"` → exit 0 (smoke script line 1)
- `grep -c 'JOB_REGISTRY' mcp-gateway/src/mcp_gateway/session_state.py` → **2** (≥2, criterion met: TYPE_CHECKING import + slot)
- `grep -c 'session_state.JOB_REGISTRY' mcp-gateway/src/mcp_gateway/app.py` → **4** (=4, criterion met: set + clear in each of 2 branches)
- `grep -c '_build_job_registry' mcp-gateway/src/mcp_gateway/app.py` → **3** (≥3, criterion met: definition + 2 call sites)
- `grep -c 'BackgroundJobRegistry' mcp-gateway/src/mcp_gateway/app.py` → **5** (≥1, criterion met: import + type annotation + builder body + 2 comments)
- `grep -n 'jobs.register(mcp)' mcp-gateway/src/mcp_gateway/tools/__init__.py` → line 57 (found)
- `grep -n 'backend_passthrough.register' mcp-gateway/src/mcp_gateway/tools/__init__.py` → line 58 (>57 — ordering invariant met: gateway-native before pass-through)

### Smoke test

```
$ .venv/bin/python -c "<plan smoke script>"
[resources] registered mare://cases/<case>/<artifact> ...
lifespan-wiring smoke OK; session_state.JOB_REGISTRY slot present; tools registered cleanly
```

### Test suite

- `pytest tests/ -x -k 'collision or tool_list' --tb=short` → **9 passed, 295 deselected** (acceptance criterion final line met)
- Broader sweep `pytest tests/test_tool_list.py tests/test_collision_check.py tests/test_tools_jobs_smoke.py tests/test_runner.py tests/test_sessions.py` → **34 passed, 3 skipped** (3 r2 skips are host-only; container provides radare2 — no regressions)

### Final tool count

```
Total gateway-native tools: 47
Phase 9 jobs tools: ['cancel_tool_job', 'get_tool_job', 'list_tool_jobs', 'start_tool_job']
```

Phase 8: 43 → Phase 9: 47 — exactly the 4 expected new names. Fits the `35 <= n <= 50` Phase 7/8/9 invariant with headroom for Phase 10/11/12 additions.

### D-24 invariant — negative grep

```
$ grep -n 'os.environ' mcp-gateway/src/mcp_gateway/app.py
78:    skip_backend = os.environ.get("MCP_GATEWAY_SKIP_BACKEND") == "1"
119,120: # log-string host/port (no-backend branch)
145,146: # log-string host/port (pinned-backend branch)
153,156: # log-string token-file
```

Zero new `os.environ` reads from Plan 03's edits — all pre-existing. `_build_job_registry` reads ONLY `MAX_JOBS_INFLIGHT / JOB_CANCEL_GRACE_S / MAX_COMPLETED_JOBS` module constants imported at the top of `app.py`. D-24 invariant preserved.

### D-25 LIFO order — source-grep proof

In both lifespan branches the relative line ordering is:

1. `async with _build_registry() as registry:` (SessionRegistry — OUTER)
2. `async with _build_job_registry() as job_registry:` (BackgroundJobRegistry — INNER)
3. `async with mcp.session_manager.run():` (FastMCP transport — INNERMOST)
4. `finally: session_state.JOB_REGISTRY = None` (JOB inner cleanup runs first)
5. `finally: session_state.SESSION_REGISTRY = None` (SESSION outer cleanup runs after)

LIFO unwind on shutdown: jobs cancelled → r2 sessions killed → backend torn down. Pitfall avoided: Phase 11's session-orchestrated jobs will release their r2 handles BEFORE the SessionRegistry's __aexit__ tries to kill those sessions.

## Self-Check: PASSED

Files verified:

- FOUND: `mcp-gateway/src/mcp_gateway/session_state.py` (extended; JOB_REGISTRY slot at module level, default None)
- FOUND: `mcp-gateway/src/mcp_gateway/app.py` (lifespan rewired; both branches nest BackgroundJobRegistry inside SessionRegistry)
- FOUND: `mcp-gateway/src/mcp_gateway/tools/__init__.py` (jobs imported and registered; placement before backend_passthrough)
- FOUND: `mcp-gateway/tests/test_tool_list.py` (EXPECTED_TOOLS bumped 43 → 47)

Commits verified:

- FOUND: 35f3294 (Task 1 wiring)

All Plan 03 `<success_criteria>` satisfied:

- [x] `session_state.JOB_REGISTRY` slot exists, defaults to None
- [x] `app.py::lifespan` nests `BackgroundJobRegistry` INSIDE `SessionRegistry` in BOTH branches
- [x] LIFO unwind order matches D-25 (verified by source-grep)
- [x] `_build_job_registry` reads ONLY module constants from `jobs.py` (D-24)
- [x] `register_all_tools` imports `jobs` and calls `jobs.register(mcp)` BEFORE `backend_passthrough.register(mcp)`
- [x] Existing collision check still passes; tool count 43 → 47
- [x] Smoke test prints "lifespan-wiring smoke OK; session_state.JOB_REGISTRY slot present; tools registered cleanly"

Plan 04 (Wave 3 end-to-end test suite) can now exercise the fully wired stack against a real (or mock-spawned) `BackgroundJobRegistry`.
