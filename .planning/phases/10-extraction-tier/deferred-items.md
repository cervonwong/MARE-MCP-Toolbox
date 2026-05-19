# Phase 10 Deferred Items

Items discovered during Plan 05 execution that are OUT OF SCOPE for Plan 05
(pre-exist Plan 05 or live in a different code area).

## Pre-existing failures detected before Plan 05

These four test failures predate Plan 05 (visible immediately at Task-2 start,
caused by Plan 02's JOB_TOOL_REGISTRY mutation):

1. **tests/jobs/test_errors.py::test_unknown_tool_shape** — fails because the
   error message's `known` list now includes `binwalk_extract` + `unblob`
   (registered at extraction-module import time). Phase 9 test does not
   anticipate Phase 10 entries.

2. **tests/jobs/test_list_tool_jobs.py::test_specs_default_hides_underscore** —
   same root cause: asserts `names == ["capa"]` but JOB_TOOL_REGISTRY now
   also contains `binwalk_extract` + `unblob`.

3. **tests/jobs/test_list_tool_jobs.py::test_specs_with_include_internal_shows_all** —
   same root cause.

4. **tests/test_acl_available.py::test_setfacl_on_path** — pre-existing
   host-environment failure: `setfacl` is only available in the container,
   not on the executor host. Existing test marks similar checks with skip
   conditions; this one should be similarly conditional or rely on the
   container CI image.

**Resolution path:** Phase 9 test maintainers should update the assertions to
either filter to capa-only or accept the Phase 10 entries; the acl test should
adopt the same skip pattern used by `test_run_shell.py` (skip when `setfacl`
absent from host). These are housekeeping tasks for Phase 9 / Phase 7 owners.

## Plan-acceptance-criterion drift

The Plan 05 Task 2 acceptance criterion `_require_*_or_skip` count `>= 5` is
inconsistent with Plan 01's design (one slow test per engine = exactly 3 slow
tests, each gated). Plan 05's grep target should read `>= 3`. The semantic
invariant (every slow test has a gate) is satisfied: 3 slow tests, 3 gates.
