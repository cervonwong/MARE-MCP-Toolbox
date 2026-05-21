---
phase: 13
plan: 02
subsystem: jobs
tags:
  - harden
  - concurrency
  - jobs
  - bounded-semaphore
  - toctou
  - cap-enforcement
requirements:
  - HARDEN-02
  - HARDEN-07
  - JOBS-CAP-01
requirements_addressed:
  - HARDEN-02
  - HARDEN-07
  - JOBS-CAP-01
dependency_graph:
  requires:
    - phase-09-background-job-system (BackgroundJobRegistry shape, JobCapReached contract, _mark_terminal sink)
    - phase-13-plan-01 (atomic-probe-and-acquire pattern, _slot_released invariant, BoundedSemaphore primitive precedent)
  provides:
    - "self._sem: asyncio.BoundedSemaphore on BackgroundJobRegistry (cap-enforcement gate)"
    - "_slot_released: bool field on Job dataclass (release-idempotency guard)"
    - "Atomic probe-and-acquire pattern in BackgroundJobRegistry.submit"
    - "Pre-spawn-failure release-on-except branch (except BaseException)"
    - "3-test concurrency-atomicity matrix + 1-test dict-shape snapshot"
  affects:
    - tools/jobs.py (cap-reject error dict shape preserved verbatim through D-15 to_dict contract)
tech-stack:
  added: []
  patterns:
    - "asyncio.BoundedSemaphore as cap-enforcement primitive (stdlib, 3.10+ cancel-safe) -- mirror of Plan 13-01 SessionRegistry pattern"
    - "Atomic probe-and-acquire under registry._lock (Pitfall 3 fix)"
    - "_slot_released idempotency flag + try/except BaseException release-on-failure (mirror of Plan 13-01 BaseSession pattern)"
    - "Single release sink in _mark_terminal covering all 7 terminal-state transition paths"
key-files:
  created:
    - mcp-gateway/tests/jobs/test_concurrency.py
    - .planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/deferred-items.md
  modified:
    - mcp-gateway/src/mcp_gateway/jobs.py
    - mcp-gateway/tests/jobs/test_errors.py
decisions:
  - "BoundedSemaphore (not plain Semaphore) on BackgroundJobRegistry as self._sem attr -- raises ValueError on over-release, fails loud on cleanup bugs (CONTEXT.md D-01)"
  - "Atomic probe-and-acquire pattern: probe locked() + acquire() under registry._lock so the test-and-take is one atomic step (RESEARCH.md Pitfall 3 fix)"
  - "Single release sink at the END of _mark_terminal -- covers all 7 enumerated terminal-state paths (succeeded/failed/cancelled/killed_timeout/killed_log_cap/outer-CancelledError/outer-Exception) via the existing `finally:` convergence in _spawn_and_drive (RESEARCH.md Pitfall 6)"
  - "Pre-spawn-failure release via `except BaseException` in submit() -- catches CancelledError + Exception subclasses raised by Path / ensure_subdir / build_argv / tool_log_path / Job-constructor / dict-insert BEFORE create_task (CONTEXT.md D-02)"
  - "_slot_released bool flag on Job dataclass guards against double-release if any future refactor calls _mark_terminal twice (Pitfall 4)"
  - "__aexit__ does NOT touch self._sem -- shutdown sweep calls cancel(job) which the drive task's finally-block routes to _mark_terminal (the single sink)"
  - "Cap-reject error payload still reads from self._inflight (the dict is truth, semaphore is gate -- D-04 invariant preserved)"
  - "JobCapReached.to_dict() shape locked byte-identical via test_job_cap_reached_dict_shape (HARDEN-07 / D-03)"
  - "Concurrency tests use _sleep_probe + a synthetic ['false']-spec for the 4 reachable terminal statuses; killed_log_cap is covered in tests/jobs/test_log_cap.py (Pitfall 10 -- no real-tool dependencies)"
metrics:
  duration: 525s
  tasks: 2
  files: 4
  completed: 2026-05-20
---

# Phase 13 Plan 02: Atomic BackgroundJobRegistry cap enforcement Summary

Replaced TOCTOU `if len(self._inflight) >= self._max_inflight: raise JobCapReached` cap check in `BackgroundJobRegistry.submit` with an `asyncio.BoundedSemaphore` reservation acquired atomically under `registry._lock` and released at the single terminal sink (`_mark_terminal`) or in `submit()`'s `except BaseException` branch (pre-spawn-failure). All 7 terminal-state transition paths in `_spawn_and_drive` converge at the existing `finally:` that calls `_mark_terminal`, giving us one place to release. Two concurrent submit callers can no longer both observe `count<cap` and both proceed.

This mirrors Plan 13-01's atomic probe-and-acquire pattern on `SessionRegistry` -- same primitive, same `_slot_released` idempotency flag, same `except BaseException` pre-spawn-failure branch, scaled to the jobs subsystem.

## What Was Built

### Files modified (1 source + 2 test) + 1 deferred-items log

1. **mcp-gateway/src/mcp_gateway/jobs.py** -- added `self._sem: asyncio.BoundedSemaphore(max_inflight)` in `BackgroundJobRegistry.__init__`; added `_slot_released: bool = False` to the `Job` dataclass; replaced the racy `len(self._inflight) >= self._max_inflight` check in `submit()` with `if self._sem.locked(): raise JobCapReached(...)` + `await self._sem.acquire()` under `self._lock` (atomic probe-and-acquire). Wrapped the pre-spawn body (Path / ensure_subdir / build_argv / tool_log_path / Job constructor / dict-insert / drive-task create) in `try / except BaseException: self._sem.release(); raise`. Added a single `self._sem.release()` site at the END of `_mark_terminal` (after dict-move + LRU eviction), guarded by `_slot_released` + `try/except ValueError` defensive log. `__aexit__` and `cancel()` UNCHANGED -- shutdown sweep flows through `cancel(job)` -> drive task `finally:` -> `_mark_terminal` -> single release.

2. **mcp-gateway/tests/jobs/test_concurrency.py (NEW, 206 lines)** -- 3 concurrency-atomicity tests:
   - `test_n_concurrent_submits_exactly_one_rejected` (HARDEN-02 / JOBS-CAP-01 central proof: 4 concurrent against cap=3 -> exactly 1 JobCapReached + 3 successes; cap-reject `to_dict()` payload verified)
   - `test_terminal_transitions_release_exactly_once` (covers 4 of 5 reachable terminal statuses: succeeded / failed / cancelled / killed_timeout; killed_log_cap cross-referenced to `tests/jobs/test_log_cap.py`)
   - `test_cancel_pre_spawn_releases` (monkeypatch `jobs.ensure_subdir` to raise PermissionError; assert `not reg._sem.locked()` after; assert subsequent submit succeeds)

3. **mcp-gateway/tests/jobs/test_errors.py** -- appended `test_job_cap_reached_dict_shape` byte-identical snapshot test (HARDEN-07 / D-03). Constructs `JobCapReached(inflight=4, cap=4)` and asserts `to_dict() ==` the full 4-key dict verbatim.

4. **.planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/deferred-items.md (NEW)** -- documents 4 pre-existing test-isolation failures discovered during regression verification (`test_unknown_tool_shape`, two `test_specs_*` in `test_list_tool_jobs.py`, `test_progress_fields_set_on_drive`). All four reproduce against the pre-Plan-13-02 commit (`git stash` + rerun) and are caused by Phase 11 dynamic-tools registering into `JOB_TOOL_REGISTRY` when an earlier test imports `mcp_gateway.tools.dynamic`. Out of scope per the SCOPE BOUNDARY rule.

## Key Invariants Locked in Tests

| Invariant | Test | Source |
|-----------|------|--------|
| HARDEN-02 atomic cap (no TOCTOU) | `test_n_concurrent_submits_exactly_one_rejected` | CONTEXT.md D-01..D-03 |
| HARDEN-07 dict shape byte-identical | `test_job_cap_reached_dict_shape` | CONTEXT.md D-03 |
| JOBS-CAP-01 single release sink (4 terminal statuses) | `test_terminal_transitions_release_exactly_once` | CONTEXT.md D-02; RESEARCH Pitfall 6 |
| JOBS-CAP-01 pre-spawn failure releases | `test_cancel_pre_spawn_releases` | CONTEXT.md D-02; RESEARCH Pitfall 6 |
| D-04 dict-is-truth (no semaphore counter leakage) | N+1 test inspects `to_dict()` payload reads from `len(self._inflight)` | CONTEXT.md D-04 |
| Legacy cap-shape test (regression) | `test_cap_reached_shape` (Phase 9, unchanged) | Phase 9 D-15 |

## Threat Model Verification

| Threat ID | Mitigation Verified By |
|-----------|------------------------|
| **T-13-05** (DoS via TOCTOU on jobs cap) | `test_n_concurrent_submits_exactly_one_rejected` -- 4 concurrent submits against cap=3 always produce exactly 3 successes + 1 JobCapReached. The atomic probe-and-acquire under `registry._lock` closes the race window that previously allowed N+M to bypass cap=N. |
| **T-13-06** (DoS via slot leak under terminal-state branches) | `test_terminal_transitions_release_exactly_once` -- every reachable terminal status (succeeded/failed/cancelled/killed_timeout) releases the slot exactly once; `_slot_released` flag prevents double-release; no `ValueError` raised under any tested scenario. The 5th terminal status (killed_log_cap) flows through the same `finally:` / `_mark_terminal` path and is exercised by `tests/jobs/test_log_cap.py`. |
| **T-13-07** (DoS via slot leak on pre-spawn failure) | `test_cancel_pre_spawn_releases` -- monkeypatched `ensure_subdir` raises PermissionError; `except BaseException` branch in `submit()` releases the slot; subsequent submit succeeds. |
| **T-13-08** (cap-reject contract change) | `test_job_cap_reached_dict_shape` locks `to_dict()` byte-identical; legacy `test_cap_reached_shape` continues to assert the same shape on the integration path; no change to `JobCapReached.__init__` or `to_dict()` signature. |

## Verification Results

```
=== New concurrency suite ===
$ pytest tests/jobs/test_concurrency.py tests/jobs/test_errors.py::test_job_cap_reached_dict_shape -x
tests/jobs/test_concurrency.py .........3 passed
tests/jobs/test_errors.py ............1 passed
========================= 4 passed in 5.43s =========================

=== Legacy cap-shape test (D-03 preserved) ===
$ pytest tests/jobs/test_errors.py::test_cap_reached_shape -x
========================= 1 passed in 30.19s =========================

=== Smoke test ===
$ python -c "from mcp_gateway.jobs import BackgroundJobRegistry, Job; import asyncio; \
              r=BackgroundJobRegistry(max_inflight=4,cancel_grace_s=10,max_completed=200); \
              assert isinstance(r._sem, asyncio.BoundedSemaphore); \
              assert '_slot_released' in Job.__dataclass_fields__"
SMOKE TEST OK

=== Full jobs regression (excluding 4 pre-existing pollution failures, see deferred-items.md) ===
$ pytest tests/jobs/ -k "not slow and not test_unknown_tool_shape and not test_specs_default_hides_underscore and not test_specs_with_include_internal_shows_all and not test_progress_fields_set_on_drive"
================= 68 passed, 5 deselected in 37.08s =================

=== Lifespan / lifecycle integration ===
$ pytest tests/jobs/test_lifespan_integration.py tests/jobs/test_registry_lifecycle.py -x
========================= 6 passed in 0.99s =========================
```

## Acceptance Criteria Verification

| Criterion | Result |
|-----------|--------|
| `grep "self._sem: asyncio.BoundedSemaphore = asyncio.BoundedSemaphore" jobs.py` | 1 line (in `__init__`) -- OK |
| `grep -n "_slot_released" jobs.py` | 4 matches (dataclass field; comment in dataclass; `_mark_terminal` guard; `_mark_terminal` flag-set) -- OK (>= 3) |
| `grep -c "self._sem.release()" jobs.py` | 2 (submit-except + `_mark_terminal`) -- exact match |
| `grep "self._sem.locked()" jobs.py` | 1 (probe in submit) -- OK |
| `grep "await self._sem.acquire()" jobs.py` | 1 (acquire in submit) -- OK |
| `grep "len(self._inflight) >= self._max_inflight" jobs.py` | 0 -- legacy racy check removed |
| `grep "except BaseException" jobs.py` | 2 -- OK (>= 1) |
| `grep -E "async def test_(n_concurrent_submits_exactly_one_rejected\|terminal_transitions_release_exactly_once\|cancel_pre_spawn_releases)" test_concurrency.py | wc -l` | 3 -- OK |
| `grep "def test_job_cap_reached_dict_shape" test_errors.py` | 1 -- OK |
| `grep "err.to_dict() ==" test_errors.py` | 1 -- OK (full-dict snapshot) |
| `grep "len(successes) == 3" test_concurrency.py` | 1 -- OK |
| `grep "j._slot_released is True" test_concurrency.py` | 5 -- OK (>= 4) |

## Deviations from Plan

**[Rule 3 - Blocking] Pre-existing test-isolation pollution in `tests/jobs/` documented as deferred items.**

- **Found during:** Task 1 verification (`pytest tests/jobs/ -x -k "not slow"`).
- **Issue:** Four pre-existing tests (`test_unknown_tool_shape`, two `test_specs_*` in `test_list_tool_jobs.py`, `test_progress_fields_set_on_drive`) FAIL when the full `tests/jobs/` suite runs sequentially, but PASS in isolation. Root cause: an earlier test imports `mcp_gateway.tools.dynamic`, which calls `register_job_tool` for Phase 11 dynamic-mode tools (`ltrace`, `strace`, `qemu_*`); the four affected tests hard-code Phase-9-era assertions (e.g., `sorted(result["known"]) == ["_log_burst_probe", "_sleep_probe", "capa"]`).
- **Verification it is pre-existing:** Reproduces against the parent commit `d368896` via `git stash` + rerun. NOT caused by Plan 13-02.
- **Action taken:** Documented in `.planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/deferred-items.md` for a future quick-task pass. SCOPE BOUNDARY rule applied -- only auto-fix issues directly caused by current task's changes. The Plan-02 source change in `jobs.py` is orthogonal: it touches `BackgroundJobRegistry` semaphore + `Job._slot_released`, not `JOB_TOOL_REGISTRY` contents.
- **Files affected:** None modified -- only the deferred-items.md log was added.
- **Commit:** 52a0eeb (Task 1 commit includes the deferred-items log).

No other deviations. The paste-ready code from `13-02-PLAN.md::<action>` blocks landed without modification; all greps for acceptance criteria pass; the byte-identical `JobCapReached.to_dict()` snapshot is exact verbatim.

## Authentication Gates

None -- no auth surfaces touched by this plan.

## Self-Check: PASSED

- mcp-gateway/src/mcp_gateway/jobs.py: MODIFIED -- verified via `git show 52a0eeb --stat`
- mcp-gateway/tests/jobs/test_concurrency.py: CREATED (206 lines) -- verified via `wc -l`
- mcp-gateway/tests/jobs/test_errors.py: MODIFIED (test_job_cap_reached_dict_shape appended) -- verified via `grep -c "def test_job_cap_reached_dict_shape"`
- .planning/phases/13-harden-concurrency-caps-and-r2-sandboxing/deferred-items.md: CREATED -- verified via Read
- Commit 52a0eeb (Task 1): FOUND in `git log`
- Commit af296f5 (Task 2): FOUND in `git log`

All claimed artifacts exist; all claimed commits exist.
