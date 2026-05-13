---
phase: 06-retoolrunner-artifacts-io-foundation
plan: 01
subsystem: testing
tags: [pytest, tdd, red-state, test-scaffolding, mcp-gateway, retoolrunner, artifacts-io]

# Dependency graph
requires:
  - phase: 05-f-1-image-hash-fix
    provides: Hermetic test layout pattern (single fixture per test, tmp_path-only, explicit env dicts) reused verbatim from test_image_hash.py
provides:
  - Pytest `slow` marker registered in mcp-gateway/pyproject.toml -- no PytestUnknownMarkWarning when Wave 2 marks the 100 MB urandom test
  - tests/test_runner.py with 10 named test functions (RED state) -- locks the SC-1..SC-4 + D-08 + manifest-regression contract for Plan 03
  - tests/test_artifacts_io.py with 16 named test functions (RED state) -- locks the SC-5 matrix + D-09 + D-15 + D-16 contract for Plan 02
  - Threat-register-as-tests scaffolding for T-6-01 (path traversal), T-6-02 (shell injection), T-6-03 (symlink escape), T-6-06 (log collision), T-6-07 (env validation)
affects: [06-02 artifacts_io implementation, 06-03 runner implementation, all later Phase 6+ plans referencing ReToolRunner/case-dir confinement]

# Tech tracking
tech-stack:
  added: []  # No new pip deps; stdlib + existing pytest only
  patterns:
    - "Wave-0 RED-state test scaffolding -- tests imported targets that do not yet exist; Wave 1/2 turn them GREEN"
    - "Grep-the-source chokepoint test (mirrors test_sample_resolution.py:148 pattern) -- verifies T-6-02 invariant by inspecting runner.py source for shell=True"
    - "Hermetic test layout per D-21 -- every test uses tmp_path, no real STATUS_ROOT, no os.environ read in env-validation test (explicit subprocess env dict)"
    - "Threat-register-as-tests -- T-6-01/03/06/07 each have a named test function rather than being prose-only mitigations"

key-files:
  created:
    - mcp-gateway/tests/test_runner.py
    - mcp-gateway/tests/test_artifacts_io.py
  modified:
    - mcp-gateway/pyproject.toml

key-decisions:
  - "Wave-0 plan creates RED tests only -- Plan 02 (artifacts_io) and Plan 03 (runner) turn them GREEN; enforces Nyquist (every <verify> in Plans 02/03 references an existing test)"
  - "test_timeout_kills_process_group asserts on wait_for(0.5) + 0.2s cleanup budget (0.7s upper bound) -- runner internally swallows asyncio.TimeoutError so the test layer cannot record a post-timeout-only timer; documented inline in the test"
  - "test_100mb_urandom_bounded_rss skips on non-Linux -- ru_maxrss semantics are KB on Linux but bytes elsewhere"
  - "slow marker registered (rather than addopts -p no:cacheprovider hack) -- minimal one-line fix in [tool.pytest.ini_options] surfaces in pytest --markers"

patterns-established:
  - "RED-state test scaffolding: name the test function, import the not-yet-existing module, mark intent in docstring -- collection failure is the expected signal"
  - "Slug-regex tests pair a reject case with a lowercase-happy-path case -- catches both validation and auto-normalization"
  - "Threat-register-as-tests: every <threat_model> row with disposition=mitigate has at least one named test function in this plan's outputs"

requirements-completed: [FOUND-02, FOUND-03, FOUND-04]

# Metrics
duration: 3min
completed: 2026-05-13
---

# Phase 6 Plan 1: Wave-0 Test Scaffolding for ReToolRunner + artifacts_io Summary

**Locked the SC-1..SC-5 + D-08/D-09/D-15/D-16 contract via 26 RED-state pytest functions and a registered `slow` marker -- Plans 02/03 now have concrete failing tests to turn green rather than free-form acceptance prose.**

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-13T01:16:44Z
- **Completed:** 2026-05-13T01:19:24Z
- **Tasks:** 3 / 3
- **Files modified:** 3 (1 modified, 2 created)

## Accomplishments

- Registered `slow` pytest marker in `mcp-gateway/pyproject.toml` -- pre-empts `PytestUnknownMarkWarning` on Wave 2's `test_100mb_urandom_bounded_rss` (D-21).
- Created `mcp-gateway/tests/test_runner.py` with 10 RED tests covering FOUND-02 + FOUND-03: SC-1a/b/c/d (shell=True grep, cwd confine, timeout SIGKILL, cancel propagation), SC-2 (12-key return shape), SC-3 (auto-capture + log_path relative + head alignment), SC-4 (100 MB urandom bounded RSS), D-08 (env-var validation), default-timeout-sane, manifest regression (no psutil/aiofiles).
- Created `mcp-gateway/tests/test_artifacts_io.py` with 16 RED tests covering FOUND-04: SC-5a..g confine_to matrix + 2 case_dir validation cases, D-09 tool_log_path (format + no-collision + slug regex), D-15 ensure_subdir (idempotent + slug regex), D-16 EXPANDED_CASE_SUBDIRS (9-name catalog + lazy-create discipline).

## Task Commits

Each task committed atomically:

1. **Task 1: Register `slow` pytest marker in pyproject.toml** -- `c09018a` (chore)
2. **Task 2: Create `tests/test_runner.py` RED stubs** -- `7fa0f7c` (test)
3. **Task 3: Create `tests/test_artifacts_io.py` RED stubs** -- `8116d3f` (test)

_Note: Tasks 2 and 3 are TDD RED-only -- the corresponding GREEN commit lives in Plans 02/03._

## Files Created/Modified

- `mcp-gateway/pyproject.toml` -- added `markers = ["slow: ..."]` array under `[tool.pytest.ini_options]`; existing `asyncio_mode`, `testpaths`, `addopts` keys preserved verbatim.
- `mcp-gateway/tests/test_runner.py` (new, 168 lines) -- 10 named test functions importing `mcp_gateway.runner` (does not yet exist).
- `mcp-gateway/tests/test_artifacts_io.py` (new, 167 lines) -- 16 named test functions importing `mcp_gateway.artifacts_io` (does not yet exist).

## Verification Results

End-to-end verification per plan's `<verification>` block:

1. **Marker registered:** `python -c "import tomllib; ..."` confirms `slow` present under `[tool.pytest.ini_options].markers`.
2. **Test files parse:** `ast.parse()` succeeds on both files.
3. **Test counts:** `test_runner.py` -> 10 functions; `test_artifacts_io.py` -> 16 functions.
4. **RED state confirmed:** `importlib.import_module('mcp_gateway.runner')` and `importlib.import_module('mcp_gateway.artifacts_io')` both raise `ModuleNotFoundError`. Plans 02/03 will turn these GREEN.
5. **No regression to existing tests:** Phase 5's `test_image_hash.py` and the 18 v1.0 tests are untouched; only `pyproject.toml`'s `[tool.pytest.ini_options]` block changed (adds, no edits to existing keys).

## Deviations from Plan

None -- plan executed exactly as written. All 10 + 16 test function names match the spec, all literal strings (`@pytest.mark.slow`, `from mcp_gateway.runner import`, `from mcp_gateway.artifacts_io import`, `from mcp_gateway import runner as runner_module`) are present.

## Auth Gates

None -- plan is local file scaffolding only.

## Threat Surface Scan

No new attack surface introduced by this plan -- test files are not a security boundary. The plan's `<threat_model>` block enumerates T-6-01..T-6-07 as expectations encoded by the tests for Plans 02/03 to satisfy; each `mitigate` disposition has at least one named test function:

| Threat | Test |
|--------|------|
| T-6-01 (path traversal) | `test_confine_to_rejects_traversal`, `test_confine_to_rejects_absolute_outside`, `test_confine_to_rejects_nonexistent_case_dir`, `test_confine_to_rejects_non_directory_case_dir` |
| T-6-02 (shell injection) | `test_runner_never_uses_shell_true` (grep-the-source) |
| T-6-03 (symlink escape) | `test_confine_to_rejects_escaping_symlink`, `test_confine_to_allows_inside_symlink` |
| T-6-06 (log collision) | `test_tool_log_path_no_collision`, `test_tool_log_path_format` |
| T-6-07 (env-var validation) | `test_env_validation_rejects_bad_values`, `test_default_timeout_below_mcp_cap` |

## Known Stubs

None -- this plan is intentionally RED-state test scaffolding. The "stubs" are the not-yet-existing target modules `mcp_gateway.runner` and `mcp_gateway.artifacts_io`, which are explicitly the deliverables of Plans 03 and 02 respectively (documented in the `<objective>` and the `<must_haves>` block).

## Self-Check: PASSED

- FOUND: mcp-gateway/pyproject.toml (markers array present)
- FOUND: mcp-gateway/tests/test_runner.py (10 test functions, 168 lines)
- FOUND: mcp-gateway/tests/test_artifacts_io.py (16 test functions, 167 lines)
- FOUND: commit c09018a (Task 1 -- pyproject.toml marker)
- FOUND: commit 7fa0f7c (Task 2 -- test_runner.py RED stubs)
- FOUND: commit 8116d3f (Task 3 -- test_artifacts_io.py RED stubs)
