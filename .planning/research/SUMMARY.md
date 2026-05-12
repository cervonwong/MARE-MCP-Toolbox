# Project Research Summary — v1.1 Remote RE Tool Expansion

**Project:** MARE-MCP-Toolbox v2 (v1.1 milestone)
**Domain:** Containerized FastMCP gateway extension — typed RE-tool wrappers, constrained shell, session-scoped r2/gdb, env-gated dynamic lab mode, background-job system
**Researched:** 2026-05-12
**Confidence:** HIGH (v1.0 architecture is shipped + validated; v1.1 deltas are extensions to a known surface, every recommendation grounded in existing `mcp-gateway/src/` code or verified library docs)

> **Scope note:** v1.0 (Remote MCP Foundation, shipped 2026-04-27) is fixed: custom FastMCP gateway, MCP Python SDK 1.27.x, Streamable HTTP, bearer auth, sha256 content-addressed uploads, `PinnedBackend` ClientSession, 22 curated tools. This summary covers **only the v1.1 deltas**: a constrained `run_shell`, ~12 typed static wrappers, an extraction tier, session-scoped r2 (and gdb under dynamic mode), env-gated dynamic tools (strace/ltrace/qemu-user/gdb), a background-job system, an expanded case-dir artifact tree, the orchestrator-skill rewrite, and the F-1 carryover image-hash fix.

---

## Executive Summary

v1.1 is an **extension milestone**, not a redesign. The v1.0 gateway already provides the network boundary, auth, upload, sha256 sample resolution, case-dir path-traversal guard, and backend pass-through; v1.1 layers RE-tool surface area on top of that boundary. The four research streams converged on a single architectural picture: a new in-process `ReToolRunner` becomes the chokepoint for every new subprocess invocation (argv-only, cwd-confined to `case_dir`, process-group SIGKILL on timeout/cancel, auto-capture to `tool-logs/`, head-truncated MCP response + full output on disk). Every new tool — `run_shell`, the typed static wrappers, extraction tools, dynamic tools, background jobs — is a thin schema layer over that one runner. Persistent r2 and gdb subprocesses live in a separate `SessionRegistry` keyed by an opaque UUID, with an idle reaper owned by `app.py::lifespan`. Dynamic tools (strace/ltrace/qemu-user/gdb session) are env-gated by **not being imported** when `MCP_GATEWAY_DYNAMIC_TOOLS != "1"` — the gate is at module-registration time in `tools/__init__.py`, not per-call.

The recommended approach is conservative: keep the existing `subprocess_runner.run_script` (used by orchestrator pipeline scripts) untouched, and add `runner.py` for v1.1 RE tools. The security model shifts from "no shell" to "constrained shell" via *structural* confinement — non-root `mare-shell` UID, env scrub (no `MCP_GATEWAY_TOKEN`/API keys reach bash), cwd = canonicalized `case_dir`, hard timeout, output cap with the full log on disk, and ANSI-stripping before write. Mount-namespace isolation is **deferred** out of v1.1 (would require CAP_SYS_ADMIN, broadens the cap surface; the four documents converge on "skip for v1.1, document the limitation"). All new Python dependencies are well-pinned, narrow-purpose wrappers around already-installed Kali CLIs (r2pipe, pygdbmi, capstone, ropper, unblob); image growth is negligible (~150 KB net).

The dominant risks are operational, not architectural. Top three: **(1)** stdout/stderr PIPE deadlock on large outputs — solved by concurrent stream-drain + byte cap + file sink in `ReToolRunner` (Pitfall 1); **(2)** F-1 carryover (image content-hash misses `mcp-gateway/src/`) — must land *first* or every subsequent v1.1 commit silently ships nothing to the running container (Pitfall 15); **(3)** session and job lifecycle — r2/gdb processes outlive disconnected agents and accumulate; jobs that double-fork outlive the gateway. Solved by an idle reaper task + session cap, in-memory-only job registry, and `asyncio.shield(proc.wait())` cleanup wrapped around every long-running tool to ensure `CancelledError` propagates to a real `killpg` (Pitfall 18).

---

## Key Findings

### Recommended Stack (deltas only; v1.0 stack unchanged)

[Full details in STACK.md]

The v1.0 stack (`mcp` SDK 1.27.x, Streamable HTTP, custom FastMCP gateway, `anyio` 4.5+, bearer auth) is fixed and not re-researched. v1.1 adds five runtime Python deps and one dev-only test helper — all narrow wrappers around already-installed Kali CLIs.

**Core additions (mcp-gateway runtime deps):**

- **r2pipe (1.9.8)** — official radare2 bindings; drives `r2 -q0` over stdio for session-scoped `open_r2_session` / `r2_cmd` / `close_r2_session`. Sync-only — wrap in `anyio.to_thread.run_sync()` inside FastMCP handlers.
- **pygdbmi (0.11.0.0)** — drives `gdb --interpreter=mi3`, parses MI output to typed dicts; powers `gdb_exec`. Stable-but-slow-moving (Jan 2023 last release); thin parser around stable GDB/MI3 grammar.
- **capstone (5.0.7)** — multi-arch disassembly; backs `run_capstone_disasm(arch, mode, bytes)` with typed `CsInsn` JSON output. In-process, no subprocess. Already installed in Dockerfile — just pin the version.
- **ropper (1.13.13)** — multi-arch ROP gadget search; `RopperService` Python class returns typed `Gadget` objects (avoid fragile CLI text parsing). Already installed — just pin.
- **unblob (26.3.30)** — modern firmware extractor with structured `--report` JSON; replaces/complements `binwalk -e`. Already installed — just pin. Requires Python ≥3.10 (container is 3.11+).

**Dev-only (mcp-gateway `[dev]` extras, not in image):**

- **pexpect (4.9.0)** — PTY-driven session tests in pytest (asserts on real r2/gdb protocol, not mocked r2pipe/pygdbmi internals).

**Already-pinned, no change:** `mcp>=1.27,<1.28` (confirmed `Context.report_progress(progress, total, message)` available — the streaming primitive for jobs), `anyio>=4.5` (`to_thread.run_sync`, `create_task_group`, memory object streams), `httpx`, `starlette`, `uvicorn`, `python-multipart`. No version bumps needed.

**Stdlib primitives (no new deps):** `asyncio.create_subprocess_exec` (argv-only — never `shell=True`), `asyncio.wait_for` / `asyncio.timeout`, `os.setsid` + `os.killpg` (process-group cleanup), `uuid.uuid4` / `secrets.token_urlsafe(12)` (opaque session/job IDs), `anyio.create_task_group`, `pathlib.Path` + `os.path.commonpath` (case-dir confinement).

**No new apt packages required.** `radare2`, `gdb`/`gdb-multiarch`, `qemu-user`, `strace`, `ltrace`, `binwalk`, `upx-ucl`, `yara`, `jq`, `yq`, `xxd`, `file`, `detect-it-easy`, `capa` are all installed by the current Dockerfile. v1.1 adds **two** pip lines (`r2pipe`, `pygdbmi`) and pins **three** previously-unpinned ones (`capstone`, `ropper`, `unblob`).

### Expected Features

[Full details in FEATURES.md]

**Must have (table stakes for analyst parity over MCP):**

- **F-1 image-hash fix** — non-negotiable; without it every v1.1 edit silently fails to reach the running container (caught during 2026-05-11 UAT)
- **`ReToolRunner`** internal primitive — argv-only subprocess + cwd-confine + process-group + timeout + output cap + auto-capture + structured JSON result; the chokepoint for every new tool
- **`run_shell(cmd: str)`** — constrained bash one-liner with structural confinement (cwd=case_dir, timeout, output cap, capture, env scrub)
- **Expanded case-dir artifact tree** — `tool-logs/`, `extracted/`, `hex/`, `rop/`, `dynamic/`, `qemu/`, `disassembly/`, `decompilation/`, `xrefs/` (lazy-created on first write)
- **Typed static wrappers** — `run_file`, `run_die`, `run_xxd`, `run_readelf`, `run_objdump`, `run_nm`, `run_rabin2` (JSON-first), `run_capstone_disasm` (typed instruction JSON), `run_ropper` (typed gadget JSON), `run_jq`, `run_yq` — wrap only where structured output or argv-profile discoverability pays off; the long tail is `run_shell`
- **Session-scoped r2** — `open_r2_session` / `r2_cmd` / `close_r2_session` so `aaa` analysis state persists across calls (the entire point of using r2 for non-trivial RE)
- **Extraction tier** — `run_binwalk`, `run_unblob`, `run_upx_test`, `run_upx_list`, `run_upx_unpack`, `extract_embedded_files` (engine-agnostic composer), `list_extracted_files`, `promote_extracted_sample` (turn a child into a first-class case)
- **Background job system** — `start_tool_job` / `get_tool_job` / `cancel_tool_job` / `list_tool_jobs` for tools that routinely exceed the 60 s MCP request cap (capa, unblob, strace, qemu, Ghidra/IDA full-auto)
- **Artifact / control helpers** — `write_artifact`, `append_artifact`, `list_artifacts`, `get_artifact_tree`, `get_tool_log` (range-read of giant logs)
- **Orchestrator-skill update** — encode deep RE checklists (W-1..W-7 workflows), fix stale assumptions (backend priority `IDA > BN > Ghidra`, remote agents use gateway tools not local `scripts/`, dynamic-mode flag in `CURRENT_STATE.json`), preserve dual-mode operation

**Should have (v1.1 second wave — dynamic-mode bundle):**

- **Dynamic env-gate** — `MCP_GATEWAY_DYNAMIC_TOOLS=1`, surfaced as `./run_docker.sh --dynamic`; tools registered at startup (not at call time); `--network=none` (or per-call netns) default
- **`run_strace`, `run_ltrace`, `run_qemu_user`** — first-class dynamic tools with argv profiles; job-required by default (long-running)
- **Session-scoped gdb** — `open_gdb_session` / `gdb_exec` / `close_gdb_session` using `gdb --interpreter=mi3`; reuses the r2 session plumbing; pager-off + confirm-off at session open

**Defer (v1.2+):**

- Sandboxed-network dynamic (INetSim/FakeDNS/honeynet integration; `allow_network=true` opt-in)
- Coverage-guided dynamic (afl-style fuzzing hooks)
- Memory snapshot tooling (Volatility integration)
- Per-`Mcp-Session-Id` keying of sessions and jobs (currently shared across all clients with the same bearer token — documented limitation)
- Job persistence across gateway restart (currently in-memory-only by design)
- Web UI for case browsing (already Out of Scope in PROJECT.md)

**Anti-features explicitly out of scope (4 documents converge):**

- **Composite `investigate_*` MCP tools** (e.g., `investigate_packer`, `auto_triage_pe`) — these are agent prompts dressed as tools; gateway exposes primitives, orchestrator skill composes them
- **Argv allowlist for everything (no `run_shell`)** — analysts ad-lib pipelines constantly; wrapper count explodes; gaps remain. Replace with structural confinement
- **Typed-per-r2-command surface** (`r2_pdf`, `r2_aflj`, `r2_iz`, …) — r2 has thousands of commands and analysts compose them (`pdf @ sym.foo~call`); a per-command surface covers ~5% of real use. Expose raw `r2_cmd(session_id, cmd, format)` with r2's native `j` suffix
- **Always-on dynamic mode** — widens attack surface, creates accidental sample-execution incidents; env-gated default-off is the explicit decision
- **Batch-only gdb (`run_gdb_script(script)`)** — every interactive analysis becomes a script-generation problem; agent can't react between commands. Use session-managed gdb
- **`run_strings` as a v1.1 typed wrapper** — v1.0's `collect_strings` already covers this; don't duplicate. Use `run_shell` for ad-hoc strings invocations

### Architecture Approach

[Full details in ARCHITECTURE.md]

v1.1 is **purely additive** to `mcp-gateway/src/mcp_gateway/`. No v1.0 file is rewritten; the only modifications are: (1) `tools/__init__.py::register_all_tools` adds 7 new module registrations + the dynamic-mode gate (and keeps `backend_passthrough.register()` last so it sees the merged tool surface); (2) `app.py::lifespan` adds two `async with` blocks for `SessionRegistry` and `BackgroundJobRegistry` (additive — existing `PinnedBackend` block unchanged); (3) `session_state.py` gains two `Optional` module-level slots (`SESSIONS`, `JOBS`) — same pattern as `PINNED_BACKEND`; (4) `run_docker.sh` content-hash extended to include `mcp-gateway/src/` (F-1).

**Major components (new):**

1. **`runner.py` — `ReToolRunner`** — single execution path for every v1.1 tool. argv-only `asyncio.create_subprocess_exec` with `start_new_session=True`, cwd = `resolve_case_dir(case_dir)`, concurrent stream drain into head-buffer + file sink, hard timeout via `asyncio.wait_for`, process-group SIGKILL on timeout/cancel via `os.killpg`, returns `{exit_code, stdout_head, stdout_truncated, stdout_bytes_total, stderr_head, stderr_truncated, log_path, duration_s, timed_out}`. Includes `run_shell(cmd)` as a thin variant that builds `argv = ["bash", "-lc", cmd]` (single argv element — Python never shell-interpolates).
2. **`artifacts_io.py`** — case-dir subdir helpers (`ensure_subdir(case_dir, name)`), lazy-create on first write so empty subdirs don't proliferate; canonical `confine_to(case_dir, path)` helper reused by every new path-accepting tool.
3. **`sessions/` package** — `SessionRegistry` keyed by UUID4 + `Session` instances (`R2Session`, `GdbSession`) holding `proc`, `asyncio.Lock` (serializes per-session commands), `last_used`, `case_dir`, `transcript_path`, `pgid`. Idle reaper task owned by lifespan (default 30 min, cap 8 sessions). Sentinel-marker pattern (`?e __MARE_END__\n` for r2, equivalent for gdb-MI) sidesteps prompt parsing.
4. **`jobs.py` — `BackgroundJobRegistry`** — `dict[job_id, BackgroundJob]` with one `asyncio.Task` per job, registry holds the reference so the loop doesn't GC the task between the `start_tool_job` response and the next `get_tool_job` poll. Per-job log capped at `MCP_GATEWAY_MAX_JOB_LOG_MB` (default 256 MB); over-cap kills the job and marks `status="killed_log_cap"`. Lifespan teardown kills all jobs.
5. **`tools/shell.py`, `tools/re_static.py`, `tools/re_sessions.py`, `tools/re_extract.py`, `tools/re_dynamic.py`, `tools/re_jobs.py`, `tools/re_artifacts.py`** — MCP-tool layer; each module exports `register(mcp)` matching the v1.0 seam. `re_dynamic.py` is only imported when the dynamic env-gate is on.

**Why two runners coexist (not a refactor):** `subprocess_runner.run_script` (v1.0) is purpose-built for orchestrator pipeline scripts (`/agent` cwd, no log-capture). Migrating its callers (`artifacts.py`, `workflows.py`) for cosmetic deduplication is needless risk. `ReToolRunner` is purpose-built for opaque RE binaries (case-dir cwd, auto-capture, head+log_path). Both share the same low-level primitives (`create_subprocess_exec`, `start_new_session=True`, `killpg`) — convergence is a v1.2 chore at most.

**Session vs job — different infra, do not conflate:** A *session* is a long-lived subprocess the agent talks to repeatedly (r2/gdb); keep-alive + idle-timeout + per-session command lock. A *job* is a single subprocess whose result the agent polls (capa/unblob/strace); queue/cancel/log-tail. Different lifecycles, different registries.

**Dynamic-mode gating at registration, not call time:** When `MCP_GATEWAY_DYNAMIC_TOOLS != "1"`, the `re_dynamic` module is never imported. `tools/list` does not advertise gated tools (correct discoverability signal to agents); `tools/call` rejects them with the standard "tool not found" MCP error. Zero per-call overhead, zero leaked surface, the gate is checked exactly once at startup.

### Critical Pitfalls

[Full details in PITFALLS.md — 18 cataloged pitfalls]

The top five load-bearing pitfalls (each maps to a specific phase; full table in "Pitfall-to-Phase Mapping" below):

1. **PIPE deadlock on large subprocess output (Pitfall 1)** — `subprocess.communicate()` buffers everything; works for v1.0's small JSON returns, breaks on v1.1's `objdump -d`, `strings`, `xxd`, `strace`. **Mitigation:** `ReToolRunner` streams stdout/stderr concurrently via `anyio.create_task_group()` with a head buffer (suggest 256 KB stdout / 64 KB stderr default) + file sink. After head cap, drain continues to keep child unblocked, bytes go only to `tool-logs/<ts>-<slug>.txt`. Truncate on UTF-8 codepoint boundary; strip ANSI before write.
2. **F-1 image-hash carryover (Pitfall 15)** — `run_docker.sh:209-222` `DOCKERFILE_SHA` excludes `mcp-gateway/src/`. **Mitigation:** Land F-1 *first*. Single small commit; extend the find/sha256sum inclusion list to add `-path "./mcp-gateway/src"` and `-path "./mcp-gateway/pyproject.toml"` (exclude `__pycache__`, `.venv`, `*.egg-info`, `.pytest_cache`). Add a regression test that touches `mcp-gateway/src/x.py` and asserts the hash changed.
3. **Process-group cleanup leaks grandchildren + FastMCP cancel doesn't kill subprocess (Pitfalls 4, 18)** — `asyncio` cancellation cancels the Python task, not the OS process; `setsid()`'d grandchildren of `strace -f` escape the pgroup. **Mitigation:** Wrap every long-running tool in `try/except (asyncio.TimeoutError, asyncio.CancelledError)` → `killpg(SIGKILL)` → `asyncio.shield(proc.wait())` → re-raise. For follow-fork tools, also scan `/proc/<runner_pid>/task/*/children` for stragglers. Test: client disconnect → subprocess dead < 200 ms.
4. **Session leaks / zombie r2 + gdb subprocesses (Pitfalls 5, 6)** — agent disconnects, sessions sit at the r2 prompt forever; some commands (`Vp`, `?I`, gdb `quit` while running) hit confirmation prompts that hang `readuntil(prompt)`. **Mitigation:** Background reaper task (60 s poll) closes sessions idle > `MCP_GATEWAY_SESSION_IDLE_S` (default 1800 s); session cap (`MCP_GATEWAY_MAX_SESSIONS` default 8); r2 init prepends `e scr.interactive=false; e scr.color=0`; gdb init runs `set pagination off; set confirm off`; sentinel-marker pattern after every command; per-command timeout kills the whole session (state unrecoverable) and returns `session_invalidated: true`.
5. **`run_shell` confinement is posture, not isolation (Pitfalls 2, 14)** — `cwd=case_dir` is the *starting* directory, not a sandbox; bash can `cd /root`. **Mitigation:** Run `bash -c` as a dedicated non-root `mare-shell` UID (created at image build) with primary-group ACL on `case_dir` + RO `/agent/uploads/`; whitelist env (exclude `MCP_GATEWAY_TOKEN`, `*_API_KEY`, `AWS_*`); canonicalize `case_dir` via `realpath` once; `TERM=dumb`, `NO_COLOR=1`. Document explicitly in the `run_shell` docstring that this is *agent-trust*, not isolation. **Mount-namespace (`unshare --mount`, requires CAP_SYS_ADMIN) is deferred out of v1.1** — all four research documents converge on this (Stack says "skip", Architecture treats it as optional, Pitfalls Pitfall 14 says "default v1.1: skip mount-ns, document").

Additional load-bearing pitfalls (full mitigations in PITFALLS.md):

- **Pitfall 7 — Archive bombs / symlink escapes during extraction:** canonical `confine_to(case_dir, path)` helper, extraction inside `case_dir/extracted/<tool>-<ts>/`, size-cap budget (`MCP_GATEWAY_MAX_EXTRACT_MB` default 4 GB), pre-decompress check for known formats, periodic disk-usage poll for stream formats, symlinks replaced with `.symlink-target.txt` quarantine files, `promote_extracted_sample` re-computes sha256 atomically.
- **Pitfall 8 — Background jobs orphaned by gateway restart:** in-memory-only registry by design; lifespan teardown kills all jobs; per-job log cap; LRU cleanup of completed jobs.
- **Pitfall 9 — Dynamic-mode network egress when no-net was intended:** per-sample `unshare --net --ipc --uts --mount` (combined with Pitfall 14 mount-ns if accepted); sanity-test sample DNS lookup must return `ENETUNREACH`; `--dynamic` flag and no-net policy are independent (don't conflate tool registration with network policy).
- **Pitfall 11 — ptrace permission gotchas:** probe `ptrace_scope` at gateway startup, surface via `get_dynamic_capabilities()`, return actionable errors (not opaque EPERM).
- **Pitfall 12 — 25k-token MCP result cap silent client-side truncation:** every `ReToolRunner`-driven tool returns head + `log_path` MCP Resource URI by default; full output via `get_tool_log(case_dir, log_name)` or `mare://cases/<case>/tool-logs/<file>`. Backstop with FastMCP `ResponseLimitingMiddleware` (~80 KB serialized JSON cap).
- **Pitfall 13 — `Mcp-Session-Id` collisions / single-session state leaking across clients:** v1.1 keeps single-session state (matches existing `session_state.py` pattern from v1.0); use `secrets.token_urlsafe(12)` session-ids to make guessing infeasible; **document the limitation** in `open_r2_session` / `start_tool_job` docstrings ("Sessions and jobs are shared across all MCP clients connected with the same bearer token"); per-`ctx.session_id` keying is deferred to v1.2/v2 (flagged as `GW-V2-03`).
- **Pitfall 16 — Orchestrator skill breaks the inside-container agent flow:** the skill must work in both `./run_docker.sh` (local, no gateway) and `--remote` (gateway) modes. Each step documents the goal + two implementations with a decision rule ("if `mcp__mare__collect_strings` is in `tools/list`, call it; otherwise run the bash script"). Dual-mode test gates merge.
- **Pitfall 17 — Gateway-native tool name collides with backend pass-through:** registration-time check against `pinned.list_tools()`; hard-fail at startup so the collision is fixed in code; `run_*` prefix convention for new v1.1 tools.

---

## Open Decisions / Tensions Surfaced by Research

Each research document took a position on a few load-bearing trade-offs; here's where they agree, where they disagree, and what the roadmapper needs to resolve.

| Decision | Position | Roadmapper resolution |
|----------|----------|------------------------|
| **Mount-namespace for `run_shell`** | STACK: skip (no new caps); PITFALLS: default v1.1 skip, document limitation; ARCHITECTURE: optional | **CONSENSUS: defer.** v1.1 ships posture-only confinement (UID + env scrub + cwd + ACL). Flag for v1.2 if CAP_SYS_ADMIN becomes acceptable. |
| **Tool-log file rotation / retention** | ARCHITECTURE: bounded by case lifecycle, no auto rotation; PITFALLS: per-job log cap mandatory + LRU on completed jobs | **OPEN — needs phase-level decision.** Recommendation: per-job log cap mandatory (mitigates Pitfall 8); per-call log rotation is a v1.2 concern. |
| **Session TTL default** | FEATURES + ARCHITECTURE + PITFALLS: 30 min idle + cap 8 sessions | **CONSENSUS: 30 min idle, cap 8.** Configurable via env. |
| **Per-`Mcp-Session-Id` keying for sessions/jobs** | All converge: defer to v1.2/v2; v1.1 single-session state matches v1.0 `session_state.py` | **CONSENSUS: defer per-session keying.** Documented limitation in tool docstrings. |
| **`run_shell` env scrub: whitelist vs blacklist** | PITFALLS: whitelist; everyone else implicit | **CONSENSUS: whitelist.** Explicit allowlist of `PATH`, `HOME`, `TERM=dumb`, `NO_COLOR=1`, `COLUMNS=120`, plus case-dir/sample-related vars. |
| **Background job persistence across gateway restart** | ARCHITECTURE + PITFALLS: in-memory only, restart cancels in-flight jobs by design | **CONSENSUS: in-memory only for v1.1.** Document the restart-cancels-jobs behavior. |
| **r2/gdb session model** | STACK: r2pipe + pygdbmi (sync, offload via `anyio.to_thread`); FEATURES: session-managed for both; PITFALLS: sentinel-marker output framing | **CONSENSUS: sentinel-marker over prompt-parsing.** r2 `j`-suffix JSON output where possible; gdb MI3 with `^done`/`^error`/`*stopped` markers. |
| **Dynamic-mode network policy enforcement mechanism** | PITFALLS: per-call `unshare --net --ipc --uts`; FEATURES: `--network=none` enforced at container level | **OPEN — needs Dynamic-phase decision.** Recommendation: per-call `unshare --net` (cheap, requires no extra caps if combined carefully). |

**Items everyone agreed on without tension:**

- F-1 lands first (all 4 docs).
- ReToolRunner is the chokepoint primitive (all 4 docs).
- `run_shell` is constrained-by-posture, not by argv allowlist (all 4 docs).
- Composite `investigate_*` MCP tools are explicitly out-of-scope (FEATURES, PITFALLS, PROJECT.md).
- Dynamic mode env-gated default-off (all 4 docs + PROJECT.md decision row).
- Sessions and jobs are different infrastructure, not unified (FEATURES, ARCHITECTURE, PITFALLS).

---

## Implications for Roadmap

All four research documents independently suggested 7–10 phases with substantial overlap. The convergence is striking — each researcher identified the same load-bearing chokepoints in roughly the same order. Below is the consensus phase structure with each phase's drivers cross-referenced.

### Phase 1: F-1 Image-Hash Fix

**Rationale:** All 4 documents demand this lands first. Without it, every subsequent v1.1 commit silently ships nothing to the running container (2026-05-11 UAT failure mode). Trivial single-file change; gates everything else.
**Delivers:** `run_docker.sh` content-hash extended to include `mcp-gateway/src/` + `mcp-gateway/pyproject.toml`; regression test that touches a gateway source file and asserts `DOCKERFILE_SHA` changed.
**Addresses:** Pitfall 15 (F-1 carryover).
**Implementation cost:** LOW.

### Phase 2: `ReToolRunner` + `artifacts_io.py` Foundation

**Rationale:** The chokepoint primitive. Every subsequent v1.1 tool layers over this. No MCP surface change; introduces the runner + artifact subdir helpers + canonical `confine_to(case_dir, path)` helper.
**Delivers:** `runner.py::ReToolRunner` (argv-only, cwd-confine, process-group, head+log_path, `CancelledError`-safe cleanup via `asyncio.shield`), `artifacts_io.py::ensure_subdir` and `confine_to`, unit tests including the 100-MB-`/dev/urandom` OOM-safety test.
**Addresses:** Pitfalls 1 (PIPE deadlock), 3 (ANSI/slow loris/output bombs), 4 (process-group cleanup), 12 (head+log_path return shape), 17 (tool-name convention), 18 (FastMCP cancel propagation).
**Implementation cost:** MEDIUM.

### Phase 3: `run_shell` + Typed Static Wrappers + `re_artifacts`

**Rationale:** First real consumers of Runner. Highest-value, lowest-risk surface area; validates the runner under real load before sessions and jobs build on it. Also lands the `mare-shell` UID changes in the Dockerfile.
**Delivers:** `tools/shell.py::run_shell` + `tools/re_static.py::{run_file, run_die, run_xxd, run_readelf, run_objdump, run_nm, run_rabin2, run_capstone_disasm, run_ropper, run_jq, run_yq}` + `tools/re_artifacts.py::{write_artifact, append_artifact, list_artifacts, get_artifact_tree, get_tool_log}`. Dockerfile adds the `mare-shell` user.
**Addresses:** Pitfalls 2 (run_shell posture), 3 (regression tests for ANSI/slow loris), 7 (canonical confine_to helper), 12 (head+log_path adopted), 17 (collision test against backend tools), env scrub.
**Implementation cost:** MEDIUM.

### Phase 4: Session-Scoped r2

**Rationale:** Most impactful new capability for non-trivial RE. Adds the shared `sessions/` package that gdb will reuse in Phase 7. Lands the `app.py::lifespan` modification (SessionRegistry idle reaper). Validates session plumbing under r2 (lower-complexity than gdb).
**Delivers:** `sessions/__init__.py` (SessionRegistry + idle reaper), `sessions/r2.py` (R2Session with sentinel-marker framing), `tools/re_sessions.py::{open_r2_session, r2_cmd, close_r2_session, list_sessions}`. `app.py::lifespan` modified. `session_state.py` gains `SESSIONS` slot.
**Addresses:** Pitfalls 5 (session leaks/zombie), 6 (interactive prompt hangs), 13 (single-session state limitation documented).
**Implementation cost:** HIGH.

### Phase 5: Background Job System

**Rationale:** Depends on ReToolRunner. Without jobs, unblob (recursive firmware) and all dynamic tools are essentially unusable due to MCP request-timeout. Validated against long-running capa/unblob from Phase 3's static surface.
**Delivers:** `jobs.py::BackgroundJobRegistry`, `tools/re_jobs.py::{start_tool_job, get_tool_job, cancel_tool_job, list_tool_jobs}`. `session_state.py` gains `JOBS` slot. `app.py::lifespan` adds the registry.
**Addresses:** Pitfalls 4 (cancellation race tests), 8 (orphan jobs/log growth), 18 (CancelledError → killpg in worker tasks).
**Implementation cost:** HIGH.

### Phase 6: Extraction Tier

**Rationale:** Depends on Runner + Artifacts + Jobs (unblob on big firmware). Introduces `promote_extracted_sample` — the canonical "extract → promote child → triage child → recurse" RE workflow as one MCP call.
**Delivers:** `tools/re_extract.py::{run_binwalk, run_unblob, run_upx_test, run_upx_list, run_upx_unpack, extract_embedded_files, list_extracted_files, promote_extracted_sample}`.
**Addresses:** Pitfall 7 (symlinks/archive bombs), Pitfall 8 partial (unblob runs as a job).
**Implementation cost:** MEDIUM.

### Phase 7: Dynamic Lab Mode (env-gated default-off)

**Rationale:** Reuses Phase 4's session plumbing (gdb session) + Phase 2's Runner (strace/ltrace/qemu) + Phase 5's job system (long traces). Env-gate lands in `tools/__init__.py`. `run_docker.sh --dynamic` surfaces the env var. Per-call `unshare --net` for no-net enforcement.
**Delivers:** `tools/re_dynamic.py::{run_strace, run_ltrace, run_qemu_user, open_gdb_session, gdb_exec, close_gdb_session}`, `sessions/gdb.py` (gdb MI3 with sentinel marker), dynamic-mode env-gate in `tools/__init__.py`, `--dynamic` flag in `run_docker.sh`, `get_dynamic_capabilities()` probe (ptrace_scope, binfmt status).
**Addresses:** Pitfalls 4 (`strace -f` follow-fork tests), 6 (gdb pager-off + MI3 markers), 9 (netns enforcement), 10 (qemu binfmt drift detection), 11 (ptrace permission probe), 14 (mount-ns deferred decision).
**Implementation cost:** HIGH.

### Phase 8: Orchestrator Skill Update

**Rationale:** Lands LAST among code phases because it references tools that must exist. Critical: must preserve dual-mode operation — the inside-container agent has no MCP target, so skill steps need MCP-or-bash-fallback decision rules.
**Delivers:** Updated `workspace/.claude/skills/malware-analysis-orchestrator/` — backend priority `IDA > BN > Ghidra`, deep RE checklists (W-1 packed-binary triage, W-2 ELF deep-dive, W-3 PE deep-dive, W-4 ROP hunt, W-5 dynamic API trace, W-6 firmware unpack, W-7 cross-arch IoT), `CURRENT_STATE.json` dynamic-mode flag, dual-mode-test that snapshots SKILL.md and fails CI on unconditional `mcp__mare__*` references with no `scripts/` fallback.
**Addresses:** Pitfall 16 (dual-mode preservation), Pitfall 13 note ("remote orchestrator should not assume sole gateway ownership").
**Implementation cost:** MEDIUM.

### Phase Ordering Rationale

- **F-1 first (everyone agrees).** Image-hash carryover is the root cause of the 2026-05-11 UAT failure.
- **Runner before wrappers.** Wrappers can't compile without the runner type; runner's OOM/cancel/timeout properties must be proven before tools build on top.
- **Wrappers (Phase 3) before sessions (Phase 4) before jobs (Phase 5).** Each phase exercises the lifespan/state pattern at lower complexity before the next builds on top.
- **Extraction (Phase 6) needs jobs.** Unblob on multi-GB firmware exceeds 60 s MCP request cap.
- **Dynamic (Phase 7) last among code.** Gdb piggybacks on session plumbing. Env-gate keeps the default container shape unchanged.
- **Skill (Phase 8) very last.** References all primitives.

**Parallelization opportunities:**

- F-1 (shell) and Phase 2 (Python) can land simultaneously.
- Phase 3's `re_artifacts.py` is independent of the static wrappers.
- Phase 5 (jobs) and Phase 6 (extraction) can interleave.
- Phase 7's gdb session work and the strace/ltrace/qemu wrappers are independent within the phase.

### Research Flags

**Phases that need deeper research during planning:**

- **Phase 7 (Dynamic Lab Mode):** Multiple unresolved sub-decisions — per-call netns mechanism, binfmt detection + helper, ptrace probe error UX, gdb MI3 edge cases. PITFALLS.md cataloged 6 distinct pitfalls (4, 6, 9, 10, 11, 14) clustered in this phase. **Recommend `/gsd-research-phase` before planning Phase 7.**
- **Phase 4 + Phase 5:** Need phase-level decisions on session resource limits and log retention/rotation. **Light research.**
- **Phase 3 (`run_shell`):** Final decision on env whitelist contents and `mare-shell` UID's primary group ACL on existing case-dirs. **Light research.**

**Phases with well-documented standard patterns (skip dedicated research):**

- **Phase 1 (F-1):** Trivial shell-script edit.
- **Phase 2 (ReToolRunner):** Well-established asyncio patterns.
- **Phase 6 (Extraction):** Direct CLI wrappers; stable output formats.
- **Phase 8 (Skill):** Content work.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | **HIGH** | All recommendations are pinned versions of mature libraries; each verified on PyPI; v1.0 stack unchanged. |
| Features | **HIGH** | Analyst workflows W-1..W-7 are decades-stable RE practice; tool-specific argv conventions are long-stable; JSON-output flag availability verified per tool. |
| Architecture | **HIGH** | Built on direct file inspection of the shipped v1.0 gateway; every new component fits an existing seam. |
| Pitfalls | **HIGH** | 18 cataloged pitfalls; every one grounded in existing-code review or verified docs; each has a phase mapping and verification test. |

**Overall confidence:** **HIGH**

### Gaps to Address

Items the roadmapper should flag for the relevant phase planner:

- **Netns mechanism for dynamic mode (Phase 7)**
- **Session resource caps (Phase 4)**
- **Job log rotation / retention (Phase 5)**
- **`run_shell` env whitelist contents (Phase 3)**
- **`mare-shell` UID migration (Phase 3)**
- **gdb command allowlist (Phase 7)**
- **r2 dangerous-command refusal regex (Phase 4)**
- **Per-`Mcp-Session-Id` keying timeline** — v1.1 keeps single-session state by design; flag for v1.2 (`GW-V2-03`) as roadmap-known-debt.

---

## Sources

### Primary (HIGH confidence)

**v1.0 codebase (direct file inspection):**

- `mcp-gateway/src/mcp_gateway/subprocess_runner.py`, `app.py`, `session_state.py`, `tools/__init__.py`, `tools/artifacts.py`, `tools/case_dirs.py`, `uploads.py`, `backend/client.py`, `tools/backend_passthrough.py`
- `mcp-gateway/pyproject.toml`, `Dockerfile`
- `.planning/PROJECT.md`, `.planning/MILESTONES.md`, `CLAUDE.md`

**Python / asyncio / MCP standards:**

- [Python 3 asyncio-subprocess docs](https://docs.python.org/3/library/asyncio-subprocess.html)
- [Asynchronous subprocess pipe reading (Stefaan Lippens)](https://www.stefaanlippens.net/python-asynchronous-subprocess-pipe-reading/)
- [MCP Python SDK v1.27.0 release notes](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v1.27.0)
- [MCP transports spec 2025-03-26](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports)
- [Response size limit for MCP responses (#2211)](https://github.com/modelcontextprotocol/modelcontextprotocol/discussions/2211)
- [FastMCP Updates — `ResponseLimitingMiddleware`](https://gofastmcp.com/updates)
- [Truncated MCP Tool Responses (anthropics/claude-code #2638)](https://github.com/anthropics/claude-code/issues/2638)

**Library official sources:**

- [r2pipe](https://pypi.org/pypi/r2pipe/) + [radareorg/radare2-r2pipe](https://github.com/radareorg/radare2-r2pipe)
- [pygdbmi](https://pypi.org/pypi/pygdbmi/) + [GitHub (cs01)](https://github.com/cs01/pygdbmi)
- [capstone](https://pypi.org/pypi/capstone/)
- [ropper](https://pypi.org/pypi/ropper/) + [GitHub (sashs/Ropper)](https://github.com/sashs/Ropper)
- [unblob](https://pypi.org/pypi/unblob/) + [unblob homepage](https://unblob.org/)
- [pexpect](https://pypi.org/pypi/pexpect/)
- [anyio](https://pypi.org/pypi/anyio/)
- [The Official Radare2 Book — rabin2](https://book.rada.re/tools/rabin2/intro.html)

### Secondary (MEDIUM confidence)

- [SentinelOne — Radare2 power-ups for macOS malware](https://www.sentinelone.com/labs/radare2-power-ups-delivering-faster-macos-malware-analysis-with-r2-customization/)
- [Retrieving RAT config statically with radare2](https://radareorg.github.io/blog/posts/malware-static-analysis/)
- [EMBA firmware extraction layer (wiki)](https://github.com/e-m-b-a/emba/wiki/The-EMBA-book-%E2%80%90-Chapter-1:-Firmware-Extraction-Layer)
- [ReFirmLabs/binwalk](https://github.com/ReFirmLabs/binwalk)
- [multiarch/qemu-user-static](https://github.com/multiarch/qemu-user-static)
- [binfmt_misc — Wikipedia](https://en.wikipedia.org/wiki/Binfmt_misc)

---

*Research completed: 2026-05-12*
*Synthesizes: STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md*
*Ready for roadmap: yes*
