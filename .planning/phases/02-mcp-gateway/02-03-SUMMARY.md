---
phase: 02-mcp-gateway
plan: 03
subsystem: gateway
tags: [mcp, backend, routing, client, pinned, python]

# Dependency graph
requires:
  - phase: 02-mcp-gateway
    plan: 01
    provides: session_state.PINNED_BACKEND module attribute, backend.detect detect_backend(), auth middleware, installable package
  - phase: 02-mcp-gateway
    plan: 02
    provides: build_app() Starlette factory, get_mcp() FastMCP singleton, disasm.py tools already call session_state.PINNED_BACKEND.call_unified()
provides:
  - mcp_gateway.backend.tool_map.translate(unified, backend, args) -> (backend_tool_name, transformed_args)
  - mcp_gateway.backend.client.PinnedBackend async context manager (IDA http / BN stdio / Ghidra stdio)
  - mcp_gateway.backend.__init__ re-exports PinnedBackend alongside detect_backend
  - app.py lifespan that enters PinnedBackend and toggles session_state.PINNED_BACKEND for the gateway lifetime
  - asyncio.Lock-based serialization of concurrent call_unified invocations (Open Q2 resolved)
affects: [02-04, 02-05]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AsyncExitStack composition: stack.enter_async_context(transport) -> stack.enter_async_context(ClientSession(read,write)) -> initialize() -- single aclose() unwinds everything"
    - "Transport-switch dispatch by backend name in PinnedBackend.__aenter__ (ida -> streamablehttp_client; bn/ghidra -> stdio_client with StdioServerParameters)"
    - "Fail-loud __aenter__: wrap in try/except, aclose the partial stack, re-raise the original exception (D-10)"
    - "asyncio.Lock around session.call_tool to serialize concurrent unified tool invocations against a single ClientSession"
    - "CallToolResult normalization: extract TextContent -> {type:text, text:...}; fall back to {type: ClassName} for other block types"
    - "TOOL_MAP double-nested dict ({unified: {backend: (backend_tool, args_xform)}}) with identity xform in Phase 2, ready for DIS-V2-01 shape-normalization swaps"
    - "Lifespan outer-with-inner: `async with PinnedBackend(name) as pinned` wraps `async with mcp.session_manager.run()`; try/finally clears session_state.PINNED_BACKEND even if session_manager raises"
    - "Test singleton reset pattern: monkeypatch.setattr(app_mod, '_MCP_INSTANCE', None) lets lifespan tests enter a fresh FastMCP so StreamableHTTPSessionManager.run() can be called again"
    - "Fake PinnedBackend drop-in via mcp.shared.memory.create_connected_server_and_client_session for in-process integration tests (no network, no stdio)"

key-files:
  created:
    - mcp-gateway/src/mcp_gateway/backend/tool_map.py
    - mcp-gateway/src/mcp_gateway/backend/client.py
    - mcp-gateway/tests/test_tool_map.py
    - mcp-gateway/tests/test_tool_routing.py
  modified:
    - mcp-gateway/src/mcp_gateway/backend/__init__.py
    - mcp-gateway/src/mcp_gateway/app.py
    - mcp-gateway/src/mcp_gateway/tools/disasm.py

key-decisions:
  - "BN tool names flagged TODO(Plan 03 container-side validation): vendored submodule at /agent/mcp/binary-ninja-headless-mcp/ not available on the devlaptop worktree so Phase 2 uses unified names as fallback; Plan 05 installer must re-verify via tools/list at container startup"
  - "IDA uses Streamable HTTP 127.0.0.1:8745/mcp via mcp.client.streamable_http.streamablehttp_client - literal IPv4 (avoids DNS hostname IPv6 hang per RESEARCH Pitfall 3); no re-spawn of idalib-mcp (daemon already running from Phase 1)"
  - "BN/Ghidra use stdio subprocess via mcp.client.stdio.stdio_client + StdioServerParameters(command='python3', args=[LITERAL_SCRIPT_PATH]) - hardcoded paths, argv-only, no shell; Ghidra injects GHIDRA_INSTALL_DIR env (resolves /usr/share/ghidra by default, matches configure-agent-mcp.sh)"
  - "asyncio.Lock on PinnedBackend._call_lock serializes ALL concurrent call/call_unified invocations - resolves RESEARCH Open Q2 (FastMCP may invoke tool handlers concurrently; ClientSession single-socket stream requires serialization)"
  - "D-09 enforcement: backend_name captured at build_app() time; lifespan enters exactly one PinnedBackend for the gateway's lifetime; session_state.PINNED_BACKEND is set/cleared by the lifespan so concurrent requests share the same pinned session"
  - "D-10 enforcement: PinnedBackend.__aenter__ re-raises on init failure AFTER aclosing the partial stack - the lifespan does NOT fall back to the next-priority backend (silent fallback would violate fail-loud)"
  - "MCP_GATEWAY_SKIP_BACKEND=1 escape hatch: lifespan takes the backend_name=None branch, enters session_manager.run() alone, and disasm tools continue returning Plan 02's {error, unified_tool, note} stub - allows server_init + tool_list tests to drive the full app without requiring a real disassembler"
  - "Rule 1 ruff E731 fix: tool_map._identity replaced with def _identity(args): return dict(args) - functionally identical but type-annotation-friendlier; tests still green"

patterns-established:
  - "Double-nested TOOL_MAP with args_transform slot for future shape normalization (no-op identity in Phase 2, ready for DIS-V2-01)"
  - "Backend client uses SDK-public APIs only (ClientSession, streamablehttp_client, stdio_client) - no private-attr access; the only SDK-version-coupled code is the tests' .fn extraction (inherited from Plan 02)"
  - "Rule 1 auto-fix within scope boundary: ruff errors in my new files fixed; F401 in unrelated conftest.py/test_auth.py/test_cli.py left untouched (Plan 01 scope)"

requirements-completed: [GW-03]

# Metrics
duration: 8min
completed: 2026-04-23
---

# Phase 02 Plan 03: Backend Client Routing Summary

**PinnedBackend async context manager (IDA Streamable HTTP + BN/Ghidra stdio) + tool_map unified->backend translation layer wired into Starlette lifespan, with asyncio.Lock serialization, fail-loud error propagation, and end-to-end delegation from unified MCP tools to the pinned disassembler backend -- 28 new tests green (81 total).**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-04-23T07:13:04Z
- **Tasks:** 3 (all TDD RED -> GREEN cycles)
- **Files created:** 4 (2 src + 2 test)
- **Files modified:** 3 (backend/__init__.py, app.py, tools/disasm.py)
- **Tests added:** 28 (13 tool_map parametrized + 15 tool_routing/lifespan)
- **Full suite:** 81 passed in 0.98s (53 Plan 01/02 baseline + 28 new)
- **Commits:** 6 (`a85d11f`, `749886c`, `c449c94`, `f196758`, `d791c65`, `73cda7e`)

## Accomplishments

### Transport Matrix (GW-03)

| Backend | Transport | URL / Command | Source |
|---|---|---|---|
| `ida` | Streamable HTTP | `http://127.0.0.1:8745/mcp` (literal IPv4) | idalib-mcp daemon from Phase 1 (already running) |
| `bn` | stdio subprocess | `python3 /agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` | spawned inside lifespan, argv-only, no shell |
| `ghidra` | stdio subprocess | `python3 /agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` with `GHIDRA_INSTALL_DIR=/usr/share/ghidra` (default) | spawned inside lifespan, GHIDRA_INSTALL_DIR injected via env |

All three transports are managed by a single `AsyncExitStack` inside `PinnedBackend.__aenter__` so one `aclose()` tears down transport + ClientSession + stdio pipes cleanly on exit.

### tool_map Unified -> Backend Translation (D-07)

| Unified | IDA | BN (placeholder, verify in container) | Ghidra |
|---|---|---|---|
| `decompile` | `decompile` | `decompile` (TODO: grep-verify) | `decomp.function` |
| `list_functions` | `list_funcs` | `list_functions` (TODO: grep-verify) | `function.list` |
| `get_xrefs` | `xrefs_to` | `get_xrefs` (TODO: grep-verify) | `reference.to` |

Three `TODO(Plan 03 container-side validation)` comments flag BN names for installer-time verification (RESEARCH.md Assumption A5). The BN submodule is vendored into the Docker image at `/agent/mcp/binary-ninja-headless-mcp/` but not checked into this repo; Plan 05's smoke test must run `tools/list` against the BN backend and log a warning if any unified tool maps to a missing name.

`translate(unified, backend, args)` raises `KeyError` with a clear message for unknown unified names or unsupported backends. Args are passed through via an identity transform in Phase 2 (`def _identity(args): return dict(args)`); the args_transform slot is reserved for DIS-V2-01 shape normalization.

### Lifespan Wiring (D-09, D-10)

`build_app()` now threads a `PinnedBackend` through the Starlette lifespan:

1. `load_or_generate_token()` (unchanged, Plan 01).
2. `detect_backend()` (unchanged, Plan 01) -> `backend_name` string, OR `None` when `MCP_GATEWAY_SKIP_BACKEND=1` (test mode).
3. `register_all_tools(mcp)` (unchanged, Plan 02) on the module-level FastMCP singleton.
4. Lifespan: `async with PinnedBackend(backend_name) as pinned` -> `session_state.PINNED_BACKEND = pinned` -> `async with mcp.session_manager.run()` -> log ready -> `yield`. On exit (normal or exception) the `try/finally` clears `session_state.PINNED_BACKEND` even if `session_manager.run()` raises.
5. When `backend_name is None`, the lifespan enters `session_manager.run()` WITHOUT `PinnedBackend` so disasm tools return their Plan 02 stub.

### End-to-End Delegation

`disasm.py` tools (from Plan 02) were already calling `session_state.PINNED_BACKEND.call_unified(unified_name, args)` guarded by a `None` check; Plan 03 only needed to make `PINNED_BACKEND` non-None by entering a real `PinnedBackend` in the lifespan. A new integration test (`test_disasm_tool_handler_delegates_to_pinned`) injects a `_Capture` fake and verifies the `decompile` handler in fact calls `call_unified("decompile", {"function": "main", ...})` and returns the fake's response.

### Concurrency (Open Q2 resolved)

`PinnedBackend._call_lock` is an `asyncio.Lock` acquired inside both `call()` and `call_unified()`. `test_call_unified_serializes_concurrent_calls` fires three concurrent `call_unified("decompile", ...)` calls via `asyncio.gather` and verifies all three return successfully -- the lock prevents stream interleaving on the single ClientSession without serializing by starving (each completes).

## Test Counts

| Test module | Count | Focus |
|---|---|---|
| `test_tool_map.py` | 13 | translate() parametrized (6 rows + unknown unified + unknown backend + empty args + supported_unified_tools + all-backends sanity + validate_backend_support ida + validate_backend_support missing) |
| `test_tool_routing.py` (tool_map + PinnedBackend + lifespan) | 15 | 5 class smoke (ValueError unknown, IDA URL literal, BN/Ghidra script paths, SUPPORTED_BACKENDS parity) + 5 async routing (ida decompile, ghidra list_functions, get_xrefs per-backend, concurrent serialization, KeyError) + 2 disasm handler (delegates to PINNED, stub when None) + 3 lifespan (skip_backend, import parity, enter/exit toggle) |
| **Plan 02-03 new total** | **28** | |
| Plan 02-01 + 02-02 carryover | 53 | all still green (regression-clean) |
| **Full mcp-gateway suite** | **81** | all passing, 0.98s runtime |

## Threat Mitigations

| Threat | File | Mitigation |
|---|---|---|
| **T-02-SUBPROC** (RCE via shell injection in stdio spawn) | `backend/client.py` PinnedBackend.__aenter__ | `StdioServerParameters(command="python3", args=[LITERAL_SCRIPT_PATH])`; script paths are module-level constants `BN_SCRIPT` / `GHIDRA_SCRIPT`, NOT user-controlled; zero `shell=True`, zero `os.system`/`os.popen`; argv-only execution via SDK's stdio_client which uses subprocess.Popen without shell |
| **T-02-NET** (IPv6 hang via `localhost`) | `backend/client.py` `IDA_URL` | Literal `"http://127.0.0.1:8745/mcp"` -- zero `localhost` tokens anywhere in the file (grep-verified in acceptance criteria); Pitfall 3 avoided |
| **T-02-SILENT-FALLBACK** (backend crash silently fallback) | `backend/client.py` PinnedBackend.__aenter__ + `app.py` lifespan | __aenter__ wraps the stack entry in try/except, calls `self._stack.aclose()` on failure, then `raise` -- re-raises the original exception up through the lifespan which propagates to Starlette (fail-loud per D-10); the lifespan does NOT try the next-priority backend |
| **T-02-SUBPROC-DEADLOCK** (stdio subprocess stderr hang) | `backend/client.py` | Uses SDK's `stdio_client` which handles stdout/stderr reading in background tasks; Plan 03 does NOT wrap it with additional I/O - Pitfall 4 avoided |
| **T-02-PATHTRAVERSAL** | (Plan 02 owns) | Not weakened: disasm handlers still call resolve_sample() from Plan 02 before passing to call_unified |
| **T-02-AUTH** / **T-02-TOKENLEAK** | (Plan 01 owns) | Not touched by Plan 03 |
| **T-02-UPLOAD** | (Plan 04 scope) | `/upload` still the 501 placeholder from Plan 02 |

## Security Verification

- `grep -c 'localhost' mcp-gateway/src/mcp_gateway/backend/client.py` -> **0**
- `grep -c 'shell=True' mcp-gateway/src/mcp_gateway/backend/client.py` -> **0**
- `grep -c '127.0.0.1' mcp-gateway/src/mcp_gateway/backend/client.py` -> **4** (>= 1 required: URL literal + 3 comment references)
- `ruff check mcp-gateway/src/ mcp-gateway/tests/test_tool_map.py mcp-gateway/tests/test_tool_routing.py` -> clean

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_lifespan_enters_and_exits_pinned_backend failed when run after test_server_init.test_mcp_initialize_succeeds**
- **Found during:** Task 3 GREEN after initial wiring passed in isolation.
- **Issue:** `mcp.server.streamable_http_manager.StreamableHTTPSessionManager.run()` is a one-shot context manager ("This method can only be called once per instance"). Plan 02's `test_mcp_initialize_succeeds` had already entered `run()` on the module-level `_MCP_INSTANCE`, so the lifespan test's second entry raised `RuntimeError: StreamableHTTPSessionManager cannot be restarted`.
- **Fix:** Added `monkeypatch.setattr(app_mod, "_MCP_INSTANCE", None)` at the top of the lifespan test so `build_app()` creates a fresh FastMCP. Documented as a test-isolation pattern in `patterns-established`.
- **Files modified:** `mcp-gateway/tests/test_tool_routing.py`
- **Commit:** `73cda7e` (combined with Task 3 GREEN)

**2. [Rule 1 - Bug] ruff E731 on tool_map._identity lambda**
- **Found during:** Post-Task-3 ruff pass.
- **Fix:** Replaced `_identity: Callable[[dict], dict] = lambda args: dict(args)` with a proper `def _identity(args: dict) -> dict: return dict(args)`. Functionally identical; satisfies ruff E731 "no lambda assigned to name."
- **Files modified:** `mcp-gateway/src/mcp_gateway/backend/tool_map.py`
- **Commit:** `73cda7e` (batched with Task 3)

**3. [Rule 1 - Bug] ruff F401 unused `import os` in test**
- **Found during:** Post-Task-3 ruff pass.
- **Fix:** Removed `import os` from `test_build_app_skips_backend_when_env_flag_set` (the plan snippet included it but monkeypatch.setenv/setenv-only usage doesn't need it).
- **Files modified:** `mcp-gateway/tests/test_tool_routing.py`
- **Commit:** `73cda7e` (batched with Task 3)

### Pre-existing ruff warnings left untouched (scope boundary)

`conftest.py`, `test_auth.py`, `test_cli.py` from Plan 01 have unused `import os` / `pathlib.Path` / `pytest` -- left alone per scope boundary rule. Plan 01's summary already flagged its own files as clean; these likely drifted during Plan 02 tweaks.

## Issues Encountered

- **Worktree base mismatch:** Initial `git merge-base` returned `db828373` (Plan 02's pre-branch point) but the orchestrator expected base `74a014cd4d1c6f75d0d90b790e1e6b015c8263dd` (Plan 02-02 completion). Reset via `git reset --hard 74a014c` to pick up Plan 02's work. Noted per worktree_branch_check protocol.
- **Environment bootstrap (non-code):** Reused the `/tmp/gw-venv` venv from Plan 02 after `pip install -e mcp-gateway/` (the editable install needed re-activation). Ruff installed on demand (not in pyproject.toml dev-deps yet -- that's a Plan 05 cleanup).

## Handoff to Downstream Plans

### To Plan 04 (upload endpoint)

- `/upload` route is still the `_upload_placeholder` returning 501 -- Plan 03 did not touch it.
- `session_state.PINNED_BACKEND` is now reliably non-None during the real-backend lifespan path, so Plan 04's upload handler can assume the gateway has a live disassembler session when it needs to dispatch analysis work.
- `mcp-gateway/src/mcp_gateway/tools/samples.py::UPLOADS_ROOT` (Plan 02) remains the canonical write target.

### To Plan 05 (container integration + smoke)

- Backend subprocess paths expected at `/agent/mcp/binary-ninja-headless-mcp/binary_ninja_headless_mcp.py` and `/agent/mcp/ghidra-headless-mcp/ghidra_headless_mcp.py` -- Plan 05's Dockerfile must ensure these are present in the container image. They are module-level constants `BN_SCRIPT` / `GHIDRA_SCRIPT` in `backend/client.py`.
- **BN tool-name validation:** Plan 05's smoke test should run `tools/list` against the BN backend at container startup and emit a WARN log line for each unified tool whose mapped `bn` name is missing (the three `TODO(Plan 03 container-side validation)` comments in `tool_map.py` point at the rows to validate).
- `GHIDRA_INSTALL_DIR` defaults to `/usr/share/ghidra` if the env var is unset and that directory exists; Plan 05 should document the container's Ghidra install location and wire `configure-agent-mcp.sh`'s existing logic.
- E2E smoke test idea: after container start, hit `POST /mcp` with `tools/call` method invoking `decompile` and verify the response content is non-error.

## Known Stubs

| File | Line | Reason | Resolved by |
|---|---|---|---|
| `src/mcp_gateway/backend/tool_map.py` | 3 x `TODO(Plan 03 container-side validation)` | BN submodule not available on devlaptop; BN tool names set to unified-name fallbacks | Plan 05 container smoke (tools/list against BN backend) |
| `src/mcp_gateway/app.py` | `_upload_placeholder` | Upload handler is Plan 04 scope | Plan 04 |

## Verification Summary

- [x] `pytest mcp-gateway/tests/ -x --no-header -q` -> 81 passed in 0.98s (full suite green, no regression)
- [x] `ruff check mcp-gateway/src/ mcp-gateway/tests/test_tool_map.py mcp-gateway/tests/test_tool_routing.py` -> All checks passed!
- [x] `python -c "from mcp_gateway.app import build_app; from mcp_gateway.backend import PinnedBackend, detect_backend; from mcp_gateway.backend.tool_map import translate; print('imports ok')"` -> `imports ok`
- [x] `grep -c 'localhost' .../client.py` -> 0
- [x] `grep -c 'shell=True' .../client.py` -> 0
- [x] `grep -c '127.0.0.1' .../client.py` -> 4 (>= 1 required)
- [x] `grep -q 'async with PinnedBackend' .../app.py` -> pass
- [x] `grep -q 'session_state.PINNED_BACKEND = pinned' .../app.py` -> pass
- [x] `grep -q 'session_state.PINNED_BACKEND = None' .../app.py` -> pass (try/finally reset)
- [x] `grep -q 'TODO(Plan 03 container-side validation)' .../tool_map.py` -> pass (3 hits)
- [x] D-06 (gateway as MCP client): PinnedBackend wraps ClientSession over real transports; no re-implementation
- [x] D-07 (unified surface): disasm tools expose `decompile`/`list_functions`/`get_xrefs` only; backend-specific names are internal
- [x] D-09 (pinned): backend chosen once at build_app(); single PinnedBackend per lifespan
- [x] D-10 (fail loud): __aenter__ re-raises on init failure; no backend fallback

## Self-Check: PASSED

Verified artifacts exist and commits recorded:

- FOUND: mcp-gateway/src/mcp_gateway/backend/tool_map.py
- FOUND: mcp-gateway/src/mcp_gateway/backend/client.py
- FOUND: mcp-gateway/tests/test_tool_map.py
- FOUND: mcp-gateway/tests/test_tool_routing.py
- FOUND: mcp-gateway/src/mcp_gateway/backend/__init__.py (modified, PinnedBackend re-export)
- FOUND: mcp-gateway/src/mcp_gateway/app.py (modified, lifespan wiring)
- FOUND: mcp-gateway/src/mcp_gateway/tools/disasm.py (modified, docstring update)
- FOUND: a85d11f (test RED Task 1)
- FOUND: 749886c (feat GREEN Task 1)
- FOUND: c449c94 (test RED Task 2)
- FOUND: f196758 (feat GREEN Task 2)
- FOUND: d791c65 (test RED Task 3)
- FOUND: 73cda7e (feat GREEN Task 3 + ruff fixes)

---
*Phase: 02-mcp-gateway*
*Completed: 2026-04-23*
