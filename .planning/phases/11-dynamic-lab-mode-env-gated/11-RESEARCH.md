# Phase 11: Dynamic Lab Mode (env-gated) - Research

**Researched:** 2026-05-19
**Domain:** Linux dynamic-analysis tooling (strace / ltrace / qemu-user / gdb-MI3) under per-call netns isolation, integrated into an existing FastMCP gateway with JOBS + SessionRegistry plumbing.
**Confidence:** HIGH for the locked architectural decisions (CONTEXT.md is exhaustive). Where research found friction this document flags it explicitly.

## Summary

CONTEXT.md (1573 lines) already locks the full design: module layout, env-gate semantics, gdb-MI3 framing, MI-prefix allowlist, three job specs, capability probe shape, follow-fork stray reaping, and the `--dynamic` flag. The role of this research is therefore VERIFICATION + PITFALL HARDENING, not re-design. I validated the eight technical assumptions called out as "research targets" in the additional context, and found:

1. **gdb-MI3 sentinel framing is sound** — `-data-evaluate-expression` returning a per-session random token is a known idiom; the `(gdb) \n` prompt is unreliable as a terminator because async stop records interleave with `^done`. The MI3 result class always closes a record group, so reading until `^done,value="\"__MARE_END_<8hex>__\""` is the safe terminator. `set mi-async off` is implicit (mi3 is sync-by-default at the wrapper level when `-exec-*` is the only async source).
2. **MI-prefix allowlist must include both `-interpreter-exec` AND raw CLI escapes** — confirmed via sourceware docs: `-interpreter-exec console "python ..."` is the canonical sandbox-escape vector. CONTEXT.md's denylist hits this exactly. CONTEXT.md also covers `-target-select` / `-target-attach`, `add-symbol-file`, `generate-core-file`, `dump`, `set inferior-tty`. No additional escape vectors found that aren't already blocked.
3. **strace argv profiles are well-chosen but two CONTEXT.md entries need correction** — strace has no `--exec` flag (it has `-b execve` / `--detach-on=execve`); the denylist entry should be renamed or removed. Also `--kill-on-exit` is a recent strace flag that would help with stray-process cleanup and should be considered for inclusion in the builder (not the allowlist).
4. **qemu-user binfmt with the `F` flag is the standard idiom**, registered by `qemu-user-static` package's postinst via `update-binfmts` / systemd-binfmt. Detection via `/proc/sys/fs/binfmt_misc/qemu-<arch>` files is correct. The CONTEXT.md probe is bit-precise: check `enabled` line AND `flags: ...F...` to ensure the registration survives mount-namespace switching into the container.
5. **Follow-fork stray reaping via `/proc/<pid>/task/*/children`** is the canonical Linux mechanism — bubblewrap and nsjail use similar walks. Grandchildren that `setsid()` DO escape `killpg` and require explicit per-pid SIGKILL. Recursive scan to depth 8 (CONTEXT.md default) is adequate.
6. **ptrace_scope semantics are confirmed (0/1/2/3 from Yama LSM docs)** and Docker's `--cap-add=SYS_PTRACE` is the correct posture (CLAUDE.md already declares this). The container's seccomp posture (`seccomp=unconfined` per CLAUDE.md) is what permits `unshare(CLONE_NEWNET)` — Docker's default seccomp blocks unshare without CAP_SYS_ADMIN. **This is the single highest-risk dependency**: if the container ever loses `seccomp=unconfined`, every dynamic-mode subprocess fails at `unshare` invocation with EPERM.
7. **netns feasibility** — `unshare --net true` round-trip is the right probe. On hosts where the container lacks CAP_SYS_ADMIN AND seccomp is the default profile, this returns `EPERM`. Probe must call `subprocess.run` (not `os.unshare`) so it exercises the actual syscall path the dynamic-mode subprocesses will take.
8. **Lifespan startup ordering** — `CAPABILITIES` slot must be populated AFTER `register_all_tools` (so JOB_TOOL_REGISTRY exists for any spec-validation logging) but BEFORE `PinnedBackend.__aenter__`. CONTEXT.md gets this right. The capability probe should run unconditionally (both backend and no-backend lifespan paths) because `get_dynamic_capabilities()` is also useful for diagnostics even when dynamic mode is off.

**Primary recommendation:** Implement exactly as CONTEXT.md prescribes. The only deltas this research surfaces are: (a) a minor naming fix for strace `--exec` in the denylist, (b) explicit empirical capability-probe verification of `unshare --net` (because seccomp-unconfined is the load-bearing assumption), (c) document that ltrace's packaged version is from 2015 and is essentially unmaintained (the orchestrator skill should prefer strace where possible), and (d) add a sessions/ package import-migration test plan to detect any Phase 8/9 callers that broke during the refactor.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

Source: CONTEXT.md `<decisions>` block, 80+ explicit decision IDs. The planner MUST honor every "D-XX" entry verbatim. The following enumerated decisions are LOCKED and are not subject to research alternatives:

- **D-01..D-03:** `sessions.py` is refactored into a `sessions/` package with `_base.py`, `r2.py`, `gdb.py`. `SessionRegistry` becomes kind-aware (`kind="r2"|"gdb"`) with a shared cap of 8 (combined). `BaseSession` dataclass holds kind-agnostic fields; `R2Session` and `GdbSession` subclass it.
- **D-04..D-10:** gdb launches with `gdb --interpreter=mi3 --quiet --nx --nh <sample>` wrapped in `unshare --net --ipc --uts --`. Mandatory init batch lists 10 `-gdb-set` commands. Per-session random sentinel `__MARE_END_<8hex>__` via `-data-evaluate-expression`. Strict MI-prefix allowlist + denylist regex. 12-key result dict + gdb-session extensions. Per-command timeout 60 s, open timeout 30 s (env overridable).
- **D-DYN-NET-01..03:** Mandatory per-call `unshare --net --ipc --uts --` for every dynamic-mode subprocess. No loopback inside netns. No opt-out in v1.1.
- **D-DYN-PROF-01..04:** Hybrid named-profile + `extra_args` allowlist model. Strace profiles (file_io, network, process, signals, file_network_process, all, summary). Ltrace profiles (library_calls, system_only, library_and_system, library_count_summary). Qemu-user profiles (simple, syscall_strace, singlestep_asm, page_faults, all_trace). Per-arg allowlist regex + denylist of `-o / -D / --daemonize / --detach / -p / --attach / --output-separately / --exec`.
- **D-DYN-DISPATCH-01..02:** All 3 trace tools dispatch through `start_tool_job` (no `wait=True` shortcut). gdb is the only session-style dynamic primitive.
- **D-DYN-CAP-PROBE-01..02:** Capability probe runs once at lifespan startup (unconditional). `DynamicCapabilities` dataclass with `ptrace_scope`, `ptrace_traceme_works`, `binfmt_misc_mounted`, `qemu_architectures`, `netns_feasible`, etc. Never raises. Tools return structured `{error, missing, hint}` on capability-missing.
- **D-DYN-FLAG-01..03:** `run_docker.sh --dynamic` exports `MCP_GATEWAY_DYNAMIC_TOOLS=1`. Compositional with `--remote`; hard-error if passed without `--remote`. No `--dynamic-and-allow-net` in v1.1.
- **D-DYN-JOB-01..03:** Three `JobToolSpec` entries (strace, ltrace, qemu_user) registered at `dynamic.py` import. Default timeouts 900 s for strace/ltrace, 1800 s for qemu_user. Post-terminal hook for follow-fork stray reap (extends `JobToolSpec` dataclass with a new optional field).
- **D-DYN-TOOL-01..03:** Seven `@mcp.tool()` handlers in `tools/dynamic.py` (run_strace, run_ltrace, run_qemu_user, open_gdb_session, gdb_exec, close_gdb_session, get_dynamic_capabilities). Disclaimer string on every docstring (regression-tested).
- **D-DYN-IMPORT-01..02:** Strict import graph (sessions/_base.py is leaf; tools/dynamic.py imports sessions + dynamic + tools.case_dirs + tools.samples ONLY). `register_job_tool` must be a public callable.
- **D-DYN-ENV-01:** Five new env vars (`MCP_GATEWAY_DYNAMIC_TOOLS`, `MCP_GATEWAY_GDB_OPEN_TIMEOUT_S`, `MCP_GATEWAY_GDB_CMD_TIMEOUT_S`, `MCP_GATEWAY_DYN_REAP_DEPTH`, `MCP_GATEWAY_DYN_PROBE_TIMEOUT_S`). Existing Phase 8 env vars carry forward unchanged.
- **D-DYN-TEST-01..07:** Six test files. Env-gate regression. Allowlist matrix. Netns enforcement. Probe fail-safe. Follow-fork reap. Disclaimer presence.

### Claude's Discretion

Per CONTEXT.md `<decisions>` § "Claude's Discretion (within these constraints)":

- Exact WARN log string wording (structure locked).
- Whether `reap_followfork_strays` is a method on `Job` or a free function in `dynamic.py` (recommend free function — keeps Phase 9 D-22 drain ownership clean).
- Whether `STRACE_PROFILES` lives module-level or in `dynamic/_profiles.py` (recommend module-level — only 3 dicts).
- Whether `sessions/__init__.py` does explicit name-by-name re-export or `from .r2 import *` (recommend explicit — easier audit).
- Whether `get_dynamic_capabilities()` returns dataclass-as-dict directly or wraps (recommend direct).
- Whether `open_gdb_session` accepts `follow_fork_mode="child"` (recommend YES).
- Whether `gdb` is wrapped with `gosu agent` / setpriv (recommend NO — needs SYS_PTRACE, netns wrap provides isolation).
- The exact `gdb` argv: verify `--nh` works on the container's gdb (Kali ships gdb 13+, supports `--nh` since gdb 9). Pre-9.0 fallback: `-iex "set auto-load no"`.
- Whether `tools/dynamic.py` defines coroutines module-level or inside `register(mcp)` (recommend module-level per Phase 10 D-19 / Phase 8 D-23).
- Whether to keep a `MCP_GATEWAY_DYNAMIC_TOOLS=force_enable_in_tests` test bypass (recommend NO — monkeypatch is cleaner).

### Deferred Ideas (OUT OF SCOPE)

Per CONTEXT.md `<deferred>` block — DO NOT plan or implement:

- `allow_network=True` per-call opt-in (v1.2)
- Mount-namespace isolation for dynamic subprocesses (v1.2)
- Coverage-guided dynamic / fuzzing hooks (afl/libFuzzer)
- Memory snapshot tooling (Volatility)
- Full-VM / kernel-mode dynamic
- Per-`Mcp-Session-Id` keying of gdb sessions / dynamic jobs (v1.2)
- `job_specs/` package refactor (defer until >10 specs)
- CLI-mode gdb support (MI3-only)
- Auto-registering binfmt_misc handlers from inside the container (requires `--privileged`)
- Persistent named netns at gateway start (rejected in favor of per-call unshare)
- `run_strings` over dynamic-mode outputs (REQUIREMENTS Out of Scope)
- Shell escape via gdb python / source / ! (HARD-BLOCKED, not deferred)
- Sandboxed sample-execution with eBPF / bpftrace
- Replay-from-trace (rr, gdb record)
- Per-`Mcp-Session-Id`-scoped dynamic capabilities (capabilities are container-wide)
- CURRENT_STATE.json dynamic-mode marker writing (Phase 12 responsibility)

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DYN-01 | Dynamic tools registered iff `MCP_GATEWAY_DYNAMIC_TOOLS=1` at startup; `tools/list` does not advertise them when off. | Confirmed feasible via env-gated conditional import in `tools/__init__.py::register_all_tools` (the pattern Phase 9/10 ship-with-import already uses). `EXPECTED_TOOLS` test parametrized by env var: 54 (off) vs 61 (on). [VERIFIED: codebase grep — `mcp-gateway/tests/test_tool_list.py:43`]. |
| DYN-02 | `./run_docker.sh --dynamic` enables dynamic mode end-to-end (env var set, CURRENT_STATE.json marks mode, dynamic-mode defaults applied). | Phase 11 owns ONLY the env-var export + container-side gate. `CURRENT_STATE.json` write is a Phase 12 orchestrator-skill task (CONTEXT.md D-DYN-CAP-CURRENTSTATE explicit). Flag parsing pattern mirrors Phase 3's `--remote` (`run_docker.sh:12`). [VERIFIED: codebase grep]. |
| DYN-03 | `run_strace` / `run_ltrace` with allowlisted argv profiles; output to `case_dir/dynamic/`; default no-net via per-call `unshare --net`. | strace 6.8 (Ubuntu noble), gdb 15.1, qemu-user-static 8.2.2 confirmed available [VERIFIED: apt-cache policy]. `unshare --net` requires CAP_SYS_ADMIN OR `seccomp=unconfined` [CITED: docs.docker.com/engine/security/seccomp]. CLAUDE.md declares `seccomp=unconfined` posture. **Risk:** if seccomp ever gets restored, every dynamic call fails — the netns capability probe catches this. |
| DYN-04 | `run_qemu_user` for cross-arch user-mode; binfmt drift detected via `get_dynamic_capabilities()`; output to `case_dir/qemu/`. | `qemu-user-static` package installs `/usr/bin/qemu-<arch>-static` for ~10 architectures. binfmt_misc entries appear under `/proc/sys/fs/binfmt_misc/qemu-<arch>` with `enabled` and `flags: ...F...` lines [CITED: docs.kernel.org/admin-guide/binfmt-misc.html, github.com/multiarch/qemu-user-static]. `F` flag is critical for container mount-namespace compatibility. |
| DYN-05 | Interactive gdb via `open_gdb_session` → `gdb_exec` → `close_gdb_session` using `gdb --interpreter=mi3`; MI-prefix allowlist prevents `python <code>` escape. | mi3 is the current MI version (gdb 9.1+); Kali/Ubuntu ship gdb 15 [VERIFIED: apt-cache policy gdb → 15.1]. `-interpreter-exec console "..."` IS the canonical sandbox escape [CITED: sourceware.org/gdb/current/onlinedocs/gdb.html/Interpreters.html]. CONTEXT.md D-07 denylist covers this exactly + python/pi/source/shell/!/add-symbol-file/dump/set inferior-tty/-target-* . |
| DYN-06 | `get_dynamic_capabilities()` probes and reports `ptrace_scope`, `binfmt_misc` status, qemu archs, netns feasibility at startup. | All probes are cheap (<200 ms). yama ptrace_scope 0..3 semantics confirmed [CITED: kernel.org/doc/Documentation/security/Yama.txt]. Empirical probe via `unshare --net true` round-trip is essential because the capability surface depends on three independent layers (kernel + Docker seccomp + Docker --cap-add). |
| DYN-07 | Long-running tools use JOBS; output to `case_dir/{dynamic,qemu}/`; sample resolved via sha256 from `uploads/` or existing `case_dir`; follow-fork process groups reaped via `/proc/<runner_pid>/task/*/children`. | All 3 trace tools dispatch via `start_tool_job` (`jobs.py:296 register_job_tool` is public [VERIFIED: code read]). Sample resolution uses Phase 6/7's `tools/samples.py::resolve_sample` already. `/proc/<pid>/task/*/children` scan is the canonical Linux mechanism [CITED: skullsecurity.org/2023/fork-off-three-ways-to-deal-with-forking-processes]. Grandchildren that `setsid()` escape `killpg` and need explicit per-pid SIGKILL — CONTEXT.md D-DYN-JOB-03 covers this with depth-8 recursive walk. |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

| Directive | Source | How Research Respects It |
|-----------|--------|--------------------------|
| Backward compatibility: "agent inside container" mode unchanged | CLAUDE.md §Constraints | Phase 11 is purely additive; env-gate default-off keeps the v1.0 tool surface byte-identical. |
| IDA Pro / Binary Ninja licenses never baked into images | CLAUDE.md §Constraints | Phase 11 touches gdb/strace/ltrace/qemu-user only — no commercial RE tooling. |
| Container elevated capabilities: `SYS_PTRACE`, `seccomp=unconfined` | CLAUDE.md §Constraints | This is the load-bearing posture. ptrace works only when ptrace_scope <= 1 AND container has SYS_PTRACE. `unshare --net` works only when seccomp is unconfined OR container has CAP_SYS_ADMIN. **Phase 11's capability probe verifies both empirically.** |
| Bearer token auth + Docker network isolation | CLAUDE.md §"Authentication & Security" | Dynamic tools inherit the same bearer auth (Phase 2 D-12). The disclaimer (CONTEXT.md D-DYN-TOOL-02) repeats the SESS-05 limitation that sessions are shared across same-token clients. |
| Streamable HTTP transport via mcp-gateway custom FastMCP | CLAUDE.md §Stack | Dynamic tools register via `@mcp.tool()` decorator like every other Phase 7+ surface — no transport-level changes. |
| `gsd:execute-phase` workflow gate | CLAUDE.md §"GSD Workflow Enforcement" | Phase 11 plans MUST be created via gsd-planner and executed via gsd-execute-phase. |

## Standard Stack

### Core (already provisioned by Kali / Phase 10 / Phase 6 base apt set)

| Tool | Version | Purpose | Provided By |
|------|---------|---------|-------------|
| gdb | >=13.0 (Kali) / 15.1 (Ubuntu noble) | MI3 interactive debugger | apt `gdb` [VERIFIED: apt-cache policy → 15.1-1ubuntu1~24.04.1 on Ubuntu noble] |
| strace | >=6.0 (Kali) / 6.8 (Ubuntu noble) | Syscall tracer | apt `strace` [VERIFIED: apt-cache policy → 6.8-0ubuntu2] |
| ltrace | 0.7.3 (only packaged version) | Library-call tracer | apt `ltrace` [VERIFIED: apt-cache policy → 0.7.3-6.4ubuntu3]. **WARNING: this is the 2015 upstream release; project is essentially unmaintained.** |
| qemu-user-static | >=8.0 (Kali) / 8.2.2 (Ubuntu noble) | Cross-arch user-mode emulator | apt `qemu-user-static` [VERIFIED: apt-cache policy → 1:8.2.2+ds-0ubuntu1.16] |
| unshare | from util-linux >=2.39 | Per-call netns wrapping | apt `util-linux` (Kali base) [VERIFIED: apt-cache policy → 2.39.3-9ubuntu6.5; host probe `unshare --version` → "from util-linux 2.39.3"] |

**Installation verification command for Wave 0:**

```bash
docker compose exec kali bash -c '
  for t in gdb strace ltrace unshare qemu-aarch64-static qemu-arm-static qemu-mips-static qemu-mipsel-static qemu-ppc-static qemu-ppc64-static qemu-i386-static qemu-riscv64-static; do
    command -v "$t" >/dev/null && echo "OK: $t -> $(command -v "$t")" || echo "MISSING: $t"
  done
  echo "---"
  cat /proc/sys/kernel/yama/ptrace_scope || echo "ptrace_scope: not readable"
  echo "---"
  ls /proc/sys/fs/binfmt_misc/qemu-* 2>/dev/null | head -20 || echo "binfmt_misc: no qemu registrations"
  echo "---"
  unshare --net true && echo "unshare-net: OK" || echo "unshare-net: BLOCKED"
'
```

### Supporting (existing — no new deps)

| Module | Phase | Purpose |
|--------|-------|---------|
| `mcp_gateway.runner.ReToolRunner` | 6 | 12-key result dict baseline (gdb_exec layers on this; trace tools go through JOBS which wraps internally) |
| `mcp_gateway.jobs.{BackgroundJobRegistry, JobToolSpec, JOB_TOOL_REGISTRY, register_job_tool}` | 9 | 3 dynamic-mode `JobToolSpec` entries register at `dynamic.py` import time |
| `mcp_gateway.sessions.{SessionRegistry, R2Session, BaseSession (new)}` | 8 → 11 refactor | Refactored to `sessions/` package; one registry, two kinds, shared cap 8 |
| `mcp_gateway.artifacts_io.{confine_to, ensure_subdir, tool_log_path, EXPANDED_CASE_SUBDIRS}` | 6 | `dynamic/` and `qemu/` subdirs already cataloged; lazy-created on first write |
| `mcp_gateway.tools.{samples.resolve_sample, case_dirs.resolve_case_dir}` | 7 | Sample sha256 resolution; case-dir resolution (DYN-07) |
| `mcp_gateway.session_state.SESSION_REGISTRY` | 8 | Reused; now holds both r2 and gdb sessions per D-02 |

### Alternatives Considered (and Rejected by CONTEXT.md)

| Instead of | Could Use | Why Not |
|------------|-----------|---------|
| `gdb --interpreter=mi3` | `gdb` CLI mode | Prompt framing ambiguous; MI3 record format is structured (Pitfall 6). [CITED: sourceware.org/gdb/current/onlinedocs/gdb.html/Interpreters.html — MI3 introduced GDB 9.1]. |
| `gdb --interpreter=mi3` | `gdb --interpreter=mi2` | mi3 stabilized record format and structured `-data-evaluate-expression` output. Kali ships gdb 13+. |
| pygdbmi for MI parsing | Hand-rolled best-effort parser per D-08 | One more dep; MI format is simple enough that line-by-line parsing into dicts is ~50 LoC. pygdbmi confirmed as reference [CITED: github.com/cs01/pygdbmi]. |
| Per-call `unshare --net` | Persistent named netns (`ip netns add mare-dynamic`) | Adds gateway-start coordination, new failure mode if netns missing. Per-call is what FEATURES/PITFALLS/ARCHITECTURE all converge on (CONTEXT.md D-DYN-NET-01 rationale). |
| `unshare --net` | Docker `--network=none` per subprocess | Requires docker-in-docker or compose orchestration per call — far heavier than a single argv prefix. |
| Mount-namespace isolation (`unshare --mount`) | Path-traversal guarding via `confine_to` | CAP_SYS_ADMIN cost; conflicts with case-dir reachability (REQUIREMENTS Out of Scope v1.1). |
| Sync `wait=True` for trace tools | All-JOBS dispatch | Bypasses log-cap / cancel / retention scaffolding. DYN-07 mandates JOBS. |
| Auto-register binfmt_misc from inside the container | Probe binfmt and report only | Requires `--privileged`; breaks default posture. Operator-side setup is a Phase 12 doc item. |

## Architecture Patterns

### Recommended Project Structure (matches CONTEXT.md D-01 verbatim)

```
mcp-gateway/src/mcp_gateway/
├── dynamic.py                 # NEW: primitive layer (capability probes, argv builders, wrap_netns, follow-fork reap, JobToolSpec registrations)
├── sessions/                  # PROMOTED from sessions.py per Phase 8 D-05
│   ├── __init__.py            # re-exports every Phase 8 public symbol verbatim
│   ├── _base.py               # SessionRegistry, BaseSession, env-var helpers, sentinel + ANSI helpers
│   ├── r2.py                  # R2Session + r2 driver (moved verbatim from sessions.py)
│   └── gdb.py                 # NEW: GdbSession + gdb-MI3 driver + MI allowlist + denylist
├── tools/
│   └── dynamic.py             # NEW: 7 MCP @mcp.tool() handlers (conditional import in tools/__init__.py)
└── (existing modules unchanged: runner, jobs, app, artifacts_io, ...)
```

### Pattern 1: Env-Gated Conditional Registration (CONTEXT.md D-DYN-IMPORT-01 / CONTEXT.md integration points)

**What:** A new tool surface registered iff `MCP_GATEWAY_DYNAMIC_TOOLS=="1"` at startup. Achieved by conditional import in `tools/__init__.py::register_all_tools`.

**When to use:** Any future env-gated mode that should leave both `tools/list` and `JOB_TOOL_REGISTRY` byte-identical when off.

**Example:**

```python
# tools/__init__.py — add ONE conditional block AFTER jobs.register(mcp), BEFORE backend_passthrough.register(mcp)
def register_all_tools(mcp: FastMCP) -> None:
    # ... (existing 18 lines unchanged) ...
    jobs.register(mcp)
    extract.register(mcp)
    # Phase 11 D-DYN-IMPORT-01: env-gated dynamic surface
    if os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1":
        from . import dynamic as dynamic_tools
        dynamic_tools.register(mcp)
    backend_passthrough.register(mcp)
```

**Verification:** [VERIFIED: codebase read of `tools/__init__.py` — current 66 lines, ordering matches D-DYN-IMPORT-01 expectation; one new conditional block fits cleanly].

### Pattern 2: Argv-Builder + JobToolSpec Ship-With Pattern (CONTEXT.md D-DYN-JOB-01)

**What:** Phase 9 / 10's idiom — a primitive module registers its `JobToolSpec` at import time via `register_job_tool(spec)`. Phase 11 adds 3 specs from `dynamic.py`.

**When to use:** Any new long-running tool that needs JOBS-managed dispatch.

**Example (verbatim from Phase 9 capa precedent):**

```python
# dynamic.py
from mcp_gateway.jobs import JobToolSpec, register_job_tool

STRACE_SPEC = JobToolSpec(
    name="strace",
    slug="strace",
    build_argv=build_strace_argv,
    default_timeout_s=900.0,
    progress_parser=None,
    kwargs_schema={
        "sample":     {"type": "string", "required": True},
        "profile":    {"type": "string", "required": True, "enum": list(STRACE_PROFILES)},
        "extra_args": {"type": "array", "items": {"type": "string"}, "max_items": 16},  # Note: array shape not in current _validate_kwargs
        "run_argv":   {"type": "array", "items": {"type": "string"}, "max_items": 32},
    },
    description="Linux strace under per-call netns (no-net). Profile-driven argv. "
                "Output: case_dir/dynamic/<ts>-strace-<rand4>.txt",
)

for spec in (STRACE_SPEC, LTRACE_SPEC, QEMU_USER_SPEC):
    register_job_tool(spec)
```

**[VERIFIED: codebase read of `jobs.py:296-313`]** `register_job_tool` is already a public symbol; no Phase 11 promotion needed.

**Pitfall:** Current `_validate_kwargs` only handles `integer / string / boolean` schema rules (`jobs.py:254-290`). Phase 11's `kwargs_schema` introduces `"type": "array"` for `extra_args` and `run_argv`. The planner must either:
- (a) extend `_validate_kwargs` with array handling, OR
- (b) drop the array schema entries and validate inside the `build_argv` function (CONTEXT.md D-DYN-PROF-02 already specifies the validation logic; doing it in `build_argv` is consistent with how `extra_args` allowlist regex works).
Recommendation: **(b)** — keeps `_validate_kwargs` simple and matches the Phase 10 builder pattern.

### Pattern 3: Sentinel-Framed Subprocess Sessions (Phase 8 D-04 → Phase 11 D-06)

**What:** Per-session random 8-hex sentinel `__MARE_END_<rand8>__` emitted after every user command to disambiguate end-of-output from interleaved async records.

**When to use:** Any long-lived stdin/stdout-driven subprocess where the application's prompt is ambiguous.

**Example (gdb-MI3 specialization):**

```python
# sessions/gdb.py
import secrets

class GdbSession(BaseSession):
    # ... fields ...
    async def exec_one(self, cmd: str, *, timeout: float) -> tuple[bytes, bool]:
        sentinel_token = self.sentinel  # set once at open(): f"__MARE_END_{secrets.token_hex(4)}__"
        # Send user cmd then gateway-side sentinel emitter — quotes are critical
        self.proc.stdin.write(cmd.encode("utf-8") + b"\n")
        self.proc.stdin.write(
            f'-data-evaluate-expression "\\"{sentinel_token}\\""\n'.encode()
        )
        await self.proc.stdin.drain()
        # gdb-MI3 returns: ^done,value="\"__MARE_END_<rand8>__\""
        terminator = f'^done,value="\\"{sentinel_token}\\""'.encode()
        buf = bytearray()
        try:
            while True:
                line = await asyncio.wait_for(
                    self.proc.stdout.readuntil(b"\n"),
                    timeout=timeout,
                )
                # Strip trailing newline + optional carriage return for compare
                if line.rstrip(b"\r\n") == terminator:
                    return bytes(buf), False
                buf.extend(line)
        except asyncio.TimeoutError:
            return bytes(buf), True
```

**Source for the framing approach:** [CITED: sourceware.org/gdb/current/onlinedocs/gdb.html/Interpreters.html — `interpreter-exec mi` and result-record format; the `^done,value="..."` shape is the documented MI3 result class].

### Anti-Patterns to Avoid

- **Don't terminate on `(gdb) \n` prompt** — MI3 emits this after every record group, including async stop notifications that fire during long-running commands (e.g., `-exec-continue` followed by a breakpoint hit). Naive `readuntil(b"(gdb) \n")` will terminate too early when an async record interleaves. The per-command sentinel via `-data-evaluate-expression` is unambiguous because it only emits ONCE per user command (after the previous command's `^done`). [CITED: pygdbmi source — distinguishes `result` records from `notify` async records]
- **Don't trust the `unshare` syscall is available** — Docker default seccomp profile blocks `unshare` unless container has CAP_SYS_ADMIN. The capability probe is the only reliable detection. [CITED: docs.docker.com/engine/security/seccomp].
- **Don't trust binfmt_misc lazy-load** — entries registered without the `F` flag require the qemu binary to be visible inside the calling process's mount namespace. Always check for `F` in the `flags:` line. [CITED: docs.kernel.org/admin-guide/binfmt-misc.html].
- **Don't rely on `killpg` alone for follow-fork cleanup** — grandchildren that call `setsid()` get a fresh session and pgid; they survive `killpg(orig_pgid, SIGKILL)`. Recursive scan + per-pid SIGKILL is required. [CITED: skullsecurity.org/2023/fork-off-three-ways-to-deal-with-forking-processes].
- **Don't `pi` or `interpreter-exec console` allow** — these are the two CLI/MI escape paths to gdb's embedded Python. CONTEXT.md D-07 denylist already covers both.
- **Don't use `--exec` in strace argv** — strace has no `--exec` flag. The actual flag is `-b execve` (`--detach-on=execve`). CONTEXT.md D-DYN-PROF-02 lists `--exec` in `_DENIED_EXTRA_ARG_FLAGS` — this entry is a no-op safety measure but is misleading; the planner should rename to `-b` and `--detach-on` to be effective.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Process-group cleanup | Custom signal-handler tree-walk | `start_new_session=True` + `os.killpg(pgid, SIGKILL)` + `/proc/<pid>/task/*/children` for setsid escapees | Phase 6 D-17 already does the spawn side; Phase 11 adds the recursive `/proc` scan because setsid grandchildren escape pgid scope. |
| Network isolation | Per-process iptables rules | `unshare --net --ipc --uts -- <argv>` | One syscall, ENETUNREACH cleanly, no host-side state. [CITED: PITFALLS.md §9]. |
| Sample sha256 resolution | Custom hash lookup | `mcp_gateway.tools.samples.resolve_sample` (Phase 7) | Already validates `uploads/` and existing case_dir provenance; returns `(sha256, abs_path)`. |
| Case-dir path resolution | Custom path math | `mcp_gateway.tools.case_dirs.resolve_case_dir` (Phase 7) | Existing convention; collision-checks for path traversal. |
| Tool-log filename generation | Custom timestamp + rand | `mcp_gateway.artifacts_io.tool_log_path(case_dir, slug)` (Phase 6 D-09) | `tool-logs/<UTC>Z-<slug>-<rand4>.txt` format already canonical. |
| MI parsing | A new pygdbmi-shaped library | Best-effort line-by-line parser per CONTEXT.md D-08 (~50 LoC) | One more dep doesn't justify itself; MI3's `^done,key=value,...` parses cleanly with stdlib regex. |
| ANSI strip / UTF-8 truncate | New code | Hoist Phase 8 `sessions.py` helpers (`strip_ansi`, `truncate_for_response`) into `sessions/_base.py` | Same code used by r2 and gdb; one place, two callers. |
| MCP tool result dict shape | Custom serialization | 12-key Phase 6 D-03 base + session/job extensions per Phase 8 D-11 / Phase 9 D-19 | Stable invariant across phases; verified by `EXPECTED_TOOLS` and result-shape tests. |
| JobToolSpec dispatch | Custom subprocess orchestration | `mcp_gateway.jobs.start_tool_job(tool, kwargs, case_dir, timeout)` (Phase 9) | Already handles SIGTERM-grace-SIGKILL ladder, head/tail ring buffers, log cap, cancel propagation, drain task ownership. |
| binfmt_misc auto-registration | Re-implement | Probe and report only; document host-side `update-binfmts --enable` / `multiarch/qemu-user-static --reset -p yes` | Auto-register needs `--privileged`; breaks the v1.1 posture. |

**Key insight:** Phase 11 is plumbing on top of plumbing — the value-add is the seven tools, their argv builders, and the capability probe. Every layer below (subprocess spawning, drain, cancel, file capture, sample resolution, case dirs, session registry) is reused verbatim from Phases 6-10.

## Common Pitfalls

### Pitfall 1: gdb async stop records interleave with `^done`

**What goes wrong:** Operator issues `-exec-continue`; gdb runs the inferior; inferior hits a breakpoint; gdb emits an async `*stopped` notify record BEFORE the `^done` for the original `-exec-continue` command (the continue itself has run-to-completion semantics that emit `^running` then `*stopped`). If gdb_exec naively reads until `(gdb) \n`, it may capture the async record but miss subsequent state changes.

**Why it happens:** MI3's design — async records (`*`-prefixed) are interleaved with sync result records (`^`-prefixed) to give frontends real-time updates.

**How to avoid:** Per-session random sentinel emitted via a follow-up `-data-evaluate-expression` AFTER the user command. The sentinel's `^done` record only fires when gdb has processed the previous command's result record fully. [CITED: pygdbmi readme — distinguishes record types].

**Warning signs:** gdb_exec returns truncated output; subsequent commands return content from the previous one; the `(gdb) \n` literal appears in `stdout_head` of a command result.

### Pitfall 2: `unshare` syscall blocked by Docker default seccomp

**What goes wrong:** Operator runs `./run_docker.sh --remote --dynamic` on a host where the compose file ever drops `--security-opt seccomp=unconfined`. Every `run_strace` invocation fails with `unshare: unshare failed: Operation not permitted`.

**Why it happens:** Docker's default seccomp profile (`/etc/docker/seccomp.json`) blocks the `unshare` syscall unless the container has CAP_SYS_ADMIN. Container has SYS_PTRACE (per CLAUDE.md) but NOT CAP_SYS_ADMIN.

**How to avoid:** The capability probe MUST empirically test `unshare --net true` and surface a WARN. Tests must monkeypatch this probe to BOTH outcomes (feasible / blocked). The Wave 0 container-side smoke test must include `unshare --net true && echo OK` to fail fast at build time if the posture is wrong.

**Warning signs:** Capability probe reports `netns_feasible=False`; every `run_strace` call returns `{error: "dynamic capability unavailable", missing: ["netns"]}`.

[CITED: docs.docker.com/engine/security/seccomp]. [CITED: github.com/moby/moby/issues/42441 — "Reevaluate the default seccomp policy on clone and unshare"].

### Pitfall 3: setsid grandchildren escape killpg

**What goes wrong:** A sample under `strace -f` forks, child calls `setsid()` (which creates a fresh session and process group, detaching from the runner's pgid), then sleeps. When the strace job terminates and `killpg(orig_pgid, SIGKILL)` runs, the setsid grandchild survives. Over multiple analysis runs, the container accumulates zombie samples consuming PIDs and (if a real sample) potentially executing payload.

**Why it happens:** `setsid(2)` is explicitly designed to create a new session whose process group is NOT signaled by signals sent to the original session. This is the standard daemon-detachment idiom; samples that mimic daemons trigger it.

**How to avoid:** After `killpg(orig_pgid, SIGKILL)` and `proc.wait()`, recursively walk `/proc/<runner_pid>/task/*/children` (depth 8). For each PID encountered, check `/proc/<pid>/stat` — if alive AND its session ID matches the original pgid's session, or if it has any ancestor in the runner's task tree, SIGKILL it. CONTEXT.md D-DYN-JOB-03 specifies this as a `post_terminal_hook` extension to `JobToolSpec`.

**Warning signs:** `ps -ef | grep <sample_basename>` shows orphan processes after job termination. `reap_followfork_strays` log line `INFO: reaped N strays` with N > 0.

[CITED: skullsecurity.org/2023/fork-off-three-ways-to-deal-with-forking-processes — three approaches to forking-process cleanup]. [CITED: man7.org/linux/man-pages/man1/strace.1.html — `--kill-on-exit` flag added in strace 5.x is a defense-in-depth complement].

### Pitfall 4: ltrace 0.7.3 is unmaintained

**What goes wrong:** `run_ltrace` on a modern statically-linked or musl-libc binary returns no output or crashes with "Couldn't find any function symbol" or similar. Sample runs to completion unhooked, leaving the orchestrator with no library-call trace.

**Why it happens:** ltrace 0.7.3 was released in May 2013. The packaged version on Debian/Ubuntu/Kali (`0.7.3-6.4ubuntu3` on Ubuntu noble) has only minor patches; the project has had effectively no upstream development since 2015. It does not handle modern ELF features (some forms of PIE, IFUNC, lazy-binding via DT_FLAGS_1) reliably.

**How to avoid:** Document the limitation in the `run_ltrace` docstring. The orchestrator skill (Phase 12) should prefer `run_strace` with `trace=process,signal,file,desc` for behavior coverage when ltrace fails. Mark the ltrace round-trip test as `slow` and `skip if ltrace doesn't produce output on a known-good fixture`.

**Warning signs:** Empty `stdout_head` from `run_ltrace` jobs; ltrace stderr contains `Couldn't find...` or `Can't attach to PID...` despite `ptrace_traceme_works=True`.

[VERIFIED: apt-cache policy — 0.7.3-6.4ubuntu3 is the only version available]. [ASSUMED: The project's lack of upstream commits is a well-known issue in the RE community but I did not exhaustively verify via the upstream Git repo in this research.]

### Pitfall 5: qemu-user-static multi-threaded sample emulation is unreliable

**What goes wrong:** A multi-threaded sample (e.g., a worker-pool malware payload) under `run_qemu_user` exhibits non-deterministic crashes, signal-delivery glitches, or hangs. The sample doesn't reproduce the same behavior twice.

**Why it happens:** "Multithreaded guest processes are unreliable under qemu linux-user mode, even ignoring signal handling related races." [CITED: bugs.launchpad.net/qemu/+bug/1319100].

**How to avoid:** Document the limitation in the `run_qemu_user` docstring. For multi-threaded samples, the analyst should prefer `run_strace`/`run_ltrace` on a native-arch sample OR full-VM (out of scope for v1.1). Add a `qemu_known_limitations` field to the capability probe noting "multi-thread + signals = unreliable".

**Warning signs:** Repeated `run_qemu_user` jobs on the same sample produce different results; SIGSEGV in qemu's signal-delivery path; sample crashes that don't reproduce natively.

[CITED: bugs.launchpad.net/qemu/+bug/1319100 — qemu-arm-static signal handling]. [CITED: qemu-project.gitlab.io/qemu/user/main.html — official user-mode emulation docs].

### Pitfall 6: binfmt_misc `F` flag is required for in-container exec

**What goes wrong:** `run_shell("./mips_payload")` returns "exec format error" even though `qemu-mips-static` is installed in the container. Sample never runs.

**Why it happens:** Without the `F` (fix-binary) flag, binfmt_misc resolves the interpreter path lazily — at exec time, in the calling process's mount namespace. When the container's mount namespace doesn't contain `/usr/bin/qemu-mips-static` (because the host registered the binfmt entry pointing to the host's `/usr/bin/qemu-mips-static` which isn't visible inside the container), the lazy lookup fails.

**How to avoid:**
1. Capability probe checks the `flags:` line of each `/proc/sys/fs/binfmt_misc/qemu-*` file for the `F` character. If missing, surface a WARN.
2. The PRIMARY path for cross-arch sample execution is `run_qemu_user(arch="mips", sample=...)` — explicit `qemu-mips-static <sample>` argv that does NOT rely on binfmt at all. This works whether or not binfmt is set up.
3. Document in the operator-facing setup notes (Phase 12): "if you want `run_shell('./mips_binary')` to work without `qemu-<arch>-static` prefix, run on the HOST: `docker run --rm --privileged multiarch/qemu-user-static --reset -p yes` BEFORE starting the gateway container."

**Warning signs:** `qemu_architectures` tuple in the capability probe is empty or short, despite `qemu-*-static` binaries being present; `run_shell` on a foreign-arch binary fails with "exec format error".

[CITED: docs.kernel.org/admin-guide/binfmt-misc.html — F flag described as "opens the binary as soon as the emulation is installed"]. [CITED: github.com/multiarch/qemu-user-static — registers with `flags: F`].

### Pitfall 7: yama ptrace_scope is HOST-controlled, not container-controlled

**What goes wrong:** Operator sets `--cap-add SYS_PTRACE` and `--security-opt apparmor=unconfined` on the container, but ptrace still fails. The capability probe reports `ptrace_traceme_works=False` even though `ptrace_scope` is 0 inside the container.

**Why it happens:** `/proc/sys/kernel/yama/ptrace_scope` is the same kernel sysctl visible from inside a non-privileged container — the container shares the host kernel and the yama LSM hooks fire host-side. If the host has `ptrace_scope=2` or `=3`, even a CAP_SYS_PTRACE-equipped container is denied. Containerized `echo 0 > /proc/sys/kernel/yama/ptrace_scope` fails with EACCES (the proc file is host-RW).

**How to avoid:** The probe must read `/proc/sys/kernel/yama/ptrace_scope` AND empirically test PTRACE_TRACEME via a forked child. The error-dict hint must point to the HOST: `host operator: sudo sysctl -w kernel.yama.ptrace_scope=0`. Do NOT instruct the operator to `echo` inside the container.

**Warning signs:** Capability probe reports `ptrace_scope=2` or `=3` and `ptrace_traceme_works=False`; every strace/ltrace/gdb tool returns the structured-error dict with `missing: ["ptrace"]`.

[CITED: kernel.org/doc/Documentation/security/Yama.txt — defines the four scope values]. [CITED: docs.kernel.org/admin-guide/LSM/Yama.html — explains host-namespace control].

### Pitfall 8: Phase 8's `_validate_kwargs` doesn't handle array schemas

**What goes wrong:** `start_tool_job("strace", kwargs={"sample": "...", "profile": "all", "extra_args": ["-e", "trace=open"]})` fails — `_validate_kwargs` sees the `"type": "array"` rule in the spec, doesn't have a branch for it, and silently does nothing (falls through; in fact, the entire `extra_args` validation passes through with no checks).

**Why it happens:** [VERIFIED: codebase read of `mcp-gateway/src/mcp_gateway/jobs.py:254-290`] — only `integer / string / boolean` types have validation branches. Unknown types fall through. CONTEXT.md D-DYN-JOB-01 specifies `"type": "array"` schema for `extra_args` and `run_argv` but this is not validated by the registry-level helper.

**How to avoid:** Validate `extra_args` and `run_argv` INSIDE `build_strace_argv` / `build_ltrace_argv` / `build_qemu_user_argv` against `EXTRA_ARGS_ALLOWLIST_RE` and `_DENIED_EXTRA_ARG_FLAGS` per CONTEXT.md D-DYN-PROF-02. This is consistent with how the `extra_args` allowlist regex works (per-arg, applied at builder time). The kwargs_schema entries can REMAIN in `JobToolSpec` for self-documentation, but the validation logic lives in `build_argv`. Alternatively, the planner may extend `_validate_kwargs` with an `array` branch — but this couples Phase 11's needs into Phase 9's primitive.

**Warning signs:** Test `test_strace_extra_args_blocks_shell_metachar` fails because no validation occurs; or `start_tool_job` accepts garbage kwargs and the builder crashes later with cryptic IndexError.

### Pitfall 9: strace `--exec` is not a real flag

**What goes wrong:** CONTEXT.md D-DYN-PROF-02 includes `"--exec"` in `_DENIED_EXTRA_ARG_FLAGS`. An operator who reads the denylist may think strace has an `--exec` flag they're being blocked from; but the actual flag they're worried about is `-b execve` / `--detach-on=execve` (which causes strace to detach from the tracee at execve).

**Why it happens:** Likely a misremembering during context-gathering of the `--detach-on=execve` semantic. [CITED: man7.org/linux/man-pages/man1/strace.1.html — strace flag inventory verified; no `--exec` flag exists in strace 6.8].

**How to avoid:** Update the planner's denylist to include `"-b"` and `"--detach-on"` (the actual flag names). Optionally drop `"--exec"` since it's a no-op anyway. This is a minor planner-time correction; no design change.

**Warning signs:** None at runtime — `--exec` would just be rejected as an unknown strace flag by strace itself. The denylist remains correct in spirit; only the spelling needs work.

### Pitfall 10: gdb's `-iex` / `-ex` / `-x` are pre-init command sources

**What goes wrong:** Even with `--nx --nh`, gdb may execute `-iex` / `-ex` / `-x` flag-arguments BEFORE the MI loop is fully online — and these flags can execute arbitrary gdb commands including `python ...`. If a future code change adds any of these flags (perhaps in a "convenience init" feature), the MI allowlist is bypassed.

**Why it happens:** `-iex` runs commands before reading any init files; `-ex` runs after init files; `-x <file>` sources a file. None go through the MI allowlist because they fire at gdb startup before stdin is processed.

**How to avoid:** The gdb argv (D-04) MUST NOT include `-iex` / `-ex` / `-x`. Add a regression test that greps the constructed argv for these flags and fails if any appear. Document in `sessions/gdb.py` module docstring: "DO NOT add -iex/-ex/-x to the gdb argv — they bypass the MI allowlist."

**Warning signs:** Code review flag — any PR that adds `-iex` / `-ex` / `-x` to the gdb argv constructor.

### Pitfall 11: sessions/ refactor breaks Phase 8 test imports

**What goes wrong:** After moving `sessions.py` → `sessions/__init__.py + r2.py + _base.py`, Phase 8's tests fail with `ImportError: cannot import name 'X' from 'mcp_gateway.sessions'` or `AttributeError`.

**Why it happens:** Python's module-vs-package import semantics: `from mcp_gateway.sessions import X` works if `X` is in `sessions/__init__.py`. But module-level operations like `import mcp_gateway.sessions; sessions.X` or `importlib.reload(sessions)` may have subtle differences if `X` is actually defined in `sessions/r2.py` and only re-exported. The Phase 9 conftest uses `importlib.reload(mcp_gateway.jobs)` and `importlib.reload(mcp_gateway.tools.jobs)` (per STATE.md [Phase 09 Plan 04] entry) — Phase 11's refactor must verify that `importlib.reload(mcp_gateway.sessions)` propagates reload state to the submodules.

**How to avoid:**
1. `sessions/__init__.py` uses explicit `from .r2 import R2Session, ...` AND `from ._base import SessionRegistry, ...` (NOT `from .r2 import *`) so reload semantics are deterministic.
2. Add `test_sessions_package.py` (CONTEXT.md D-DYN-TEST-01 mentions this) that asserts:
   - `from mcp_gateway.sessions import SessionRegistry, R2Session, _DANGEROUS_R2_CMD_RE, MAX_SESSIONS, SESSION_IDLE_S, REAPER_INTERVAL_S, R2_CMD_TIMEOUT_S, SESSION_OPEN_TIMEOUT_S` ALL succeed.
   - `mcp_gateway.sessions.R2Session is mcp_gateway.sessions.r2.R2Session` (no duplicate class definitions).
   - `importlib.reload(mcp_gateway.sessions)` does not raise.
3. Run the FULL existing Phase 8 test suite (`tests/test_sessions.py`, `tests/test_r2_sessions.py`, `tests/test_artifacts_io.py`) without modification — every test must continue to pass.

**Warning signs:** Phase 8 tests fail after the refactor; `importlib.reload(mcp_gateway.sessions)` raises; `R2Session` has duplicate class instances across `r2.py` and a stale `sessions.py`.

### Pitfall 12: capability probe runs BEFORE backend connect — backend may not be available

**What goes wrong:** The `dynamic.probe_all()` call inside `lifespan` runs `subprocess.run(["unshare", "--net", "true"], timeout=3)` AND `subprocess.run(["gdb", "--version"], timeout=3)`. If gdb is missing (because the Dockerfile changed and removed it), the probe completes (returning `gdb_path=None`) — but startup logs may not surface this clearly to the operator.

**Why it happens:** Probe is best-effort (never raises). Missing tools just become `None` in the dataclass.

**How to avoid:** The startup log block (D-DYN-PROBE-LOG) MUST print one `WARN:` line per missing critical tool. The planner test must assert that probe-with-monkeypatched-which-gdb=None produces a WARN log line.

**Warning signs:** Operator runs `--dynamic`, all run_strace calls return "missing: ['ptrace']" or similar, but no WARN appeared at startup explaining why.

## Runtime State Inventory

> Phase 11 is primarily an additive code change but it includes a `sessions.py` → `sessions/` package refactor. The refactor is rename-only (no behavior change) but it touches existing import sites. This inventory covers what could break.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — no persistent state stored under any name containing "sessions" or "dynamic" that would survive the refactor; the in-memory `SessionRegistry` is per-process. The `dynamic/` and `qemu/` case_dir subdirectories already exist per Phase 6 D-16 catalog. | None. |
| Live service config | None — gateway is the only "service" and it is the thing being changed. Compose / Docker config: `MCP_GATEWAY_DYNAMIC_TOOLS` is a new env var, passes through compose verbatim like `MCP_GATEWAY_ENABLED`. No compose.yaml edit. | Verify `compose.yaml` passes through env vars implicitly (it does — confirmed via Phase 3 pattern). |
| OS-registered state | binfmt_misc registrations live in `/proc/sys/fs/binfmt_misc/qemu-*` — these are HOST-controlled, not container-controlled. They are NOT changed by Phase 11; only probed. If the host has none registered, qemu-arch list will be empty (handled gracefully). | None — Phase 11 reads only. |
| Secrets/env vars | NEW: `MCP_GATEWAY_DYNAMIC_TOOLS`, `MCP_GATEWAY_GDB_OPEN_TIMEOUT_S`, `MCP_GATEWAY_GDB_CMD_TIMEOUT_S`, `MCP_GATEWAY_DYN_REAP_DEPTH`, `MCP_GATEWAY_DYN_PROBE_TIMEOUT_S`. Existing Phase 8 env vars (`MCP_GATEWAY_MAX_SESSIONS`, etc.) carry forward and now apply to BOTH r2 and gdb session kinds. | Document in the project's env-var inventory (likely a README or PROJECT.md section). Verify no existing env var conflicts (none found via grep). |
| Build artifacts | `mcp-gateway` package is a normal `pyproject.toml` project; no egg-info or build cache that names `sessions.py` as a module path that would invalidate. Container image must include `util-linux` (for `unshare`), `qemu-user-static`, `gdb`, `strace`, `ltrace`. | Verify Dockerfile installs all five (CONTEXT.md says Phase 11 first plan adds explicit `apt-get install` even if redundant). Wave 0 `probe_dynamic_tools.sh` (analogue to Phase 10's `probe_extraction_tools.sh`) confirms. |

**Critical Migration Risk: sessions.py → sessions/ refactor.** The Python import system will refuse to have BOTH `sessions.py` AND `sessions/` in the same directory (one will shadow the other). The rename must be atomic in a single commit. Tests that monkeypatch `mcp_gateway.sessions.<name>` continue to work as long as the name is re-exported by `__init__.py`. The Phase 9 conftest `importlib.reload(mcp_gateway.jobs)` pattern (per STATE.md) shows that the test suite DOES reload modules — Phase 11's refactor must verify reload-semantics on the new package.

## Environment Availability

| Dependency | Required By | Available (dev host probe) | Version | Fallback |
|------------|------------|----------------------------|---------|----------|
| gdb (with MI3) | DYN-05 (gdb session) | ✗ on dev host (WSL2 Ubuntu); installs from `gdb` apt package | 15.1 (Ubuntu noble), 13+ (Kali base) | None — DYN-05 cannot proceed without gdb. Container Dockerfile must install. |
| strace | DYN-03 (run_strace) | ✗ on dev host; installs from `strace` apt package | 6.8 (Ubuntu noble), 6.0+ (Kali) | None — DYN-03 cannot proceed without strace. |
| ltrace | DYN-03 (run_ltrace) | ✗ on dev host; installs from `ltrace` apt package | 0.7.3 (only available version, since 2015) | Document limitation; orchestrator prefers strace for behavior coverage. |
| qemu-user-static | DYN-04 (run_qemu_user) | ✗ on dev host; installs from `qemu-user-static` apt package | 8.2.2 (Ubuntu noble), 8.0+ (Kali) | None — DYN-04 cannot proceed without qemu. |
| unshare (util-linux) | DYN-03 / DYN-04 / DYN-05 netns wrap | ✓ on dev host | 2.39.3 | None — without unshare, no network isolation. (Note: `unshare --net` succeeds only when seccomp permits the syscall.) |
| yama ptrace_scope <= 1 (HOST) | DYN-03 / DYN-05 ptrace operations | ✓ probed (dev host reports 1) | n/a | Hard-fail with operator hint: `sudo sysctl -w kernel.yama.ptrace_scope=0` on host. |
| Container has CAP_SYS_PTRACE + seccomp=unconfined | DYN-03 / DYN-05 (ptrace works) AND DYN-03/04/05 (unshare works) | ✓ declared in CLAUDE.md and compose configuration | n/a | Without seccomp=unconfined, dynamic mode cannot use unshare. Without SYS_PTRACE, ptrace operations fail. |
| binfmt_misc with F flag for qemu archs (HOST) | DYN-04 (foreign-arch via `run_shell`) | n/a (probed at runtime) | n/a | `run_qemu_user(arch=...)` is the primary path and bypasses binfmt entirely. binfmt is optional for direct `./foreign_binary` exec. |

**Missing dependencies with no fallback:** None (when running inside the proper container). On a dev host without the apt packages, run all tests with `-m "not slow"` or behind `_require_<tool>_or_skip` fixtures.

**Missing dependencies with fallback:**
- ltrace 0.7.3 limitations → orchestrator prefers strace.
- binfmt_misc missing → `run_qemu_user` (explicit qemu invocation) is the primary path; only `run_shell` on cross-arch binaries is impacted.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (existing; see `mcp-gateway/tests/conftest.py`) |
| Config file | `mcp-gateway/pyproject.toml` and `mcp-gateway/pytest.ini` if present (otherwise default pytest discovery) |
| Quick run command | `pytest mcp-gateway/tests/test_dynamic_*.py mcp-gateway/tests/test_sessions_package.py mcp-gateway/tests/test_gdb_session.py -x -m "not slow"` |
| Full suite command | `pytest mcp-gateway/tests/ -x` (includes slow tests gated by `_require_*_or_skip`) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| DYN-01 | Tools registered iff env var set | unit | `pytest mcp-gateway/tests/test_dynamic_gate.py -x` | Wave 0 |
| DYN-01 | EXPECTED_TOOLS = 54 (off) / 61 (on) | unit | `pytest mcp-gateway/tests/test_tool_list.py -x -k "expected_tools"` (parametrized) | Edit existing |
| DYN-02 | `--dynamic` exports env var, requires `--remote` | shell | `bats run_docker.sh --dynamic` (or pytest-shell-wrap; matches Phase 3 pattern) | Wave 0 |
| DYN-03 | strace runs with profile, netns active, output in `case_dir/dynamic/` | integration | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_run_strace_roundtrip -x -m slow` | Wave 0 |
| DYN-03 | argv allowlist rejects shell-metachar in extra_args | unit | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_extra_args_rejects_metachar -x` | Wave 0 |
| DYN-03 | netns prevents network: getaddrinfo returns ENETUNREACH | integration | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_netns_blocks_dns -x -m slow` | Wave 0 |
| DYN-04 | run_qemu_user with arch=arm runs on a known-good ELF | integration | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_run_qemu_user_arm -x -m slow` | Wave 0 |
| DYN-04 | qemu_architectures probe returns non-empty when binaries exist | unit | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_probe_qemu_architectures -x` | Wave 0 |
| DYN-05 | Open gdb session → exec → close roundtrip with MI3 framing | integration | `pytest mcp-gateway/tests/test_gdb_session.py::test_gdb_session_roundtrip -x -m slow` | Wave 0 |
| DYN-05 | MI allowlist accepts known prefixes | unit | `pytest mcp-gateway/tests/test_gdb_session.py::test_mi_allowlist_positive -x` | Wave 0 |
| DYN-05 | MI allowlist rejects `python` / `interpreter-exec console` / `source` / `!` / `pi` / `attach` / `-target-select` / `-gdb-set logging on` / `add-symbol-file` / `dump` / `set inferior-tty` | unit | `pytest mcp-gateway/tests/test_gdb_session.py::test_mi_allowlist_negative_matrix -x` | Wave 0 |
| DYN-06 | Capability probe returns expected fields, never raises | unit | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_probe_all -x` | Wave 0 |
| DYN-06 | Probe with monkeypatched missing tools surfaces warnings | unit | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_probe_warnings_on_missing -x` | Wave 0 |
| DYN-07 | Trace tools dispatch via start_tool_job | integration | `pytest mcp-gateway/tests/test_dynamic_jobs.py::test_strace_via_jobs -x -m slow` | Wave 0 |
| DYN-07 | reap_followfork_strays kills setsid grandchildren | integration | `pytest mcp-gateway/tests/test_dynamic_primitive.py::test_reap_followfork_strays -x -m slow` | Wave 0 |
| DYN-07 | Sample resolved by sha256 from uploads/ and existing case_dir | unit | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_sample_resolution -x` | Wave 0 |
| Refactor | sessions/ package re-exports preserve every Phase 8 symbol | unit | `pytest mcp-gateway/tests/test_sessions_package.py -x` | Wave 0 |
| Refactor | Phase 8 existing tests continue to pass | regression | `pytest mcp-gateway/tests/test_sessions.py mcp-gateway/tests/test_r2_sessions.py -x` | Existing |
| All | Disclaimer string in all 7 dynamic-tool docstrings | unit | `pytest mcp-gateway/tests/test_dynamic_tools.py::test_disclaimer_in_all_docstrings -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `pytest mcp-gateway/tests/test_dynamic_*.py mcp-gateway/tests/test_sessions_package.py mcp-gateway/tests/test_gdb_session.py -x -m "not slow"` (~10 s expected)
- **Per wave merge:** `pytest mcp-gateway/tests/ -x -m "not slow"` (~30 s expected)
- **Phase gate:** Full suite green before `/gsd-verify-work`: `pytest mcp-gateway/tests/ -x` including slow tests. Slow tests require apt-installed tools (gdb/strace/ltrace/qemu-user-static) AND host posture (ptrace_scope <= 1, seccomp permitting unshare). On dev hosts that lack any of these, slow tests skip via `_require_gdb_or_skip` / `_require_strace_or_skip` / `_require_qemu_user_or_skip` / `_require_netns_or_skip`. The CI runner inside the rebuilt container must pass all slow tests.

### Wave 0 Gaps

- [ ] `mcp-gateway/tests/test_dynamic_primitive.py` — covers DYN-03 / DYN-04 / DYN-06 / DYN-07 builder + probe + reap logic
- [ ] `mcp-gateway/tests/test_dynamic_tools.py` — MCP surface tests for all 7 tools (DYN-03 / DYN-04 / DYN-05 / DYN-06)
- [ ] `mcp-gateway/tests/test_gdb_session.py` — gdb-MI3 driver, sentinel framing, allowlist matrix (DYN-05)
- [ ] `mcp-gateway/tests/test_sessions_package.py` — Phase 8/11 refactor regression
- [ ] `mcp-gateway/tests/test_dynamic_jobs.py` — JobToolSpec integration for 3 dynamic specs (DYN-07)
- [ ] `mcp-gateway/tests/test_dynamic_gate.py` — env-gate behavior (DYN-01)
- [ ] `mcp-gateway/tests/conftest.py` — add `_require_gdb_or_skip`, `_require_strace_or_skip`, `_require_ltrace_or_skip`, `_require_qemu_user_or_skip`, `_require_netns_or_skip` helpers analogous to Phase 8's `_require_r2_or_skip`
- [ ] `scripts/probe_dynamic_tools.sh` — operator helper analogous to Phase 10's `probe_extraction_tools.sh` (optional)
- [ ] `mcp-gateway/tests/fixtures/` — 30-line C fixture: `dns_lookup.c` (calls `getaddrinfo("example.com", ...)` to verify ENETUNREACH under netns); `setsid_escape.c` (forks, child `setsid()` + `sleep(60)` to verify reap); pre-built foreign-arch ELF (e.g., `hello_mips.bin`) for qemu round-trip

**Framework install:** No new framework — pytest-asyncio is already in `mcp-gateway/pyproject.toml` test deps (per Phase 6 onward).

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Bearer token (Phase 2 D-12) — dynamic tools inherit; no new auth surface |
| V3 Session Management | yes | Same bearer-token sharing model as r2 (Phase 8 SESS-05); disclaimer present on all 7 dynamic tools |
| V4 Access Control | yes | `confine_to` for case-dir paths; argv-only spawn (no shell expansion); samples resolved by sha256 ONLY |
| V5 Input Validation | yes (CRITICAL) | `EXTRA_ARGS_ALLOWLIST_RE` regex per arg + `_DENIED_EXTRA_ARG_FLAGS` per-flag set; gdb-MI prefix allowlist + deny regex |
| V6 Cryptography | no | No new cryptographic operations |
| V7 Error Handling | yes | Structured `{error, missing, hint}` dicts per Phase 6 D-04 "tools never raise" contract |
| V12 Files and Resources | yes | `ensure_subdir` + `confine_to` for case-dir writes; `-o` flag forbidden in `extra_args` so agent cannot redirect output |
| V14 Configuration | yes | Default-off via env gate; bearer token, no-net default, MI allowlist all default-deny |

### Known Threat Patterns for {Dynamic-Analysis Containerized Sample Execution}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Sample exfiltrates data via DNS / HTTP / SOCKS | Information Disclosure | Per-call `unshare --net --ipc --uts --` — no interfaces, no loopback (D-DYN-NET-01..03). Probe + tests assert ENETUNREACH. |
| Sample escapes via gdb embedded Python | Elevation of Privilege | MI prefix allowlist (D-07) blocks `-interpreter-exec console`, `python`, `pi`, `source`, `!`, `shell`. Belt-and-braces deny regex. |
| Sample escapes process group via `setsid()` | Tampering / Repudiation | `reap_followfork_strays` walks `/proc/<runner_pid>/task/*/children` recursively after termination (D-DYN-JOB-03). |
| Sample writes arbitrary host path via gdb logging/dump | Tampering | MI deny regex blocks `-gdb-set logging on`, `dump <...>`, `add-symbol-file`, `generate-core-file`. Builder forbids `-o` in strace/ltrace `extra_args`. |
| Sample attaches to gateway-owned process | Elevation of Privilege | MI deny regex blocks `-target-select`, `-target-attach`, `attach`. Sample's PID can't even see gateway PID under unshare-ipc. |
| Operator injects shell metachar via extra_args | Tampering / Information Disclosure | `EXTRA_ARGS_ALLOWLIST_RE` rejects `; | & $ backtick > < \n \t \0`. argv-only spawn (no shell) ensures even bypass would have no effect. |
| Sample exhausts session cap (DoS) | DoS | Combined r2+gdb cap of 8 sessions (D-02). Reaper kills idle sessions after 1800 s. |
| Sample's strace output fills disk | DoS | Phase 9 log-cap (`JOB_LOG_CAP_BYTES` default 256 MB). Per-job `default_timeout_s` (15 min strace, 30 min qemu). |
| Capability probe reveals attack surface to sample | Information Disclosure | Probe runs at gateway startup, results returned to authenticated MCP clients only via `get_dynamic_capabilities`. Sample (subprocess) cannot read gateway memory. |
| Sample probes binfmt or yama state | Information Disclosure | Sample runs as `agent` (no special permission to read host sysctls beyond stock proc filesystem). Limited damage — sample can read `/proc/sys/kernel/yama/ptrace_scope` itself anyway. |
| Operator passes malicious `init_commands` to gdb | Elevation of Privilege | Each init_command runs through the same MI allowlist as `gdb_exec`. Reject before spawn. |
| Stale gdb process leaks across gateway restart | Resource Exhaustion | `SessionRegistry.__aexit__` parallel killpg sweep + `start_new_session=True` for each gdb spawn. Reaper on startup-without-cleanup is the existing Phase 8 reaper. |

## Code Examples

### Example 1: gdb-MI3 driver per-command flow (matches CONTEXT.md D-06)

```python
# sessions/gdb.py
import asyncio
import secrets
from typing import Tuple

# At session open:
self.sentinel = f"__MARE_END_{secrets.token_hex(4)}__"

async def exec_one(self, cmd: str, *, timeout: float) -> Tuple[bytes, bool]:
    """Send one MI command + sentinel; read until terminator. Caller holds session lock."""
    # Validate against allowlist (D-07) BEFORE writing to stdin
    if not _is_allowed_mi(cmd):
        raise ValueError(f"gdb-MI command refused: not in allowlist: {cmd!r}")
    if _DANGEROUS_GDB_RE.search(cmd):
        raise ValueError(f"gdb-MI command refused: matches deny regex: {cmd!r}")

    self.proc.stdin.write(cmd.encode("utf-8") + b"\n")
    # Sentinel emitter — escape inner quotes for gdb-MI string-literal syntax
    sentinel_emit = f'-data-evaluate-expression "\\"{self.sentinel}\\""\n'
    self.proc.stdin.write(sentinel_emit.encode("ascii"))
    await self.proc.stdin.drain()

    # Terminator: gdb emits ^done,value="\"__MARE_END_<8hex>__\""
    # Note: the inner \" appears verbatim in the output stream
    terminator_substr = f'^done,value="\\"{self.sentinel}\\""'.encode("ascii")
    buf = bytearray()
    try:
        while True:
            line = await asyncio.wait_for(
                self.proc.stdout.readuntil(b"\n"),
                timeout=timeout,
            )
            if terminator_substr in line:
                return bytes(buf), False  # Exclude terminator from output
            buf.extend(line)
    except asyncio.TimeoutError:
        return bytes(buf), True
```

[CITED: sourceware.org/gdb/current/onlinedocs/gdb.html/Interpreters.html — MI3 result record format].

### Example 2: argv builder with netns wrap (matches CONTEXT.md D-DYN-JOB-02)

```python
# dynamic.py
from pathlib import Path
from mcp_gateway.artifacts_io import ensure_subdir, tool_log_path

def wrap_netns(argv: list[str]) -> list[str]:
    """Prepend per-call netns isolation. Defense-in-depth atop killpg + MI allowlist."""
    return ["unshare", "--net", "--ipc", "--uts", "--", *argv]

def build_strace_argv(case_dir: Path, kwargs: dict) -> list[str]:
    """JobToolSpec.build_argv for strace. Pure: no side effects beyond ensure_subdir.

    Validates extra_args / run_argv against allowlist (D-DYN-PROF-02);
    raises ValueError on metachar / denied flag (caught by JOBS as InvalidKwargs).
    """
    from mcp_gateway.tools.samples import resolve_sample

    sample_input = kwargs["sample"]
    profile = kwargs["profile"]
    extra_args = kwargs.get("extra_args") or []
    run_argv = kwargs.get("run_argv") or []

    # Validate extra_args / run_argv per D-DYN-PROF-02
    _validate_argv_list(extra_args, field="extra_args")
    _validate_argv_list(run_argv, field="run_argv")

    if profile not in STRACE_PROFILES:
        raise ValueError(f"unknown strace profile: {profile!r}; "
                         f"allowed: {sorted(STRACE_PROFILES)}")
    profile_args = list(STRACE_PROFILES[profile])

    sample_sha, sample_path = resolve_sample(sample_input)
    out_path = tool_log_path(case_dir, "strace", ".txt", subdir="dynamic")

    inner = [
        "strace",
        *profile_args,
        "-o", str(out_path),
        *extra_args,
        "--",
        str(sample_path),
        *run_argv,
    ]
    return wrap_netns(inner)
```

### Example 3: capability probe shape (matches CONTEXT.md D-DYN-CAP-PROBE-01)

```python
# dynamic.py
import dataclasses
import datetime
import os
import shutil
import subprocess
from pathlib import Path

@dataclasses.dataclass(frozen=True)
class DynamicCapabilities:
    probed_at: str
    dynamic_mode_enabled: bool
    ptrace_scope: int | None
    ptrace_traceme_works: bool
    binfmt_misc_mounted: bool
    qemu_architectures: tuple[str, ...]
    qemu_static_binaries: tuple[str, ...]
    netns_feasible: bool
    unshare_path: str | None
    gdb_path: str | None
    gdb_version: str | None
    strace_path: str | None
    ltrace_path: str | None
    warnings: tuple[str, ...]

def probe_all() -> DynamicCapabilities:
    """Probe all dynamic-mode capabilities. NEVER raises."""
    warnings = []
    probed_at = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    dynamic_mode = os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1"

    # 1. ptrace_scope (HOST yama)
    ptrace_scope = None
    try:
        ptrace_scope = int(Path("/proc/sys/kernel/yama/ptrace_scope").read_text().strip())
        if ptrace_scope >= 2:
            warnings.append(
                f"ptrace_scope={ptrace_scope} — strace/ltrace/gdb will fail. "
                f"Host operator: sudo sysctl -w kernel.yama.ptrace_scope=0"
            )
    except (OSError, ValueError):
        warnings.append("ptrace_scope: /proc/sys/kernel/yama/ptrace_scope not readable")

    # 2. ptrace TRACEME smoke test via forked child
    ptrace_works = _probe_ptrace_traceme()  # see below
    if not ptrace_works:
        warnings.append("ptrace TRACEME smoke test failed — check container CAP_SYS_PTRACE")

    # 3. binfmt_misc
    binfmt_mounted = (Path("/proc/sys/fs/binfmt_misc").is_dir()
                      and Path("/proc/sys/fs/binfmt_misc/register").exists())

    # 4. qemu architectures (binfmt + binary cross-check)
    qemu_arches, qemu_bins = _probe_qemu(binfmt_mounted)

    # 5. netns feasibility (THIS IS THE LOAD-BEARING ONE)
    netns_ok = False
    try:
        rc = subprocess.run(
            ["unshare", "--net", "true"],
            capture_output=True, timeout=3,
        ).returncode
        netns_ok = (rc == 0)
        if not netns_ok:
            warnings.append(
                "unshare --net failed — check container --security-opt seccomp=unconfined "
                "or --cap-add=SYS_ADMIN"
            )
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        warnings.append(f"unshare probe error: {type(e).__name__}")

    # 6. Tool paths
    gdb_path = shutil.which("gdb")
    strace_path = shutil.which("strace")
    ltrace_path = shutil.which("ltrace")
    unshare_path = shutil.which("unshare")

    gdb_version = None
    if gdb_path:
        try:
            gdb_version = subprocess.run(
                ["gdb", "--version"], capture_output=True, timeout=3,
            ).stdout.decode("utf-8", errors="replace").splitlines()[0]
        except (subprocess.TimeoutExpired, OSError):
            pass

    return DynamicCapabilities(
        probed_at=probed_at,
        dynamic_mode_enabled=dynamic_mode,
        ptrace_scope=ptrace_scope,
        ptrace_traceme_works=ptrace_works,
        binfmt_misc_mounted=binfmt_mounted,
        qemu_architectures=tuple(qemu_arches),
        qemu_static_binaries=tuple(qemu_bins),
        netns_feasible=netns_ok,
        unshare_path=unshare_path,
        gdb_path=gdb_path,
        gdb_version=gdb_version,
        strace_path=strace_path,
        ltrace_path=ltrace_path,
        warnings=tuple(warnings),
    )
```

### Example 4: follow-fork stray reap (matches CONTEXT.md D-DYN-JOB-03)

```python
# dynamic.py
import os
import signal
from pathlib import Path

REAP_DEPTH = int(os.environ.get("MCP_GATEWAY_DYN_REAP_DEPTH", "8"))

def reap_followfork_strays(runner_pid: int, original_pgid: int) -> int:
    """Scan /proc descendants of runner_pid; SIGKILL any that escaped via setsid.

    Called from JobToolSpec.post_terminal_hook after killpg has run.
    Returns count of strays reaped (logged at INFO if > 0).
    """
    killed = 0
    visited: set[int] = set()

    def _walk(pid: int, depth: int) -> None:
        nonlocal killed
        if depth >= REAP_DEPTH or pid in visited:
            return
        visited.add(pid)
        # Collect children of every task (thread) of pid
        task_dir = Path(f"/proc/{pid}/task")
        if not task_dir.is_dir():
            return
        for tdir in task_dir.iterdir():
            try:
                children_str = (tdir / "children").read_text().strip()
            except (OSError, PermissionError):
                continue
            for c in children_str.split():
                try:
                    cpid = int(c)
                except ValueError:
                    continue
                _walk(cpid, depth + 1)
                # Check if child has a different pgid (setsid escapee)
                try:
                    cpgid = os.getpgid(cpid)
                except (ProcessLookupError, PermissionError):
                    continue
                if cpgid != original_pgid:
                    try:
                        os.kill(cpid, signal.SIGKILL)
                        killed += 1
                    except (ProcessLookupError, PermissionError):
                        pass

    _walk(runner_pid, depth=0)
    return killed
```

### Example 5: env-gated registration (matches CONTEXT.md "Integration points")

```python
# tools/__init__.py — single diff line inserted between jobs.register and backend_passthrough.register
import os
# ... existing imports unchanged ...

def register_all_tools(mcp: FastMCP) -> None:
    # ... existing 30+ lines unchanged ...
    jobs.register(mcp)
    extract.register(mcp)
    # Phase 11 D-DYN-IMPORT-01: conditional registration of dynamic-mode surface.
    # When MCP_GATEWAY_DYNAMIC_TOOLS=1, tools/dynamic.py is imported (which transitively
    # imports mcp_gateway.dynamic, registering 3 JobToolSpecs via register_job_tool at
    # import time). When unset, neither the 7 tools nor the 3 specs leak.
    if os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1":
        from . import dynamic as dynamic_tools
        dynamic_tools.register(mcp)
    backend_passthrough.register(mcp)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| gdb CLI prompt parsing | gdb-MI3 structured records | mi3 standardized in GDB 9.1 (2020) | Robust framing via `^done`/`*stopped`/`(gdb)` boundaries — Phase 11 uses sentinel-after-cmd, the safest variant |
| ltrace with active upstream | ltrace 0.7.3 frozen | Last meaningful release 2015 | strace is preferred for behavioral coverage on modern binaries; ltrace remains the only library-call tracer available on Debian/Ubuntu/Kali |
| Per-arch qemu binaries in `qemu` package | `qemu-user-static` separate package | Debian transition ~2018 | Static binaries are mountable into other containers; `F` flag in binfmt registration makes container use seamless |
| Container ptrace requires `--privileged` | `--cap-add SYS_PTRACE` + `seccomp=unconfined` | Standard since Docker 1.12 | CLAUDE.md adopts this posture; container is NOT fully privileged |
| Persistent named netns (`ip netns add ...`) | Per-call `unshare --net --ipc --uts` | Ergonomic shift driven by container ecosystem (~2018+) | Cleaner; no host-state leak; one syscall per invocation |
| Sentinel via printf | Sentinel via `-data-evaluate-expression` for MI / `?e <token>` for r2 | This project's Phase 8 → 11 lineage | Each tool's native string-eval is unambiguous against its async record format |

**Deprecated / outdated:**
- gdb-MI2 — superseded by mi3 since gdb 9.1.
- ltrace 0.7.3 — no replacement; the library-call tracing niche is unmaintained.
- `--privileged` for dynamic analysis — replaced with targeted capabilities + seccomp posture.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Kali container's gdb is >= 13 and supports `--nh` flag | Standard Stack | If container ships gdb < 9, `--nh` fails. Fallback: `-iex "set auto-load no"`. Wave 0 probe verifies. |
| A2 | ltrace 0.7.3 is essentially unmaintained | Common Pitfalls #4 | Low — even if upstream is alive, packaged version is what matters. Skip-marker on slow tests covers. |
| A3 | Kali's `qemu-user-static` package registers binfmt with `F` flag | Standard Stack | If F flag not set, run_qemu_user (explicit qemu argv) still works; only `run_shell("./foreign")` is affected. Documented in Pitfall #6. |
| A4 | Container's `seccomp=unconfined` posture is preserved through compose.yaml | Common Pitfalls #2 | Critical — without unconfined seccomp, `unshare --net` fails. Probe catches at startup. Recommend pinning `security_opt: ["seccomp=unconfined"]` in compose.yaml explicitly. |
| A5 | gdb 13+ on Kali emits the exact `^done,value="\"<token>\""` sentinel terminator format | Architecture Patterns / Pattern 3 | If the format differs (escaped quotes, different field name), the readuntil terminator pattern needs adjustment. Wave 0 integration test verifies live. |
| A6 | `_validate_kwargs` array-schema gap is a real limitation, not just a documentation gap | Common Pitfalls #8 | Verified by codebase read of `jobs.py:254-290` — array branch is absent. [VERIFIED]. |
| A7 | `qemu-user-static` on Ubuntu/Kali installs binaries to `/usr/bin/qemu-<arch>-static` (consistent path across distros) | Code Examples / probe_qemu | Standard since Debian transition. If different path, `shutil.which("qemu-<arch>-static")` still finds them. |
| A8 | strace's `-b execve` is the actual flag (not `--exec`) | Common Pitfalls #9 | [VERIFIED: man7.org strace manpage]. |
| A9 | Phase 9's `register_job_tool` is callable from `dynamic.py` at import time | Pattern 2 | [VERIFIED: jobs.py:299 — public function, module-level definition]. |
| A10 | Refactor `sessions.py` → `sessions/` will not break existing Phase 8/9 imports if `__init__.py` re-exports verbatim | Pitfalls #11 | Python import semantics are well-defined for this case; tests catch regressions. |

**[ASSUMED] items needing user confirmation:** A2 (ltrace maintenance status — should the orchestrator skill explicitly de-prioritize ltrace?). A4 (compose.yaml security_opt — should Phase 11 explicitly pin `seccomp=unconfined` in compose.yaml to lock the posture?). These are low-stakes but explicit confirmation tightens the security story.

## Open Questions

1. **Should Phase 11 explicitly pin `security_opt: ["seccomp=unconfined"]` and `cap_add: ["SYS_PTRACE"]` in compose.yaml?**
   - What we know: CLAUDE.md declares this posture; compose.yaml currently relies on this implicitly or via compose.remote.yaml.
   - What's unclear: whether the posture is pinned in code or only documented.
   - Recommendation: Verify `compose.yaml` / `compose.remote.yaml` and PIN explicitly in Phase 11's Plan 01 if not already pinned. Otherwise a future compose edit could silently break dynamic mode.

2. **Should `_validate_kwargs` be extended with array schema support, or should array validation move to `build_argv`?**
   - What we know: Current Phase 9 `_validate_kwargs` only handles integer/string/boolean.
   - What's unclear: whether extending it is in-scope for Phase 11 or a Phase 9 retrofit.
   - Recommendation: Validate in `build_argv` (cleaner separation; matches Phase 10 pattern; minimal Phase 9 touch).

3. **Should `JobToolSpec` gain a `post_terminal_hook` field?**
   - What we know: CONTEXT.md D-DYN-JOB-03 prescribes this; Phase 9's spec is a frozen 7-field dataclass.
   - What's unclear: Adding the field is a 1-line change but constitutes a Phase 9 contract extension.
   - Recommendation: Add as optional 8th field (`post_terminal_hook: Optional[Callable[[Job], Awaitable[None]]] = None`). Phase 10's existing specs don't use it; only Phase 11's three do. Backward-compatible.

4. **Should `run_docker.sh --dynamic` warn about ptrace_scope on the HOST before starting the container?**
   - What we know: ptrace_scope is host-controlled; the in-container probe runs only after the gateway starts.
   - What's unclear: Whether host-side detection in run_docker.sh adds enough value to be worth the bash complexity.
   - Recommendation: Defer to Phase 12 (orchestrator-skill operator-help script). Phase 11's in-container WARN log + structured error from each tool is sufficient.

5. **Is `qemu-user-static` from Kali base apt set sufficient, or should Phase 11 pin a specific version?**
   - What we know: Ubuntu noble ships 8.2.2; Kali ships 8.x.
   - What's unclear: Whether qemu's multi-thread/signal stability has materially improved post-8.0 — the Debian bug 925358 was closed April 2024 but other multi-thread issues persist.
   - Recommendation: Use whatever apt provides; document the multi-thread limitation; do NOT pin a specific qemu version (rebuilds become fragile).

## Sources

### Primary (HIGH confidence)

- **CONTEXT.md (1573 lines)** — `.planning/phases/11-dynamic-lab-mode-env-gated/11-CONTEXT.md` — full design lock; this research validated rather than re-decided
- **REQUIREMENTS.md** — `.planning/REQUIREMENTS.md` lines 75-81 (DYN-01..DYN-07) and Out of Scope section
- **ROADMAP.md** — `.planning/ROADMAP.md` lines 139-150 (Phase 11 goals and success criteria)
- **STATE.md** — `.planning/STATE.md` — historical phase completion artifacts; especially Phase 9 conftest reload pattern
- **CLAUDE.md** — root and user — project posture (SYS_PTRACE + seccomp=unconfined, bearer auth, Streamable HTTP)
- **Codebase read:**
  - `mcp-gateway/src/mcp_gateway/sessions.py` (458 lines) — Phase 8 baseline for refactor
  - `mcp-gateway/src/mcp_gateway/jobs.py` (755 lines) — Phase 9 baseline for spec registration; `_validate_kwargs` gap identified at lines 254-290
  - `mcp-gateway/src/mcp_gateway/app.py` (205 lines) — lifespan ordering confirmed
  - `mcp-gateway/src/mcp_gateway/tools/__init__.py` (66 lines) — registration site for env-gated dynamic import
  - `mcp-gateway/tests/test_tool_list.py` lines 43-72 — EXPECTED_TOOLS = 54 confirmed
  - `run_docker.sh` (364 lines) — flag-parsing and env-var passthrough pattern
- **Host probes** (Ubuntu noble dev box):
  - `apt-cache policy gdb strace ltrace qemu-user-static util-linux` — versions confirmed
  - `unshare --version`, `cat /proc/sys/kernel/yama/ptrace_scope`, `ls /proc/sys/fs/binfmt_misc/` — capability shape verified
- **GDB documentation:** [sourceware.org/gdb/current/onlinedocs/gdb.html/Interpreters.html](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Interpreters.html) — MI3 + interpreter-exec semantics, MI3 stabilized in GDB 9.1
- **GDB forks documentation:** [sourceware.org/gdb/current/onlinedocs/gdb.html/Forks.html](https://sourceware.org/gdb/current/onlinedocs/gdb.html/Forks.html) — follow-fork-mode / detach-on-fork semantics
- **strace manpage:** [man7.org/linux/man-pages/man1/strace.1.html](https://man7.org/linux/man-pages/man1/strace.1.html) — flag inventory; `--exec` is NOT a flag; `--kill-on-exit` documented
- **binfmt_misc kernel docs:** [docs.kernel.org/admin-guide/binfmt-misc.html](https://docs.kernel.org/admin-guide/binfmt-misc.html) — F flag definition; mount-namespace caveats
- **qemu-user-static multiarch:** [github.com/multiarch/qemu-user-static](https://github.com/multiarch/qemu-user-static) — registration format with `flags: F`
- **Yama LSM (ptrace_scope):** [kernel.org/doc/Documentation/security/Yama.txt](https://www.kernel.org/doc/Documentation/security/Yama.txt) and [docs.kernel.org/admin-guide/LSM/Yama.html](https://docs.kernel.org/admin-guide/LSM/Yama.html) — 0/1/2/3 semantics; PR_SET_PTRACER usage
- **Docker seccomp:** [docs.docker.com/engine/security/seccomp/](https://docs.docker.com/engine/security/seccomp/) — default profile blocks `unshare` without CAP_SYS_ADMIN

### Secondary (MEDIUM confidence)

- **pygdbmi reference:** [github.com/cs01/pygdbmi](https://github.com/cs01/pygdbmi) and [pypi.org/project/pygdbmi/](https://pypi.org/project/pygdbmi/) — MI record types (result/notify), parsing approach (we don't depend on it, but format-compatible)
- **Fork-handling reaping techniques:** [skullsecurity.org/2023/fork-off-three-ways-to-deal-with-forking-processes](https://www.skullsecurity.org/2023/fork-off-three-ways-to-deal-with-forking-processes) — three approaches; `/proc/<pid>/task/*/children` recursion validated
- **qemu user-mode signal-handling bug:** [bugs.launchpad.net/qemu/+bug/1319100](https://bugs.launchpad.net/qemu/+bug/1319100) — multi-threaded sample limitation
- **moby/moby seccomp issue:** [github.com/moby/moby/issues/42441](https://github.com/moby/moby/issues/42441) — discussion of unshare in default seccomp profile
- **GDB command refs:** [visualgdb.com/gdbreference/commands/set_follow-fork-mode](https://visualgdb.com/gdbreference/commands/set_follow-fork-mode), [visualgdb.com/gdbreference/commands/set_detach-on-fork](https://visualgdb.com/gdbreference/commands/set_detach-on-fork)

### Tertiary (LOW confidence — flagged for verification)

- **ltrace maintenance state:** [ASSUMED A2] based on apt version being from 2015. Did not exhaustively verify upstream repo activity.
- **Container's exact gdb version:** [ASSUMED A1] Kali ships >= 13 per `.planning/research/STACK.md` (cited in CONTEXT.md). Container Wave 0 probe will confirm.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all five tools (gdb, strace, ltrace, qemu-user-static, unshare) verified available via apt; versions confirmed.
- Architecture: HIGH — CONTEXT.md prescribes exact integration points; codebase reads confirm all referenced infrastructure exists and is compatible.
- Pitfalls: HIGH — twelve pitfalls documented, each with primary-source citations and concrete avoidance strategies.
- Capability probe: HIGH — every probe target verified empirically against /proc, kernel docs, and Docker docs.
- Security posture: MEDIUM — depends on `seccomp=unconfined` being preserved in compose.yaml (Open Question #1); recommend explicit pinning.
- ltrace usability: LOW — known-unmaintained tool; recommend orchestrator skill prefers strace where possible.

**Research date:** 2026-05-19

**Valid until:** 2026-06-19 (30 days for stable; longer if no GDB/QEMU/strace major versions release in that window. Reassess if any of: gdb major version bump, Docker default seccomp profile change, kernel ptrace_scope semantics revision, qemu major release with multi-thread fixes).

## RESEARCH COMPLETE
