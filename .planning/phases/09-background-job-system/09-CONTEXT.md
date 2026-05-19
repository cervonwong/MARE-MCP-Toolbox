# Phase 9: Background Job System - Context

**Gathered:** 2026-05-19
**Status:** Ready for planning

<domain>
## Phase Boundary

Add an asynchronous, long-running-tool execution surface to the gateway so
remote agents can launch tools that exceed MCP's effective 60-second
per-request cap (capa, unblob, Ghidra/IDA auto-analysis, strace, qemu-user,
binwalk-extract) and poll for completion without holding an MCP request
open.

Scope:

- `mcp-gateway/src/mcp_gateway/jobs.py` — primitive layer. Public surface:
  `BackgroundJobRegistry` (async-context-manager), `Job` dataclass,
  `JobToolSpec` registration record, `JOB_TOOL_REGISTRY` module-level
  mapping, `JobCapReached` / `JobNotFound` error dataclasses, ~6 env-var
  module constants. Mirrors the `runner.py` / `sessions.py` primitive
  pattern.
- `mcp-gateway/src/mcp_gateway/tools/jobs.py` — MCP surface. Four
  MCP-registered tools: `start_tool_job`, `get_tool_job`,
  `cancel_tool_job`, `list_tool_jobs`. Mirrors the `tools/r2_sessions.py`
  pattern.
- Extensions to existing modules:
  - `mcp-gateway/src/mcp_gateway/session_state.py` gains one
    `Optional[BackgroundJobRegistry]` slot
    (`session_state.JOB_REGISTRY`) — same pattern as `PINNED_BACKEND`
    (v1.0) and `SESSION_REGISTRY` (Phase 8 D-07).
  - `mcp-gateway/src/mcp_gateway/tools/__init__.py::register_all_tools`
    gains one import + one register call for `tools/jobs.py`.
  - `mcp-gateway/src/mcp_gateway/app.py::lifespan` gains one
    `async with BackgroundJobRegistry(...)` block in BOTH the
    no-backend and real-backend branches, nested INSIDE the existing
    `SessionRegistry` block (LIFO unwind: jobs killed → sessions
    killed → backend torn down).
  - `mcp-gateway/src/mcp_gateway/artifacts_io.py::EXPANDED_CASE_SUBDIRS`
    grows by zero entries — job logs reuse the existing `tool-logs/`
    directory established in Phase 7 D-09 (no new top-level case-dir
    subdir). Job-specific *snapshot* artifacts (kwargs echo, final
    result dict) live alongside the log as `tool-logs/<ts>-<slug>-<rand4>.json`.

Explicitly NOT in this phase:

- Phase 10/11 tools that *consume* the JOB system. Phase 9 ships the
  registry, the four MCP tools, AND a `JOB_TOOL_REGISTRY` with a small
  initial set of pluggable tool specs that proves the surface works
  end-to-end. Phase 10 adds extraction-tool specs; Phase 11 adds
  dynamic-tool specs. The initial Phase 9 spec set is deliberately
  minimal — see D-04 below.
- Persistent (across-restart) job state — JOBS-04 explicitly says
  "in-memory only, gateway restart cancels in-flight jobs." Persisting
  to disk is a v1.2 concern; Phase 9 documents the in-memory limitation
  in every job-tool docstring.
- Per-`Mcp-Session-Id` keying of jobs — jobs are shared across all
  bearer-token clients, identical to Phase 8 sessions (SESS-05).
  Documented in every job-tool docstring.
- Cross-job dependencies / DAG orchestration — agents compose by
  polling job A, then calling `start_tool_job` for job B; no
  gateway-side dependency graph.
- A separate `jobs/` MCP Resource walker — job logs are already
  exposed via the Phase 7 D-26 walker at depth ≤ 2 because they live
  under `tool-logs/`. Listing of jobs is via `list_tool_jobs`, not
  Resources.
- Refactoring `runner.py` to internally call into a job manager — the
  synchronous `run_tool(...)` Phase 6 D-02 convenience helper remains
  the API for tools that fit in the 60s budget. Jobs are a separate
  surface for tools that do not.

</domain>

<decisions>
## Implementation Decisions

### Dispatch surface (Area 1)

- **D-01:** `start_tool_job(tool: str, kwargs: dict, *, case_dir: str,
  timeout: float | None = None) -> dict` accepts a tool *name* string
  resolved against a module-level `JOB_TOOL_REGISTRY`, NOT a raw argv
  list. The registry maps `name -> JobToolSpec`. This satisfies
  JOBS-01's literal phrasing (`start_tool_job(tool, args)`) and lets
  Phase 10/11 plug in by registration rather than by knowing
  ReToolRunner internals.

  *Rationale:* An allowlist registry is the safe shape. A raw-argv
  surface would let an agent background `rm -rf /`, defeating the
  Phase 6 D-01 "argv-only, never shell" guarantee on the chokepoint.
  A registry also gives us a natural home for per-tool overrides
  (default timeout, progress parser, slug, kwargs schema).

- **D-02:** `JobToolSpec` is a frozen dataclass with this shape:

  ```python
  @dataclasses.dataclass(frozen=True)
  class JobToolSpec:
      name: str                                          # registry key, e.g. "unblob"
      slug: str                                          # ReToolRunner slug, usually == name
      build_argv: Callable[[Path, dict], list[str]]      # (case_dir, kwargs) -> argv
      default_timeout_s: float                           # per-tool default; honors D-12
      progress_parser: Callable[[bytes], tuple[int, int, str] | None] | None
      kwargs_schema: dict | None                         # JSON-schema-style dict; None = no validation
      description: str                                   # surfaced in list_tool_jobs help
  ```

  `build_argv` returns the argv list ReToolRunner will spawn. It is
  pure — no side effects, no I/O — so Phase 10 can unit-test the
  argv build without spawning processes. The registry function
  `register_job_tool(spec: JobToolSpec)` is called at Phase 10/11
  module-import time, parallel to FastMCP's `@mcp.tool()` decorator
  pattern.

- **D-03:** Phase 9 ships the registry empty by default, but ships
  ONE end-to-end smoke tool inside `jobs.py` itself to prove the
  surface works without a Phase 10/11 dependency:

  ```python
  # jobs.py module-level spec used by tests + as live smoke
  _SLEEP_PROBE_SPEC = JobToolSpec(
      name="_sleep_probe",
      slug="sleep_probe",
      build_argv=lambda case_dir, kw: ["sleep", str(int(kw.get("seconds", 1)))],
      default_timeout_s=300.0,
      progress_parser=None,
      kwargs_schema={"seconds": {"type": "integer", "min": 0, "max": 600}},
      description="Internal probe — sleeps N seconds. Used for plumbing tests.",
  )
  ```

  The underscore prefix marks it as internal. Phase 10/11 register
  real tools (`unblob`, `binwalk_extract`, `ghidra_analyze`, `capa`,
  `strace`, `ltrace`, `qemu_user`) with full progress parsers. The
  probe ensures Phase 9 itself does not need Phase 10 to demonstrate
  SC-1..SC-6.

- **D-04:** **Phase 9 ships exactly one user-visible tool spec**:
  `capa` (capa is already in the Kali container; capa runs static
  analysis that routinely takes 60-300s on real samples — the
  canonical phase-9-only motivator). This:
  (a) proves the registration pattern works for a real Kali tool,
  (b) gives Phase 9 a non-trivial integration test (`pytest -m slow`
      capa-on-a-known-good-binary, gated behind capa-availability
      check),
  (c) does NOT depend on Phase 10's `unblob`/`binwalk` extraction or
      Phase 11's dynamic mode, both of which add their own
      `JobToolSpec` registrations in their respective phases.

  `capa`'s spec lives in `jobs.py` directly for Phase 9 (not in a
  separate `tools/job_specs/` package) — a `job_specs/` package
  shape is appropriate when there are 5+ specs (Phase 10/11 will
  refactor at that point), not yet.

- **D-05:** `start_tool_job` signature, locked:

  ```python
  async def start_tool_job(
      tool: str,
      kwargs: dict,
      *,
      case_dir: str,
      timeout: float | None = None,
      ctx: Context | None = None,
  ) -> dict
  ```

  Returns immediately with a snapshot dict (D-19 shape) where
  `status == "pending"` (briefly, until the spawn task picks it up
  on the next event-loop tick) or `status == "running"` if the spawn
  has already begun. NEVER awaits subprocess completion.

  Argument resolution order:
  1. Validate `tool` is in `JOB_TOOL_REGISTRY` (else `JobNotFound`).
  2. Validate `kwargs` against `spec.kwargs_schema` if non-None (else
     `ValueError` with the failing field name).
  3. Resolve `case_dir` via the existing `tools/case_dirs.resolve_case_dir`
     helper (Phase 7 convention — same as every typed wrapper).
  4. Resolve effective timeout: caller `timeout` > `spec.default_timeout_s`
     > `MCP_GATEWAY_JOB_TIMEOUT_S` (default 3600.0). Capped at
     `MCP_GATEWAY_JOB_MAX_TIMEOUT_S` (default 86400.0). Negative or
     zero → `ValueError`.
  5. Check `len(registry.inflight) < MAX_JOBS_INFLIGHT`; cap-reach
     returns the D-15 cap-error dict (no queueing — see D-15).
  6. Generate `job_id` = `secrets.token_hex(8)` (16 lowercase hex).
  7. Create `Job(...)`, add to registry, schedule
     `asyncio.create_task(registry._spawn_and_drive(job))`, return
     snapshot.

### Job lifecycle (Area 3)

- **D-06:** Status vocabulary (7-state, terminal states are
  immutable once set):

  ```python
  JobStatus = Literal[
      "pending",          # registered, asyncio task not yet picked up
      "running",          # subprocess spawned, drain loop active
      "succeeded",        # exit_code == 0, no kill
      "failed",           # exit_code != 0, no kill (tool returned error)
      "cancelled",        # cancel_tool_job called
      "killed_timeout",   # job-level hard timeout fired
      "killed_log_cap",   # MCP_GATEWAY_MAX_JOB_LOG_MB exceeded
  ]
  ```

  Terminal states: `succeeded`, `failed`, `cancelled`,
  `killed_timeout`, `killed_log_cap`. Once a job enters a terminal
  state, its `status` field never mutates again — this is the
  invariant `get_tool_job`/`list_tool_jobs` rely on for
  cheap-to-serialize snapshots without locking.

  `failed` is distinct from the `killed_*` states because tool exit
  codes (e.g., capa exiting 1 on parse error) are meaningful and
  agents should be able to discriminate "the tool ran but said no"
  from "we killed it before it finished."

- **D-07:** Cancellation timing: SIGTERM then SIGKILL with a grace
  period. `cancel_tool_job(job_id)`:

  ```python
  async def cancel(job: Job) -> None:
      if job.status not in ("pending", "running"):
          return  # idempotent no-op on terminal jobs
      job._cancel_requested = True
      os.killpg(job.pgid, signal.SIGTERM)
      try:
          await asyncio.wait_for(job.proc.wait(), timeout=JOB_CANCEL_GRACE_S)
      except asyncio.TimeoutError:
          os.killpg(job.pgid, signal.SIGKILL)
          await job.proc.wait()
      # drain loop sets status=cancelled on _cancel_requested=True at finally
  ```

  Default grace: `MCP_GATEWAY_JOB_CANCEL_GRACE_S = 10.0`. Phase 8's
  session shutdown used immediate killpg-SIGKILL because r2 has no
  flush-on-SIGTERM behavior worth preserving; jobs may be tools
  that write final output files on SIGTERM (capa flushes its
  JSON-on-completion path), so a 10s grace is the common-sense
  choice. Env-overridable.

- **D-08:** Job hard-timeout enforcement. ReToolRunner already has a
  per-call hard timeout (Phase 6 D-04), but the job-level timeout
  may be MUCH longer (1h default vs the 60s default ReToolRunner
  uses). The job wraps ReToolRunner with `RUNNER_TIMEOUT_S = None`
  (Phase 6 D-04 supports `timeout=None` for unbounded) and enforces
  its own timeout via an `asyncio.wait_for(...)` around the drain
  loop. On timeout: same SIGTERM-grace-SIGKILL ladder as D-07, then
  `status="killed_timeout"`. This composition is intentional: jobs
  get the runner's argv-only / process-group / capture guarantees
  WITHOUT the runner's short-timeout semantics, which are wrong for
  jobs.

- **D-09:** Log cap enforcement. Counter-based, in the drain loop
  (NOT periodic stat):

  ```python
  # inside the per-line drain
  async def _drain(stream, role: str):
      while True:
          line = await stream.readline()
          if not line:
              return
          job.log_bytes_written += len(line)
          if job.log_bytes_written > MAX_JOB_LOG_BYTES:
              job._log_cap_exceeded = True
              os.killpg(job.pgid, signal.SIGKILL)  # immediate, no grace
              # write a final marker line
              await _append_log(job.log_path, b"\n=== MARE_JOB_KILLED_LOG_CAP ===\n")
              return
          await _append_log(job.log_path, line)
          if role == "stdout" and len(job.stdout_head) < HEAD_CAP:
              job.stdout_head += line.decode(errors="replace")
          # ... (analogous for stderr)
  ```

  `MAX_JOB_LOG_BYTES = MCP_GATEWAY_MAX_JOB_LOG_MB * 1024 * 1024`,
  default `256 * 1024 * 1024`. Counter-based avoids the
  periodic-stat race where a tool bursts 1 GB between checks and
  the cap is effectively meaningless. Kill is immediate SIGKILL
  (no SIGTERM grace) on cap-exceed — the tool is, by definition,
  pathologically loud and there is nothing to preserve. Status
  becomes `killed_log_cap` on drain-finally.

  Stdout and stderr share the cap (combined). Two separate caps
  would let an agent dodge the cap by splitting output.

- **D-10:** LRU retention. The registry caps completed jobs at
  `MCP_GATEWAY_MAX_COMPLETED_JOBS` (default `200`). On 201st
  completion, the oldest-completed entry is evicted from the
  registry. Eviction policy:

  - Eviction is age-based (oldest `ended_at` first), not
    access-based — strictly speaking FIFO-of-completed not LRU. JOBS-05
    says "LRU" but the spirit is "bound memory"; pure FIFO is simpler
    to reason about and matches what an agent intuits ("old jobs go
    away"). Documented as such in `BackgroundJobRegistry` docstring.
  - The on-disk log file (`tool-logs/<ts>-<slug>-<rand4>.txt`) is
    **preserved**, not deleted. Logs are MCP Resources via Phase 7
    D-26 and are part of the case-dir audit trail; deleting them on
    eviction would silently destroy evidence and break the
    `tool-logs/` invariant other phases depend on.
  - `get_tool_job(evicted_id)` returns the D-15 `JobNotFound` error
    dict: `{error: "job not found (evicted from in-memory registry; gateway restart also evicts)", job_id: ..., hint: "browse tool-logs/ via Resources to inspect the log"}`.
  - In-flight jobs are never evicted (cap applies to terminal jobs
    only).

- **D-11:** Concurrency cap: `MCP_GATEWAY_MAX_JOBS_INFLIGHT`,
  default `4`. Jobs are MUCH heavier than r2 sessions (capa pegs a
  CPU core; unblob can use multi-GB scratch space), so the cap is
  lower than Phase 8's session cap of 8. Cap-reach behavior: NO
  queueing. `start_tool_job` returns a `JobCapReached`-shaped error
  dict (D-15) and the agent re-tries explicitly. This matches Phase
  8 D-18's session-cap behavior exactly — uniformity over
  implicit-queue ergonomics, because hidden queues create
  head-of-line surprises that are very hard to debug remotely.

- **D-12:** Effective-timeout resolution (per-call):

  ```
  effective = (
      timeout                         # caller param, if not None
      or spec.default_timeout_s       # per-tool default
      or JOB_TIMEOUT_S                # env-var default (3600.0)
  )
  effective = min(effective, JOB_MAX_TIMEOUT_S)  # 86400.0 hard cap
  ```

  `JOB_MAX_TIMEOUT_S` is a defense-in-depth ceiling against agents
  passing `timeout=10**9`. 24h is the documented ceiling per the
  v1.1 README orchestration timing.

- **D-13:** Env-var module constants, read ONCE at `jobs.py` import
  (matches Phase 8 D-14 / Phase 6 D-08 pattern, same `_env_float` /
  `_env_int` helpers — either imported from `sessions.py` if Phase 8
  exports them or inlined):

  ```python
  JOB_TIMEOUT_S      = _env_float("MCP_GATEWAY_JOB_TIMEOUT_S",      3600.0)
  JOB_MAX_TIMEOUT_S  = _env_float("MCP_GATEWAY_JOB_MAX_TIMEOUT_S",  86400.0)
  JOB_CANCEL_GRACE_S = _env_float("MCP_GATEWAY_JOB_CANCEL_GRACE_S", 10.0)
  MAX_JOB_LOG_MB     = _env_int(  "MCP_GATEWAY_MAX_JOB_LOG_MB",     256)
  MAX_JOBS_INFLIGHT  = _env_int(  "MCP_GATEWAY_MAX_JOBS_INFLIGHT",  4)
  MAX_COMPLETED_JOBS = _env_int(  "MCP_GATEWAY_MAX_COMPLETED_JOBS", 200)
  ```

  Bad values raise `RuntimeError` at import (NOT at first call —
  same fail-fast contract as Phase 6/8).

### Registry shape & lifecycle ownership

- **D-14:** `BackgroundJobRegistry` is an async-context-manager
  (matching Phase 8 D-16's `SessionRegistry` pattern). `__aenter__`
  initializes empty dicts; `__aexit__` cancels every in-flight job
  in parallel (`asyncio.gather(*[reg.cancel(j) for j in inflight], return_exceptions=True)`)
  with the SIGTERM-grace-SIGKILL ladder, then waits for every job's
  drain task. On shutdown, no LRU eviction occurs — terminal jobs
  are simply lost (in-memory contract, JOBS-04).

  Internal state:

  ```python
  class BackgroundJobRegistry:
      _inflight: dict[str, Job]    # job_id -> Job in pending/running
      _completed: collections.OrderedDict[str, Job]  # FIFO for eviction
      _lock: asyncio.Lock          # guards add/move-to-completed/evict
  ```

  The lock protects only state-machine transitions (add to inflight,
  move from inflight to completed, evict from completed). It does
  NOT protect drain — each job owns its own drain task and its own
  log file. The lock is therefore never held during subprocess I/O,
  which would create cross-job head-of-line blocking.

- **D-15:** Structured error dicts (returned by tool surface, NOT
  raised; matches Phase 6 D-04 / Phase 8 D-18 "never raises"
  contract):

  ```python
  # cap-reached on start_tool_job
  {"error": "job cap reached",
   "inflight": int, "cap": int,
   "hint": "wait for an inflight job to complete or cancel one"}

  # tool name not registered
  {"error": "unknown job tool",
   "tool": str, "known": list[str],
   "hint": "see list_tool_jobs(filter='_specs') or job tool docstrings"}

  # job_id not found (evicted or never existed)
  {"error": "job not found (evicted from in-memory registry; gateway restart also evicts)",
   "job_id": str,
   "hint": "browse tool-logs/ via Resources to inspect the log"}

  # kwargs validation failed
  {"error": "invalid kwargs",
   "field": str, "expected": str, "got": str}
  ```

  Every MCP tool returns one of these error dict shapes or a
  success snapshot (D-19) — never both, never a Python exception
  bubbling out.

### Progress reporting (Area 2 — JOBS-07)

- **D-16:** Two-tier progress model:

  **Tier 1: Job-side capture.** Each `JobToolSpec` may carry a
  `progress_parser: Callable[[bytes], tuple[int, int, str] | None]`.
  The drain loop calls `spec.progress_parser(line)` on every stderr
  line. When it returns `(current, total, message)`, the job's
  `progress`, `progress_total`, `progress_message` fields update
  (locklessly — single-writer, multi-reader).

  **Tier 2: Poll-side push.** When `get_tool_job(job_id, ctx)` is
  called with `ctx: Context` (FastMCP injects it automatically),
  the handler checks if `job.progress is not None` AND if it has
  changed since the last call from this `ctx.session_id` (tracked
  via `job._last_reported_to: dict[str, tuple[int, int]]`). If so,
  it calls `await ctx.report_progress(current, total, message)`
  BEFORE returning the snapshot. The poller's MCP request gets a
  progress notification.

  *Rationale:* The fundamental tension is that MCP progress
  notifications are per-request, but jobs outlive requests. The
  resolution is "progress is repaint-on-poll" — agents that don't
  care never receive notifications, agents that poll get a
  notification each time they poll a job that has made progress
  since their last poll. This is simple, idempotent, and requires
  no server-push session bookkeeping.

  Tier-1-only fallback: if `ctx` is None (programmatic call,
  pre-Phase-10 unit test), Tier 2 is skipped silently. The `progress`
  fields are still present in the snapshot dict regardless.

- **D-17:** Initial progress parsers ship with Phase 9 for capa
  only (D-04). The capa parser handles capa's
  `[INFO] processing N/M ...` progress lines (capa's actual
  progress emission format — verify in research phase against
  capa's --help and stderr output). If capa's stderr is silent
  (capa emits progress only to stdout JSON), the parser is None
  and Phase 9 ships with `progress: None` for capa — that's
  acceptable; JOBS-07 says progress is supported "where the tool
  can produce progress signals," not "for every tool." Phase 10
  registers unblob's parser; Phase 11 registers strace/qemu
  parsers if they emit any.

- **D-18:** Progress field shape. Always three fields in the
  snapshot, always all-None or all-Some (no partial states):

  ```python
  "progress":         int | None,   # current step
  "progress_total":   int | None,   # total steps; may be 0 if unknown
  "progress_message": str | None,   # last parsed message, truncated to 200 chars
  ```

  Message truncation matches MCP notification size budgets
  (Anthropic's MCP spec recommends ≤256 bytes for progress
  messages). 200 chars is conservatively safe under UTF-8.

### get_tool_job result shape (Area 4)

- **D-19:** The job snapshot result dict, locked, layered onto
  Phase 6 D-03's 12 keys (matches the Phase 8 D-11 layering
  precedent):

  ```python
  {
      # ---- Phase 6 D-03's 12 keys, sentinel-valued while non-terminal ----
      "exit_code": int,           # -1 while running; final code at terminal
      "timed_out": bool,          # true iff status == "killed_timeout"
      "duration_s": float,        # so-far if running, final if terminal
      "stdout_head": str,         # first JOB_STDOUT_HEAD_KB (default 32 KB)
      "stdout_truncated": bool,   # true iff total > head cap
      "stdout_bytes_total": int,
      "stderr_head": str,
      "stderr_truncated": bool,
      "stderr_bytes_total": int,
      "log_path": str,            # case-rel: tool-logs/<ts>-<slug>-<rand4>.txt
      "argv": list[str],          # as executed
      "slug": str,                # spec.slug

      # ---- Phase 9 extensions ----
      "job_id": str,                                       # 16-hex
      "tool": str,                                         # spec.name
      "status": JobStatus,                                 # D-06
      "started_at": str,                                   # ISO8601 Z
      "ended_at": str | None,                              # ISO8601 Z if terminal
      "stdout_tail": str,                                  # last JOB_STDOUT_TAIL_KB
      "stderr_tail": str,                                  # last JOB_STDERR_TAIL_KB
      "progress": int | None,                              # D-18
      "progress_total": int | None,
      "progress_message": str | None,
      "kwargs": dict,                                      # echo of caller's kwargs
      "case_dir": str,                                     # case-rel root
      "effective_timeout_s": float,                        # D-12 resolved
  }
  ```

  `stdout_head` and `stdout_tail` are sourced differently:
  `stdout_head` is from the in-memory head buffer kept by the drain
  loop (capped at `JOB_STDOUT_HEAD_KB`, default 32). `stdout_tail` is
  computed fresh per poll by `_read_file_tail(log_path, n_bytes,
  filter_role=...)` reading the last `JOB_STDOUT_TAIL_KB` (default 32)
  from the on-disk log, parsing role tags. If the log file is smaller
  than head+tail combined, `stdout_tail == ""` (avoid duplication with
  head).

  Snapshot model only — no streaming/cursor/since-token. Every
  `get_tool_job` call returns a full snapshot. Simpler, idempotent,
  matches the "result-shape never raises" contract from Phase 6
  D-04. Agents that want the whole log use `get_tool_log(case_dir,
  log_name, start, length)` from Phase 7 D-25 — already an
  established range-read surface for the same `tool-logs/` location.

- **D-20:** `list_tool_jobs(state: str | list[str] | None = None,
  *, limit: int = 50) -> dict`:

  ```python
  {
      "jobs": list[dict],          # each dict = D-19 snapshot, sorted started_at DESC
      "inflight_count": int,       # currently pending|running
      "completed_count": int,      # currently in completed FIFO
      "completed_cap": int,        # MAX_COMPLETED_JOBS
      "truncated": bool,           # true if total > limit
  }
  ```

  `state` filter accepts a single status string, a list of status
  strings, OR the literal `"_specs"` (lists registered job-tool
  specs with name/description/default_timeout/kwargs_schema for
  agent discovery — NOT a real status). `limit` caps the returned
  jobs list (default 50, max 500); the order is `started_at` DESC
  so most-recent-first.

  *Rationale:* The `_specs` magic value avoids a fifth MCP tool
  (`list_job_tools`) just for discoverability — agents already call
  `list_tool_jobs` to inspect state, and one extra branch in the
  same handler is simpler than another surface.

- **D-21:** Job log filename uses the existing Phase 6 D-09 shape
  literally:

  ```
  tool-logs/<UTC>Z-<slug>-<rand4>.txt
  ```

  Constructed via `artifacts_io.tool_log_path(case_dir, spec.slug)`.
  Job logs are indistinguishable on disk from synchronous
  tool-runner logs — this is by design. Agents that want to find a
  job's log do so by `job["log_path"]`, not by directory walking.

  Job results (the final terminal snapshot dict) are also persisted
  to a sibling JSON file:

  ```
  tool-logs/<UTC>Z-<slug>-<rand4>.json
  ```

  Written once on terminal-state transition. Provides
  audit-trail-after-eviction (the in-memory registry forgets the
  job, but the JSON on disk preserves the full final shape). The
  JSON file is also exposed via the Phase 7 D-26 Resource walker.

### Concurrency, cancellation, and CancelledError propagation (JOBS-06)

- **D-22:** Drain task ownership and cancellation. Each `Job` owns
  exactly one `asyncio.Task` (its drain loop). The drain task is
  created with `asyncio.create_task(...)` BY the registry's
  `_spawn_and_drive(job)` coroutine, NOT by the MCP request handler.
  This decouples job lifetime from request lifetime, which is the
  whole point of the phase.

  When the gateway's lifespan unwinds (container shutdown,
  CancelledError to the lifespan), the registry's `__aexit__`
  cancels every drain task and awaits them with
  `return_exceptions=True`. This matches Phase 8 D-26's shutdown
  contract.

  Client disconnect on `start_tool_job` is harmless: the registry
  has already taken ownership of the drain task; the request
  handler returning early does NOT cancel the job. Documented in
  `start_tool_job`'s docstring with the explicit phrase "the job
  survives the request that launched it."

- **D-23:** `asyncio.shield(proc.wait())` is used at exactly one
  place: inside the SIGTERM-grace path of `cancel()` (D-07).
  Outside of that, `proc.wait()` is awaited normally — there is
  nothing to shield against because the drain task is not bound to
  any request's CancelledError. (Contrast Phase 6 D-04 where
  `asyncio.shield(proc.wait())` is essential because the runner IS
  invoked from inside the request handler.)

  Phase 9's SC-4 200-ms-on-disconnect assertion is a test that
  spawns a `_sleep_probe` job, then cancels its drain task
  externally (simulating registry shutdown), and asserts the
  subprocess is reaped within 200 ms. This is structurally the
  same as Phase 6's CancelledError test, just at the job-drain-task
  level rather than the request-handler level.

### Module imports and boundaries

- **D-24:** Import graph (matches the Phase 8 D-06 layering pattern):

  ```
  jobs.py            imports: artifacts_io, runner, optionally sessions._env_helpers
                     MUST NOT import: tools/*, mcp.server.fastmcp
  tools/jobs.py      imports: jobs, tools.case_dirs, tools.samples
                     MUST NOT import: tools/r2_sessions, tools/shell, tools/re_static
                     (no cross-tool coupling)
  app.py::lifespan   imports BackgroundJobRegistry from jobs
                     constructs registry with kwargs read from jobs.py constants
                     NOT re-reading os.environ here (Phase 8 D-24 invariant)
  ```

- **D-25:** Registration order in `app.py::lifespan` (matters for
  shutdown unwind ordering — LIFO):

  ```
  PinnedBackend          [v1.0]
    SessionRegistry      [Phase 8]
      BackgroundJobRegistry [Phase 9]   <-- new, innermost
        mcp.session_manager.run()
        yield
  ```

  On shutdown: BackgroundJobRegistry's `__aexit__` runs FIRST (kills
  all in-flight jobs), THEN SessionRegistry's `__aexit__` (kills
  all r2 sessions), THEN PinnedBackend's `__aexit__` (tears down
  backend). This ordering matters because some Phase 11 jobs may
  drive r2 (`open_r2_session` → `start_tool_job(tool='ghidra_analyze')`
  workflow), and killing the job first means the r2 session it
  was driving doesn't get a misleading "session went away" error
  partway through a session-orchestrated job.

### Job tool docstring contract

- **D-26:** Every MCP-registered tool in `tools/jobs.py` MUST
  include in its docstring (verbatim, like Phase 8 SESS-05
  disclaimer):

  ```
  In-memory registry — gateway restart cancels in-flight jobs and
  forgets terminal jobs. On-disk logs and JSON result snapshots
  under tool-logs/ are preserved across restart.

  Jobs are shared across all bearer-token clients (no per-Mcp-Session-Id
  keying). Any client with the bearer token can see and cancel any
  job. (Per-session keying deferred to v1.2.)
  ```

  Tested in the same way Phase 8 tested SESS-05 — a regression test
  scans the docstrings for the disclaimer string.

### Claude's Discretion

- Internal naming of private helpers (`_drain`, `_spawn_and_drive`,
  `_read_file_tail`, etc.).
- Exact `_sleep_probe` test fixture argv (`sleep N` is fine; `sh -c
  'echo a; sleep N; echo b'` if a multi-line drain test is needed —
  research phase decides).
- Whether to also write a one-line per-job `tool-logs/<ts>-<slug>-<rand4>.meta`
  with the kwargs for grep-friendliness, or rely solely on the
  `.json` snapshot per D-21. (Lean toward NOT adding `.meta`;
  `.json` is enough.)
- ANSI-strip / UTF-8-codepoint-boundary truncation reuse from
  Phase 6 — if Phase 6 exports `_strip_ansi` and `_truncate_utf8_safe`
  helpers, jobs reuses them; if Phase 6 made them private,
  jobs.py inlines its own copies (matches Phase 8 D-06's
  "MAY import from runner.py; if not, inlines its own").
- Exact wording of error-hint strings in D-15 (the structure is
  locked; the prose can be polished).
- Whether `list_tool_jobs(state='_specs')` returns just the spec
  registry or also includes "what specs are registered AND have
  no progress_parser yet" hints — small UX polish.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### v1.1 milestone requirements

- `.planning/REQUIREMENTS.md` §"Background Job System (JOBS)" (JOBS-01..JOBS-07) — the seven authoritative requirements for this phase
- `.planning/REQUIREMENTS.md` §"Out of Scope (v1.1)" — confirms per-Mcp-Session-Id keying is deferred, persistent state is deferred
- `.planning/ROADMAP.md` §"Phase 9: Background Job System" — phase goal, depends-on, six success criteria, sister-phase context

### Project & milestone framing

- `.planning/PROJECT.md` §"Current Milestone: v1.1 Remote RE Tool Expansion" — "Background job system" target-feature paragraph naming capa, unblob, Ghidra/IDA analysis, strace, qemu as motivating tools
- `.planning/PROJECT.md` §"Key Decisions" / "Out of Scope" — confirms in-memory-only, no composite tools

### Phase 6 chokepoint runner (the layer this phase sits on)

- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-01..D-04 — `ReToolRunner` class shape, the 12-key locked result dict (`stdout_head`, `stdout_truncated`, `stdout_bytes_total`, ...), the "never raises on subprocess state" contract
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-08, D-09 — env-var module-constant pattern, `tool-logs/<UTC>Z-<slug>-<rand4>.txt` log filename shape
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-17 — `start_new_session=True` + `killpg` process-group SIGKILL contract
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` D-04 — `asyncio.shield(proc.wait())` CancelledError pattern (this phase's D-23 layers on top)

### Phase 7 case-dir conventions

- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-09 — `tool_log_path` API and filename shape (Phase 9 D-21 calls this verbatim)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-11..D-15 — `assert_no_collisions` invariant (Phase 9's four tool names must not collide with backend-pass-through)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-25 — `get_tool_log(case_dir, log_name, start, length)` range-read surface (the answer for "give me the whole log" once head/tail isn't enough)
- `.planning/phases/07-run-shell-typed-static-wrappers-re-artifacts/07-CONTEXT.md` D-26 — depth-2 case-dir Resources walker (`tool-logs/<file>` is auto-exposed; this is why we keep job logs in `tool-logs/` and not a new subdir)

### Phase 8 registry pattern (the precedent this phase mirrors)

- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-05, D-06 — primitive (`sessions.py`) + MCP surface (`tools/r2_sessions.py`) module split; import-direction invariants
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-07 — `session_state.SESSION_REGISTRY` slot pattern (Phase 9 adds `JOB_REGISTRY` parallel to this)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-14 — env-var module-constant pattern + `_env_float`/`_env_int` helpers (Phase 9 D-13 reuses or inlines)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-11 — "layer onto the Phase 6 12-key dict" precedent (Phase 9 D-19 follows this exactly)
- `.planning/phases/08-session-scoped-r2/08-CONTEXT.md` D-18, D-24, D-26 — `JobCapReached`-style structured cap error (Phase 9 D-15 mirrors), `async with Registry` block in BOTH lifespan branches, parallel-kill on shutdown

### Existing source files (read before writing plans)

- `mcp-gateway/src/mcp_gateway/runner.py` — `ReToolRunner` implementation; check whether `_strip_ansi` / `_truncate_utf8_safe` / `_env_float` / `_env_int` are module-private or exportable (affects D-13, Claude's Discretion item 4)
- `mcp-gateway/src/mcp_gateway/sessions.py` — `SessionRegistry` lifespan-ownership pattern; the closest template for `BackgroundJobRegistry`
- `mcp-gateway/src/mcp_gateway/session_state.py` — module-level slot pattern (`PINNED_BACKEND`, `SESSION_REGISTRY`); Phase 9 adds `JOB_REGISTRY` here
- `mcp-gateway/src/mcp_gateway/app.py::lifespan` lines 85-180 — the nested-async-context-manager layout; Phase 9 inserts BackgroundJobRegistry one level deeper than SessionRegistry in BOTH branches
- `mcp-gateway/src/mcp_gateway/tools/__init__.py::register_all_tools` — single registration entry point; Phase 9 adds one import + one register line
- `mcp-gateway/src/mcp_gateway/artifacts_io.py::EXPANDED_CASE_SUBDIRS` — Phase 9 does NOT extend this (job logs reuse `tool-logs/`)

### MCP protocol references

- MCP spec 2025-03-26 progress notifications — `Context.report_progress(progress, total, message)` semantics; Phase 9 D-16's Tier-2 poll-side push relies on this being request-scoped
- FastMCP `Context` parameter injection — `tools/jobs.py` handlers accept `ctx: Context` as the last positional arg per FastMCP convention

### Tools to be wrapped (only capa in Phase 9 itself)

- capa documentation — invocation argv (`capa <sample>` or `capa --format=<fmt> <sample>`), exit codes, stderr progress emission (or lack thereof). Research phase should confirm whether capa emits any parseable progress on stderr or only via stdout-JSON at end (informs D-17).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets

- `mcp_gateway.runner.ReToolRunner` — the chokepoint subprocess primitive. Phase 9 jobs are essentially "an async-detached ReToolRunner with a longer timeout and a registry entry." Reuses argv-only, `start_new_session=True`, process-group cleanup, capture-to-`tool-logs/`.
- `mcp_gateway.runner.run_tool(case_dir, argv, *, slug, ...)` — the convenience helper. Phase 9 does NOT call this (it needs to control the spawn lifecycle), but its kwargs shape informs `JobToolSpec.build_argv`'s return contract.
- `mcp_gateway.sessions.SessionRegistry` — the registry shape Phase 9 mirrors. Same async-context-manager, same env-var constants pattern, same `__aexit__`-parallel-kill-on-shutdown.
- `mcp_gateway.sessions._env_float` / `_env_int` — env-var helpers. Either re-imported into `jobs.py` (if Phase 8 exports them) or duplicated locally per D-13.
- `mcp_gateway.sessions._DANGEROUS_R2_CMD_RE` pattern — the "compile once at import" + "check at wrapper layer" pattern. Phase 9 has no dangerous-cmd analog (argv is built by the spec, not by the caller), but the import-time validation pattern carries over for `kwargs_schema` checks at registration time.
- `mcp_gateway.artifacts_io.tool_log_path(case_dir, slug)` — produces the `tool-logs/<UTC>Z-<slug>-<rand4>.txt` path. Phase 9 D-21 calls this directly.
- `mcp_gateway.artifacts_io.confine_to(case_dir, path)` — required because `kwargs` may contain agent-supplied paths (e.g., `kwargs={"sample": "uploads/abcd1234"}`); each Phase 10/11 spec's `build_argv` runs `confine_to` on every path field before composing argv.
- `mcp_gateway.tools.case_dirs.resolve_case_dir` — `start_tool_job` calls this to materialize `case_dir`, identical to every Phase 7 typed wrapper.
- `mcp_gateway.tools.samples.resolve_sample` — Phase 10 specs that take a `sample` kwarg will call this in their `build_argv`; out of scope for Phase 9's `capa` spec because capa accepts a path (which `resolve_sample` returns).
- `mcp_gateway.session_state` — the module-level-slot pattern, ALREADY proven by two slots (`PINNED_BACKEND`, `SESSION_REGISTRY`). Phase 9 adds `JOB_REGISTRY: Optional["BackgroundJobRegistry"] = None` identically.

### Established patterns

- **Primitive + tools/ surface split** (Phase 6, Phase 8) — Phase 9 follows literally: `jobs.py` is the primitive (no MCP decorators, no FastMCP imports), `tools/jobs.py` is the surface (every function is `@mcp.tool()`-decorated, returns dicts, never raises).
- **Async-context-manager registry owned by `app.py::lifespan`** (Phase 8) — Phase 9 mirrors. Nested inside SessionRegistry per D-25.
- **Module-level env-var constants validated at import** (Phase 6 D-08, Phase 8 D-14) — Phase 9 D-13 follows identically.
- **Structured error dicts, never raise out of MCP tools** (Phase 6 D-04, Phase 8 D-18) — Phase 9 D-15.
- **Layer onto Phase 6's 12-key result dict** (Phase 8 D-11) — Phase 9 D-19.
- **Docstring disclaimer for cross-cutting limitations** (Phase 8 SESS-05 disclaimer regression test) — Phase 9 D-26 disclaimer must be present in all four tool docstrings.
- **Collision check at lifespan** (Phase 7 D-11) — Phase 9's four tool names (`start_tool_job`, `get_tool_job`, `cancel_tool_job`, `list_tool_jobs`) must not collide with any backend-pass-through tool. Almost certainly safe (these names are gateway-domain, not RE-tool-domain), but the lifespan collision check enforces it.
- **`asyncio.shield(proc.wait())` ONLY inside cancellation paths** (Phase 6 D-04) — Phase 9 D-23 narrows the use site to the SIGTERM-grace path inside `registry.cancel(job)`, because the drain task is registry-owned and not bound to a request's CancelledError.

### Integration points

- `app.py::lifespan` — one additional `async with BackgroundJobRegistry(...)` nested inside `SessionRegistry`, in both the `backend_name is None` and `PinnedBackend` branches. Sets `session_state.JOB_REGISTRY = registry` in the `try`, clears it in `finally`. Matches the Phase 8 D-24 surgical-edit footprint.
- `tools/__init__.py::register_all_tools` — one import (`from mcp_gateway.tools import jobs as jobs_tools`) + one call (`jobs_tools.register(mcp)`).
- `session_state.py` — one new slot. Update the file-level `GW-V2-03` caveat to also note the JOB shared-across-bearer-token-clients implication (parallel to Phase 8's update for SESSION_REGISTRY).
- `artifacts_io.py` — no changes. Job logs reuse `tool-logs/`; the existing `EXPANDED_CASE_SUBDIRS` 9-name catalog already includes it.
- Phase 7 D-26 Resources walker — no changes. Walks depth ≤ 2, exposes `tool-logs/<ts>-<slug>-<rand4>.txt` and the sibling `.json` automatically.

</code_context>

<specifics>
## Specific Ideas

- "Snapshot per poll, no streaming cursor" is the explicit polling-loop ergonomic
  request. Agents iterate `while job["status"] not in TERMINAL: job =
  get_tool_job(job_id); await sleep(N)`. Anything more clever (event streams,
  webhooks, since-tokens) makes the agent code more complex without measurable
  benefit at v1.1 scale.
- "Eviction does NOT delete log files" is the audit-trail invariant. The
  case-dir is the source of truth; the in-memory registry is a convenience
  index. An analyst returning to a case six weeks later must still be able to
  find every job's log by browsing Resources, even though the registry has
  long since evicted the entry.
- The capa-as-canonical-Phase-9-tool choice exists because it lets Phase 9's
  integration test be self-contained — no Phase 10/11 dependency. unblob would
  be a more dramatic demo (it has obvious progress emission), but it's owned
  by Phase 10; Phase 9 owns the surface and the minimal-viable spec to prove
  the surface.

</specifics>

<deferred>
## Deferred Ideas

- **Persistent (across-restart) job state** — explicitly v1.2. The on-disk
  `.json` snapshots written per D-21 are a foundation: a future v1.2 phase can
  scan `tool-logs/*.json`, re-hydrate completed jobs into the registry on
  startup, and offer "your job from before the restart" recovery. Phase 9 ships
  the artifact, not the hydration logic.
- **Per-Mcp-Session-Id keying of jobs** — explicitly v1.2 per
  REQUIREMENTS.md §"Out of Scope (v1.1)" (parallel to SESS-05).
- **Cross-job dependencies / DAG orchestration** — out of scope; agents
  compose by polling. A future "workflow" phase could add `start_workflow_job`
  that schedules a graph, but that is a v1.2+ concern.
- **Server-push progress notifications outside of polling** — out of scope.
  The two-tier poll-push model in D-16 is sufficient for v1.1; true
  server-initiated push would require MCP session-scoped notification
  channels that the spec is still maturing on.
- **`investigate_*` composite tools that internally schedule a sequence of
  jobs** — out of scope per PROJECT.md "Out of Scope" line. Orchestration is
  the agent's responsibility, not the gateway's.
- **Disk-quota-aware log management** — the in-memory cap bounds per-job log
  size; total `tool-logs/` size is unbounded across jobs. A future phase could
  add a periodic sweeper for `tool-logs/` older than N days. For v1.1, the
  case-dir is the natural cleanup boundary (analyst deletes the case → all
  logs go).

### Reviewed todos (not folded)

None — no pending todos matched Phase 9 scope.

</deferred>

---

*Phase: 09-background-job-system*
*Context gathered: 2026-05-19*
