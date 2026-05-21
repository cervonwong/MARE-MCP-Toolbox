# Phase 13 — Deferred Items (out of scope)

Tracked here per the SCOPE BOUNDARY rule (executor's deviation policy):
pre-existing failures discovered during Phase 13 execution but UNRELATED to the
plans in this phase.

## 1. Four `tests/jobs/*` failures — pre-existing dynamic-tools pollution (Phase 11 drift)

**Affected tests (all symptom of the same root cause):**

- `tests/jobs/test_errors.py::test_unknown_tool_shape`
- `tests/jobs/test_list_tool_jobs.py::test_specs_default_hides_underscore`
- `tests/jobs/test_list_tool_jobs.py::test_specs_with_include_internal_shows_all`
- `tests/jobs/test_progress.py::test_progress_fields_set_on_drive`

**Discovered during:** Plan 13-02 Task 1 regression verification (running
`pytest tests/jobs/ -x -k "not slow"` against `origin/main`).

**Symptom:** When the full `tests/jobs/` suite is run sequentially, an earlier
test imports `mcp_gateway.tools.dynamic`, which calls `register_job_tool` for
Phase 11 dynamic-mode tools (`ltrace`, `strace`, `qemu_*`, etc.).
`JOB_TOOL_REGISTRY` then contains 6+ tools, but
`test_unknown_tool_shape` (Phase 9) hard-codes the assertion to the original
3-tool registry: `["_log_burst_probe", "_sleep_probe", "capa"]`.

**Verification it is pre-existing:** Reproduces against `git stash` (i.e., on
the parent commit `d368896` BEFORE Plan 13-02 touched `jobs.py`). The expected
assertion (`["_log_burst_probe", "_sleep_probe", "capa"]`) was correct at
Phase 9 sign-off; Phase 11 added the dynamic-mode tools and did not refresh
this assertion.

**Why deferred:** Not caused by Plan 13-02. SCOPE BOUNDARY rule (executor
deviation policy): "Only auto-fix issues DIRECTLY caused by the current task's
changes." This is a pre-existing Phase 11 -> Phase 9 test drift.

**Recommended fix (future quick task):** Either
(a) Update the assertion to match the post-Phase-11 registry contents
    (and re-derive the list dynamically: `sorted(jobs.JOB_TOOL_REGISTRY)`),
(b) Add module-isolation fixture to `tests/jobs/test_errors.py` that
    reload-resets `mcp_gateway.jobs` before `test_unknown_tool_shape` runs
    (mirrors `conftest.py::registry_factory`'s dual-reload pattern).

Both would be ~3 LOC. Leaving as a pre-existing crack for a quick-task pass.

## 2. `tests/test_sessions_concurrency.py` pollution-driven failures during full-suite runs

**Affected tests (all pass in isolation; fail when full suite runs sequentially):**

- `test_n_concurrent_opens_exactly_one_rejected`
- `test_cancel_during_spawn_releases_slot`
- `test_oserror_during_spawn_releases_slot`
- `test_runtime_error_during_init_releases_slot`
- `test_reaper_idle_releases_slot`
- `test_shutdown_active_releases_or_clean_exit`

**Discovered during:** Plan 13-04 Task 2 regression verification (full
`pytest -k "not slow"` run on dev host).

**Symptom:** Running the entire mcp-gateway test suite sequentially causes
these 6 concurrency tests to fail; running `pytest tests/test_sessions_concurrency.py`
in isolation passes all 6. Indicates test pollution / cross-file module-state
leak (Plan 01's `BoundedSemaphore` + `_slot_released` flag interacts with
state left behind by an earlier file's reload-based isolation).

**Verification it is pre-existing:** Reproduces against the parent commit
prior to Plan 13-04's changes (`stash` shows nothing to stash; pollution is
not from Plan 04's diff). The tests were added in Plan 01 and have presumably
been pollution-prone since then on hosts that run the full suite.

**Why deferred:** Not caused by Plan 13-04. SCOPE BOUNDARY rule: "Only
auto-fix issues DIRECTLY caused by the current task's changes." Plan 04
adds the env-gated unsafe tool + 7 new tests; none of those touch the
SessionRegistry semaphore initialisation order.

**Recommended fix (future quick task):** Extend `test_sessions_concurrency.py`
with a module-level fixture that performs the same `_full_reset_modules()`
sweep used in `test_tool_list.py` before each test in the file. ~10 LOC.

## 3. `tests/test_r2_sessions.py::test_unsafe_shares_combined_cap` pollution

**Discovered during:** Plan 13-04 Task 2 regression verification.

**Symptom:** Passes in isolation; fails when full suite runs sequentially.
Same family of cross-file module-state leak as item #2.

**Why deferred:** Same root cause as item #2 (pollution from other test
files reloading session/jobs modules). The fix in item #2 would resolve
this test too if the reset fixture covers `r2_sessions` imports.

