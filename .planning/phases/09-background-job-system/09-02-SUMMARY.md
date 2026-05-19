---
phase: 09-background-job-system
plan: 02
subsystem: jobs-mcp-surface
tags: [jobs, mcp, tools, fastmcp, surface]
dependency_graph:
  requires:
    - mcp_gateway.jobs (Plan 01 -- BackgroundJobRegistry primitive + JOB_TOOL_REGISTRY + 4 D-15 error types)
    - mcp_gateway.tools.case_dirs.resolve_case_dir (Phase 7 -- STATUS_ROOT-confined resolver)
    - mcp.server.fastmcp.FastMCP (mcp SDK 1.27.x)
  provides:
    - mcp_gateway.tools.jobs.start_tool_job (D-05 async handler)
    - mcp_gateway.tools.jobs.get_tool_job (D-19 snapshot + D-16 Tier-2 ctx.report_progress)
    - mcp_gateway.tools.jobs.cancel_tool_job (D-07 idempotent SIGTERM-grace-SIGKILL via registry.cancel)
    - mcp_gateway.tools.jobs.list_tool_jobs (D-20 + `_specs` magic-state + Q5 include_internal)
    - mcp_gateway.tools.jobs.register (FastMCP entry point)
    - mcp_gateway.tools.jobs._resolve_effective_timeout (D-12 ceiling helper)
    - mcp_gateway.tools.jobs._require_registry (session_state.JOB_REGISTRY accessor)
  affects:
    - Plan 03 (app.py lifespan + tools/__init__.py register_all_tools wiring + session_state.JOB_REGISTRY slot)
    - Plan 04 (tests for all four tools end-to-end: 25-key snapshot, 4 D-15 shapes, ctx.report_progress dedup, _specs filtering)

tech_stack:
  added: []  # no new deps; stdlib + mcp + existing gateway only
  patterns:
    - "Phase 8 D-23 docstring-splice via __doc__ assignment (.replace() post-definition)"
    - "Module-attribute import (`from mcp_gateway import jobs`) so importlib.reload propagates"
    - "Phase 8 r2_sessions register-wrapper pattern (`mcp.tool()(fn)` x N inside `register(mcp)`)"
    - "D-15 to_dict pattern preserved at MCP boundary (tools NEVER raise)"
    - "D-16 Tier-2 push-on-poll with session-id dedup map (`job._last_reported_to[sid]`)"

key_files:
  created:
    - mcp-gateway/src/mcp_gateway/tools/jobs.py (351 LoC -- the entire Phase 9 MCP surface)
    - mcp-gateway/tests/test_tools_jobs_smoke.py (120 LoC -- 7 smoke tests)
  modified: []

decisions:
  - "D-26 disclaimer text owned by tools/jobs.py module-level constant; spliced into all 4 tool __doc__ via post-definition .replace() to satisfy Python's docstring-literal parser rule (Phase 8 D-23 precedent in tools/r2_sessions.py)"
  - "Module-attribute access via `from mcp_gateway import jobs` (NOT `from mcp_gateway.jobs import JOB_TOOL_REGISTRY`) -- importlib.reload(jobs) in downstream tests will propagate through all 4 handlers"
  - "_resolve_effective_timeout enforces T-09-04 ceiling at min(caller_or_spec_default, jobs.JOB_MAX_TIMEOUT_S=86400s); negative/zero/non-numeric → D-15 invalid-kwargs dict via caller-side caught ValueError"
  - "D-16 Tier-2 dedup keyed by getattr(ctx, 'session_id', None) or '_anon_' fallback -- programmatic callers without a real session_id still dedupe under the sentinel"
  - "cancel_tool_job adds a single `await asyncio.sleep(0)` after registry.cancel() to yield once so the drive-task's finally-block (which calls _mark_terminal) settles status before _build_snapshot reads it; replaces the awkward wrap_future shape sketched in the plan action block"
  - "Every error path returns one of the four D-15 dict shapes via `<ErrorClass>(...).to_dict()`; the tools NEVER raise out of the MCP boundary (Phase 6 D-04 / Phase 8 D-18 contract preserved)"
  - "list_tool_jobs sort key uses started_at_iso with `0000-00-00T00:00:00+00:00` sentinel for pending jobs (started_at_iso=None) -- pending jobs sort LAST under descending order, putting running/terminal jobs at the top"

metrics:
  duration: ~6 min
  completed: "2026-05-19T01:37:00Z"
  tasks: 1
  files_touched: 2
  loc_added: ~470
---

# Phase 09 Plan 02: tools/jobs MCP Surface Summary

**One-liner:** Four `@mcp.tool()`-registered async handlers (`start_tool_job`, `get_tool_job`, `cancel_tool_job`, `list_tool_jobs`) thinly wrap the Plan 01 `BackgroundJobRegistry` primitive — D-26 disclaimer spliced into every docstring, D-16 Tier-2 `ctx.report_progress` with session-id dedup, D-15 four error shapes, D-20 `_specs` magic-state with Q5 underscore filter.

## What Was Built

### Task 1 — `tools/jobs.py` (351 LoC, single Wave-2 module)

#### Four MCP tool handlers

| Handler | Signature | Behavior summary |
|---------|-----------|------------------|
| `start_tool_job(tool, kwargs, *, case_dir, timeout=None, ctx=None) -> dict` | D-05 | Resolves spec via `jobs.JOB_TOOL_REGISTRY` → D-15 #2 on miss; validates kwargs via `jobs._validate_kwargs` → D-15 #4 on miss; resolves case_dir via `resolve_case_dir` → D-15 invalid-kwargs(field=case_dir) on miss; D-12 effective-timeout via `_resolve_effective_timeout` → D-15 invalid-kwargs(field=timeout) on miss; submits via `registry.submit` → D-15 #1 on cap; otherwise returns `registry._build_snapshot(job)` (D-19 25-key dict). |
| `get_tool_job(job_id, *, ctx=None) -> dict` | JOBS-02 | Looks up via `registry.get(job_id)` → D-15 #3 on miss; when `ctx` is non-None AND `job.progress is not None` AND `(progress, progress_total) != job._last_reported_to.get(ctx.session_id)`, calls `await ctx.report_progress(progress, progress_total, progress_message)` and updates the dedup map BEFORE returning the snapshot. |
| `cancel_tool_job(job_id) -> dict` | JOBS-03 | Looks up via `registry.get` → D-15 #3 on miss; computes `was_terminal = job.status in jobs._TERMINAL_STATUSES`; on non-terminal: `await registry.cancel(job, reason='user')` then `await asyncio.sleep(0)` to let the drive-task finally settle status; returns `_build_snapshot(job)` augmented with `previously_terminal=<was_terminal>`. |
| `list_tool_jobs(state=None, *, limit=50, include_internal=False) -> dict` | D-20 | On `state == '_specs'`: returns `{specs: [...], count, include_internal}` with underscore-prefixed spec names filtered unless `include_internal=True` (Q5). Otherwise concatenates `list_inflight() + list_completed()`, optionally filters by state set, sorts `started_at_iso` DESC (pending jobs sentinel-sorted last), caps at `min(limit, 500)`, returns `{jobs, inflight_count, completed_count, completed_cap, truncated}`. |

#### Helpers

- **`_require_registry()`** — mirrors `tools/r2_sessions.py::_require_registry`. Returns `session_state.JOB_REGISTRY` or raises `RuntimeError` if Plan 03's lifespan has not yet attached the registry. Test-friendly because the smoke test does not invoke handlers, only `register(mcp)`.
- **`_resolve_effective_timeout(spec, caller_timeout)`** — D-12 enforcer. `min(caller_or_spec_or_jobs.JOB_TIMEOUT_S, jobs.JOB_MAX_TIMEOUT_S)`. Negative/zero/non-numeric → `ValueError` caught by `start_tool_job` and converted to D-15 invalid-kwargs(field=`timeout`).

#### `register(mcp)` entry point

```python
def register(mcp: FastMCP) -> None:
    mcp.tool()(start_tool_job)
    mcp.tool()(get_tool_job)
    mcp.tool()(cancel_tool_job)
    mcp.tool()(list_tool_jobs)
```

Same shape as Phase 8 `tools/r2_sessions.py::register`. Plan 03 will add `from mcp_gateway.tools import jobs as jobs_tools` + `jobs_tools.register(mcp)` to `tools/__init__.py::register_all_tools`.

#### D-26 disclaimer splice

Module-level constant `_JOBS_DISCLAIMER` holds the two-paragraph text verbatim. After each handler definition:

```python
start_tool_job.__doc__ = (start_tool_job.__doc__ or "").replace(
    "{_JOBS_DISCLAIMER}", _JOBS_DISCLAIMER
)
```

Same `.replace()` mechanism as `tools/r2_sessions.py` for SESS-05 — Python's parser only attaches docstrings when the function body's first expression is a pure string literal, so the splice has to happen post-definition to keep the templated `{_JOBS_DISCLAIMER}` placeholder in the source-level docstring.

#### D-16 Tier-2 dedup mechanism

In `get_tool_job`:

```python
if ctx is not None and job.progress is not None:
    sid = getattr(ctx, "session_id", None) or "_anon_"
    last = job._last_reported_to.get(sid)
    cur = (job.progress, job.progress_total)
    if last != cur:
        try:
            await ctx.report_progress(job.progress, job.progress_total, job.progress_message)
            job._last_reported_to[sid] = cur
        except Exception:
            log.exception("[tools.jobs] ctx.report_progress failed -- ignoring")
```

Notes:
- `_last_reported_to` is a `dict[str, tuple[int, int]]` on the `Job` dataclass (declared in Plan 01 `jobs.py`).
- Each `ctx.session_id` (MCP-Session-Id) tracks its own last-seen `(progress, progress_total)` pair so two pollers see only the deltas relative to their own previous calls.
- Programmatic callers without a session_id collapse to the sentinel `"_anon_"` and still dedupe across calls.
- `ctx.report_progress` exceptions are swallowed-and-logged — the snapshot return still happens (D-15 "tools never raise" preserved even when MCP-side push fails).

#### D-15 four error paths

| D-15 # | Error class | Entry point | Trigger |
|--------|-------------|-------------|---------|
| #1 | `JobCapReached(inflight, cap)` | `start_tool_job` | `registry.submit` raises when `len(_inflight) >= MAX_JOBS_INFLIGHT` |
| #2 | `UnknownJobTool(tool, known)` | `start_tool_job` | `jobs.JOB_TOOL_REGISTRY.get(tool) is None` |
| #3 | `JobNotFound(job_id)` | `get_tool_job`, `cancel_tool_job` | `registry.get(job_id)` raises |
| #4 | `InvalidKwargs(field, expected, got)` | `start_tool_job` (three sites) | `jobs._validate_kwargs` raises; `resolve_case_dir` raises ValueError/TypeError; `_resolve_effective_timeout` raises ValueError |

Verification: `grep -c '\.to_dict()' tools/jobs.py` → 7 sites (one per call site, satisfies `>=4` plan acceptance criterion).

#### D-20 `_specs` magic-state + Q5 filter

`state == "_specs"` branch returns the `JOB_TOOL_REGISTRY` catalog with `has_progress_parser: bool` per spec. Underscore-prefixed names (`_sleep_probe`, `_log_burst_probe`) are HIDDEN when `include_internal=False` (default). This lets agent discovery via `list_tool_jobs(state='_specs')` show only the user-facing `capa` spec on Phase 9 baseline; future plans (10/11) will add `unblob`, `run_strace`, etc.

### Task 1 RED / GREEN commits

| Step | Description | Commit |
|------|-------------|--------|
| RED  | `test_tools_jobs_smoke.py` (7 tests) -- imports + D-26 phrases + register + module-attr import + .to_dict count + ctx.report_progress + _specs branch | `2fd6fc9` |
| GREEN | `tools/jobs.py` (351 LoC) -- all 7 tests turn PASS on first run | `0f26ce8` |

## Deviations from Plan

### Claude's Discretion — micro-edits to the plan's <action> block

The plan's `<action>` block sketched a hairy `asyncio.wrap_future(...)` shape for `cancel_tool_job` and then said immediately below "replace with a cleaner version" using a single `await asyncio.sleep(0)`. The cleaner version was applied verbatim. No `_noop()` helper was added. The intent (yield once so the drive task's `finally`-block runs after `cancel()` returns) is upheld.

### Rule 1 - Type-check fortification in _resolve_effective_timeout

**Found during:** Task 1 implementation
**Issue:** Plan's `_resolve_effective_timeout` checks `caller_timeout <= 0` but does not guard against non-numeric types (e.g., `timeout="abc"` would raise `TypeError` at comparison, not the intended `ValueError`). The handler relies on `except ValueError` to convert to D-15 invalid-kwargs.
**Fix:** Added an `isinstance(caller_timeout, (int, float)) or isinstance(caller_timeout, bool)` guard that raises `ValueError("timeout must be a number")`. Also excluded `bool` (since `bool` is a subclass of `int` in Python but a boolean timeout is nonsensical).
**Files modified:** mcp-gateway/src/mcp_gateway/tools/jobs.py
**Commit:** 0f26ce8 (folded into GREEN)
**Rationale:** Without this guard, `start_tool_job(..., timeout="bad")` would raise `TypeError` past the `except ValueError` catch and bubble out of the MCP tool boundary, violating Phase 6 D-04 "tools never raise". Defensive — preserves the D-15 invariant.

### Rule 2 - limit-arg sanitization for list_tool_jobs

**Found during:** Task 1 implementation
**Issue:** Plan's `list_tool_jobs` `limit` sanitization (`if not isinstance(limit, int) or limit <= 0 or limit > max_limit: limit = min(max(1, int(limit) if isinstance(limit, int) else 50), max_limit)`) would raise `TypeError` on `limit=None` or `limit="abc"` due to the unguarded `int(limit)` call inside the ternary.
**Fix:** Wrapped the `int(limit)` cast in try/except (TypeError, ValueError) → fallback to 50.
**Files modified:** mcp-gateway/src/mcp_gateway/tools/jobs.py
**Commit:** 0f26ce8 (folded into GREEN)
**Rationale:** Same "tools never raise" invariant. Without it, an agent passing `limit=None` would crash the tool instead of getting a sensible default.

No other deviations from CONTEXT.md, RESEARCH.md, or the plan's <action> block. The D-26 disclaimer, splice mechanism, _require_registry helper, _resolve_effective_timeout location, D-16 Tier-2 dedup-by-session-id, D-20 `_specs` + Q5 underscore filter, and register(mcp) entry point all match the plan verbatim.

## Threat Model Disposition

| Threat ID | Disposition | Mitigation In This Plan |
|-----------|-------------|-------------------------|
| T-09-01 (Tampering/Elevation via spec.build_argv) | mitigate | `start_tool_job` calls `jobs._validate_kwargs(spec, kwargs)` BEFORE `spec.build_argv` ever runs (Plan 01 controls `build_argv` via the frozen `JobToolSpec`). Path-typed kwargs (e.g., capa's `sample`) flow through `samples.resolve_sample` inside `spec.build_argv` which sha256-confines. D-15 #4 invalid-kwargs dict returned on schema miss. |
| T-09-02 (Info disclosure cross-client) | accept | D-26 disclaimer in every tool docstring (`In-memory registry` + `shared across all bearer-token clients`). Plan 04 will add `test_tools_jobs_d26_docstrings.py` regression. Per-session keying is v1.2 (GW-V2-03). |
| T-09-04 (Tampering -- huge timeout) | mitigate | `_resolve_effective_timeout` enforces D-12 `min(caller_or_spec_default, jobs.JOB_MAX_TIMEOUT_S=86400s)`. Negative/zero/non-numeric/bool → D-15 invalid-kwargs(field=`timeout`). |
| T-09-05 (DoS via submit storm) | mitigate | `registry.submit` raises `JobCapReached` when `_inflight` >= `MAX_JOBS_INFLIGHT`; handler returns D-15 #1 dict; no queueing. Cap is read from `jobs.MAX_JOBS_INFLIGHT` env constant (default 4). |
| T-09-07 (Eviction destroys evidence) | mitigate | Plan 02 never touches on-disk artifacts; eviction is in Plan 01 with the log-preservation invariant. `cancel_tool_job` returns the snapshot for a still-known job (no destruction at the MCP layer); `get_tool_job` on an evicted job returns D-15 #3 with a hint to browse `tool-logs/<...>.json` via Resources. |

## Commits

| Step | Description | Commit |
|------|-------------|--------|
| RED  | Add failing smoke tests for tools/jobs MCP surface | 2fd6fc9 |
| GREEN | Implement tools/jobs.py — 4 handlers + register + D-26 splice + D-16 dedup | 0f26ce8 |

## Verification

- `cd mcp-gateway && .venv/bin/python -m pytest tests/test_tools_jobs_smoke.py` → 7 passed
- `cd mcp-gateway && .venv/bin/python -m pytest tests/test_tools_jobs_smoke.py tests/test_runner.py tests/test_sessions.py` → 26 passed, 3 skipped (host r2 unavailable; container provides), no regressions
- Plan inline smoke script: `D-26 disclaimer present in all 4 tool docstrings` + `register(mcp) ran cleanly`
- `grep -c "In-memory registry" tools/jobs.py` → 1 (module-level constant, spliced into all 4 docstrings)
- `grep -c "shared across all bearer-token clients" tools/jobs.py` → 2 (constant + module-docstring reference)
- `grep -c '\.to_dict()' tools/jobs.py` → 7 (covers all 4 D-15 error paths; plan minimum 4)
- `grep -c "ctx.report_progress" tools/jobs.py` → 4 (D-16 Tier-2 site + 3 docstring/comment references)
- `grep -c "_last_reported_to" tools/jobs.py` → 3 (read + write + comment)
- `grep -c 'state == "_specs"' tools/jobs.py` → 1 (D-20 magic-state branch)
- `grep -c "include_internal" tools/jobs.py` → 5 (Q5 filter, default param, response key, etc.)
- `grep -c "from mcp_gateway import jobs" tools/jobs.py` → 1 (module-attribute import pattern)
- `wc -l tools/jobs.py` → 351 lines (plan minimum 280)

## Self-Check: PASSED

Files verified:

- FOUND: mcp-gateway/src/mcp_gateway/tools/jobs.py (351 lines)
- FOUND: mcp-gateway/tests/test_tools_jobs_smoke.py (120 lines)

Commits verified:

- FOUND: 2fd6fc9 (RED smoke tests)
- FOUND: 0f26ce8 (GREEN implementation)

All Plan 02 `<success_criteria>` satisfied. Plan 03 (`app.py` lifespan + `tools/__init__.py` register + `session_state.JOB_REGISTRY` slot) and Plan 04 (end-to-end behavioural tests) can now wire and exercise this surface.
