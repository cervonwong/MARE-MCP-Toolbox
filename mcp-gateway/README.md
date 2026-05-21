# mcp-gateway

MARE-MCP-Toolbox gateway: a curated MCP tool surface exposed over Streamable HTTP.

Bridges an in-container disassembler backend (IDA Pro, Binary Ninja, or Ghidra —
auto-detected via the priority chain `IDA > BN > Ghidra`) to external MCP
clients (Claude Code host, mastra.ai, etc.) with bearer-token auth and
Origin validation.

## Install

```bash
pip install -e mcp-gateway/
```

## Run

```bash
mcp-gateway --host 127.0.0.1 --port 8080
```

In practice the gateway runs inside the container, started by
`agent-entrypoint.sh` when `MCP_GATEWAY_ENABLED=1` (i.e.
`./run_docker.sh --remote`). See the top-level [`../README.md`](../README.md)
for the host-side launch UX.

## Tool surface

The gateway exposes **54 curated MCP tools** by default. Two env vars add
optional tools:

- `MCP_GATEWAY_DYNAMIC_TOOLS=1` → +7 dynamic-mode tools (total 61)
- `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` → +1 unsafe r2 tool (total 55, or 62 with both)

On top of that, the active disassembler backend's native MCP tools are merged
into `tools/list` under their original names (IDA's ~80, BN's, or Ghidra's).

Agents choose which tools to call and what arguments to pass, but **the
gateway-native tools do not call an LLM internally** — they execute fixed
Python/Bash code or forward to the pinned backend. The AI-controlled part is
deciding what to run next.

`/upload` is not an MCP tool. It is an authenticated HTTP endpoint that stores
raw sample bytes under `/agent/uploads/<sha256>/<filename>` and returns a
`sample_id` that can be passed to MCP tools as `sample`.

### Composite triage (3)

| Tool | Arguments | Determinism | Under the hood |
|---|---|---|---|
| `run_triage` | `sample` | Mostly deterministic | Composite wrapper: `init_case` → `collect_strings` → `collect_imports` → `scan_yara` → `scan_capa` → `rank_signals` → `build_hypothesis` → `update_state(phase="triage_complete")`. Continue-on-error; returns per-step exit codes. |
| `run_deep_analysis` | `case_dir` | Deterministic except timestamps | Current stub; runs `update_state.py --phase planning_complete`. |
| `generate_report` | `case_dir` | Deterministic/read-only | Reads `10_reporting_draft.md` from the case directory. |

### Atomic triage primitives (8)

| Tool | Arguments | Determinism | Under the hood |
|---|---|---|---|
| `init_case` | `sample`, optional `new` | Deterministic except existing case-directory state | `init_status_tree.sh`; creates or reuses `/agent/status/<NNN>-<filename>/` and required artifact files. |
| `collect_strings` | `sample`, optional `case_dir` | Mostly deterministic | `collect_strings.sh`; invokes `file`, `sha256sum`, `md5sum`, `ssdeep`, `die`/`diec`, `rabin2`, `r2`, `strings`, `floss`; writes profile + raw strings. |
| `collect_imports` | `sample`, optional `case_dir` | Deterministic for same tool versions | `collect_imports.sh`; invokes `rabin2` + format-specific tools (`objdump`/`readelf`/`nm`); writes raw imports/symbols. |
| `scan_yara` | `sample`, optional `case_dir` | Deterministic for same rules | `scan_yara.sh`; bundled YARA rules; appends matches to `00_sample_profile.md`. |
| `scan_capa` | `sample`, optional `case_dir` | Mostly deterministic | `scan_capa.sh`; `capa -j`; appends ATT&CK/MBC/capability summaries. |
| `rank_signals` | `case_dir` | Deterministic | `rank_signals.py`; fixed regex scoring with optional capa boosts. |
| `build_hypothesis` | `case_dir` | Deterministic | `build_hypothesis.py`; template hypotheses from ranked artifacts. No LLM. |
| `update_state` | `case_dir`, `phase` | Deterministic except timestamps | `update_state.py`; updates `INDEX.md` and `CURRENT_STATE.json` (caller controls `phase`). |

### Case + sample management (8)

| Tool | Arguments | Determinism | Under the hood |
|---|---|---|---|
| `resolve_case` | `sample` | Deterministic except FS state | `resolve_case.sh`; highest-numbered case dir for the sample filename. |
| `get_artifact` | `case_dir`, `artifact_name` | Deterministic/read-only | Reads one artifact file (simple filename, not a path). |
| `list_cases` | none | Deterministic except FS state | Lists `/agent/status/<NNN>-...` case directories. |
| `set_active_case` | `case` | Per-session state | Stores active-case value in gateway memory. |
| `get_active_case` | none | Per-session state | Returns current active-case value. |
| `list_uploads` | none | Deterministic except FS state | Lists `/agent/uploads/<sha256>/`. |
| `get_sample_info` | `sample` | Deterministic/read-only | Resolves sample id or allowed container path → sha256/size/path. |
| `get_active_backend` | none | Deterministic for gateway lifetime | Returns `ida` / `bn` / `ghidra` / `none`. Clients key on this to choose backend-native tool schemas. |

### Disassembler compat wrappers (3)

These exist so a script can call a stable name regardless of which backend is
pinned. When a backend-native tool has the same name, the backend-native
definition wins; e.g. IDA's native `decompile(addr, ...)` schema overrides
this wrapper when IDA is active.

| Tool | Arguments | Determinism | Under the hood |
|---|---|---|---|
| `decompile` | `function`, optional `sample` | Backend-dependent | Backend pass-through; IDA native uses `decompile(addr)`. |
| `list_functions` | optional `sample` | Backend-dependent | IDA native `list_funcs`; Ghidra `function.list`. |
| `get_xrefs` | `function`, optional `sample` | Backend-dependent | IDA native `xrefs_to`; Ghidra `reference.to`. |

### Constrained shell (1)

| Tool | Arguments | Determinism | Under the hood |
|---|---|---|---|
| `run_shell` | `case_dir`, `cmd`, optional `timeout` | Caller-dependent | Bash one-liner. `argv = setpriv --reuid=mare-shell --regid=mare-shell --clear-groups --no-new-privs --inh-caps=-all -- bash -c <cmd>`. cwd pinned to `case_dir`, env whitelist (no `MCP_GATEWAY_TOKEN`/API keys/AWS creds), hard timeout, auto-capture to `tool-logs/`. Confinement is **posture, not isolation**. |

Returns the 12-key `ReToolRunner` result: `exit_code`, `timed_out`,
`duration_s`, `stdout_head`, `stdout_truncated`, `stdout_bytes_total`,
`stderr_head`, `stderr_truncated`, `stderr_bytes_total`, `log_path`, `argv`,
`slug`.

### Typed static-RE wrappers (11)

All share `(case_dir, sample, …, timeout=None)` shape. Each returns the same
12-key Runner result, optionally augmented with a parsed JSON payload.

| Tool | Notes |
|---|---|
| `run_file` | `file(1)` magic-byte classification. |
| `run_die` | Detect-It-Easy / `diec` packer + compiler detection. |
| `run_xxd` | Bounded hex window: `(offset, length, cols, group, plain)`. |
| `run_readelf` | ELF headers (`-h`/`-l`/`-d`/`-S`/`-s`/`-r`/...); flag-selectable. |
| `run_objdump` | `-d`/`-D`/`-h`/`-x`/...; flag-selectable. |
| `run_nm` | Symbol listing with `--dynamic`/`--defined-only`/`--demangle`. |
| `run_rabin2` | radare2 binary info one-shots (`-I`/`-z`/`-i`/`-E`/...). |
| `run_capstone_disasm` | In-process Capstone disassembly of a byte range; returns typed JSON `instructions[]`. |
| `run_ropper` | ROP gadget search bounded by length + count; returns typed JSON `gadgets[]`. |
| `run_jq` | `jq` filter over a case-dir JSON artifact. |
| `run_yq` | `yq` filter over a case-dir YAML artifact. |

### Artifact-control helpers (5)

| Tool | Arguments | Purpose |
|---|---|---|
| `write_artifact` | `case_dir`, `relpath`, `content`, optional `mode` | Atomic write to a case-confined path. |
| `append_artifact` | `case_dir`, `relpath`, `content` | Atomic append. |
| `list_artifacts` | `case_dir`, optional `subdir` | Flat listing of one case subdir. |
| `get_artifact_tree` | `case_dir` | Depth-2 tree of `EXPANDED_CASE_SUBDIRS`. |
| `get_tool_log` | `case_dir`, `relpath`, optional `offset`/`length` | Range-read a captured tool log without blowing the MCP response cap. |

### Session-scoped r2 (4 + 1 unsafe)

`r2` is spawned WITH `cfg.sandbox=true` baked into argv before the sample is
opened (r2's one-way latch — cannot be disabled mid-session). The
`_DANGEROUS_R2_CMD_RE` regex at the wrapper layer is **UX-level defense in
depth**, not the security boundary.

| Tool | Arguments | Purpose |
|---|---|---|
| `open_r2_session` | `case_dir`, `sample`, optional `init_commands` | Spawn r2; return `session_id`. Init batch always includes `scr.interactive=false; scr.color=0`. |
| `r2_cmd` | `session_id`, `cmd`, optional `format` | Run one r2 command; refuses `!`, `R!`, `#!` shell-escape vectors via regex. |
| `close_r2_session` | `session_id` | Idempotent close. |
| `list_sessions` | none | Enumerate live r2 + gdb sessions. |
| `open_r2_session_unsafe` | (gated by `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1`) `case_dir`, `sample`, optional `init_commands` | Spawn r2 WITHOUT `cfg.sandbox=true`. WARN-logged audit line per open. Shares the combined session cap. |

Idle reaper default 30 min (`MCP_GATEWAY_SESSION_IDLE_S=1800`); session cap
default 8 across r2+gdb (`MCP_GATEWAY_MAX_SESSIONS=8`) enforced atomically
via `asyncio.BoundedSemaphore`. Sessions surviving gateway shutdown are
killed via `os.killpg` in the lifespan unwind.

Sessions are shared across all MCP clients with the same bearer token —
per-`Mcp-Session-Id` keying is deferred to v1.2.

### Background jobs (4)

For tools that exceed the 60 s MCP request cap.

| Tool | Arguments | Purpose |
|---|---|---|
| `start_tool_job` | `tool`, `kwargs`, optional `timeout` | Submit a job registered in `JOB_TOOL_REGISTRY`. Returns `{job_id, status}`. |
| `get_tool_job` | `job_id` | 25-key snapshot: `status`, head-tail of stdout/stderr, exit code if done, `log_path`. Statuses: `queued`/`running`/`done`/`killed_log_cap`/`cancelled`/`error`. |
| `cancel_tool_job` | `job_id` | SIGTERM → SIGKILL after `MCP_GATEWAY_JOB_CANCEL_GRACE_S` (default 10 s). |
| `list_tool_jobs` | optional `state`, `include_internal` | Enumerate jobs by state; `include_internal=True` surfaces the `_sleep_probe`/`_log_burst_probe` smoke specs. |

Registered job specs: `capa`, `unblob`, `binwalk_extract`, `strace`, `ltrace`,
`qemu_user`, plus the internal `_sleep_probe` and `_log_burst_probe`. Each
job's log is capped at `MCP_GATEWAY_MAX_JOB_LOG_MB` (default 256 MB) — over-cap
jobs are killed and marked `status=killed_log_cap`. In-flight cap is 4
(`MCP_GATEWAY_MAX_JOBS_INFLIGHT`); FIFO eviction at 200 completed jobs
(`MCP_GATEWAY_MAX_COMPLETED_JOBS`). All in-flight jobs are killed on
gateway shutdown (in-memory registry).

Client disconnect / request cancellation propagates within ~200 ms via
`asyncio.shield(proc.wait())` + `killpg(SIGKILL)`. Long-running tools report
progress via MCP `Context.report_progress(progress, total, message)` where
the underlying tool emits progress signals (e.g. unblob percent-complete).

### Extraction tier (7)

Carve children out of firmware / packed samples and promote them into new cases
for recursive triage. All extraction output lives at
`case_dir/extracted/<engine>-<UTC>Z-<rand4>/` with a `_mare_meta.json`
sidecar. Symlinks are quarantined recursively (replaced with
`.symlink-target.txt`). Archive-bomb cap default 4 GB
(`MCP_GATEWAY_MAX_EXTRACT_MB=4096`); over-cap creates
`.MARE_EXTRACT_CAP_EXCEEDED` and aborts.

| Tool | Arguments | Notes |
|---|---|---|
| `run_binwalk` | `case_dir`, `sample`, `mode` ∈ `signatures` / `entropy` / `extract` | `extract` dispatches as background job (`binwalk_extract` spec). |
| `run_unblob` | `case_dir`, `sample` | Always background-job dispatched; structured `--report` JSON. |
| `run_upx_test` | `case_dir`, `sample` | Returns `{packed: bool, message: str}`. |
| `run_upx_list` | `case_dir`, `sample` | Typed JSON section listing. |
| `run_upx_unpack` | `case_dir`, `sample` | Output at `case_dir/extracted/upx-<ts>/`. |
| `list_extracted_files` | `case_dir`, optional filters | Engine-agnostic enumeration. |
| `promote_extracted_sample` | `parent_case_dir`, `child_path` | Re-uploads child with sha256 content-addressing; initializes new case dir; returns new `case_dir`. |

### Dynamic Lab Mode (7, env-gated)

Registered iff `MCP_GATEWAY_DYNAMIC_TOOLS=1` at gateway startup. Each
subprocess wraps in per-call `unshare --net --ipc --uts --` (no network,
no host IPC, no shared UTS). All sample inputs are `sample_sha256` hex
only — resolved to absolute paths under `uploads/` or the active case dir.

| Tool | Notes |
|---|---|
| `run_strace` | Background job (`strace` spec). Argv profile: `file_io` / `network` / `process` / etc. |
| `run_ltrace` | Background job (`ltrace` spec). ltrace 0.7.3 is unmaintained — prefer strace. |
| `run_qemu_user` | Background job (`qemu_user` spec). Cross-arch via `qemu-<arch>-static`. |
| `open_gdb_session` | Spawns `gdb --interpreter=mi3 --quiet --nx --nh`. Mandatory lockdown init batch. |
| `gdb_exec` | One MI command; 49-prefix allowlist + 15-vector deny regex (`python`, `pi`, `source`, `shell`, `!`, `-target-select`, `attach`, …). |
| `close_gdb_session` | Idempotent. |
| `get_dynamic_capabilities` | `ptrace_scope`, `binfmt_misc`, qemu arches, netns feasibility. Probed at lifespan startup with INFO/WARN log lines. |

Follow-fork reaping: setsid grandchildren that escape the runner's process
group are killed via `/proc/<pid>/task/*/children` recursive scan
(`MCP_GATEWAY_DYN_REAP_DEPTH=8`) after each job terminates.

### Mastra starter helper tools

These exist only in `templates/mastra/`; they are not gateway MCP tools.

| Tool | Arguments | Determinism | Under the hood |
|---|---|---|---|
| `mare_status` | none | Mostly deterministic | Calls `/healthz`, then lists gateway MCP tools through `@mastra/mcp`. |
| `mare_triage_sample_path` | `samplePath` | Mostly deterministic | Reads a host-local file, uploads it to `/upload`, calls `run_triage`, then reads `10_reporting_draft.md` with `get_artifact`. |

## Backend-native pass-through

The gateway pins one backend at startup with priority `IDA > Binary Ninja >
Ghidra`. IDA is called over Streamable HTTP at `127.0.0.1:8745/mcp`; Binary
Ninja and Ghidra are launched as MCP stdio subprocesses.

When a backend is active, `tools/list` merges the gateway-native tools above
with the backend's native MCP tool definitions. Backend-native tools keep their
native names and schemas. **If a backend-native tool has the same name as a
gateway wrapper, the backend-native definition wins** (so IDA's native
`decompile(addr, ...)` schema is what agents see when IDA is active).

A `collision_check` step in `app.py::lifespan` runs AFTER the backend tools
are merged. If a STATIC wrapper name collides with a backend-pass-through
name in an unexpected way, the gateway hard-fails at startup
(`SystemExit(78)`).

### IDA Pro MCP native tools

When IDA is the pinned backend, the gateway passes through the tools reported
by `mrexodia/ida-pro-mcp`. Upstream documents the full native surface; below
is a current snapshot.

Context/session:

- `idalib_open(input_path, ...)`, `idalib_switch(session_id)`, `idalib_current()`, `idalib_unbind()`, `idalib_list()`

Core functions:

- `lookup_funcs(queries)`, `int_convert(inputs)`, `list_funcs(queries)`, `list_globals(queries)`, `imports(offset, count)`, `decompile(addr)`, `disasm(addr)`, `xrefs_to(addrs)`, `xrefs_to_field(queries)`, `callees(addrs)`

Modification:

- `set_comments(items)`, `patch_asm(items)`, `declare_type(decls)`, `define_func(items)`, `define_code(items)`, `undefine(items)`

Memory reading:

- `get_bytes(addrs)`, `get_int(queries)`, `get_string(addrs)`, `get_global_value(queries)`

Stack frame:

- `stack_frame(addrs)`, `declare_stack(items)`, `delete_stack(items)`

Structures:

- `read_struct(queries)`, `search_structs(filter)`

Advanced analysis:

- `py_eval(code)`, `analyze_funcs(addrs)`

Pattern matching and search:

- `find_regex(queries)`, `find_bytes(patterns, limit=1000, offset=0)`, `find_insns(sequences, limit=1000, offset=0)`, `find(type, targets, limit=1000, offset=0)`

Control flow, types, exports, graph:

- `basic_blocks(addrs)`, `set_type(edits)`, `infer_types(addrs)`, `export_funcs(addrs, format)`, `callgraph(roots, max_depth)`

Batch operations:

- `rename(batch)`, `patch(patches)`, `put_int(items)`

Debugger extension tools (gated upstream — appear only when the IDA MCP server exposes them):

- `dbg_start()`, `dbg_exit()`, `dbg_continue()`, `dbg_run_to(addr)`, `dbg_step_into()`, `dbg_step_over()`
- `dbg_bps()`, `dbg_add_bp(addrs)`, `dbg_delete_bp(addrs)`, `dbg_toggle_bp(items)`
- `dbg_regs()`, `dbg_regs_all()`, `dbg_regs_remote(tids)`, `dbg_gpregs()`, `dbg_gpregs_remote(tids)`, `dbg_regs_named(names)`, `dbg_regs_named_remote(tid, names)`
- `dbg_stacktrace()`, `dbg_read(regions)`, `dbg_write(regions)`

The gateway pass-through layer forwards whatever `tools/list` returns from
the active IDA backend.

## /upload contract

```
POST /upload
Authorization: Bearer <token>
Content-Type: application/octet-stream  # NOT multipart
X-Filename: <filename>                  # optional; defaults from URL or content-hash

(raw bytes)
```

- Streaming; no buffering of the full payload in memory.
- Default cap 1 GB (`MCP_GATEWAY_MAX_UPLOAD_MB`).
- Stored at `/agent/uploads/<sha256>/<filename>` — sha256 content-addressing dedups by content.
- Returns `{"sha256": "...", "filename": "...", "size": int, "stored_path": "/agent/uploads/<sha256>/<filename>", "sample_id": "<sha256>"}`.
- Rejects multipart content (use raw `application/octet-stream`).
- Rejects path-traversal in `X-Filename`.

## MCP Resources

`resources/list` enumerates files under `/agent/status/` two levels deep
(case root + the canonical case subdirs from `EXPANDED_CASE_SUBDIRS`:
`tool-logs/`, `extracted/`, `hex/`, `rop/`, `dynamic/`, `qemu/`,
`disassembly/`, `decompilation/`, `xrefs/`, `r2-sessions/`).

URI scheme: `mare://cases/<case>/<relpath>`. MIME types are sniffed per file
(`application/json`, `text/markdown`, `text/plain`).

Uploads are NOT exposed as resources — use `list_uploads()` and
`get_sample_info()` MCP tool calls.

## Environment variables

Core:

| Variable | Default | Purpose |
|---|---|---|
| `MCP_GATEWAY_TOKEN` | generated | Pin bearer token; otherwise a 43-char URL-safe token is generated + logged. |
| `MCP_GATEWAY_TOKEN_FILE` | `/agent/.mcp-gateway-token` | Path the token is written to (mode 0600). |
| `MCP_GATEWAY_HOST` | `127.0.0.1` | Bind host. |
| `MCP_GATEWAY_PORT` | `8080` | Bind port. |
| `MCP_GATEWAY_QUIET` | unset | `1` suppresses the bearer-token log line. |
| `MCP_GATEWAY_MAX_UPLOAD_MB` | `1024` | `/upload` size cap. |

Feature gates:

| Variable | Default | Purpose |
|---|---|---|
| `MCP_GATEWAY_DYNAMIC_TOOLS` | unset | `1` registers the 7 dynamic-mode tools. |
| `MCP_GATEWAY_R2_UNSAFE_ALLOWED` | unset | `1` registers `open_r2_session_unsafe`. |

Runner / tool-call shape (`runner.py`):

| Variable | Default |
|---|--:|
| `MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S` | `55.0` |
| `MCP_GATEWAY_RUNNER_MAX_LOG_MB` | `256` |
| `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB` | `256` |
| `MCP_GATEWAY_RUNNER_STDERR_HEAD_KB` | `64` |
| `MCP_GATEWAY_RUN_SHELL_MAX_CMD_BYTES` | `32768` |

Sessions (`sessions/_base.py`):

| Variable | Default |
|---|--:|
| `MCP_GATEWAY_MAX_SESSIONS` | `8` (combined r2 + gdb) |
| `MCP_GATEWAY_SESSION_IDLE_S` | `1800.0` |
| `MCP_GATEWAY_R2_CMD_TIMEOUT_S` | `30.0` |
| `MCP_GATEWAY_REAPER_INTERVAL_S` | `60.0` |
| `MCP_GATEWAY_SESSION_OPEN_TIMEOUT_S` | `15.0` |

Background jobs (`jobs.py`):

| Variable | Default |
|---|--:|
| `MCP_GATEWAY_MAX_JOBS_INFLIGHT` | `4` |
| `MCP_GATEWAY_MAX_COMPLETED_JOBS` | `200` |
| `MCP_GATEWAY_MAX_JOB_LOG_MB` | `256` |
| `MCP_GATEWAY_JOB_TIMEOUT_S` | `3600.0` |
| `MCP_GATEWAY_JOB_MAX_TIMEOUT_S` | `86400.0` |
| `MCP_GATEWAY_JOB_CANCEL_GRACE_S` | `10.0` |
| `MCP_GATEWAY_JOB_STDOUT_HEAD_KB` / `_TAIL_KB` | `32` / `32` |
| `MCP_GATEWAY_JOB_STDERR_HEAD_KB` / `_TAIL_KB` | `32` / `32` |

Extraction (`extraction.py`):

| Variable | Default |
|---|--:|
| `MCP_GATEWAY_MAX_EXTRACT_MB` | `4096` |
| `MCP_GATEWAY_EXTRACT_MONITOR_INTERVAL_S` | `5.0` |
| `MCP_GATEWAY_LIST_EXTRACT_FILES_PER_EXTRACTION` | `5000` |

Dynamic (`dynamic.py`):

| Variable | Default |
|---|--:|
| `MCP_GATEWAY_DYN_REAP_DEPTH` | `8` |
| `MCP_GATEWAY_DYN_PROBE_TIMEOUT_S` | `3.0` |

## Auth

All requests to `/mcp*` and `/upload` require:

    Authorization: Bearer <token>

An Origin middleware rejects cross-origin requests that don't match the bind
host (DNS-rebind protection). `/healthz` is intentionally open for health
checks.

## Internals

| File | Responsibility |
|---|---|
| `app.py` | FastMCP server, lifespan (PinnedBackend → SessionRegistry → BackgroundJobRegistry → `collision_check`), middleware, /upload + /healthz routes |
| `runner.py` | `ReToolRunner` chokepoint (argv-only, killpg, chunked drain, log capture, 12-key result) |
| `artifacts_io.py` | `confine_to`, `ensure_subdir`, `tool_log_path`, `ensure_mare_shell_access`, `EXPANDED_CASE_SUBDIRS` |
| `sessions/_base.py` | `BaseSession`, kind-aware `SessionRegistry`, atomic `BoundedSemaphore` cap, reaper |
| `sessions/r2.py` | r2 driver, `_DANGEROUS_R2_CMD_RE` (UX-layer defense in depth) |
| `sessions/gdb.py` | gdb-MI3 driver, MI prefix allowlist, deny regex |
| `jobs.py` | `BackgroundJobRegistry`, `JobToolSpec`, `JOB_TOOL_REGISTRY`, log-cap, FIFO eviction, atomic semaphore |
| `extraction.py` | extraction-dir mint, sidecar, symlink quarantine, archive-bomb monitor, atomic re-upload |
| `dynamic.py` | capability probes, `wrap_netns`, argv profiles + builders, `reap_followfork_strays` |
| `uploads.py` | streaming `POST /upload`, sha256 content-addressing |
| `auth.py` | bearer token, 0600 file, Origin middleware |
| `backend/` | `PinnedBackend` ClientSession; routes disasm tools to IDA (HTTP) / BN / Ghidra (stdio) |
| `tools/__init__.py` | `register_all_tools(mcp)` — registration order; env-gated dynamic + unsafe r2 |
| `tools/*.py` | One module per family: `cases`, `artifacts`, `workflows`, `disasm`, `resources`, `re_artifacts`, `re_static`, `shell`, `r2_sessions`, `jobs`, `extract`, `dynamic`, `backend_passthrough`, `collision_check` |

## Tests

```bash
cd mcp-gateway
uv run pytest -m 'not slow'
```

`slow`-marked tests cover the 100 MB urandom OOM, capa/unblob/binwalk live
runs, and the gdb/strace/qemu integration cases — gate to in-container
runs. The full non-slow suite is ≈ 600 tests. See
[`../.planning/v1.1-MILESTONE-AUDIT.md`](../.planning/v1.1-MILESTONE-AUDIT.md)
for current pass/fail status and outstanding human UAT items.
