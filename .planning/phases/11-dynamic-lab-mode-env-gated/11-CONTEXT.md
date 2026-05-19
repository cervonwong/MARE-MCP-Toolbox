# Phase 11: Dynamic Lab Mode (env-gated) - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a first-class but env-gated dynamic-analysis surface to the gateway:
seven new tools (`run_strace`, `run_ltrace`, `run_qemu_user`,
`open_gdb_session`, `gdb_exec`, `close_gdb_session`,
`get_dynamic_capabilities`) registered if and only if
`MCP_GATEWAY_DYNAMIC_TOOLS=1` at startup. Default-off so the standard
container shape is byte-identical to Phase 10. Operator opt-in via
`./run_docker.sh --dynamic` (compositional with `--remote`). Three long-
running tools (strace, ltrace, qemu_user) dispatch through the Phase 9
JOBS system; gdb runs as a persistent session reusing the Phase 8
SessionRegistry plumbing (formally promoted to a `sessions/` package
here per Phase 8 D-05's deferred refactor). No-net by default via
per-call `unshare --net --ipc --uts -- <argv>`. Ptrace / binfmt / netns
capabilities probed at gateway startup and exposed both via
`get_dynamic_capabilities()` and as structured per-call error dicts when
a tool's prerequisite is missing.

Scope:

- New module files:
  - `mcp-gateway/src/mcp_gateway/sessions/` — promoted from the
    monolithic `sessions.py`. Package layout:
    - `sessions/__init__.py` — public re-exports preserving every
      Phase 8 symbol (`SessionRegistry`, `R2Session`,
      `_DANGEROUS_R2_CMD_RE`, env-var module constants, helpers) so
      Phase 8/9 callers and tests do NOT need import-path edits.
    - `sessions/_base.py` — `SessionRegistry` (kind-agnostic),
      `BaseSession` dataclass with the shared fields
      (`session_id`, `case_dir`, `pgid`, `lock`, `opened_at`,
      `last_used_at`, `command_count`, `closed`, `close_reason`,
      `kind: Literal["r2","gdb"]`), `_env_int` / `_env_float`
      helpers, sentinel helpers (`make_sentinel`,
      `read_until_sentinel`), ANSI-strip / UTF-8-safe truncate
      helpers (hoisted from Phase 8 `sessions.py` so Phase 11's
      gdb driver reuses them).
    - `sessions/r2.py` — `R2Session` (Phase 8 D-15 shape), r2-specific
      driver (`open_r2`, `r2_cmd_impl`, `close_r2`), the dangerous-cmd
      regex, the four-line lockdown init (`scr.interactive=false`,
      `scr.color=0`, `scr.html=0`, `cfg.user=mare`), the `?e <sentinel>`
      per-command framing. Bit-for-bit move of the existing r2 logic.
    - `sessions/gdb.py` — NEW. `GdbSession` (BaseSession subclass),
      gdb-MI3 driver, MI3 sentinel framing
      (`-data-evaluate-expression "__MARE_END_<8hex>__"` post-command),
      hard-fail attempt to `attach`/`target remote`, the MI-prefix
      allowlist regex, gdb-mandatory init (`set confirm off`,
      `set pagination off`, `set print pretty off`, `set verbose off`,
      `set debuginfod enabled off`, `set auto-solib-add off`,
      `set logging off`, `set follow-fork-mode parent` default plus
      operator-overridable, `set detach-on-fork on`).
  - `mcp-gateway/src/mcp_gateway/dynamic.py` — NEW primitive layer.
    Public surface:
    - `DYNAMIC_TOOLS_ENABLED: bool` (re-reads `MCP_GATEWAY_DYNAMIC_TOOLS == "1"` once at import for cross-module access; the gate decision itself is in `tools/__init__.py`).
    - Capability probe primitives: `probe_ptrace_scope()`,
      `probe_ptrace_traceme()`, `probe_binfmt_misc()`,
      `probe_qemu_architectures()`, `probe_netns_feasible()`. Each
      returns a typed dict / value, never raises.
    - `DynamicCapabilities` dataclass + module-level
      `CAPABILITIES: DynamicCapabilities | None` slot, populated
      ONCE at lifespan startup (D-DYN-CAP-INIT) for fast tool-call
      use.
    - Argv-profile registries: `STRACE_PROFILES`, `LTRACE_PROFILES`,
      `QEMU_USER_PROFILES` — frozen dicts mapping profile-name →
      argv fragment.
    - `EXTRA_ARGS_ALLOWLIST_RE` — regex matched against each
      `extra_args` entry (D-DYN-PROF-ALLOWLIST).
    - `wrap_netns(argv: list[str]) -> list[str]` — prepends
      `["unshare", "--net", "--ipc", "--uts", "--"]` (per-call
      isolation; D-DYN-NET-01).
    - `build_strace_argv(case_dir, sample_path, profile, extra_args, output_path) -> list[str]`,
      `build_ltrace_argv(...)`, `build_qemu_user_argv(...)` — pure
      argv builders (matches Phase 10 D-15 pattern: no side effects).
    - `JobToolSpec` registrations for `strace`, `ltrace`,
      `qemu_user` registered into `mcp_gateway.jobs.JOB_TOOL_REGISTRY`
      at MODULE IMPORT (matches Phase 9 D-04 / Phase 10 D-01
      ship-with pattern). Because `dynamic.py` is only imported by
      `tools/dynamic.py`, which is only imported by `tools/__init__.py`
      when `MCP_GATEWAY_DYNAMIC_TOOLS=1`, the specs are only
      registered when dynamic mode is on. ZERO leak when off.
    - `reap_followfork_strays(runner_pid: int, pgid: int) -> int` —
      scans `/proc/<runner_pid>/task/*/children` after killpg, SIGKILLs
      any escaped grandchildren via `setsid`, returns count killed
      (Pitfall 4).
  - `mcp-gateway/src/mcp_gateway/tools/dynamic.py` — NEW MCP surface.
    Seven `@mcp.tool()` handlers (`run_strace`, `run_ltrace`,
    `run_qemu_user`, `open_gdb_session`, `gdb_exec`,
    `close_gdb_session`, `get_dynamic_capabilities`). Mirrors the
    `tools/r2_sessions.py` / `tools/jobs.py` / `tools/extract.py`
    register-pattern. The module is only imported by
    `tools/__init__.py::register_all_tools` when
    `MCP_GATEWAY_DYNAMIC_TOOLS == "1"` at startup.
- Extensions to existing modules:
  - `mcp-gateway/src/mcp_gateway/sessions.py` — DELETED (replaced
    by `sessions/` package). The package's `__init__.py` preserves
    every Phase 8 public name; no Phase 8/9/10 import sites change.
  - `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — import-only
    edit: change `from mcp_gateway import sessions` (or
    `from mcp_gateway.sessions import ...`) to whatever the new
    package re-exports name-for-name. Functional behavior unchanged.
  - `mcp-gateway/src/mcp_gateway/app.py::lifespan` — no structural
    change. The existing SessionRegistry block from Phase 8 D-24 /
    Phase 9 D-25 now manages BOTH r2 and gdb session kinds; the
    registry is kind-aware.
  - `mcp-gateway/src/mcp_gateway/app.py::lifespan` — ADD a one-time
    capability-probe call after register_all_tools returns,
    BEFORE entering `PinnedBackend`, in both branches:
    `dynamic.CAPABILITIES = dynamic.probe_all()`. Probe never raises;
    fills in best-effort fields. Logs a WARN line per missing
    capability so operators see "[gateway] WARN: ptrace_scope=2
    detected — strace/ltrace/gdb will return ERROR until host sets
    yama.ptrace_scope=0" at startup (D-DYN-PROBE-LOG).
  - `mcp-gateway/src/mcp_gateway/tools/__init__.py::register_all_tools`
    — env-gated conditional import + register for `tools/dynamic.py`
    (the gate). Tool count: 54 static + 7 conditional = 61 when on,
    54 when off. The static `EXPECTED_TOOLS` set in
    `test_tool_list.py` stays at 54; a separate parametrized test
    asserts 61 when the env var is set (D-DYN-TEST-COUNT).
  - `mcp-gateway/src/mcp_gateway/artifacts_io.py::EXPANDED_CASE_SUBDIRS`
    — grows by ZERO entries; `"dynamic"` and `"qemu"` already cataloged
    by Phase 6 D-16. Lazy-created on first dynamic-tool write.
  - `run_docker.sh` — add `--dynamic` flag that exports
    `MCP_GATEWAY_DYNAMIC_TOOLS=1` (compositional with `--remote`).
    Hard-error if `--dynamic` is passed without `--remote` (dynamic
    mode is meaningless inside the local-bash agent mode that doesn't
    start the gateway). Also rejects `--dynamic` together with
    `--print-config` (no harm but confusing). Add to usage banner.
  - `Dockerfile` — verify `util-linux` (for `unshare`) and
    `qemu-user-static` (or equivalent multi-arch package) are
    present in the base apt set. Both are in the Kali base, but
    Phase 11's first plan checks and pins explicitly via
    `apt-get install -y --no-install-recommends util-linux qemu-user-static`.
- No changes required to: `runner.py`, `jobs.py` (specs are added
  externally via `register_job_tool(spec)` from `dynamic.py`),
  `tools/collision_check.py` (depth-2 collision check still applies),
  `tools/resources.py` (depth-2 walker exposes `dynamic/<file>` and
  `qemu/<file>` automatically), `extraction.py`, `tools/extract.py`,
  `tools/shell.py` (mare-shell UID is for `run_shell` only; dynamic
  tools run as `agent` to keep `SYS_PTRACE` available — the netns
  unshare provides the network isolation, not UID drop), `auth.py`,
  `uploads.py`, `subprocess_runner.py`, `backend/*`, `cli.py`.

Explicitly NOT in this phase (deferred to other phases / out of scope):

- **`allow_network=True` opt-in per-call.** REQUIREMENTS.md §"Out of
  Scope (v1.1)" explicitly defers this. Phase 11 ships no-net only.
  v1.2 may add INetSim/FakeDNS + per-call opt-in.
- **Persistent named netns at gateway start** (rejected by
  D-DYN-NET-01 — per-call unshare is the chosen mechanism).
- **Sandboxed-network dynamic mode** (INetSim/FakeDNS/honeynet) —
  REQUIREMENTS Out of Scope.
- **Coverage-guided dynamic / fuzzing hooks** (afl, libFuzzer) —
  REQUIREMENTS Out of Scope.
- **Memory snapshot tooling** (Volatility) — REQUIREMENTS Out of
  Scope.
- **Full-VM / kernel-mode dynamic** — REQUIREMENTS Out of Scope.
- **CLI-mode gdb access** (raw `gdb` without `--interpreter=mi3`) —
  prompt-parsing ambiguity makes session framing unreliable (Pitfall
  6); MI3 is the only supported interface.
- **`-interpreter-exec console`** and any other gdb escape that
  runs Python or shell — explicitly blocked by the MI allowlist
  (D-DYN-GDB-ALLOWLIST), DYN-05.
- **Auto-registration of binfmt_misc handlers from inside the
  container** — requires `--privileged`, which is not the default
  posture. Phase 11 probes binfmt and reports; setup is host-side
  (documented in the v1.1 docs / Phase 12 skill).
- **Sync mode for strace/ltrace/qemu** — DYN-07 says long-running
  dynamic tools dispatch through JOBS. Phase 11 enforces this:
  all three are job-only (no `wait=True` shortcut). The orchestrator
  can poll fast for short traces. Robust over ergonomic shortcut.
- **Per-`Mcp-Session-Id` keying of gdb sessions** — Phase 8 SESS-05
  documented limitation carries forward to gdb. Disclaimer copied
  verbatim into the four gdb-session tool docstrings.
- **Composite `investigate_dynamic` / `dynamic_triage` MCP tools** —
  PROJECT.md Out of Scope. Orchestrator skill composes primitives.
- **Persistent capability re-probing on a timer** — capability
  state is host-namespace-controlled and effectively static during
  a container's lifetime; one probe at startup is sufficient. A
  manual `get_dynamic_capabilities(refresh=True)` re-probe is
  supported for operator troubleshooting (D-DYN-CAP-REFRESH).
- **`job_specs/` package refactor** — Phase 9 D-04 / Phase 10 D-01
  suggested it once spec count crosses 5. Phase 11 brings the count
  to 6 (capa, unblob, binwalk_extract, strace, ltrace, qemu_user) but
  the existing pattern (each owner module registers its own specs at
  import time) works fine; mirroring it (`dynamic.py` registers its
  3) keeps the env-gate clean (dynamic specs disappear from
  `JOB_TOOL_REGISTRY` entirely when dynamic mode is off, instead of
  living in a centralized package that always imports them). Refactor
  deferred to v1.2.
- **CURRENT_STATE.json dynamic-mode marker writing** — DYN-02 says
  the mode "is surfaced in CURRENT_STATE.json"; that file is the
  orchestrator skill's per-case status file (Phase 12 consumes
  `get_dynamic_capabilities()` and writes into each case's
  CURRENT_STATE.json). Phase 11 only exposes
  `get_dynamic_capabilities()` as the source of truth; Phase 12 owns
  the write. Phase 11 does NOT touch `workspace/.claude/skills/` or
  `workspace/.codex/skills/`.

</domain>

<decisions>
## Implementation Decisions

### Module architecture (Area 1: gdb session placement)

- **D-01:** `sessions.py` is refactored into a `sessions/` package
  (Phase 8 D-05 deferred this to Phase 11 explicitly). Package
  layout:

  ```
  mcp-gateway/src/mcp_gateway/sessions/
  ├── __init__.py    # re-exports every Phase 8 public symbol
  ├── _base.py       # SessionRegistry, BaseSession, env-vars, shared helpers
  ├── r2.py          # R2Session, r2 driver (moved from sessions.py)
  └── gdb.py         # GdbSession, gdb-MI3 driver (NEW)
  ```

  `sessions/__init__.py` re-exports `SessionRegistry`, `R2Session`,
  `_DANGEROUS_R2_CMD_RE`, `MAX_SESSIONS`, `SESSION_IDLE_S`,
  `REAPER_INTERVAL_S`, `R2_CMD_TIMEOUT_S`, `SESSION_OPEN_TIMEOUT_S`
  (every Phase 8 D-14 env-var module constant), plus the new
  `GdbSession`, `GDB_CMD_TIMEOUT_S`, `GDB_OPEN_TIMEOUT_S`. Phase 8's
  test file `test_sessions.py` import paths stay valid; Phase 9
  `jobs.py`'s `from mcp_gateway.sessions import ...` stays valid;
  `tools/r2_sessions.py` gets a one-line import update from
  `mcp_gateway import sessions` to whatever idiom matches the
  package (likely unchanged because re-export is via `__init__.py`).

  *Rationale:* Phase 8 D-05 said explicitly: "the subpackage layout
  is appropriate when Phase 11 adds gdb, NOT before. Premature
  packaging would create empty `gdb.py`-shaped speculation in the
  codebase; Phase 11 owns the rename-only refactor." Phase 11 now
  has the gdb driver to fill the speculation. One reaper, one cap,
  one idle counter across both kinds. Most robust.

- **D-02:** `SessionRegistry` becomes kind-aware. Internal state:

  ```python
  class SessionRegistry:
      _sessions: dict[str, BaseSession]   # session_id -> session
      # cap and idle apply uniformly across r2 + gdb (shared pool)
      _max_sessions: int                  # default 8 (unchanged from Phase 8)
      _idle_s: float                      # default 1800 (unchanged)
      _reaper_interval_s: float           # default 60 (unchanged)
  ```

  `open()` gains a `kind: Literal["r2","gdb"]` kwarg; dispatches to
  `sessions.r2._open_r2(...)` or `sessions.gdb._open_gdb(...)`. The
  cap of 8 is the COMBINED count (r2 + gdb). The reaper iterates
  every kind uniformly. `list_sessions` returns entries with a
  `kind` field so callers can filter.

  *Rationale:* Most robust default. A separate gdb-only cap would
  add config surface (`MCP_GATEWAY_MAX_GDB_SESSIONS`) for negligible
  gain — operators care that the gateway doesn't OOM, not whether
  it's r2 or gdb that pushed it. The shared cap also discourages
  forgetting to close a gdb session before opening an r2 one. Phase
  8 SUMMARY consensus on "cap 8 sessions" was kind-agnostic anyway.

- **D-03:** A new `BaseSession` dataclass in `sessions/_base.py`
  holds the Phase 8 D-15 fields that are kind-agnostic
  (`session_id`, `case_dir`, `pgid`, `lock`, `opened_at`,
  `opened_iso`, `last_used_at`, `command_count`, `closed`,
  `close_reason`, `transcript_path`, `proc`, `sentinel`). `R2Session`
  and `GdbSession` are dataclass subclasses adding kind-specific
  fields:

  ```python
  @dataclasses.dataclass
  class R2Session(BaseSession):
      kind: Literal["r2"] = "r2"
      sample_sha256: str = ""
      sample_path: pathlib.Path = ...
      # (r2-specific: no extras beyond Phase 8 D-15)

  @dataclasses.dataclass
  class GdbSession(BaseSession):
      kind: Literal["gdb"] = "gdb"
      sample_sha256: str = ""
      sample_path: pathlib.Path = ...
      gdb_version: str = ""          # parsed from -gdb-version on open
      mi_version: Literal["mi3"] = "mi3"
      follow_fork_mode: Literal["parent","child"] = "parent"
      netns_wrapped: bool = True     # always True in v1.1 (no-net default)
  ```

  *Rationale:* Single source of truth for session metadata; gdb-only
  fields are namespaced on the subclass. Mirrors how the Phase 9
  `JobStatus` enum is shared across all job tools. Future v1.2 kinds
  (e.g., a `FridaSession`) would add another subclass without
  touching `BaseSession`.

### gdb MI3 driver and command allowlist (Area 1 continued)

- **D-04:** gdb is launched with this exact argv (wrapped per
  D-DYN-NET-01):

  ```python
  argv = [
      "unshare", "--net", "--ipc", "--uts", "--",
      "gdb",
      "--interpreter=mi3",     # MI3 framing — only supported interface
      "--quiet",               # suppress banner
      "--nx",                  # ignore ~/.gdbinit (no user-state leak)
      "--nh",                  # also ignore ~/.config/gdb/* (gdb 9+)
      str(sample_path),        # the inferior (NOT attached yet — analyst issues -exec-run)
  ]
  ```

  `cwd=str(resolved_case_dir)`, `start_new_session=True`,
  `stdin/stdout/stderr = asyncio.subprocess.PIPE`. The sample is
  loaded but NOT executed at session open — analyst issues
  `-exec-run` via `gdb_exec` to start the inferior. This is the
  safest open posture (no sample code runs until the analyst
  explicitly asks).

- **D-05:** Mandatory gdb init commands sent BEFORE any user
  init_commands and BEFORE the session is registered, in this
  order (using `-interpreter-exec console` is BLOCKED, so the
  init goes via direct MI commands or via the gdb startup-set-options
  which take effect before the prompt):

  Send as a single newline-joined MI batch via stdin:

  ```
  -gdb-set confirm off
  -gdb-set pagination off
  -gdb-set print pretty off
  -gdb-set verbose off
  -gdb-set debuginfod enabled off
  -gdb-set auto-solib-add off
  -gdb-set logging file /dev/null
  -gdb-set follow-fork-mode parent
  -gdb-set detach-on-fork on
  -gdb-set startup-with-shell off
  -gdb-version
  ```

  After each, read until the MI sentinel (`^done` or `^error` record
  followed by the per-session sentinel line). The `-gdb-version`
  line populates `GdbSession.gdb_version`. If any of the lockdown
  commands returns `^error`, the open is aborted, the gdb process
  is `killpg`-ed, and `open_gdb_session` returns
  `{error: "gdb init failed", failed_cmd: <which>, gdb_stderr_head: <...>}`.

  *Rationale:* `-gdb-set` is the MI form of `set`; these commands
  go through MI's structured framing rather than CLI. `startup-with-shell off`
  disables gdb's auto-shell-fork on `-exec-run` (Pitfall 9
  defense-in-depth — no shell process in the pgroup means no shell
  escape vector even before the netns kicks in).

- **D-06:** gdb sentinel-marker framing (matches Phase 8 D-04
  posture, MI3-adapted):

  ```python
  sentinel_suffix = secrets.token_hex(4)
  sentinel_str = f"__MARE_END_{sentinel_suffix}__"
  ```

  Per-command flow:

  ```python
  # Send user command + a benign MI marker echo
  proc.stdin.write(cmd.encode() + b"\n")
  # The marker uses -data-evaluate-expression which CAN be in the
  # allowlist for inputs but here we issue it as gateway-side framing
  # — it is NEVER attributed to user-command output:
  proc.stdin.write(f"-data-evaluate-expression \"\\\"{sentinel_str}\\\"\"\n".encode())
  await proc.stdin.drain()

  # Read until the line equal to:
  #   ^done,value="\"__MARE_END_<8hex>__\""
  # capture everything before that as the command's output.
  ```

  Alternative considered and rejected: use the `(gdb) \n` MI
  prompt as the framing terminator. Rejected because MI3 emits
  `(gdb) \n` after every record group, including async records that
  fire during long-running commands — naive readuntil would terminate
  too early. Per-command sentinel via `-data-evaluate-expression` is
  unambiguous and only emits once per command (after gdb finishes
  the previous command, before the next prompt). Per-session random
  suffix prevents collision with user-supplied string literals.

- **D-07:** gdb MI allowlist — STRICT PREFIX ALLOWLIST (not
  deny-list). Wrapper-level full-string scan against a compiled
  regex BEFORE any byte is written to gdb's stdin. Approved MI
  prefixes:

  ```python
  _ALLOWED_MI_PREFIXES = (
      # State inspection
      "-info-",
      "-data-evaluate-expression",
      "-data-list-register-names",
      "-data-list-register-values",
      "-data-read-memory",
      "-data-disassemble",
      # Stack
      "-stack-list-frames",
      "-stack-list-arguments",
      "-stack-list-locals",
      "-stack-list-variables",
      "-stack-info-depth",
      "-stack-info-frame",
      "-stack-select-frame",
      # Execution control
      "-exec-run",
      "-exec-continue",
      "-exec-next",
      "-exec-step",
      "-exec-finish",
      "-exec-until",
      "-exec-interrupt",
      "-exec-return",
      # Breakpoints
      "-break-insert",
      "-break-delete",
      "-break-list",
      "-break-disable",
      "-break-enable",
      "-break-info",
      "-break-condition",
      # Threads
      "-thread-list-ids",
      "-thread-info",
      "-thread-select",
      # Symbols and files (read-only)
      "-symbol-info-functions",
      "-symbol-info-variables",
      "-symbol-info-types",
      "-symbol-info-modules",
      "-file-list-exec-source-files",
      "-file-list-exec-source-file",
      # Variable objects (gdb's structured eval)
      "-var-create",
      "-var-delete",
      "-var-evaluate-expression",
      "-var-list-children",
      "-var-info-",
      "-var-update",
      # Gateway-side framing (gdb_exec wrapper itself uses these)
      "-gdb-version",
  )
  ```

  HARD-BLOCK (regex denylist applied AFTER allowlist passes — belt
  and braces in case an allowlist prefix is somehow attached to a
  dangerous suffix):

  ```python
  _DANGEROUS_GDB_RE = re.compile(
      r"(?:^|;|\n|\s)\s*("
      r"-interpreter-exec\s+console"   # the Python/CLI escape
      r"|python(?:\s|$)"               # raw CLI python
      r"|pi(?:\s|$)"                   # CLI python alias
      r"|source(?:\s|$)"               # arbitrary file sourcing
      r"|shell(?:\s|$)"                # CLI shell
      r"|!"                            # ! shellout
      r"|-gdb-set\s+logging\s+(?:on|file)"   # arbitrary file write
      r"|-target-(?:select|attach)"          # remote/pid attach
      r"|attach(?:\s|$)"                     # CLI attach
      r"|add-symbol-file"                    # filesystem load
      r"|generate-core-file"                 # core dump anywhere
      r"|dump\s"                             # dump <addr> to file
      r"|set\s+inferior-tty"                 # tty hijack
      r")"
  )
  ```

  Each user command is FIRST checked against the prefix allowlist
  (must match one), THEN scanned for the deny regex (must NOT match).
  Both failures raise `ValueError` with the rejected token name and
  a hint pointing to the allowlist.

  *Rationale:* DYN-05 says "restricted to an allowlist of MI prefixes
  to prevent `python <code>` sandbox escape." Strict allowlist is
  the only posture that prevents future gdb additions from silently
  expanding the escape surface. The deny-regex is defense-in-depth
  for the few weird edge cases where MI commands compose (e.g., a
  `-interpreter-exec mi3 "..."` form). Both layers must pass.

- **D-08:** `gdb_exec` result dict layers on Phase 6 D-03's 12-key
  shape (mirrors Phase 8 D-11):

  ```python
  {
      # 12 base keys per Phase 6 D-03
      "exit_code": int,             # 0 if cmd completed, -9 if session killed
      "timed_out": bool,
      "duration_s": float,
      "stdout_head": str,           # ANSI-stripped MI output, truncated
      "stdout_truncated": bool,
      "stdout_bytes_total": int,
      "stderr_head": str,           # gdb stderr (rare — gdb writes most output to stdout)
      "stderr_truncated": bool,
      "stderr_bytes_total": int,
      "log_path": str,              # case-rel: tool-logs/<ts>-gdb_cmd-<rand4>.txt
      "argv": list[str],            # ["gdb-session-cmd", session_id_prefix, cmd_truncated]
      "slug": str,                  # "gdb_cmd"
      # gdb-session extensions (mirrors Phase 8 D-11 r2 additions)
      "session_id": str,
      "session_invalidated": bool,
      "transcript_path": str,       # case-rel: dynamic/<session_id>-gdb-transcript.log
      "mi_result_class": str,       # "done" | "error" | "running" | "connected" | "exit"
      "mi_records": list[dict],     # parsed MI record stream (best-effort)
      "parse_error": str | None,    # if MI parsing fell back to raw text
  }
  ```

  `mi_records` is a best-effort parse of MI's `^done,key=value,...`
  format into Python dicts. Parse failure does NOT raise; instead
  `mi_records = []`, `parse_error = "..."`, `stdout_head` keeps the
  raw text so the caller can still inspect (matches Phase 8 D-10
  best-effort JSON parsing).

- **D-09:** `gdb_exec` per-command timeout: env-var
  `MCP_GATEWAY_GDB_CMD_TIMEOUT_S`, default `60.0` (longer than r2's
  30 s because gdb commands routinely include `-exec-run` of the
  inferior, which can be slow on the first invocation). Hitting the
  timeout kills the entire gdb session (gdb is unrecoverable after
  a hung command — same posture as Phase 8 D-14 r2), returns
  `session_invalidated: true`. Per-call kwarg override allowed.

- **D-10:** `open_gdb_session` per-call timeout: env-var
  `MCP_GATEWAY_GDB_OPEN_TIMEOUT_S`, default `30.0` (gdb spawn +
  9-line MI init batch + 1 `-gdb-version` readback). Per-call
  override allowed for very large binaries where the initial symbol
  table load is slow.

### Network isolation (Area 2)

- **D-DYN-NET-01:** Per-call `unshare --net --ipc --uts -- <argv>`
  argv-prefix wrapping for EVERY dynamic-mode subprocess invocation.
  Applied uniformly by `dynamic.wrap_netns(argv)`:

  ```python
  def wrap_netns(argv: list[str]) -> list[str]:
      return ["unshare", "--net", "--ipc", "--uts", "--", *argv]
  ```

  Used by every argv builder (`build_strace_argv`,
  `build_ltrace_argv`, `build_qemu_user_argv`, and `gdb`'s spawn
  in `sessions/gdb.py`). The gateway process is NOT unshared; only
  the spawned dynamic subprocess.

  *Rationale:* Simplest robust mechanism. Pitfall 9 calls this out
  explicitly: "per-sample-execution network namespace via
  `unshare --net` for each dynamic invocation. The unshared
  namespace has no interfaces by default, no loopback unless
  explicitly created — perfect for no-net." Persistent named netns
  alternative (`ip netns add mare-dynamic; nsenter ...`) is
  feature-rich but adds gateway-start coordination and a new
  failure mode (netns missing at start → every dynamic call fails).
  Per-call is what FEATURES.md, PITFALLS.md, and ARCHITECTURE.md all
  converge on.

- **D-DYN-NET-02:** No loopback inside the netns. The kernel
  returns `ENETUNREACH` on `socket(...)+connect` cleanly. Tests
  assert this (a fixture sample that does `gethostbyname("example.com")`
  under `run_strace` must show the failed syscall, NOT a real
  resolution).

  *Rationale:* Pitfall 9: "the unshared namespace has no interfaces
  by default, no loopback unless explicitly created — perfect for
  no-net." Loopback inside the netns would let a sample talk to
  itself via TCP loopback (rare but possible C2 pattern for samples
  expecting a local proxy). Reject for v1.1.

- **D-DYN-NET-03:** Netns wrap is mandatory (no per-call opt-out
  in v1.1). The `allow_network=True` opt-in is explicit v1.2
  territory per REQUIREMENTS Out of Scope. `wrap_netns` always runs
  for every dynamic subprocess. Tests assert that no dynamic-tool
  spawn skips the wrap (grep-the-source test against
  `dynamic.py::build_*_argv` ensuring every return-statement starts
  with `["unshare", ...]` or a call to `wrap_netns(...)`).

  *Rationale:* DYN-03 says "default no-net via per-call
  `unshare --net`." Mandatory matches the requirement; opt-out
  would create a "forgot the flag" foot-gun.

### argv profile design (Area 3)

- **D-DYN-PROF-01:** Hybrid model — named profiles for the common
  cases + escape-hatch `extra_args: list[str] | None = None`
  validated against an allowlist regex. Schema for each tool:

  **`run_strace(case_dir, sample, profile, extra_args=None, run_argv=None) -> dict`**

  Profiles (each maps to an argv fragment, NOT including the sample
  path or output redirection — those are filled in by the builder):

  ```python
  STRACE_PROFILES: Mapping[str, tuple[str, ...]] = {
      "file_io":           ("-f", "-e", "trace=file,desc"),
      "network":           ("-f", "-e", "trace=network"),
      "process":           ("-f", "-e", "trace=process"),
      "signals":           ("-f", "-e", "trace=signal"),
      "file_network_process": ("-f", "-e", "trace=file,desc,network,process"),
      "all":               ("-f", "-e", "trace=all"),  # very noisy
      "summary":           ("-f", "-c"),               # syscall counts only
  }
  ```

  `-f` (follow-fork) is in every profile. `-o <case_dir>/dynamic/<ts>-strace-<rand4>.txt`
  is appended by the builder (the structured output path; head/tail
  flow via the JobToolSpec's tool-log capture in addition).

  **`run_ltrace(case_dir, sample, profile, extra_args=None, run_argv=None) -> dict`**

  ```python
  LTRACE_PROFILES: Mapping[str, tuple[str, ...]] = {
      "library_calls":         ("-f",),                   # default
      "system_only":           ("-f", "-S"),
      "library_and_system":    ("-f", "-S", "-l", "*"),
      "library_count_summary": ("-f", "-c"),
  }
  ```

  **`run_qemu_user(case_dir, sample, arch, profile, extra_args=None, run_argv=None) -> dict`**

  ```python
  QEMU_USER_PROFILES: Mapping[str, tuple[str, ...]] = {
      "simple":              (),                                # qemu-<arch>-static <sample>
      "syscall_strace":      ("-strace",),                      # qemu's built-in strace
      "singlestep_asm":      ("-singlestep", "-d", "in_asm,exec"),
      "page_faults":         ("-d", "page"),
      "all_trace":           ("-d", "in_asm,exec,page,cpu,fpu"),
  }
  ```

  `arch` is a required kwarg for qemu_user (`"arm" | "aarch64" | "mips" | "mipsel" | "ppc" | "ppc64" | "i386" | "x86_64" | "riscv64" | "sparc"`),
  validated against `dynamic.CAPABILITIES.qemu_architectures` at
  start_tool_job time; unsupported arch returns a structured error
  before any subprocess spawns.

- **D-DYN-PROF-02:** `extra_args` allowlist regex (applied per-arg,
  case-sensitive):

  ```python
  EXTRA_ARGS_ALLOWLIST_RE = re.compile(
      r"^("
      r"-[a-zA-Z][a-zA-Z0-9_-]{0,31}"          # short flag like -f, -ff, --help
      r"|--[a-zA-Z][a-zA-Z0-9_-]{0,63}"        # long flag like --signal=KILL
      r"|--[a-zA-Z][a-zA-Z0-9_-]{0,63}=[a-zA-Z0-9_,/.:+-]{1,256}"  # long flag with value
      r"|[a-zA-Z0-9_,/.:+-]{1,256}"            # bare value (e.g., 'trace=open,read')
      r")$"
  )
  ```

  Hard-blocks any arg containing:
  - `;`, `|`, `&`, `$`, backtick, redirect (`>`, `<`), newline,
    tab, NUL byte (shell-injection sanity even though we're
    argv-only — defense-in-depth)
  - Paths containing `..` (path traversal — should be path
    arguments validated separately via `confine_to`, not `extra_args`)
  - The `-o` / `--output-separately` / `-D` / `--detach` /
    `--daemonize` flags (output-path control and detachment are
    gateway responsibilities, not agent-controllable)
  - The `-p` / `--attach` flags (attaching to existing PIDs is not
    in the v1.1 model — sample-execution only)

  An explicit deny set after the allowlist regex:

  ```python
  _DENIED_EXTRA_ARG_FLAGS = frozenset({
      "-o", "-D", "--daemonize", "--detach", "-p", "--attach",
      "--output-separately", "--exec",  # strace --exec re-execs the binary
  })
  ```

  Each `extra_args` entry must:
  1. Match `EXTRA_ARGS_ALLOWLIST_RE`,
  2. NOT be in `_DENIED_EXTRA_ARG_FLAGS` (split on `=` first to handle
     `--detach=true`),
  3. NOT contain shell-metachar (redundant with regex but explicit).

  Failures return a structured `{error: "invalid extra_args[<i>]: <reason>"}`
  before the job spawns.

- **D-DYN-PROF-03:** `run_argv` parameter (optional, applies to
  strace/ltrace/qemu_user) — argv passed to the SAMPLE itself, not
  the trace tool. Defaults to `[]` (run sample with no args).
  Validated against the same allowlist regex as `extra_args` (no
  shell metachars). Useful for samples that need argv (e.g., a
  cli-style malware that does different things based on argv[1]).

  *Rationale:* Most real samples accept argv. Without this kwarg,
  agents would have to wrap the sample in a shell script just to
  pass args, breaking the argv-only safety posture. The same
  allowlist regex applies because these strings end up in argv too.

- **D-DYN-PROF-04:** Profile design is uniform across the three
  trace tools: every builder accepts `(case_dir, sample,
  profile_name, extra_args, run_argv)` plus tool-specific kwargs
  (qemu_user adds `arch`). This is deliberate: a single
  `JobToolSpec.kwargs_schema` shape across all three with one or
  two tool-specific fields keeps the orchestrator's mental model
  simple ("strace and qemu look the same; qemu adds arch").

### Sync vs job dispatch & startup capability UX (Area 4)

- **D-DYN-DISPATCH-01:** All three trace tools (`run_strace`,
  `run_ltrace`, `run_qemu_user`) ALWAYS dispatch as jobs via the
  Phase 9 `start_tool_job` mechanism. There is no `wait=True`
  shortcut. The MCP-facing `run_strace(...)` handler is a thin
  wrapper that calls `start_tool_job(tool="strace", kwargs=...,
  case_dir=...)` and returns the immediate job snapshot dict
  (`status="pending"` / `"running"`).

  Agent polling loop:
  ```python
  job = run_strace(case_dir, sample, profile="file_network_process")
  while job["status"] in ("pending", "running"):
      await sleep(1.0)
      job = get_tool_job(job["job_id"])
  ```

  *Rationale:* DYN-07 explicitly says "long-running dynamic tools
  dispatch through the JOBS system." Every dynamic invocation is
  potentially long (a sample that loops, hangs, sleeps, or does
  heavy I/O). Sync mode would bypass the JOBS log-cap / cancel /
  retention scaffolding. Robust > ergonomic shortcut. Orchestrator
  can poll at 250 ms intervals if it wants near-sync latency.

- **D-DYN-DISPATCH-02:** gdb is the ONLY dynamic-mode session
  primitive (mirrors Phase 8 r2). `open_gdb_session` / `gdb_exec` /
  `close_gdb_session` are direct MCP-facing tools that don't go
  through `start_tool_job`. Per-command 60 s timeout (D-09) keeps
  any single MI command bounded; long-running inferior execution
  (e.g., `-exec-continue` running for minutes) is handled by
  `-exec-interrupt` (which IS in the MI allowlist) rather than
  job-level cancellation.

  *Rationale:* gdb's value comes from interactive iteration —
  setting a breakpoint, continuing, inspecting state, continuing
  again. Wrapping each `gdb_exec` in a job would force the
  orchestrator to poll for every command response, defeating the
  point of the session abstraction. The 60 s per-cmd timeout
  bounds the worst-case hang.

- **D-DYN-CAP-PROBE-01:** Capability probe runs ONCE at gateway
  startup (in `app.py::lifespan`, after `register_all_tools` and
  BEFORE entering `PinnedBackend`), populating
  `dynamic.CAPABILITIES`. The probe runs unconditionally (whether
  or not dynamic mode is on) — the capability info is informational
  even when dynamic tools aren't registered, and the probe is
  cheap (<200 ms). Probe shape:

  ```python
  @dataclasses.dataclass(frozen=True)
  class DynamicCapabilities:
      probed_at: str                          # ISO8601 Z
      dynamic_mode_enabled: bool              # MCP_GATEWAY_DYNAMIC_TOOLS == "1"
      ptrace_scope: int | None                # /proc/sys/kernel/yama/ptrace_scope; None if file missing
      ptrace_traceme_works: bool              # in-fork PTRACE_TRACEME probe
      binfmt_misc_mounted: bool
      qemu_architectures: tuple[str, ...]     # arches with binfmt registration AND qemu-<arch>-static present
      qemu_static_binaries: tuple[str, ...]   # qemu-*-static binaries found in $PATH (separate signal from binfmt)
      netns_feasible: bool                    # `unshare --net true` round-trip works
      unshare_path: str | None                # /usr/bin/unshare
      gdb_path: str | None
      gdb_version: str | None                 # parsed from `gdb --version`
      strace_path: str | None
      ltrace_path: str | None
      warnings: tuple[str, ...]               # operator-visible WARN strings
  ```

  Probe methods (all best-effort, none raise):
  - `ptrace_scope` = `int(open("/proc/sys/kernel/yama/ptrace_scope").read().strip())` or `None`
  - `ptrace_traceme_works` = spawn a child that calls
    `ctypes.CDLL("libc.so.6").ptrace(PTRACE_TRACEME, 0, 0, 0)`,
    parent waits for it, returns True if rc == 0
  - `binfmt_misc_mounted` = `os.path.isdir("/proc/sys/fs/binfmt_misc")`
    AND `os.path.exists("/proc/sys/fs/binfmt_misc/register")`
  - `qemu_architectures` = parse `/proc/sys/fs/binfmt_misc/qemu-*`
    files for `enabled` flag AND for `F` flag in `flags:` line
    (Pitfall 10 — `F` is what makes the registration work inside
    container mount namespace), cross-check with `which qemu-<arch>-static`
  - `netns_feasible` = `subprocess.run(["unshare", "--net", "true"], timeout=3)` returns 0
  - `gdb_version` = `subprocess.run(["gdb", "--version"], timeout=3).stdout.decode().splitlines()[0]`

- **D-DYN-CAP-PROBE-02:** Probe failure behavior — `dynamic.probe_all()`
  NEVER raises; missing capabilities become `None` / `False` / `()`
  fields, with descriptive WARN strings appended to `capabilities.warnings`.
  Gateway startup continues regardless. Each tool consults the
  capabilities at call time and returns a structured error dict
  pointing to the missing capability with an actionable hint:

  ```python
  # run_strace handler, before start_tool_job:
  if not (dynamic.CAPABILITIES.ptrace_traceme_works
          and dynamic.CAPABILITIES.netns_feasible):
      return {
          "error": "dynamic capability unavailable",
          "missing": ["ptrace" if not dynamic.CAPABILITIES.ptrace_traceme_works else None,
                      "netns"  if not dynamic.CAPABILITIES.netns_feasible else None],
          "ptrace_scope": dynamic.CAPABILITIES.ptrace_scope,
          "hint": "host operator: set /proc/sys/kernel/yama/ptrace_scope=0 "
                  "or run docker with --cap-add=SYS_PTRACE --security-opt apparmor=unconfined",
          "capabilities_snapshot": dataclasses.asdict(dynamic.CAPABILITIES),
      }
  ```

  *Rationale:* Hard-failing at gateway startup would break the
  no-backend test path and prevent operators from running
  `--dynamic` to see what's broken. Pitfall 11 says: "Surface result
  via `get_dynamic_capabilities()`. If denied, `run_strace`/...
  return `{error: ...}`." This implements that exactly. Robust
  diagnostics > fail-fast in this case because dynamic-tool
  callers benefit from the actionable hint.

- **D-DYN-PROBE-LOG:** At gateway startup, log one WARN-level line
  per missing capability when `MCP_GATEWAY_DYNAMIC_TOOLS=1`:

  ```
  [gateway] [dynamic] startup capability probe complete
  [gateway] [dynamic] WARN: ptrace_scope=2 detected — strace/ltrace/gdb
                            will return ERROR until host sets yama.ptrace_scope=0
  [gateway] [dynamic] WARN: binfmt_misc not mounted — run_qemu_user can still
                            run explicitly (qemu-<arch>-static path), but ./<foreign_bin>
                            via run_shell will fail with exec format error
  [gateway] [dynamic] OK: netns_feasible
  [gateway] [dynamic] OK: gdb=15.0.50.20240403-git
  [gateway] [dynamic] qemu_architectures: arm, aarch64, mips, mipsel, ppc, ppc64, i386, riscv64
  ```

  When `MCP_GATEWAY_DYNAMIC_TOOLS != "1"`, log a single line:
  `[gateway] [dynamic] dynamic-mode tools DISABLED (set MCP_GATEWAY_DYNAMIC_TOOLS=1 to enable)`.
  No WARN noise — operator hasn't opted in, missing capabilities are
  irrelevant.

- **D-DYN-CAP-REFRESH:** `get_dynamic_capabilities()` MCP tool returns
  the snapshot. Optional kwarg `refresh: bool = False`: if True, re-run
  `probe_all()` and update `dynamic.CAPABILITIES` (under a module-level
  asyncio.Lock to serialize). Useful for operator troubleshooting
  ("I just set ptrace_scope=0 on the host, recheck"). Default False:
  every call returns the startup snapshot for cheap reads.

- **D-DYN-CAP-CURRENTSTATE:** `CURRENT_STATE.json` writing is a
  Phase 12 responsibility (orchestrator skill update). Phase 11
  ONLY exposes `get_dynamic_capabilities()`. Phase 12's
  `update_state.py` calls the tool and writes the result into each
  case's status file. Phase 11 does NOT modify `workspace/.claude/`,
  `workspace/.codex/`, or any orchestrator scripts. This split
  preserves Phase 11's "additive, no v1.0 file rewritten"
  invariant (per ARCHITECTURE.md "purely additive" promise).

### run_docker.sh `--dynamic` flag

- **D-DYN-FLAG-01:** `run_docker.sh` adds a `--dynamic` flag. Behavior:

  ```bash
  --dynamic) DYNAMIC_TOOLS=1; shift ;;
  ```

  Compositional with `--remote`. Hard-error if `--dynamic` is
  passed without `--remote`:

  ```bash
  if [[ "$DYNAMIC_TOOLS" == "1" && "$MODE" != "remote" ]]; then
    echo "[error] --dynamic requires --remote (dynamic tools are an MCP-only surface)" >&2
    echo "[error] retry: ./run_docker.sh --remote --dynamic" >&2
    exit 64  # EX_USAGE
  fi
  ```

  When set, exported into the docker-compose environment alongside
  `MCP_GATEWAY_ENABLED`:

  ```bash
  export MCP_GATEWAY_DYNAMIC_TOOLS="${DYNAMIC_TOOLS:-0}"
  ...
  MCP_GATEWAY_DYNAMIC_TOOLS="$MCP_GATEWAY_DYNAMIC_TOOLS" \
  docker compose up -d kali
  ```

  Usage banner updated to document `--remote --dynamic`. The
  ready-block (after the container is up) prints an extra line
  when dynamic mode is on:

  ```
  Dynamic mode: ENABLED — run_strace, run_ltrace, run_qemu_user, gdb session
                Capability probe results: /healthz or get_dynamic_capabilities()
  ```

- **D-DYN-FLAG-02:** `compose.yaml` does NOT hardcode the env var
  — it's passed through via the docker-compose env-var-export
  mechanism (same pattern Phase 3 used for `MCP_GATEWAY_HOST_BIND`
  / `MCP_GATEWAY_HOST_PORT`). This means rebuilds aren't needed
  when toggling `--dynamic`.

- **D-DYN-FLAG-03:** No `--dynamic-and-allow-net` flag in v1.1.
  Network-allowed dynamic mode is v1.2 territory (REQUIREMENTS
  Out of Scope).

### JOBS integration (Phase 9 plug-in)

- **D-DYN-JOB-01:** Three new `JobToolSpec` entries registered into
  `mcp_gateway.jobs.JOB_TOOL_REGISTRY` at `dynamic.py` import
  time (matches Phase 9 D-04 / Phase 10 D-01 pattern):

  ```python
  STRACE_SPEC = JobToolSpec(
      name="strace",
      slug="strace",
      build_argv=build_strace_argv,
      default_timeout_s=900.0,    # 15 min — strace -f on a sample that sleeps
      progress_parser=None,        # strace stderr is the trace itself; no progress lines
      kwargs_schema={
          "sample":     {"type": "string", "required": True},
          "profile":    {"type": "string", "required": True, "enum": list(STRACE_PROFILES)},
          "extra_args": {"type": "array", "items": {"type": "string"}, "max_items": 16},
          "run_argv":   {"type": "array", "items": {"type": "string"}, "max_items": 32},
      },
      description="Linux strace under per-call netns (no-net). Profile-driven argv. "
                  "Output: case_dir/dynamic/<ts>-strace-<rand4>.txt",
  )
  LTRACE_SPEC = JobToolSpec(
      name="ltrace",
      slug="ltrace",
      build_argv=build_ltrace_argv,
      default_timeout_s=900.0,
      progress_parser=None,
      kwargs_schema={...},
      description="Linux ltrace under per-call netns. Profile-driven. "
                  "Output: case_dir/dynamic/<ts>-ltrace-<rand4>.txt",
  )
  QEMU_USER_SPEC = JobToolSpec(
      name="qemu_user",
      slug="qemu_user",
      build_argv=build_qemu_user_argv,
      default_timeout_s=1800.0,   # 30 min — qemu emulation is slow
      progress_parser=None,
      kwargs_schema={
          "sample":     {"type": "string", "required": True},
          "arch":       {"type": "string", "required": True, "enum": [
              "arm","aarch64","mips","mipsel","ppc","ppc64","i386","x86_64","riscv64","sparc"
          ]},
          "profile":    {"type": "string", "required": True, "enum": list(QEMU_USER_PROFILES)},
          "extra_args": {"type": "array", "items": {"type": "string"}, "max_items": 16},
          "run_argv":   {"type": "array", "items": {"type": "string"}, "max_items": 32},
      },
      description="qemu-<arch>-static under per-call netns. "
                  "Output: case_dir/qemu/<ts>-qemu_user-<rand4>.txt",
  )

  # Register at module import:
  for spec in (STRACE_SPEC, LTRACE_SPEC, QEMU_USER_SPEC):
      register_job_tool(spec)
  ```

  Since `dynamic.py` is only imported when
  `MCP_GATEWAY_DYNAMIC_TOOLS=1`, these specs only enter
  `JOB_TOOL_REGISTRY` when dynamic mode is on. The Phase 9
  `list_tool_jobs(state="_specs")` discovery surface picks them
  up automatically when on, and omits them when off. ZERO leak.

- **D-DYN-JOB-02:** `build_strace_argv` example (verbatim shape;
  ltrace/qemu_user analogous):

  ```python
  def build_strace_argv(case_dir: Path, kwargs: dict) -> list[str]:
      sample_sha, sample_path = resolve_sample(kwargs["sample"])
      profile = kwargs["profile"]
      extra_args = _validate_extra_args(kwargs.get("extra_args", []))
      run_argv = _validate_extra_args(kwargs.get("run_argv", []))

      out_path = ensure_subdir(case_dir, "dynamic") / tool_log_filename("strace", ".txt")
      profile_args = STRACE_PROFILES[profile]

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

  Note: `confine_to(case_dir, out_path)` is run inside `ensure_subdir`
  already. The `-o <path>` flag is set by the builder, NOT the
  caller (Phase 11 D-DYN-PROF-02 deny-list of `extra_args` includes
  `-o` for this exact reason).

- **D-DYN-JOB-03:** Follow-fork process-group cleanup. After a job
  completes (either gracefully, on cancel, or on timeout) the
  Phase 9 drain loop's exit path calls
  `dynamic.reap_followfork_strays(runner_pid, pgid)` which:

  1. Walks `/proc/<runner_pid>/task/*/children` to find direct
     children of the runner pid still alive.
  2. For each, walks its own `/proc/<pid>/task/*/children`
     recursively (DFS, bounded depth 8).
  3. For any descendant whose `pgid != original_pgid` (escaped
     via `setsid`), `os.kill(pid, SIGKILL)`.
  4. Returns count of strays reaped; logged at INFO level if
     count > 0.

  Wired as a `post_terminal_hook` in the strace/ltrace/qemu_user
  JobToolSpecs. Phase 9 D-22 says drain task ownership is registry-side;
  Phase 11 extends with a post-hook (NEW small extension to
  `JobToolSpec` dataclass: `post_terminal_hook: Callable[[Job], Awaitable[None]] | None = None`).
  If Phase 9 doesn't have that field, the planner adds it as a
  one-line extension to `JobToolSpec` per the Phase 10 D-17 "Phase
  10 extends extraction.py in-place" precedent.

  *Rationale:* Pitfall 4 specifically called out follow-fork
  `setsid` escapees as a `strace -f` failure mode. Reaping in a
  post-terminal hook is the safest place — by then the drain loop
  has finished, the original pgid is dead, and any survivors are
  definitionally escapees worth killing.

### Tool surface (`tools/dynamic.py`)

- **D-DYN-TOOL-01:** Seven `@mcp.tool()` handlers, registered via
  the standard `register(mcp)` seam:

  1. `run_strace(case_dir, sample, profile, extra_args=None, run_argv=None, timeout=None) -> dict`
     — calls `start_tool_job("strace", kwargs, case_dir=case_dir, timeout=timeout)`,
     returns the Phase 9 D-19 snapshot.
  2. `run_ltrace(case_dir, sample, profile, extra_args=None, run_argv=None, timeout=None) -> dict`
     — analogous.
  3. `run_qemu_user(case_dir, sample, arch, profile, extra_args=None, run_argv=None, timeout=None) -> dict`
     — analogous.
  4. `open_gdb_session(case_dir, sample, init_commands=None, follow_fork_mode="parent", open_timeout=None) -> dict`
     — uses `session_state.SESSION_REGISTRY.open(kind="gdb", ...)`,
     returns D-15-style dict matching Phase 8 D-19 with gdb fields.
  5. `gdb_exec(session_id, cmd, timeout=None) -> dict`
     — D-08 12-key + gdb extension shape.
  6. `close_gdb_session(session_id) -> dict`
     — mirrors Phase 8 D-21 `close_r2_session` (idempotent).
  7. `get_dynamic_capabilities(refresh=False) -> dict`
     — returns `dataclasses.asdict(dynamic.CAPABILITIES)`.

  Tool count delta: +7 when env-gated on; +0 when off. Names
  collision-check at lifespan startup (Phase 7 D-12) — none of
  the seven collide with backend-pass-through (`run_*` is
  gateway-domain prefix).

- **D-DYN-TOOL-02:** Docstring disclaimer for EVERY dynamic-mode
  tool (copy-paste-able from Phase 8 D-23 / Phase 9 D-26 pattern):

  > **Dynamic mode tool (env-gated, no-net by default).**
  >
  > This tool is registered only when `MCP_GATEWAY_DYNAMIC_TOOLS=1`
  > at gateway startup. Subprocess runs under per-call
  > `unshare --net --ipc --uts` — no network, no host IPC, no
  > shared UTS. The sample IS executed; only run on samples you
  > intend to detonate. Output captured under
  > `case_dir/{dynamic,qemu}/`.
  >
  > Capability prerequisites (see `get_dynamic_capabilities()`):
  > - strace/ltrace/gdb: `ptrace_scope` must allow parent-child
  >   tracing (yama.ptrace_scope=0 or =1).
  > - qemu_user: the requested arch must be in `qemu_architectures`.
  >
  > Sessions and jobs are shared across all MCP clients with the
  > same bearer token. Per-`Mcp-Session-Id` keying is deferred
  > to v1.2.

  Phase 11 D-DYN-TOOL-02-TEST adds a regression test asserting the
  disclaimer string is present in all 7 tool docstrings.

- **D-DYN-TOOL-03:** `open_gdb_session` return dict (mirrors Phase
  8 D-19):

  ```python
  {
      "session_id": str,
      "kind": "gdb",
      "case_dir": str,
      "sample_sha256": str,
      "sample_path": str,
      "transcript_path": str,            # case-rel: dynamic/<sid>-gdb-transcript.log
      "opened_at": str,                  # ISO8601 Z
      "gdb_version": str,
      "follow_fork_mode": Literal["parent","child"],
      "max_sessions": int,
      "open_count": int,                 # AFTER this open (combined r2+gdb)
      "init_command_count": int,
      "warnings": list[str],
  }
  ```

  Transcript file mirrors Phase 8 D-13 r2 format, with `gdb_cmd`
  marker instead of `r2_cmd`. Lives under `dynamic/` (not
  `r2-sessions/`) so dynamic-mode artifacts cluster together for
  the orchestrator skill's `dynamic/` walker.

### Module imports and boundaries

- **D-DYN-IMPORT-01:** Import graph (matches Phase 8 D-06 / Phase
  9 D-24 / Phase 10 layering):

  ```
  sessions/_base.py   stdlib + nothing else (LEAF)
  sessions/r2.py      imports: sessions._base, artifacts_io
                      MUST NOT import: tools/*, mcp.server.fastmcp
  sessions/gdb.py     imports: sessions._base, artifacts_io, dynamic (for wrap_netns)
                      MUST NOT import: tools/*, mcp.server.fastmcp
  sessions/__init__.py re-exports from r2, gdb, _base
  dynamic.py          imports: artifacts_io, runner, jobs (for register_job_tool)
                      MUST NOT import: tools/*, mcp.server.fastmcp, sessions.*
  tools/dynamic.py    imports: dynamic, sessions, tools.case_dirs, tools.samples
                      MUST NOT import: tools/r2_sessions, tools/jobs, tools/extract
                      (no cross-tool coupling)
  app.py::lifespan    imports: dynamic (for CAPABILITIES + probe_all)
                      probes ONCE at startup; no re-probe in the request path
  tools/__init__.py   conditional import of tools.dynamic only when
                      MCP_GATEWAY_DYNAMIC_TOOLS == "1"
  ```

  The one cross-package edge (`sessions/gdb.py` imports `dynamic.wrap_netns`)
  is acceptable because `dynamic.py` is leaf-ish itself (stdlib +
  `artifacts_io` + `runner` + `jobs`). The alternative — moving
  `wrap_netns` into `_base.py` — couples netns posture into the
  generic session base; cleaner to keep netns isolation as a
  dynamic-mode primitive.

- **D-DYN-IMPORT-02:** `register_job_tool` (Phase 9) must be
  callable from outside `jobs.py`. If it's currently module-private,
  Phase 11 promotes it to a public symbol via re-export (matches
  Phase 10's pattern of registering specs from `extraction.py`).
  If Phase 10 already promoted it, no change.

### Env-var configuration

- **D-DYN-ENV-01:** Env vars added by Phase 11, read once at
  `dynamic.py` / `sessions/_base.py` / `sessions/gdb.py` module
  import with `RuntimeError` on bad values (matches Phase 6 D-08 /
  Phase 8 D-14 / Phase 9 D-13 / Phase 10 D-08 patterns):

  | Env var | Default | Module | Purpose |
  |---|---|---|---|
  | `MCP_GATEWAY_DYNAMIC_TOOLS` | `0` | `tools/__init__.py` | The gate; `"1"` enables registration |
  | `MCP_GATEWAY_GDB_OPEN_TIMEOUT_S` | `30.0` | `sessions/gdb.py` | gdb spawn + init batch wallclock |
  | `MCP_GATEWAY_GDB_CMD_TIMEOUT_S` | `60.0` | `sessions/gdb.py` | per-`gdb_exec` wallclock |
  | `MCP_GATEWAY_DYN_REAP_DEPTH` | `8` | `dynamic.py` | max recursion depth for follow-fork stray reaping |
  | `MCP_GATEWAY_DYN_PROBE_TIMEOUT_S` | `3.0` | `dynamic.py` | per-probe wallclock (each capability probe) |

  `MCP_GATEWAY_MAX_SESSIONS` / `MCP_GATEWAY_SESSION_IDLE_S` /
  `MCP_GATEWAY_REAPER_INTERVAL_S` carry forward from Phase 8 D-14
  unchanged and now apply to BOTH r2 and gdb session kinds (D-02).

### Tests (D-DYN-TEST-*)

- **D-DYN-TEST-01:** Test layout (mirrors Phase 8 / Phase 9 /
  Phase 10 split):

  ```
  mcp-gateway/tests/
  ├── test_dynamic_primitive.py    # dynamic.py: probes, argv builders, wrap_netns, reap_followfork_strays
  ├── test_dynamic_tools.py        # tools/dynamic.py MCP surface
  ├── test_gdb_session.py          # sessions/gdb.py driver + MI3 framing + allowlist
  ├── test_sessions_package.py     # sessions/ refactor regression (re-export name-for-name)
  ├── test_dynamic_jobs.py         # jobs.py + dynamic JobToolSpec integration (3 specs round-trip)
  └── test_dynamic_gate.py         # tools/__init__.py env-gate behavior
  ```

  Slow-marked tests:
  - Real strace round-trip on a Linux fixture binary (skip if
    `ptrace_traceme_works` is False on the runner host).
  - Real gdb MI3 session on a small ELF (skip if no gdb).
  - Real qemu-user on an arm/mips fixture (skip if arch missing).
  - Netns sanity test: a sample that does `getaddrinfo` under
    `run_strace` must show `ENETUNREACH`, NOT a real resolution.

- **D-DYN-TEST-02:** Env-gate regression tests:
  - With env unset: `tools.dynamic` is not imported (negative
    `sys.modules` check), `get_dynamic_capabilities` is not in
    `tools/list`, `JOB_TOOL_REGISTRY` does not contain
    `"strace"` / `"ltrace"` / `"qemu_user"`.
  - With env set: 7 new tools in `tools/list`, 3 new
    `JobToolSpec`s in registry.
  - `EXPECTED_TOOLS` test: parametrize on the env var. With unset,
    expect 54; with `"1"`, expect 61.

- **D-DYN-TEST-03:** gdb allowlist matrix (mirrors Phase 8 D-09):
  - POSITIVE (allowed): `-info-functions`,
    `-data-evaluate-expression "$rip"`, `-stack-list-frames`,
    `-exec-run`, `-break-insert main`, `-thread-info`,
    `-var-create v0 * argv`.
  - NEGATIVE (refused): `-interpreter-exec console "python print(1)"`,
    `python print(1)`, `pi print(1)`, `source /tmp/x`,
    `-gdb-set logging on`, `attach 1`, `add-symbol-file /tmp/x`,
    `-target-select remote :1234`, `shell ls`, `!ls`,
    `info threads` (lacks `-` prefix → not allowlisted, robust
    against CLI-mode commands that happen to share names with MI).
  - COMPOSITE: ensure that `;` / `\n` separators don't sneak a
    denied cmd past the allowlist (full-string scan).

- **D-DYN-TEST-04:** Netns enforcement test — a 30-line fixture
  C program that does `socket(AF_INET, SOCK_STREAM, 0); connect(...)`
  to `8.8.8.8:53`. Spawned under `run_strace` MUST show
  `ENETUNREACH` (or `EHOSTUNREACH`) syscall result. Spawned without
  the wrap (negative control, calls `build_strace_argv` then
  removes the `unshare` prefix) MUST connect (proves the
  wrap is what's blocking). Latter is a unit-test-only path
  (never reachable in production).

- **D-DYN-TEST-05:** Probe-fail-safe test — monkeypatch
  `/proc/sys/kernel/yama/ptrace_scope` reading to return `None`,
  monkeypatch `which("unshare")` to return None, etc., assert
  `probe_all()` returns a Capabilities object with the appropriate
  None / False / () fields and non-empty `warnings`. Lifespan
  startup with these monkeypatches MUST still succeed (no crash);
  `run_strace` MUST return the structured error dict.

- **D-DYN-TEST-06:** Follow-fork stray reap test — fixture C
  program that `fork()`s, child `setsid()`s and `sleep(60)`s,
  parent exits 0. Under `run_strace -f`, after the job terminates,
  `reap_followfork_strays` must find and SIGKILL the
  `setsid`-escaped child. Asserted by polling `/proc/<pid>/stat`
  for the child PID — must be gone within 1 s of job termination.

- **D-DYN-TEST-07:** Disclaimer regression — scan all 7 tool
  docstrings for the D-DYN-TOOL-02 disclaimer string. Fails if
  any tool is missing it.

### Claude's Discretion (within these constraints)

- Exact wording of WARN log strings (D-DYN-PROBE-LOG) — structure
  is locked, prose can be polished.
- Whether `reap_followfork_strays` is a method on `Job` or a free
  function in `dynamic.py` — both work; free function keeps Phase 9
  D-22 drain ownership clean.
- Whether `STRACE_PROFILES` lives in `dynamic.py` module-level or
  in a `dynamic/_profiles.py` submodule — for 3 dicts of <10 entries
  each, module-level is fine.
- Whether `sessions/__init__.py` does explicit name-by-name
  re-export or `from .r2 import *` (recommend explicit — easier to
  audit, easier to deprecate symbols later).
- Whether `get_dynamic_capabilities()` returns the dataclass as-is
  or wraps in `{"capabilities": ..., "as_of": ...}` — recommend
  dataclass-as-dict directly (simpler, the `probed_at` field is
  already inside).
- Whether `open_gdb_session` accepts a `follow_fork_mode="child"`
  override for analyzing child processes specifically — recommend
  YES (parent is the default per D-05; child is occasionally what
  the analyst wants for, e.g., a launcher binary that execs the
  real payload).
- Whether `gdb` is wrapped with `gosu agent` or runs as the
  gateway-default user — recommend NO setpriv wrap (shell.py's
  setpriv-to-mare-shell is for `run_shell` which untrusted commands
  flow through; gdb is invoked argv-only with a strict MI allowlist
  and runs as `agent` to keep `SYS_PTRACE` available).
- The exact `gdb` argv for `--quiet --nx --nh` — verify all three
  flags work on the container's gdb version during the research
  phase. Pre-9.0 gdbs don't have `--nh`; the planner can substitute
  `-iex "set auto-load no"` if needed (research phase will confirm
  the container ships a gdb >= 13.0 per Kali current).
- Whether `tools/dynamic.py` module-level coroutines or
  inside-`register(mcp)` definitions — recommend module-level
  coroutines (matches Phase 10 D-19 / Phase 8 D-23 pattern,
  enables direct test import).
- Whether to keep an `MCP_GATEWAY_DYNAMIC_TOOLS=force_enable_in_tests`
  bypass for the env-gate negative test — recommend NO (the
  monkeypatch approach in D-DYN-TEST-02 is cleaner).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 milestone requirements

- `.planning/REQUIREMENTS.md` §"Dynamic Lab Mode (DYN, env-gated default-off)" — DYN-01..DYN-07 are the seven authoritative requirements for this phase
- `.planning/REQUIREMENTS.md` §"Out of Scope (v1.1)" — confirms mount-ns deferred, per-`Mcp-Session-Id` keying deferred, always-on dynamic mode rejected, sandboxed-network deferred, batch-only gdb rejected
- `.planning/REQUIREMENTS.md` §"Future Requirements (deferred to v1.2+)" — per-call netns, INetSim/FakeDNS, mount-ns
- `.planning/ROADMAP.md` §"Phase 11: Dynamic Lab Mode (env-gated)" — phase goal, depends-on (Phases 6/7/8/9), six success criteria (SC-1..SC-6)

### Project & milestone framing

- `.planning/PROJECT.md` §"Current Milestone: v1.1 Remote RE Tool Expansion" — "Dynamic Lab Mode" target-feature paragraph (env-gated default-off, `./run_docker.sh --dynamic` surfaces it, tools listed)
- `.planning/PROJECT.md` §"Key Decisions" — "Dynamic mode env-gated default-off, surfaced via `./run_docker.sh --dynamic`" row
- `.planning/PROJECT.md` §Constraints — `SYS_PTRACE` + `seccomp=unconfined` posture (informs the capability probe; ptrace works iff host yama allows it)
- `.planning/STATE.md` §"Pending Todos" / "Blockers/Concerns" — Phase 11 sub-decisions list (per-call netns mechanism, ptrace probe error UX, gdb MI3 allowlist, binfmt detection helper) — each is locked in this CONTEXT

### Phase 6 chokepoint runner

- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-01..D-04 — `ReToolRunner` argv-only / start_new_session=True / process-group SIGKILL / 12-key result dict / never-raises contract (Phase 11 D-08 layers on top for gdb_exec)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-08, D-09 — env-var module-constant pattern (Phase 11 D-DYN-ENV-01 follows), `tool-logs/<UTC>Z-<slug>-<rand4>.txt` filename (Phase 11 reuses for gdb per-cmd logs)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-16 — `EXPANDED_CASE_SUBDIRS` catalog (Phase 11 reuses `dynamic/` and `qemu/` without extension)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-17 — `start_new_session=True` + `killpg(SIGKILL)` (Phase 11 D-DYN-JOB-03 extends with follow-fork stray scan)

### Phase 7 case-dir conventions

- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-09 — `tool_log_path` API and filename shape (Phase 11 D-08 calls verbatim for `gdb_cmd`)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-11..D-15 — `assert_no_collisions` invariant (Phase 11's 7 tool names must not collide; `run_*` and `*_gdb_session` are gateway-domain so safe)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-25 — `get_tool_log` range-read surface (orchestrator uses this for multi-MB strace logs)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-26 — depth-2 case-dir Resource walker (auto-exposes `dynamic/<file>` and `qemu/<file>` as `mare://cases/<case>/dynamic/<file>` once Phase 11 writes there)

### Phase 8 r2-session pattern (the direct precedent for gdb)

- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-01 — raw asyncio + sentinel over r2pipe-in-thread (Phase 11 D-06 mirrors for gdb-MI3)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-03 — mandatory lockdown init before user init_commands (Phase 11 D-05 mirrors)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-04 — per-session randomized sentinel suffix (Phase 11 D-06 reuses identical generator)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` **D-05 — "Phase 11 owns the rename-only refactor"** — explicit deferred decision now resolved by Phase 11 D-01
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-08, D-09 — dangerous-command refusal pattern (Phase 11 D-07 mirrors with MI3-specific allowlist)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-11 — 12-key + session-extension dict shape (Phase 11 D-08 mirrors)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-14 — env-var pattern + `_env_int/_env_float` helpers (Phase 11 D-DYN-ENV-01 hoists into `sessions/_base.py`)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-15..D-23 — full SessionRegistry / open / cmd / close / list shape (Phase 11 D-02..D-10 mirrors for gdb)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` SESS-05 disclaimer phrasing — Phase 11 D-DYN-TOOL-02 uses analogous wording

### Phase 9 jobs system (the layer Phase 11's trace tools sit on)

- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-01..D-05 — `JobToolSpec` shape, `JOB_TOOL_REGISTRY` registration, `start_tool_job` resolution order (Phase 11 D-DYN-JOB-01 plugs in 3 specs)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-06 — JobStatus 7-state vocabulary (Phase 11 reuses, no new states needed)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-07, D-08, D-22, D-23 — SIGTERM-grace cancel, hard-timeout, drain-task ownership, CancelledError contract (Phase 11 D-DYN-JOB-03 extends with post-terminal hook for follow-fork)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-19 — D-19 24-key snapshot shape (Phase 11 tools return this verbatim from `start_tool_job`)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-25 — lifespan nesting order: PinnedBackend > SessionRegistry > BackgroundJobRegistry > session_manager (Phase 11 does not change this; gdb sessions go into the existing SessionRegistry, not a new registry)
- `.planning/phases/09-background-job-system/09-CONTEXT.md` D-26 — disclaimer pattern (Phase 11 D-DYN-TOOL-02 mirrors)

### Phase 10 extraction tier (most recent precedent)

- `.planning/phases/10-extraction-tier/10-CONTEXT.md` D-01 — registration of new JobToolSpecs at module import (Phase 11 D-DYN-JOB-01 mirrors for 3 dynamic specs)
- `.planning/phases/10-extraction-tier/10-CONTEXT.md` D-08 — Dockerfile package additions (Phase 11 verifies util-linux + qemu-user-static)
- `.planning/phases/10-extraction-tier/10-CONTEXT.md` D-17 — sibling-monitor pattern (Phase 11 D-DYN-JOB-03 follow-fork reap hook is analogous post-terminal hook)
- `.planning/phases/10-extraction-tier/10-CONTEXT.md` notes the EXPECTED_TOOLS bump pattern (Phase 11 D-DYN-TEST-COUNT follows)

### Research consensus (v1.1 milestone-level)

- `.planning/research/SUMMARY.md` §"Critical Pitfalls" — Pitfalls 4 (follow-fork pgroup escape), 9 (netns enforcement), 10 (binfmt drift), 11 (ptrace yama scope), 13 (single-session state), 18 (FastMCP cancel propagation) — all six clustered in Phase 11 per SUMMARY's own §"Research Recommendations"
- `.planning/research/SUMMARY.md` §"Open Decisions / Tensions" — netns mechanism row resolved here (per-call unshare), binfmt detection row resolved here (probe at startup, no auto-register)
- `.planning/research/SUMMARY.md` §"Phase 7: Dynamic Lab Mode" (in research numbering — corresponds to roadmap Phase 11) — delivers list, addresses-list, implementation-cost HIGH
- `.planning/research/PITFALLS.md` §Pitfall 4 (lines covering pgroup/setsid escape) — `/proc/<runner_pid>/task/*/children` scan recommendation
- `.planning/research/PITFALLS.md` §Pitfall 5 (lines 134-160) — session reaper, cap 8, pager-off (already implemented for r2 in Phase 8; gdb mirrors)
- `.planning/research/PITFALLS.md` §Pitfall 6 (lines 164-181) — gdb pager/confirm-off, MI3 sentinel framing, per-command timeout, refuse interactive prompts
- `.planning/research/PITFALLS.md` §Pitfall 9 (lines 252-275) — per-call `unshare --net --ipc --uts`, no loopback inside netns, sanity-test getaddrinfo returns ENETUNREACH
- `.planning/research/PITFALLS.md` §Pitfall 10 (lines 279-306) — qemu-user binfmt_misc `F` flag, host-side `setup_binfmt.sh` helper, `run_qemu_user` is primary path (explicit `qemu-<arch>-static <sample>`, doesn't rely on binfmt)
- `.planning/research/PITFALLS.md` §Pitfall 11 (lines 310-332) — yama ptrace_scope probe at startup, structured error with `--cap-add=SYS_PTRACE --security-opt apparmor=unconfined` hint
- `.planning/research/PITFALLS.md` §Pitfall 18 — `asyncio.shield(proc.wait())` cancellation pattern (Phase 11 reuses via Phase 9 drain-task)
- `.planning/research/ARCHITECTURE.md` §2.5 "Dynamic-mode gating — at registration time, not call time" — Phase 11 D-DYN-IMPORT-01 implements this exactly
- `.planning/research/ARCHITECTURE.md` §"Anti-Pattern 1: Per-tool environment-variable checks for dynamic mode" — Phase 11 D-DYN-IMPORT-01 implements the recommended alternative
- `.planning/research/ARCHITECTURE.md` §"Phase F: Dynamic-mode surface" — gdb session uses Phase C plumbing (Phase 11 D-01 sessions/ package refactor)
- `.planning/research/STACK.md` — `unshare` is in `util-linux` (Kali base), `qemu-user-static`, gdb MI3 support requires gdb >= 8.3 (Kali ships 13+)
- `.planning/research/FEATURES.md` §"Should have (dynamic-mode bundle)" — env-gate registration, `--network=none`/per-call netns, session-scoped gdb with MI3, sentinel markers, pager-off

### Existing source files (read before writing plans)

- `mcp-gateway/src/mcp_gateway/runner.py` — `ReToolRunner` (Phase 11 doesn't call directly; goes through `jobs.start_tool_job`)
- `mcp-gateway/src/mcp_gateway/jobs.py` — `BackgroundJobRegistry`, `JobToolSpec`, `JOB_TOOL_REGISTRY`, `register_job_tool` (or whatever Phase 9 named the registration function — see code for exact name)
- `mcp-gateway/src/mcp_gateway/sessions.py` — `SessionRegistry`, `R2Session`, `_DANGEROUS_R2_CMD_RE`, env-var constants. Phase 11 D-01 REFACTORS this into a package; the existing file is the "before" state
- `mcp-gateway/src/mcp_gateway/tools/r2_sessions.py` — Phase 8 MCP surface (gdb tools mirror this pattern); receives one-line import update from Phase 11 D-01
- `mcp-gateway/src/mcp_gateway/session_state.py` — `SESSION_REGISTRY` slot (Phase 11 reuses; no new slot needed because gdb sessions live in the same registry per D-02)
- `mcp-gateway/src/mcp_gateway/app.py::lifespan` — Phase 11 D-DYN-CAP-PROBE-01 adds a capability probe call after `register_all_tools`, before `PinnedBackend`
- `mcp-gateway/src/mcp_gateway/tools/__init__.py::register_all_tools` — Phase 11 adds env-gated conditional import + register of `tools/dynamic.py`
- `mcp-gateway/src/mcp_gateway/extraction.py` (Phase 10) — pattern reference for "primitive module registers JobToolSpecs at import"
- `mcp-gateway/src/mcp_gateway/tools/extract.py` (Phase 10) — pattern reference for "MCP surface dispatches via start_tool_job"
- `mcp-gateway/src/mcp_gateway/tools/shell.py` — pattern reference for the `setpriv` UID-drop posture (Phase 11 chooses NOT to setpriv for gdb/strace — they run as `agent` per D-04 / Claude's Discretion)
- `mcp-gateway/src/mcp_gateway/tools/samples.py::resolve_sample` — Phase 11 calls in every `build_*_argv`
- `mcp-gateway/src/mcp_gateway/tools/case_dirs.py::resolve_case_dir` — Phase 11 calls in the MCP-tool handlers before dispatching to JOBS
- `mcp-gateway/src/mcp_gateway/artifacts_io.py` — `EXPANDED_CASE_SUBDIRS` (already contains `dynamic` + `qemu`), `ensure_subdir`, `tool_log_path` (Phase 11 reuses unchanged)
- `mcp-gateway/tests/test_tool_list.py` — `EXPECTED_TOOLS` set (Phase 11 D-DYN-TEST-COUNT parametrizes on env)
- `mcp-gateway/tests/conftest.py` — `_require_r2_or_skip` pattern (Phase 11 adds `_require_gdb_or_skip`, `_require_strace_or_skip`, `_require_qemu_user_or_skip` analogues)
- `run_docker.sh` — `--remote` flag, `MCP_GATEWAY_ENABLED` export, ready-block print, compose env-var passthrough (Phase 11 D-DYN-FLAG-01 follows pattern)
- `compose.yaml` — env-var passthrough mechanism (no edits; `MCP_GATEWAY_DYNAMIC_TOOLS` rides the same passthrough as `MCP_GATEWAY_ENABLED`)
- `Dockerfile` — base apt set; Phase 11 verifies `util-linux` (for `unshare`) and `qemu-user-static` are present; pin explicitly if not
- `scripts/probe_extraction_tools.sh` — pattern reference for the Phase 11 capability-probe equivalent in `scripts/probe_dynamic_tools.sh` (optional operator helper, see Claude's Discretion)

### gdb / strace / qemu reference

- gdb MI3 spec: https://sourceware.org/gdb/current/onlinedocs/gdb.html/GDB_002fMI.html — the MI3 record format and prefix listing (Phase 11 D-07 allowlist references)
- strace manpage — `-f`, `-e trace=<set>`, `-o`, `-c` flags (Phase 11 D-DYN-PROF-01 profile mappings)
- ltrace manpage — `-f`, `-S`, `-l`, `-c` flags
- qemu-user manpage — `-strace`, `-singlestep`, `-d <items>`, `-cpu <model>` flags; binfmt registration requirements
- yama ptrace_scope docs: https://www.kernel.org/doc/Documentation/security/Yama.txt — `0`/`1`/`2`/`3` semantics (Phase 11 D-DYN-CAP-PROBE-01 reports the value; tools surface actionable hints)
- binfmt_misc docs: https://docs.kernel.org/admin-guide/binfmt-misc.html — `F` flag semantics for cross-mount-namespace registration (Pitfall 10)

### Constraint references

- `CLAUDE.md` §Constraints — container runs with `SYS_PTRACE` + `seccomp=unconfined` (Phase 11 relies on this; the capability probe verifies actual ability, not just declared cap)
- `CLAUDE.md` §"Recommended Stack > Authentication & Security" — Bearer token model; gdb-session SESS-05-style sharing across bearer-token clients (D-DYN-TOOL-02 disclaimer covers)
- `.planning/REQUIREMENTS.md` §"Out of Scope (v1.1)" — mount-ns isolation deferred, `allow_network=true` deferred, sandboxed-network deferred, full-VM deferred, batch-only gdb rejected

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets

- **`mcp_gateway.runner.ReToolRunner` + 12-key result dict (Phase 6 D-03)** — Phase 11's gdb_exec result layers on this exact shape (D-08). Trace tools (strace/ltrace/qemu_user) don't call ReToolRunner directly; they go through `start_tool_job` which wraps it internally.
- **`mcp_gateway.jobs.BackgroundJobRegistry` + `JobToolSpec` (Phase 9)** — Phase 11's 3 trace tools register `JobToolSpec` entries; the registry handles spawn / drain / log-cap / cancel / progress / snapshot uniformly.
- **`mcp_gateway.sessions.SessionRegistry` (Phase 8)** — refactored to `sessions/_base.py` in D-01; one registry now manages BOTH r2 and gdb session kinds via a `kind` discriminator. Same cap (8), same idle (1800 s), same reaper.
- **`mcp_gateway.sessions.R2Session` (Phase 8)** — moved to `sessions/r2.py`; `GdbSession` is the parallel new class in `sessions/gdb.py`. Both subclass `BaseSession`.
- **`mcp_gateway.sessions._DANGEROUS_R2_CMD_RE` (Phase 8)** — Phase 11 D-07 mirrors with `_ALLOWED_MI_PREFIXES` (positive allowlist) + `_DANGEROUS_GDB_RE` (negative deny-list, belt + braces).
- **`mcp_gateway.artifacts_io.{confine_to, ensure_subdir, tool_log_path, EXPANDED_CASE_SUBDIRS}`** — Phase 11 reuses unchanged. `EXPANDED_CASE_SUBDIRS` already contains `dynamic` + `qemu`.
- **`mcp_gateway.tools.case_dirs.resolve_case_dir` + `mcp_gateway.tools.samples.resolve_sample`** — Phase 11's MCP handlers call these as the first step (same convention as every Phase 7+ wrapper).
- **`mcp_gateway.session_state.SESSION_REGISTRY` (Phase 8 D-07)** — Phase 11 reuses this slot for gdb sessions (no new slot). The registry knows about both kinds.
- **`mcp_gateway.tools.shell._build_setpriv_argv` (Phase 7)** — pattern reference for argv-wrapping (Phase 11's `wrap_netns` is the analogous primitive for netns). Phase 11 chooses NOT to setpriv to mare-shell for gdb/strace because they need `SYS_PTRACE`; the netns wrap is the structural isolation.
- **`mcp_gateway.app.py::lifespan` PinnedBackend > SessionRegistry > BackgroundJobRegistry nesting** — Phase 11 doesn't change this; capability probe runs BEFORE entering PinnedBackend (one-shot, no lifespan).

### Established patterns

- **Primitive + tools/ surface split** — Phase 11 follows: `dynamic.py` + `sessions/gdb.py` are primitives; `tools/dynamic.py` is the MCP surface.
- **Async-context-manager registry owned by `app.py::lifespan`** — Phase 11 reuses Phase 8's `SessionRegistry`, no new registry.
- **Module-level env-var constants validated at import** — Phase 11 D-DYN-ENV-01 follows.
- **Structured error dicts, never raise out of MCP tools** — Phase 11 D-DYN-CAP-PROBE-02 returns `{error, missing, hint}` on capability-missing.
- **Layer onto Phase 6's 12-key result dict** — Phase 11 D-08 follows for gdb_exec.
- **Docstring disclaimer for cross-cutting limitations** — Phase 11 D-DYN-TOOL-02 follows, regression-tested.
- **Conditional registration in `tools/__init__.py`** — Phase 11 introduces this pattern (env-gate). Future phases that add gated surfaces follow.
- **Argv-prefix wrapping for sandbox posture** — Phase 7's `setpriv` prefix for `run_shell`; Phase 11's `unshare --net` prefix for every dynamic-mode subprocess. Same compositional pattern.
- **Capability probe at startup, surfaced via tool** — NEW pattern in Phase 11. `get_dynamic_capabilities()` is the discovery surface; tools consult `dynamic.CAPABILITIES` at call time.
- **Tool-name registration order matters for collision_check** — Phase 11 tools register AFTER all v1.0/Phase 7-10 tools (alphabetical within the conditional block); collision_check at lifespan startup ensures no overlap with backend pass-through.

### Integration points

- `tools/__init__.py::register_all_tools` — one conditional import block:
  ```python
  if os.environ.get("MCP_GATEWAY_DYNAMIC_TOOLS") == "1":
      from . import dynamic as dynamic_tools
      dynamic_tools.register(mcp)
  ```
  Placed AFTER `jobs.register(mcp)` (so dynamic JobToolSpecs are registered into a populated `JOB_TOOL_REGISTRY`) and BEFORE `backend_passthrough.register(mcp)` (the Phase 7 D-14 ordering).
- `app.py::lifespan` — one new line BEFORE the `if backend_name is None:` branch:
  ```python
  dynamic.CAPABILITIES = dynamic.probe_all()  # never raises; populates module slot
  log_dynamic_probe_result(dynamic.CAPABILITIES)  # WARN log lines per D-DYN-PROBE-LOG
  ```
  Runs unconditionally (both branches) so `get_dynamic_capabilities()` works even when dynamic tools aren't registered.
- `session_state.py` — NO new slot. `SESSION_REGISTRY` (Phase 8 D-07) now manages both kinds.
- `sessions.py` — DELETED, replaced by `sessions/` package per D-01. All Phase 8/9 callers continue to work via re-export.
- `jobs.py::JOB_TOOL_REGISTRY` — 3 new entries when dynamic mode is on, 0 when off (specs are registered from `dynamic.py` at its import time).
- `run_docker.sh` — one new flag (`--dynamic`), one new env-var export, two new lines in the docker-compose passthrough, ~5 new lines in the usage banner / ready-block.
- `Dockerfile` — verify `util-linux` + `qemu-user-static` present; explicit `apt-get install --no-install-recommends` line for both even if redundant with the Kali base (defense-in-depth against base-image churn). One new test (`scripts/probe_dynamic_tools.sh` analogue to Phase 10's probe script, optional).
- `tools/r2_sessions.py` — one-line import update (`from mcp_gateway import sessions` continues to work via package re-export; ideally NO change needed if Phase 8's import uses the re-exported symbols).
- `compose.yaml` — NO change. Env-var passthrough is generic.
- `mcp-gateway/pyproject.toml` — NO new pip deps. `unshare`, `gdb`, `strace`, `ltrace`, `qemu-user-static` are all apt-provided. (Python-level gdb-MI parsing is best-effort in our own code; pygdbmi is mentioned in research but the line-by-line MI parser is simple enough to write directly per D-08.)

</code_context>

<specifics>
## Specific Ideas

- User mandate at discuss-phase (consistent with all prior v1.1 phases):
  "Choose the most robust, common-sensical, and feature-rich option for
  all questions." Every locked decision above is the most-robust default
  under that mandate; the planner/executor may adjust within the
  constraints listed under "Claude's Discretion" but not the locked
  decisions.
- Defense-in-depth carried forward across the entire dynamic surface:
  per-call `unshare --net --ipc --uts` (D-DYN-NET-01) on top of the
  Phase 6 D-17 process-group cleanup, ON TOP OF strict MI3 allowlist
  for gdb (D-07) AND a deny-regex belt-and-braces (D-07), ON TOP OF
  follow-fork stray reaping (D-DYN-JOB-03). Each layer covers a
  different failure mode; none is sufficient alone.
- The sessions/ package refactor (D-01) is "rename-only" per Phase 8
  D-05's exact wording. Phase 8's test suite SHOULD continue to pass
  bit-for-bit after the refactor. Any test failure during the
  refactor is a Phase 11 regression, not a Phase 8 fragility.
- One shared SessionRegistry across r2 + gdb (D-02) means the cap-8
  limit is the COMBINED count. An operator who runs 5 r2 sessions
  then opens 3 gdb sessions hits the cap. The cap-reach error dict
  shows `existing: [<r2 sessions>, <gdb sessions>]` with `kind` per
  entry so the operator can decide which to close.
- gdb MI3 was chosen over MI2 because MI3 (gdb 9+) added structured
  output for `-data-evaluate-expression` and stabilized the record
  format. Kali ships gdb 13+. Pin to MI3 explicitly in the argv
  (`--interpreter=mi3`); MI2 is not a fallback.
- The strict MI prefix allowlist (D-07) is consciously conservative —
  some MI commands an analyst might want (e.g., `-environment-cd`)
  are NOT included. The orchestrator can wrap CLI-style intent into
  allowlisted MI prefixes (e.g., "look at this struct" becomes
  `-var-create + -var-list-children`). Adding more prefixes is a
  one-line CONTEXT update + tests, but each addition is a deliberate
  posture choice, not a casual extension.
- `run_qemu_user` is the EXPLICIT path for foreign-arch sample
  execution (Pitfall 10 mandate). `run_shell("./mips_sample")`
  works only if the operator has set up binfmt_misc with the `F`
  flag on the host, AND the container can see the registrations.
  Phase 11 doesn't try to be clever about binfmt — if the agent
  wants cross-arch, they call `run_qemu_user(arch="mips", ...)`
  explicitly. `get_dynamic_capabilities().qemu_architectures` is
  the discovery surface.
- Capability probe runs unconditionally (both backend branches,
  both dynamic-on/off) so `get_dynamic_capabilities()` always works.
  The probe is <200 ms total (5 sub-probes, each <100 ms typical),
  acceptable startup cost. Hosts without `util-linux` will fail the
  netns probe — operator sees a clear WARN line and knows what's
  wrong.
- The `--dynamic` flag requires `--remote` (D-DYN-FLAG-01) because
  dynamic tools are exclusively an MCP surface — there is no
  in-container agent path that calls them directly. The hard-error
  surfaces this clearly; a "silent acceptance + no effect" would
  confuse operators.
- Phase 12's orchestrator-skill update consumes
  `get_dynamic_capabilities()` and writes the result into each case's
  `CURRENT_STATE.json`. Phase 11 does NOT touch workspace skill
  files. This split keeps Phase 11 "additive to the gateway, zero
  edits to v1.0 surfaces outside the gateway" per ARCHITECTURE.md.
- All trace tools go through JOBS even for short traces
  (D-DYN-DISPATCH-01). The orchestrator can poll at 250 ms intervals
  for near-sync feel; the alternative (`wait=True` sync path) would
  bypass log-cap / cancel / retention / progress, which is more
  fragile than worth the ergonomic shortcut.

</specifics>

<deferred>
## Deferred Ideas

- **`allow_network=True` per-call opt-in** — REQUIREMENTS Out of Scope
  for v1.1. v1.2 adds INetSim/FakeDNS/honeynet integration with
  per-call opt-in.
- **Mount-namespace isolation for dynamic subprocesses** — REQUIREMENTS
  Out of Scope (CAP_SYS_ADMIN cost; posture-only via `unshare --mount`
  was considered but rejected here because it conflicts with
  `confine_to`-based path-traversal guarding that ASSUMES the case
  dir is reachable). v1.2 may revisit.
- **Coverage-guided dynamic (afl/libFuzzer hooks)** — REQUIREMENTS
  Out of Scope. v1.2+ if a real fuzzing workflow emerges.
- **Memory snapshot tooling (Volatility integration)** — REQUIREMENTS
  Out of Scope.
- **Full-VM / kernel-mode dynamic** — REQUIREMENTS Out of Scope (the
  v1.1 dynamic model is user-mode only).
- **Per-`Mcp-Session-Id` keying of gdb sessions and dynamic jobs** —
  Phase 8 SESS-05 / Phase 9 D-26 deferred this gateway-wide to v1.2.
  Phase 11's gdb tools inherit the same disclaimer (D-DYN-TOOL-02).
- **`job_specs/` package refactor** — Phase 9 / Phase 10 deferred it
  until needed; Phase 11 brings spec count to 6 but the per-owner-
  module-registers-its-specs pattern still works and supports the
  env-gate cleanly (dynamic specs disappear when off). Refactor when
  ~10+ specs or when cross-spec sharing becomes painful.
- **CLI-mode gdb support** — explicitly rejected (D-04, D-07); MI3 is
  the only supported interface for posture/framing reasons. The
  orchestrator skill maps analyst CLI-style intent ("set breakpoint
  at main") to MI commands ("-break-insert main").
- **Auto-registering binfmt_misc handlers from inside the container** —
  rejected (Pitfall 10); requires `--privileged`, breaks the default
  posture. Host-side setup script is a Phase 12 documentation item.
- **Persistent named netns at gateway start** — rejected (D-DYN-NET-01)
  in favor of per-call `unshare`. v1.2+ could reconsider if loopback
  inside the netns becomes useful (e.g., for INetSim integration where
  fake services bind on loopback).
- **`run_strings` over dynamic-mode outputs** — out of scope per
  REQUIREMENTS; v1.0 `collect_strings` and `run_shell` cover this.
- **CLI-mode shell escape via `python` / `source` / `!` in gdb** —
  explicitly hard-blocked (D-07 deny-regex + allowlist refusal). This
  is a posture lock, not deferred.
- **Sandboxed sample-execution with kernel-mode trace (eBPF/bpftrace)** —
  out of scope; user-mode strace is the v1.1 trace mechanism.
- **Replay-from-trace (rr, gdb record)** — out of scope; v1.2+ if
  reverse-debugging workflows emerge.
- **Per-`Mcp-Session-Id`-scoped dynamic capabilities** — capabilities
  are container-wide (host-namespace-controlled); per-session keying
  doesn't apply.

### Reviewed Todos (not folded)

None matched Phase 11 scope outside what's already captured (the
STATE.md "Pending Todos" entries about per-call netns mechanism,
ptrace probe error UX, gdb MI3 allowlist, and binfmt detection helper
are all LOCKED in this CONTEXT as D-DYN-NET-01, D-DYN-CAP-PROBE-02,
D-07, D-DYN-CAP-PROBE-01 respectively — folded, not deferred).

</deferred>

---

*Phase: 11-dynamic-lab-mode-env-gated*
*Context gathered: 2026-05-19*
