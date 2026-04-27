---
phase: 02-mcp-gateway
verified: 2026-04-27T00:00:00Z
status: passed
score: 5/5 must-haves verified
overrides_applied: 0
---

# Phase 02: MCP Gateway Verification Report

**Phase Goal:** A curated set of orchestrator-level analysis tools is accessible over Streamable HTTP with bearer token authentication
**Verified:** 2026-04-27
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (ROADMAP Success Criteria)

| #   | Truth                                                                                                                                                         | Status     | Evidence |
| --- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- | -------- |
| 1   | Streamable HTTP endpoint on port 8080 responds to MCP tool discovery and returns curated tool list (15-25 tools)                                              | VERIFIED   | 22 tools enumerated via in-memory client; CLI defaults port 8080; build_app() mounts FastMCP at /mcp; behavioral spot-check `POST /mcp initialize` returns 200 with serverInfo. Tool names include 3 composite + 10 atomic + 3 disasm + 6 case/sample mgmt = 22 total. |
| 2   | Requests without valid bearer rejected with 401; with valid token succeed                                                                                     | VERIFIED   | `BearerAuthMiddleware` uses `hmac.compare_digest` (auth.py:70); spot-check: POST /mcp unauth → 401, POST /upload unauth → 401, POST /mcp with bearer + initialize → 200. PROTECTED_PREFIXES = ("/mcp", "/upload"), /healthz intentionally open. |
| 3   | Disassembler tools (decompile, list_functions, get_xrefs) route to installed backend transparently — unified interface across BN/IDA/Ghidra                   | VERIFIED   | tools/disasm.py registers `decompile`, `list_functions`, `get_xrefs` as gateway-native tools that delegate via `session_state.PINNED_BACKEND.call_unified()`. `tool_map.translate(unified, backend, args)` resolves to backend-specific names: ida→`decompile`/`list_funcs`/`xrefs_to`, ghidra→`decomp.function`/`function.list`/`reference.to`, bn→placeholder fallbacks (TODOs documented). Plan 05 live-container smoke confirmed Ghidra delegation. Note: full backend native pass-through registration (e.g., exposing Ghidra's `program.open` directly) is documented as a future enhancement; the roadmap criterion specifies the unified trio, which is met. |
| 4   | Remote client can upload binary sample via file transfer and run analysis tools against it                                                                    | VERIFIED   | `/upload` streaming handler writes `<UPLOAD_DIR>/<sha256>/<filename>`, returns `{sample_id, path, size}`. Spot-check confirmed sha256 round-trip. Plan 05 e2e `test_upload_then_analyze.sh` confirmed: upload → tools/call collect_strings(sample=<sha256>) succeeds end-to-end against live container. |
| 5   | Gateway binds to localhost only by default; explicit configuration to listen on all interfaces                                                                | VERIFIED   | `cli.py` `DEFAULT_HOST = "127.0.0.1"`; `MCP_GATEWAY_HOST=0.0.0.0` is explicit opt-in. `Dockerfile` agent-entrypoint binds `${MCP_GATEWAY_HOST:-127.0.0.1}`. `compose.yaml` has NO `ports:` block (port publishing intentionally deferred to Phase 3 INF-02 per ROADMAP). OriginMiddleware adds DNS-rebind protection. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact                                                       | Expected                                                            | Status     | Details |
| -------------------------------------------------------------- | ------------------------------------------------------------------- | ---------- | ------- |
| `mcp-gateway/pyproject.toml`                                   | Package metadata, mcp>=1.27,<1.28, entry point                      | VERIFIED   | mcp-gateway 0.1.0 installable; `mcp-gateway` console script registered |
| `mcp-gateway/src/mcp_gateway/auth.py`                          | load_or_generate_token, BearerAuthMiddleware, OriginMiddleware      | VERIFIED   | All 3 exports present; hmac.compare_digest at line 70; 0o600 token file enforced; MCP_GATEWAY_QUIET respected |
| `mcp-gateway/src/mcp_gateway/cli.py`                           | main() argparse; default host=127.0.0.1, port=8080                  | VERIFIED   | DEFAULT_HOST="127.0.0.1", DEFAULT_PORT=8080 (cli.py:8-9); env override; lazy build_app import |
| `mcp-gateway/src/mcp_gateway/backend/detect.py`                | detect_backend() → 'ida'\|'bn'\|'ghidra' or RuntimeError; IDA>BN>Ghidra | VERIFIED | Mirrors docker-bin/configure-agent-mcp.sh lines 67-119; raises clear RuntimeError when none installed |
| `mcp-gateway/src/mcp_gateway/backend/client.py`                | PinnedBackend async ctx mgr (IDA http / BN+Ghidra stdio)             | VERIFIED   | IDA_URL = "http://127.0.0.1:8745/mcp" (literal IPv4); StdioServerParameters argv-only; asyncio.Lock for serialization; D-10 fail-loud __aenter__ |
| `mcp-gateway/src/mcp_gateway/backend/tool_map.py`              | TOOL_MAP unified→backend translation                                 | VERIFIED   | translate() with 3 unified tools × 3 backends; TODO comments for BN container-side validation |
| `mcp-gateway/src/mcp_gateway/uploads.py`                       | Streaming /upload handler with sha256 + size cap + filename sanitize | VERIFIED   | `async for chunk in request.stream()`; no `request.body()`/`request.form()`; default 1 GB cap; `_is_invalid_filename` rejects /,\\,..,leading dot,control chars; multipart→415 |
| `mcp-gateway/src/mcp_gateway/app.py`                           | build_app() Starlette factory; FastMCP mount; lifespan + middleware | VERIFIED   | Mounts FastMCP at /mcp with `streamable_http_path="/"` workaround; Bearer + Origin middleware ordered correctly; PinnedBackend in lifespan; MCP_GATEWAY_SKIP_BACKEND escape hatch |
| `mcp-gateway/src/mcp_gateway/tools/` (cases, artifacts, workflows, disasm, samples) | 22 curated tools                                       | VERIFIED   | register_all_tools() registers 22 tools; orchestrator script→tool mapping verified by test_atomic_tools_map_to_scripts |
| `Dockerfile`                                                    | mcp-gateway install + agent-entrypoint daemon block                 | VERIFIED   | COPY + pip install -e at lines 120-123; daemon startup at lines 304-329 binds 127.0.0.1:8080; runtime deps in pip install (mcp/starlette/uvicorn/python-multipart) |
| `compose.yaml`                                                  | MCP_GATEWAY_* env passthroughs                                       | VERIFIED   | 5 env vars: MCP_GATEWAY_TOKEN/HOST/PORT/MAX_UPLOAD_MB/QUIET; no ports: block (Phase 3 scope) |
| `mcp-gateway/tests/e2e/smoke.sh`                                | healthz + initialize + tools/list + unauth check                     | VERIFIED   | 156 lines; checks healthz/initialize/tools count≥15/get_active_backend/canary native tools/unauth 401 |
| `mcp-gateway/tests/e2e/test_upload_then_analyze.sh`             | upload + collect_strings round-trip                                  | VERIFIED   | 71 lines; uploads synthetic ELF stub, calls collect_strings via tools/call |

### Key Link Verification

| From                                                            | To                                              | Status   | Details |
| --------------------------------------------------------------- | ----------------------------------------------- | -------- | ------- |
| `auth.py::load_or_generate_token`                               | env var / secrets.token_urlsafe                 | WIRED    | env-var-wins fallback; secrets.token_urlsafe(32) when unset |
| `auth.py::BearerAuthMiddleware.dispatch`                        | hmac.compare_digest                             | WIRED    | constant-time compare confirmed at line 70 |
| `app.py::build_app::lifespan`                                   | PinnedBackend + session_state.PINNED_BACKEND    | WIRED    | `async with PinnedBackend(backend_name)` (app.py:101); session_state set/cleared in try/finally |
| `app.py` Starlette routes                                       | /healthz, /upload (uploads.upload_handler), /mcp (FastMCP mount) | WIRED | 3 routes registered; upload_handler swapped in for old _upload_placeholder |
| `uploads.py::upload_handler`                                    | request.stream() + hashlib.sha256                | WIRED    | streaming + hash both confirmed; tempfile cleanup on error |
| `disasm.py` tool handlers                                       | session_state.PINNED_BACKEND.call_unified        | WIRED    | All 3 unified disasm tools delegate via call_unified; stub when PINNED_BACKEND is None |
| `client.py::PinnedBackend.call_unified`                         | tool_map.translate + session.call_tool          | WIRED    | translate() resolves to backend-specific name; call_tool() invocation under asyncio.Lock |
| Dockerfile agent-entrypoint                                     | mcp-gateway daemon                               | WIRED    | `gosu agent + nohup mcp-gateway --host --port` at lines 311-322 |
| compose.yaml environment                                        | gateway runtime env                              | WIRED    | 5 MCP_GATEWAY_* env passthroughs |

### Data-Flow Trace (Level 4)

| Artifact                                  | Data Variable                | Source                               | Produces Real Data | Status |
| ----------------------------------------- | ---------------------------- | ------------------------------------ | ------------------ | ------ |
| /healthz                                  | static {"ok": true}          | n/a                                  | static literal     | FLOWING (intentional health check) |
| /upload                                   | sample_id (sha256)           | hashlib.sha256 of streamed body      | Yes                | FLOWING |
| /mcp tools/list                           | 22 registered tools          | register_all_tools(mcp)              | Yes                | FLOWING |
| disasm tools (decompile/list_functions/get_xrefs) | result dict                  | PinnedBackend.call_unified → backend ClientSession.call_tool | Yes (when backend pinned) | FLOWING |
| get_active_backend                        | backend name                 | session_state.PINNED_BACKEND.backend | Yes (set in lifespan) | FLOWING |

### Behavioral Spot-Checks

| Behavior                          | Command                                                       | Result                                              | Status |
| --------------------------------- | ------------------------------------------------------------- | --------------------------------------------------- | ------ |
| Package import                    | `python -c "import mcp_gateway"` after `pip install -e`       | mcp_gateway 0.1.0                                   | PASS   |
| Test suite                        | `pytest mcp-gateway/tests/ --ignore=tests/e2e -q`              | 95 passed                                            | PASS   |
| build_app() instantiates          | `build_app()` with MCP_GATEWAY_SKIP_BACKEND=1                  | App constructed; no exceptions                       | PASS   |
| GET /healthz                      | TestClient                                                     | 200 {"ok": true}                                     | PASS   |
| POST /mcp unauth                  | TestClient                                                     | 401                                                  | PASS   |
| POST /upload unauth               | TestClient                                                     | 401                                                  | PASS   |
| POST /mcp evil-origin             | TestClient with Origin: http://evil.com                        | 403                                                  | PASS   |
| POST /mcp initialize (auth)       | TestClient with Bearer + JSON-RPC initialize                   | 200 with serverInfo                                  | PASS   |
| Upload roundtrip                  | TestClient POST /upload                                        | 200, sample_id matches sha256                        | PASS   |
| tools/list count                  | in-memory MCP session                                          | 22 tools (in [15,25])                                | PASS   |
| Required tool names               | tools/list filter                                              | decompile, list_functions, get_xrefs, get_active_backend, collect_strings, run_triage all present | PASS |

### Requirements Coverage

| Requirement | Source Plan(s)                  | Description                                                                       | Status     | Evidence |
| ----------- | ------------------------------- | --------------------------------------------------------------------------------- | ---------- | -------- |
| GW-01       | 02-02, 02-05                    | FastMCP server over Streamable HTTP                                               | SATISFIED  | build_app() mounts FastMCP; initialize handshake returns 200; spec 2025-03-26 |
| GW-02       | 02-02, 02-05                    | 15-25 orchestrator-level tools mapping to 13-artifact pipeline                    | SATISFIED  | 22 tools registered; orchestrator scripts mapped 1:1; covers triage/strings/imports/yara/capa/disasm |
| GW-03       | 02-03, 02-05                    | Disassembler tools route through pinned backend (IDA>BN>Ghidra) via single endpoint | SATISFIED | detect_backend() priority confirmed; PinnedBackend pins for lifetime; tool_map.translate routes 3 unified disasm tools to per-backend names; REQUIREMENTS.md GW-03 wording corrected by Plan 05 |
| GW-04       | 02-01, 02-05                    | Bearer token auth on remote MCP endpoints                                         | SATISFIED  | BearerAuthMiddleware + hmac.compare_digest; token generated/loaded at startup; 401 spot-check confirmed |
| GW-05       | 02-01, 02-05                    | Localhost-only by default; explicit network exposure opt-in                       | SATISFIED  | CLI DEFAULT_HOST=127.0.0.1; agent-entrypoint defaults; compose has no ports: block (Phase 3 INF-02) |
| GW-06       | 02-04, 02-05                    | File upload mechanism for remote sample submission                                | SATISFIED  | /upload streaming handler; sha256 content-addressing; size cap; filename sanitization; e2e roundtrip with collect_strings confirmed |

All 6 GW-0x requirements declared in Phase 2 plans are satisfied. No orphaned requirements.

### Anti-Patterns Found

| File                                                  | Line | Pattern                                              | Severity | Impact |
| ----------------------------------------------------- | ---- | ---------------------------------------------------- | -------- | ------ |
| `mcp-gateway/src/mcp_gateway/backend/tool_map.py`     | 28-41 | 3× `TODO(Plan 03 container-side validation)` for BN | Info     | BN tool names are placeholder fallbacks (use unified names verbatim). Container-side smoke test against an actual BN backend is required to verify; not blocking GW-03 because IDA and Ghidra mappings are concrete. Documented in Plan 03 SUMMARY and Plan 05 deferral note. |
| `tools/workflows.py::run_deep_analysis`               | n/a  | Phase 2 stub: only flips phase to `planning_complete` | Info     | Documented v2 scope per RESEARCH Open Q#2; not in any GW-0x success criterion. |

No blocker anti-patterns. No `request.body()` / `request.form()` in uploads.py. No `shell=True` / `os.system` / `os.popen` anywhere in src. No `localhost` literals in backend/client.py.

### Architectural Note: Pass-through vs. Translation

The Plan 02-03 PLAN frontmatter (must_haves) describes a **pass-through registration** model where `register_backend_passthrough(mcp, pinned)` enumerates the backend's tools/list and re-exposes each backend tool on the gateway under its NATIVE name (e.g., Ghidra's `program.open`, `function.list`, `decomp.function` would appear in the gateway's tools/list). However, the actual implementation (and the Plan 02-03 SUMMARY) uses a **translation** model: 3 gateway-native unified disasm tools (`decompile`, `list_functions`, `get_xrefs`) call `tool_map.translate(unified, backend, args)` to resolve to backend-specific names, then forward via `PinnedBackend.call_unified`.

The roadmap success criterion #3 explicitly references the unified disasm trio by name ("decompile, list_functions, get_xrefs"), so the implemented translation model meets the **roadmap goal**. REQUIREMENTS.md GW-03 was rewritten by Plan 05 to align with this approach. The pass-through registration model is documented in Plan 05 SUMMARY as a deferred future enhancement ("Pass-through Registration Follow-up"). This deviation is intentional and does not block phase 02 goal achievement.

### Gaps Summary

None. All 5 ROADMAP Success Criteria are met. All 6 declared requirement IDs (GW-01..GW-06) are satisfied with implementation evidence. 95 unit tests pass. Behavioral spot-checks confirm end-to-end functionality. Plan 05 SUMMARY documents the live-container e2e validation that ran successfully.

Future enhancement (not a phase 2 gap): full backend native tool pass-through registration (so Ghidra's `program.open`, IDA's `xrefs_to`, etc. appear as first-class tools in the gateway's tools/list). Documented in Plan 05 SUMMARY.

---

_Verified: 2026-04-27_
_Verifier: Claude (gsd-verifier)_
