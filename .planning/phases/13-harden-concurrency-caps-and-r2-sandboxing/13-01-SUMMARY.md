---
phase: 13
plan: 01
subsystem: sessions
tags:
  - harden
  - concurrency
  - sessions
  - bounded-semaphore
  - toctou
  - cap-enforcement
requirements:
  - HARDEN-01
  - HARDEN-07
  - SESS-CAP-01
requirements_addressed:
  - HARDEN-01
  - HARDEN-07
  - SESS-CAP-01
dependency_graph:
  requires:
    - phase-08-session-scoped-r2 (SessionRegistry shape, SessionCapReached contract)
    - phase-11-dynamic-lab-mode-env-gated (sessions/ package, gdb driver, combined r2+gdb cap)
  provides:
    - "self._sem: asyncio.BoundedSemaphore on SessionRegistry (cap-enforcement gate)"
    - "_slot_released: bool field on BaseSession (release-idempotency guard)"
    - "Atomic probe-and-acquire pattern in _open_r2 / _open_gdb"
    - "6-test concurrency-atomicity matrix + 1-test dict-shape snapshot"
  affects:
    - tools/r2_sessions.py (cap-reject error dict shape preserved verbatim)
    - tools/jobs.py (SessionCapReached.to_dict() contract preserved)
tech-stack:
  added: []
  patterns:
    - "asyncio.BoundedSemaphore as cap-enforcement primitive (stdlib, 3.10+ cancel-safe)"
    - "Atomic probe-and-acquire under registry._lock (Pitfall 3 fix)"
    - "_slot_released idempotency flag + try/except BaseException release-on-failure"
    - "Stub-driver concurrency tests with pgid sentinel + os.killpg autouse patch"
key-files:
  created:
    - mcp-gateway/tests/test_sessions_concurrency.py
  modified:
    - mcp-gateway/src/mcp_gateway/sessions/_base.py
    - mcp-gateway/src/mcp_gateway/sessions/r2.py
    - mcp-gateway/src/mcp_gateway/sessions/gdb.py
    - mcp-gateway/tests/test_sessions.py
decisions:
  - "BoundedSemaphore (not plain Semaphore) on SessionRegistry as `self._sem` attr -- raises ValueError on over-release, fails loud on cleanup bugs (CONTEXT.md D-01)"
  - "Atomic probe-and-acquire pattern: probe locked() + acquire() under registry._lock so the test-and-take is one atomic step (RESEARCH.md Pitfall 3 fix)"
  - "Release happens at exactly two points: spawn-failure except branch AND close() live-close branch -- never in __aexit__ (D-02 invariant)"
  - "_slot_released bool flag on BaseSession dataclass guards against double-release across spawn-failure -> close() and reaper -> shutdown paths (Pitfall 4/5)"
  - "Cap-reject error payload still reads from registry.count_open() + registry.list() (the dict is truth, semaphore is gate -- D-04 invariant preserved)"
  - "SessionCapReached.to_dict() shape locked byte-identical via test_session_cap_reached_dict_shape (HARDEN-07 / D-03)"
  - "Concurrency tests use stub _open_r2 driver + sentinel pgid=-99999 + autouse os.killpg patch so killpg cannot SIGKILL the test runner's own process group"
metrics:
  duration: 459s
  tasks: 3
  files: 5
  completed: 2026-05-20
---

# Phase 13 Plan 01: Atomic SessionRegistry cap enforcement Summary

Replaced TOCTOU `if count_open() >= max: raise` cap check in `_open_r2` and `_open_gdb` with an `asyncio.BoundedSemaphore` reservation acquired atomically under `registry._lock` and released on close() or any spawn-failure path. Two concurrent open callers can no longer both observe `count<cap` and both proceed.

## What Was Built

### Files modified (3 source + 2 test)

1. **mcp-gateway/src/mcp_gateway/sessions/_base.py** — added `self._sem: asyncio.BoundedSemaphore(max_sessions)` in `SessionRegistry.__init__`; added `_slot_released: bool = False` as the last field of `BaseSession`; added a single `self._sem.release()` site in `SessionRegistry.close()` guarded by `getattr(sess, "_slot_released", False)` + `try/except ValueError`. `count_open()` / `list()` / `__aexit__` unchanged (D-04 dict-is-truth invariant).

2. **mcp-gateway/src/mcp_gateway/sessions/r2.py::_open_r2** — replaced lines 130-134 (the racy `count_open() >= _max` check) with the atomic probe-and-acquire pattern. Wrapped spawn-through-register body in `try/except BaseException` so spawn failures (`CancelledError` + `Exception`) release the slot. Sets `sess._slot_released = True` on the failure path so any subsequent `close()` call is a no-op on the semaphore.

3. **mcp-gateway/src/mcp_gateway/sessions/gdb.py::_open_gdb** — mirror-image change to lines 300-304, same pattern. Internal init-batch try/except blocks (lockdown + init_commands) preserved verbatim; their `raise RuntimeError(...)` propagates UP through the outer except.

4. **mcp-gateway/tests/test_sessions_concurrency.py** — 6 new tests covering the D-02 failure-cleanup matrix:
   - `test_n_concurrent_opens_exactly_one_rejected` (T-13-01 central proof: 4 concurrent against cap=3 → exactly 1 SessionCapReached)
   - `test_cancel_during_spawn_releases_slot`
   - `test_oserror_during_spawn_releases_slot`
   - `test_runtime_error_during_init_releases_slot`
   - `test_reaper_idle_releases_slot`
   - `test_shutdown_active_releases_or_clean_exit`

5. **mcp-gateway/tests/test_sessions.py** — 1 new snapshot test `test_session_cap_reached_dict_shape` locking the cap-reject dict shape byte-identical to pre-Phase-13 (HARDEN-07 / D-03 contract).

## Key Invariants Locked in Tests

| Invariant | Test | Source |
|-----------|------|--------|
| HARDEN-01 atomic cap (no TOCTOU) | `test_n_concurrent_opens_exactly_one_rejected` | CONTEXT.md D-01..D-03 |
| HARDEN-07 dict shape byte-identical | `test_session_cap_reached_dict_shape` | CONTEXT.md D-03 |
| SESS-CAP-01 slot lifecycle (5 failure modes) | 5 D-02 matrix tests | CONTEXT.md D-02 |
| D-04 dict-is-truth (no semaphore counter leakage) | Test inspects `to_dict()` payload still uses `count_open()` | CONTEXT.md D-04 |

## Threat Model Verification

| Threat ID | Mitigation Verified By |
|-----------|------------------------|
| **T-13-01** (DoS via TOCTOU) | `test_n_concurrent_opens_exactly_one_rejected` — 4 concurrent calls against cap=3 always produce exactly 3 successes + 1 SessionCapReached. The atomic probe-and-acquire under `registry._lock` closes the race window. |
| **T-13-02** (cleanup-path crash on over-release) | 5 D-02 matrix tests — every failure path (cancel/oserror/runtime-error/reaper-idle/shutdown) releases the slot exactly once; `_slot_released` flag prevents double-release; no `ValueError` raised under any tested scenario. |
| **T-13-03** (cap-reject contract change) | `test_session_cap_reached_dict_shape` locks `to_dict()` byte-identical; legacy `test_cap_reject` continues to assert the same shape on the integration path. |
| **T-13-04** (info disclosure via list_sessions) | D-04 preserved — `list()` and `count_open()` continue reading from `self._sessions`, not the semaphore counter. Operators see the same shape as before. |

## Verification Results

```
=== Final regression run ===
tests/test_sessions.py            sss......        (3 r2-skip + 6 PASS)
tests/test_sessions_concurrency.py ......          (6 PASS — all new)
tests/test_sessions_package.py    ..........       (10 PASS)
tests/test_gdb_session.py         ...46.tests...   (54 collected, 52 PASS + 2 gdb-skip)
================ 77 passed, 5 skipped, 1 warning in 6.10s ================
```

Smoke test:
```
$ python -c "from mcp_gateway.sessions import SessionRegistry; ..."
SMOKE TEST OK
```

## Deviations from Plan

**[Rule 1 - Bug] Sentinel pgid + os.killpg autouse patch in test_sessions_concurrency.py.**

- **Found during:** Task 3 test execution
- **Issue:** Initial stub sessions used `pgid=0` (the default for `BaseSession`). `SessionRegistry.close()` calls `os.killpg(sess.pgid, SIGKILL)`. With `pgid=0`, killpg sends SIGKILL to the **current process group** — i.e., the test runner itself. The result was a silent exit-137 OOM-like kill on the first concurrency test that exercised the shutdown path.
- **Fix:**
  1. Sentinel `_STUB_PGID = -99999` (a never-existing pgid) so killpg raises `ProcessLookupError` (already caught silently by `close()`).
  2. Belt-and-braces `@pytest.fixture(autouse=True)` that monkeypatches `os.killpg` to refuse any non-positive pgid with `ProcessLookupError`. The kill code path is still exercised; only the actual signal-send is bypassed.
- **Files modified:** `tests/test_sessions_concurrency.py` (test infrastructure only; no production code change)
- **Commit:** 497ba7b

This is a Rule-1 bug fix on the test harness; the production code is unchanged and the original plan structure (stub `_open_r2` + 6 D-02 matrix tests) is preserved.

No other deviations.

## Authentication Gates

None — no auth surfaces touched by this plan.

## Self-Check: PASSED

- mcp-gateway/src/mcp_gateway/sessions/_base.py: MODIFIED (verified via `git diff --stat HEAD~3..HEAD`)
- mcp-gateway/src/mcp_gateway/sessions/r2.py: MODIFIED
- mcp-gateway/src/mcp_gateway/sessions/gdb.py: MODIFIED
- mcp-gateway/tests/test_sessions_concurrency.py: CREATED (430 lines)
- mcp-gateway/tests/test_sessions.py: MODIFIED (test_session_cap_reached_dict_shape appended)
- Commit 6770453 (Task 1): FOUND in `git log`
- Commit 8a24bb7 (Task 2): FOUND in `git log`
- Commit 497ba7b (Task 3): FOUND in `git log`

All claimed artifacts exist; all claimed commits exist.
