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
