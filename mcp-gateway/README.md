# mcp-gateway

MARE-MCP-Toolbox gateway: a curated MCP tool surface exposed over Streamable HTTP.

Bridges an in-container disassembler backend (IDA Pro, Binary Ninja, or Ghidra —
auto-detected via priority chain) to external MCP clients (Claude Code host,
mastra.ai, etc.) with bearer-token auth and Origin validation.

## Install

```bash
pip install -e mcp-gateway/
```

## Run

```bash
mcp-gateway --host 127.0.0.1 --port 8080
```

## Tool surface

The gateway exposes a curated MCP tool surface for external agents and merges
in the active backend's native MCP tools at runtime. Agents choose which tools
to call and what arguments to pass, but the gateway-native tools below do not
call an LLM internally. They execute fixed Python/Bash code or forward to the
pinned disassembler backend.

`/upload` is not an MCP tool. It is an authenticated HTTP endpoint that stores
raw sample bytes under `/agent/uploads/<sha256>/<filename>` and returns a
`sample_id` that can be passed to MCP tools as `sample`.

### Mastra starter helper tools

These exist only in `templates/mastra/`; they are not gateway MCP tools.

| Tool | Arguments | Determinism | Under the hood |
|---|---|---|---|
| `mare_status` | none | Mostly deterministic | Calls `/healthz`, then lists gateway MCP tools through `@mastra/mcp`. |
| `mare_triage_sample_path` | `samplePath` | Mostly deterministic | Reads a host-local file, uploads it to `/upload`, calls `run_triage`, then reads `10_reporting_draft.md` with `get_artifact`. |

### Gateway MCP tools

| Tool | Arguments | Determinism | Under the hood |
|---|---|---|---|
| `init_case` | `sample`, optional `new` | Deterministic except existing case-directory state | Runs `init_status_tree.sh`; creates or reuses `/agent/status/<NNN>-<filename>/` and required artifact files. |
| `collect_strings` | `sample`, optional `case_dir` | Mostly deterministic | Runs `collect_strings.sh`; invokes tools such as `file`, `sha256sum`, `md5sum`, `ssdeep`, `die`/`diec`, `rabin2`, `r2`, `strings`, and `floss`; writes profile and raw strings. Includes collection time. |
| `collect_imports` | `sample`, optional `case_dir` | Deterministic for the same tool versions | Runs `collect_imports.sh`; invokes `rabin2` plus format-specific tools such as `objdump`, `readelf`, and `nm`; writes raw imports/symbols. |
| `scan_yara` | `sample`, optional `case_dir` | Deterministic for the same YARA rules/version | Runs `scan_yara.sh`; executes bundled YARA rules and appends match sections to `00_sample_profile.md`. |
| `scan_capa` | `sample`, optional `case_dir` | Mostly deterministic | Runs `scan_capa.sh`; executes `capa -j`, parses JSON, and appends ATT&CK/MBC/capability summaries. Depends on capa rules/version and timeout behavior. |
| `rank_signals` | `case_dir` | Deterministic | Runs `rank_signals.py`; applies fixed regex scoring rules to raw strings/imports, with optional score boosts from `tool-logs/capa.json`. |
| `build_hypothesis` | `case_dir` | Deterministic | Runs `build_hypothesis.py`; generates baseline template hypotheses from ranked artifacts and optional capa evidence. No LLM is called. |
| `update_state` | `case_dir`, `phase` | Deterministic except timestamps and file mtimes | Runs `update_state.py`; updates `INDEX.md` and `CURRENT_STATE.json`. The caller controls the `phase` string. |
| `resolve_case` | `sample` | Deterministic except existing case-directory state | Runs `resolve_case.sh`; returns the highest-numbered case directory for the sample filename. |
| `get_artifact` | `case_dir`, `artifact_name` | Deterministic/read-only | Reads one artifact file from a case directory. `artifact_name` must be a simple filename, not a path. |
| `run_triage` | `sample` | Mostly deterministic | Composite wrapper: `init_case` -> `collect_strings` -> `collect_imports` -> `scan_yara` -> `scan_capa` -> `rank_signals` -> `build_hypothesis` -> `update_state(phase="triage_complete")`. Continue-on-error; returns per-step exit codes. |
| `run_deep_analysis` | `case_dir` | Deterministic except timestamps | Current stub; runs `update_state.py --phase planning_complete`. |
| `generate_report` | `case_dir` | Deterministic/read-only | Reads `10_reporting_draft.md` from the case directory. |
| `list_cases` | none | Deterministic except filesystem state | Lists `/agent/status/<NNN>-...` case directories. |
| `set_active_case` | `case` | Deterministic/session state | Stores a per-session active-case value in gateway memory. |
| `get_active_case` | none | Deterministic/session state | Returns the current per-session active-case value. |
| `list_uploads` | none | Deterministic except filesystem state | Lists stored uploads under `/agent/uploads/<sha256>/`. |
| `get_sample_info` | `sample` | Deterministic/read-only | Resolves a sample id or allowed container path, then returns SHA-256, size, and path. |
| `get_active_backend` | none | Deterministic for the gateway lifetime | Returns the pinned disassembler backend: `ida`, `bn`, `ghidra`, or `none`. |
| `decompile` | `function`, optional `sample` | Backend-dependent | Compatibility wrapper for decompilation when no backend-native `decompile` tool overrides the name. |
| `list_functions` | optional `sample` | Backend-dependent | Compatibility wrapper for function listing. Backend-native IDA uses `list_funcs`; Ghidra uses `function.list`. |
| `get_xrefs` | `function`, optional `sample` | Backend-dependent | Compatibility wrapper for xrefs. Backend-native IDA uses `xrefs_to`; Ghidra uses `reference.to`. |

### Backend-native pass-through

The gateway pins one backend at startup with priority `IDA > Binary Ninja >
Ghidra`. IDA is called over Streamable HTTP at `127.0.0.1:8745/mcp`; Binary
Ninja and Ghidra are launched as MCP stdio subprocesses.

When a backend is active, `tools/list` merges the gateway-native tools above
with the backend's native MCP tool definitions. Backend-native tools keep their
native names and schemas. If a backend-native tool has the same name as a
gateway wrapper, the backend-native definition wins, so IDA's native
`decompile(addr, ...)` schema is what agents see when IDA is active.

### IDA Pro MCP native tools

When IDA is the pinned backend, the gateway passes through the tools reported
by `mrexodia/ida-pro-mcp`. The upstream README documents this native surface:

Context/session:

- `idalib_open(input_path, ...)`
- `idalib_switch(session_id)`
- `idalib_current()`
- `idalib_unbind()`
- `idalib_list()`

Core functions:

- `lookup_funcs(queries)`
- `int_convert(inputs)`
- `list_funcs(queries)`
- `list_globals(queries)`
- `imports(offset, count)`
- `decompile(addr)`
- `disasm(addr)`
- `xrefs_to(addrs)`
- `xrefs_to_field(queries)`
- `callees(addrs)`

Modification:

- `set_comments(items)`
- `patch_asm(items)`
- `declare_type(decls)`
- `define_func(items)`
- `define_code(items)`
- `undefine(items)`

Memory reading:

- `get_bytes(addrs)`
- `get_int(queries)`
- `get_string(addrs)`
- `get_global_value(queries)`

Stack frame:

- `stack_frame(addrs)`
- `declare_stack(items)`
- `delete_stack(items)`

Structures:

- `read_struct(queries)`
- `search_structs(filter)`

Advanced analysis:

- `py_eval(code)`
- `analyze_funcs(addrs)`

Pattern matching and search:

- `find_regex(queries)`
- `find_bytes(patterns, limit=1000, offset=0)`
- `find_insns(sequences, limit=1000, offset=0)`
- `find(type, targets, limit=1000, offset=0)`

Control flow, types, exports, graph:

- `basic_blocks(addrs)`
- `set_type(edits)`
- `infer_types(addrs)`
- `export_funcs(addrs, format)`
- `callgraph(roots, max_depth)`

Batch operations:

- `rename(batch)`
- `patch(patches)`
- `put_int(items)`

Debugger extension tools:

- `dbg_start()`
- `dbg_exit()`
- `dbg_continue()`
- `dbg_run_to(addr)`
- `dbg_step_into()`
- `dbg_step_over()`
- `dbg_bps()`
- `dbg_add_bp(addrs)`
- `dbg_delete_bp(addrs)`
- `dbg_toggle_bp(items)`
- `dbg_regs()`
- `dbg_regs_all()`
- `dbg_regs_remote(tids)`
- `dbg_gpregs()`
- `dbg_gpregs_remote(tids)`
- `dbg_regs_named(names)`
- `dbg_regs_named_remote(tid, names)`
- `dbg_stacktrace()`
- `dbg_read(regions)`
- `dbg_write(regions)`

The debugger tools are extension-gated upstream and appear only when the IDA
MCP server exposes them. The gateway pass-through layer forwards whatever
`tools/list` returns from the active IDA backend.

## Environment variables

- `MCP_GATEWAY_TOKEN` — bearer token (if unset, a 43-char URL-safe token is generated and logged)
- `MCP_GATEWAY_TOKEN_FILE` — path to write the token (default `/agent/.mcp-gateway-token`, mode 0600)
- `MCP_GATEWAY_HOST` — bind host (default `127.0.0.1`)
- `MCP_GATEWAY_PORT` — bind port (default `8080`)
- `MCP_GATEWAY_MAX_UPLOAD_MB` — max upload size in MB (enforced by Plan 04)
- `MCP_GATEWAY_QUIET` — set to `1` to suppress the `[gateway] Bearer token: ...` log line

## Auth

All requests to `/mcp*` and `/upload` require:

    Authorization: Bearer <token>

`/healthz` is intentionally open for health checks.
