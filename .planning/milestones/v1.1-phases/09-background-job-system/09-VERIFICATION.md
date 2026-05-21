---
phase: 09-background-job-system
verified: 2026-05-19T03:26:38Z
status: passed
score: 7/7 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 5/7
  gaps_closed:
    - "Cap-reach/unknown-tool/invalid-kwargs/build-argv error paths now ALL return one of the four D-15 shapes; tools never raise (truth #7)"
    - "start_tool_job(tool='_sleep_probe' / 'capa', ...) returns D-19 snapshot OR a D-15 #4 InvalidKwargs dict — no raise (truth #2 re-paired)"
  gaps_remaining: []
  regressions: []
gaps: []
deferred: []
---

# Phase 9: background-job-system Verification Report (Re-verification)

**Phase Goal:** Remote agents can launch long-running RE tools (capa, unblob, Ghidra/IDA auto, strace, qemu) and poll for completion without hitting the 60s MCP request cap. Four MCP tools (start_tool_job, get_tool_job, cancel_tool_job, list_tool_jobs) backed by `BackgroundJobRegistry`.
**Verified:** 2026-05-19T03:26:38Z
**Status:** passed
**Re-verification:** Yes — after gap closure (Plan 09-05)

## Re-verification Summary

The previous verification (2026-05-19, initial run) flagged **truth #7** as ✗ FAILED due to two confirmed D-15 escape paths in the `capa` tool:

1. `start_tool_job(tool='capa', kwargs={})` raised `KeyError('sample')` out of the MCP boundary (CR-02)
2. `start_tool_job(tool='capa', kwargs={'sample': '../etc/passwd'})` raised `ValueError('path traversal rejected')` out of the MCP boundary (CR-01)

Gap-closure Plan 09-05 executed three tasks:

| Task | Change | File | Commit |
|------|--------|------|--------|
| 1 | Added `'required': True` to `_CAPA_SPEC.kwargs_schema` + taught `_validate_kwargs` to honor `rule.get("required")` | `mcp-gateway/src/mcp_gateway/jobs.py` | `66e0e30` |
| 2 | Added second `except (ValueError, FileNotFoundError, KeyError, OSError)` branch around `registry.submit()` returning D-15 #4 InvalidKwargs dict | `mcp-gateway/src/mcp_gateway/tools/jobs.py` | `bc3b5cb` |
| 3 | Added `test_capa_missing_sample_returns_invalid_kwargs` + `test_capa_path_traversal_returns_invalid_kwargs` + expanded `test_no_tool_handler_raises._calls` body | `mcp-gateway/tests/jobs/test_errors.py` | `f386cfe` |

**Re-verification outcome:**
- All three commits present in `git log`
- All 8 tests in `test_errors.py` pass (6 prior + 2 new)
- Phase 9 non-slow suite: **68 passed** (was 66 at initial verification + 2 new)
- Full gateway non-slow suite: **323 passed**, 46 skipped (was 321 + 2 new)
- `except Exception` count in `tools/jobs.py` unchanged at 1 (no bare-Exception swallowing introduced)
- Truth #7 flipped from ✗ FAILED to ✓ VERIFIED
- Truth #2 (re-paired note) explicitly re-confirmed for both `_sleep_probe` and `capa` tools

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|---------|
| 1  | `start_tool_job` returns 25-key D-19 snapshot with `job_id` (16 lowercase hex), `status in {pending,running}`, `argv`, `slug` (SC-1) | ✓ VERIFIED | `test_start_tool_job.py` 7 tests pass; D-19 25-key dict confirmed; job_id matches `r'[0-9a-f]{16}'` |
| 2  | `get_tool_job` returns D-19 25-key snapshot; `cancel_tool_job` SIGTERM→SIGKILL grace ladder; `list_tool_jobs(state)` filters correctly (SC-2) | ✓ VERIFIED | `test_get_tool_job` (3), `test_cancel_grace` (2), `test_list_tool_jobs` (6) all pass |
| 3  | Log capped at `MAX_JOB_LOG_MB`; over-cap killed → `status=killed_log_cap`; completed jobs LRU-cleaned (SC-3) | ✓ VERIFIED | `test_log_cap.py` passes (`_log_burst_probe` 1 MiB override → `killed_log_cap` + `MARE_JOB_KILLED_LOG_CAP` marker); `test_lru_retention.py` passes (FIFO eviction + log files preserved on disk) |
| 4  | Client disconnect/cancellation: subprocess dead within 200ms via `asyncio.shield(proc.wait())` + `killpg(SIGKILL)` (SC-4) | ✓ VERIFIED | `test_disconnect_200ms.py` passes; `start_new_session=True` + `os.killpg` confirmed in `jobs.py` |
| 5  | Long-running tools can report progress via MCP `Context.report_progress` (SC-5) | ✓ VERIFIED | `test_progress.py` 5 tests pass; D-16 Tier-2 `ctx.report_progress` with `_last_reported_to` session-id dedup confirmed |
| 6  | Gateway restart cancels all in-flight jobs (in-memory only); documented in tool docstrings (SC-6) | ✓ VERIFIED | `test_lifespan_integration.py`: LIFO unwind order `["jobs.__aexit__", "sessions.__aexit__"]`; `BackgroundJobRegistry.__aexit__` parallel-cancels via `asyncio.gather`; D-26 disclaimer in all 4 docstrings |
| 7  | Every error path returns ONE of the four D-15 shapes; tools NEVER raise | ✓ VERIFIED | **Gap closed by Plan 09-05.** `test_errors.py` now has 8 tests including the two regression tests `test_capa_missing_sample_returns_invalid_kwargs` (D-15 #4, field='sample') and `test_capa_path_traversal_returns_invalid_kwargs` (D-15 #4, field='kwargs'). `test_no_tool_handler_raises` expanded to include both capa paths. All pass. |

**Score:** 7/7 truths verified

### Deferred Items

None.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `mcp-gateway/src/mcp_gateway/jobs.py` | `BackgroundJobRegistry` primitive, `Job` dataclass, `JOB_TOOL_REGISTRY`, errors, **`required`-rule support** | ✓ VERIFIED | 754 lines; `_validate_kwargs` walker (lines 255-291) has `if rule.get("required"): raise InvalidKwargs(field, "required field", "missing")` at line 269-270; `_CAPA_SPEC.kwargs_schema` at line 375 has `"required": True` |
| `mcp-gateway/src/mcp_gateway/runner.py` | `proc_callback` kwarg extension | ✓ VERIFIED | `proc_callback` at line 212; dispatch at line 237-238 |
| `mcp-gateway/src/mcp_gateway/tools/jobs.py` | 4 MCP tools + `register(mcp)` + **broader except around `registry.submit()`** | ✓ VERIFIED | 354 lines; `start_tool_job` submit block (lines 157-176) has TWO except branches: `JobCapReached` (D-15 #1) and `(ValueError, FileNotFoundError, KeyError, OSError)` (D-15 #4); `register()` at line 349 |
| `mcp-gateway/src/mcp_gateway/session_state.py` | `JOB_REGISTRY` slot | ✓ VERIFIED | `JOB_REGISTRY: Optional["BackgroundJobRegistry"] = None` at line 27 |
| `mcp-gateway/src/mcp_gateway/app.py` | Lifespan nesting `BackgroundJobRegistry` inside `SessionRegistry` (both branches) | ✓ VERIFIED | `_build_job_registry` at line 110; nested in both branches; 4 `JOB_REGISTRY` set/clear sites |
| `mcp-gateway/src/mcp_gateway/tools/__init__.py` | `import jobs` + `jobs.register(mcp)` before `backend_passthrough` | ✓ VERIFIED | `jobs` imported at line 43; `jobs.register(mcp)` at line 57; `backend_passthrough` at line 58 |
| `mcp-gateway/tests/jobs/test_errors.py` | D-15 error-shape suite **including 2 new capa regression tests** | ✓ VERIFIED | 8 tests: `test_cap_reached_shape`, `test_unknown_tool_shape`, `test_job_not_found_shape`, `test_invalid_kwargs_shape`, **`test_capa_missing_sample_returns_invalid_kwargs`**, **`test_capa_path_traversal_returns_invalid_kwargs`**, `test_every_error_has_error_key`, `test_no_tool_handler_raises` (expanded) — all pass |
| `mcp-gateway/tests/jobs/` | 18+ test files | ✓ VERIFIED | All Phase 9 test files present; 68 non-slow tests pass |
| `mcp-gateway/tests/jobs/conftest.py` | Shared fixtures: `registry_factory`, `fake_ctx`, `case_dir_fixture`, `_require_capa_or_skip` | ✓ VERIFIED | All 4 fixture symbols confirmed |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `tools/jobs.py::start_tool_job` | `jobs.py::BackgroundJobRegistry.submit → spec.build_argv → _build_capa_argv → samples.resolve_sample` | Broader except clause around `registry.submit()` catches `(ValueError, FileNotFoundError, KeyError, OSError)` and converts to D-15 #4 `InvalidKwargs` dict (gap closure key link) | ✓ WIRED | `mcp-gateway/src/mcp_gateway/tools/jobs.py:167-176` — exact pattern from 09-05-PLAN present |
| `jobs.py::_validate_kwargs` | `jobs.py::_CAPA_SPEC.kwargs_schema` | New `required` rule handler raises `InvalidKwargs(field, 'required field', 'missing')` BEFORE `build_argv` is reached | ✓ WIRED | `mcp-gateway/src/mcp_gateway/jobs.py:269-270` and `:375` — both legs of two-layer defense present |
| `tools/jobs.py` | `jobs.py` | `from mcp_gateway import jobs` (module attribute access) | ✓ WIRED | Line 26 import; module constants accessed |
| `tools/jobs.py` | `session_state.py` | `session_state.JOB_REGISTRY` via `_require_registry` | ✓ WIRED | `_require_registry()` returns `session_state.JOB_REGISTRY` |
| `app.py` | `jobs.py` | `from .jobs import BackgroundJobRegistry, MAX_JOBS_INFLIGHT, JOB_CANCEL_GRACE_S, MAX_COMPLETED_JOBS` | ✓ WIRED | Line 29 import block; `_build_job_registry` uses module constants |
| `app.py` | `session_state.py` | `session_state.JOB_REGISTRY = registry / None` in try/finally | ✓ WIRED | 4 occurrences confirmed: set in both branches + clear in both finally blocks |
| `tools/__init__.py` | `tools/jobs.py` | `from . import jobs` + `jobs.register(mcp)` | ✓ WIRED | Line 43 import, line 57 register call; ordering before `backend_passthrough` confirmed |
| `tests/jobs/conftest.py` | `jobs.py` | `BackgroundJobRegistry` + dual-module `importlib.reload` | ✓ WIRED | `registry_factory` fixture confirmed |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `tools/jobs.py::start_tool_job` | snapshot dict (D-19 25 keys) OR D-15 #4 InvalidKwargs dict on build_argv failure | `registry.submit() → _build_snapshot(job)` OR caught `(ValueError, FileNotFoundError, KeyError, OSError)` → `InvalidKwargs.to_dict()` | Yes — real subprocess for success path; structured error dict for failure path | ✓ FLOWING |
| `tools/jobs.py::get_tool_job` | snapshot dict + progress push | `registry.get(job_id) → _build_snapshot(job)` + `ctx.report_progress` | Yes — live job state from in-memory `Job` dataclass | ✓ FLOWING |
| `tools/jobs.py::list_tool_jobs` | jobs list or specs catalog | `registry.list_inflight() + registry.list_completed()` or `JOB_TOOL_REGISTRY` | Yes — live registry state | ✓ FLOWING |
| `jobs.py::_spawn_and_drive` | log file, progress fields, snapshot | `asyncio.create_subprocess_exec` + `_drain` | Yes — real subprocess I/O; log written to `tool-logs/` | ✓ FLOWING |
| `jobs.py::_validate_kwargs` (new required rule) | InvalidKwargs raised on missing required field | `rule.get("required")` check at top of per-field loop | Yes — produces correct D-15 #4 `InvalidKwargs(field, 'required field', 'missing')` | ✓ FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SC-1: `start_tool_job` returns 25-key snapshot | `pytest tests/jobs/test_start_tool_job.py` | 7 passed | ✓ PASS |
| SC-2: poll/cancel/list contracts | `pytest tests/jobs/test_get_tool_job.py test_cancel_grace.py test_list_tool_jobs.py` | 11 passed | ✓ PASS |
| SC-3: log cap → killed_log_cap + marker | `pytest tests/jobs/test_log_cap.py` | 1 passed | ✓ PASS |
| SC-4: subprocess dead within 200ms | `pytest tests/jobs/test_disconnect_200ms.py` | 1 passed | ✓ PASS |
| SC-5: progress dedup by session_id | `pytest tests/jobs/test_progress.py` | 5 passed | ✓ PASS |
| SC-6: LIFO unwind on shutdown | `pytest tests/jobs/test_lifespan_integration.py` | 1 passed | ✓ PASS |
| D-15: all four error shapes + capa regression paths | `pytest tests/jobs/test_errors.py -v` | **8 passed** (6 prior + 2 new); includes `test_capa_missing_sample_returns_invalid_kwargs` PASSED and `test_capa_path_traversal_returns_invalid_kwargs` PASSED | ✓ PASS |
| D-26: disclaimer in all docstrings | `pytest tests/jobs/test_docstring_disclaimer.py` | 12 passed | ✓ PASS |
| Phase 9 non-slow full suite | `pytest tests/jobs/ -m 'not slow' --ignore=tests/jobs/test_capa_integration.py` | **68 passed** (was 66 → +2 new) | ✓ PASS |
| Full gateway non-slow suite | `pytest -m 'not slow' tests/ --ignore=tests/test_acl_available.py` | **323 passed**, 46 skipped, 3 deselected (was 321 → +2 new) | ✓ PASS |
| capa integration (slow) | `pytest -m slow tests/jobs/test_capa_integration.py` | 1 skipped (capa not on host) | ? SKIP (expected; container-only) |
| Bare-Exception non-regression | `grep -c "except Exception" src/mcp_gateway/tools/jobs.py` | 1 (baseline unchanged) | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| JOBS-01 | Plans 01, 02, 04, **05** | Agent can start background job via `start_tool_job`, opaque `job_id`, runs through `ReToolRunner` safety properties | ✓ SATISFIED | `start_new_session=True`, `killpg`, cwd-confine in `jobs.py`; `test_start_tool_job` + `test_disconnect_200ms` pass. Plan 05 closed the D-15 #4 escape paths for capa specifically referenced under JOBS-01. |
| JOBS-02 | Plans 02, 04 | Agent can poll via `get_tool_job` returning status, head-tail stdout/stderr, exit code, log path | ✓ SATISFIED | D-19 25-key snapshot confirmed; `test_get_tool_job` 3 tests pass |
| JOBS-03 | Plans 02, 04 | Agent can cancel via `cancel_tool_job` (SIGTERM then SIGKILL grace) | ✓ SATISFIED | D-07 SIGTERM-grace-SIGKILL ladder in `cancel()`; idempotent; `test_cancel_grace` 2 tests pass |
| JOBS-04 | Plans 01, 03, 04 | Agent can list active/completed jobs via `list_tool_jobs`; registry in-memory only; restart cancels | ✓ SATISFIED | `list_tool_jobs` implemented; `BackgroundJobRegistry` in-memory; D-26 disclaimer documents behavior; `test_registry_lifecycle` + `test_list_tool_jobs` pass |
| JOBS-05 | Plans 01, 04 | Log capped at `MAX_JOB_LOG_MB`; over-cap → `killed_log_cap`; completed jobs LRU-cleaned | ✓ SATISFIED | `_drain` counter cap + `MARE_JOB_KILLED_LOG_CAP` marker; FIFO eviction via `OrderedDict.popitem(last=False)`; `test_log_cap` + `test_lru_retention` pass |
| JOBS-06 | Plans 01, 04 | Jobs survive request cancellation; subprocess dead within 200ms | ✓ SATISFIED | `asyncio.shield(proc.wait())` in `cancel()`; `test_disconnect_200ms` passes |
| JOBS-07 | Plans 02, 04 | Progress notifications via `Context.report_progress` | ✓ SATISFIED | D-16 Tier-2 in `get_tool_job`; `_last_reported_to` session-id dedup; `test_progress` 5 tests pass |

All 7 JOBS-XX requirements have passing test evidence. REQUIREMENTS.md (lines 65-71) marks all 7 `[x]` complete; tracking table (lines 161-167) maps all to Phase 9.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|---------|--------|
| `jobs.py` | ~542-569 | Two-lock submit: cap check lock released before inflight insertion lock (CR-03) | ℹ️ Info (deferred) | Concurrent submits at cap-1 can both pass check; max_inflight briefly exceeded. Correctness warning, NOT a D-15 escape. **Explicitly deferred** in 09-05-PLAN (out of scope) and 09-05-SUMMARY non-goals. Not required to close phase goal. |
| `jobs.py` | ~457-472 | `line_buf` (bytearray for stderr progress parsing) has no upper bound other than log cap (WR-03) | ℹ️ Info (deferred) | Misbehaving tools without newlines hold up to 256 MiB in RAM before cap-kill fires. **Explicitly deferred** in 09-05-PLAN (out of scope). Not required to close phase goal. |

**Note:** The two previously-flagged BLOCKER findings (CR-01 path-traversal escape, CR-02 missing-required-kwarg escape) have been **closed** by Plan 09-05. The remaining anti-patterns are informational deferrals tracked for a future hardening phase — they do NOT block the phase goal of "remote agents can launch long-running RE tools and poll for completion without hitting the 60s MCP request cap."

### Human Verification Required

None — all observable truths are verified programmatically. The capa integration test (SC-6 user-visible spec) is gated by `_require_capa_or_skip` and skips cleanly on the dev host; it will execute when capa is present in the container image.

### Gaps Summary

**No gaps.** The single gap from the initial verification (truth #7 / D-15 "tools never raise" contract hole for the `capa` tool's two escape paths) has been **fully closed** by Plan 09-05:

1. **Schema-level defense (first line):** `_CAPA_SPEC.kwargs_schema["sample"]["required"] = True` + `_validate_kwargs` honors the new `required` rule, raising `InvalidKwargs(field='sample', expected='required field', got='missing')` BEFORE `build_argv` is reached. Verified by `test_capa_missing_sample_returns_invalid_kwargs` PASSED.

2. **Boundary-level defense (second line):** `start_tool_job` now has a second `except (ValueError, FileNotFoundError, KeyError, OSError)` branch around `registry.submit()` that converts any `build_argv`-time exception to a D-15 #4 `InvalidKwargs(field='kwargs', expected='valid per-tool argv inputs', got=f'{type(e).__name__}: {e}')` dict. Verified by `test_capa_path_traversal_returns_invalid_kwargs` PASSED.

3. **Regression coverage:** `test_no_tool_handler_raises` (the D-15 negative-control test) expanded to call both previously-broken capa paths inside `_no_exception` — both now succeed without raising.

4. **No bare-Exception swallowing introduced:** `except Exception` count in `tools/jobs.py` remains at 1 (the existing top-level handler that returns a structured dict). The new catch is narrow and intentional.

5. **No regressions:** Phase 9 non-slow suite grew from 66 → 68 passed (the 2 added regression tests); full gateway non-slow suite grew from 321 → 323 passed; all skips unchanged.

The phase goal — "remote agents can launch long-running RE tools and poll for completion without hitting the 60s MCP request cap" — is achieved. All 7 SC criteria pass; all 7 JOBS-XX requirements satisfied; all 7 observable must-have truths verified.

---

_Re-verified: 2026-05-19T03:26:38Z_
_Previous status: gaps_found (5/7) → Current status: passed (7/7)_
_Verifier: Claude (gsd-verifier)_
