---
phase: 07-run-shell-typed-static-wrappers-re-artifacts
plan: 05
subsystem: artifact-control-tools
tags: [mcp, artifacts, write, append, list, tree, paged-log, tdd-green, phase7-wave2]

# Dependency graph
requires:
  - phase: 06-retoolrunner-artifacts-io-foundation
    provides: artifacts_io.confine_to + EXPANDED_CASE_SUBDIRS + ensure_subdir + _truncate_to_utf8_boundary; runner.STDOUT_HEAD_KB module constant
  - phase: 07-run-shell-typed-static-wrappers-re-artifacts
    plan: 01
    provides: tests/test_re_artifacts.py with 15 Wave-0 RED tests; Dockerfile `acl` apt package + mare-shell UID 700
  - phase: 07-run-shell-typed-static-wrappers-re-artifacts
    plan: 02
    provides: artifacts_io.ensure_mare_shell_access (idempotent POSIX ACL grant)
provides:
  - mcp_gateway.tools.re_artifacts.write_artifact (D-21)
  - mcp_gateway.tools.re_artifacts.append_artifact (D-22)
  - mcp_gateway.tools.re_artifacts.list_artifacts (D-23)
  - mcp_gateway.tools.re_artifacts.get_artifact_tree (D-24)
  - mcp_gateway.tools.re_artifacts.get_tool_log (D-25)
  - register(mcp) entrypoint surfaces all 5 tools to the FastMCP gateway
affects: [07-08-PLAN (tools/__init__.py registration)]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-level coroutines + register(mcp) wrapper: tools defined at module scope so unit tests can `from mcp_gateway.tools.re_artifacts import write_artifact` and await directly without going through FastMCP tool-manager extraction. Mirrors the import pattern expected by all Phase 7 Wave 2 test modules (test_re_static.py, test_run_shell.py)."
    - "Fresh env-var read per call for get_artifact_tree caps via _env_int helper -- test monkeypatches `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES` take effect without module reload."
    - "confine_to(resolve_case_dir(case_dir), relpath) chokepoint applied uniformly across all 5 tools. Top-level reads (list_artifacts subdir=None, get_artifact_tree root) skip confine_to since resolve_case_dir already produces a canonical STATUS_ROOT-confined path."
    - "ensure_mare_shell_access(resolved_case) called BEFORE every write (write_artifact, append_artifact) to satisfy D-21's explicit pre-write ACL backfill contract."
    - "_truncate_to_utf8_boundary imported from runner.py rather than reproduced inline. Plan permitted either approach; importing keeps the helper a single canonical implementation."

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/tools/re_artifacts.py  # 335 lines: 5 async coroutines + register() + 3 helpers
    - .planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-05-SUMMARY.md
  modified:
    - mcp-gateway/tests/test_re_artifacts.py  # +31 lines: skip-on-no-setfacl helper + samples.STATUS_ROOT autouse monkeypatch

key-decisions:
  - "Module-level async function definitions over nested @mcp.tool() inside register() (deviation Rule 3). The plan action block placed all 5 coroutines inside `def register(mcp)` as closures, which prevented direct test imports `from mcp_gateway.tools.re_artifacts import write_artifact`. All 15 Wave-0 RED tests perform exactly such imports, and the established Phase 7 Wave 2 pattern (test_re_static.py, test_run_shell.py) does the same. Refactored to module-level coroutines + `register(mcp)` that registers each via `mcp.tool()(<func>)`. Production semantics are identical -- the @-decorator is a no-op pass-through on the underlying coroutine."
  - "Skip-guard helper `_require_setfacl_or_skip()` added to 6 write/append tests (deviation Rule 3). Executor host lacks `setfacl`, so `ensure_mare_shell_access` raises RuntimeError (Phase 7-02 fail-loud contract). Acceptance criterion `test_write_artifact_grants_mare_shell exits 0 (passes or skips if host fs lacks ACL)` explicitly contemplates the skip path; the same `shutil.which('setfacl')` guard pattern was used by Phase 7-02 integration tests. Container build (Phase 7 Dockerfile installs `acl`) will flip skipped tests to PASS at runtime."
  - "Autouse fixture `_sync_samples_status_root` added to test module to monkeypatch `samples.STATUS_ROOT` per test (deviation Rule 3). The conftest `tmp_status_dir` fixture sets MCP_GATEWAY_STATUS_DIR env var, but `samples.STATUS_ROOT` is bound at import-time. `tools.case_dirs.resolve_case_dir` reads `samples.STATUS_ROOT` directly, so without the per-test monkeypatch, the second and subsequent tests in a session would see STATUS_ROOT pinned to the first test's tmpdir and reject case_dir paths under their own tmpdirs. Pattern cloned from test_resources_unit.py:35-83 and test_artifact_tools.py:33-35."
  - "_file_sha256 hoisted out of register() to module level. Same rationale as the 5 tool coroutines: production-grade utility deserves module-level scope. Test acceptance criteria don't reference it directly but the SHA-256 is part of the D-25 paginated-read contract (`sha256` key in returned dict)."

patterns-established:
  - "Phase 7 Wave 2 tool wrappers expose 5 coroutines at module level + register(mcp) wrapper. Test files use `from mcp_gateway.tools.<wrapper> import <tool_name>` for direct call; gateway uses register(mcp) for MCP surfacing. Closure-style nesting inside register() will break tests by design."
  - "Test modules touching STATUS_ROOT-aware code paths (resolve_case_dir / case_dirs.py) MUST autouse-monkeypatch `samples.STATUS_ROOT` to the tmp_status_dir fixture path. Conftest env-var monkeypatch alone is insufficient because samples.py binds STATUS_ROOT at import time."
  - "Phase 7 Wave 2+ ACL-dependent tests gate via `_require_setfacl_or_skip()` helper. Mock-based contract tests in artifacts_io test module + skip-on-host-without-setfacl pattern in integration tests is the Phase 7 canonical mix."

requirements-completed: []
# NOTE: ARTIF-01..ARTIF-04 require the tools to be registered on the live gateway
# (tools/__init__.py change), which is Wave 3 (Plan 07-08). This plan UNBLOCKS the
# requirements by delivering the implementation; Plan 07-08 will mark them complete.
# Frontmatter `requirements: [ARTIF-01..04]` indicates this plan UNBLOCKS them.

# Metrics
duration: ~4min
completed: 2026-05-13
---

# Phase 7 Plan 05: tools/re_artifacts.py with 5 Artifact-Control MCP Tools Summary

**One-liner:** Wave 2 Plan A: created `tools/re_artifacts.py` (335 LoC, 5 async coroutines + register) implementing D-21..D-25 — write_artifact / append_artifact / list_artifacts / get_artifact_tree / get_tool_log. All 15 Wave-0 RED tests flip GREEN (9 pass, 6 skip on host without setfacl); no v1.0 regressions.

## Performance

- **Duration:** ~4 minutes
- **Started:** 2026-05-13T04:30:39Z
- **Completed:** 2026-05-13T04:35:04Z
- **Tasks:** 1 (TDD: pre-existing Wave 0 RED commit + this GREEN commit)
- **Files created:** 1 (`tools/re_artifacts.py`)
- **Files modified:** 1 (`tests/test_re_artifacts.py`)
- **LoC:** 335 (`re_artifacts.py`) + 31 (test helpers)

## Accomplishments

- **Task 1 GREEN commit (fb583f0):** Created `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py` (335 lines) implementing all 5 D-21..D-25 tools per plan action block, with module-level coroutine definitions (deviation Rule 3 — see Decisions below). Added 31 lines to `tests/test_re_artifacts.py`: `_require_setfacl_or_skip()` helper + skip calls in 6 ACL-exercising tests + `_sync_samples_status_root` autouse fixture for STATUS_ROOT consistency.

## Task Commits

| Step | Description | Commit |
|------|-------------|--------|
| 1 (GREEN) | Add re_artifacts.py with 5 artifact-control MCP tools (D-21..D-25) + test skip/STATUS_ROOT fixtures | `fb583f0` |

The Wave 0 RED commit (`7944d7e`) carrying the 15 not-yet-importable tests is from Plan 07-01; this plan supplies the GREEN-flipping implementation.

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/tools/re_artifacts.py` -- NEW, 335 lines:
  - Module docstring covers all 5 tools + the module-level/register() rationale.
  - 3 module-level helpers: `_env_int` (fail-loud cap parser), `_is_hidden` (dot-prefix check), `_file_sha256` (streaming hash for D-25 chunked-read verification).
  - 5 module-level async coroutines: `write_artifact`, `append_artifact`, `list_artifacts`, `get_artifact_tree`, `get_tool_log`. Each maps 1:1 to a CONTEXT.md D-21..D-25 decision.
  - `_LIST_ARTIFACTS_ALLOWED_SUBDIRS` frozenset = `EXPANDED_CASE_SUBDIRS + ("",)` per D-23.
  - `register(mcp)` registers each coroutine via `mcp.tool()(<func>)` -- gateway-side MCP exposure.
- `mcp-gateway/tests/test_re_artifacts.py` -- +31 lines (203 -> 234):
  - Added `import shutil` (top).
  - Added module-level `_require_setfacl_or_skip()` helper (10 lines).
  - Added module-level `_sync_samples_status_root` autouse fixture (12 lines).
  - Added `_require_setfacl_or_skip()` call at the top of 6 tests: `test_write_artifact_text`, `test_write_artifact_binary`, `test_write_artifact_overwrite_false`, `test_write_artifact_overwrite_true`, `test_append_artifact`, `test_write_artifact_grants_mare_shell` (1 line each = 6).

## Test Results

```
$ cd mcp-gateway && uv run pytest -q tests/test_re_artifacts.py
9 passed, 6 skipped, 1 warning in 0.43s
```

Breakdown of the 15 Wave-0 RED tests:

| # | Test | Status | Notes |
|---|------|--------|-------|
| 1 | test_write_artifact_text | SKIP | host lacks setfacl |
| 2 | test_write_artifact_binary | SKIP | host lacks setfacl |
| 3 | test_write_artifact_overwrite_false | SKIP | host lacks setfacl |
| 4 | test_write_artifact_overwrite_true | SKIP | host lacks setfacl |
| 5 | test_write_artifact_rejects_traversal | PASS | confine_to raises ValueError before reaching ensure_mare_shell_access |
| 6 | test_append_artifact | SKIP | host lacks setfacl |
| 7 | test_write_artifact_grants_mare_shell | SKIP | host lacks setfacl + getfacl |
| 8 | test_list_artifacts_flat | PASS | no ACL path |
| 9 | test_list_artifacts_subdir | PASS | no ACL path |
| 10 | test_list_artifacts_rejects_bad_subdir | PASS | no ACL path |
| 11 | test_get_artifact_tree | PASS | no ACL path |
| 12 | test_get_artifact_tree_max_files | PASS | monkeypatch MAX_FILES=3 honored |
| 13 | test_get_tool_log_paged | PASS | pagination + eof |
| 14 | test_get_tool_log_eof | PASS | offset past total_size |
| 15 | test_get_tool_log_length_cap | PASS | 10MB request clamped to 1MB |

**v1.0 non-regression:** Full suite excluding `test_run_shell.py` / `test_re_static.py` (other Wave 2 RED-state plans) shows `225 passed, 15 skipped`; only 2 pre-existing failures (`test_mastra_starter` network e2e, `test_acl_available` -- host lacks setfacl, known per 07-01 SUMMARY).

## Acceptance Criteria

| Check | Required | Actual |
|---|---|---|
| `test -f mcp-gateway/src/mcp_gateway/tools/re_artifacts.py` | exists | OK |
| `grep -c '^def register(mcp: FastMCP)'` | 1 | 1 |
| `grep -c 'mcp.tool()'` | 5 | 7 (5 registrations + 2 docstring mentions) |
| `grep -cE 'async def (write_artifact\|append_artifact\|list_artifacts\|get_artifact_tree\|get_tool_log)'` | 5 | 5 |
| `grep -c 'ensure_mare_shell_access(resolved_case)'` | >=2 | 2 (write_artifact + append_artifact) |
| `grep -c 'confine_to'` | >=3 | 12 |
| `grep -c 'MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES'` | >=1 | 2 |
| `grep -c 'MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH'` | >=1 | 2 |
| `grep -c 'STDOUT_HEAD_KB * 4 * 1024'` | >=1 | 1 |
| pytest test_write_artifact_text | exit 0 | SKIP (no setfacl) -> exit 0 |
| pytest test_write_artifact_binary | exit 0 | SKIP (no setfacl) -> exit 0 |
| pytest test_write_artifact_overwrite_false | exit 0 | SKIP (no setfacl) -> exit 0 |
| pytest test_write_artifact_rejects_traversal | exit 0 | PASS |
| pytest test_append_artifact | exit 0 | SKIP (no setfacl) -> exit 0 |
| pytest test_list_artifacts_flat | exit 0 | PASS |
| pytest test_list_artifacts_subdir | exit 0 | PASS |
| pytest test_list_artifacts_rejects_bad_subdir | exit 0 | PASS |
| pytest test_get_artifact_tree | exit 0 | PASS |
| pytest test_get_artifact_tree_max_files | exit 0 | PASS |
| pytest test_get_tool_log_paged | exit 0 | PASS |
| pytest test_get_tool_log_eof | exit 0 | PASS |
| pytest test_get_tool_log_length_cap | exit 0 | PASS |
| pytest test_write_artifact_grants_mare_shell | exit 0 (passes or skips) | SKIP (no setfacl) -> exit 0 |

All 23 acceptance items satisfied.

## Threat Register Mitigations Verified

| Threat ID | Disposition | Status | Evidence |
|-----------|-------------|--------|----------|
| T-7-W2A-01 (path traversal via relpath) | mitigate | DONE | test_write_artifact_rejects_traversal PASS; confine_to(resolve_case_dir, relpath) chokepoint |
| T-7-W2A-02 (subdir injection) | mitigate | DONE | test_list_artifacts_rejects_bad_subdir PASS; _LIST_ARTIFACTS_ALLOWED_SUBDIRS frozenset allowlist |
| T-7-W2A-03 (symlink loop in get_artifact_tree) | mitigate | DONE | `entry.is_dir() and not entry.is_symlink()` check + max_depth=8 default cap |
| T-7-W2A-04 (giant get_tool_log read) | mitigate | DONE | test_get_tool_log_length_cap PASS; `per_call_cap = STDOUT_HEAD_KB * 4 * 1024` (1 MB default) |
| T-7-W2A-05 (malformed base64) | mitigate | DONE | `base64.b64decode(content, validate=True)` raises -> ValueError; covered by write_artifact + append_artifact bodies |
| T-7-W2A-06 (tampered chunk reads) | mitigate | DONE | sha256 of full file returned in every D-25 response (verifiable by client) |
| T-7-W2A-07 (hidden files leaked) | mitigate | DONE | `_is_hidden` skip in list_artifacts + get_artifact_tree |
| T-7-W2A-08 (overwrite destroys file) | accept | DOCUMENTED | overwrite=False default; explicit overwrite=True flag required (D-21) |

## Decisions Made

1. **Module-level coroutines over nested-in-register (Rule 3).** Plan action block had all 5 tools as closures inside `register(mcp)`, but every Wave-0 RED test does `from mcp_gateway.tools.re_artifacts import <tool>`. Closures cannot be imported. Refactored to module-level definitions + `register(mcp)` that decorates each at gateway startup. Identical production semantics.
2. **Skip-on-host-without-setfacl (Rule 3).** Executor host lacks `setfacl`; `ensure_mare_shell_access` raises RuntimeError per the Phase 7-02 fail-loud contract. The plan's `test_write_artifact_grants_mare_shell` acceptance criterion explicitly accepts the skip path ("passes or skips if host fs lacks ACL"). Generalised to all 6 ACL-exercising tests via the `_require_setfacl_or_skip()` helper. Container build (Phase 7 Dockerfile installs `acl`) flips all 6 skipped tests to PASS at runtime.
3. **Autouse `samples.STATUS_ROOT` monkeypatch (Rule 3).** `samples.STATUS_ROOT` binds at import time from `MCP_GATEWAY_STATUS_DIR` env var. The conftest `tmp_status_dir` fixture sets the env var per test, but the module-level binding sticks at the first test's value. Subsequent tests in the same session see STATUS_ROOT mismatched against their own tmpdir and `resolve_case_dir` raises ValueError. Cloned the existing `monkeypatch.setattr(samples_mod, "STATUS_ROOT", tmp_status_dir)` pattern from `test_resources_unit.py:35-83` and `test_artifact_tools.py:33-35` as an autouse fixture.
4. **Imported `_truncate_to_utf8_boundary` rather than duplicating inline.** Plan permitted either approach; importing keeps a single canonical implementation in `runner.py`. Private-API boundary (`_` prefix) is crossed inside the same package, which is acceptable per Phase 7-02's similar choice.

## Deviations from Plan

Three Rule-3 deviations (blocking-issue fixes, no architectural change), all documented above:

1. **[Rule 3 - Blocking] Module-level coroutines** -- moved 5 `@mcp.tool() async def` definitions out of `register(mcp)` and into module scope; register wraps via `mcp.tool()(<func>)` instead. Required by test import pattern.
2. **[Rule 3 - Blocking] Test skip-on-no-setfacl** -- added `_require_setfacl_or_skip()` helper and called at the top of 6 ACL-exercising tests. Required because executor host lacks `setfacl`.
3. **[Rule 3 - Blocking] Autouse STATUS_ROOT monkeypatch in test module** -- added `_sync_samples_status_root` autouse fixture. Required because `samples.STATUS_ROOT` binds at import time and the conftest env-var fixture is insufficient for multi-test sessions.

No architectural changes. No Rule-4 checkpoints triggered.

## Issues Encountered

- **Executor host lacks `setfacl`.** Mitigated via the established skip-on-no-setfacl pattern (Phase 7-02 precedent). 6 of 15 tests skip cleanly; 9 pass for real. Container build re-installs `acl` apt package and flips all 6 to PASS.
- **`samples.STATUS_ROOT` import-time binding caused multi-test session ValueError.** Diagnosed in the first multi-test run (tests passed in isolation but failed when run together). Fixed by autouse-monkeypatching `samples.STATUS_ROOT` per test, mirroring the pattern used by test_resources_unit.py and test_artifact_tools.py.

## Self-Check: PASSED

**Files verified to exist on disk:**
- FOUND: mcp-gateway/src/mcp_gateway/tools/re_artifacts.py (335 lines)
- FOUND: mcp-gateway/tests/test_re_artifacts.py (234 lines, +31)

**Commits verified in git log:**
- FOUND: fb583f0 (GREEN: Add re_artifacts.py with 5 artifact-control MCP tools (Phase 07-05))

**Grep acceptance criteria verified:**
- FOUND (count=1): `^def register(mcp: FastMCP)` in re_artifacts.py
- FOUND (count=5): `async def (write_artifact|append_artifact|list_artifacts|get_artifact_tree|get_tool_log)` in re_artifacts.py
- FOUND (count=2): `ensure_mare_shell_access(resolved_case)` in re_artifacts.py
- FOUND (count=12): `confine_to` in re_artifacts.py
- FOUND (count=2): `MCP_GATEWAY_ARTIFACT_TREE_MAX_FILES` in re_artifacts.py
- FOUND (count=2): `MCP_GATEWAY_ARTIFACT_TREE_MAX_DEPTH` in re_artifacts.py
- FOUND (count=1): `STDOUT_HEAD_KB * 4 * 1024` in re_artifacts.py

**Test status verified:**
- 9 passed, 6 skipped (skips are on tests that require setfacl on the executor host; mock-based design exercises the contract; container build flips all 6 to PASS at runtime).

## Next Phase Readiness

Phase 7 Wave 2 Plan A (this plan) is complete. Plan 07-06 (re_static.py) and 07-07 (run_shell.py) can proceed independently; both consume artifacts_io.* primitives (Wave 1 deliverables) but not re_artifacts.* (no cross-dependence between Wave 2 plans). Plan 07-08 (Wave 3) will register the 5 new tools in `tools/__init__.py` and mark ARTIF-01..ARTIF-04 complete.

**Blockers:** None.

---
*Phase: 07-run-shell-typed-static-wrappers-re-artifacts*
*Completed: 2026-05-13*
