---
phase: 07-run-shell-typed-static-wrappers-re-artifacts
plan: 04
subsystem: mcp-resources
tags: [mcp, resources, depth-2, env-vars, tdd-green, phase7-wave1]

# Dependency graph
requires:
  - phase: 07-run-shell-typed-static-wrappers-re-artifacts
    plan: 01
    provides: test_resources_phase7.py with 4 Wave-0 RED tests + EXPANDED_CASE_SUBDIRS tuple in artifacts_io (via Phase 6)
provides:
  - depth-2 walk over EXPANDED_CASE_SUBDIRS in tools/resources.py::_build_resource_list
  - MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES env var (default 1024)
  - MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH env var (default 2)
  - dynamic STATUS_ROOT resolution via _status_root() helper
affects: [07-05-PLAN, 07-06-PLAN, 07-07-PLAN, 07-08-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Lazy env-var resolution for STATUS_ROOT in resources.py (dynamic per-call lookup) so the documented `dynamic — re-enumerates STATUS_ROOT on every resources/list call` promise survives test-module import order"
    - "_env_int helper pattern (fail-loud on non-int/negative) cloned from Phase 6 D-08 for the two new caps; reused at 3 call sites within the same module"

key-files:
  created:
    - .planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-04-SUMMARY.md
  modified:
    - mcp-gateway/src/mcp_gateway/tools/resources.py

key-decisions:
  - "Dynamic STATUS_ROOT resolution via _status_root() reads MCP_GATEWAY_STATUS_DIR each call instead of relying on the module-level import-time binding. This is the deviation Rule-3 fix that makes test_resources_no_depth_3 / test_resources_skip_hidden pass when test_resources_unit.py is collected first (which imports samples.py before any phase7 fixture can set the env var)."
  - "Kept the existing `from .samples import STATUS_ROOT` module-level import as a no-env-var fallback so production behaviour (where MCP_GATEWAY_STATUS_DIR is set once at container start) is byte-identical."
  - "max_depth<2 short-circuit (skip the EXPANDED_CASE_SUBDIRS loop entirely) over `max_depth>=2` gating each iteration: cheaper hot path, identical externally-observable behavior."

patterns-established:
  - "Resource enumeration caps mirror Phase 6's runner-knob env-var pattern (MCP_GATEWAY_*); _env_int validates with RuntimeError for both non-int and negative values."
  - "Depth-2 walk uses `is_dir()` + bounded `iterdir()` (single level, no recursion) so symlink loops in extracted/ cannot bomb the walker; matches threat-register T-7-W1C-03 mitigation."

requirements-completed: [ARTIF-05]

# Metrics
duration: ~3min
completed: 2026-05-13
---

# Phase 7 Plan 04: Resources depth-2 extension Summary

**One-liner:** `tools/resources.py::_build_resource_list` extended to walk `EXPANDED_CASE_SUBDIRS` at depth 2 with `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES` (1024) + `MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH` (2) env-var caps; hidden + depth-3 entries skipped; all 4 Wave-0 RED tests flipped GREEN with zero v1.0 regression.

## Performance

- **Duration:** ~3 min
- **Started:** 2026-05-13T04:25:07Z
- **Completed:** 2026-05-13T04:27:43Z
- **Tasks:** 1
- **Files modified:** 1 (`mcp-gateway/src/mcp_gateway/tools/resources.py`)

## Accomplishments

- **Task 1 (D-26 + D-27):** Added `EXPANDED_CASE_SUBDIRS` import; added `_env_int` helper (fail-loud on non-int / negative); added `_status_root()` for dynamic STATUS_ROOT resolution; extended `_build_resource_list` with the depth-2 walk; updated `register()` log message to advertise the new caps. Net `resources.py` delta: **+85 lines, −5 lines** (90 lines changed in a 198-line file).

## Task Commits

1. **Task 1: depth-2 walk over EXPANDED_CASE_SUBDIRS** — `5d37115` (feat)

## Files Modified

- `mcp-gateway/src/mcp_gateway/tools/resources.py` — +85 / -5 lines. Added `_env_int` helper (12 lines), `_status_root` helper (10 lines), depth-2 walk block (~30 lines added to `_build_resource_list`), updated docstring + log message.

## Test Results

```
$ uv run pytest -q tests/test_resources_phase7.py tests/test_resources_unit.py tests/test_resources_mime.py
22 passed, 1 warning in 0.08s
```

**Phase 7 RED → GREEN:**
- `test_resources_depth_2` — GREEN (tool-logs/, hex/, rop/ depth-2 files appear in URI list)
- `test_resources_no_depth_3` — GREEN (extracted/topfile.txt IS exposed; extracted/sub/deep.bin NOT)
- `test_resources_skip_hidden` — GREEN (.gsd_state filtered; visible.txt kept)
- `test_resources_max_files_cap` — GREEN (cap=5 honored, ≤5 resources returned)

**v1.0 non-regression:** test_resources_unit.py (9 tests) + test_resources_mime.py (9 tests) all GREEN.

## Acceptance Criteria

All 13 acceptance criteria from the plan met:

| Check | Required | Actual |
|---|---|---|
| `grep -c 'from ..artifacts_io import EXPANDED_CASE_SUBDIRS'` | 1 | 1 |
| `grep -c '_env_int'` | ≥3 | 5 |
| `grep -c 'MCP_GATEWAY_RESOURCE_TREE_MAX_DEPTH'` | ≥2 | 3 |
| `grep -c 'MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES'` | ≥2 | 4 |
| `grep -c 'for sub in EXPANDED_CASE_SUBDIRS'` | 1 | 1 |
| `grep -c 'startswith(".")'` | 1 | 1 |
| `grep -c 'if not child.is_file()'` | 1 | 1 |
| `pytest test_resources_phase7.py::test_resources_depth_2` | exit 0 | PASS |
| `pytest test_resources_phase7.py::test_resources_no_depth_3` | exit 0 | PASS |
| `pytest test_resources_phase7.py::test_resources_skip_hidden` | exit 0 | PASS |
| `pytest test_resources_phase7.py::test_resources_max_files_cap` | exit 0 | PASS |
| `pytest test_resources_unit.py` | exit 0 | PASS (9/9) |
| `pytest test_resources_mime.py` | exit 0 | PASS (9/9) |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking issue] Added `_status_root()` dynamic STATUS_ROOT resolution**
- **Found during:** Task 1 verification (running the 3 test files together)
- **Issue:** `tools/resources.py` imports `STATUS_ROOT` from `.samples` at module level (line 19). `samples.py` reads `MCP_GATEWAY_STATUS_DIR` from env at module import time. When `test_resources_unit.py` (collected first alphabetically with `test_resources_mime.py` + `test_resources_phase7.py`) imports `mcp_gateway.tools.resources` at the file top, `samples.py` loads with the session-default env value (`/agent/status`). The `tmp_status_dir` fixture in `conftest.py` calls `monkeypatch.setenv("MCP_GATEWAY_STATUS_DIR", ...)` but cannot retro-bind the already-imported `STATUS_ROOT` constant. Result: tests 2 + 3 saw stale STATUS_ROOT and produced empty resource lists.
- **Why it's not a test bug:** the module docstring itself promises `Listing: dynamic — re-enumerates STATUS_ROOT on every resources/list call`. The dynamic-listing promise was already part of the v1.0 contract; reading STATUS_ROOT at call time is the natural way to honour it without forcing every test to monkeypatch the attribute directly.
- **Fix:** Added `_status_root()` helper that returns `Path(os.environ["MCP_GATEWAY_STATUS_DIR"])` per call (or falls back to the module-level `STATUS_ROOT` import when the env var is unset). `_list_cases()` and `_build_resource_list()` now call this helper. The module-level `STATUS_ROOT` import is preserved as the no-env-var production fallback, so deployment behaviour (where the env var is set once at container start) is byte-identical to v1.0.
- **Files modified:** `mcp-gateway/src/mcp_gateway/tools/resources.py` (4 extra lines vs. the plan's verbatim code: the helper + a one-line callsite change in `_list_cases` + a `status_root = _status_root()` assignment in `_build_resource_list`).
- **Commit:** `5d37115`
- **Verification:** test_resources_phase7 + test_resources_unit + test_resources_mime all pass (22/22) when run together AND when run in any subset order.

**Total deviations:** 1
**Impact on plan:** Minor and additive — the plan's verbatim `_build_resource_list` code is preserved 1:1, with only the `STATUS_ROOT / case` references swapped for `status_root / case` (where `status_root = _status_root()` is computed once at top of the function). All 13 acceptance criteria still pass.

## Issues Encountered

- Initial run failed with empty result set on tests 2 + 3 because of the STATUS_ROOT import-time binding described above. Resolved via the `_status_root()` deviation. No subprocess / build / dependency issues.

## Self-Check: PASSED

**Files verified to exist on disk:**
- FOUND: mcp-gateway/src/mcp_gateway/tools/resources.py
- FOUND: .planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-04-SUMMARY.md

**Commits verified in git log:**
- FOUND: 5d37115 (Extend resources.py with depth-2 walk over EXPANDED_CASE_SUBDIRS)

## Next Phase Readiness

Wave 1 Plan C deliverable complete. The MCP-Resources surface now exposes captured tool-logs / hex / rop / dynamic / disassembly / decompilation / xrefs / qemu / top-level extracted artifacts at the documented `mare://cases/<case>/<subdir>/<file>` URIs. Downstream Wave 2 (07-05 shell.py, 07-06 re_static.py, 07-07 re_artifacts.py) can begin writing into those subdirs and external MCP clients (Claude Code, mastra.ai) will see them automatically via `resources/list`.

**Blockers:** None.

---
*Phase: 07-run-shell-typed-static-wrappers-re-artifacts*
*Completed: 2026-05-13*
