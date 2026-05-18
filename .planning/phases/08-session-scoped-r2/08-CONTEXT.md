# Phase 8: Session-Scoped r2 - Context

**Gathered:** 2026-05-18
**Status:** Ready for planning

<domain>
## Phase Boundary

The first persistent-subprocess surface in v1.1: long-lived `r2` analysis
sessions that remote agents can reuse across MCP calls so `aaa` analysis
state (flags, comments, xrefs, decompilation cache) survives between
`r2_cmd` invocations. Without this, agents re-pay 5–30 seconds of `aaa`
on every call and lose every flag/comment they set.

Scope:

- `mcp-gateway/src/mcp_gateway/sessions.py` — `SessionRegistry`,
  `R2Session`, and the reaper task. **Primitive** layer (no MCP
  registration), mirroring Phase 6's `runner.py` / `artifacts_io.py`
  pattern.
- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — four
  MCP-registered tools: `open_r2_session`, `r2_cmd`, `close_r2_session`,
  `list_sessions`.
- Extensions:
  - `mcp-gateway/src/mcp_gateway/artifacts_io.py::EXPANDED_CASE_SUBDIRS`
    grows by one entry (`"r2-sessions"`).
  - `mcp-gateway/src/mcp_gateway/session_state.py` gains one
    `Optional[SessionRegistry]` slot (same pattern as
    `PINNED_BACKEND`).
  - `mcp-gateway/src/mcp_gateway/tools/__init__.py::register_all_tools`
    gains one import + register line for `r2_sessions`.
  - `mcp-gateway/src/mcp_gateway/app.py::lifespan` gains one `async
    with SessionRegistry(...)` block (parallel to `PinnedBackend`)
    that owns the reaper task and kills every session on shutdown.

Explicitly NOT in this phase (deferred to other phases):

- gdb sessions, dynamic-mode tools (`run_strace`, `run_ltrace`,
  `run_qemu_user`, `open_gdb_session`, …) — Phase 11. The session
  driver is designed to be reusable: Phase 11 will refactor
  `sessions.py` into a `sessions/` package with `r2.py` + `gdb.py`
  sharing a common base; that refactor is a Phase 11 line item, not
  Phase 8's concern.
- `jobs.py` / `BackgroundJobRegistry` / `start_tool_job` — Phase 9.
- Extraction tools — Phase 10.
- Per-`Mcp-Session-Id` keying of sessions — explicitly deferred to
  v1.2 by `REQUIREMENTS.md` §"Out of Scope (v1.1)" + SESS-05. Sessions
  remain shared across all MCP clients connected with the same bearer
  token; this limitation is loudly documented in `open_r2_session` and
  `r2_cmd` docstrings.
- Replacing r2pipe with this driver in any v1.0 code path — there is
  none; v1.0 has no r2 surface to migrate.
- Adding an MCP Resource walker depth > 2 — Phase 7 D-26 chose depth 2;
  Phase 8's `r2-sessions/<session_id>-transcript.log` is at depth 2 by
  design (flat naming under `r2-sessions/`), so the existing walker
  exposes it without modification.

</domain>

<decisions>
## Implementation Decisions

### r2 IPC driver

- **D-01:** The session driver uses **raw
  `asyncio.create_subprocess_exec` + a sentinel-marker read loop**, NOT
  r2pipe.

  *Rationale:* r2pipe is sync — every command would require
  `anyio.to_thread.run_sync(r2.cmd, ...)`, adding a thread boundary
  per call. The thread boundary breaks two contracts:
  (a) `asyncio.shield(proc.wait())` cleanup on cancellation (Phase 6
  D-04, Pitfall 18) cannot interrupt a blocked thread; we would have
  to abandon the thread and rely on `killpg` to unblock it via EOF.
  (b) Per-command timeout enforcement (Pitfall 6: 30 s default, kill
  the session on miss, return `session_invalidated: true`) becomes
  "abandon the thread + killpg" rather than a clean
  `asyncio.wait_for(read_until_sentinel, timeout=...)`. Raw asyncio
  matches the rest of the gateway's I/O model exactly and reuses the
  Phase 6 cancellation contract without a thread-offload special
  case.

- **D-02:** r2 is launched with this exact argv:

  ```python
  argv = ["r2", "-2", "-q0", str(sample_path)]
  ```

  - `-2` — silent stderr at startup (suppresses the banner).
  - `-q0` — quiet mode, do not read `~/.radare2rc` / project files;
    avoids leaking user state into a session. Equivalent to "no
    init."
  - `sample_path` is resolved via `samples.resolve_sample(sample)`
    (the v1.0 sha256 / case-dir resolver, same convention as every
    Phase 7 typed wrapper).
  - `-A` (auto-analysis on open) is NOT passed by default. Heavy
    analysis is a user choice via `init_commands=["aaa"]` (or `aa`,
    `aaaa`, etc.) — the requirement says `init_commands` is a
    parameter; the wrapper does not impose `aaa` as a hidden cost.

  `cwd=str(resolved_case_dir)`, `start_new_session=True` (Phase 6
  D-17 process-group cleanup contract applies), `stdin/stdout/stderr`
  = `asyncio.subprocess.PIPE`.

- **D-03:** Mandatory r2 init commands sent BEFORE any user
  `init_commands` and BEFORE the session is registered, in this order:

  ```
  e scr.interactive=false
  e scr.color=0
  e scr.html=0
  e cfg.user=mare
  ```

  Sent as a single newline-joined batch via `proc.stdin.write(...)`
  followed by the per-session sentinel emitter (D-04). If any of the
  four lockdown commands fails (sentinel-marker timeout, non-zero
  return, etc.) the open is aborted, the r2 process is `killpg`-ed,
  and `open_r2_session` returns `{error: "r2 init failed", …}`. This
  closes Pitfall 6 at the protocol layer regardless of what the user
  passes in `init_commands`.

  *Rationale:* `scr.interactive=false` + `scr.color=0` are mandated
  by SESS-06. `scr.html=0` is research-recommended belt-and-braces
  (avoid HTML escapes leaking into structured output if a user sets
  some other r2 mode). `cfg.user=mare` is Pitfall 6's
  defense-in-depth (some r2 commands probe `cfg.user`; setting it
  explicitly to a fixed value avoids surprises).

- **D-04:** Sentinel-marker output framing. Each session gets a
  unique sentinel generated at open time:

  ```python
  sentinel_suffix = secrets.token_hex(4)              # 8 lowercase hex
  sentinel_str = f"__MARE_END_{sentinel_suffix}__"
  sentinel_bytes = (sentinel_str + "\n").encode()
  ```

  Per-command flow:

  ```python
  # Send the user's command, then ask r2 to print our sentinel
  proc.stdin.write(cmd.encode("utf-8") + b"\n")
  proc.stdin.write(f"?e {sentinel_str}\n".encode())
  await proc.stdin.drain()
  # Read stdout until the line equal to sentinel_bytes appears
  buf = bytearray()
  while True:
      line = await proc.stdout.readuntil(b"\n")
      if line == sentinel_bytes:
          break
      buf.extend(line)
  return buf.decode("utf-8", errors="replace")
  ```

  Per-session randomized sentinel prevents the (astronomically
  unlikely but cheap-to-eliminate) case where r2 output contains a
  literal `__MARE_END__` substring from earlier sessions or some
  malware string-table grep. Sidesteps r2 prompt-detection entirely
  (Pitfall 6 mitigation).

### Module layout

- **D-05:** Two new files, mirroring the Phase 6 / Phase 7 split:

  ```
  mcp-gateway/src/mcp_gateway/sessions.py             # primitive
  mcp-gateway/src/mcp_gateway/tools/r2_sessions.py    # MCP surface
  ```

  No `sessions/` subpackage. The subpackage layout
  (`sessions/__init__.py`, `sessions/r2.py`, `sessions/registry.py`,
  `sessions/reaper.py`) is appropriate when Phase 11 adds gdb, NOT
  before. Premature packaging would create empty `gdb.py`-shaped
  speculation in the codebase; Phase 11 owns the rename-only
  refactor.

  *Rationale:* Mirrors `runner.py` (primitive) + `tools/shell.py`
  (MCP surface) split established in Phase 6/7. Consistency wins.

- **D-06:** `sessions.py` MAY import from `runner.py` (e.g., to reuse
  ANSI-strip + UTF-8-safe head-truncate helpers if Phase 6 exported
  them; if not, Phase 8 inlines its own copy) and `artifacts_io.py`
  (`confine_to`, `ensure_subdir`, `tool_log_path`,
  `EXPANDED_CASE_SUBDIRS`). It MUST NOT import from `tools/*`.
  `tools/r2_sessions.py` imports `sessions.py` plus the standard
  Phase 7 conventions (`tools.case_dirs.resolve_case_dir`,
  `tools.samples.resolve_sample`).

- **D-07:** `session_state.py` gains one additional module-level slot:

  ```python
  # mcp-gateway/src/mcp_gateway/session_state.py
  PINNED_BACKEND: Optional["PinnedBackend"] = None
  ACTIVE_CASE: Optional[str] = None
  SESSION_REGISTRY: Optional["SessionRegistry"] = None   # new in Phase 8
  ```

  Tools access the registry via `session_state.SESSION_REGISTRY`;
  pattern is identical to v1.0's `session_state.PINNED_BACKEND`
  access from `tools/backend_passthrough.py`. The v2/`GW-V2-03`
  caveat at the top of `session_state.py` is updated to note the
  shared-across-bearer-token-clients implication (SESS-05).

### Dangerous-command refusal scope (SESS-06)

- **D-08:** Refusal is a **full-string scan**, not literal-first-char.
  Compiled module-level regex:

  ```python
  # sessions.py
  _DANGEROUS_R2_CMD_RE = re.compile(
      r"(?:^|;|\||\n)\s*(?:#!|R!|!)"
  )
  ```

  Applied to every user-supplied command at the wrapper layer (both
  `r2_cmd(cmd)` and every entry in `init_commands` on
  `open_r2_session`). A match raises
  `ValueError("dangerous r2 command refused: shell-escape prefix
  '!' / '#!' / 'R!' is blocked by the gateway wrapper")`.

  *Rationale:* r2 natively supports `;` for compound commands and `|`
  for shell pipes. Literal-first-char (`cmd.startswith("!")`) would
  let `pdf ; !ls`, `aaa | !whoami`, multi-line strings, etc., slip
  past. SESS-06 explicitly says "refuse dangerous shell-escape
  commands at the wrapper layer"; full-string scan is what actually
  satisfies that. Defense-in-depth philosophy carried forward from
  Phases 6 and 7 (Phase 6 D-11 `confine_to` rejects all traversal
  vectors, not just `..` literal; Phase 7 D-09 whitelist env vs
  blacklist).

- **D-09:** The refusal regex is `re.compile`-d once at module
  import. Failure messages name the rejected prefix specifically
  (`'!'`, `'#!'`, `'R!'`) so the operator sees an actionable error.
  Refusal is per-command (one bad command does not invalidate the
  session); the session lock is held only briefly during the regex
  check, before any bytes are written to r2's stdin.

  Regression tests (D-27) cover: `!ls`, `#!python print(1)`,
  `R!whoami`, `pdf ; !ls`, `aflj | !cat /etc/passwd`,
  `?e foo\n!ls` (newline-embedded), `init_commands=["aaa", "!ls"]`
  (init-time refusal), and a no-false-positive test
  (`pi 10`, `?V`, `pdf @ sym.foo`, `aaa ; afl` — all allowed).

### Output capture & `format` parameter

- **D-10:** `r2_cmd(session_id: str, cmd: str, *, format:
  Literal["text", "json"] = "text", timeout: float | None = None) ->
  dict`. The `format` parameter behavior:

  - `format="text"` (default): the command is sent verbatim. Result
    has `parsed_json: None`.
  - `format="json"`: the command is sent with a `j` suffix appended
    if it does not already end in `j` (e.g., `pdf` → `pdfj`, `aflj`
    stays `aflj`). After read, attempt `json.loads(stdout_full)`. On
    success, populate `parsed_json` with the result. On parse
    failure (some r2 commands don't support `j`, or output is
    truncated past valid JSON), set `parsed_json: None`,
    `parse_error: str` (the exception message), and leave the raw
    text head in `stdout_head` so the caller can still inspect.

  *Rationale:* r2's `j` suffix convention is universal across r2's
  query commands (`pdfj`, `aflj`, `iij`, `izj`, …). Surfacing it as a
  named parameter saves agents from remembering the convention and
  centralizes the JSON-parse error handling. Best-effort parsing
  with a never-throw contract matches Phase 6 D-04's
  "runner.run() never raises on subprocess state."

- **D-11:** The full r2_cmd result dict layers exactly on top of
  Phase 6's 12-key shape (D-03). Additional keys for r2 sessions:

  ```python
  {
      # 12 base keys per Phase 6 D-03:
      "exit_code": int,        # 0 if command completed; -9 if session killed (timeout/cancel)
      "timed_out": bool,
      "duration_s": float,
      "stdout_head": str,      # ANSI-stripped, UTF-8-safe, truncated at MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB
      "stdout_truncated": bool,
      "stdout_bytes_total": int,
      "stderr_head": str,      # always "" — r2 sentinel framing reads from stdout only
      "stderr_truncated": bool,# always false
      "stderr_bytes_total": int,
      "log_path": str,         # case-rel; "tool-logs/<ts>-r2_cmd-<rand4>.txt"
      "argv": list[str],       # ["r2-session-cmd", "<session_id_prefix>", cmd_truncated]
      "slug": str,             # "r2_cmd"
      # r2-session-specific extensions:
      "session_id": str,
      "session_invalidated": bool,   # true iff the session was killed by this call
      "format": Literal["text", "json"],
      "parsed_json": object | None,
      "parse_error": str | None,     # set only if format="json" and parse failed
      "transcript_path": str,        # case-rel; "r2-sessions/<session_id>-transcript.log"
  }
  ```

  Stderr is included for shape uniformity (Phase 6 D-03 lock-in) but
  always empty because the r2 process keeps stderr open without
  framing; framed output comes only via the sentinel-tracked stdout
  channel. Phase 8 deliberately does not drain stderr concurrently
  (would complicate the lock-step protocol); a single best-effort
  `proc.stderr.read(8192)` is captured into the session transcript
  on close (D-13) for post-mortem visibility.

- **D-12:** Per-command tool-log capture. Every successful `r2_cmd`
  call writes its full output (post-sentinel-strip, ANSI-stripped,
  UTF-8-safe) to a file matching Phase 6 D-09's exact filename
  shape:

  ```
  tool-logs/<timestamp>Z-r2_cmd-<rand4>.txt
  ```

  Constructed via `artifacts_io.tool_log_path(case_dir, "r2_cmd")`.
  Uniform with `run_shell` / `run_file` / every Phase 7 wrapper —
  agents calling `get_tool_log(case_dir, log_name, …)` (Phase 7
  D-25) handle r2 outputs identically to subprocess-tool outputs.

- **D-13:** Session-wide transcript. In addition to per-command
  logs, each session writes an append-only transcript at:

  ```
  r2-sessions/<session_id>-transcript.log
  ```

  (Flat — depth 2 — so Phase 7 D-26's `EXPANDED_CASE_SUBDIRS` walker
  at depth ≤ 2 exposes it as `mare://cases/<case>/r2-sessions/<session_id>-transcript.log`
  without modification.)

  Transcript line format (every line newline-terminated):

  ```
  === MARE r2_session <session_id> opened <ISO8601> sample=<sha256_short> ===
  >>> CMD <ISO8601> <duration_s>s format=<text|json> [INVALIDATED]
  <cmd>
  <<< OUTPUT bytes=<stdout_bytes_total> truncated=<bool>
  <full output, ANSI-stripped>
  --- END ---
  >>> CMD …
  …
  === MARE r2_session <session_id> closed <ISO8601> reason=<idle|user|shutdown|timeout> ===
  ```

  Append-only via `tools.re_artifacts.append_artifact`-style
  open-for-append (NOT going through the MCP tool — the session
  driver opens the file directly with `confine_to` first).
  Transcript captures stderr-on-close (D-11) and the close reason.

  *Rationale:* Per-command logs are great for "go look at the
  output of one call." The transcript is the replay artifact —
  "show me what this analyst did in this session." Both have
  legitimate uses; the storage cost is identical bytes and the
  write cost is one extra `open("ab")`-style append per command.

### Config knobs (env vars, Phase 6 D-08 pattern)

- **D-14:** Five new env vars, all read once at `sessions.py` module
  import, sanity-checked (non-negative, in range) at startup, raise
  `RuntimeError` on bad values to fail loud (matches Phase 6 D-08,
  Phase 7 D-24 D-27 D-29):

  | Env var | Default | Purpose |
  |---------|---------|---------|
  | `MCP_GATEWAY_SESSION_IDLE_S` | `1800` (30 min) | Idle threshold the reaper uses to close stale sessions (SESS-04) |
  | `MCP_GATEWAY_MAX_SESSIONS` | `8` | Concurrent-session cap; `open_r2_session` rejects when at cap (SESS-04) |
  | `MCP_GATEWAY_R2_CMD_TIMEOUT_S` | `30.0` | Per-`r2_cmd` wallclock; timeout kills the session, returns `session_invalidated: true` (Pitfall 6) |
  | `MCP_GATEWAY_REAPER_INTERVAL_S` | `60` | Background reaper poll cadence |
  | `MCP_GATEWAY_SESSION_OPEN_TIMEOUT_S` | `15.0` | Combined timeout for r2 spawn + mandatory lockdown (D-03) + user `init_commands` |

  All five overridable per-call via kwarg where applicable (timeouts
  on `r2_cmd` and `open_r2_session`); `MAX_SESSIONS` and
  `SESSION_IDLE_S` and `REAPER_INTERVAL_S` are gateway-wide only.

### `R2Session` shape

- **D-15:** Dataclass with these fields (immutable after open
  except `last_used_at` / `command_count` / `closed`):

  ```python
  @dataclasses.dataclass
  class R2Session:
      session_id: str                          # secrets.token_urlsafe(12)
      case_dir: pathlib.Path                   # resolved (resolve_case_dir output)
      sample_sha256: str                       # 64-char hex from resolve_sample
      sample_path: pathlib.Path                # absolute, as passed to r2
      proc: asyncio.subprocess.Process
      pgid: int                                # os.getpgid(proc.pid) at spawn
      lock: asyncio.Lock                       # serializes per-session commands
      sentinel: str                            # "__MARE_END_<8hex>__"
      transcript_path: pathlib.Path            # case-rel; r2-sessions/<id>-transcript.log
      opened_at: float                         # time.monotonic()
      opened_iso: str                          # ISO8601 wall-clock for transcript header
      last_used_at: float                      # time.monotonic(); updated each cmd
      command_count: int = 0
      closed: bool = False
      close_reason: str | None = None          # "idle" | "user" | "shutdown" | "timeout" | "error"
  ```

  The `lock` serializes ALL commands on this session (the r2
  protocol is single-threaded per process). Different sessions can
  run commands in parallel — each owns its own r2 process and lock.

### `SessionRegistry` shape

- **D-16:** Class lives in `sessions.py`. Async-context-manager so
  `app.py::lifespan` can use it with `async with`:

  ```python
  class SessionRegistry:
      def __init__(self, *, max_sessions: int, idle_s: float,
                   reaper_interval_s: float): ...
      async def __aenter__(self): ...     # start reaper task
      async def __aexit__(self, ...): ... # cancel reaper, killpg every session

      async def open(self, *, case_dir: str, sample: str,
                     init_commands: list[str] | None,
                     open_timeout_s: float) -> R2Session: ...
      def get(self, session_id: str) -> R2Session: ...   # raises KeyError if missing
      async def close(self, session_id: str, *,
                      reason: str = "user") -> dict: ...
      def list(self) -> list[dict]: ...
      def count_open(self) -> int: ...

      async def _reaper_loop(self) -> None: ...
  ```

  `open` holds a registry-level `asyncio.Lock` while reading
  `count_open()` and inserting the new session, so the cap check
  is race-free against concurrent opens.

  *Rationale:* Async-context-manager pattern matches `PinnedBackend`
  in v1.0 (`app.py:106 async with PinnedBackend(backend_name) as
  pinned:`). The reaper is started in `__aenter__` and cancelled in
  `__aexit__`; shutdown also iterates every open session and runs
  `killpg(SIGKILL)` to satisfy SESS-04's "sessions surviving
  gateway shutdown are killed (no zombie r2 processes)."

- **D-17:** Reaper loop algorithm:

  ```python
  async def _reaper_loop(self):
      while True:
          await asyncio.sleep(self._reaper_interval_s)
          try:
              now = time.monotonic()
              stale_ids = [
                  sid for sid, sess in list(self._sessions.items())
                  if not sess.closed
                  and (now - sess.last_used_at) > self._idle_s
              ]
              for sid in stale_ids:
                  log.info("[sessions] reaping idle session %s", sid)
                  try:
                      await self.close(sid, reason="idle")
                  except Exception:
                      log.exception("[sessions] reaper failed to close %s", sid)
          except asyncio.CancelledError:
              raise
          except Exception:
              log.exception("[sessions] reaper iteration crashed; continuing")
  ```

  Three properties:
  (a) Exceptions inside one iteration never kill the reaper —
      `try/except Exception` wraps each iteration. Only
      `CancelledError` exits the loop (lifespan teardown).
  (b) Snapshotting via `list(self._sessions.items())` avoids
      "dictionary changed size during iteration" if a parallel
      close fires.
  (c) The reaper takes no registry-level lock (close itself does)
      — read-only enumeration is safe under CPython GIL.

- **D-18:** Session cap behavior on overflow: **reject the new
  open**, do NOT LRU-evict. `open_r2_session` returns:

  ```python
  {
      "error": "session cap reached",
      "max": MAX_SESSIONS,
      "open_count": N,
      "existing": [<list_sessions output>],
  }
  ```

  *Rationale:* Research consensus (Pitfall 5, SUMMARY) — "refuse
  `open_*_session` when at cap, return `{error: 'session cap
  reached', existing: [...]}`." LRU-evict would silently break the
  evicted client's analysis state. Caller can call
  `close_r2_session` on a stale entry and retry.

### Tool surface (`tools/r2_sessions.py`)

- **D-19:** `open_r2_session(case_dir: str, sample: str, *,
  init_commands: list[str] | None = None, open_timeout: float | None
  = None) -> dict`. Slug: `r2_open`. Steps:

  1. `resolved_case = resolve_case_dir(case_dir)` (raises `ValueError`
     on bad case_dir).
  2. `sample_sha, sample_path = resolve_sample(sample)` (sha256 or
     case-dir-relative ref).
  3. Validate `init_commands` (D-08 regex on each entry) BEFORE
     spawning r2 — fail fast on dangerous commands without leaving a
     half-initialized r2.
  4. `await session_state.SESSION_REGISTRY.open(case_dir=...,
     sample=..., init_commands=..., open_timeout_s=...)`.
  5. Return dict shape:

     ```python
     {
         "session_id": str,
         "case_dir": str,                       # echoed (resolved)
         "sample_sha256": str,
         "sample_path": str,
         "transcript_path": str,                # case-rel
         "opened_at": str,                      # ISO8601
         "max_sessions": int,                   # echoed cap (operator visibility)
         "open_count": int,                     # AFTER this open
         "init_command_count": int,             # how many user init_commands ran
         "warnings": list[str],                 # e.g., r2 stderr noise during init
     }
     ```

  On cap-exceeded, return the D-18 error dict instead.

- **D-20:** `r2_cmd(session_id: str, cmd: str, *, format:
  Literal["text", "json"] = "text", timeout: float | None = None) ->
  dict`. Slug: `r2_cmd`. Steps:

  1. Validate `session_id` exists in the registry (raises
     `ValueError("unknown session_id: ...")` if not).
  2. Validate `cmd` (D-08 regex). Raises `ValueError` on refusal.
  3. Acquire `sess.lock`. Inside the lock:
     a. Optionally append `j` to cmd if format="json" and cmd
        doesn't already end in `j` (D-10).
     b. Send cmd + sentinel emitter. Read with `asyncio.wait_for(...,
        timeout=timeout or _R2_CMD_TIMEOUT_S)`.
     c. On success: ANSI-strip, UTF-8-safe truncate, write
        per-command log file (D-12), append to transcript (D-13),
        parse JSON if requested (D-10), update
        `sess.last_used_at` + `sess.command_count`.
     d. On `asyncio.TimeoutError` or `asyncio.CancelledError`:
        `await SESSION_REGISTRY.close(session_id, reason="timeout"
        or "cancelled")` — which killpg's the r2 process via D-15's
        `pgid`. Return result dict with `session_invalidated: true`,
        `exit_code: -9`, `timed_out: true`.
  4. Return the D-11 result dict.

  Cancellation contract: even if the runner's awaiter is being
  cancelled, transcript-write + per-command-log-write happen under
  `asyncio.shield(...)` so the artifacts persist (same posture as
  Phase 6 D-04 / D-17).

- **D-21:** `close_r2_session(session_id: str) -> dict`. Slug:
  `r2_close`. Idempotent — closing an already-closed session
  returns `{ok: true, already_closed: true, session_id: ...}` rather
  than raising. Returns:

  ```python
  {
      "ok": True,
      "session_id": str,
      "already_closed": bool,
      "transcript_path": str,
      "closed_at": str,                       # ISO8601
      "command_count": int,
      "duration_s": float,                    # opened_at to closed_at
      "close_reason": Literal["user", "idle", "shutdown", "timeout"],
  }
  ```

  Internally: acquires registry lock briefly to mark `closed=True`,
  releases, then `killpg(pgid, SIGKILL)`, then
  `asyncio.shield(proc.wait())` (Phase 6 D-17 contract reused),
  then writes the transcript-close footer line + flushes.

- **D-22:** `list_sessions() -> dict`. Slug: `r2_list`. Returns:

  ```python
  {
      "max_sessions": int,
      "open_count": int,
      "sessions": [
          {
              "session_id": str,
              "case_dir": str,
              "sample_sha256": str,
              "opened_at": str,
              "last_used_at": str,                # ISO8601
              "idle_s": float,                    # now - last_used_at
              "command_count": int,
              "fd_count": int,                    # len(os.listdir(f"/proc/{pid}/fd")) — Pitfall 5
              "pid": int,
              "transcript_path": str,
          },
          ...
      ],
  }
  ```

  `fd_count` per Pitfall 5: "Track FDs: `len(os.listdir(f'/proc/{proc.pid}/fd'))`
  reported in `list_sessions()` so leaks are visible." If reading
  `/proc/<pid>/fd` raises (process gone, raceful close in flight),
  return `fd_count: -1` rather than throwing — `list_sessions` must
  never fail.

- **D-23:** All four tools include the SESS-05 limitation in their
  docstrings, prominently. Suggested phrasing:

  > **Limitation (v1.1):** Sessions are shared across all MCP
  > clients connected with the same bearer token. A `session_id`
  > returned by one client is accessible to every other client with
  > the same token. Per-`Mcp-Session-Id` keying is deferred to v1.2
  > (`GW-V2-03`). Rotate the bearer token if a new client must not
  > see existing sessions.

  Same disclaimer goes in the `open_r2_session` and `r2_cmd`
  docstrings (the two surfaces an agent reads most). `list_sessions`
  and `close_r2_session` get the shorter form: "See
  `open_r2_session` for the cross-client-sharing limitation."

### Lifespan wiring

- **D-24:** `app.py::lifespan` gains one `async with` block,
  inserted INSIDE the `PinnedBackend` block and AFTER
  `assert_no_collisions(mcp)`:

  ```python
  async with PinnedBackend(backend_name) as pinned:
      session_state.PINNED_BACKEND = pinned
      try:
          await assert_no_collisions(mcp)
          async with SessionRegistry(
              max_sessions=int(os.environ.get("MCP_GATEWAY_MAX_SESSIONS", "8")),
              idle_s=float(os.environ.get("MCP_GATEWAY_SESSION_IDLE_S", "1800")),
              reaper_interval_s=float(os.environ.get("MCP_GATEWAY_REAPER_INTERVAL_S", "60")),
          ) as registry:
              session_state.SESSION_REGISTRY = registry
              try:
                  async with mcp.session_manager.run():
                      log.info("[gateway] ready on %s:%s", …)
                      yield
              finally:
                  session_state.SESSION_REGISTRY = None
      finally:
          session_state.PINNED_BACKEND = None
  ```

  Order matters: `PinnedBackend` → `assert_no_collisions` →
  `SessionRegistry` → `mcp.session_manager.run()`. If collision
  check fails, no SessionRegistry is started (clean shutdown).
  Registry's `__aexit__` kills every open session before
  `PinnedBackend`'s `__aexit__` fires, so no zombie r2's at
  shutdown.

  The `MCP_GATEWAY_SKIP_BACKEND=1` no-backend branch
  (`app.py:87-103`) also gets the `async with SessionRegistry`
  block so r2 sessions work without a disassembler backend (r2 is
  fully standalone).

- **D-25:** No new health endpoint, no new collision check. The
  four r2-session tool names (`open_r2_session`, `r2_cmd`,
  `close_r2_session`, `list_sessions`) are checked against backend
  pass-through by Phase 7's existing `assert_no_collisions`
  (D-12 of Phase 7: "ALL gateway-native tools, not just `run_*`").

### `EXPANDED_CASE_SUBDIRS` extension

- **D-26:** `artifacts_io.py::EXPANDED_CASE_SUBDIRS` grows by one
  entry:

  ```python
  EXPANDED_CASE_SUBDIRS = (
      "tool-logs", "extracted", "hex", "rop",
      "dynamic", "qemu", "disassembly", "decompilation",
      "xrefs",
      "r2-sessions",                  # new in Phase 8
  )
  ```

  Lazy-created on first `open_r2_session` via
  `artifacts_io.ensure_subdir(case_dir, "r2-sessions")` (Phase 6
  D-15 contract). The Phase 7 D-26 resource walker automatically
  picks up `r2-sessions/<id>-transcript.log` at depth 2 — no
  changes to `tools/resources.py` required.

  *Rationale:* Phase 6 D-16 explicitly designed the constant to be
  a "catalog, not a create-all-at-init list," and explicitly
  envisioned future phases extending it (`from
  mcp_gateway.artifacts_io import EXPANDED_CASE_SUBDIRS` is the
  shared name). Phase 8 is the first such extension. Phase 7 D-26
  tests iterate the constant; those tests automatically extend
  coverage to `r2-sessions/` (no test changes needed beyond
  appending the name to the fixture list).

### Test design

- **D-27:** Tests at `mcp-gateway/tests/test_r2_sessions.py` and
  `mcp-gateway/tests/test_sessions.py` (split: registry/reaper
  internals in `test_sessions.py`, MCP tool surface in
  `test_r2_sessions.py`). Required coverage by SC:

  - **SC-1 (analysis state persistence):** `open → r2_cmd("aaa")
    → r2_cmd("aflj")` returns parsed JSON with at least one
    function entry. Asserts state carried across calls.
  - **SC-2 (12-key shape + format=json):** every key in D-11
    present, types match, `parsed_json` non-None for a known JSON
    command (`iij` on a small ELF), `parsed_json=None +
    parse_error` for a known non-JSON command (`?V`) called with
    format="json".
  - **SC-3 (close + list):** `close_r2_session(sid)` returns
    `ok=True`; `list_sessions()` afterwards has empty sessions
    array; `fd_count` field present and non-negative for a live
    session.
  - **SC-4 (reaper + cap):** environment override
    `MCP_GATEWAY_SESSION_IDLE_S=2,
    MCP_GATEWAY_REAPER_INTERVAL_S=1`; open a session, sleep 4
    seconds, `list_sessions` returns empty AND the r2 PID is
    dead (`os.kill(pid, 0)` raises `ProcessLookupError`). Cap
    test: `MCP_GATEWAY_MAX_SESSIONS=2`, open 3 → third returns
    D-18 error dict with `open_count: 2`.
  - **SC-4 (shutdown):** lifespan teardown via Starlette
    `LifespanContext` test; assert all session PIDs are dead
    after teardown.
  - **SC-5 (dangerous-cmd refusal):** matrix listed in D-09
    (positive + negative cases). Each runs `r2_cmd`,
    `init_commands` on `open_r2_session`. Asserts `ValueError`
    with the right message.
  - **SC-5 (mandatory init):** assert that after open, `r2_cmd(sid,
    "e scr.interactive")` returns `"false"` (verifies the D-03
    lockdown actually took effect).
  - **Pitfall 6 (hung command):** `r2_cmd(sid, "?I prompt",
    timeout=2.0)` returns `session_invalidated: true` within 5
    seconds; subsequent `list_sessions` does NOT include the
    invalidated session.
  - **Pitfall 18 (cancellation):** wrap `r2_cmd(sid, "aaaa")` in
    a task with a slow sample, cancel after 0.5s, assert r2 PID
    is dead within 200 ms.
  - **Defense-in-depth on transcript:** open → 3 commands →
    close; assert transcript file contains all 3 commands +
    outputs + the close footer in order; assert per-command logs
    exist with the Phase 6 D-09 filename shape.

- **D-28:** Tests are hermetic — `tmp_path` for case-dirs, the
  fixture-binary directory from Phase 7 D-34 reused for samples
  (small public-domain ELF). No real `STATUS_ROOT` touch. The SC-4
  shutdown test uses Starlette's test client lifespan helpers;
  Phase 7's lifespan test (or a new lightweight one) is the
  pattern. No `slow` markers — every test should complete in <10
  seconds with the reaper-interval override.

- **D-29:** A regression test asserts `EXPANDED_CASE_SUBDIRS`
  contains `"r2-sessions"` (catches accidental Phase 8 reverts).
  Lives in `test_sessions.py` or `test_artifacts_io.py` —
  planner's call.

### Claude's Discretion (within these constraints)

- Whether `sessions.py` and `tools/r2_sessions.py` reuse Phase 6's
  ANSI-strip + UTF-8-safe head-truncate helpers (preferred: yes,
  import them from `runner.py` or `artifacts_io.py`) or inline copies
  — planner's call. Recommendation: hoist them into
  `artifacts_io.py` as `strip_ansi(text)` + `truncate_for_response(text,
  head_kb)` if they aren't there yet, since both runner and r2
  sessions need them.
- Whether `r2_cmd` exposes a separate `truncate_kb: int | None`
  kwarg for per-call head-size override or uses the
  `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB` default unconditionally —
  recommend the default-unconditionally path for uniformity; tools
  needing more bytes use `get_tool_log` on the per-command log.
- Whether `list_sessions` includes raw r2 process info beyond
  `fd_count` and `pid` (e.g., RSS, CPU time) — recommend no for
  Phase 8 (`fd_count` is the leak indicator Pitfall 5 calls out;
  the rest is sysadmin-tier and out of agent scope). Future
  observability work can extend.
- Whether `close_r2_session(reason="shutdown")` runs in parallel
  for every open session at lifespan exit or sequentially —
  recommend a single `await asyncio.gather(...)` over
  `self._sessions.values()` so shutdown is bounded by the slowest
  killpg, not their sum.
- Exact `secrets.token_urlsafe(12)` byte length — research says 12;
  planner may pick 16 if local convention prefers (16-byte token is
  the upper bound before responses get ugly).
- Whether per-command log files for `r2_cmd` always write even on
  refused commands — recommend NO (refused commands are
  pre-protocol; nothing to log). Refusal counts toward the
  transcript footer.
- Whether the transcript header includes the gateway version /
  build sha — recommend yes if cheap, mostly useful for incident
  forensics. Embed via `_version.py` (already imported by `cli.py`).
- ANSI-strip on r2 output — Pitfall 5 mentions `scr.color=0`
  already, so r2 should not emit colors. Defense-in-depth says
  ANSI-strip anyway (some r2 commands print directly to stdout
  bypassing `scr.color`). Reuse Phase 6's helper.
- Whether `r2_cmd` accepts a `format="r2"` (raw) for r2's
  newline-binary output mode — recommend NO for Phase 8; `text` +
  `json` covers 99% of analyst workflow. v1.2 can add if a real
  need emerges.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase spec
- `.planning/ROADMAP.md` §"Phase 8: Session-Scoped r2" — 5 success criteria (SC-1..SC-5)
- `.planning/REQUIREMENTS.md` §Session-Scoped r2 (SESS-01..SESS-06) and §"Out of Scope (v1.1)" (per-`Mcp-Session-Id` keying, restart-persistence)
- `.planning/PROJECT.md` §"Current Milestone: v1.1 Remote RE Tool Expansion" — Session-scoped r2 bullet
- `.planning/STATE.md` §"v1.1 design decisions" — top-level decision rows this phase implements (session model, idle reaper, dangerous-command refusal)

### Prior-phase contracts (lock-ins this phase consumes)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` §Decisions — D-03 (12-key result dict — layered on by D-11 here), D-04 (never-raises + cancellation contract — reused by D-20), D-08 (env-var config pattern — extended by D-14), D-09 (tool-log filename — reused verbatim by D-12), D-11..D-14 (`confine_to` composition — used by transcript write), D-15..D-16 (`ensure_subdir` + `EXPANDED_CASE_SUBDIRS` — extended by D-26), D-17 (process-group cleanup — reused by D-16 `__aexit__` and D-21 close)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` §Decisions — D-11..D-15 (collision check, also covers Phase 8 tool names — see D-25 here), D-16 (tools/__init__.py register pattern — extended by D-05), D-26 (resource walker at depth ≤ 2 — automatically exposes Phase 8's transcript at depth 2 per D-13)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-PLAN.md` and `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-PLAN.md` — concrete module shapes Phase 8 imports from

### Research consensus (cross-document positions)
- `.planning/research/SUMMARY.md` §"Phase 4: Session-Scoped r2" (or equivalent — search for "Session-Scoped r2") — phase-level rationale, consumer mapping
- `.planning/research/SUMMARY.md` §"Critical Pitfalls" — Pitfalls 5 (idle session leaks, reaper, cap), 6 (interactive-prompt hangs, sentinel marker, per-command timeout), 12 (head + log_path return), 13 (single-session state across MCP clients — SESS-05 disclaimer), 18 (FastMCP cancel propagation)
- `.planning/research/SUMMARY.md` §"Open Decisions / Tensions" — confirms 30 min / 8 cap consensus, sentinel-marker over prompt-parse consensus, per-`Mcp-Session-Id` defer consensus
- `.planning/research/PITFALLS.md` §Pitfall 5 (lines 134-160) — idle reaper, session cap, `secrets.token_urlsafe(12)`, r2 launch flags, FD tracking, lifespan-shutdown killpg
- `.planning/research/PITFALLS.md` §Pitfall 6 (lines 164-181) — `e scr.interactive=false` mandatory, sentinel-marker pattern (`?e __MARE_END__`), per-command timeout kills session, `Vp`/`?I`/`!`/`#!` refused at wrapper layer
- `.planning/research/PITFALLS.md` §Pitfall 13 (lines 362-379) — single-session-state across MCP clients limitation; documented in tool docstrings (D-23)
- `.planning/research/PITFALLS.md` §Pitfall 18 — FastMCP cancellation propagates to killpg via `asyncio.shield(proc.wait())` (reused by D-20 timeout/cancel path)
- `.planning/research/ARCHITECTURE.md` — additive-changes diagram; Phase 8 adds one primitive (`sessions.py`), one MCP module (`tools/r2_sessions.py`), one extension (`session_state.SESSION_REGISTRY`), one lifespan block, one `EXPANDED_CASE_SUBDIRS` entry. No v1.0 file rewritten.
- `.planning/research/STACK.md` — confirms r2 is already installed in the Kali base image; r2pipe is mentioned but Phase 8 chooses raw subprocess + sentinel (D-01 rationale); no new pip deps required for Phase 8
- `.planning/research/FEATURES.md` §"Must have" — "Session-scoped r2" listed as a non-negotiable

### Code to modify or extend
- `mcp-gateway/src/mcp_gateway/runner.py` — read-only consumer (Phase 6 D-03 result shape; D-11 here layers on top); MAY need to export an ANSI-strip / truncate helper if not already public
- `mcp-gateway/src/mcp_gateway/artifacts_io.py` — **extend** `EXPANDED_CASE_SUBDIRS` to add `"r2-sessions"` (D-26); reuse `confine_to`, `ensure_subdir`, `tool_log_path` unchanged
- `mcp-gateway/src/mcp_gateway/session_state.py` — **extend** with `SESSION_REGISTRY: Optional["SessionRegistry"] = None` slot (D-07); update the GW-V2-03 caveat at top to mention r2-session sharing (SESS-05)
- `mcp-gateway/src/mcp_gateway/tools/__init__.py` — **extend** `register_all_tools` with one import + register line for `tools.r2_sessions` (D-05)
- `mcp-gateway/src/mcp_gateway/app.py::lifespan` — **extend** with `async with SessionRegistry(...) as registry` block inside both the with-backend and no-backend branches (D-24)
- `mcp-gateway/src/mcp_gateway/tools/case_dirs.py::resolve_case_dir` — read-only consumer (D-19 step 1)
- `mcp-gateway/src/mcp_gateway/tools/samples.py::resolve_sample` — read-only consumer (D-19 step 2)
- `mcp-gateway/src/mcp_gateway/tools/collision_check.py` — no change; Phase 7 D-12 already covers ALL gateway-native tool names (D-25)
- `mcp-gateway/src/mcp_gateway/tools/resources.py` — no change; Phase 7 D-26's depth-≤-2 walker already exposes `r2-sessions/<id>-transcript.log` once `EXPANDED_CASE_SUBDIRS` is extended (D-26)
- `mcp-gateway/pyproject.toml` — no new deps (D-01 rejects r2pipe; raw asyncio is stdlib)
- `Dockerfile` — no change; `radare2` is already installed in the Kali base image (verified by Phase 5/6/7 research)

### Test pattern references
- `mcp-gateway/tests/test_runner.py` (Phase 6) — 12-key result dict assertions, cancellation-within-200ms pattern (reused by D-27 Pitfall 18 test)
- `mcp-gateway/tests/test_artifacts_io.py` (Phase 6) — `EXPANDED_CASE_SUBDIRS` iteration pattern (reused by D-29 regression)
- `mcp-gateway/tests/test_run_shell.py` (Phase 7) — env-scrub assertions; pattern reused for r2's `scr.interactive=false` lockdown assertion
- `mcp-gateway/tests/test_collision_check.py` (Phase 7) — lifespan-test pattern; reused by D-27 shutdown-kills-all-sessions test
- `mcp-gateway/tests/fixtures/` (Phase 7 D-34) — small public-domain ELFs reused as r2 samples in `test_r2_sessions.py`

### Constraint references
- `CLAUDE.md` §Constraints — container runs with SYS_PTRACE + seccomp=unconfined; r2 sessions inherit this surface (no additional posture hardening in Phase 8 because r2 itself doesn't ptrace; that's a Phase 11 concern with strace/ltrace/gdb)
- `CLAUDE.md` §"Recommended Stack > Authentication & Security" — Bearer token model; SESS-05's "shared-across-bearer-token-clients" disclaimer (D-23) is the direct consequence of this design
- `.planning/REQUIREMENTS.md` §"Out of Scope (v1.1)" — per-`Mcp-Session-Id` keying deferred to v1.2; Phase 8 documents the limitation (D-23) rather than implementing the workaround
- `.planning/REQUIREMENTS.md` §"Future Requirements" — `GW-V2-03` ticket tracks the per-session refactor that Phase 8 deliberately does not attempt

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets
- **`mcp-gateway/src/mcp_gateway/runner.py::ReToolRunner` + result-dict
  shape (Phase 6 D-03)** — Phase 8's `r2_cmd` result layers on top
  of this 12-key dict (D-11). If Phase 6 already exports the
  ANSI-strip / UTF-8-safe truncate helpers, reuse them; otherwise
  hoist them in this phase per the Claude's Discretion note. Do NOT
  reimplement.
- **`mcp-gateway/src/mcp_gateway/artifacts_io.py`** — `confine_to`
  used for transcript-path resolution and `r2-sessions/` subdir
  guard; `ensure_subdir` lazy-creates `r2-sessions/`;
  `tool_log_path(case_dir, "r2_cmd")` produces per-command log
  filenames (D-12); `EXPANDED_CASE_SUBDIRS` extended by D-26.
- **`mcp-gateway/src/mcp_gateway/session_state.py`** — module-level
  state pattern (`PINNED_BACKEND`) extended with `SESSION_REGISTRY`
  (D-07). Same `Optional[...]` Optional / lifespan-managed pattern.
- **`mcp-gateway/src/mcp_gateway/app.py::lifespan`** — established
  `async with PinnedBackend(...) as pinned:` pattern; D-24's
  `async with SessionRegistry(...) as registry:` nests inside.
  Lifespan ordering is precise: backend → collision check → session
  registry → mcp.session_manager.run() → yield → teardown in
  reverse.
- **`mcp-gateway/src/mcp_gateway/backend/client.py::PinnedBackend`** —
  reference implementation of `async with`-based, lifespan-owned
  resource holder with `__aenter__` / `__aexit__` cleanup. D-16's
  `SessionRegistry` mirrors this exact pattern (start a background
  task in `__aenter__`, cancel + cleanup in `__aexit__`).
- **`mcp-gateway/src/mcp_gateway/tools/case_dirs.py::resolve_case_dir`**
  and **`tools/samples.py::resolve_sample`** — same composition
  Phase 7 wrappers use: `resolve_case_dir(case_dir)` first, then
  `resolve_sample(sample)`, then `confine_to(...)` on any
  artifact-output paths.
- **`mcp-gateway/src/mcp_gateway/tools/collision_check.py`
  + `assert_no_collisions`** — Phase 7 D-12 covers ALL
  gateway-native tools, so Phase 8's four new tool names are
  collision-checked at lifespan startup automatically (D-25). No
  changes to this module.
- **`mcp-gateway/src/mcp_gateway/tools/resources.py::_build_resource_list`**
  (Phase 7 D-26) — already walks `EXPANDED_CASE_SUBDIRS` at depth
  ≤ 2. Once D-26 here adds `"r2-sessions"` to the constant, the
  walker automatically exposes `r2-sessions/<id>-transcript.log`
  as `mare://cases/<case>/r2-sessions/<id>-transcript.log`. No
  changes to this module.

### Established patterns
- All v1.0 / v1.1 subprocess work uses `asyncio.create_subprocess_exec`
  with `start_new_session=True`; never `shell=True`. Phase 8 inherits
  this (r2 is spawned argv-only per D-02).
- All tests are pytest under `mcp-gateway/tests/`. One fixture per
  test (Phase 5/6/7 discipline). Phase 8 inherits.
- Env vars influencing runtime defaults are read once at module
  import and sanity-checked (`uploads._max_bytes` / Phase 6's
  runner knobs / Phase 7's tree caps). D-14's five new vars
  follow the same pattern.
- Module-level constants UPPER_SNAKE; functions lower_snake;
  classes PascalCase. Dataclasses for state holders (D-15).
- Tool registration: each `tools/<name>.py` exposes `register(mcp)`
  invoked from `tools/__init__.py::register_all_tools` —
  `tools/r2_sessions.py` follows.
- Process-group cleanup: every subprocess that may need killing
  later spawns with `start_new_session=True`, stores `pgid =
  os.getpgid(proc.pid)`, kills via `killpg(pgid, SIGKILL)`,
  cleans up via `asyncio.shield(proc.wait())` to survive
  cancellation. Phase 6 D-17 is the contract; Phase 8 reuses it
  in D-16 / D-21.

### Integration points
- `app.py::lifespan` gains exactly ONE new `async with` block per
  branch (with-backend and no-backend). Other lifespan ordering
  (Phase 7 collision check after `PinnedBackend.__aenter__`)
  unchanged.
- `tools/__init__.py::register_all_tools` gains exactly ONE new
  `from . import r2_sessions; r2_sessions.register(mcp)` line.
- `session_state.py` gains exactly ONE new module-level slot
  (`SESSION_REGISTRY`).
- `artifacts_io.py::EXPANDED_CASE_SUBDIRS` grows by exactly ONE
  string (`"r2-sessions"`).
- No change to `runner.py` semantically (Phase 8 consumes Phase
  6's existing surface). Phase 8 may extend `runner.py` to export
  the ANSI-strip / truncate helpers if they are currently
  private — that is a Claude's Discretion call by the planner.
- No change to `subprocess_runner.py`, `uploads.py`, `auth.py`,
  `backend/*`, `tools/shell.py`, `tools/re_static.py`,
  `tools/re_artifacts.py`, `tools/collision_check.py`,
  `tools/resources.py`, `tools/case_dirs.py`, `tools/samples.py`,
  `tools/artifacts.py`, `tools/workflows.py`,
  `tools/backend_passthrough.py`, `tools/cases.py`,
  `tools/disasm.py`, or `cli.py`.

</code_context>

<specifics>
## Specific Ideas

- User mandate at discuss-phase (consistent with Phases 6 and 7):
  "Choose the most robust and appropriate option for all questions."
  All D-01..D-29 decisions above are the most-robust default under
  that mandate; the planner/executor may adjust within the
  constraints listed under "Claude's Discretion" but not the locked
  decisions.
- Defense-in-depth carried forward: raw asyncio + sentinel over
  r2pipe-in-thread (D-01) for cleaner cancellation/timeout;
  full-string regex over literal-first-char (D-08) for actual
  shell-escape refusal under r2's `;`/`|` compound syntax;
  per-session randomized sentinel suffix (D-04) over a global
  static one; per-command log + session transcript (D-12, D-13)
  rather than choosing one; mandatory r2 lockdown applied BEFORE
  user `init_commands` (D-03) and validated for dangerous commands
  before spawn (D-19 step 3).
- The 30 min idle / 8 session cap defaults (D-14) come from
  research consensus (Pitfall 5 + SUMMARY). The 30 s per-command
  timeout default (D-14, `MCP_GATEWAY_R2_CMD_TIMEOUT_S`) is
  research-recommended for r2 (some r2 commands like `aaaa` on a
  large binary legitimately take longer; per-call override is
  available so analysts of large samples bump it).
- The 15 s `MCP_GATEWAY_SESSION_OPEN_TIMEOUT_S` default (D-14) is
  generous for r2 startup + four lockdown commands; user-supplied
  `init_commands=["aaa"]` on a large binary will typically need a
  higher per-call override (e.g., `open_timeout=120.0`). The
  default protects the gateway from hung opens on
  startup-misconfigured r2 binaries; analyst-driven heavy init is
  expected to pass a larger timeout.
- The per-command tool-log naming (D-12) is intentionally identical
  to every other Phase 6/7 wrapper. An agent doing
  `get_tool_log(case_dir, log_name, …)` does not need to know
  whether the log came from `run_shell`, `run_file`, or `r2_cmd`.
- The session-wide transcript (D-13) is intentionally flat
  (`r2-sessions/<session_id>-transcript.log`, not
  `r2-sessions/<session_id>/transcript.log`) so Phase 7 D-26's
  depth-≤-2 resource walker exposes it without modification. The
  alternative (deeper nesting) would have required either
  modifying the resource walker (out-of-scope refactor) or
  hiding the transcript from MCP Resources (worse for analyst
  workflow).
- The `format="json"` auto-suffix + best-effort `parsed_json` field
  (D-10, D-11) keeps the wrapper friction-free: an agent writing
  `r2_cmd(sid, "pdf", format="json")` gets the parsed result
  without needing to remember r2's `j` convention, and an agent
  passing a non-JSON command sees `parsed_json: None` +
  `parse_error: "..."` rather than an exception. The 12-key base
  shape (Phase 6 D-03) is always uniform regardless of `format`.
- `fd_count` in `list_sessions` (D-22) is the operational
  observability hook Pitfall 5 calls out specifically. Phase 8's
  reaper kills stale sessions, but `fd_count > 50` for a
  short-running session is a smoke signal for "this session is
  about to OOM the gateway" or "an r2 plugin is leaking handles."
- The cap-reject behavior (D-18) over LRU-evict is research
  consensus; LRU-evict would silently break the evicted client's
  analysis state, which is hostile to multi-client (same bearer
  token) usage. The error dict tells the caller "here are the
  existing sessions; close one and retry."
- The Phase 11 refactor path (eventual `sessions/` package
  splitting r2 and gdb into peer modules) is acknowledged but
  deliberately not pre-built. Premature packaging would create
  empty-shaped speculation; the rename-only refactor in Phase 11
  costs minutes, the pre-built abstraction costs decision-bound
  flexibility.

</specifics>

<deferred>
## Deferred Ideas

- **Per-`Mcp-Session-Id` keying of r2 sessions (`GW-V2-03`)** —
  explicitly out-of-scope per `REQUIREMENTS.md` §"Out of Scope
  (v1.1)" and §"Future Requirements". Phase 8 documents the
  shared-across-bearer-token-clients limitation loudly (D-23) but
  does not implement the refactor. v1.2 territory.
- **`sessions/` subpackage layout (r2.py + gdb.py + registry.py +
  reaper.py)** — Phase 11 owns the rename-only refactor when gdb
  sessions land. Phase 8 ships the flat `sessions.py` (D-05) to
  avoid premature packaging.
- **`format="r2"` (raw binary newline-framed) mode for `r2_cmd`** —
  rejected for Phase 8; `text` + `json` covers the analyst
  workflow. v1.2+ can revisit if a real need surfaces.
- **r2 plugin support in sessions (e.g., `r2ghidra`,
  `r2dec-js`)** — the r2 binary in the Kali image carries default
  plugins; loading custom plugins from agent-supplied paths is
  out-of-scope (would expand the attack surface and conflict with
  `cfg.user=mare` posture). Not added.
- **LRU-evict instead of cap-reject** — rejected (D-18) for the
  silent-state-loss reason. v1.2 may revisit with per-session
  keying once cross-client identity is real.
- **Session-restart-recovery (re-attach to a still-running r2
  after gateway restart)** — out-of-scope; in-memory registry by
  design (mirrors the Phase 9 background-jobs decision). Already
  deferred in `REQUIREMENTS.md` §"Future Requirements".
- **Convergence of `subprocess_runner.run_script` and
  `ReToolRunner` and Phase 8's r2-driver into one runner** —
  v1.2+ deferred; three runners coexist by design in v1.1.
- **r2-session-scoped UID drop (e.g., r2 running as
  `mare-shell` instead of `agent`)** — defense-in-depth bonus but
  significant complexity (r2 needs `agent`-readable access to
  `samples`, `tool-logs`, transcript). Phase 7's `mare-shell` is
  for `run_shell` only; r2 sessions stay as `agent`. v1.2 might
  reconsider if a credible threat model emerges.
- **MCP progress reporting for long r2 commands (e.g., `aaa` on a
  large binary)** — Phase 9's `Context.report_progress` is the
  framework, but r2 doesn't emit progress signals. Until r2
  exposes progress, the only options are (a) per-call timeout +
  retry pattern (current Phase 8 design), or (b) Phase 9 jobs +
  poll. Composite "long-r2-as-job" workflow is an orchestrator
  pattern, not a Phase 8 tool surface.
- **Multi-line / heredoc commands via `r2_cmd`** — research mentions
  it, but the sentinel-marker protocol works newline-by-newline;
  multi-line commands can be split client-side or written to a
  temp file and `r2_cmd(sid, ". /tmp/script.r2")` invoked. Adding
  multi-line transport over MCP is yagni.
- **Auto-checkpointing of r2 project state (`Ps`/`Po` per N
  commands)** — useful for "restore analysis if session dies"
  workflows but conflicts with the cap-reject + reaper model. The
  transcript (D-13) is the Phase 8 audit/replay artifact;
  checkpointing is v1.2+ territory.

</deferred>

---

*Phase: 08-session-scoped-r2*
*Context gathered: 2026-05-18*
