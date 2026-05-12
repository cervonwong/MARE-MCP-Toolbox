# Stack Research — v1.1 Remote RE Tool Expansion

**Domain:** Agentic malware analysis platform — extending the existing MCP gateway with typed RE tool wrappers, session-scoped interactive tools (r2/gdb), a constrained `run_shell`, and a background job system.
**Researched:** 2026-05-12
**Confidence:** HIGH (existing stack already validated; this milestone only adds library bindings around CLI tools that are already installed in the container)

**Scope note:** v1.0 stack (custom FastMCP gateway, MCP Python SDK 1.27.x, Streamable HTTP, bearer auth, sha256 uploads, `PinnedBackend` ClientSession) is **fixed and not re-researched**. This file lists only the deltas required for v1.1 — every recommendation extends `mcp-gateway/pyproject.toml` or adds an apt/pip line in `Dockerfile`; nothing replaces validated v1.0 choices.

---

## Recommended Stack — Additions for v1.1

### Core Additions (mcp-gateway runtime deps)

| Technology | Version | Purpose | Why Recommended | Confidence |
|------------|---------|---------|-----------------|------------|
| r2pipe (Python) | 1.9.8 | Session-scoped radare2 driver behind `open_r2_session` / `r2_cmd` / `close_r2_session` | Official radare2 bindings (`radareorg/radare2-r2pipe`); spawns one `r2 -q0` subprocess per session and pipes commands over stdio, so analysis state (`aaa`, flags, `s @`) persists across MCP calls. **Synchronous-only** — wrap calls in `anyio.to_thread.run_sync()` inside FastMCP tool handlers. Subprocess + `Popen` alternative would force us to re-implement r2's framing protocol, which r2pipe already handles. | HIGH |
| pygdbmi | 0.11.0.0 | Session-scoped GDB driver behind `open_gdb_session` / `gdb_exec` / `close_gdb_session` | Drives `gdb --interpreter=mi3` as a subprocess and parses GDB/MI output into structured Python dicts — exactly what an MCP tool wants to return as JSON. Persistent `GdbController` instance per session matches r2's session shape. Synchronous; offload via `anyio.to_thread.run_sync()`. Maintained but slow-moving (last release Jan 2023) — acceptable because GDB/MI itself is stable and pygdbmi is a thin parser, not a feature-rich client. | HIGH |
| capstone | 5.0.7 | Disassembly engine behind `run_capstone_disasm(arch, mode, bytes)` | Industry-standard multi-arch disassembler (x86/x64/ARM/ARM64/MIPS/PPC/RISC-V); Python bindings are a lightweight ctypes wrapper around the C lib, returning structured `CsInsn` objects perfect for JSON serialization. Already installed via pip in `Dockerfile` — this milestone pins the version. Pure in-process call, no subprocess. | HIGH |
| ropper | 1.13.13 | ROP/JOP gadget search behind `run_ropper(file, arch, depth)` | Multi-arch (x86, ARM, MIPS, PPC, SPARC); exposes `RopperService` Python class so we can avoid spawning the CLI and serialize gadgets directly to JSON with structured `Gadget` objects. Already installed via pip in `Dockerfile`. | HIGH |
| unblob | 26.3.30 | Recursive firmware/archive extraction behind `run_unblob(file)` | Sandia/ONEKEY's modern replacement for `binwalk -e` with better filesystem/firmware support; exposes Python API (`unblob.processing.process_file` + `ExtractionConfig`) so we can avoid CLI parsing. Already installed via pip in `Dockerfile`. **Requires Python ≥3.10** — container is on 3.11+, fine. | HIGH |
| pexpect | 4.9.0 | **Test-side only** — pty-driven assertion of session-scoped r2/gdb tools in pytest | Drives subprocesses through a real PTY so tests can assert on the actual interactive protocol (banner, prompt, command echo) rather than mocking r2pipe/pygdbmi internals. Last release Nov 2023, stable. | HIGH |

### Already-pinned, no change needed

| Technology | Version | Why mentioned here |
|------------|---------|---------------------|
| mcp (Python SDK) | `>=1.27,<1.28` | **Already pinned.** Confirmed during this research that `Context.report_progress(progress, total, message)` is available in 1.27 — this is the streaming primitive for the v1.1 background job system. No version bump needed. |
| anyio | `>=4.5` | **Already pinned.** `anyio.to_thread.run_sync()` is exactly what we need to offload the synchronous r2pipe/pygdbmi/ropper/unblob calls from the FastMCP event loop. `anyio.create_memory_object_stream()` is the recommended pattern for tool→job-log streaming. Latest is 4.13 — current `>=4.5` floor covers it. |
| httpx | `>=0.27` | **Already pinned.** No change. |
| starlette / uvicorn / python-multipart | as pinned | **Already pinned.** No change. |

### Standard-library primitives (no new deps)

| API | Purpose | Notes |
|-----|---------|-------|
| `asyncio.create_subprocess_exec` | argv-only subprocess execution inside `ReToolRunner` | Already the v1.0 pattern (`PinnedBackend` uses it for BN/Ghidra stdio). Reuse for `run_shell` (with `/bin/bash -c <cmd>` argv) and all typed CLI wrappers. Preserves the "argv-only, no shell-string interpolation" security property from v1.0 — `run_shell`'s string is passed as a single argv element to bash, not concatenated. |
| `asyncio.wait_for` / `asyncio.timeout` | Per-tool timeout enforcement | Returns to caller after kill; pair with `os.killpg(os.getpgid(pid), SIGTERM)` (already in `ReToolRunner` design) so child processes don't outlive timeout. |
| `os.setsid` (preexec / Popen `start_new_session=True`) | Process-group cleanup | Required so SIGTERM hits children of `run_shell` invocations (pipes, subshells) — without it a `run_shell "binwalk x \| tee y"` leaks `tee` on timeout. |
| `uuid.uuid4` + `dict[str, JobRecord]` | Background job registry | Job IDs returned by `start_tool_job`, looked up by `get_tool_job` / `cancel_tool_job`. No DB needed — gateway is single-process. |
| `anyio.create_task_group` | Lifecycle for background jobs | Structured concurrency so cancellation cleanly tears down running subprocess + log writer. |
| `pathlib.Path` + `os.path.commonpath` | `case_dir` confinement for `run_shell` cwd and artifact writes | Reject any resolved path that isn't under `case_dir`. Mirrors the path-traversal check already used by `POST /upload`. |
| `secrets.token_hex(4)` | Slug for `tool-logs/<timestamp>-<slug>.txt` filenames | Avoid collision when two `run_shell` calls land in the same second. |

### Optional Kali apt packages — confirm installed

The Dockerfile audit shows almost everything is already there. Verify-only list:

| Package | Status in current `Dockerfile` | Action |
|---------|-------------------------------|--------|
| `radare2` | Installed via apt | No action — confirmed |
| `gdb`, `gdb-multiarch` | Installed via apt | No action — confirmed |
| `qemu-user` | Installed via apt | No action — confirmed (used by `run_qemu_user`) |
| `strace`, `ltrace` | Installed via apt | No action — confirmed |
| `binwalk` | Installed via apt | No action — confirmed |
| `upx-ucl` | Installed via apt | No action — confirmed (powers `run_upx_test` / `run_upx_unpack`) |
| `yara`, `jq`, `yq`, `xxd`, `file`, `detect-it-easy`, `ssdeep` | Installed | No action — confirmed |
| `unblob` (Python pkg) | Installed via pip `--break-system-packages` | **Pin version** in pip line — currently unpinned |
| `capstone`, `ropper` (Python pkg) | Installed via pip `--break-system-packages` | **Pin versions** in pip line — currently unpinned |
| **r2pipe** | **NOT installed** | **NEW** — add `r2pipe==1.9.8` to the Dockerfile pip line |
| **pygdbmi** | **NOT installed** | **NEW** — add `pygdbmi==0.11.0.0` to the Dockerfile pip line |
| **pexpect** | **NOT installed** | **NEW (dev only)** — add to `mcp-gateway/pyproject.toml` `[project.optional-dependencies] dev`, not to the image proper |
| `capa` | Installed standalone in `/usr/local/bin/capa` | No action — confirmed (background-job candidate) |

### Development Tools — no change

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest / pytest-asyncio | Already in `[dev]` | Add `pexpect` to `[dev]` for session-scoped tool tests |
| ruff | Already in `[dev]` | No change |
| `tempfile` / real tempdirs | Already the v1.0 test pattern | **Confirmed: do NOT add `pyfakefs`.** Existing tests use real tempdirs (e.g., upload tests in Phase 2); session-scoped r2/gdb tests will spawn real subprocesses that read real files — `pyfakefs` would break them. |

---

## Installation

### Extend `mcp-gateway/pyproject.toml`

```toml
[project]
# ... existing v1.0 deps unchanged ...
dependencies = [
    "mcp>=1.27,<1.28",
    "starlette>=0.37",
    "uvicorn>=0.27",
    "python-multipart>=0.0.9",
    "httpx>=0.27",
    "anyio>=4.5",
    # --- v1.1 additions ---
    "r2pipe>=1.9.8,<2",
    "pygdbmi>=0.11,<0.12",
    "capstone>=5.0.7,<6",
    "ropper>=1.13.13,<2",
    "unblob>=26.3,<27",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "ruff>=0.5",
    "pexpect>=4.9,<5",  # v1.1: PTY-driven session tests
]
```

### Extend `Dockerfile` pip block

```dockerfile
RUN python3 -m pip install --no-cache-dir --break-system-packages \
    pytest pytest-asyncio ruff flare-floss uv ipython ipdb \
    "capstone==5.0.7" "ropper==1.13.13" "unblob==26.3.30" \
    "r2pipe==1.9.8" "pygdbmi==0.11.0.0" \
    "mcp>=1.27,<1.28" "starlette>=0.37" "uvicorn>=0.27" \
    "python-multipart>=0.0.9" "httpx>=0.27" "anyio>=4.5"
```

No new apt packages required. Pin existing unpinned `capstone` / `ropper` / `unblob` lines while we're touching that block.

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| **r2pipe** | Raw `subprocess.Popen("r2", ...)` + manual stdio framing | Never for this project. We'd be re-implementing r2pipe's framing (`r2 -q0` null-terminator protocol). r2pipe is 200 lines of well-tested code we'd otherwise rewrite. |
| **r2pipe** | `r2papi` (higher-level Python wrapper over r2pipe) | If we wanted typed Pythonic accessors (`r2.functions`, `r2.strings`). v1.1 explicitly exposes raw `r2_cmd(cmd)` for the agent — the LLM writes r2 commands, we don't curate them. Adds a dep for no benefit. |
| **pygdbmi** | gdb's built-in Python API (`import gdb`) | Only works *inside* a running GDB process, not from the gateway. Wrong direction of control. |
| **pygdbmi** | gdbgui | A web UI for GDB. Wrong product category — we don't want a UI, we want structured GDB/MI parsing. |
| **pygdbmi** | Raw `subprocess` + manual GDB/MI parser | We'd be writing a parser for `^done,bkpt={number="1",type="breakpoint",...}` GDB/MI grammar. pygdbmi already does this with documented edge cases. |
| **capstone (Python)** | `objdump -d` parsing | Loses structured opcodes/operands; no programmatic access to instruction groups, registers read/written. Capstone returns `CsInsn` objects that JSON-serialize cleanly. |
| **ropper (Python API)** | Shelling out to `ropper` CLI and parsing text | The `RopperService` class returns `Gadget` objects directly. CLI parsing is fragile (column widths shift per arch). |
| **unblob (Python API)** | `binwalk -e` only | binwalk is still installed and exposed via `run_binwalk` — unblob covers modern firmware/container formats binwalk misses (squashfs variants, modern UEFI, exotic compression). Use both; orchestrator skill picks per case. |
| **MCP `Context.report_progress`** | Custom WebSocket / SSE side-channel | We already have Streamable HTTP. `report_progress` is the spec-defined way; clients (Claude Code, mastra.ai) already render progress notifications. No side-channel needed. |
| **`anyio.to_thread.run_sync`** | `asyncio.run_in_executor` directly | `anyio` is already a dep and abstracts asyncio vs trio. `to_thread.run_sync` is the documented v1.0 pattern in the existing gateway. |
| **pytest + pexpect for session tests** | `pyfakefs` for filesystem isolation | Sessions spawn real `r2` / `gdb` subprocesses that mmap real binaries — pyfakefs would break them. Existing v1.0 tests use real tempdirs already. |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `os.system()` or `subprocess.Popen(..., shell=True)` for `run_shell` | Re-introduces shell injection that v1.0's argv-only mitigation explicitly prevented | `asyncio.create_subprocess_exec("/bin/bash", "-c", user_cmd, cwd=case_dir, start_new_session=True)` — the user string is a single argv element to bash, not concatenated into a shell line by Python |
| `r2papi` (high-level Python r2 wrapper) | Adds an opinionated typed layer the agent doesn't need; the agent writes raw r2 commands | `r2pipe` |
| `gdbgui` / `pygdbgui` | Web UI for GDB; wrong product shape for an MCP backend | `pygdbmi` |
| `python-ptrace` | Pure-Python ptrace bindings — useful for custom tracers, but we just shell out to `strace`/`ltrace`, which are installed | `strace` / `ltrace` CLI via `ReToolRunner` |
| `mcp-remote` (npm) | CVE-2025-6514 (CVSS 9.6 command injection); also wrong language | N/A — v1.0 already chose the Python SDK directly |
| MCP SSE transport | Deprecated June 2025 in MCP spec | Already on Streamable HTTP from v1.0 — no change |
| `pyfakefs` for v1.1 tests | Sessions spawn real r2/gdb subprocesses against real binaries | Real tempdirs (existing pattern) + `pexpect` for PTY assertions |
| Threading-based background jobs (`threading.Thread`) | Mixes badly with FastMCP's anyio task groups; cancellation is hard | `anyio.create_task_group()` + `anyio.to_thread.run_sync()` for the actual subprocess wait |

---

## Stack Patterns by Variant

**For session-scoped tools (`open_r2_session`, `open_gdb_session`):**
- One subprocess per session, lifetime owned by a gateway-side `dict[session_id, SessionHandle]`
- `SessionHandle` stores: `subprocess` (managed by r2pipe/pygdbmi), `anyio.Lock` (serialize concurrent `r2_cmd` calls on the same session), `created_at`, `case_dir`
- TTL sweeper task (anyio background task) closes idle sessions after N minutes
- All `r2pipe.open(...).cmd(...)` and `GdbController.write(...)` calls go through `anyio.to_thread.run_sync()` — both libs are sync

**For one-shot typed wrappers (`run_binwalk`, `run_readelf`, `run_capstone_disasm`, ...):**
- Single `ReToolRunner.run(argv, timeout, output_cap)` call
- Result JSON: `{status, exit_code, stdout, stderr, stdout_truncated, log_path}`
- Auto-capture to `case_dir/tool-logs/<ts>-<slug>.txt`
- For capstone/ropper/unblob (in-process Python): same shape, but `exit_code` is synthetic (0 on no-exception, non-zero on caught exception)

**For `run_shell`:**
- Same `ReToolRunner` but argv is `["/bin/bash", "-c", cmd]` plus `cwd=case_dir`, `start_new_session=True`
- Hard timeout (default 60s, configurable up to a ceiling like 600s)
- Output cap (default 256 KB, configurable up to ~10 MB) — anything beyond goes only to the `tool-logs/` file
- Resolved-path verification on any artifact the agent then asks us to read back (existing `case_dir` check from v1.0)

**For background jobs (`start_tool_job`):**
- `start_tool_job(tool="capa", argv=[...], timeout=600)` → returns `{job_id}`
- Job runs in an `anyio` task group launched at gateway startup
- Streams stdout/stderr lines into `case_dir/tool-logs/<job_id>.log` as they arrive (`asyncio.subprocess.PIPE` + `readline`)
- `Context.report_progress` fired on N-line boundaries (10? 100? — phase planner's call) so MCP clients see progress
- `get_tool_job(job_id)` returns `{status: running|done|failed|cancelled, tail: <last 4 KB>, log_path, exit_code?}`
- `cancel_tool_job(job_id)` → `os.killpg(pgid, SIGTERM)`, then SIGKILL after grace period

**For dynamic mode gating:**
- Read `MCP_GATEWAY_DYNAMIC_TOOLS` env var at gateway startup (same pattern as `MCP_GATEWAY_ENABLED` in v1.0)
- If unset/0: do not call `@mcp.tool` for `run_strace` / `run_ltrace` / `run_qemu_user` / `open_gdb_session` / `gdb_exec` / `close_gdb_session`
- Tool registration must be guard-conditional, not just runtime-error — otherwise the tool surface advertises tools it refuses to run, which is confusing for agents

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `r2pipe 1.9.8` | `radare2` (any modern build — Kali ships current) | r2pipe is just a stdio framing layer; the actual r2 version is whatever apt installed. Verify with `r2 -v` during container build smoke test. |
| `pygdbmi 0.11.0.0` | `gdb` 8+ / `gdb-multiarch` (both installed) | Library is a thin GDB/MI3 parser; MI3 has been stable since GDB 9. Container has gdb 14+. |
| `capstone 5.0.7` (Python) | Python ≥3.8 | Container has 3.11+. Bundles its own native lib via the wheel — no system `libcapstone` needed. |
| `ropper 1.13.13` | `capstone ≥3`, `filebytes ≥0.10.0` | filebytes pulled in transitively. capstone 5.x is compatible (ropper specifies `>=3`). |
| `unblob 26.3.30` | Python ≥3.10 | Container has 3.11+. Pulls in `pycdc`/`jefferson`/etc. transitively — these may push image size up; verify in build smoke test. |
| `mcp 1.27.x` | `Context.report_progress`, Streamable HTTP, idle timeout | Confirmed in MCP SDK 1.27 release notes. No bump needed for v1.1 features. |
| `anyio 4.5+` | `to_thread.run_sync`, memory object streams, task groups | All v1.1 patterns work on the current floor; latest is 4.13. |
| `pexpect 4.9.0` | Python 3.11+ (Linux/macOS) | Linux-only test helper — container is Linux. Not used at runtime. |

### Image size and build-time impact

| Addition | Approx. wheel size | Build-time concern |
|----------|-------------------|--------------------|
| r2pipe | <50 KB | None |
| pygdbmi | <100 KB | None |
| capstone (already installed) | ~5 MB (native lib) | Already present |
| ropper (already installed) | <500 KB | Already present |
| unblob (already installed) | ~3 MB + extractors | Already present; transitive deps are the bulk |
| **New mass: ~150 KB** | | **Negligible** vs. current ~4 GB image with IDA/BN/Ghidra |

---

## Sources

- [r2pipe 1.9.8 on PyPI](https://pypi.org/pypi/r2pipe/) — version, Python compatibility, sync-only API — **HIGH** (official package)
- [radare2-r2pipe GitHub](https://github.com/radareorg/radare2-r2pipe) — confirmed no async API, official radare2 org — **HIGH**
- [pygdbmi 0.11.0.0 on PyPI](https://pypi.org/pypi/pygdbmi/) — version, GDB/MI parser scope, `GdbController` class shape — **HIGH**
- [pygdbmi GitHub (cs01)](https://github.com/cs01/pygdbmi) — usage pattern for persistent sessions — **HIGH**
- [capstone 5.0.7 on PyPI](https://pypi.org/pypi/capstone/) — version, Python ≥3.8 floor — **HIGH** (official Capstone team)
- [ropper 1.13.13 on PyPI](https://pypi.org/pypi/ropper/) — version, `RopperService` Python API, capstone≥3 dep — **HIGH**
- [unblob 26.3.30 on PyPI](https://pypi.org/pypi/unblob/) — version, Python ≥3.10 floor, `unblob.processing` API — **HIGH** (ONEKEY official)
- [pexpect 4.9.0 on PyPI](https://pypi.org/pypi/pexpect/) — version, last release Nov 2023 — **HIGH**
- [anyio 4.13.0 on PyPI](https://pypi.org/pypi/anyio/) — `to_thread.run_sync`, task groups, current floor `>=4.5` covers needed APIs — **HIGH**
- [MCP Python SDK v1.27.0 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.27.0) — `Context.report_progress(progress, total, message)` is supported in 1.27; idle timeout for StreamableHTTP added — **HIGH** (official release)
- [MCP transports spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports) — Streamable HTTP is current; SSE deprecated — **HIGH**
- Existing `mcp-gateway/pyproject.toml` and `Dockerfile` — established v1.0 pin policy and apt manifest — **HIGH** (in-repo, verified by Read)

---

*Stack research for: v1.1 Remote RE Tool Expansion — additions only*
*Researched: 2026-05-12*
