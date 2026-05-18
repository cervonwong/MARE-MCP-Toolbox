# Phase 8: Session-Scoped r2 — Research

**Researched:** 2026-05-18
**Domain:** asyncio long-lived subprocess driver + radare2 IPC + session registry + idle reaper + MCP tool surface
**Confidence:** HIGH on (driver semantics, r2 framing, integration shape); MEDIUM on (json-suffix edge cases, idle-reaper interaction with FastMCP shutdown ordering); honest LOW areas flagged below.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

The following 29 decisions are LOCKED by `.planning/phases/08-session-scoped-r2/08-CONTEXT.md`. Research below investigates HOW to implement them, NOT whether to do them. Alternatives are out of scope.

**r2 IPC driver (D-01 .. D-04)**
- D-01: raw `asyncio.create_subprocess_exec` + sentinel-marker read loop. NOT r2pipe.
- D-02: `argv = ["r2", "-2", "-q0", str(sample_path)]`, `cwd=resolved_case_dir`, `start_new_session=True`, stdin/stdout/stderr=`asyncio.subprocess.PIPE`.
- D-03: mandatory init batch BEFORE any user `init_commands`: `e scr.interactive=false; e scr.color=0; e scr.html=0; e cfg.user=mare`. On failure → `killpg` + abort `open_r2_session`.
- D-04: per-session sentinel = `f"__MARE_END_{secrets.token_hex(4)}__"`; per-command flow = write `cmd\n` then `?e SENTINEL\n`, `readuntil(sentinel + b"\n")`.

**Module layout (D-05 .. D-07)**
- D-05: two flat files — `mcp-gateway/src/mcp_gateway/sessions.py` (primitive) + `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` (MCP surface). NO `sessions/` subpackage (Phase 11's job).
- D-06: `sessions.py` MAY import `runner.py` / `artifacts_io.py`; MUST NOT import `tools/*`.
- D-07: `session_state.SESSION_REGISTRY: Optional["SessionRegistry"] = None` slot.

**Dangerous-command refusal (D-08 .. D-09)**
- D-08: full-string regex `r"(?:^|;|\||\n)\s*(?:#!|R!|!)"` applied to `r2_cmd` cmd AND every `init_commands` entry.
- D-09: regex compiled once at module import; refusal is per-command (no session invalidation); covers `!ls`, `#!python`, `R!cmd`, `pdf;!ls`, `aflj|!cat`, newline-embedded injections.

**Output capture / format (D-10 .. D-13)**
- D-10: `r2_cmd(session_id, cmd, *, format: Literal["text","json"] = "text", timeout: float | None = None)`. format="json" auto-appends `j` if cmd doesn't already end in `j`; best-effort `json.loads`; `parsed_json` + `parse_error` fields.
- D-11: result dict = Phase 6 D-03 12-key shape PLUS `session_id`, `session_invalidated`, `format`, `parsed_json`, `parse_error`, `transcript_path`. `stderr_head` always `""` (sentinel reads stdout only).
- D-12: per-command tool-log via `tool_log_path(case_dir, "r2_cmd")` (Phase 6 D-09 shape).
- D-13: session transcript at `r2-sessions/<session_id>-transcript.log` (flat, depth 2), append-only, header/cmd/output/footer format.

**Env-var config (D-14)**
- 5 env vars: `MCP_GATEWAY_SESSION_IDLE_S=1800`, `MCP_GATEWAY_MAX_SESSIONS=8`, `MCP_GATEWAY_R2_CMD_TIMEOUT_S=30.0`, `MCP_GATEWAY_REAPER_INTERVAL_S=60`, `MCP_GATEWAY_SESSION_OPEN_TIMEOUT_S=15.0`.

**Registry / session shape (D-15 .. D-18)**
- D-15: `R2Session` dataclass with `proc`, `pgid`, `lock`, `sentinel`, `transcript_path`, `opened_at`/`_iso`, `last_used_at`, `command_count`, `closed`, `close_reason`.
- D-16: `SessionRegistry` async-context-manager — reaper started in `__aenter__`, cancelled+killpg-all in `__aexit__`. Registry-level lock around cap check + insert (race-free).
- D-17: reaper snapshots via `list(items())`, try/except per iteration, `CancelledError` exits loop, no registry-level lock during enumeration.
- D-18: cap behavior = REJECT (not LRU-evict). Returns `{error, max, open_count, existing: [list_sessions()]}`.

**Tool surface (D-19 .. D-23)**
- D-19: `open_r2_session` step order = `resolve_case_dir → resolve_sample → validate init_commands regex (BEFORE spawn) → registry.open → return dict`.
- D-20: `r2_cmd` step order = validate session_id, validate cmd regex, acquire `sess.lock`, optional `j`-append, send+sentinel read with `asyncio.wait_for`, transcript+log under `asyncio.shield`, return result dict.
- D-21: `close_r2_session` idempotent — returns `ok + already_closed + duration + close_reason`.
- D-22: `list_sessions` returns `{max_sessions, open_count, sessions:[…]}` with `fd_count` (= -1 on `/proc/<pid>/fd` read failure).
- D-23: SESS-05 disclaimer prominently in `open_r2_session` and `r2_cmd` docstrings (full text); `list_sessions` and `close_r2_session` get short form.

**Lifespan / extension (D-24 .. D-26)**
- D-24: `app.py::lifespan` gains `async with SessionRegistry(...)` block INSIDE PinnedBackend block AFTER `assert_no_collisions`. Same block in the `MCP_GATEWAY_SKIP_BACKEND=1` branch.
- D-25: no new collision check (Phase 7 D-12 already covers all gateway-native tool names).
- D-26: `EXPANDED_CASE_SUBDIRS += "r2-sessions"` (one new entry). Resource walker exposes transcripts automatically (depth 2).

**Test design (D-27 .. D-29)**
- D-27: tests split — `test_sessions.py` (registry/reaper internals) + `test_r2_sessions.py` (MCP surface). Per-SC coverage matrix.
- D-28: hermetic tests (`tmp_path`, fixture binaries from Phase 7 D-34); reaper-interval override <10s per test.
- D-29: regression test asserts `EXPANDED_CASE_SUBDIRS` contains `"r2-sessions"`.

### Claude's Discretion

- Whether `sessions.py` / `tools/r2_sessions.py` reuse Phase 6's ANSI-strip + UTF-8-safe head-truncate helpers (recommended: yes, hoist them into `artifacts_io.py` as `strip_ansi(text)` + `truncate_for_response(text, head_kb)` if not already public).
- Whether `r2_cmd` exposes a separate `truncate_kb` kwarg — recommend default-unconditional (uniform with Phase 6).
- Whether `list_sessions` includes raw r2 process info beyond `fd_count` + `pid` (RSS/CPU) — recommend NO for Phase 8.
- Whether `close_r2_session(reason="shutdown")` runs in parallel at lifespan exit — recommend `asyncio.gather(...)` over `self._sessions.values()`.
- Exact `secrets.token_urlsafe(N)` byte length — research says 12; planner may pick 16.
- Whether per-command log files for `r2_cmd` always write even on refused commands — recommend NO (refused commands are pre-protocol, nothing to log).
- Whether the transcript header includes the gateway version / build sha — recommend yes via `_version.py`.
- ANSI-strip on r2 output — defense-in-depth despite `scr.color=0` (recommend YES).
- Whether `r2_cmd` accepts `format="r2"` (raw newline-binary mode) — recommend NO for Phase 8.

### Deferred Ideas (OUT OF SCOPE)

- Per-`Mcp-Session-Id` keying of r2 sessions (`GW-V2-03`) — v1.2.
- `sessions/` subpackage layout (r2.py + gdb.py + registry.py + reaper.py) — Phase 11.
- `format="r2"` (raw binary newline-framed) mode — v1.2+.
- r2 plugin support in sessions (`r2ghidra`, `r2dec-js`) — out of scope (attack-surface expansion).
- LRU-evict instead of cap-reject — rejected for silent-state-loss reason.
- Session-restart-recovery — in-memory registry by design.
- Convergence of `subprocess_runner.run_script` and `ReToolRunner` and Phase 8's r2-driver — v1.2+.
- r2-session-scoped UID drop (e.g., `mare-shell`) — out of scope; r2 stays as `agent`.
- MCP progress reporting for long r2 commands — r2 doesn't emit progress; use Phase 9 jobs as the long-r2 escape hatch.
- Multi-line / heredoc commands via `r2_cmd` — split client-side or write a temp file + `r2_cmd(sid, ". /tmp/script.r2")`.
- Auto-checkpointing of r2 project state (`Ps`/`Po` per N commands) — v1.2+.

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID      | Description (verbatim from REQUIREMENTS.md)                                                                                                                                                                            | Research Support                                                                                                                                                                                |
|---------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| SESS-01 | Agent can open a persistent r2 analysis session via `open_r2_session(case_dir, sample, init_commands)`, receive an opaque session_id, and reuse r2's analysis state (e.g., results of `aaa`) across subsequent calls.  | Standard Stack — `asyncio.create_subprocess_exec`; Pattern 1 (R2Session lifecycle); Code Example "open + persist analysis state"; D-04 sentinel framing keeps the single r2 process alive.       |
| SESS-02 | Agent can execute arbitrary r2 commands in an open session via `r2_cmd(session_id, cmd, format)` with output head-truncated + full output captured.                                                                    | Pattern 2 (sentinel-marker per-command IPC); D-11 result-dict shape; D-12 per-command log; Pitfall (sentinel collision); Code Example "r2_cmd with json suffix".                                  |
| SESS-03 | Agent can close a session via `close_r2_session(session_id)` and enumerate active sessions via `list_sessions()`.                                                                                                       | Pattern 3 (idempotent close via process-group kill); Pattern 4 (`/proc/<pid>/fd` FD count); Code Example "close + list".                                                                          |
| SESS-04 | r2 sessions are auto-reaped after configurable idle (default 30 min); session cap (default 8) enforced; sessions surviving gateway shutdown are killed (no zombies).                                                    | Pattern 5 (idle reaper as lifespan-owned background task); Pattern 6 (registry async-context-manager pairs `__aenter__`/`__aexit__` with reaper-cancel + killpg-all); Pitfall 5 mitigation.       |
| SESS-05 | Sessions are shared across all MCP clients with the same bearer token (single-tenant by design); limitation documented in tool docstrings (per-`Mcp-Session-Id` keying deferred to v1.2).                              | Standard Stack — module-level `SESSION_REGISTRY` mirrors v1.0's `PINNED_BACKEND`; Pitfall 13 (single-session state leak) — defense is the docstring (D-23), not the implementation.               |
| SESS-06 | r2 sessions refuse dangerous shell-escape commands (`#!`, `R!`, `!`) at the wrapper layer; r2 init runs with `scr.interactive=false; scr.color=0`.                                                                      | Pattern 7 (full-string regex over literal-first-char); D-03 mandatory lockdown batch; Pitfall 6 mitigation. Tests cover positive/negative refusal matrix per D-09.                                |

</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Licensing:** IDA Pro/Binja licenses never baked into images — irrelevant to Phase 8 (r2 is open-source). [VERIFIED: CLAUDE.md]
- **Security:** Container runs with `SYS_PTRACE` + `seccomp=unconfined`. Phase 8's r2 inherits this surface. r2 itself does NOT ptrace (no `--debug`), so no incremental risk vs. Phase 7. Tests must NOT depend on these capabilities (they affect dynamic-mode tooling in Phase 11, not r2 static analysis). [VERIFIED: CLAUDE.md §Constraints]
- **Bearer token auth:** Single-token model. SESS-05's "shared-across-bearer-token-clients" disclaimer (D-23) is the direct consequence — REQUIRED in `open_r2_session` and `r2_cmd` docstrings per D-23. [VERIFIED: CLAUDE.md §Authentication & Security]
- **GSD workflow:** All edits go through GSD; planner uses `/gsd:execute-phase`. No direct edits outside workflow. [VERIFIED: CLAUDE.md §GSD Workflow Enforcement]
- **Backward compatibility:** v1.0 "agent inside container" mode must still work — Phase 8 only adds files + extends three modules + adds one lifespan block; no v1.0 surface mutates. [VERIFIED: CLAUDE.md §Project §Core Value]
- **Conventions:** project-level conventions explicitly "not yet established". Defer to v1.1 patterns (Phase 6/7 lock-ins).

## Summary

Phase 8 adds one new primitive (`sessions.py`), one new MCP-tool module (`tools/r2_sessions.py`), and four small extensions (`session_state.SESSION_REGISTRY` slot, `app.py::lifespan` block, `EXPANDED_CASE_SUBDIRS += "r2-sessions"`, `tools/__init__.py` import+register). The 29 locked decisions cover every architectural fork; this research fills in the implementation-level details the planner needs.

The dominant technical question is the r2 IPC contract. CONTEXT.md locks `?e __MARE_END_<8hex>__` as the per-command sentinel, but `r2 -q0` (D-02) **also** natively emits `\x00` after every command's output [VERIFIED: book.rada.re/first_steps/commandline_flags.html]. This is a happy redundancy — the sentinel approach is r2pipe-style framing on top of an already-framed protocol, giving the driver two independent end-of-output markers. Research recommends reading **only** the sentinel (per D-04) and treating any `\x00` bytes as opaque payload — switching to `\x00`-framing would have meant reimplementing r2pipe's protocol, which D-01 explicitly rejected. The redundancy is correctness margin, not branching logic.

The dominant operational risk is reaper / lifespan ordering. The reaper is a background `asyncio.Task` owned by `SessionRegistry.__aenter__`; on shutdown, `mcp.session_manager.run()` cancels in-flight tool calls FIRST (Starlette lifespan semantics), then the SessionRegistry's `__aexit__` runs reaper-cancel + killpg-all. `r2_cmd` calls under cancellation must `asyncio.shield` their transcript+log writes (D-20) so the post-mortem artifact persists even when the reaper is concurrently invalidating the session. This is the Phase 6 D-04 / D-17 contract reused verbatim.

**Primary recommendation:** Implement the locked decisions directly. Hoist `strip_ansi` / `truncate_for_response` helpers into `artifacts_io.py` (Claude's Discretion call) so `sessions.py` doesn't need a private copy. Use `_DANGEROUS_R2_CMD_RE` compiled at module import (per D-09). Pre-create `r2-sessions/` via `ensure_subdir` inside `SessionRegistry.open()` before transcript open. The 13 fixture-binary needs reduce to one: `mcp-gateway/tests/fixtures/hello_elf` (already exists, ~8.7 KB ELF) is sufficient for SC-1 `aaa → aflj` verification.

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `asyncio` | 3.11+ (container) | `create_subprocess_exec`, `Lock`, `wait_for`, `shield`, `gather`, `Task.cancel`, `subprocess.PIPE`, `Process.stdin/stdout`, `StreamReader.readuntil` | Direct lock-in from Phase 6 D-01..D-04 + D-17. Already proven in `runner.py` (the 100MB urandom test passes against this stack). No new pip deps. [VERIFIED: `mcp-gateway/src/mcp_gateway/runner.py`] |
| Python stdlib `dataclasses` | 3.11+ | `R2Session` dataclass per D-15 | Frozen-ish state holder pattern; idiomatic Python. Phase 6/7 don't use dataclasses today, but the field count (12) crosses the "switch from dict to dataclass" threshold. [CITED: Python docs] |
| Python stdlib `secrets` | 3.11+ | `token_urlsafe(12)` session_id, `token_hex(4)` sentinel suffix | Same primitive used by Phase 6 D-09 (`tool_log_path` rand4) and PINNED_BACKEND session model. Cryptographic-grade entropy avoids session-id guessing. [VERIFIED: `mcp-gateway/src/mcp_gateway/artifacts_io.py:128`] |
| Python stdlib `re` | 3.11+ | `_DANGEROUS_R2_CMD_RE = re.compile(r"(?:^|;|\||\n)\s*(?:#!|R!|!)")` compiled once at module import (D-08, D-09) | Direct CONTEXT.md lock-in. |
| Python stdlib `signal` | 3.11+ | `SIGKILL` constant for `killpg` | Phase 6 D-17 pattern reused. |
| Python stdlib `os` | 3.11+ | `getpgid`, `killpg`, `listdir(/proc/<pid>/fd)` for `fd_count` (D-22) | Phase 6 D-17 + Pitfall 5 mitigation. |
| Python stdlib `json` | 3.11+ | `json.loads(stdout_full)` for D-10 `format="json"` parse | Best-effort parsing per D-10 — `parsed_json` on success, `parse_error: str` on failure. Never raises. |
| Python stdlib `time` | 3.11+ | `time.monotonic()` for `opened_at` / `last_used_at` / `duration_s` | Monotonic so reaper math is wallclock-jump-safe. ISO timestamp for transcript header uses `datetime.now(timezone.utc).isoformat()`. [VERIFIED: `artifacts_io.tool_log_path` already uses this pattern] |
| Python stdlib `pathlib.Path` | 3.11+ | All path manipulation; `confine_to` from Phase 6 D-11 | Per D-06 import contract. |
| `radare2` (apt) | 6.x (Kali base) | The r2 binary itself | Already installed in the Kali base image (`Dockerfile:46 nasm radare2 ascii bsdextrautils`). No version pin in Dockerfile; Kali rolling tracks upstream master. `-q0` and `?e` are both present in radare2 4.x+, so any Kali r2 works. [VERIFIED: `Dockerfile` line 46; CITED: book.rada.re/first_steps/commandline_flags.html] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Phase 6 `runner.py` exports | locked | `_ANSI_ESCAPE` regex, `_truncate_to_utf8_boundary`, `_finalize_head` | These are currently module-private (`_`-prefixed) — Claude's Discretion says hoist them to `artifacts_io.py` as `strip_ansi(text: str)` + `truncate_for_response(text: str, head_kb: int)` so `sessions.py` can import without breaking the leaf-module invariant (Phase 6 D-07 says `runner.py` may import from `artifacts_io`, NOT vice-versa). [VERIFIED: `runner.py:46-49`, `runner.py:82-98`, `runner.py:149-157`] |
| Phase 6 `artifacts_io.py` exports | locked | `confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS` | Per D-06 `sessions.py` import contract. |
| Phase 7 `tools.case_dirs.resolve_case_dir` | locked | First call in `open_r2_session` step 1 (D-19) | STATUS_ROOT-aware. |
| Phase 7 `tools.samples.resolve_sample` | locked | Second call in `open_r2_session` step 2 (D-19) | sha256 or case-dir-relative. |
| Phase 7 `tools.collision_check.assert_no_collisions` | locked | No code change — Phase 7 D-12 already covers all gateway-native names including Phase 8's four (D-25) | Verified: `collision_check.assert_no_collisions` iterates `await mcp.list_tools()` which returns the merged surface after `register_all_tools(mcp)` has run. [VERIFIED: `mcp-gateway/src/mcp_gateway/tools/collision_check.py:49`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Raw `asyncio` + sentinel (D-01) | `r2pipe` (Python pkg, sync) | Phase 8 explicitly rejects per D-01. r2pipe is sync → would need `anyio.to_thread.run_sync()` wrapper per call. Breaks Phase 6 D-04 (CancelledError contract — `asyncio.shield(proc.wait())` cleanup cannot interrupt a blocked thread) and Phase 6 D-17 (process-group cleanup via `killpg`). RAW asyncio matches the rest of the gateway exactly. [VERIFIED: CONTEXT.md D-01 rationale; STACK.md] |
| `?e SENTINEL` framing (D-04) | `\x00` framing native to `r2 -q0` | r2 native NUL-byte framing (per `-0` flag) [CITED: book.rada.re/first_steps/commandline_flags.html] would work, BUT (1) reading `readuntil(b"\x00")` instead of `readuntil(b"\n")` complicates stdin/stdout/transcript handling and breaks the line-oriented "head + log" abstraction Phase 6 D-03 establishes, (2) the sentinel approach is explicitly locked by D-04, (3) any binary r2 command that happens to print `\x00` bytes inside its output would desync the NUL-framer (sentinel is randomized + line-anchored, far safer). KEEP D-04. Treat any `\x00` r2 emits as opaque payload. |
| Class-form session registry (D-16) | Free-function module-level dict | Phase 6/7 lifespan integration mandates the async-context-manager protocol (`async with SessionRegistry(...)` per D-24). Free functions can't own a background task with `__aenter__`/`__aexit__` semantics. [VERIFIED: `mcp-gateway/src/mcp_gateway/backend/client.py:35` PinnedBackend pattern] |
| Cap-reject (D-18) | LRU-evict | Rejected per D-18 with research-consensus rationale: LRU-evict silently breaks the evicted client's analysis state, which is hostile to multi-client (same-bearer-token) usage. [VERIFIED: PITFALLS.md Pitfall 5; SUMMARY.md] |
| Flat `sessions.py` (D-05) | `sessions/` subpackage | Phase 11 owns the rename refactor when gdb sessions land. Premature packaging would create empty-shaped speculation. [VERIFIED: CONTEXT.md D-05; SUMMARY.md Phase 4 / Phase 7 ordering] |

**Installation:** No new pip deps required. No new apt packages required. Phase 8 is pure stdlib + reuse of Phase 6/7 helpers.

```bash
# verify no new deps; this is informational, not actionable:
grep -n "r2pipe\|radare2" mcp-gateway/pyproject.toml   # expect: no matches
```

**Version verification:**

```bash
# Confirm r2 is in the Kali base apt package list (already verified: Dockerfile:46):
grep radare2 Dockerfile
# Inside container:
r2 -v | head -1
```

The Kali base ships r2 from upstream master (Kali rolling); `?e <text>` and the `-q0` / `-2` flags have existed for many years (radare2 4.x+ definitely; verified via the official book commandline_flags.html page). [CITED: book.rada.re/first_steps/commandline_flags.html] Within-Kali version drift is bounded by Phase 5 (F-1 image-hash fix): a re-pull of the base image triggers a rebuild, so the gateway pins to whatever r2 version the Dockerfile produced at last build.

## Architecture Patterns

### Recommended Project Structure

```
mcp-gateway/src/mcp_gateway/
├── sessions.py                          # NEW (Phase 8 primitive — D-05)
│   ├── _DANGEROUS_R2_CMD_RE             # compiled once at import (D-09)
│   ├── _SESSION_IDLE_S, _MAX_SESSIONS,  # 5 env-var module constants (D-14)
│   │   _R2_CMD_TIMEOUT_S,
│   │   _REAPER_INTERVAL_S,
│   │   _SESSION_OPEN_TIMEOUT_S
│   ├── R2Session                        # dataclass (D-15)
│   └── SessionRegistry                  # async-context-manager (D-16)
│       ├── __aenter__/__aexit__         # reaper task + killpg-all on exit
│       ├── open()                       # spawn + lockdown + insert
│       ├── get()/close()/list()/count_open()
│       └── _reaper_loop()               # idle reaper (D-17)
│
├── tools/
│   └── r2_sessions.py                   # NEW (Phase 8 MCP surface — D-05)
│       ├── register(mcp)                # invoked from tools/__init__
│       ├── open_r2_session              # D-19
│       ├── r2_cmd                       # D-20
│       ├── close_r2_session             # D-21
│       └── list_sessions                # D-22
│
├── session_state.py                     # EXTEND — add SESSION_REGISTRY slot (D-07)
├── artifacts_io.py                      # EXTEND — append "r2-sessions" to EXPANDED_CASE_SUBDIRS (D-26)
│                                         #         optionally hoist strip_ansi / truncate_for_response helpers
├── app.py                                # EXTEND — async with SessionRegistry(...) block (D-24)
│                                         #         in BOTH backend and SKIP_BACKEND branches
└── tools/__init__.py                    # EXTEND — `from . import r2_sessions` + register call (D-05)

mcp-gateway/tests/
├── test_sessions.py                     # NEW — registry/reaper internals (D-27 split)
├── test_r2_sessions.py                  # NEW — MCP surface (D-27 split)
└── (test_artifacts_io.py augmented      # D-29 regression: EXPANDED_CASE_SUBDIRS contains "r2-sessions")
```

### Pattern 1: Async-Context-Manager Registry with Lifespan-Owned Reaper

**What:** `SessionRegistry` owns a background `asyncio.Task` (the reaper) that polls every `MCP_GATEWAY_REAPER_INTERVAL_S` for stale sessions. Lifespan ownership = the reaper is started in `__aenter__` and cancelled+awaited in `__aexit__`. On `__aexit__` the registry also kills every open session via `killpg`.

**When to use:** Every long-lived MCP gateway resource that has a background cleanup task. Phase 9 jobs will reuse this exact pattern. Phase 11 will refactor to a shared base class.

**Reference implementation:** v1.0's `PinnedBackend` (`backend/client.py`) is the canonical reference — async-context-manager that holds a long-lived resource (`ClientSession`) plus an `AsyncExitStack` for ordered teardown. `SessionRegistry` is the same shape WITH a background task instead of a single resource. [VERIFIED: `mcp-gateway/src/mcp_gateway/backend/client.py:35-81`]

**Example (skeleton from CONTEXT.md D-16 + D-17, paraphrased):**

```python
# sessions.py
class SessionRegistry:
    def __init__(self, *, max_sessions: int, idle_s: float, reaper_interval_s: float) -> None:
        self._max = max_sessions
        self._idle_s = idle_s
        self._reaper_interval_s = reaper_interval_s
        self._sessions: dict[str, R2Session] = {}
        self._lock = asyncio.Lock()           # registry-level cap+insert
        self._reaper_task: asyncio.Task | None = None

    async def __aenter__(self) -> "SessionRegistry":
        self._reaper_task = asyncio.create_task(self._reaper_loop())
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # 1) Cancel reaper FIRST so it doesn't race close() during shutdown.
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except asyncio.CancelledError:
                pass
            except Exception:
                log.exception("[sessions] reaper raised on shutdown")
        # 2) Close every open session in parallel (Claude's-Discretion: gather).
        sids = list(self._sessions)
        if sids:
            await asyncio.gather(
                *(self.close(sid, reason="shutdown") for sid in sids),
                return_exceptions=True,  # one bad close must not block the others
            )

    async def _reaper_loop(self) -> None:
        while True:
            await asyncio.sleep(self._reaper_interval_s)
            try:
                now = time.monotonic()
                stale = [
                    sid for sid, sess in list(self._sessions.items())
                    if not sess.closed and (now - sess.last_used_at) > self._idle_s
                ]
                for sid in stale:
                    try:
                        await self.close(sid, reason="idle")
                    except Exception:
                        log.exception("[sessions] reaper failed to close %s", sid)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("[sessions] reaper iteration crashed; continuing")
```

[VERIFIED: pattern matches `mcp-gateway/src/mcp_gateway/backend/client.py:35-81`; CITED: CONTEXT.md D-16/D-17]

### Pattern 2: Sentinel-Marker Per-Command IPC

**What:** Each session has a unique sentinel string. After writing the user command, the driver writes `?e <SENTINEL>\n` to r2's stdin (r2's `?e` echos a string verbatim to stdout). The reader does `readuntil(SENTINEL + b"\n")` and treats everything before the sentinel line as the command's output.

**When to use:** Phase 8 only (Phase 11 gdb will use the equivalent `printf "__MARE_END__\n"` pattern, but the gdb-MI3 native `^done`/`^error` markers may make that unnecessary — Phase 11's call).

**Key properties:**
1. **Per-session randomization** (D-04 `secrets.token_hex(4)` → 8 hex chars → 32 bits entropy) → collision probability 2⁻³² per session. With 8 concurrent sessions × 100 commands × full session lifetime, the birthday-collision probability is ~10⁻⁷. Practically zero. Cheap to eliminate via per-session randomization.
2. **Line-anchored** (`readuntil(SENTINEL + b"\n")`) — even if r2 emits the sentinel substring mid-line (impossible without `?e SENTINEL` from US, but defense-in-depth), the line-anchor means it must appear standalone.
3. **r2 `?e` semantics:** `?e <text>` prints `<text>\n` to stdout exactly. Researched: `?e` is documented in book.rada.re/refcard. [CITED: book.rada.re/refcard/intro.html]
4. **Latent dual-framing redundancy:** `r2 -q0` (per D-02) ALSO emits `\x00` after every command's output [VERIFIED: book.rada.re/first_steps/commandline_flags.html]. The sentinel is an explicit higher-level frame layered on top of an already-framed protocol. Reading by sentinel ignores the `\x00` bytes (they appear inside `buf` and pass through to the per-command log + transcript as opaque bytes). This is correctness margin, NOT branching logic.

**Example:**

```python
# sessions.py — inside R2Session, called under sess.lock
async def _exec_one(self, cmd: str, timeout: float) -> tuple[bytes, bool]:
    """Send cmd + sentinel, read until sentinel-line. Returns (raw_stdout_bytes, timed_out)."""
    self.proc.stdin.write(cmd.encode("utf-8") + b"\n")
    self.proc.stdin.write(f"?e {self.sentinel}\n".encode())
    await self.proc.stdin.drain()
    sentinel_line = (self.sentinel + "\n").encode()
    try:
        raw = await asyncio.wait_for(
            self.proc.stdout.readuntil(sentinel_line),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        return b"", True
    # raw includes the sentinel line at the end; strip it.
    return raw[: -len(sentinel_line)], False
```

[CITED: CONTEXT.md D-04]

### Pattern 3: Process-Group Cleanup on Close (Phase 6 D-17 Reuse)

**What:** Every session spawns with `start_new_session=True`; the registry stores `pgid = os.getpgid(proc.pid)`. Close path:

```python
async def close(self, session_id: str, *, reason: str = "user") -> dict:
    sess = self._sessions.get(session_id)
    if sess is None:
        raise KeyError(f"unknown session_id: {session_id}")
    if sess.closed:
        return {"ok": True, "session_id": session_id, "already_closed": True, ...}
    sess.closed = True
    sess.close_reason = reason
    try:
        os.killpg(sess.pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass                                   # already dead is fine — idempotent
    await asyncio.shield(sess.proc.wait())     # Phase 6 D-17 contract reused
    # Best-effort stderr drain (D-11): if r2 wrote anything to stderr, capture once.
    try:
        stderr_bytes = await asyncio.wait_for(sess.proc.stderr.read(8192), timeout=0.5)
    except (asyncio.TimeoutError, Exception):
        stderr_bytes = b""
    # Append transcript close footer + stderr-on-close.
    ...
```

**Critical edge case:** `ProcessLookupError` MUST be suppressed when the r2 process has already exited (idle reaper races, command-timeout-already-killed-it, etc.). `PermissionError` is unreachable in practice (we own pgid) but suppressed for defensive symmetry. This exact suppression pattern is in `runner.py:246-247` and `runner.py:256-257`. [VERIFIED: `mcp-gateway/src/mcp_gateway/runner.py:246`]

### Pattern 4: `/proc/<pid>/fd` FD Count for `list_sessions` Operability (Pitfall 5 Mitigation)

**What:** `list_sessions` reports `fd_count` per session = `len(os.listdir(f"/proc/{sess.proc.pid}/fd"))`. Defends against r2 plugin FD leaks.

**Permission errors to handle (D-22 says "return -1"):**
- `FileNotFoundError` — r2 process died between snapshot and readdir; harmless race.
- `PermissionError` — `/proc/<pid>/fd` requires either same UID or `PTRACE_MODE_READ_FSCREDS` capability. Inside the container, the gateway runs as `agent` and r2 runs as `agent` (same UID), so this is unreachable. SYS_PTRACE is granted to the container regardless [VERIFIED: CLAUDE.md §Constraints]. **HOWEVER**, the test layer runs on the host where r2 spawns as the test user — same UID, also fine.
- `OSError` (generic) — defensive catch-all.
- `NotADirectoryError` — impossible (`/proc/<pid>/fd` is always a dir on Linux).

```python
def _fd_count(pid: int) -> int:
    try:
        return len(os.listdir(f"/proc/{pid}/fd"))
    except (FileNotFoundError, PermissionError, OSError):
        return -1
```

**Why `-1` and not `None`:** D-22 specifies the result-dict shape includes `fd_count: int`. `-1` keeps the type uniform (int always), agents can `if entry["fd_count"] < 0: ...` as a "data unavailable" check.

### Pattern 5: Per-Session `asyncio.Lock` Serializes r2 Commands

**What:** Each `R2Session` has an `asyncio.Lock` (D-15). `r2_cmd` acquires it before writing to `proc.stdin`. This is mandatory — r2's stdin protocol is single-threaded (one command in, output until sentinel, next command in). Two interleaved `r2_cmd` calls on the same session would corrupt the stdout stream.

Different sessions own different locks, so cross-session parallelism is free.

```python
# tools/r2_sessions.py — inside r2_cmd
async with sess.lock:
    if format == "json" and not _ends_in_j(cmd):
        cmd = cmd + "j"
    raw_bytes, timed_out = await sess._exec_one(cmd, timeout=resolved_timeout)
    if timed_out:
        # Whole-session-kill per Pitfall 6 / D-20 step d.
        await registry.close(session_id, reason="timeout")
        return _build_invalidated_result(...)
    # Transcript+log writes UNDER shield (D-20):
    await asyncio.shield(_persist_command_artifacts(sess, cmd, raw_bytes, ...))
```

### Pattern 6: `format="json"` Suffix Append — Conservative Boundary Rule (D-10 + Open Question)

**Issue:** D-10 says "append `j` if it doesn't already end in `j`". Naive `cmd.endswith("j")` is wrong for cases like:
- `cmd="aflj@sym.main"` — already ends in `"n"` (after `@`), but the *command* is already JSON-suffixed (`aflj`). Appending `j` → `aflj@sym.mainj` (BAD — modifies the address spec).
- `cmd="?V"` (version query) — doesn't end in `j`; append gives `?Vj` which r2 will reject. We send it, parse fails, `parsed_json=None + parse_error=...` per D-10. **This is the documented best-effort contract.**

**Recommended rule:**

```python
def _ends_in_j(cmd: str) -> bool:
    """Conservative: only check the substring BEFORE the first r2 separator/modifier.

    r2 command anatomy: <verb>[<separator><modifier>]
    Separators that introduce modifiers (do NOT count toward the j-suffix check):
      '@'  -- temporary offset
      '~'  -- internal grep filter
      '|'  -- shell pipe (refused by D-08 anyway, but defense-in-depth)
      ';'  -- compound (refused by D-08 if dangerous)
      ' '  -- argument

    Whichever appears first defines the base command. Check ends_in_j on the base only.
    """
    seps = "@~| ;"
    base = cmd
    for sep in seps:
        idx = base.find(sep)
        if idx != -1:
            base = base[:idx]
    return base.endswith("j")
```

[ASSUMED: this is the conservative interpretation; r2's actual parse boundary may have edge cases this misses. Tests cover `aflj@sym.main`, `pdf @ sym.foo`, `pdf~call`, `?V`, `aaa`, plain `pdf`.]

**Why this is safe:** D-10 explicitly says "best-effort … leave the raw text head in `stdout_head` so the caller can still inspect" on parse failure. The wrapper does NOT guarantee `parsed_json` is non-None — failure modes are catalogued (`parse_error: str`). So the rule is allowed to be wrong on adversarial inputs; the cost is just a parse_error.

### Pattern 7: Full-String Dangerous-Command Regex (D-08 — Pitfall 6 mitigation)

**What:** A single compiled regex applied to every user command (both `r2_cmd` cmd and every `init_commands` entry) BEFORE any bytes hit r2's stdin.

```python
# sessions.py — module level
_DANGEROUS_R2_CMD_RE = re.compile(r"(?:^|;|\||\n)\s*(?:#!|R!|!)")

def _check_dangerous(cmd: str) -> None:
    """Raise ValueError if cmd attempts a shell escape via #!, R!, or !."""
    if _DANGEROUS_R2_CMD_RE.search(cmd):
        raise ValueError(
            "dangerous r2 command refused: shell-escape prefix "
            "'!' / '#!' / 'R!' is blocked by the gateway wrapper"
        )
```

**Coverage matrix (CONTEXT.md D-09 enumerated cases — RECOMMEND test verbatim):**

| Input                                  | Expected | Reasoning                                        |
|----------------------------------------|----------|--------------------------------------------------|
| `!ls`                                  | REJECT   | `(?:^)\s*(?:!)` — literal first char shell-out   |
| `#!python print(1)`                    | REJECT   | `(?:^)\s*(?:#!)` — script header escape          |
| `R!whoami`                             | REJECT   | `(?:^)\s*(?:R!)` — radare-shell prefix            |
| `pdf ; !ls`                            | REJECT   | `(?:;)\s*(?:!)` — compound shell-out             |
| `aflj | !cat /etc/passwd`              | REJECT   | `(?:\|)\s*(?:!)` — pipe shell-out                 |
| `?e foo\n!ls` (literal newline)        | REJECT   | `(?:\n)\s*(?:!)` — newline-embedded escape       |
| `pi 10` (print 10 instructions)        | ALLOW    | no match                                          |
| `?V` (version)                          | ALLOW    | no match                                          |
| `pdf @ sym.foo`                        | ALLOW    | no match                                          |
| `aaa ; afl`                             | ALLOW    | no `!`-prefixed compound                          |
| `pdf~main` (grep filter)               | ALLOW    | no match                                          |

The full-string scan over `cmd.startswith("!")` is what actually satisfies SESS-06; literal-first-char would miss the four mid-string cases above.

### Anti-Patterns to Avoid

- **`shell=True` anywhere.** Phase 6 invariant; grep-the-source test enforces it. [VERIFIED: `mcp-gateway/tests/test_runner.py:33`]
- **Reading r2's stdin/stdout outside `sess.lock`.** Will corrupt the lock-step protocol. (D-15 lock is mandatory.)
- **Catching `CancelledError` and swallowing it.** Re-raise per Phase 6 D-04 contract. The shield is around the cleanup *write*, not around the cancellation.
- **`asyncio.create_subprocess_exec` without `start_new_session=True`.** Without it, `killpg(pgid, SIGKILL)` won't reach r2's child processes (r2 spawns helpers for some plugins). Phase 6 D-17 lock-in.
- **`proc.stderr.read()` in the main IPC loop.** D-11 mandates `stderr_head = ""` — read stderr ONLY once at session close (D-11 / Pattern 3 above). Concurrent stderr drain would complicate the sentinel lock-step protocol.
- **Eager session-list lock-holding in the reaper.** D-17 explicitly forbids it — snapshot via `list(self._sessions.items())` and operate on the snapshot. CPython GIL makes dict-item enumeration safe under concurrent close.
- **Setting `last_used_at` inside the reaper.** Only `r2_cmd` updates `last_used_at`. The reaper READS it.
- **Spawning a session WITHOUT the four lockdown commands (D-03) succeeding.** If init fails, abort `open_r2_session` (D-03 + D-19 step 3).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| r2 IPC framing | A custom NUL-byte-or-prompt parser | The D-04 sentinel approach (locked) | Locked by CONTEXT.md; r2pipe is rejected (D-01). |
| Process-group cleanup | Per-call ps walking | `start_new_session=True` + `os.killpg(pgid, SIGKILL)` + `asyncio.shield(proc.wait())` | Phase 6 D-17 contract, already battle-tested. |
| ANSI escape stripping | A new regex | Phase 6's `_ANSI_ESCAPE` (`re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")`) | Hoist to `artifacts_io.py` as `strip_ansi(text)`; Phase 6 already proved it's sufficient for `objdump --color`, `grep --color`. r2's `scr.color=0` (D-03) means there shouldn't be ANSI to strip, but defense-in-depth. |
| UTF-8 boundary truncation | Naive `s[:n]` truncation | Phase 6's `_truncate_to_utf8_boundary` | Critical for r2 commands that emit non-ASCII (samples with UTF-8 strings, e.g., `iz` on a localized binary). |
| Tool-log filename construction | Manual datetime+slug+rand | `artifacts_io.tool_log_path(case_dir, "r2_cmd")` | Phase 6 D-09 contract; D-12 references this exact helper. |
| Path traversal rejection | `path.startswith(case_dir)` | `artifacts_io.confine_to(case_dir, path)` | Phase 6 D-11 contract; transcript path resolution MUST use this. |
| Session-id generation | `uuid.uuid4()` (returns hyphenated UUID) | `secrets.token_urlsafe(12)` | More compact (16 chars vs 36), cryptographic-grade, URL-safe. Phase 6 D-09 uses `secrets.token_hex(2)` for collision suffixes — same library. |
| `EXPANDED_CASE_SUBDIRS` membership | Hard-coded `"r2-sessions"` in `tools/r2_sessions.py` | Add ONE entry to `artifacts_io.EXPANDED_CASE_SUBDIRS` (D-26) and use it via `ensure_subdir(case_dir, "r2-sessions")` | Phase 6 D-16 explicitly designed the constant for this extension; Phase 7 D-26 resource walker iterates it. Single source of truth. |
| Transcript writing | Per-session `open` handle held in `R2Session` | Per-command `open(transcript_path, "ab")` — see Pattern 9 below | See Open Question 4 below; recommended for crash-safety. |

**Key insight:** Phase 8 is a *consumer* phase. The temptation to extend `runner.py` or create new helpers is real but unnecessary. CONTEXT.md's D-06 import contract is the contract: `sessions.py` consumes Phase 6/7, never the other way around.

## Runtime State Inventory

Phase 8 is an **additive** phase (Architecture diagram: no v1.0 file rewritten; CONTEXT.md `<domain>` block). It introduces new state (`SessionRegistry`, `r2-sessions/` subdir) but does not rename or migrate any existing state. The runtime state inventory below documents what *new* state is born during Phase 8 execution, not pre-existing state that must be migrated.

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 8 introduces session state (in-memory only) and transcript files (new on first open). No existing database/datastore stores Phase 8 state. | Lazy-create `r2-sessions/<session_id>-transcript.log` via `ensure_subdir(case_dir, "r2-sessions") + confine_to(...)` in `open_r2_session`. |
| Live service config | None — no external service registers Phase 8 session ids. Sessions are in-process and die with the gateway. | None. |
| OS-registered state | r2 subprocesses are registered with the Linux kernel as PGIDs (created via `start_new_session=True`). On gateway shutdown, `SessionRegistry.__aexit__` `killpg`s every PGID (D-16). Verified: confirmed by SC-4 lifespan-teardown test (CONTEXT.md D-27). | Test asserts `os.kill(pid, 0) → ProcessLookupError` after lifespan teardown for every open session. |
| Secrets/env vars | None — Phase 8 adds five env-VAR-named READS (`MCP_GATEWAY_SESSION_IDLE_S`, etc., per D-14) but uses no secrets; the gateway's bearer token is NOT exposed to r2 (r2 inherits `os.environ.copy()` — same as Phase 6/7 runner). | None for migration. Document the 5 env vars in operator runbook (out of Phase 8 scope; Phase 12 skill update may surface them). |
| Build artifacts | None — no pyproject.toml change (no new pip deps, no version bump). No new Dockerfile change (radare2 already in apt list — `Dockerfile:46`). Phase 5 (F-1) ensures gateway-source edits trigger rebuild. | None. |

**Nothing found in category "stored data" / "live service config" / "secrets/env vars" / "build artifacts":** Stated explicitly above — verified by reading CONTEXT.md `<domain>` ("Explicitly NOT in this phase") + the `<canonical_refs>` "Code to modify or extend" section.

## Common Pitfalls

### Pitfall 1: Reaper Cancellation Races with In-Flight `r2_cmd` During Shutdown

**What goes wrong:** During lifespan teardown, `mcp.session_manager.run().__aexit__` cancels in-flight tool calls (including a running `r2_cmd`). Then `SessionRegistry.__aexit__` cancels the reaper. If `r2_cmd` is mid-`sentinel_read` and the reaper is mid-`close(reason="idle")` for the same session, the close path runs twice (race) — one from `r2_cmd`'s `CancelledError` handler (D-20 step d says close on cancel/timeout), one from the reaper.

**Why it happens:** Both call paths share `SessionRegistry.close(...)`. Without idempotency, `killpg` runs twice (second one gets `ProcessLookupError` — harmless), `proc.wait()` runs twice (second one returns immediately, the session is already in `wait`-returned state), transcript-footer line written twice.

**How to avoid:** `close()` MUST be idempotent (D-21 — `already_closed: True`). Use the `sess.closed` flag with a registry-level lock around the flag transition:

```python
async def close(self, session_id: str, *, reason: str = "user") -> dict:
    async with self._lock:                           # serialize the flag transition
        sess = self._sessions.get(session_id)
        if sess is None:
            raise KeyError(f"unknown session_id: {session_id}")
        if sess.closed:
            return {"ok": True, "already_closed": True, ...}
        sess.closed = True
        sess.close_reason = reason
    # OUTSIDE the lock — killpg + proc.wait + transcript footer
    ...
```

**Warning signs:** Transcript footer appears twice in `r2-sessions/<sid>-transcript.log`. Test for it: pytest fixture that closes the session twice in a row asserts only one footer line is written.

### Pitfall 2: Sentinel Collision in r2 Output (Pitfall 6 Mitigation Verification)

**What goes wrong:** If r2 emits a literal string matching `__MARE_END_<8hex>__\n` inside a command's output (e.g., `cat` of a malware string-table grep that happens to contain that prefix), the `readuntil` returns prematurely. The next `r2_cmd` reads the orphaned tail as part of its output → silent desync.

**Why it happens (in theory):** A malicious sample with strings tailored to the sentinel format. With 32 bits of per-session entropy (D-04 — 8 hex chars = 32 bits), the collision probability is 2⁻³² per command — vanishingly small but not impossible.

**Why it doesn't happen in practice (defense):**
1. The full sentinel line is `__MARE_END_<8hex>__\n` (~24 bytes). Any natural malware string of this exact shape is birthday-paradox astronomically unlikely.
2. The sentinel is randomized PER session (D-04). An attacker cannot pre-craft a sample to match a known sentinel.
3. The sentinel is line-anchored (`readuntil(sentinel + b"\n")`) — a sentinel substring mid-line won't match.

**How to avoid:** No additional code. Document the failure mode in the `r2_cmd` docstring as a known-and-accepted risk. If this ever manifests in the field, the session is killed (sentinel arrives twice, the next `r2_cmd` `readuntil` blocks until timeout, D-20 step d kicks in, `session_invalidated: true`).

**Warning signs:** A test sends `r2_cmd(sid, "echo __MARE_END_aaaa__\n?V")` and asserts that even when the output coincidentally contains the literal sentinel substring (but with a different hex suffix from the per-session sentinel), the read still framings correctly. Cover this in D-27.

### Pitfall 3: `r2 -q0` Startup Banner / Pre-First-Command Output

**What goes wrong:** r2 may print warnings or notices on stdout BEFORE the first command response. If the driver's first `readuntil(sentinel)` reads through this pre-output, fine. If the first command's sentinel hasn't been written yet (race), the read blocks until init completes.

**Why it happens in theory:** Various r2 flag combinations affect startup output. `-2` (D-02) silences stderr. `-q0` (D-02) means "quiet + emit \x00 after init and every command." `-q0` does emit the post-init `\x00` on stdout. [CITED: book.rada.re/first_steps/commandline_flags.html]

**How to avoid:** D-03's lockdown init sends 4 lines, then ONE sentinel emitter. The first `readuntil(sentinel + b"\n")` consumes (a) the post-`-q0` init `\x00`, (b) any pre-banner stdout that survives `-2`, (c) the 4 lockdown-command outputs (each empty for `e var=val`), (d) the `?e SENTINEL\n` sentinel itself. All in one readuntil. Whatever bytes are read before the sentinel line are written to the per-command log + transcript as the init output (mostly empty + `\x00`).

**Canonical "no-op" command for init sentinel:** Just `?e <SENTINEL>` itself works — `?e` is the sentinel emitter. No extra command needed. The 4 lockdown lines + sentinel emitter is the entire init batch.

**Recommended init batch (single stdin write):**

```python
init_batch = (
    "e scr.interactive=false\n"
    "e scr.color=0\n"
    "e scr.html=0\n"
    "e cfg.user=mare\n"
    f"?e {self.sentinel}\n"
)
self.proc.stdin.write(init_batch.encode())
await self.proc.stdin.drain()
# Now read until sentinel-line; everything before is "init output" (mostly empty).
sentinel_line = (self.sentinel + "\n").encode()
await asyncio.wait_for(
    self.proc.stdout.readuntil(sentinel_line),
    timeout=open_timeout_s,
)
```

[VERIFIED: This is the single-batch-then-sentinel pattern; D-03 says "single newline-joined batch", confirmed.]

**Warning signs:** `open_r2_session` times out at the default 15 s (D-14) on small ELFs. Means r2 didn't reach the sentinel within budget — investigate startup banner. (15 s is generous for r2 + 4 lockdown lines on small samples; large binaries that need `-A` should use `init_commands=["aaa"]` with a larger `open_timeout` override per D-19.)

### Pitfall 4: `init_commands` Containing a Dangerous Command (Validation Order)

**What goes wrong:** Agent passes `init_commands=["aaa", "!ls"]`. r2 is spawned, the 4 lockdown commands run, then `aaa`, then `!ls` is sent — the agent gets a shell escape past the wrapper.

**How to avoid:** D-19 step 3 says "Validate `init_commands` (D-08 regex on each entry) BEFORE spawning r2 — fail fast on dangerous commands without leaving a half-initialized r2." MANDATORY ordering:

```python
async def open_r2_session(case_dir, sample, *, init_commands=None, open_timeout=None):
    resolved_case = resolve_case_dir(case_dir)
    sample_sha, sample_path = resolve_sample(sample)
    # Step 3 (D-19): validate BEFORE spawn.
    for entry in (init_commands or []):
        _check_dangerous(entry)              # raises ValueError on dangerous match
    # NOW spawn:
    return await session_state.SESSION_REGISTRY.open(...)
```

**Warning signs:** A test passes `init_commands=["aaa", "!ls"]` and asserts (a) `ValueError` raises, (b) no `r2-sessions/*-transcript.log` is created, (c) `os.kill(<would-be-pid>, 0)` raises (no r2 spawned).

### Pitfall 5: `format="json"` Auto-Append on Non-Query Commands (Acceptable Failure)

**What goes wrong:** Agent calls `r2_cmd(sid, "aaa", format="json")`. The wrapper appends `j` → `aaaj`. r2 either rejects (silently swallowing) or runs `aaa` and prints non-JSON. `json.loads(stdout_full)` fails. Result dict has `parsed_json: None + parse_error: "..." + stdout_head: <raw>`. Agent sees `parse_error` and falls back to text mode.

**How to avoid:** This is the documented best-effort contract (D-10). Document in `r2_cmd` docstring: "format='json' attempts to coerce the command into r2's JSON output mode by appending 'j'. Not all r2 commands support JSON output; on parse failure, `parsed_json` is None, `parse_error` is set, and `stdout_head` carries the raw text head." The fallback is the contract.

**Boundary rule:** See Pattern 6 above for the `_ends_in_j` conservative rule.

**Warning signs:** Test matrix per D-27 SC-2 covers:
- `r2_cmd(sid, "iij", format="json")` → `parsed_json` non-None, `parse_error: None`.
- `r2_cmd(sid, "?V", format="json")` → `parsed_json: None`, `parse_error: <str>`, `stdout_head` includes version string.

### Pitfall 6: Reading `proc.stderr` Hangs on a Live Session

**What goes wrong:** If a future maintainer adds a `proc.stderr.read(N)` call mid-session (not on close), the read blocks because r2 keeps stderr open but emits nothing (the `-2` flag silences startup stderr; runtime stderr is rare and not framed).

**How to avoid:** D-11 explicitly says `stderr_head = ""` for r2_cmd, and stderr is read ONLY ONCE at session close via `asyncio.wait_for(proc.stderr.read(8192), timeout=0.5)` — bounded and best-effort. Document this in a comment in `sessions.py`. Phase 8 deliberately does NOT drain stderr concurrently. [VERIFIED: CONTEXT.md D-11]

**Async correctness check for stderr-on-close:** `asyncio.subprocess.StreamReader.read(n)` returns when EITHER `n` bytes are read OR EOF is reached. After `killpg(SIGKILL) + await proc.wait()`, stderr's EOF should be detected within microseconds. The `timeout=0.5` is the generous upper bound; in practice the read completes in ~milliseconds. [VERIFIED: Python docs `asyncio.StreamReader.read`]

**Warning signs:** None — this is a "future-proofing the design" pitfall.

## Code Examples

Verified patterns from official sources + CONTEXT.md.

### `SessionRegistry.open` skeleton (D-19 / D-03 / D-16)

```python
# sessions.py
async def open(
    self,
    *,
    case_dir: pathlib.Path,
    sample_sha256: str,
    sample_path: pathlib.Path,
    init_commands: list[str] | None,
    open_timeout_s: float,
) -> R2Session:
    # Cap check + insert under registry lock (D-16):
    async with self._lock:
        if len(self._sessions) >= self._max:
            raise _SessionCapReached(self._max, len(self._sessions), self.list())
        session_id = secrets.token_urlsafe(12)
        # (no concurrent insert wins this slot)

    # Lazy-create r2-sessions/ subdir + transcript path (D-13):
    ensure_subdir(case_dir, "r2-sessions")
    transcript_path = confine_to(case_dir, f"r2-sessions/{session_id}-transcript.log")

    # Spawn r2 (D-02):
    sentinel = f"__MARE_END_{secrets.token_hex(4)}__"
    proc = await asyncio.create_subprocess_exec(
        "r2", "-2", "-q0", str(sample_path),
        cwd=str(case_dir),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    pgid = os.getpgid(proc.pid)

    # Lockdown init batch (D-03):
    init_batch = (
        "e scr.interactive=false\n"
        "e scr.color=0\n"
        "e scr.html=0\n"
        "e cfg.user=mare\n"
        f"?e {sentinel}\n"
    )
    try:
        proc.stdin.write(init_batch.encode())
        await proc.stdin.drain()
        sentinel_line = (sentinel + "\n").encode()
        await asyncio.wait_for(
            proc.stdout.readuntil(sentinel_line),
            timeout=open_timeout_s,
        )
    except (asyncio.TimeoutError, Exception):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        await asyncio.shield(proc.wait())
        raise RuntimeError("r2 init failed: lockdown commands did not complete within timeout")

    # Write transcript header (D-13):
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    with open(transcript_path, "ab") as f:
        f.write(
            f"=== MARE r2_session {session_id} opened {now_iso} "
            f"sample={sample_sha256[:8]} ===\n".encode()
        )

    # Run user init_commands (D-19 step 4 — each goes through the same exec_one path):
    sess = R2Session(
        session_id=session_id,
        case_dir=case_dir,
        sample_sha256=sample_sha256,
        sample_path=sample_path,
        proc=proc,
        pgid=pgid,
        lock=asyncio.Lock(),
        sentinel=sentinel,
        transcript_path=transcript_path,
        opened_at=time.monotonic(),
        opened_iso=now_iso,
        last_used_at=time.monotonic(),
    )

    for ic in (init_commands or []):
        # _exec_one updates last_used_at + writes to transcript
        await sess._exec_one(ic, timeout=open_timeout_s)
        sess.command_count += 1

    # Insert into registry under lock (D-16):
    async with self._lock:
        self._sessions[session_id] = sess
    return sess
```

[CITED: CONTEXT.md D-02, D-03, D-04, D-13, D-15, D-16, D-19; VERIFIED against `runner.py` spawn pattern at `runner.py:217-224`.]

### `r2_cmd` skeleton (D-20 / D-11)

```python
# tools/r2_sessions.py
from typing import Literal

async def r2_cmd(
    session_id: str,
    cmd: str,
    *,
    format: Literal["text", "json"] = "text",
    timeout: float | None = None,
) -> dict:
    """Execute one command in an open r2 session.

    Limitation (v1.1): Sessions are shared across all MCP clients connected with
    the same bearer token. ... [SESS-05 full disclaimer per D-23] ...
    """
    registry = session_state.SESSION_REGISTRY
    if registry is None:
        raise RuntimeError("session registry not initialized — gateway lifespan not running")

    sess = registry.get(session_id)  # raises KeyError → MCP error

    _check_dangerous(cmd)            # D-08 — raises ValueError BEFORE bytes hit r2

    resolved_timeout = timeout if timeout is not None else _R2_CMD_TIMEOUT_S
    started = time.monotonic()
    invalidated = False
    parse_error: str | None = None
    parsed_json = None

    # Optional j-append (D-10):
    sent_cmd = cmd + "j" if (format == "json" and not _ends_in_j(cmd)) else cmd

    async with sess.lock:
        raw_bytes, timed_out = await sess._exec_one(sent_cmd, timeout=resolved_timeout)

    if timed_out:
        await registry.close(session_id, reason="timeout")
        invalidated = True
        stdout_full_text = ""
        exit_code = -9
    else:
        stdout_full_text = strip_ansi(raw_bytes.decode("utf-8", errors="replace"))
        exit_code = 0
        sess.last_used_at = time.monotonic()
        sess.command_count += 1
        if format == "json":
            try:
                parsed_json = json.loads(stdout_full_text)
            except (json.JSONDecodeError, ValueError) as e:
                parse_error = str(e)

    # Per-command log + transcript writes UNDER shield (D-20 step c/d):
    await asyncio.shield(_persist_artifacts(
        sess=sess,
        cmd=sent_cmd,
        stdout_full=stdout_full_text,
        format=format,
        invalidated=invalidated,
        duration_s=time.monotonic() - started,
    ))

    head_kb = STDOUT_HEAD_KB  # from runner module
    stdout_head = truncate_for_response(stdout_full_text, head_kb)
    stdout_bytes_total = len(stdout_full_text.encode("utf-8"))
    log_path_rel = ...  # from _persist_artifacts return

    return {
        # Phase 6 D-03 12-key base:
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": time.monotonic() - started,
        "stdout_head": stdout_head,
        "stdout_truncated": stdout_bytes_total > head_kb * 1024,
        "stdout_bytes_total": stdout_bytes_total,
        "stderr_head": "",                             # D-11: always empty
        "stderr_truncated": False,
        "stderr_bytes_total": 0,
        "log_path": str(log_path_rel),
        "argv": ["r2-session-cmd", session_id[:8], sent_cmd[:120]],
        "slug": "r2_cmd",
        # r2-session extensions (D-11):
        "session_id": session_id,
        "session_invalidated": invalidated,
        "format": format,
        "parsed_json": parsed_json,
        "parse_error": parse_error,
        "transcript_path": str(sess.transcript_path.relative_to(sess.case_dir)),
    }
```

[CITED: CONTEXT.md D-10, D-11, D-20.]

### `app.py::lifespan` extension (D-24)

```python
# app.py — inside the existing lifespan
async with PinnedBackend(backend_name) as pinned:
    session_state.PINNED_BACKEND = pinned
    try:
        await assert_no_collisions(mcp)              # Phase 7 D-11 — UNCHANGED
        # NEW Phase 8 D-24:
        async with SessionRegistry(
            max_sessions=int(os.environ.get("MCP_GATEWAY_MAX_SESSIONS", "8")),
            idle_s=float(os.environ.get("MCP_GATEWAY_SESSION_IDLE_S", "1800")),
            reaper_interval_s=float(os.environ.get("MCP_GATEWAY_REAPER_INTERVAL_S", "60")),
        ) as registry:
            session_state.SESSION_REGISTRY = registry
            try:
                async with mcp.session_manager.run():
                    log.info("[gateway] ready on %s:%s", ...)
                    yield
            finally:
                session_state.SESSION_REGISTRY = None
    finally:
        session_state.PINNED_BACKEND = None
```

Same block (sans the `PinnedBackend` outer layer) goes in the `MCP_GATEWAY_SKIP_BACKEND=1` branch — sessions work standalone without a disassembler backend. [CITED: CONTEXT.md D-24.]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Sync r2pipe (Python) wrapped in `anyio.to_thread.run_sync` | Raw `asyncio.create_subprocess_exec` + sentinel framing | Phase 8 design (CONTEXT.md D-01) | Clean cancellation contract via `asyncio.shield`, no thread boundary. |
| Prompt-detection (`readuntil(b"[0x...]> ")`) | Sentinel-marker (`?e __MARE_END_<8hex>__`) | Pitfall 6 mitigation (CONTEXT.md D-04) | r2 commands that emit prompt-like strings inside output no longer desync the reader. |
| Literal-first-char shell-out refusal (`cmd.startswith("!")`) | Full-string regex `r"(?:^|;|\||\n)\s*(?:#!|R!|!)"` | Pitfall 6 / SESS-06 (CONTEXT.md D-08) | Catches `pdf;!ls`, `aflj|!cat`, newline-injection vectors. |
| Shared global static sentinel | Per-session `secrets.token_hex(4)` sentinel | Defense-in-depth (CONTEXT.md D-04) | Eliminates the (already astronomically unlikely) cross-session sentinel collision. |
| LRU-evict at session cap | Reject + return existing list | Pitfall 5 consensus (CONTEXT.md D-18) | Preserves analyst's analysis state across all sessions; "close one and retry" UX. |
| In-process per-session-file handle | Per-command `open("ab")` write | Crash-safety (Open Question 4 recommendation) | Transcript line is durable after each command, even on gateway crash. |

**Deprecated/outdated:**
- **r2pipe Python (1.x):** sync-only, not suitable for asyncio chokepoint per Phase 8 D-01. r2pipe itself stays as a useful CLI for inside-container scripts; just not the v1.1 gateway driver.

## Assumptions Log

| #  | Claim                                                                                                                            | Section                                | Risk if Wrong                                                                                       |
|----|----------------------------------------------------------------------------------------------------------------------------------|----------------------------------------|-----------------------------------------------------------------------------------------------------|
| A1 | `_ends_in_j` boundary rule (Pattern 6) — only check `cmd` substring before the first `@~| ;` separator                            | Pattern 6 (`format="json"` suffix)     | LOW. Wrong rule → wrong j-append → parse fails → `parse_error` set, `stdout_head` carries raw. Documented best-effort contract per D-10. |
| A2 | The Kali base image's r2 supports `?e` and `-q0` exactly as documented in book.rada.re                                            | Standard Stack — radare2 row           | LOW. r2 4.x+ has both flags. Image is built off Kali rolling, which tracks upstream. Verified via Phase 7 fixture-binary-build which already runs r2-adjacent tooling. [CITED: book.rada.re/first_steps/commandline_flags.html] |
| A3 | `os.listdir(/proc/<pid>/fd)` works for the gateway's own child r2 processes on the Kali container (same UID `agent`)              | Pattern 4 (FD count)                   | LOW. Same UID → same `/proc/<pid>` visibility. SYS_PTRACE granted regardless. Falls back to `-1` on any error (D-22). |
| A4 | r2's `?e <text>` emits exactly `<text>\n` to stdout, regardless of `scr.color` / `scr.html` / `scr.interactive` settings           | Pattern 2 (sentinel framing)           | MEDIUM. If r2 prepends anything (banner, color reset) → the sentinel line won't be the exact bytes `<text>\n`. Mitigation: `?e` is the canonical "echo to stdout, no decoration" command per book.rada.re. Test SC-2 covers the round-trip. [CITED: book.rada.re/refcard/intro.html] |
| A5 | The Phase 7 `mcp-gateway/tests/fixtures/hello_elf` ELF (~8.7 KB) is amenable to `r2 -2 -q0 hello_elf` + `aaa` + `aflj`              | Test Coverage                          | LOW. The fixture is a static x86_64 ELF; r2 handles such ELFs as the canonical sample shape. If r2 refuses (rare), `tests/fixtures/stripped.o` (relocatable object, also present) is the fallback. |
| A6 | `mcp.session_manager.run()` cancels in-flight tool calls BEFORE the outer `SessionRegistry.__aexit__` runs                        | Pitfall 1 (reaper/r2_cmd race)         | MEDIUM. Lifespan teardown order is set by Starlette/uvicorn. If the inverse order happens, the close path runs from the reaper first; idempotent close (D-21) is the defense regardless. |
| A7 | `secrets.token_urlsafe(12)` is sufficient session-id entropy for SESS-05 (single-bearer-token clients are mutually trusted)        | Don't Hand-Roll — session_id gen        | LOW. 12 bytes = 96 bits, URL-safe-base64 → 16 chars. Same-token clients are trusted per SESS-05 by design. |
| A8 | `asyncio.subprocess.StreamReader.read(8192)` on r2's stderr-after-killpg returns within ~0.5 s on the Kali image                   | Pitfall 6 (stderr-on-close)            | LOW. EOF is detected once `proc.wait()` returns (which we await before the stderr read). 0.5 s is 100x typical. |

**Empty-table risk:** None of these assumptions affect the locked decisions in CONTEXT.md; they are implementation-level. The planner can verify each via tests during execution.

## Open Questions

### OQ-1: Does the `?e SENTINEL` sentinel emission go to stdout (line 1) or stderr (line 2)?

- **What we know:** r2's `?e` command is documented as "print string to stdout, like the OS `echo` command." The `-2` flag closes r2's stderr file descriptor (silencing it). `?e` is not affected by `-2`. [CITED: book.rada.re/refcard/intro.html + commandline_flags.html]
- **What's unclear:** Whether r2 might emit a trailing space, color reset, or HTML wrapper around `?e` output under any default state. Our D-03 lockdown explicitly sets `scr.color=0; scr.html=0; scr.interactive=false`, so the output SHOULD be unadorned.
- **Recommendation:** Plan a Wave-0 test (`test_sentinel_framing_roundtrip`) that opens a session, sends `?e __TESTSENTINEL__`, asserts the stdout contains exactly `__TESTSENTINEL__\n`. If r2 surprises us with adornment, the planner can adjust the readuntil string in one place. RISK: LOW.

### OQ-2: Per-session file handle vs. per-command `open("ab")` for transcript writes (Don't-Hand-Roll table)

- **What we know:** Phase 6 D-09 tool-logs are `open(log_abs, "ab", buffering=0)` once per call (`runner.py:229`). Per-command transcript writes here are the same pattern — open, write, close. Linux filesystem `O_APPEND` semantics guarantee atomic-per-write append, so two concurrent `r2_cmd`s on the SAME session (impossible per `sess.lock`) and DIFFERENT sessions (different files) are both safe.
- **What's unclear:** Whether keeping a per-session `BinaryIO` handle open (closing it in `close()`) is materially faster. For 100 r2_cmd calls per session, the difference is ~100 syscalls (`open` + `close` per command) — negligible compared to r2 itself.
- **Recommendation:** Per-command `open("ab")` for crash-safety. If the gateway dies mid-session, the transcript is durable up to the last completed command. The performance cost is negligible. [VERIFIED: matches Phase 6 `runner.py:229` pattern]

### OQ-3: Does r2 close stdin on EOF-from-our-side, gracefully exit?

- **What we know:** When `proc.stdin.close()` is called, r2 should see EOF on its stdin and exit cleanly (it's documented to exit on EOF in interactive mode; `-q0` is non-interactive so behavior may differ). On `killpg(SIGKILL)`, exit is immediate regardless.
- **What's unclear:** Whether stdin-close + `proc.wait` (without killpg) is fast enough that `close_r2_session(reason="user")` could use it as a "graceful close" path before killpg. NOT a Phase 8 requirement — D-21 says use killpg + shielded wait, which matches Phase 6 D-17. Stdin-close-graceful is a v1.2 nicety.
- **Recommendation:** Use killpg + shielded wait per D-21. Document in the close path comment that graceful stdin-close is deferred to v1.2.

### OQ-4: How does the reaper interact with `SessionRegistry._lock`?

- **What we know:** D-17 says "the reaper takes no registry-level lock during enumeration." Reaper does `list(self._sessions.items())` (CPython GIL-safe snapshot), then for each stale sid calls `await self.close(sid, reason="idle")`. `close()` DOES acquire `self._lock` per Pitfall 1's idempotency pattern.
- **What's unclear:** None — the design is clean: enumeration is lock-free (read-only snapshot), state-change is locked (inside close).
- **Recommendation:** Document the reaper-no-lock + close-takes-lock distinction in a docstring comment on `_reaper_loop` and `close` so future maintainers don't "helpfully" add a lock to enumeration.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `r2` (radare2) binary | r2 session spawn (D-02) | ✓ in container | Kali rolling (any 4.x+) | None — fail loud at first `open_r2_session` (raises `FileNotFoundError` from `asyncio.create_subprocess_exec`). [VERIFIED: `Dockerfile:46`] |
| Python `secrets`, `signal`, `asyncio`, `json`, `re`, `dataclasses`, `time`, `pathlib`, `os`, `datetime`, `logging` | All Phase 8 code | ✓ stdlib | 3.11+ | None — stdlib. |
| `/proc/<pid>/fd` readable on Linux | `list_sessions` `fd_count` (D-22) | ✓ Kali container | Linux 6.x | Returns `-1` per D-22. |
| Phase 5 image-hash fix | New `sessions.py` and `tools/r2_sessions.py` files reach the running container | ✓ shipped | — | None — F-1 must be present, blocks Phase 8 e2e. |
| Phase 6 `runner.py` + `artifacts_io.py` | Imports in `sessions.py` (D-06) | ✓ shipped | — | None — direct dependency. |
| Phase 7 `tools.case_dirs.resolve_case_dir` + `tools.samples.resolve_sample` | `open_r2_session` step 1-2 (D-19) | ✓ shipped | — | None — direct dependency. |
| Phase 7 `tools.collision_check.assert_no_collisions` | Lifespan startup (D-25) | ✓ shipped | — | None — already covers Phase 8 tool names per D-12 of Phase 7. |
| Test fixture: `mcp-gateway/tests/fixtures/hello_elf` (8776 bytes ELF) | SC-1 `aaa → aflj` test (D-27) | ✓ shipped | — | `stripped.o` (1376 bytes ELF relocatable) is a smaller fallback if `hello_elf` proves unsuitable. [VERIFIED: `ls mcp-gateway/tests/fixtures/`] |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** None.

**On-host execution caveat:** Tests run on the host where r2 may not be installed (the dev's WSL2 has no r2 binary). Recommend a `_require_r2_or_skip()` helper modeled on Phase 7's `_require_setfacl_or_skip()` (`tests/test_run_shell.py:32`) — tests that actually spawn r2 skip cleanly on hosts without r2, run for real inside the container. Same TDD-discipline pattern Phase 7 already proved. [VERIFIED: `mcp-gateway/tests/test_run_shell.py:32-39`]

## Validation Architecture

Workflow `nyquist_validation: true` per `.planning/config.json`. Include this section.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | `pytest` 8.x + `pytest-asyncio` (asyncio_mode='auto') |
| Config file | `mcp-gateway/pyproject.toml` (asyncio mode), `mcp-gateway/conftest.py` (shared fixtures) [VERIFIED: `mcp-gateway/tests/__init__.py`, `conftest.py` exists] |
| Quick run command | `cd mcp-gateway && pytest tests/test_sessions.py tests/test_r2_sessions.py -x` |
| Full suite command | `cd mcp-gateway && pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID  | Behavior                                                                                  | Test Type | Automated Command                                                                    | File Exists?       |
|---------|-------------------------------------------------------------------------------------------|-----------|--------------------------------------------------------------------------------------|--------------------|
| SESS-01 | `open` returns session_id; `aaa` analysis state persists to next `aflj` call               | integration | `pytest tests/test_r2_sessions.py::test_aaa_aflj_persists -x`                          | ❌ Wave 0 (new)    |
| SESS-02 | `r2_cmd` returns 12-key + 6-extension shape; head-truncated; full log on disk              | unit | `pytest tests/test_r2_sessions.py::test_r2_cmd_result_shape -x`                          | ❌ Wave 0 (new)    |
| SESS-02 | `format="json"` parses known-JSON command (`iij`)                                          | unit | `pytest tests/test_r2_sessions.py::test_format_json_iij -x`                              | ❌ Wave 0 (new)    |
| SESS-02 | `format="json"` graceful-fail on `?V` → parsed_json=None, parse_error set                  | unit | `pytest tests/test_r2_sessions.py::test_format_json_non_json_command -x`                 | ❌ Wave 0 (new)    |
| SESS-03 | `close_r2_session` idempotent; second call returns `already_closed: True`                  | unit | `pytest tests/test_r2_sessions.py::test_close_idempotent -x`                             | ❌ Wave 0 (new)    |
| SESS-03 | `list_sessions` returns `fd_count >= 0` for live session                                   | integration | `pytest tests/test_r2_sessions.py::test_list_fd_count_nonneg -x`                       | ❌ Wave 0 (new)    |
| SESS-04 | Reaper kills idle session within `idle_s + reaper_interval_s` of inactivity                 | integration | `pytest tests/test_sessions.py::test_reaper_kills_idle -x` (override env vars <10s)     | ❌ Wave 0 (new)    |
| SESS-04 | Cap-reject: open N+1 → returns D-18 error dict                                              | unit | `pytest tests/test_sessions.py::test_cap_reject -x`                                      | ❌ Wave 0 (new)    |
| SESS-04 | Lifespan teardown kills every open r2 PID                                                   | integration | `pytest tests/test_sessions.py::test_lifespan_teardown_kills_all -x`                    | ❌ Wave 0 (new)    |
| SESS-05 | `open_r2_session.__doc__` contains full SESS-05 disclaimer (D-23 phrasing)                  | grep-source | `pytest tests/test_r2_sessions.py::test_sess05_disclaimer_in_docstrings -x`              | ❌ Wave 0 (new)    |
| SESS-06 | `r2_cmd(sid, "!ls")` raises ValueError; matrix (positive + negative cases per D-09)         | unit | `pytest tests/test_r2_sessions.py::test_dangerous_cmd_refusal_matrix -x`                | ❌ Wave 0 (new)    |
| SESS-06 | After open, `r2_cmd(sid, "e scr.interactive")` returns `"false"`                            | integration | `pytest tests/test_r2_sessions.py::test_lockdown_init_took_effect -x`                  | ❌ Wave 0 (new)    |
| Pitfall 6 | `r2_cmd(sid, "?I prompt", timeout=2.0)` returns `session_invalidated: true` in <5s          | integration | `pytest tests/test_r2_sessions.py::test_hung_cmd_kills_session -x`                     | ❌ Wave 0 (new)    |
| Pitfall 18 | Cancel `r2_cmd("aaaa")` after 0.5s; r2 PID dead within 200ms                                | integration | `pytest tests/test_r2_sessions.py::test_cancel_propagates_to_killpg -x`                 | ❌ Wave 0 (new)    |
| D-26    | `EXPANDED_CASE_SUBDIRS` contains `"r2-sessions"`                                            | unit | `pytest tests/test_artifacts_io.py::test_expanded_case_subdirs_contains_r2_sessions -x` | ❌ Wave 0 (new entry, file exists) |
| D-26    | Resource walker exposes `mare://cases/<case>/r2-sessions/<sid>-transcript.log`              | integration | `pytest tests/test_resources_phase7.py::test_r2_sessions_transcript_exposed -x`         | ❌ Wave 0 (new entry, file exists) |

### Sampling Rate

- **Per task commit:** `cd mcp-gateway && pytest tests/test_sessions.py tests/test_r2_sessions.py -x` (~5-10 s on host with skips; ~15-30 s in container)
- **Per wave merge:** `cd mcp-gateway && pytest tests/ -x` (full suite; ~30 s host, ~60 s container)
- **Phase gate:** Full suite green + the slow-marked test `test_lifespan_teardown_kills_all` (uses Starlette `LifespanContext`) passes.

### Wave 0 Gaps

- [ ] `mcp-gateway/tests/test_sessions.py` — registry internals + reaper. NEW file.
- [ ] `mcp-gateway/tests/test_r2_sessions.py` — MCP tool surface. NEW file.
- [ ] `_require_r2_or_skip()` helper — add to `mcp-gateway/tests/conftest.py` (or copy the per-file pattern from `test_run_shell.py`). Pattern: `shutil.which("r2") is None → pytest.skip(...)`.
- [ ] Augment `mcp-gateway/tests/test_artifacts_io.py::test_expanded_case_subdirs_catalog` to include `"r2-sessions"` in the expected set (touches existing test).
- [ ] Augment `mcp-gateway/tests/test_resources_phase7.py` with a depth-2 `r2-sessions/` exposure test (new test in existing file).
- [ ] No new test framework install needed — `pytest` + `pytest-asyncio` already pinned.

## Security Domain

`security_enforcement` is not in `.planning/config.json`, so treat as enabled. Phase 8 inherits the v1.0 + v1.1 posture; the new attack surface is bounded.

### Applicable ASVS Categories

| ASVS Category               | Applies | Standard Control                                                                                                                                                                              |
|-----------------------------|---------|-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| V2 Authentication           | no      | Auth is bearer-token on the gateway transport (v1.0). r2 sessions inherit the auth boundary; SESS-05 documents the consequence (shared across same-token clients) per D-23.                   |
| V3 Session Management       | yes     | Session IDs use `secrets.token_urlsafe(12)` (96-bit cryptographic entropy). Reaper enforces idle timeout (D-14). Cap-reject prevents DoS via session-flooding (D-18). Shutdown kills all sessions (D-16). |
| V4 Access Control           | yes     | `confine_to(case_dir, ...)` enforces case-dir confinement on transcript paths. `resolve_case_dir` enforces STATUS_ROOT membership. No new access-control surface beyond Phase 7's.            |
| V5 Input Validation         | yes     | `_DANGEROUS_R2_CMD_RE` (D-08) refuses shell-escape commands. `init_commands` validated BEFORE spawn (D-19 step 3). `cmd` validated BEFORE bytes hit r2 (D-20 step 2).                          |
| V6 Cryptography             | no      | No new crypto. Reuses `secrets` for token generation only.                                                                                                                                    |
| V7 Error Handling & Logging | yes     | Transcript captures every command (D-13) — audit trail. Tool-logs capture every output (D-12). `close_reason` recorded (D-15 / D-21). Reaper logs each kill via stdlib `logging`.                |
| V12 Files & Resources       | yes     | `EXPANDED_CASE_SUBDIRS += "r2-sessions"` (D-26). `confine_to` on transcript path. `ensure_subdir` for lazy creation. Phase 6 D-11..D-14 contracts reused.                                       |

### Known Threat Patterns for r2-driver stack

| Pattern                                                                                            | STRIDE                | Standard Mitigation                                                                                                                                                                                                                                                |
|----------------------------------------------------------------------------------------------------|-----------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| r2 shell-escape via `!`, `#!`, `R!`                                                                | Elevation of Privilege | `_DANGEROUS_R2_CMD_RE` full-string regex (D-08). Per-command refusal. Tests cover compound + pipe + newline injection variants.                                                                                                                                     |
| Session-id guessing (one client guesses another's session_id)                                      | Spoofing              | `secrets.token_urlsafe(12)` — 96 bits cryptographic entropy. SESS-05 explicitly documents the "shared across same-token clients are trusted" model. Documented in `open_r2_session` docstring per D-23.                                                              |
| Resource exhaustion via unlimited concurrent sessions                                              | Denial of Service     | `MCP_GATEWAY_MAX_SESSIONS=8` cap (D-14, D-18); cap-reject NOT LRU-evict.                                                                                                                                                                                              |
| Idle-session leak (analyst disconnects, r2 holds mmap forever)                                     | Denial of Service     | `MCP_GATEWAY_SESSION_IDLE_S=1800` reaper (D-14). Operator-visible via `fd_count` in `list_sessions` (D-22).                                                                                                                                                          |
| Hung command (interactive prompt) blocks session forever                                           | Denial of Service     | `MCP_GATEWAY_R2_CMD_TIMEOUT_S=30.0` per-command timeout (D-14). On timeout: whole-session-kill (D-20 step d). `session_invalidated: true` returned to caller (Pitfall 6 mitigation).                                                                                  |
| Zombie r2 processes after gateway shutdown                                                          | Denial of Service / Tampering | `SessionRegistry.__aexit__` iterates `_sessions` and killpg's every entry (D-16). Tested at SC-4 via Starlette `LifespanContext` (D-27).                                                                                                                       |
| Path traversal via session_id or transcript path                                                   | Tampering             | `session_id = secrets.token_urlsafe(12)` (no caller-controlled bytes). Transcript path = `confine_to(case_dir, f"r2-sessions/{session_id}-transcript.log")` (D-13 + Phase 6 D-11 contract).                                                                          |
| MCP-client-side request cancellation orphans r2 subprocess                                          | Denial of Service     | `asyncio.shield(proc.wait())` cleanup in `close()` ensures wait completes (Phase 6 D-17 reused). `CancelledError` in `r2_cmd` triggers `close(reason="cancelled")` (D-20 step d). Test asserts <200ms cancel-to-dead (D-27 Pitfall 18 row).                          |
| Tool-name collision with future backend adding `open_r2_session` / `r2_cmd` / etc.                   | Tampering             | Phase 7 D-12's `assert_no_collisions` covers ALL gateway-native names, INCLUDING Phase 8's four (D-25 — no new collision check needed). Hard-fail at lifespan startup with EX_CONFIG=78.                                                                              |
| Sentinel collision in r2 output (theoretical)                                                       | Tampering             | Per-session randomized sentinel (D-04, 32 bits entropy). Line-anchored readuntil. Documented as accepted residual risk (Pitfall 2 above).                                                                                                                            |
| Init-time shell-escape via `init_commands=["!ls"]`                                                   | Elevation of Privilege | D-19 step 3 — validate `init_commands` BEFORE spawning r2. No half-initialized r2 created (Pitfall 4).                                                                                                                                                                |
| stderr drain hangs the IPC loop                                                                     | Denial of Service     | `stderr_head = ""` always; stderr read ONLY at close with 0.5s timeout (D-11; Pitfall 6).                                                                                                                                                                            |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` — 29 locked decisions (D-01..D-29). Authoritative.
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` — Phase 6 D-03 (12-key shape), D-04 (never-raises + cancellation), D-08 (env-var pattern), D-09 (tool-log filename), D-11..D-14 (`confine_to`), D-15..D-16 (`ensure_subdir`, `EXPANDED_CASE_SUBDIRS`), D-17 (process-group cleanup).
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` — Phase 7 D-11..D-15 (collision check), D-16 (tools/__init__ pattern), D-26 (resource walker).
- `mcp-gateway/src/mcp_gateway/runner.py` — verified spawn pattern, 12-key result dict, cancellation contract, `_ANSI_ESCAPE` regex, `_truncate_to_utf8_boundary`.
- `mcp-gateway/src/mcp_gateway/artifacts_io.py` — verified `confine_to`, `ensure_subdir`, `tool_log_path`, `EXPANDED_CASE_SUBDIRS`.
- `mcp-gateway/src/mcp_gateway/backend/client.py` — verified `PinnedBackend` async-context-manager pattern (D-16 reference impl).
- `mcp-gateway/src/mcp_gateway/app.py` — verified existing lifespan structure (D-24 insertion site).
- `mcp-gateway/src/mcp_gateway/tools/collision_check.py` — verified `assert_no_collisions` covers all gateway-native tools (D-25 contract).
- `mcp-gateway/src/mcp_gateway/tools/resources.py` — verified depth-2 walker iterates `EXPANDED_CASE_SUBDIRS` (D-26 contract).
- `mcp-gateway/tests/test_runner.py`, `test_artifacts_io.py`, `test_collision_check.py`, `test_run_shell.py` — verified test patterns to mirror.
- `mcp-gateway/tests/fixtures/` — verified `hello_elf` (8776 B) + `stripped.o` (1376 B) ELFs available.
- `Dockerfile:46` — verified `radare2` in apt install line.
- [The Official Radare2 Book — Commandline Flags](https://book.rada.re/first_steps/commandline_flags.html) — verified `-q0` semantics ("quiet + print \x00 after init and every command"), `-2` semantics ("close stderr").
- [The Official Radare2 Book — Reference Card](https://book.rada.re/refcard/intro.html) — `?e` command semantics.

### Secondary (MEDIUM confidence)

- [radare2 GitHub repo](https://github.com/radareorg/radare2) — source of truth for r2 behavior, used as the secondary verification anchor.
- [r2pipe overview (Medium / pancake)](https://medium.com/@trufae/scripting-r2-with-pipes-47a7e14c50aa) — explains the NUL-byte framing inside r2pipe, confirms `r2 -q0` natively NUL-terminates output (independent confirmation of the book.rada.re finding).
- [.planning/research/SUMMARY.md, ARCHITECTURE.md, PITFALLS.md, STACK.md] — research consensus on Phase 8 design.

### Tertiary (LOW confidence)

- WebSearch result on `cfg.user` semantics — not authoritative. D-03 sets `cfg.user=mare` as defense-in-depth per CONTEXT.md; the planner does not need to verify the exact r2 behavior here.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — pure stdlib + reuse of already-shipped Phase 6/7 helpers. r2 binary verified in apt list.
- Architecture patterns: HIGH — PinnedBackend is the canonical async-context-manager reference, ReToolRunner is the canonical cleanup-and-cancellation reference. Both are shipped.
- r2 IPC framing (sentinel): HIGH — `?e` and `-q0` semantics verified against book.rada.re. Sentinel approach is the explicit lock-in (D-04), not an open design.
- `_ends_in_j` boundary rule: MEDIUM — conservative interpretation; adversarial inputs may surprise us, but D-10 contract is best-effort. (Assumption A1.)
- Pitfalls: HIGH — all 6 listed pitfalls have concrete code-level mitigations grounded in Phase 6 contracts or CONTEXT.md decisions.
- Validation Architecture: HIGH — test-map row count matches SC + Pitfall count; each row references a specific async/integration/unit test shape.
- Security: HIGH — ASVS V3 (sessions), V4 (access control), V5 (input validation), V7 (logging), V12 (files) all mapped to a CONTEXT.md decision or Phase 6/7 contract.

**Research date:** 2026-05-18
**Valid until:** 2026-06-15 (~30 days; r2 / radare2 has slow-moving CLI compatibility, the Python stdlib + Phase 6/7 contracts are version-locked).
