---
phase: 13-harden-concurrency-caps-and-r2-sandboxing
verified: 2026-05-21T10:00:00Z
status: human_needed
score: 9/9 must-haves verified (automated); 1 item requires in-container test
overrides_applied: 0
---

# Phase 13: Harden concurrency caps and r2 sandboxing — Verification Report

**Phase Goal:** Make session and job cap enforcement atomic under concurrency (replace TOCTOU `count >= max` with `asyncio.BoundedSemaphore`), and move the r2 security boundary from a regex parser-arms-race onto r2's native `cfg.sandbox=true` (enforced at argv-eval time, BEFORE binary open). Adds env-gated `open_r2_session_unsafe` opt-in (`MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`) with WARN-level audit logging.
**Verified:** 2026-05-21
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| # | Requirement | Truth | Status | Evidence |
|---|-------------|-------|--------|----------|
| 1 | HARDEN-01 | Two concurrent open_r2_session / open_gdb_session callers against cap=N never both proceed past it; exactly 1 of N+1 raises SessionCapReached | VERIFIED | `test_n_concurrent_opens_exactly_one_rejected` passes; atomic probe-and-acquire confirmed in r2.py:172-176, gdb.py:304-308 |
| 2 | HARDEN-01 | Cancel/OSError/RuntimeError during spawn releases the slot (no slot leak) | VERIFIED | `test_cancel_during_spawn_releases_slot`, `test_oserror_during_spawn_releases_slot`, `test_runtime_error_during_init_releases_slot` pass; `except BaseException: registry._sem.release()` at r2.py:280-287, gdb.py:427-433 |
| 3 | HARDEN-02 | N+1 concurrent BackgroundJobRegistry.submit() calls against cap=N → exactly 1 raises JobCapReached | VERIFIED | `test_n_concurrent_submits_exactly_one_rejected` passes; atomic probe-and-acquire at jobs.py:562-569 |
| 4 | HARDEN-02 | All 7 terminal-state paths release the slot exactly once via _mark_terminal | VERIFIED | `test_terminal_transitions_release_exactly_once` covers 4 reachable statuses (succeeded/failed/cancelled/killed_timeout); `_mark_terminal` release at jobs.py:757-763 guarded by `_slot_released`; killed_log_cap path covered by existing `test_log_cap.py` |
| 5 | HARDEN-03 | r2 sessions spawned with `[-e, cfg.sandbox=true]` BEFORE the positional sample path when sandbox=True | VERIFIED | `test_argv_sandbox_flag_present_before_sample` passes; argv building at r2.py:194-197: `argv += ["-e", "cfg.sandbox=true"]` then `argv.append(str(sample_path))` |
| 6 | HARDEN-04 | No `cfg.sandbox.grain` argv flag emitted (default grain=all preserved) | VERIFIED | `test_argv_no_grain_override` passes (parametrized over True/False); `grep "cfg.sandbox.grain" sessions/r2.py` returns 0 |
| 7 | HARDEN-05 | `_DANGEROUS_R2_CMD_RE` pattern is byte-identical to Phase 8; docstring reframed with "DO NOT EXTEND" + "PHASE 13 SECURITY BOUNDARY DELINEATION" | VERIFIED | `test_dangerous_regex_frozen` + `test_dangerous_regex_docstring_reframed` pass; pattern confirmed: `(?:^;\|\||\n)\s*(?:#!|R!|!)` |
| 8 | HARDEN-06 | `open_r2_session_unsafe` registered iff `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`; absent from tools/list when unset | VERIFIED | `test_tool_list_with_unsafe_axis` (4-case parametrize: 54/55/61/62) passes; env-gate at tools/__init__.py:80-81 |
| 9 | HARDEN-07 | `SessionCapReached.to_dict()` and `JobCapReached.to_dict()` are byte-identical to pre-Phase-13 | VERIFIED | `test_session_cap_reached_dict_shape` + `test_job_cap_reached_dict_shape` pass; smoke test confirms shapes |
| 10 | SESS-CAP-01 | Reaper-closes-idle and shutdown-closes-active release slots without semaphore ValueError | VERIFIED | `test_reaper_idle_releases_slot` + `test_shutdown_active_releases_or_clean_exit` pass; release at _base.py:330-336 guarded by `_slot_released` flag |
| 11 | JOBS-CAP-01 | Pre-spawn failure in submit() (e.g., ensure_subdir raises) releases the slot | VERIFIED | `test_cancel_pre_spawn_releases` passes; `except BaseException: self._sem.release()` at jobs.py:606-613 |
| 12 | HARDEN-03 (in-container) | `e cfg.sandbox` query inside a live r2 session returns `true` at runtime | HUMAN NEEDED | `test_sandbox_active_when_open_r2` is `@pytest.mark.slow` + gated on `_require_r2_or_skip`; skips on dev host (r2 unavailable). Wave 0 probe `test_r2_cfg_sandbox_supported` also skips. These tests are container-ready. |

**Score:** 11/11 automated truths verified

---

### Required Artifacts

| Artifact | Expected | Status | Evidence |
|----------|----------|--------|----------|
| `mcp-gateway/src/mcp_gateway/sessions/_base.py` | `self._sem: asyncio.BoundedSemaphore` on SessionRegistry; `_slot_released: bool = False` on BaseSession; release in close() live-close branch | VERIFIED | `self._sem` at line 194; `_slot_released` field at line 138; release at lines 330-336 |
| `mcp-gateway/src/mcp_gateway/sessions/r2.py` | `_open_r2` atomic probe+acquire under registry._lock; release-on-failure except branch; `-e cfg.sandbox=true` argv; `sandbox: bool = True` kwarg; frozen regex with reframed docstring | VERIFIED | Atomic block at lines 172-176; except BaseException at lines 280-287; argv at lines 194-197; kwarg at line 144; regex at lines 64-66 with sentinel strings at lines 43-63 |
| `mcp-gateway/src/mcp_gateway/sessions/gdb.py` | `_open_gdb` atomic probe+acquire under registry._lock; release-on-failure except branch | VERIFIED | Atomic block at lines 304-308; except BaseException at lines 427-433 |
| `mcp-gateway/src/mcp_gateway/jobs.py` | `self._sem: asyncio.BoundedSemaphore` on BackgroundJobRegistry; `_slot_released: bool = False` on Job; pre-spawn except release; single release at end of _mark_terminal | VERIFIED | `self._sem` at line 527; `_slot_released` at line 198; submit except at lines 606-613; _mark_terminal release at lines 757-763 |
| `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` | `open_r2_session_unsafe` coroutine + `register_unsafe(mcp)` function; calls `registry.open(..., sandbox=False)`; WARN log on open; `warnings` field with literal | VERIFIED | `open_r2_session_unsafe` at line 401; `register_unsafe` at line 495; `sandbox=False` at line 462; `log.warning` at line 469; warnings field at line 484 |
| `mcp-gateway/src/mcp_gateway/tools/__init__.py` | Env-gate block for `MCP_GATEWAY_R2_UNSAFE_ALLOWED` calling `r2_sessions.register_unsafe(mcp)` | VERIFIED | Env-gate at lines 80-81 |
| `mcp-gateway/tests/test_sessions_concurrency.py` | 6 concurrency-atomicity tests (N+1 contention + 5 failure-cleanup matrix rows) | VERIFIED | File exists, 17252 bytes, 6 test functions confirmed |
| `mcp-gateway/tests/jobs/test_concurrency.py` | 3 concurrency-atomicity tests | VERIFIED | File exists, 8079 bytes, 3 test functions confirmed |
| `mcp-gateway/tests/test_r2_argv.py` | 3 argv-builder tests (4 parametrized cases, no r2 spawn) | VERIFIED | File exists, 3849 bytes; 4 cases pass |
| `mcp-gateway/tests/test_r2_version.py` | Wave 0 r2 version + cfg.sandbox accept probe (skip on dev host) | VERIFIED | File exists, 2121 bytes; 2 tests skip cleanly on dev host |
| `mcp-gateway/tests/test_r2_sandbox_integration.py` | Integration positive control (skip on dev host, runs in container) | VERIFIED | File exists, 1834 bytes; skips cleanly on dev host |

---

### Key Link Verification

| From | To | Via | Status | Evidence |
|------|-----|-----|--------|----------|
| `sessions/r2.py::_open_r2` | `registry._sem.acquire()` | atomic probe-and-acquire under `registry._lock` | WIRED | `registry._sem.locked()` probe + `await registry._sem.acquire()` at r2.py:173-175 |
| `sessions/gdb.py::_open_gdb` | `registry._sem.acquire()` | atomic probe-and-acquire under `registry._lock` | WIRED | Same pattern at gdb.py:305-307 |
| `sessions/_base.py::SessionRegistry.close` | `self._sem.release()` | live-close branch, guarded by `_slot_released` | WIRED | `self._sem.release()` at _base.py:332; guard at line 330 |
| `jobs.py::BackgroundJobRegistry.submit` | `self._sem.acquire()` | atomic probe-and-acquire under `self._lock` | WIRED | `self._sem.locked()` probe + `await self._sem.acquire()` at jobs.py:563-565 |
| `jobs.py::BackgroundJobRegistry._mark_terminal` | `self._sem.release()` | single release at end of function, guarded by `_slot_released` | WIRED | `self._sem.release()` at jobs.py:759; guard at line 757 |
| `tools/__init__.py` | `tools/r2_sessions.py::register_unsafe` | `if _os.environ.get("MCP_GATEWAY_R2_UNSAFE_ALLOWED") == "1"` | WIRED | `r2_sessions.register_unsafe(mcp)` at __init__.py:81 |
| `tools/r2_sessions.py::open_r2_session_unsafe` | `sessions/r2.py::_open_r2` | `registry.open(..., sandbox=False)` propagates through `SessionRegistry.open` to `_open_r2` | WIRED | `sandbox=False` at r2_sessions.py:462; `SessionRegistry.open` forwards `sandbox` kwarg at _base.py:263 |

---

### Data-Flow Trace (Level 4)

Not applicable. This phase delivers concurrency primitives and security boundary changes, not components that render dynamic UI data. The cap-reject error dicts are tested for byte-identical content by snapshot tests.

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| SessionRegistry has BoundedSemaphore | smoke import + isinstance check | PASS | PASS |
| BaseSession has _slot_released field | `'_slot_released' in BaseSession.__dataclass_fields__` | True | PASS |
| BackgroundJobRegistry has BoundedSemaphore | smoke import + isinstance check | PASS | PASS |
| Job has _slot_released field | `'_slot_released' in Job.__dataclass_fields__` | True | PASS |
| SessionCapReached.to_dict() exact shape | dict equality check | Matches expected 4-key dict | PASS |
| JobCapReached.to_dict() exact shape | dict equality check | Matches expected 4-key dict | PASS |
| _DANGEROUS_R2_CMD_RE pattern | pattern string equality | Byte-identical to Phase 8 | PASS |
| _open_r2 sandbox kwarg default | inspect.signature check | `sandbox` param default is True | PASS |
| SessionRegistry.open sandbox forwarding | inspect.signature + source grep | sandbox kwarg forwarded to _open_r2 | PASS |
| Legacy racy cap checks removed | grep in r2.py, gdb.py, jobs.py | 0 matches for old patterns | PASS |
| r2 cfg.sandbox active at runtime | `test_sandbox_active_when_open_r2` | SKIP (no r2 on dev host) | HUMAN NEEDED |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| HARDEN-01 | 13-01 | Cap-enforcement is atomic across concurrent callers — SessionRegistry r2+gdb | SATISFIED | `test_n_concurrent_opens_exactly_one_rejected` + 5 failure-cleanup matrix tests |
| HARDEN-02 | 13-02 | Cap-enforcement is atomic across concurrent callers — BackgroundJobRegistry.submit | SATISFIED | `test_n_concurrent_submits_exactly_one_rejected` + `test_terminal_transitions_release_exactly_once` + `test_cancel_pre_spawn_releases` |
| HARDEN-03 | 13-03 | r2 spawn is sandboxed at argv-eval time via `cfg.sandbox=true` | SATISFIED (automated) + HUMAN NEEDED (in-container positive control) | `test_argv_sandbox_flag_present_before_sample` passes; `test_sandbox_active_when_open_r2` skips on dev host |
| HARDEN-04 | 13-03 | No `cfg.sandbox.grain` argv flag; default grain=all | SATISFIED | `test_argv_no_grain_override` passes; 0 grep matches |
| HARDEN-05 | 13-03 | `_DANGEROUS_R2_CMD_RE` frozen + reframed docstring with sentinel strings | SATISFIED | `test_dangerous_regex_frozen` + `test_dangerous_regex_docstring_reframed` pass |
| HARDEN-06 | 13-04 | `open_r2_session_unsafe` env-gated; not in tools/list when MCP_GATEWAY_R2_UNSAFE_ALLOWED unset | SATISFIED | `test_tool_list_with_unsafe_axis` 4-case parametrize passes; `test_unsafe_r2_absent_baseline` + `test_unsafe_r2_present_with_env` pass |
| HARDEN-07 | 13-01, 13-02 | Cap-reject error dict shapes byte-identical to pre-Phase-13 | SATISFIED | `test_session_cap_reached_dict_shape` + `test_job_cap_reached_dict_shape` pass |
| SESS-CAP-01 | 13-01 | Session slot lifecycle: acquire-before-spawn, release-on-close and spawn-failure | SATISFIED | 6 concurrency tests pass; reaper and shutdown paths verified |
| JOBS-CAP-01 | 13-02 | Job slot lifecycle: acquire-before-submit, single release via _mark_terminal | SATISFIED | 3 concurrency tests pass; 4 terminal-status release assertions pass |

---

### Anti-Patterns Found

| File | Pattern | Severity | Assessment |
|------|---------|----------|------------|
| None | — | — | No TODO/FIXME/placeholder patterns found in phase-13 modified files. No empty return stubs. No hardcoded empty arrays as rendering data. |

---

### Human Verification Required

#### 1. r2 cfg.sandbox active at runtime (HARDEN-03 in-container positive control)

**Test:** Inside the Kali container, run `cd mcp-gateway && pytest tests/test_r2_sandbox_integration.py -v`
**Expected:** `test_sandbox_active_when_open_r2` PASSES. The test opens a real r2 session with `sandbox=True`, sends `e cfg.sandbox` via `exec_one`, and asserts the response contains `true`.
**Why human:** r2 is not available on the dev host. The argv ordering unit test (`test_argv_sandbox_flag_present_before_sample`) proves the `-e cfg.sandbox=true` flag is in the argv in the correct position. The runtime positive control verifies that r2 actually accepts and activates the flag — this is the last mile that cannot be verified without the container.

**Also run (bonus):**
- `pytest tests/test_r2_version.py -v` — verifies r2 version is parseable and cfg.sandbox is accepted without "unknown variable" warning.
- `pytest tests/test_r2_sessions.py::test_unsafe_open_warn_log -v` — verifies the WARN-level log line is emitted on a real unsafe-session open.

---

### Gaps Summary

No automated gaps. All 9 requirements (HARDEN-01 through HARDEN-07, SESS-CAP-01, JOBS-CAP-01) are satisfied by code that exists, is substantive, is wired, and is covered by passing tests on the dev host.

The single human-verification item (HARDEN-03 in-container positive control) is a correctness confirmation for a path whose argv ordering is already proven by automated unit tests. It is not a blocker in the code-exists-and-is-wired sense — the implementation is correct and complete. The test was designed to skip on dev hosts and run in the container from the beginning (per VALIDATION.md manual-only verification section and 13-03-SUMMARY.md Wave 0 A1 Status).

**Pre-existing test isolation pollution (not caused by Phase 13):**
Four tests in `tests/jobs/` fail under full-suite ordering due to Phase 11 dynamic-tools registering into `JOB_TOOL_REGISTRY` when an earlier test imports `mcp_gateway.tools.dynamic` (documented in `deferred-items.md`). These reproduce against the pre-Phase-13 commit and are out of scope. The Phase 13 jobs tests all pass in isolation and when deselecting these 4 known-bad tests (`-k "not test_unknown_tool_shape and not test_specs_default_hides_underscore and not test_specs_with_include_internal_shows_all and not test_progress_fields_set_on_drive"`).

---

## Test Run Summary

| Suite | Command | Result |
|-------|---------|--------|
| Sessions concurrency + HARDEN-07 + HARDEN-05 + argv | `pytest tests/test_sessions_concurrency.py tests/test_sessions.py::test_session_cap_reached_dict_shape tests/test_sessions.py::test_dangerous_regex_frozen tests/test_sessions.py::test_dangerous_regex_docstring_reframed tests/test_r2_argv.py` | 13 passed |
| Jobs concurrency + HARDEN-07 | `pytest tests/jobs/test_concurrency.py tests/jobs/test_errors.py::test_job_cap_reached_dict_shape` | 4 passed |
| HARDEN-06 tool list + unsafe session | `pytest tests/test_tool_list.py::test_tool_list_with_unsafe_axis tests/test_r2_sessions.py::test_unsafe_passes_sandbox_false tests/test_r2_sessions.py::test_unsafe_shares_combined_cap` | 6 passed |
| r2 version + sandbox integration | `pytest tests/test_r2_version.py tests/test_r2_sandbox_integration.py` | 3 skipped (r2 unavailable on dev host) |
| Full sessions regression | `pytest tests/test_sessions.py tests/test_sessions_package.py tests/test_sessions_concurrency.py tests/test_gdb_session.py -k "not slow"` | 79 passed, 3 skipped |
| Full jobs regression (minus 4 pre-existing pollution) | `pytest tests/jobs/ -k "not slow and not test_unknown_tool_shape..."` | 68 passed |
| Full tool list | `pytest tests/test_tool_list.py` | 15 passed |

---

_Verified: 2026-05-21_
_Verifier: Claude (gsd-verifier)_
