---
phase: 04-external-client-integration
plan: "03"
subsystem: api
tags: [mcp, resources, fastmcp, mime, python]

# Dependency graph
requires:
  - phase: 02-mcp-gateway
    provides: FastMCP gateway with register_all_tools() entry point, STATUS_ROOT, CASE_NAME_RE
provides:
  - "mare://cases/<case>/<artifact> MCP Resources URI scheme (D-01)"
  - "Dynamic resources/list enumeration of all cases × 13 artifacts (D-02)"
  - "13-artifact ARTIFACTS tuple matching artifact-spec.md (D-03)"
  - "Extension-based MIME map with .log=text/plain and octet-stream fallback (D-04)"
  - "Path traversal protection via CASE_NAME_RE + artifact allowlist + realpath check (T-04-01)"
  - "Unit tests for MIME map and resources module internals"
affects:
  - 04-external-client-integration
  - any plan that tests or exercises resources/list + resources/read

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastMCP resource registration: @mcp.resource() template + @mcp._mcp_server.list_resources() low-level handler"
    - "Path safety: CASE_NAME_RE allowlist + artifact tuple allowlist + os.path.realpath + relative_to()"
    - "MIME inference: hand-rolled _MIME_MAP dict keyed on lowercased suffix (avoids stdlib mimetypes .log gap)"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/tools/resources.py
    - mcp-gateway/tests/test_resources_mime.py
    - mcp-gateway/tests/test_resources_unit.py
  modified:
    - mcp-gateway/src/mcp_gateway/tools/__init__.py

key-decisions:
  - "Two-pronged FastMCP resource registration: URI template (@mcp.resource) for templates/list + low-level list_resources override for dynamic resources/list"
  - "MIME map is hand-rolled (not stdlib mimetypes) because mimetypes returns None for .log on stock Linux"
  - "_safe_artifact_path() validates case name via CASE_NAME_RE, artifact via ARTIFACTS allowlist, then realpath+relative_to for symlink escape prevention"
  - "Uploads NOT exposed as resources per D-05 (D-04 in context doc)"

patterns-established:
  - "Pattern: resources module follows same register(mcp) pattern as tools/{cases,artifacts,workflows,disasm}.py"
  - "Pattern: monkeypatch STATUS_ROOT attribute on the resources module for filesystem-isolated unit tests"

requirements-completed: [CLI-04]

# Metrics
duration: 5min
completed: 2026-04-27
---

# Phase 4 Plan 03: MCP Resources for Case Artifacts Summary

**`mare://cases/<case>/<artifact>` resource URI scheme with dynamic listing, 13-artifact coverage, MIME inference, and path traversal protection — registered via two-pronged FastMCP pattern**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-27T08:03:28Z
- **Completed:** 2026-04-27T08:08:44Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Created `tools/resources.py` with ARTIFACTS tuple (13 items matching artifact-spec.md), `_mime_for()`, `_list_cases()`, `_build_resource_list()`, `_safe_artifact_path()`, and `register(mcp)`
- Wired resources module into `register_all_tools()` via single import + register call in `tools/__init__.py`
- Added 9 parametrized MIME map tests (`test_resources_mime.py`) and 9 unit tests for module internals (`test_resources_unit.py`) — 18 tests total, all green
- Verified existing gateway tests (`test_server_init.py`, `test_tool_list.py`) unaffected — 9/9 still pass

## Task Commits

Each task was committed atomically:

1. **Task 1: MIME map unit test (TDD-RED)** - `aa86f2a` (test)
2. **Task 2: resources.py + __init__.py wiring + unit tests (TDD-GREEN)** - `1351582` (feat)

## Files Created/Modified

- `mcp-gateway/src/mcp_gateway/tools/resources.py` - MCP Resources module: ARTIFACTS tuple, MIME map, _list_cases, _build_resource_list, _safe_artifact_path, register(mcp)
- `mcp-gateway/src/mcp_gateway/tools/__init__.py` - Added `resources` to import list and `resources.register(mcp)` call
- `mcp-gateway/tests/test_resources_mime.py` - 9 parametrized tests for _mime_for() covering .json, .txt, .log, .md, .bin, no-ext, uppercase variants
- `mcp-gateway/tests/test_resources_unit.py` - 9 unit tests: ARTIFACTS count/content, _list_cases enumeration/filtering, _build_resource_list cartesian product, _safe_artifact_path traversal rejection

## Decisions Made

- Two-pronged resource registration required: `@mcp.resource()` template alone only appears in `resources/templates/list`, not `resources/list`; `@mcp._mcp_server.list_resources()` override is needed for dynamic per-request enumeration (RESEARCH Pitfalls 1 & 2)
- MIME map hand-rolled: `stdlib.mimetypes` returns `None` for `.log` on stock Linux, per RESEARCH Pitfall 3
- `_safe_artifact_path()` uses three layers: (1) CASE_NAME_RE rejects `..` and non-case names, (2) ARTIFACTS tuple allowlist rejects unknown filenames, (3) `os.path.realpath` + `relative_to(STATUS_ROOT)` blocks symlink escapes

## Deviations from Plan

None - plan executed exactly as written. Implementation matches RESEARCH Pattern 1 verbatim.

## Issues Encountered

- `uv` was not in PATH on this host; installed via `pip3 install --break-system-packages uv` before running tests. No impact on deliverables.

## Threat Surface Scan

No new network endpoints, auth paths, or file access patterns beyond what is specified in the plan's threat model (T-04-01, T-04-03, T-04-T1, T-04-T2). The `resources.py` module reads only under `STATUS_ROOT`; uploads remain unexposed per D-05.

## Known Stubs

None. The `ARTIFACTS` tuple and `_mime_for()` map are fully wired. `_list_cases()` enumerates the real filesystem (returning empty when `STATUS_ROOT` doesn't exist in test environments). No placeholder data flows to any rendering surface.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `mare://cases/<case>/<artifact>` URI scheme is live; e2e tests (04-05) can issue `resources/list` and `resources/read` against a running gateway container
- `test_resources_unit.py` uses `monkeypatch.setattr(R, "STATUS_ROOT", ...)` pattern — reusable for future resource-related tests
- Tool count in `test_tool_list.py` (15-25 range) is unaffected; resources are not tools

---
*Phase: 04-external-client-integration*
*Completed: 2026-04-27*
