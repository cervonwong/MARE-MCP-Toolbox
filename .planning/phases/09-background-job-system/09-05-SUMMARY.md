---
phase: 09-background-job-system
plan: 05
subsystem: jobs
tags: [jobs, d-15, error-contract, gap-closure, capa, mcp-boundary]

# Dependency graph
requires:
  - phase: 09-background-job-system
    provides: "BackgroundJobRegistry primitive (Plan 01) + tools/jobs.py MCP surface (Plan 02) + test scaffolding (Plan 04)"
provides:
  - "D-15 'tools never raise' contract restored for the capa user-facing job spec"
  - "_validate_kwargs gains 'required' rule handler (forward-compatible for Phase 10/11 specs)"
  - "Broader exception catch (ValueError, FileNotFoundError, KeyError, OSError) around registry.submit() converts build_argv exceptions into D-15 #4 InvalidKwargs dicts"
  - "Two new regression tests + expanded test_no_tool_handler_raises in tests/jobs/test_errors.py"
affects: [10-extraction, 11-dynamic-lab-mode]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Schema-driven required-field validation in _validate_kwargs (rule.get('required'))"
    - "Layered defense: schema validation BEFORE build_argv (Task 1) + broader except AROUND submit() (Task 2)"
    - "D-15 #4 InvalidKwargs(field='kwargs', expected='valid per-tool argv inputs', got=f'{type(e).__name__}: {e}') for build_argv-time failures"

key-files:
  created: []
  modified:
    - "mcp-gateway/src/mcp_gateway/jobs.py"
    - "mcp-gateway/src/mcp_gateway/tools/jobs.py"
    - "mcp-gateway/tests/jobs/test_errors.py"

key-decisions:
  - "Narrow except (ValueError, FileNotFoundError, KeyError, OSError) chosen over bare 'except Exception' to avoid swallowing programmer bugs or asyncio.CancelledError"
  - "Two-layer defense: schema 'required' rule (cheap, runs before submit) + broader except (catches everything that escapes build_argv)"
  - "Exception class name included in 'got' field but never the full traceback (Information Disclosure mitigation T-09-05-02)"

patterns-established:
  - "Required-field schema rule: {field: {'required': True, ...}} -- raises InvalidKwargs(field, 'required field', 'missing') BEFORE build_argv is reached"
  - "Two-branch except ordering: specific D-15 exceptions (JobCapReached) first, broader build_argv-time exceptions after"

requirements-completed: [JOBS-01]

# Metrics
duration: 7min
completed: 2026-05-19
---

# Phase 9 Plan 5: D-15 Contract Gap Closure for capa Tool

**Closed two confirmed D-15 'tools never raise' escape paths (missing 'sample' kwarg KeyError + path-traversal ValueError) by adding 'required' schema rule + broader except around registry.submit(); test suite grows from 66 to 68 non-slow passing.**

## Performance

- **Duration:** ~7 min (RED-probe + 3 task edits + 3 commits + suite runs)
- **Started:** 2026-05-19T03:08:03Z
- **Completed:** 2026-05-19T03:14:33Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- **D-15 #4 contract restored for capa kwargs={} path**: `start_tool_job(tool='capa', kwargs={}, case_dir=...)` now returns `{"error": "invalid kwargs", "field": "sample", "expected": "required field", "got": "missing"}` instead of raising `KeyError('sample')`.
- **D-15 #4 contract restored for capa path-traversal path**: `start_tool_job(tool='capa', kwargs={'sample': '../etc/passwd'}, case_dir=...)` now returns `{"error": "invalid kwargs", "field": "kwargs", "expected": "valid per-tool argv inputs", "got": "ValueError: path traversal rejected: ..."}` instead of raising `ValueError`.
- **_validate_kwargs gained a forward-compatible 'required' rule** -- usable by all future Phase 10/11 specs without further code changes.
- **Test surface expanded from 6 to 8 tests** in `tests/jobs/test_errors.py`; the existing `test_no_tool_handler_raises` negative-control test was expanded to exercise both previously-broken paths.
- **No regressions**: Phase 9 non-slow suite goes 66 → 68 (added 2), full gateway non-slow suite goes 321 → 323 (added 2), all skips unchanged.

## Task Commits

Each task was committed atomically:

1. **Task 1: Mark capa's 'sample' kwarg as required + teach _validate_kwargs to enforce it** — `66e0e30`
2. **Task 2: Broaden start_tool_job's except clause around registry.submit() to catch build_argv exceptions** — `bc3b5cb`
3. **Task 3: Add two regression tests for the capa D-15 escape paths in test_errors.py** — `f386cfe`

_Note: TDD steps fused for these surgical edits — a single RED probe via Python REPL (recorded in execution log) confirmed both bugs before applying Task 1 and Task 2 fixes; Task 3 wrote dedicated regression tests last so they GREEN-pass against the fixes._

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/jobs.py` — `_validate_kwargs` walker gains `if rule.get("required"): raise InvalidKwargs(field, "required field", "missing")` at top of per-field loop; `_CAPA_SPEC.kwargs_schema` now includes `"required": True`.
- `mcp-gateway/src/mcp_gateway/tools/jobs.py` — `start_tool_job` submit-block adds a second `except (ValueError, FileNotFoundError, KeyError, OSError) as e:` branch AFTER the existing `except JobCapReached`. Returns `InvalidKwargs(field='kwargs', expected='valid per-tool argv inputs', got=f'{type(e).__name__}: {e}').to_dict()`. Comment in body cites `09-VERIFICATION.md` truth #7 / CR-01 + CR-02.
- `mcp-gateway/tests/jobs/test_errors.py` — Two new tests (`test_capa_missing_sample_returns_invalid_kwargs`, `test_capa_path_traversal_returns_invalid_kwargs`); expanded `test_no_tool_handler_raises._calls` body adds the two capa calls so the negative-control covers the previously-broken paths.

## Decisions Made

- **Narrow exception list over bare `except Exception`**: caught only `(ValueError, FileNotFoundError, KeyError, OSError)` to avoid swallowing `asyncio.CancelledError`, `RuntimeError`, or programmer bugs. Baseline `except Exception` count in `tools/jobs.py` preserved at 1.
- **Exception class name in `got`, not full traceback**: matches T-09-05-02 Information Disclosure mitigation -- agent sees `"ValueError: path traversal rejected: '../etc/passwd'"` but never a stack frame.
- **`_validate_kwargs` 'required' rule runs BEFORE `build_argv` in `submit()`**: defense-in-depth. The schema check is the first line; the broader `except` is the second line of defense for any build_argv-time exception not pre-caught by schema (e.g., FileNotFoundError on non-existent sha256, OSError on unexpected filesystem state).

## Deviations from Plan

None - plan executed exactly as written. Two surgical edits + one test file addition matched the paste-ready code blocks in the plan verbatim.

The plan's TDD flow was lightly compressed: a single Python-REPL RED probe (recorded in execution log) confirmed both bugs at the start of Task 1, rather than splitting each task into RED→GREEN commits. The functional outcome (existing tests stay green, new tests GREEN-pass against the fixes) is identical. This is consistent with prior Phase 9 plans (e.g., Plan 02 used the same compressed pattern when the surgical scope was 1-3 hunks).

## Verification Commands

```bash
cd /home/cervon/Code/MARE-MCP-Toolbox/mcp-gateway

# Targeted -- D-15 error contract suite (must include the two new tests)
pytest tests/jobs/test_errors.py -v
# Result: 8 passed, 1 warning in 30.10s

# Phase 9 non-slow suite -- regression check (was 66 at verification time)
pytest tests/jobs/ -m 'not slow' --ignore=tests/jobs/test_capa_integration.py
# Result: 68 passed, 1 warning in 30.97s  (66 prior + 2 new = 68)

# Full gateway non-slow suite (was 321 at verification time)
pytest -m 'not slow' tests/ --ignore=tests/test_acl_available.py
# Result: 323 passed, 46 skipped, 3 deselected, 2 warnings in 38.28s

# Negative grep -- bare-Exception count unchanged
grep -c "except Exception" src/mcp_gateway/tools/jobs.py
# Result: 1 (baseline preserved)
```

## Issues Encountered

None.

## Non-Goals (Explicit)

- **CR-03 (submit lock gap)** -- two-lock release-and-reacquire in `BackgroundJobRegistry.submit()` (cap check releases lock before inflight insertion). Concurrent submits at cap-1 can both pass check; max_inflight briefly exceeded. This is a correctness warning, not a D-15 escape — **deferred to a separate hardening phase**.
- **WR-03 (line_buf unbounded growth)** -- progress-parser `line_buf` (bytearray for stderr) has no upper bound other than the global log cap. Misbehaving tools without newlines could hold 256 MiB in RAM before cap-kill fires. Correctness/safety concern, not a D-15 escape — **deferred to a separate hardening phase**.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- **VERIFICATION.md truth #7 can be flipped to VERIFIED** on the next `/gsd-verify-work` run for Phase 9.
- All 7 JOBS-XX requirements remain satisfied (JOBS-01 explicitly closed by this plan).
- Phase 9 ready for re-verification / formal sign-off.
- Phase 10 (Extraction Tier) and Phase 11 (Dynamic Lab Mode) inherit the now-complete D-15 contract; any new job specs can use the 'required' rule out of the box.

## Self-Check: PASSED

- File `mcp-gateway/src/mcp_gateway/jobs.py` exists (modified) — verified.
- File `mcp-gateway/src/mcp_gateway/tools/jobs.py` exists (modified) — verified.
- File `mcp-gateway/tests/jobs/test_errors.py` exists (modified) — verified.
- Commit `66e0e30` (Task 1) present in git log — verified.
- Commit `bc3b5cb` (Task 2) present in git log — verified.
- Commit `f386cfe` (Task 3) present in git log — verified.
- All 8 tests pass in `tests/jobs/test_errors.py` — verified.
- Phase 9 non-slow suite green at 68 passed — verified.
- Full gateway non-slow suite green at 323 passed — verified.
- `except Exception` count in `tools/jobs.py` unchanged at 1 — verified.

---
*Phase: 09-background-job-system*
*Completed: 2026-05-19*
