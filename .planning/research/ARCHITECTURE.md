# Architecture Patterns — v1.1 Remote RE Tool Expansion

**Domain:** MCP gateway extension — argv-only subprocess runner, typed RE-tool wrappers, persistent r2/gdb sessions, background-job registry, env-gated dynamic-mode surface
**Researched:** 2026-05-12
**Scope:** How v1.1's new tool surface integrates with the existing FastMCP gateway (`mcp-gateway/src/mcp_gateway/`) without duplicating or breaking the shipped v1.0 architecture (PinnedBackend, upload streaming, bearer auth, Origin middleware, 22 curated tools).

---

## 0. Existing Architecture — What v1.1 Must Not Break

```
mcp-gateway/src/mcp_gateway/
├── __main__.py / cli.py        # uvicorn entry — invokes app.build_app()
├── app.py                       # Starlette factory + FastMCP wiring + lifespan
├── auth.py                      # BearerAuthMiddleware + OriginMiddleware
├── uploads.py                   # POST /upload streaming handler
├── session_state.py             # module-level PINNED_BACKEND, ACTIVE_CASE
├── subprocess_runner.py         # run_script(argv, cwd, timeout, env) — orchestrator scripts
├── backend/
│   ├── client.py                # PinnedBackend (ClientSession to IDA/BN/Ghidra)
│   ├── detect.py
│   └── tool_map.py
└── tools/                       # 22 curated tools + resources
    ├── __init__.py              # register_all_tools(mcp) — single registration seam
    ├── cases.py                 # list_cases / set_active_case / list_uploads / ...
    ├── samples.py               # resolve_sample (sha256 → path, prefix allowlist)
    ├── case_dirs.py             # resolve_case_dir (case-dir traversal guard)
    ├── artifacts.py             # 10 atomic pipeline tools (init_case, collect_strings, ...)
    ├── workflows.py             # run_triage / run_deep_analysis / generate_report
    ├── disasm.py                # decompile / list_functions / get_xrefs (PinnedBackend)
    ├── backend_passthrough.py   # tools/list + tools/call merge handler
    └── resources.py             # mare://cases/<case>/<artifact>
```

**Critical existing invariants v1.1 MUST preserve:**

| Invariant | Source | v1.1 Implication |
|-----------|--------|------------------|
| All subprocess execution is argv-only (T-02-SUBPROC) | `subprocess_runner.run_script` uses `asyncio.create_subprocess_exec`, never shell=True | New `ReToolRunner` and `run_shell` MUST also use `create_subprocess_exec`. `run_shell` becomes `exec("bash", "-lc", cmd)` — the user's bash string is a single argv element, NOT shell-interpolated by Python |
| `start_new_session=True` + process-group SIGKILL on timeout | `subprocess_runner.py:58, 64` | v1.1 keeps process-group semantics. Background-job cancel uses `os.killpg(pid, SIG…)` on the same PGID |
| Path-traversal rejection via canonicalize + prefix allowlist | `samples._resolve_allowed`, `case_dirs.resolve_case_dir` | All new tools (typed wrappers, `run_shell`, extraction, dynamic) MUST run through `resolve_case_dir` for `cwd`. New artifact subdirs (`tool-logs/`, `extracted/`, etc.) MUST be confined under the case dir's realpath |
| Single tool-registration seam: `tools/__init__.py::register_all_tools(mcp)` | Called once in `app.py:82` | v1.1 adds new sub-modules; `register_all_tools` is the only place that learns about them. Dynamic-mode gate lives here (not scattered through every `register()`) |
| `MCP_GATEWAY_ENABLED` Dockerfile guard for byte-identical local mode | Phase 3 dual-mode design | v1.1's dynamic-mode gate is a *separate* env gate (`MCP_GATEWAY_DYNAMIC_TOOLS`). Both gates must compose; default-off dynamic in `--remote` mode is required |
| Lifespan-managed long-lived resources | `app.py::lifespan` holds PinnedBackend across requests | r2/gdb session managers are long-lived too, but **per-session** (keyed by session_id), not gateway-singleton. They live in module-level registries with a lifespan-managed reaper task |
| F-1 image-hash bug | `run_docker.sh` content-hash misses `mcp-gateway/src/` | v1.1 must extend the hash; otherwise every v1.1 phase ships repo edits that the container never sees |

---

## 1. Recommended v1.1 Architecture

### 1.1 Component Map (new files + modified files)

```
mcp-gateway/src/mcp_gateway/
│
├── runner.py                    # NEW — ReToolRunner (single execution path)
├── jobs.py                      # NEW — BackgroundJobRegistry (asyncio.Task table)
├── sessions/                    # NEW — persistent subprocess sessions
│   ├── __init__.py              # SessionRegistry base + idle reaper
│   ├── r2.py                    # R2Session (radare2 -q0 stdin/stdout pump)
│   └── gdb.py                   # GdbSession (gdb --interpreter=mi3 pump)
├── artifacts_io.py              # NEW — case-dir subdir helpers (tool-logs/, extracted/, ...)
│
├── tools/
│   ├── __init__.py              # MODIFIED — dynamic-mode gate + new module registration
│   ├── shell.py                 # NEW — run_shell (single new tool, reuses ReToolRunner)
│   ├── re_static.py             # NEW — run_binwalk / run_xxd / run_readelf / run_objdump /
│   │                            #       run_nm / run_rabin2 / run_capstone_disasm /
│   │                            #       run_ropper / run_jq / run_yq / run_file / run_die
│   ├── re_sessions.py           # NEW — open_r2_session / r2_cmd / close_r2_session
│   ├── re_extract.py            # NEW — run_unblob / run_binwalk_extract / run_upx_test /
│   │                            #       run_upx_unpack / extract_embedded_files /
│   │                            #       list_extracted_files / promote_extracted_sample
│   ├── re_dynamic.py            # NEW — run_strace / run_ltrace / run_qemu_user +
│   │                            #       open_gdb_session / gdb_exec / close_gdb_session
│   │                            #       (this module's register() is the gated one)
│   ├── re_jobs.py               # NEW — start_tool_job / get_tool_job / cancel_tool_job
│   └── re_artifacts.py          # NEW — write_artifact / append_artifact / list_artifacts /
│                                #       get_artifact_tree / get_tool_log
│
├── subprocess_runner.py         # KEEP UNCHANGED — orchestrator scripts (workflows.py)
│                                # still use this; v1.1 does not migrate them
│
└── app.py                       # MODIFIED — lifespan also enters SessionRegistry +
                                 # BackgroundJobRegistry context managers
```

### 1.2 Why two runners coexist (`subprocess_runner.py` + `runner.py`)

`subprocess_runner.run_script` is purpose-built for **orchestrator pipeline scripts** that already write artifacts (00_sample_profile.md, etc.) — it has no notion of "case_dir cwd-confinement" or "auto-capture log under tool-logs/". `workflows.py` and `artifacts.py` already depend on it with stable semantics; rewriting them in v1.1 is needless risk.

`ReToolRunner` is purpose-built for **opaque RE binaries** (binwalk, readelf, strace, …) that the gateway invokes on behalf of the analyst. Its contract differs:

- cwd = `resolve_case_dir(case_dir)` (NOT `/agent`)
- Auto-capture full stdout/stderr to `<case_dir>/tool-logs/<UTC>-<slug>.txt` regardless of result size
- Output truncation in MCP response (configurable cap, default ~64 KB) so >LLM-context dumps don't blow the wire
- Returns a structured JSON shape that wrappers can layer over: `{exit_code, stdout_truncated, stderr_truncated, truncated: bool, log_path, duration_s, timed_out}`
- Optionally accepts a `slug` for the log filename (otherwise derived from argv[0])

**Both runners share the same low-level primitives** — process-group, SIGKILL on timeout, argv-only `create_subprocess_exec`. The shared bits could be lifted to a private `_exec_argv()` helper in `runner.py`, but a clean rule of thumb: don't migrate `subprocess_runner.py`'s callers (artifacts, workflows). New code goes through `runner.py`.

---

## 2. Integration Points (Concrete)

### 2.1 `ReToolRunner` — the single new execution path

```python
# runner.py
class ReToolRunner:
    """Single execution path for v1.1 RE tools. argv-only, cwd-confined to case_dir,
    auto-captures full output to tool-logs/, returns truncated payload + log_path.
    """

    DEFAULT_STDOUT_CAP = 64 * 1024
    DEFAULT_STDERR_CAP = 16 * 1024

    async def run(
        self,
        argv: list[str],
        *,
        case_dir: str,                 # MUST be a resolved case-dir from resolve_case_dir
        timeout: float,
        slug: str | None = None,       # log-filename hint; defaults to Path(argv[0]).name
        stdout_cap: int = DEFAULT_STDOUT_CAP,
        stderr_cap: int = DEFAULT_STDERR_CAP,
        env: dict[str, str] | None = None,
    ) -> dict: ...

    async def run_shell(
        self,
        cmd: str,                      # raw bash command — single argv element
        *,
        case_dir: str,
        timeout: float,
        slug: str | None = None,
    ) -> dict:
        # Single code path delegating to .run() with argv=["bash", "-lc", cmd]
        ...
```

**Integration points:**

| Caller | How |
|--------|-----|
| `tools/shell.py::run_shell` | `await runner.run_shell(cmd=cmd, case_dir=resolve_case_dir(case_dir), timeout=...)` |
| `tools/re_static.py::run_binwalk` | `await runner.run(["binwalk", path], case_dir=…, slug="binwalk")` |
| `tools/re_extract.py::run_unblob` | `await runner.run(["unblob", "-o", str(extract_dir), path], case_dir=…, timeout=1800.0, slug="unblob")` |
| `tools/re_dynamic.py::run_strace` | `await runner.run(["strace", "-f", "-o", str(out), path], …)` |
| `tools/re_jobs.py::start_tool_job` | Wraps `runner.run(...)` in an `asyncio.Task`; registers the task in `BackgroundJobRegistry` |

**Where the singleton lives:** `runner.py` exposes `_RUNNER = ReToolRunner()` and a `get_runner()` accessor (mirrors `app.get_mcp()`). No state; safe as a global. Tests inject a subclass via monkey-patching `runner._RUNNER`.

### 2.2 `run_shell` and typed wrappers share one code path

`run_shell(cmd: str)` is **not** a different runner. It is a thin wrapper that constructs `argv = ["bash", "-lc", cmd]` and calls `ReToolRunner.run()`. The bash string is a single argv element — Python never shell-interpolates it. The shell *inside the subprocess* does interpolation, but that is the analyst's intent (they're asking for a bash one-liner).

This means:

- Every safety property of typed wrappers (cwd-confinement, timeout, output cap, auto-capture, process-group cleanup) applies to `run_shell` for free
- No "argv allowlist" — security is structural (case-dir cwd + timeout + capture + no privileged ops by default), not enumerative
- Wrappers exist for **discoverability and structured output** only (capstone JSON, ropper bounds, file detection) — not as a safety mechanism. The CLAUDE.md decision row "Typed wrappers only where parsing/validation pays off" is the load-bearing principle here.

### 2.3 Session managers (r2, gdb) — registry + lifespan integration

**Where state lives:** `sessions/__init__.py` defines a `SessionRegistry` keyed by `session_id` (UUID4 string returned to the client). Each entry is a `Session` instance holding:

```python
class Session:
    session_id: str
    case_dir: str
    proc: asyncio.subprocess.Process
    stdin_lock: asyncio.Lock        # serialize concurrent commands per session
    last_used: float                # monotonic
    transcript_path: Path            # <case_dir>/tool-logs/<session_id>-<kind>.log
    kind: Literal["r2", "gdb"]
```

**Lifecycle:**

1. **Open** (`open_r2_session(sample, case_dir)`):
   - Resolves sample + case_dir.
   - Spawns `radare2 -q0 <sample>` (or `gdb --interpreter=mi3 -q <sample>`) via `create_subprocess_exec` with `start_new_session=True` and the same pipe pump pattern as `ReToolRunner`, but the process is **kept alive**.
   - Registers in `SessionRegistry`; returns `{session_id}`.
2. **Command** (`r2_cmd(session_id, cmd)`, `gdb_exec(session_id, cmd)`):
   - Looks up session; acquires `stdin_lock`; writes `cmd + "\n"`; reads until a sentinel (r2's prompt or gdb's `(gdb)` MI `(gdb) \n`).
   - Appends to `transcript_path`; returns `{output, duration_s}`.
3. **Close** (`close_r2_session(session_id)`): graceful `q\n` / `-gdb-exit`, then `killpg` after small grace, removes from registry.

**Idle reaping:** A background `asyncio.Task` polls every 30s and closes sessions where `now - last_used > MCP_GATEWAY_SESSION_IDLE_S` (default 1800s = 30 min). This task is owned by the **lifespan in `app.py`** — entered alongside `PinnedBackend`, cancelled cleanly on shutdown so leftover r2/gdb processes don't survive a gateway restart.

**`app.py` lifespan modification (additive only):**

```python
async with PinnedBackend(backend_name) as pinned:
    session_state.PINNED_BACKEND = pinned
    async with SessionRegistry() as session_registry:       # NEW
        async with BackgroundJobRegistry() as job_registry: # NEW
            session_state.SESSIONS = session_registry
            session_state.JOBS = job_registry
            async with mcp.session_manager.run():
                yield
```

`session_state.py` gains `SESSIONS: Optional[SessionRegistry]` and `JOBS: Optional[BackgroundJobRegistry]` fields — the same module-level pattern already used for `PINNED_BACKEND` and `ACTIVE_CASE`. Tools look these up exactly the way `disasm.py` looks up `PINNED_BACKEND`.

**Important constraint (per-client-session vs. gateway-global):** The CLAUDE.md `session_state` comment notes v2 will move to per-client-session state. For v1.1, r2/gdb sessions are intentionally **gateway-global** (any MCP client knowing the `session_id` can drive them). This is acceptable because:

- `session_id` is a UUID4 — opaque, unguessable
- Bearer auth already gates who can talk to the gateway at all
- Single-user/team Docker deployment is the operating envelope
- The migration path is clean: `SessionRegistry` already keys by `session_id`; later, sessions become scoped under a per-MCP-session bucket

### 2.4 Background jobs — `BackgroundJobRegistry`

**Why this exists:** MCP tool calls are request/response. capa on a 200 MB sample, unblob on a recursive firmware image, strace running for 5 minutes, or a Ghidra full-auto analysis all exceed the gateway's per-call timeout. The orchestrator skill needs fire-and-forget + poll.

**Shape:**

```python
class BackgroundJob:
    job_id: str                     # UUID4
    case_dir: str
    argv: list[str]                 # frozen for debugging
    task: asyncio.Task              # the running coroutine
    proc: asyncio.subprocess.Process | None  # populated after spawn
    pgid: int | None                # for cancel
    log_path: Path                  # <case_dir>/tool-logs/jobs/<job_id>.log
    started_at: float
    completed_at: float | None
    exit_code: int | None
    status: Literal["running", "completed", "failed", "cancelled", "timed_out"]

class BackgroundJobRegistry:
    """Owns asyncio.Tasks for long-running tools. Bound to the gateway lifespan;
    on shutdown, cancels outstanding jobs and SIGTERMs their process groups.
    """
    async def start(self, argv, *, case_dir, timeout, slug) -> str: ...
    def get(self, job_id) -> dict: ...            # status + tail of log
    async def cancel(self, job_id) -> dict: ...   # SIGTERM, then SIGKILL on grace
```

**Critical detail — surviving the MCP call duration:** The `asyncio.Task` is created on the **gateway event loop**, not the per-request task. FastMCP's request-handling task completes (returns the `job_id` to the client) while the spawned task continues. The Task is kept alive by the `BackgroundJobRegistry`'s reference. This is exactly how Python's `asyncio.create_task` works — the registry holds the reference so the loop doesn't GC the task between the `start` response and the next `get` poll.

**Tail-of-log streaming:** `get_tool_job(job_id, tail_bytes=8192)` reads the last N bytes of `log_path` and returns them, plus the status. No SSE streaming inside MCP — clients poll. (SSE inside MCP for incremental tool results is a 2025/2026 spec area but neither Claude Code nor mastra implement it cleanly; polling is the portable choice.)

**Why one asyncio.Task per job (not a worker pool):** The container is a single-tenant analysis box; concurrency comes from the OS (multiple subprocesses), not from queueing. A pool adds head-of-line blocking for no benefit at this scale. The natural backpressure is "the host runs out of RAM" — which means the answer is "don't run six capas at once," documented in the orchestrator skill, not enforced in the gateway.

### 2.5 Dynamic-mode gating — at registration time, not call time

**Wrong shape (rejected):**

```python
# DON'T: each tool checks the env var at call time
@mcp.tool()
async def run_strace(...):
    if os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") != "1":
        return {"error": "dynamic mode disabled"}
    ...
```

This pollutes every tool, ships the tool definitions in `tools/list` (giving agents false signals), and creates one branch per tool to forget.

**Right shape (recommended):**

```python
# tools/__init__.py
def register_all_tools(mcp: FastMCP) -> None:
    from . import (
        cases, artifacts, workflows, disasm, resources, backend_passthrough,
        shell, re_static, re_sessions, re_extract, re_jobs, re_artifacts,
    )
    # v1.0 surface
    cases.register(mcp)
    artifacts.register(mcp)
    workflows.register(mcp)
    disasm.register(mcp)
    resources.register(mcp)
    # v1.1 always-on surface
    shell.register(mcp)
    re_static.register(mcp)
    re_sessions.register(mcp)
    re_extract.register(mcp)
    re_jobs.register(mcp)
    re_artifacts.register(mcp)
    # v1.1 env-gated dynamic surface (default-off)
    if os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1":
        from . import re_dynamic
        re_dynamic.register(mcp)
    # Backend pass-through must register LAST (it installs the merged tools/list handler)
    backend_passthrough.register(mcp)
```

The gate is checked **once, at startup**. When off, `re_dynamic` is never imported, so:

- `tools/list` does not advertise strace/ltrace/qemu/gdb (correct discoverability signal)
- `tools/call` rejects them with the standard "tool not found" error from MCP (no custom branch)
- Zero per-call overhead, zero leaked surface

`run_docker.sh --dynamic` sets `MCP_GATEWAY_DYNAMIC_TOOLS=1` in the gateway's environment via the same overlay mechanism Phase 3 used for `--remote`. The flag composes additively: `--remote` enables the gateway, `--remote --dynamic` enables the gateway with the dynamic surface registered.

### 2.6 Expanded case-dir artifact tree

```
/agent/status/NNN-<sample>/
├── 00_sample_profile.md            # existing 13 artifacts (untouched)
├── … (12 more)
├── tool-logs/                      # NEW — auto-capture from ReToolRunner
│   ├── 20260512T140301Z-binwalk.txt
│   ├── 20260512T140312Z-readelf.txt
│   └── jobs/
│       └── <job_id>.log            # background-job streamed logs
├── extracted/                      # NEW — unblob/binwalk -e outputs
├── hex/                            # NEW — xxd dumps
├── rop/                            # NEW — ropper output
├── dynamic/                        # NEW — strace/ltrace/qemu outputs (gated)
├── qemu/                           # NEW — qemu-user run artifacts (gated)
├── disassembly/                    # NEW — capstone JSON dumps
├── decompilation/                  # NEW — IDA/BN/Ghidra decomp exports
└── xrefs/                          # NEW — get_xrefs persisted output
```

**Creation policy:** `artifacts_io.py` exposes `ensure_subdir(case_dir, name) -> Path` that creates subdirs lazily on first write. This avoids 8 always-empty directories per case. `init_case` (atomic tool, unchanged) does not need to know about v1.1 subdirs — they appear when first used.

**Resource exposure:** Adding all `tool-logs/*.txt` files to `mare://cases/<case>/...` resources is tempting but explodes the resource list. **Recommendation:** keep resources at the 13-artifact level (D-03 unchanged); add a single `get_tool_log(case_dir, log_name)` tool for fetching log contents on demand. This preserves the v1.0 resource contract.

---

## 3. Build Order (Phase Dependencies)

```
F-1 fix (image-hash includes mcp-gateway/)
     │
     │   ← unblocks everything; without it, every v1.1 phase ships repo edits
     │     that the container never sees.
     ▼
Phase A: ReToolRunner + artifacts_io          (no MCP surface change)
     │
     │   ← introduces runner.py + artifacts_io.py + unit tests; no tool exposure.
     │     Existing 22 tools untouched.
     ▼
Phase B: run_shell + typed static wrappers     (re_static.py, shell.py)
     │   + re_artifacts.py
     │
     │   ← these share the runner. Highest-value, lowest-risk surface area.
     │     Validates the runner under real load before sessions/jobs build on it.
     ▼
Phase C: Persistent sessions (r2, gdb-free)    (sessions/, re_sessions.py)
     │
     │   ← r2 first because gdb is dynamic-mode-gated and benefits from session
     │     plumbing already in place. Lifespan modification in app.py lands here.
     │     SessionRegistry idle reaper validated under r2 before gdb piles on.
     ▼
Phase D: Background-job registry               (jobs.py, re_jobs.py)
     │
     │   ← depends on ReToolRunner. Adds asyncio.Task lifecycle, kill-on-shutdown,
     │     log-tail polling. Validated against long-running capa/unblob from
     │     Phase B's static surface.
     ▼
Phase E: Extraction tier                       (re_extract.py)
     │
     │   ← uses jobs (unblob is slow) and runner (upx is fast). Adds the
     │     promote_extracted_sample primitive that turns a child into a case.
     │     Could ship in parallel with Phase D if extraction wrappers
     │     temporarily run synchronously, but cleaner serialized.
     ▼
Phase F: Dynamic-mode surface                  (re_dynamic.py + gate in __init__.py)
     │
     │   ← gdb session manager (reuses Phase C plumbing) + strace/ltrace/qemu
     │     (reuses runner). Env-gate lands in tools/__init__.py.
     │     run_docker.sh --dynamic surfaces the env var.
     ▼
Phase G: Orchestrator skill update             (workspace/.claude/skills/...)
     │
     │   ← LAST. Updates malware-analysis-orchestrator to: backend priority IDA>BN>Ghidra,
     │     deep RE checklist mapping findings→tools, CURRENT_STATE.json dynamic flag,
     │     remote-agent gateway-tool usage docs. Depends on all prior phases shipping
     │     so the skill can reference tools that exist.
```

**Parallelization opportunities:**

- F-1 (image-hash fix) and Phase A can land simultaneously (one is shell, one is Python).
- Phase B's `re_artifacts.py` (write/list/get artifact helpers) has no dependency on the static wrappers and can be split off.
- Phase E (extraction) and Phase D (jobs) can interleave if extraction wrappers ship without job-mode first and gain it later.
- Phase F's gdb session work and strace/ltrace/qemu wrappers are independent within the phase; one engineer per side.

**Why the order is robust against re-sequencing:**

- Runner before wrappers — wrappers can't compile without the runner type.
- Wrappers before sessions — sessions reuse the runner's process-group pattern, validated under wrappers' load.
- Sessions before jobs — `app.py::lifespan` is modified once for `SessionRegistry`; `BackgroundJobRegistry` reuses the same pattern.
- Jobs before extraction — extraction's biggest wins (unblob 30-min recursive carve) require jobs.
- Dynamic last among code — gdb piggybacks on session plumbing.
- Orchestrator last — references all primitives.

---

## 4. Component Boundaries

### 4.1 What goes where (decision matrix)

| New code | Module | Why this module |
|----------|--------|-----------------|
| argv-only async exec + cwd + timeout + capture | `runner.py` | One execution path, no MCP imports, easy to unit-test |
| `<case_dir>/tool-logs/`, `extracted/`, … helpers | `artifacts_io.py` | Filesystem concern, not MCP-aware; runner depends on it |
| `bash -lc` wrapper that calls runner | `tools/shell.py` | MCP-tool layer; nothing else lives here so the boundary "shell is one tool" stays visible in the source tree |
| `run_binwalk` / `run_readelf` / `run_capstone_disasm` / … | `tools/re_static.py` | Cluster: opaque tool wrappers with no persistent state. Splitting per-tool inflates file count for no benefit |
| `open_r2_session` / `r2_cmd` / `close_r2_session` | `tools/re_sessions.py` | MCP-tool layer; thin delegations to `sessions/r2.py` |
| `R2Session`, `GdbSession`, `SessionRegistry`, idle reaper | `sessions/` package | Long-lived process management. Decoupled from MCP so it can be unit-tested without spinning up FastMCP |
| `BackgroundJob`, `BackgroundJobRegistry`, kill-on-shutdown | `jobs.py` | Same justification as sessions — long-lived state, MCP-agnostic core |
| `start_tool_job` / `get_tool_job` / `cancel_tool_job` | `tools/re_jobs.py` | MCP-tool layer; thin wrappers over `JobRegistry` |
| extraction wrappers (unblob, upx, binwalk -e, promote) | `tools/re_extract.py` | Cluster with shared semantics ("produces files under `extracted/`"); promote_extracted_sample is the one stateful one |
| strace / ltrace / qemu / gdb-session tools | `tools/re_dynamic.py` | Env-gate boundary — module is imported only when dynamic mode is on, making the gate's behavior auditable at file granularity |
| `write_artifact` / `append_artifact` / `list_artifacts` / `get_artifact_tree` / `get_tool_log` | `tools/re_artifacts.py` | Distinct from `artifacts.py` (orchestrator pipeline tools) — file-name suffix `_io` vs. `re_` keeps the v1.0/v1.1 split obvious |

### 4.2 What stays put (do NOT modify)

- `subprocess_runner.py` — orchestrator-script runner. Untouched in v1.1.
- `tools/artifacts.py` — 10 atomic pipeline tools, all bash/python scripts via `run_script`. Untouched.
- `tools/workflows.py` — `run_triage` etc. Untouched.
- `tools/disasm.py` — `decompile`, `list_functions`, `get_xrefs`. Untouched. v1.1 may add a `persist_decompilation` tool in `re_artifacts.py` that writes IDA/BN/Ghidra output under `decompilation/`, but that is additive.
- `backend/client.py`, `backend/tool_map.py`, `backend/detect.py` — PinnedBackend stays as-is.
- `uploads.py` — POST /upload stays as-is.
- `auth.py` — middlewares unchanged.
- `tools/backend_passthrough.py` — registration order in `tools/__init__.py` keeps this **last** so its `tools/list`/`tools/call` merge handler sees v1.1's tools.

### 4.3 What changes (small, targeted)

- `app.py::lifespan` — adds two `async with` blocks for `SessionRegistry` and `BackgroundJobRegistry` (additive; existing `PinnedBackend` block unchanged).
- `session_state.py` — adds two `Optional` module-level slots: `SESSIONS`, `JOBS`. Same pattern as `PINNED_BACKEND`.
- `tools/__init__.py::register_all_tools` — adds 7 new module registrations plus the dynamic-mode gate. Pass-through `register()` is still called last.
- `run_docker.sh` — F-1 fix (hash includes `mcp-gateway/`) + `--dynamic` flag → `MCP_GATEWAY_DYNAMIC_TOOLS=1` export.

---

## 5. Data Flow Examples

### 5.1 `run_shell(cmd="readelf -a $(pwd)/sample.bin | head -100", case_dir=...)`

```
Client (Claude Code / mastra)
   │
   │ MCP tools/call run_shell
   ▼
FastMCP request handler
   │
   ▼
tools/shell.py::run_shell()
   │  validates case_dir via case_dirs.resolve_case_dir
   │
   ▼
runner.ReToolRunner.run_shell(cmd, case_dir=resolved)
   │  argv = ["bash", "-lc", cmd]
   │  asyncio.create_subprocess_exec(*argv, cwd=case_dir,
   │                                 start_new_session=True, ...)
   │
   ├─► child bash process (PGID = N)
   │       └── readelf, head subprocesses (same PGID)
   │
   │  artifacts_io.open_capture(case_dir, "shell")
   │       writes <case_dir>/tool-logs/20260512T140301Z-shell.txt
   │
   │  on timeout: os.killpg(N, SIGKILL)
   │
   ▼
return {exit_code, stdout_truncated, log_path, truncated, ...}
```

### 5.2 `start_tool_job(argv=["capa", path], case_dir=...)`

```
Client
   │  tools/call start_tool_job
   ▼
tools/re_jobs.py::start_tool_job()
   │
   ▼
jobs.BackgroundJobRegistry.start(argv, case_dir, ...)
   │
   │  task = asyncio.create_task(_run_job(...))
   │  self._jobs[job_id] = BackgroundJob(task=task, ...)
   │
   ▼  (handler returns to client almost immediately)
{"job_id": "abc-...", "status": "running"}

... time passes; the asyncio.Task continues on the gateway loop ...

Client (polls)
   │  tools/call get_tool_job job_id=abc-...
   ▼
jobs.BackgroundJobRegistry.get(job_id)
   │  reads tail of log_path, status
   ▼
{"status": "running" | "completed" | "failed", "tail": "...", "exit_code": ...}
```

### 5.3 r2 persistent session

```
open_r2_session(sample, case_dir)
   │   spawns radare2 -q0 <sample> (kept alive)
   │   SessionRegistry[session_id] = R2Session(proc, stdin_lock, ...)
   ▼  {"session_id": "..."}

r2_cmd(session_id, cmd="aaa; afl")    ── analyst-style state-sharing across calls
   │   session.stdin_lock.acquire()
   │   writes "aaa; afl\n" to proc.stdin
   │   reads until prompt sentinel
   ▼  {"output": "...", "duration_s": 12.3}

r2_cmd(session_id, cmd="pdf @ main")  ── analysis state persists
   ▼  {"output": "...", ...}

close_r2_session(session_id)
   │   writes "q\n"; small grace; killpg
   │   removes from registry
   ▼  {"closed": true}
```

---

## 6. Patterns to Follow

### Pattern 1: Tool module shape mirrors v1.0

```python
# tools/re_static.py
from __future__ import annotations
from mcp.server.fastmcp import FastMCP
from ..runner import get_runner
from .case_dirs import resolve_case_dir
from .samples import resolve_sample

def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def run_binwalk(sample: str, case_dir: str) -> dict:
        path = resolve_sample(sample)
        cd = resolve_case_dir(case_dir)
        return await get_runner().run(
            ["binwalk", path], case_dir=cd, timeout=300.0, slug="binwalk",
        )
    # ... other typed wrappers
```

**Why:** matches the established `register(mcp)` seam (artifacts.py, workflows.py, cases.py). Reviewers find consistency.

### Pattern 2: Session lookup mirrors PinnedBackend lookup

```python
# tools/re_sessions.py
from .. import session_state

@mcp.tool()
async def r2_cmd(session_id: str, cmd: str) -> dict:
    sessions = session_state.SESSIONS
    if sessions is None:
        raise RuntimeError("session registry not initialized")
    return await sessions.r2.exec(session_id, cmd)
```

**Why:** mirrors `disasm.py`'s `session_state.PINNED_BACKEND` pattern. Same idiom = lower cognitive load.

### Pattern 3: Lifespan ownership for long-lived resources

Anything that outlives a request lives in `app.py::lifespan` as an `async with` block. The body registers the instance into `session_state`; the `finally` clears it. v1.1 adds `SessionRegistry` and `BackgroundJobRegistry` to this list — same pattern as v1.0's `PinnedBackend`.

### Pattern 4: Auto-capture by default, opt-out is the rare path

Every tool that produces output writes the full untruncated stream to a log file. MCP response payload is the truncated view + the log path. Clients reading the resource (or calling `get_tool_log`) get the full output. This makes "I lost my output to truncation" impossible.

---

## 7. Anti-Patterns to Avoid

### Anti-Pattern 1: Per-tool environment-variable checks for dynamic mode
**Why bad:** Pollutes every tool with the same conditional; lets `tools/list` advertise tools that always 4xx; multiplies test surface.
**Instead:** Gate at module registration in `tools/__init__.py`. Dynamic tools are absent — not disabled — when off.

### Anti-Pattern 2: Sharing `subprocess_runner.run_script` between orchestrator and RE tools
**Why bad:** `run_script` defaults `cwd="/agent"` (orchestrator's relative STATUS_ROOT depends on it); has no log-capture or output-cap semantics; its callers (artifacts.py, workflows.py) have stable behavior that would change subtly.
**Instead:** New `ReToolRunner` for v1.1. Old runner left alone. The 80-line duplication of `create_subprocess_exec + start_new_session + killpg` is acceptable price for stable v1.0 behavior; the two modules can converge in v1.2 once both surfaces are settled.

### Anti-Pattern 3: Running background jobs as ad-hoc `asyncio.create_task` without a registry
**Why bad:** Task references are GC'd; processes outlive the gateway on shutdown; no way to cancel; no observability.
**Instead:** `BackgroundJobRegistry` holds task refs and process-group IDs, cancels on lifespan exit.

### Anti-Pattern 4: Persistent r2/gdb processes as `asyncio.subprocess.Process` references in a dict without a stdin lock
**Why bad:** Concurrent `r2_cmd` calls interleave bytes on stdin/stdout, corrupting output parsing.
**Instead:** `Session.stdin_lock = asyncio.Lock()`; every command acquires it. Serializes per-session, parallel across sessions.

### Anti-Pattern 5: Exposing every tool-log as an MCP Resource
**Why bad:** Cases accumulate dozens of timestamped logs; `resources/list` payload explodes; URI table is overwhelming for agents.
**Instead:** Resources stay at the 13-artifact level. `get_tool_log(case_dir, log_name)` and `list_artifacts(case_dir, subdir="tool-logs")` cover ad-hoc access.

### Anti-Pattern 6: Allow-listing argv tokens for `run_shell`
**Why bad:** The whole point of `run_shell` is the long tail of Kali utilities. An allowlist defeats the purpose; analyst-typed bash one-liners have unbounded shape.
**Instead:** Structural safety (cwd-confinement + timeout + capture + dynamic-mode gate for risky ops). The decision row in CLAUDE.md ("Expose a constrained `run_shell` over MCP") is explicit.

### Anti-Pattern 7: Touching `backend_passthrough.register()` ordering
**Why bad:** It installs custom `tools/list`/`tools/call` handlers via `mcp._mcp_server.list_tools()` and `.call_tool()` — registering anything **after** it would not appear in the merged surface.
**Instead:** Always register pass-through last in `tools/__init__.py`. Keep the comment that says so.

---

## 8. Scalability Considerations

| Concern | Single analyst | Small team (3-5 concurrent) | Stress (10+ jobs) |
|---------|----------------|------------------------------|---------------------|
| Concurrent r2/gdb sessions | 1-3 sessions, fine | Each session is one subprocess + one asyncio.Task — Python's loop handles 20-50 sessions trivially; OS handles the procs | Lock contention possible only **within** a session; cross-session is fully parallel |
| Background jobs | 1-2 long-running tasks | Lock-free registry; only the asyncio loop is shared | Container RAM is the bound (capa+unblob+ghidra-auto ≈ multi-GB each) — gateway shouldn't queue; document the limit |
| Tool-logs disk growth | Bounded by case lifecycle | `tool-logs/jobs/` cleaned on case deletion | No automatic rotation in v1.1; revisit if cases live >30 days |
| FastMCP request handlers | Single-process uvicorn | Stateless tools handle concurrent requests; PinnedBackend has its own `_call_lock` per disasm call | uvicorn `--workers > 1` is incompatible with the gateway-singleton model — keep single-worker |

**Where this can bite:** Process-group cleanup is at SIGKILL-on-timeout granularity, not finer. A misbehaving `run_shell` that forks a daemon and detaches with `setsid` will outlive the gateway. Mitigation: the dynamic-mode tools (qemu in particular) document this and recommend running long observations as `start_tool_job` jobs (where the registry tracks PGID and the cancel path is explicit).

---

## 9. Sources

**Primary — file inspection of existing gateway (HIGH confidence):**
- `mcp-gateway/src/mcp_gateway/app.py` — lifespan + middleware wiring
- `mcp-gateway/src/mcp_gateway/subprocess_runner.py` — argv-only async exec pattern
- `mcp-gateway/src/mcp_gateway/session_state.py` — module-level slot pattern
- `mcp-gateway/src/mcp_gateway/tools/__init__.py` — single registration seam
- `mcp-gateway/src/mcp_gateway/backend/client.py` — long-lived ClientSession via AsyncExitStack
- `mcp-gateway/src/mcp_gateway/tools/backend_passthrough.py` — merged tools/list/call ordering constraint
- `mcp-gateway/src/mcp_gateway/tools/artifacts.py` — atomic-tool register pattern
- `mcp-gateway/src/mcp_gateway/tools/workflows.py` — composite tool dispatch pattern

**Primary — planning context (HIGH confidence):**
- `.planning/PROJECT.md` — v1.1 target features, key decisions, security boundary shift
- `.planning/MILESTONES.md` — F-1 carryover finding (image-hash bug)
- `CLAUDE.md` — Technology Stack, Do NOT Use list, Key Decisions

**Secondary — Python asyncio semantics (HIGH confidence, training data + idiomatic):**
- `asyncio.subprocess.Process` + `start_new_session=True` + `os.killpg` is the documented process-group pattern (used in the existing `subprocess_runner.run_script`)
- `asyncio.create_task` + explicit registry to keep task alive is the documented anti-GC pattern (PEP 3156 / asyncio docs)
- FastMCP's `lifespan` is the documented hook for resources spanning the server's lifetime (MCP Python SDK README)
