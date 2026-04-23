---
phase: 02-mcp-gateway
plan: 02
subsystem: gateway
tags: [mcp, fastmcp, tools, orchestrator, starlette, streamable-http, python]

# Dependency graph
requires:
  - phase: 02-mcp-gateway
    plan: 01
    provides: auth (BearerAuthMiddleware, OriginMiddleware, load_or_generate_token), backend.detect, session_state
provides:
  - build_app() Starlette factory mounting FastMCP Streamable HTTP at /mcp with auth + origin middleware
  - register_all_tools() entry point registering 21 curated tools (3 composite + 10 atomic + 3 disasm + 5 case/sample)
  - resolve_sample() path resolver with realpath+allowlist traversal protection (T-02-PATHTRAVERSAL)
  - run_script() argv-only asyncio subprocess runner with timeout + kill (T-02-SUBPROC)
  - get_mcp() singleton accessor for FastMCP instance (used by Plan 03 to attach backend-fed delegations)
  - /healthz (open) + /upload (501 placeholder) + /mcp (FastMCP mount)
affects: [02-03, 02-04, 02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Starlette mount hack: FastMCP(streamable_http_path='/') + Mount('/mcp', inner) so outer endpoint is exactly /mcp (avoids /mcp/mcp)"
    - "FastMCP built-in transport_security disabled — OriginMiddleware at Starlette layer covers T-02-NET"
    - "Lazy module-level FastMCP singleton (_MCP_INSTANCE) with get_mcp() accessor so Plan 03 can register backend-fed tools on the same instance"
    - "Each tool module exposes a single register(mcp) function called by register_all_tools — keeps tool files decoupled from MCP import cycles"
    - "Atomic tool argv construction: ['bash', str(SCRIPTS/'<name>.sh'), resolved_path] for shell scripts; ['python3', str(SCRIPTS/'<name>.py'), '--status-dir', case_dir] for Python helpers"
    - "resolve_sample canonicalize-then-allowlist: os.path.realpath + Path.relative_to each ALLOWED_PREFIX"
    - "Continue-on-error composite workflow (run_triage) collects {step, exit_code, stderr_head} per step rather than short-circuiting"
    - "Backend-wired stub: disasm tools return {error, unified_tool, note} when session_state.PINNED_BACKEND is None so Plan 03 can swap bodies without re-registering"
    - "Private _tool_manager._tools access guarded by mcp>=1.27,<1.28 pin; public create_connected_server_and_client_session used for name listing"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/app.py
    - mcp-gateway/src/mcp_gateway/subprocess_runner.py
    - mcp-gateway/src/mcp_gateway/tools/__init__.py
    - mcp-gateway/src/mcp_gateway/tools/samples.py
    - mcp-gateway/src/mcp_gateway/tools/cases.py
    - mcp-gateway/src/mcp_gateway/tools/artifacts.py
    - mcp-gateway/src/mcp_gateway/tools/workflows.py
    - mcp-gateway/src/mcp_gateway/tools/disasm.py
    - mcp-gateway/tests/test_sample_resolution.py
    - mcp-gateway/tests/test_artifact_tools.py
    - mcp-gateway/tests/test_workflow_tools.py
    - mcp-gateway/tests/test_server_init.py
    - mcp-gateway/tests/test_tool_list.py
  modified: []

key-decisions:
  - "Rule 1 bug-fix vs plan: FastMCP default streamable_http_path='/mcp' combined with Mount('/mcp', ...) produced /mcp/mcp at runtime (404). Fixed by passing streamable_http_path='/' to FastMCP so Mount('/mcp', ...) yields the expected /mcp endpoint"
  - "Disabled FastMCP built-in transport_security (enable_dns_rebinding_protection=False) because OriginMiddleware on the outer Starlette app already covers T-02-NET; leaving FastMCP's check on rejected TestClient requests with 421 Invalid Host"
  - "Deep analysis run_deep_analysis is a Phase 2 stub: just marks phase=planning_complete via update_state.py — full deep-analysis is v2 scope per RESEARCH.md Open Questions #2"
  - "21-tool target (D-01..D-04) chosen over plan frontmatter's 18; 5+10+3+3 composition sits well within GW-02 range [15,25]"
  - "Tool decorators apply @mcp.tool() inside register(mcp) closures rather than at module top level — lets each module be importable without a FastMCP instance; FastMCP captures the decorated handler when register() runs"
  - "Continue-on-error for run_triage per RESEARCH.md Open Questions #3: individual script failures append to the steps list rather than short-circuiting the workflow"
  - "PINNED_BACKEND stub pattern in disasm.py: Plan 02 returns {error, unified_tool, note} when None; Plan 03 will drop in PinnedBackend.call_unified(unified_name, args) delegation without re-registering tools"

patterns-established:
  - "Canonicalize-then-allowlist for all user-provided paths (resolve_sample + get_artifact)"
  - "argv-only subprocess execution (zero shell=True, zero os.system/os.popen) — caller builds argv list with filesystem paths from resolve_sample"
  - "Test seam: monkeypatch mcp_gateway.tools.samples.ALLOWED_PREFIXES + UPLOADS_ROOT to tmp_path rather than touching /agent/uploads"
  - "FastMCP handler extraction pattern (for unit tests): _get_tool(mcp, name) -> mcp._tool_manager._tools[name].fn; documented as SDK-version-coupled with pin"
  - "BearerAuth + Origin middleware ordering in build_app: add_middleware(Bearer) then add_middleware(Origin) so Origin runs outer (DNS rebind 403 precedes 401)"

requirements-completed: [GW-01, GW-02]

# Metrics
duration: ~12min
completed: 2026-04-23
---

# Phase 02 Plan 02: FastMCP Server and Tool Surface Summary

**Starlette + FastMCP gateway with 21 curated MCP tools (3 composite + 10 atomic orchestrator shell-outs + 3 disassembler stubs + 5 case/sample mgmt), Streamable HTTP at `/mcp` gated by bearer + Origin middleware, with path-traversal and argv-only subprocess mitigations — 53 tests green.**

## Performance

- **Duration:** ~12 min (resumed after prior API error)
- **Completed:** 2026-04-23
- **Tasks:** 3 (all TDD RED -> GREEN cycles)
- **Files created:** 13 (8 src modules + 5 test modules)
- **Tests added this plan:** 31 new (12 sample_resolution + 6 artifact_tools + 4 workflow_tools + 4 server_init + 5 tool_list) — full suite: 53 passing
- **Commits:** 7 (`18bce39`, `1665198`, `097bd1e`, `831c2be`, `17c8bb9`, `d34fea1`, `7605537`)

## Accomplishments

### 21-Tool Curated Surface (GW-02)

| Category | Tool | Module | Shells out to / Behavior |
|---|---|---|---|
| Composite (3) | `run_triage` | workflows.py | init -> strings -> imports -> yara -> capa -> rank -> hypothesis -> update_state(phase=triage_complete); continue-on-error |
|               | `run_deep_analysis` | workflows.py | Phase 2 stub: update_state --phase planning_complete |
|               | `generate_report` | workflows.py | Reads `<case_dir>/10_reporting_draft.md` |
| Atomic (10)   | `init_case` | artifacts.py | `bash init_status_tree.sh <sample> [--new]` |
|               | `collect_strings` | artifacts.py | `bash collect_strings.sh <sample> [case_dir]` |
|               | `collect_imports` | artifacts.py | `bash collect_imports.sh <sample> [case_dir]` |
|               | `scan_yara` | artifacts.py | `bash scan_yara.sh <sample> [case_dir]` |
|               | `scan_capa` | artifacts.py | `bash scan_capa.sh <sample> [case_dir]` |
|               | `rank_signals` | artifacts.py | `python3 rank_signals.py --status-dir <case>` |
|               | `build_hypothesis` | artifacts.py | `python3 build_hypothesis.py --status-dir <case>` |
|               | `update_state` | artifacts.py | `python3 update_state.py --status-dir <case> --phase <phase>` |
|               | `resolve_case` | artifacts.py | `bash resolve_case.sh <sample>` -> stdout-trimmed path |
|               | `get_artifact` | artifacts.py | Reads `<case_dir>/<name>` with traversal check |
| Disasm (3)    | `decompile` | disasm.py | PINNED_BACKEND stub (Plan 03 wires) |
|               | `list_functions` | disasm.py | PINNED_BACKEND stub (Plan 03 wires) |
|               | `get_xrefs` | disasm.py | PINNED_BACKEND stub (Plan 03 wires) |
| Case/sample (5)| `list_cases` | cases.py | Enumerate `/agent/status/NNN-*` |
|               | `set_active_case` | cases.py | Writes session_state.ACTIVE_CASE |
|               | `get_active_case` | cases.py | Reads session_state.ACTIVE_CASE |
|               | `list_uploads` | cases.py | Enumerate `/agent/uploads/<sha256>/*` |
|               | `get_sample_info` | cases.py | resolve_sample + stat + sha256 |

Tool count in-range: 21 (GW-02 target 15-25). Every orchestrator script in `workspace/.claude/skills/malware-analysis-orchestrator/scripts/` has a matching atomic tool (verified by `test_atomic_tools_map_to_scripts`).

### FastMCP + Starlette Wiring (GW-01)

- `build_app()` order:
  1. `load_or_generate_token()` from Plan 01 (D-16 env-var-wins, D-17 0600 file, T-02-TOKENLEAK).
  2. `detect_backend()` (D-09 IDA>BN>Ghidra) with `MCP_GATEWAY_SKIP_BACKEND=1` test escape hatch (D-10 fail-loud default).
  3. `get_mcp()` returns module-level FastMCP singleton (Plan 03 reuses).
  4. `register_all_tools(mcp)` registers all 21 tools.
  5. Routes: `Route("/healthz")` open, `Route("/upload")` 501 placeholder, `Mount("/mcp", streamable_http_app())`.
  6. Middleware order (LIFO add -> LIFO run): `OriginMiddleware` outer (T-02-NET), `BearerAuthMiddleware` inner (T-02-AUTH).
  7. Lifespan enters `mcp.session_manager.run()` context for Streamable HTTP session manager lifecycle.

### Initialize Handshake

`test_mcp_initialize_succeeds` posts a JSON-RPC `initialize` to `/mcp` with bearer + Accept headers through Starlette's `TestClient`. Response: 200 with `result.serverInfo.name == "mare-gateway"` — FastMCP Streamable HTTP round-trip works end-to-end (GW-01).

### Security Mitigations

| Threat | File | Mitigation |
|---|---|---|
| T-02-SUBPROC (RCE via shell injection) | `subprocess_runner.py`, all atomic tools | `asyncio.create_subprocess_exec(*argv)`; zero `shell=True`; zero `os.system`/`os.popen` (grep-verified) |
| T-02-PATHTRAVERSAL (`..` in sample path) | `tools/samples.py::resolve_sample` | `os.path.realpath()` canonicalize + `Path.relative_to(prefix)` allowlist (uploads, examples, status); pre-canonicalization `".."` reject for defense in depth |
| T-02-PATHTRAVERSAL (artifact name) | `tools/artifacts.py::get_artifact` | Reject `/`, `..`, leading `.` in name; canonicalize `<case_dir>/<name>` + verify stays under case_dir |
| T-02-AUTH | `app.py` build_app middleware wiring | `BearerAuthMiddleware` covers `/mcp*` + `/upload`; `/healthz` open by design (Plan 01) |
| T-02-NET | `app.py` middleware wiring | `OriginMiddleware` outer; rejects evil Origin with 403; allows localhost, 127.0.0.1, null, missing |
| T-02-UPLOAD (DoS) | `/upload` placeholder | Returns 501 — does not accept body; Plan 04 replaces with streaming handler + `MCP_GATEWAY_MAX_UPLOAD_MB` |
| T-02-TOKENLEAK | Plan 01 owns; Task 3 doesn't re-log token | `build_app()` only calls `load_or_generate_token()` — no second log site |

## Test Counts

| Test module | Count | Focus |
|---|---|---|
| `test_sample_resolution.py` | 12 | resolve_sample traversal protection (7) + run_script (5) |
| `test_artifact_tools.py` | 6 | argv shape for init_case, collect_strings, rank_signals, update_state; get_artifact traversal + happy path |
| `test_workflow_tools.py` | 4 | run_triage canonical script order; run_deep_analysis phase arg; generate_report missing + content |
| `test_server_init.py` | 4 | /healthz open, evil Origin 403, /mcp requires bearer, initialize handshake 200 |
| `test_tool_list.py` | 5 | 21 expected tools present, count in [15,25], no unexpected, script->tool map, private-attr sanity |
| **Plan 02-02 new total** | **31** |  |
| Plan 02-01 carryover | 22 | auth (14) + cli (3) + detect (6) — same commit range, all still green |
| **Full mcp-gateway suite** | **53** | all passing, 0.69s runtime |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FastMCP mount path produced /mcp/mcp instead of /mcp**
- **Found during:** Task 3 GREEN (test_mcp_initialize_succeeds failed with 404 after first `app.py` run).
- **Issue:** The plan's `app.py` used `FastMCP(..., json_response=True)` (default `streamable_http_path="/mcp"`) combined with `Mount("/mcp", app=mcp.streamable_http_app())`. Mount prefix-strips, so the inner route registered at `/mcp` was only reachable at `/mcp/mcp` — POST `/mcp` returned 404.
- **Fix:** Pass `streamable_http_path="/"` to FastMCP and disable FastMCP's built-in `transport_security` (DNS-rebind) since the outer Starlette app already applies `OriginMiddleware` for T-02-NET. FastMCP's built-in check was rejecting `TestClient` requests with 421 "Invalid Host header" because `TestClient` uses `testserver` as host. `OriginMiddleware` + `BearerAuthMiddleware` at the Starlette layer are sufficient.
- **Files modified:** `mcp-gateway/src/mcp_gateway/app.py` (`get_mcp()` constructor args)
- **Commit:** `d34fea1`

**2. [Rule 1 - Bug] ruff-flagged unused imports**
- **Found during:** Post-GREEN verification with `ruff check`.
- **Fix:** `ruff --fix` removed unused `session_state` (app.py), `os` + `typing.Optional` (cases.py), and `pathlib.Path` / `typing.Any` imports in the 4 test files I authored in Task 2/3. Pre-existing unused imports in Plan 01's `conftest.py` and older tests left untouched (scope boundary).
- **Commit:** `7605537`

## Handoffs

### To Plan 03 (backend client + pinned routing)
- `session_state.PINNED_BACKEND` is still `None` at module import — `disasm.py` tools return the `{error, unified_tool, note}` stub so Plan 03's body swap is self-contained.
- Expected contract (planned for Plan 03): `session_state.PINNED_BACKEND` becomes a `PinnedBackend` with async method `call_unified(unified_name: str, args: dict) -> dict`. `disasm.py` already calls that method when PINNED_BACKEND is truthy; Plan 03 only needs to set it and implement the class.
- `get_mcp()` is the single entry point for Plan 03 to register backend-fed tools on the same FastMCP instance used by `build_app()`.
- The lifespan in `build_app()` uses `@contextlib.asynccontextmanager` — Plan 03 should extend it with an inner `async with PinnedBackend(...):` block that sets `session_state.PINNED_BACKEND` on entry and clears it on exit.

### To Plan 04 (upload endpoint)
- `/upload` route is `Route("/upload", _upload_placeholder, methods=["POST"])` returning 501 `{error, plan}`.
- Plan 04 replaces `_upload_placeholder` (or adds a new handler and swaps the Route) with a streaming multipart handler enforcing `MCP_GATEWAY_MAX_UPLOAD_MB`. The placeholder intentionally refuses the body so a client hitting the unfinished endpoint gets an immediate 501 rather than accumulating upload state.
- `UPLOADS_ROOT = Path(os.environ.get("MCP_GATEWAY_UPLOAD_DIR", "/agent/uploads"))` already exists in `tools/samples.py` and is the canonical write target.

## Known Stubs

| File | Line | Reason | Resolved by |
|---|---|---|---|
| `src/mcp_gateway/tools/disasm.py` | `_backend_error_stub` returned in 3 tool handlers | `session_state.PINNED_BACKEND` not wired this plan | Plan 03 |
| `src/mcp_gateway/app.py` | `_upload_placeholder` returns 501 | Streaming upload handler is Plan 04 scope | Plan 04 |
| `src/mcp_gateway/tools/workflows.py` | `run_deep_analysis` only flips phase to `planning_complete` | Full deep-analysis pipeline is v2 scope (RESEARCH.md Open Q#2) | v2 backlog |

All stubs are intentional per plan — disasm and /upload have explicit handoff documentation and are covered by D-05 (no raw passthrough) + VALIDATION.md expected-outcome rows for their respective later plans.

## Verification Summary

- [x] `pytest mcp-gateway/tests/ --no-header -q` -> 53 passed in 0.69s
- [x] `python -c "from mcp_gateway.tools import register_all_tools; ..."` prints `21`
- [x] `grep -rn 'shell=True' mcp-gateway/src/` -> no hits
- [x] `grep -rn 'os.system\|os.popen' mcp-gateway/src/` -> no hits
- [x] `ruff check` on all plan 02-02 files -> clean
- [x] All 9 acceptance-grep patterns in Task 3 match (streamable_http_app, session_manager.run, BearerAuthMiddleware, OriginMiddleware, /healthz route, /upload route, /mcp mount, detect_backend)
- [x] GW-01: `test_mcp_initialize_succeeds` green — FastMCP Streamable HTTP initialize over `/mcp` with bearer returns 200 with `serverInfo.name == "mare-gateway"`
- [x] GW-02: 21 tools registered, in [15,25], every orchestrator script mapped to a tool

## Self-Check: PASSED

Verified artifacts exist and commits are recorded:

- FOUND: mcp-gateway/src/mcp_gateway/app.py
- FOUND: mcp-gateway/src/mcp_gateway/subprocess_runner.py
- FOUND: mcp-gateway/src/mcp_gateway/tools/__init__.py
- FOUND: mcp-gateway/src/mcp_gateway/tools/samples.py
- FOUND: mcp-gateway/src/mcp_gateway/tools/cases.py
- FOUND: mcp-gateway/src/mcp_gateway/tools/artifacts.py
- FOUND: mcp-gateway/src/mcp_gateway/tools/workflows.py
- FOUND: mcp-gateway/src/mcp_gateway/tools/disasm.py
- FOUND: mcp-gateway/tests/test_sample_resolution.py
- FOUND: mcp-gateway/tests/test_artifact_tools.py
- FOUND: mcp-gateway/tests/test_workflow_tools.py
- FOUND: mcp-gateway/tests/test_server_init.py
- FOUND: mcp-gateway/tests/test_tool_list.py
- FOUND: 18bce39 (test RED Task 1)
- FOUND: 1665198 (feat GREEN Task 1)
- FOUND: 097bd1e (test RED Task 2)
- FOUND: 831c2be (feat GREEN Task 2)
- FOUND: 17c8bb9 (test RED Task 3)
- FOUND: d34fea1 (feat GREEN Task 3)
- FOUND: 7605537 (chore ruff cleanup)
