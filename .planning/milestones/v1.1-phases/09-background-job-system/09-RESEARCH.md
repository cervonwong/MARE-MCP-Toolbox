# Phase 9: Background Job System - Research

**Researched:** 2026-05-19
**Domain:** asyncio job orchestration on top of mcp-gateway's Phase 6 chokepoint runner
**Confidence:** HIGH (most decisions locked in CONTEXT.md; this research verifies code-level assumptions and resolves Claude's-Discretion items)

## Summary

Phase 9 adds an asynchronous, long-running tool execution surface to mcp-gateway so remote agents can launch tools (capa today; unblob/Ghidra/IDA/strace/qemu in later phases) that exceed MCP's effective 60 s per-request cap. The design is locked by D-01..D-26 of CONTEXT.md; this research focuses on verifying code-level assumptions, resolving Claude's-Discretion items, and surfacing one concrete refutation:

**Primary correction surfaced by research:** capa does NOT emit parseable progress lines on stderr. Verified by reading `capa/loader.py` on master — capa uses `rich.console.Console(stderr=True).status("analyzing program...", spinner="dots")`, a spinner that draws via ANSI cursor-move escape sequences with NO newline-terminated progress events. This means **D-17's capa `progress_parser` MUST be `None`** and Phase 9's Tier-1 progress capture is null for capa. JOBS-07 is still satisfied — its phrasing is "where the tool can produce progress signals," and capa cannot. The progress plumbing (D-16 Tier-1 + Tier-2 + D-18 fields) still ships because Phase 10's unblob and Phase 11's tools will use it; Phase 9 only proves the field shape.

**Primary recommendation:** Follow CONTEXT.md exactly with two structural narrowings (1) `JobToolSpec.kwargs_schema` validation is hand-rolled against the existing slug/type-check patterns in the codebase — `jsonschema` is NOT a project dependency and adding it for one optional spec field is over-engineering; (2) re-implement `_env_float`/`_env_int` locally in `jobs.py` (mirror Phase 8's choice in `sessions.py`) rather than importing from `sessions.py` — the existing two-module pattern is the established precedent and avoids cross-primitive coupling.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

The full D-01..D-26 set is locked. Summarized below for the planner; the original CONTEXT.md is the authoritative source.

- **D-01:** `start_tool_job(tool, kwargs, *, case_dir, timeout)` resolves `tool` against `JOB_TOOL_REGISTRY` (allowlist, NOT raw argv).
- **D-02:** `JobToolSpec` frozen dataclass with 7 fields (name, slug, build_argv, default_timeout_s, progress_parser, kwargs_schema, description). `register_job_tool(spec)` at module-import time.
- **D-03:** `_sleep_probe` spec ships in `jobs.py` itself as an internal smoke fixture.
- **D-04:** One user-visible spec — `capa` — ships in `jobs.py`. unblob/binwalk/ghidra/etc. are Phase 10/11.
- **D-05:** `start_tool_job` signature locked; returns snapshot immediately (status `pending` or `running`); never awaits subprocess.
- **D-06:** 7-state status vocabulary (`pending`, `running`, `succeeded`, `failed`, `cancelled`, `killed_timeout`, `killed_log_cap`). Terminal states immutable.
- **D-07:** SIGTERM → grace (`JOB_CANCEL_GRACE_S = 10.0`) → SIGKILL ladder. `cancel()` is idempotent.
- **D-08:** Job hard timeout wraps `ReToolRunner` with `timeout=None`; job-level `asyncio.wait_for` is the enforcement boundary. On timeout: same SIGTERM-grace-SIGKILL ladder, status `killed_timeout`.
- **D-09:** Log cap is counter-based per-line drain. Immediate SIGKILL (no grace) on cap-exceed. Stdout+stderr share cap (combined).
- **D-10:** FIFO eviction of completed jobs at cap (default 200). On-disk logs preserved. In-flight jobs never evicted.
- **D-11:** Concurrency cap `MCP_GATEWAY_MAX_JOBS_INFLIGHT = 4`. NO queueing — cap-reach returns error dict.
- **D-12:** Effective-timeout = `min(caller_timeout or spec.default_timeout_s or JOB_TIMEOUT_S, JOB_MAX_TIMEOUT_S)`.
- **D-13:** 6 env-var module constants read once at `jobs.py` import. RuntimeError on bad values.
- **D-14:** `BackgroundJobRegistry` is async-context-manager. Lock guards state transitions only (NEVER held during drain).
- **D-15:** Four structured error dict shapes (cap-reached / unknown-tool / job-not-found / invalid-kwargs). Tools never raise.
- **D-16:** Two-tier progress: Tier-1 (drain captures via parser), Tier-2 (poll-side push via `Context.report_progress`).
- **D-17:** Phase 9 ships capa parser (research must verify capa's emission format).
- **D-18:** Progress field shape: all-None or all-Some, message ≤200 chars.
- **D-19:** Snapshot result dict layers onto Phase 6's 12 keys; adds 13 Phase 9 extensions. Snapshot-only — no streaming/cursor.
- **D-20:** `list_tool_jobs(state, *, limit=50)` returns jobs + counters; `state='_specs'` magic value lists registered specs.
- **D-21:** Log filename via existing `artifacts_io.tool_log_path(case_dir, spec.slug)`. Sibling `.json` snapshot on terminal transition.
- **D-22:** Drain task owned by registry, NOT by request handler. Client disconnect on start does NOT cancel job.
- **D-23:** `asyncio.shield(proc.wait())` ONLY inside cancel-grace path. Drain-task wait is not shielded.
- **D-24:** Import graph: `jobs.py` → artifacts_io + runner (+ optionally `sessions._env_helpers`); `tools/jobs.py` → jobs + tools.case_dirs + tools.samples; no cross-tool coupling.
- **D-25:** Lifespan nesting order: `PinnedBackend > SessionRegistry > BackgroundJobRegistry > mcp.session_manager.run()`. LIFO unwind.
- **D-26:** Verbatim disclaimer in every `tools/jobs.py` MCP tool docstring (in-memory + shared-across-bearer-token-clients).

### Claude's Discretion

The following from CONTEXT.md remain Claude's call; resolved in this research:

1. Internal naming of private helpers (`_drain`, `_spawn_and_drive`, `_read_file_tail`).
   → **Resolved:** Use exactly those names. Matches Phase 6's `_drain` private helper.
2. `_sleep_probe` test fixture argv (`sleep N` vs `sh -c 'echo a; sleep N; echo b'`).
   → **Resolved:** Use **two specs** — `_sleep_probe` (`["sleep", str(int(seconds))]`) for the SC-4 disconnect-cancellation test (clean, no shell layer in the way of killpg), AND `_log_burst_probe` (`["sh", "-c", "while true; do head -c 1048576 /dev/urandom | base64; done"]`) for the SC-3 log-cap-kill test. The latter cannot be `sleep` because it must drive bytes into the drain loop fast enough to exceed `MAX_JOB_LOG_BYTES`.
3. Add a `.meta` file alongside the `.json`? → **Resolved:** NO. `.json` per D-21 is sufficient; no `.meta`.
4. Reuse Phase 6's `_strip_ansi`/`_truncate_to_utf8_boundary` vs inline.
   → **Resolved:** **Inline copies in `jobs.py`** (mirror Phase 8's decision in `sessions.py` lines 102-125). Phase 6's helpers are module-private with leading underscore (`_ANSI_ESCAPE`, `_truncate_to_utf8_boundary`); importing private names creates a brittle coupling that Phase 8 already declined.
5. Exact wording of D-15 error-hint strings — locked in this research's Pattern 4 below.
6. Does `list_tool_jobs(state='_specs')` include "no progress_parser yet" hints? → **Resolved:** YES — include `has_progress_parser: bool` per spec in the returned dict so agents can detect non-emitting tools (capa today) without a separate probe.

### Deferred Ideas (OUT OF SCOPE)

- Persistent (across-restart) job state. `.json` snapshots written by D-21 are the v1.2 foundation but Phase 9 ships zero hydration code.
- Per-Mcp-Session-Id keying of jobs (v1.2; GW-V2-03).
- Cross-job DAG / dependency orchestration.
- Server-push progress (push outside of polling).
- Composite `investigate_*` tools.
- Disk-quota-aware total-log management (per-job cap only).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| JOBS-01 | `start_tool_job(tool, args)` returns opaque `job_id`; runs through `ReToolRunner` with same safety properties | Verified: `runner.ReToolRunner` exposes `__init__` and `run(argv)` separately; D-01 wraps `run` with a registry-owned drive task. argv-only enforced by `create_subprocess_exec` (line 217 of runner.py). |
| JOBS-02 | `get_tool_job(job_id)` returns status + head/tail of stdout/stderr + exit_code + log_path | Snapshot shape in D-19 layers onto runner.py's 12-key D-03 dict + 13 Phase 9 extensions. `stdout_tail`/`stderr_tail` computed via on-disk read of log_path (per-role tags TBD — see Open Q1). |
| JOBS-03 | `cancel_tool_job` SIGTERMs the pgroup, then SIGKILLs after grace | D-07 ladder verified against runner.py:245 `killpg(getpgid(proc.pid), SIGKILL)`. Phase 6 uses immediate SIGKILL; Phase 9 adds SIGTERM-then-SIGKILL because tools may flush-on-SIGTERM (capa's rich Console catches SIGINT/SIGTERM and flushes). |
| JOBS-04 | `list_tool_jobs(state)` enumerates jobs; in-memory only; restart cancels in-flight | D-14's `__aexit__` parallel-kill matches sessions.py:223-239 verbatim pattern. `.json` snapshot per D-21 provides post-restart artifact even though registry is gone. |
| JOBS-05 | `MCP_GATEWAY_MAX_JOB_LOG_MB` default 256 MB; over-cap → `killed_log_cap`; LRU/FIFO cleanup | runner.py already has `MAX_LOG_MB = 256` constant (line 79). Phase 9 uses its OWN constant `MAX_JOB_LOG_MB` (D-13) so the two caps are independent; jobs may run different shape from one-shot static tools. D-10 documents FIFO-of-completed (NOT pure LRU) to bound memory. |
| JOBS-06 | CancelledError → `killpg(SIGKILL)` via `asyncio.shield(proc.wait())`; client disconnect → subprocess dead within 200 ms | D-23 narrows shield to ONLY inside `registry.cancel()` SIGTERM-grace path. Drain-task wait is normal. SC-4 test (200 ms) is structurally the same as runner.py's existing `test_cancel_propagates_to_killpg` test (tests/test_runner.py:64-78). |
| JOBS-07 | `Context.report_progress(progress, total, message)` for tools that emit progress signals | Verified: mcp SDK 1.27.x `Context.report_progress` signature is `async def report_progress(self, progress: float, total: float \| None = None, message: str \| None = None) -> None`. Per-request-scoped — works in poll-side push (D-16 Tier-2). |
</phase_requirements>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `mcp` (Python SDK) | 1.27.x (pinned `>=1.27,<1.28` in mcp-gateway/pyproject.toml) | FastMCP server + `Context.report_progress` | Already the gateway's transport SDK. `Context` injection into MCP tools is FastMCP's native pattern. |
| Python `asyncio` (stdlib) | 3.11+ | Subprocess + task orchestration | Same primitive Phase 6 and Phase 8 use; no new dep. |
| Python `dataclasses` (stdlib) | 3.11+ | `JobToolSpec` frozen dataclass, `Job` dataclass | Matches `R2Session` dataclass in sessions.py:131. |
| Python `secrets` (stdlib) | 3.11+ | `job_id = secrets.token_hex(8)` | Matches sessions.py:268 `secrets.token_urlsafe(12)` precedent. Token hex (D-05) gives a 16-char URL-safe ID. |
| Python `collections.OrderedDict` (stdlib) | 3.11+ | FIFO of completed jobs (D-10 eviction) | Stdlib; preserves insertion order; `popitem(last=False)` is O(1) FIFO pop. |
| Python `signal` (stdlib) | 3.11+ | `SIGTERM`, `SIGKILL` for ladder | Matches runner.py:38, sessions.py:36. |
| `pathlib.Path` (stdlib) | 3.11+ | Filesystem paths | Codebase-wide convention. |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `mcp_gateway.runner.ReToolRunner` | 0.1.0 (this codebase) | Spawn + drain + log-write primitive | Each `Job` constructs ONE `ReToolRunner(case_dir, slug, timeout=None)` per D-08 (timeout=None means unbounded; job-level wait_for enforces). [VERIFIED: runner.py:160] |
| `mcp_gateway.artifacts_io.tool_log_path` | 0.1.0 | Compute `tool-logs/<UTC>Z-<slug>-<rand4>.txt` | Called by `JobToolSpec`-driven spawn to determine log path. Returns `Path`; caller `ensure_subdir(case_dir, "tool-logs")` first. [VERIFIED: artifacts_io.py:124] |
| `mcp_gateway.tools.case_dirs.resolve_case_dir` | 0.1.0 | STATUS_ROOT containment | `start_tool_job` calls this first. [VERIFIED: case_dirs.py:10] |
| `mcp_gateway.tools.samples.resolve_sample` | 0.1.0 | sha256/path → absolute path | NOT used by Phase 9 directly. Phase 10/11 specs' `build_argv` will use this. [VERIFIED: samples.py:34] |
| `mcp_gateway.session_state` | 0.1.0 | Module-level `JOB_REGISTRY` slot | Add one new `Optional["BackgroundJobRegistry"] = None` slot. [VERIFIED: session_state.py:19 shows precedent] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-rolled `kwargs_schema` validator | `jsonschema` PyPI lib | jsonschema NOT a project dep; adds wheel weight + sync-with-stdlib-Optional surface for ONE optional field with a single spec using it. The spec ships `{"seconds": {"type": "integer", "min": 0, "max": 600}}` — a 4-line walk is trivially correct. **Decision: hand-roll.** |
| Inline ANSI/UTF-8 helpers in `jobs.py` | Import from `runner.py` | Phase 6 marks `_ANSI_ESCAPE` and `_truncate_to_utf8_boundary` as module-private (leading underscore). Phase 8 declined this import (sessions.py:107-125 has its own copies). Phase 9 follows Phase 8. **Decision: inline.** |
| Re-import `_env_int`/`_env_float` from `sessions.py` | Inline | Both modules are siblings; Phase 8 chose to inline (sessions.py:52-71) rather than import from runner.py. Phase 9 matches. **Decision: inline copies in `jobs.py`.** |
| Stream-style readline drain (CONTEXT.md D-09 example) | Chunked binary read (Phase 6's pattern) | runner.py:120 uses `await stream.read(CHUNK)` with `CHUNK = 64 * 1024`. CONTEXT.md's D-09 pseudocode uses `await stream.readline()`. **Conflict surfaced — see Open Q2.** Recommendation: chunked read for consistency, but track byte count per chunk for the cap check; head-buffer slicing per-byte. |

**Installation:** No new dependencies. Phase 9 reuses the existing `mcp`, `starlette`, `anyio`, `asyncio` stack. Verified against mcp-gateway/pyproject.toml.

**Version verification:**
- `mcp>=1.27,<1.28` pinned — `Context.report_progress` available since 1.20 [CITED: https://github.com/modelcontextprotocol/python-sdk]. Signature `(progress: float, total: float | None = None, message: str | None = None)` matches D-18's three-tuple `(int, int, str)` after int→float coercion.
- `pydantic` — transitive via mcp/starlette; not used directly by Phase 9.

## Architecture Patterns

### Recommended Project Structure

```
mcp-gateway/src/mcp_gateway/
├── jobs.py                  # PRIMITIVE — new in Phase 9 (D-01..D-26 home)
│   ├── _env_int / _env_float helpers (inlined; Phase 8 precedent)
│   ├── 6 module constants (D-13)
│   ├── _strip_ansi / _truncate_for_response helpers (inlined per Phase 8 precedent)
│   ├── JobStatus = Literal[...] (D-06)
│   ├── JobToolSpec frozen dataclass (D-02)
│   ├── Job dataclass (per-job state)
│   ├── JobCapReached / JobNotFound exception types (D-15)
│   ├── JOB_TOOL_REGISTRY: dict[str, JobToolSpec] (module-level)
│   ├── register_job_tool(spec)
│   ├── _validate_kwargs(spec, kwargs) (hand-rolled per Open Q3 below)
│   ├── _SLEEP_PROBE_SPEC, _LOG_BURST_PROBE_SPEC, _CAPA_SPEC (D-03, D-04)
│   ├── _parse_capa_progress(line) -> None (D-17 verified; capa emits no parseable progress)
│   └── BackgroundJobRegistry async-context-manager (D-14)
│
├── tools/jobs.py            # MCP SURFACE — new in Phase 9 (4 tools)
│   ├── start_tool_job
│   ├── get_tool_job (accepts ctx: Context | None for D-16 Tier-2)
│   ├── cancel_tool_job
│   ├── list_tool_jobs (accepts state filter incl. '_specs' magic)
│   └── register(mcp) entry point — matches r2_sessions.register pattern
│
├── session_state.py         # +1 line: JOB_REGISTRY slot (D-07-parallel)
├── app.py                   # +1 nested-async-with in both lifespan branches (D-25)
├── tools/__init__.py        # +1 import, +1 register call
└── (no changes to artifacts_io.py — tool-logs/ already in EXPANDED_CASE_SUBDIRS)
```

### Pattern 1: Primitive + tools/ surface split (Phase 6, Phase 8 precedent)

**What:** The primitive layer (`jobs.py`) contains no MCP decorators or FastMCP imports. The tools/ layer (`tools/jobs.py`) is the only place `@mcp.tool()` / `mcp.tool()(fn)` registrations happen, and it imports from the primitive.

**When to use:** Always for new gateway surfaces. Phases 6, 8 follow this; deviation creates testing pain (the primitive can't be unit-tested without a FastMCP harness).

**Example (from `tools/r2_sessions.py`):**
```python
# tools/r2_sessions.py
from mcp_gateway import session_state, sessions  # module-attribute access
from mcp_gateway.sessions import SessionCapReached, check_dangerous_cmd
# ... handler functions ...
def register(mcp: FastMCP) -> None:
    mcp.tool()(open_r2_session)
    mcp.tool()(r2_cmd)
    mcp.tool()(close_r2_session)
    mcp.tool()(list_sessions)
```
[VERIFIED: tools/r2_sessions.py:398-403]

### Pattern 2: Async-context-manager registry owned by lifespan (Phase 8 precedent)

**What:** The registry is constructed inside `app.py::lifespan`, used as `async with` block, and stored on `session_state` for tool-handler lookup. On `__aexit__`, parallel-kill via `asyncio.gather(close(...), return_exceptions=True)`.

**Example (from `app.py:144-161`):**
```python
async with _build_registry() as registry:
    session_state.SESSION_REGISTRY = registry
    try:
        async with mcp.session_manager.run():
            yield
    finally:
        session_state.SESSION_REGISTRY = None
```

**Phase 9 nests one level deeper:**
```python
async with PinnedBackend(backend_name) as pinned:
    session_state.PINNED_BACKEND = pinned
    try:
        await assert_no_collisions(mcp)
        async with _build_session_registry() as sess_registry:
            session_state.SESSION_REGISTRY = sess_registry
            try:
                async with _build_job_registry() as job_registry:        # NEW
                    session_state.JOB_REGISTRY = job_registry            # NEW
                    try:
                        async with mcp.session_manager.run():
                            yield
                    finally:
                        session_state.JOB_REGISTRY = None                # NEW
            finally:
                session_state.SESSION_REGISTRY = None
    finally:
        session_state.PINNED_BACKEND = None
```

Repeat in the `backend_name is None` branch. **LIFO unwind:** Jobs killed → r2 sessions killed → backend torn down.

### Pattern 3: Env-var module constants read once at import

**What:** All env-var lookups happen at module import via `_env_int`/`_env_float` helpers that raise `RuntimeError` on bad values. Constants are stored at module level; downstream code uses `module.CONST` (not `os.environ[...]`) so `importlib.reload(module)` propagates correctly in tests.

**Verified in codebase:**
- runner.py:52-79 (4 constants)
- sessions.py:49-75 (5 constants)

**Phase 9 pattern (D-13):**
```python
# jobs.py
def _env_int(name: str, default: int) -> int: ...
def _env_float(name: str, default: float) -> float: ...

JOB_TIMEOUT_S      = _env_float("MCP_GATEWAY_JOB_TIMEOUT_S",      3600.0)
JOB_MAX_TIMEOUT_S  = _env_float("MCP_GATEWAY_JOB_MAX_TIMEOUT_S",  86400.0)
JOB_CANCEL_GRACE_S = _env_float("MCP_GATEWAY_JOB_CANCEL_GRACE_S", 10.0)
MAX_JOB_LOG_MB     = _env_int(  "MCP_GATEWAY_MAX_JOB_LOG_MB",     256)
MAX_JOBS_INFLIGHT  = _env_int(  "MCP_GATEWAY_MAX_JOBS_INFLIGHT",  4)
MAX_COMPLETED_JOBS = _env_int(  "MCP_GATEWAY_MAX_COMPLETED_JOBS", 200)
JOB_STDOUT_HEAD_KB = _env_int(  "MCP_GATEWAY_JOB_STDOUT_HEAD_KB", 32)
JOB_STDOUT_TAIL_KB = _env_int(  "MCP_GATEWAY_JOB_STDOUT_TAIL_KB", 32)
JOB_STDERR_HEAD_KB = _env_int(  "MCP_GATEWAY_JOB_STDERR_HEAD_KB", 32)
JOB_STDERR_TAIL_KB = _env_int(  "MCP_GATEWAY_JOB_STDERR_TAIL_KB", 32)
```

(D-13 lists 6; the 4 additional `*_HEAD/TAIL_KB` constants are required because the D-19 snapshot shape has fields like `stdout_head`/`stdout_tail` that must be sized — surfacing them as env-overridable matches runner.py:76-77's pattern.)

### Pattern 4: Structured error dicts via exception → `.to_dict()` (Phase 8 D-18 precedent)

**Verified in codebase (sessions.py:177-192):**
```python
class SessionCapReached(Exception):
    def __init__(self, max_sessions, open_count, existing):
        self.max_sessions = max_sessions
        ...
    def to_dict(self) -> dict:
        return {"error": "session cap reached", "max": ..., "open_count": ..., "existing": ...}
```

**Tool surface catches and returns the dict (tools/r2_sessions.py:175-184):**
```python
try:
    sess = await registry.open(...)
except SessionCapReached as e:
    return e.to_dict()
```

**Phase 9 follows this pattern for all four D-15 error shapes.** The exception classes live in `jobs.py`; the tool surface in `tools/jobs.py` catches and returns `.to_dict()`. Error-hint wording locked here:

```python
# D-15 #1: cap-reached
{"error": "job cap reached",
 "inflight": <int>, "cap": <int>,
 "hint": "wait for an inflight job to complete or cancel one via cancel_tool_job(job_id)"}

# D-15 #2: unknown tool name
{"error": "unknown job tool",
 "tool": <str>, "known": [<sorted list of registered names>],
 "hint": "call list_tool_jobs(state='_specs') for the spec catalog"}

# D-15 #3: job not found (evicted or never existed)
{"error": "job not found (evicted from in-memory registry; gateway restart also evicts)",
 "job_id": <str>,
 "hint": "browse tool-logs/<ts>-<slug>-<rand4>.json via Resources for the final snapshot"}

# D-15 #4: kwargs validation failed
{"error": "invalid kwargs",
 "field": <str>, "expected": <str>, "got": <str>}
```

### Pattern 5: Docstring disclaimer splice (Phase 8 D-23 precedent)

**Verified in codebase (tools/r2_sessions.py:200-207):**
```python
open_r2_session.__doc__ = (open_r2_session.__doc__ or "").replace(
    "{_FULL_DISCLAIMER}", _SESS_05_DISCLAIMER_FULL
)
```

The trick is that Python only attaches a docstring to `__doc__` when the function body's first expression is a pure string literal. F-string interpolation or string concatenation breaks docstring attachment. The post-definition splice via `.replace()` is the proven workaround.

**Phase 9's D-26 disclaimer (verbatim, two paragraphs):**
```python
_JOBS_DISCLAIMER = """
    In-memory registry — gateway restart cancels in-flight jobs and
    forgets terminal jobs. On-disk logs and JSON result snapshots
    under tool-logs/ are preserved across restart.

    Jobs are shared across all bearer-token clients (no per-Mcp-Session-Id
    keying). Any client with the bearer token can see and cancel any
    job. (Per-session keying deferred to v1.2.)
"""
```

Each of `start_tool_job`, `get_tool_job`, `cancel_tool_job`, `list_tool_jobs` gets `__doc__ = (...).replace("{_JOBS_DISCLAIMER}", _JOBS_DISCLAIMER)` post-definition.

### Anti-Patterns to Avoid

- **`asyncio.shield(proc.wait())` outside the SIGTERM-grace path.** Phase 6 D-04 needed shield because `run_tool` is called from inside an MCP request handler whose `CancelledError` would otherwise drop the wait mid-flight. Phase 9's drain task is registry-owned, not request-bound — there is no CancelledError to shield against during normal operation. Shielding everywhere makes shutdown unkillable.
- **Holding the registry `_lock` during subprocess I/O.** sessions.py:380 acquires the lock for `sess.closed = True` then releases BEFORE the killpg + shielded wait. Same pattern for Phase 9. Holding the lock during drain creates cross-job head-of-line blocking.
- **Reading `os.environ` from inside lifespan or handlers.** Phase 8 D-24 invariant — bypass D-13's validation if you re-read at lifespan time. Always reference module constants.
- **Calling `await proc.wait()` without `start_new_session=True` upstream.** `killpg` needs the pgroup. `ReToolRunner` already sets `start_new_session=True` (runner.py:223) — Phase 9 inherits this.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Subprocess spawn + drain + log-write + ANSI/UTF-8 head | New spawning logic in `jobs.py` | `ReToolRunner(case_dir, slug, timeout=None)` then `.run(argv)` | Phase 6 already proves the spawn surface. Reusing it gives jobs argv-only, cwd-confinement, pgroup kill, drain-without-deadlock, head-truncation, log-write — for free. |
| FIFO of completed jobs | `list[Job]` + sort-on-evict | `collections.OrderedDict[str, Job]` with `popitem(last=False)` | O(1) FIFO pop; preserves insertion order; stdlib. |
| Job-ID generation | `uuid.uuid4().hex` or `random.randint` | `secrets.token_hex(8)` | Cryptographically random; 64 bits avoids collisions across registry lifetime. Matches sessions.py precedent. |
| Timestamp formatting for log filenames | hand-roll strftime | `artifacts_io.tool_log_path(case_dir, slug)` | Already returns `tool-logs/<UTC>Z-<slug>-<rand4>.txt`. Same shape as Phase 6/7 logs — agents can't tell job logs apart from sync-runner logs (intentional per D-21). |
| Progress notification dispatch | Manual SSE / WebSocket | `ctx.report_progress(progress, total, message)` | FastMCP injects `ctx: Context` automatically when a handler declares it. Per-request scope is exactly right for poll-side push (D-16 Tier-2). |
| JSON-schema validation for `kwargs_schema` | `jsonschema` PyPI dep | Hand-rolled walker (see Pattern below) | Single-use, four-line schema; adding `jsonschema` for this is over-engineering. Verified pyproject.toml has no jsonschema dep. |
| ANSI / UTF-8-boundary truncation | New regex + decode logic | Inline copies of runner.py's helpers per Phase 8 precedent | Phase 8 inlined; Phase 9 mirrors. Two locations is fine — Pythonic duplication is cheaper than cross-primitive coupling. |

**Hand-rolled `kwargs_schema` walker (recommendation):**
```python
def _validate_kwargs(spec: JobToolSpec, kwargs: dict) -> None:
    """Hand-rolled minimal walker. Raises InvalidKwargs(field, expected, got) on first miss.

    Supported schema shapes (sufficient for Phase 9's _sleep_probe + capa specs):
      {field: {"type": "integer", "min": int, "max": int}}
      {field: {"type": "string", "max_length": int}}
      {field: {"type": "boolean"}}
      {field: {"type": "string", "enum": [str, ...]}}
    Unknown fields in kwargs are ignored (forward-compatible).
    """
    if spec.kwargs_schema is None:
        return
    for field, rule in spec.kwargs_schema.items():
        if field not in kwargs:
            continue  # optional unless rule has "required": True (not needed Phase 9)
        val = kwargs[field]
        expected = rule.get("type")
        if expected == "integer":
            if not isinstance(val, int) or isinstance(val, bool):
                raise InvalidKwargs(field, "integer", type(val).__name__)
            if "min" in rule and val < rule["min"]:
                raise InvalidKwargs(field, f">= {rule['min']}", str(val))
            if "max" in rule and val > rule["max"]:
                raise InvalidKwargs(field, f"<= {rule['max']}", str(val))
        elif expected == "string":
            if not isinstance(val, str):
                raise InvalidKwargs(field, "string", type(val).__name__)
            if "max_length" in rule and len(val) > rule["max_length"]:
                raise InvalidKwargs(field, f"length <= {rule['max_length']}", f"length {len(val)}")
            if "enum" in rule and val not in rule["enum"]:
                raise InvalidKwargs(field, f"one of {rule['enum']}", val)
        elif expected == "boolean":
            if not isinstance(val, bool):
                raise InvalidKwargs(field, "boolean", type(val).__name__)
        # Phase 10/11 may add more types (object, array); extend here when needed.
```

## Runtime State Inventory

Phase 9 is greenfield (a new primitive + four new MCP tools + lifespan extensions). No rename / refactor / migration risk. This section is included for completeness:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | None — Phase 9 ships with `JOB_REGISTRY` empty at start, populated at runtime, in-memory only | None |
| Live service config | None | None |
| OS-registered state | None | None |
| Secrets/env vars | 10 new `MCP_GATEWAY_JOB_*` env var NAMES introduced (D-13 + 4 head/tail kb); all are optional with defaults; no live key changes | Document in README during planning |
| Build artifacts | None — pure Python additions; no compiled artifacts | None |

**Nothing renamed; nothing migrated.** Phase 9 is purely additive.

## Common Pitfalls

### Pitfall 1: tqdm/rich progress bars confuse the drain loop

**What goes wrong:** Tools that use `tqdm` or `rich.console.Console` write progress updates with **carriage return** (`\r`) instead of newline (`\n`). A `readline()`-based drain blocks forever waiting for `\n`; a `read(CHUNK)`-based drain captures the carriage-returned bytes but cannot parse them as discrete progress events.

**Why it happens:** Both tqdm and rich are designed for terminal display, not machine parsing. The "progress bar" is a single visual line that gets overwritten in place via ANSI cursor-move and `\r`. There are no newline-terminated events to parse.

**How to avoid:**
1. Use `read(CHUNK)` (Phase 6's pattern, runner.py:120), NOT `readline()` (CONTEXT.md D-09's example).
2. Accept that for tqdm/rich-using tools, `progress_parser = None`. Phase 9 ships capa with `None` because capa uses `rich.Console.status(spinner='dots')` [VERIFIED: capa/loader.py — `rich.console.Console(stderr=True, quiet=disable_progress)` then `console.status("analyzing program...", spinner="dots")`].
3. Phase 10's unblob uses `rich.progress.Progress` with bars that produce newline-terminated milestone events (e.g., "Extracting block 5/10") — that's parseable. Unblob is Phase 10's problem, not Phase 9's.

**Warning signs:** `progress_parser` returns `None` for every line during a real run, despite the tool clearly "showing progress" in a terminal — that's tqdm/rich/spinner with `\r` updates, and the drain is correctly capturing them as opaque bytes.

### Pitfall 2: `asyncio.create_task(...)` without retaining a reference garbage-collects the task

**What goes wrong:** `_spawn_and_drive(job)` is created with `asyncio.create_task(...)` inside `start_tool_job`. If the returned `Task` reference is not retained, Python may garbage-collect it mid-flight, raising "Task was destroyed but it is pending!" and dropping the job.

**Why it happens:** asyncio docs explicitly warn about this — `create_task` returns a weak-reference-style handle.

**How to avoid:** Store the drive task on the `Job` dataclass: `job._drive_task = asyncio.create_task(...)`. The Job is held in `registry._inflight` for its lifetime, transitively keeping the task alive.

### Pitfall 3: `os.killpg` on an already-dead process raises `ProcessLookupError`

**What goes wrong:** Between SIGTERM and SIGKILL, the process may exit (graceful shutdown). The second `os.killpg(pgid, SIGKILL)` raises `ProcessLookupError`.

**How to avoid:** Wrap both killpg calls in `try/except (ProcessLookupError, PermissionError): pass`. Verified pattern at runner.py:246 and sessions.py:306. Idempotent shutdown.

### Pitfall 4: `proc.wait()` after `killpg(SIGKILL)` can still time out if drain tasks aren't cancelled

**What goes wrong:** Pipe drain tasks hold a reader on `proc.stdout`/`proc.stderr`. If those tasks are still running and the pipe is full, `proc.wait()` blocks waiting for the OS to reap.

**How to avoid:** The chunked-read drain (runner.py:120 pattern) doesn't deadlock because `_drain` always drains-and-drops past the head cap. After `killpg(SIGKILL)`, EOF arrives at the pipes naturally and drain exits. The job-level `wait_for(... wait_timeout)` in `registry.cancel` provides defense-in-depth.

### Pitfall 5: Multiple coroutines polling `get_tool_job` produce duplicate `report_progress` notifications

**What goes wrong:** Two concurrent agents (or two parallel tasks of one agent) both poll the same `job_id`. Both see the progress has advanced and both call `ctx.report_progress`, producing duplicate notifications on each agent's MCP request channel.

**Why it (doesn't) happen with the D-16 design:** D-16 specifies `job._last_reported_to: dict[str, tuple[int, int]]` keyed by `ctx.session_id`. Each poller sees its OWN last-reported state, so duplicates on the SAME `session_id` are deduped, but different sessions get independent notifications — which is correct (different agents want their own progress streams).

**How to avoid:** Implement the `_last_reported_to` dict per D-16. Key is `ctx.session_id`. Value is `(progress, progress_total)`. Skip the report if unchanged from last call.

### Pitfall 6: Snapshot dict serialization on every poll is expensive when log files are large

**What goes wrong:** `get_tool_job` returns `stdout_tail` and `stderr_tail` by reading the LAST N KB of `log_path` each poll. For a 200 MB log file, naive `f.read()` then slicing is awful. Naive `f.seek(-N, 2); f.read()` works on Linux but doesn't separate stdout from stderr.

**How to avoid:** Phase 9 deliberately writes stdout and stderr into the SAME log file (runner.py:228-233 opens one sink for both, alternating writes). To extract just stdout-tail from the unified log requires per-line role tags — which Phase 6 doesn't write. **See Open Q1 for the design call here.**

### Pitfall 7: capa's `rich.Console(stderr=True)` produces ANSI escape sequences in the log

**What goes wrong:** rich writes color codes, cursor-move sequences, and box-drawing characters to stderr. The log file gets unreadable noise.

**How to avoid:** runner.py's `_finalize_head` already strips ANSI from the head buffer (runner.py:155). For the on-disk log, ANSI is preserved as-is (this is Phase 6's choice — keep raw bytes for forensic value). Agents reading `log_path` via `get_tool_log` Phase 7 D-25 see the raw bytes including ANSI. capa supports `--debug` or `--quiet` to suppress the spinner; the capa spec's `build_argv` should pass `--quiet`. Verified: `capa/main.py` sets `disable_progress=args.quiet or args.debug` [CITED: github.com/mandiant/capa].

### Pitfall 8: Job timeout vs. ReToolRunner timeout double-cap confusion

**What goes wrong:** If both the runner timeout and the job timeout are set, whichever fires first wins, leading to misleading status codes (e.g., status=succeeded with exit_code=-9 because runner-side timeout fired but job logic didn't notice).

**How to avoid:** Phase 9 wraps ReToolRunner with `timeout=None` (Phase 6 D-04 supports None for "no timeout"). The job-level `asyncio.wait_for(..., effective_timeout)` is the ONLY timeout. Verified at runner.py:173 — `timeout: Optional[float] = None` is the signature; setting it to None disables wait_for.

## Code Examples

### Example 1: Job drive task (D-22)

```python
# jobs.py — registry-owned drive task
async def _spawn_and_drive(self, job: Job) -> None:
    """Construct ReToolRunner with timeout=None, run argv, capture terminal state.

    Owns the asyncio.Task lifetime independent of any MCP request handler.
    """
    try:
        spec = JOB_TOOL_REGISTRY[job.tool]
        case_dir_path = Path(job.case_dir)
        argv = spec.build_argv(case_dir_path, job.kwargs)
        runner = ReToolRunner(
            case_dir=case_dir_path,
            slug=spec.slug,
            timeout=None,  # Job-level wait_for is the boundary (D-08)
        )
        # Status: pending -> running on first await yield
        job.status = "running"
        job.started_at_mono = time.monotonic()

        try:
            result = await asyncio.wait_for(
                runner.run(argv),
                timeout=job.effective_timeout_s,
            )
        except asyncio.TimeoutError:
            # SIGTERM-grace-SIGKILL ladder via cancel()
            await self.cancel(job, reason="timeout")
            job.status = "killed_timeout"
            return

        # Inspect result for cap-exceeded vs success vs failed
        if job._cancel_requested:
            job.status = "cancelled"
        elif job._log_cap_exceeded:
            job.status = "killed_log_cap"
        elif result["exit_code"] == 0:
            job.status = "succeeded"
        else:
            job.status = "failed"
        job._terminal_result = result

    finally:
        job.ended_at_mono = time.monotonic()
        await self._mark_terminal(job)  # writes .json snapshot per D-21
```

### Example 2: Cancel ladder (D-07)

```python
async def cancel(self, job: Job, *, reason: str = "user") -> None:
    """SIGTERM-grace-SIGKILL ladder. Idempotent on terminal jobs."""
    if job.status not in ("pending", "running"):
        return  # terminal jobs are immutable per D-06
    job._cancel_requested = True
    try:
        os.killpg(job.pgid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return  # already dead
    try:
        # D-23: shield is the ONLY place inside Phase 9 that uses shield.
        await asyncio.wait_for(
            asyncio.shield(job.proc.wait()),
            timeout=JOB_CANCEL_GRACE_S,
        )
    except asyncio.TimeoutError:
        try:
            os.killpg(job.pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        await asyncio.shield(job.proc.wait())
    # Drive task's finally-block sets the terminal status when it observes
    # job._cancel_requested == True.
```

**Note:** The above is a sketch. The actual integration with `ReToolRunner` may require restructuring because `ReToolRunner.run()` owns the `proc` reference internally. **See Open Q4 below.**

### Example 3: Snapshot dict construction (D-19)

```python
def snapshot(self, job: Job) -> dict:
    """Return the D-19 snapshot dict. Cheap to call repeatedly (no I/O for head)."""
    if job._terminal_result is not None:
        base = job._terminal_result  # the 12-key dict from runner.run()
    else:
        # Pre-terminal: synthesize Phase 6 D-03 12 keys with sentinels
        base = {
            "exit_code": -1,
            "timed_out": False,
            "duration_s": time.monotonic() - job.started_at_mono if job.started_at_mono else 0.0,
            "stdout_head": str(job._head_buf_stdout),  # populated incrementally
            "stdout_truncated": job._head_truncated_stdout,
            "stdout_bytes_total": job._total_bytes_stdout,
            "stderr_head": str(job._head_buf_stderr),
            "stderr_truncated": job._head_truncated_stderr,
            "stderr_bytes_total": job._total_bytes_stderr,
            "log_path": str(job.log_path_rel),
            "argv": list(job.argv),
            "slug": job.spec.slug,
        }
    # Phase 9 extensions
    base.update({
        "job_id": job.job_id,
        "tool": job.tool,
        "status": job.status,
        "started_at": job.started_at_iso,
        "ended_at": job.ended_at_iso,  # None if non-terminal
        "stdout_tail": _read_log_tail(job.log_path_abs, JOB_STDOUT_TAIL_KB),  # see Open Q1
        "stderr_tail": _read_log_tail(job.log_path_abs, JOB_STDERR_TAIL_KB),  # see Open Q1
        "progress": job.progress,
        "progress_total": job.progress_total,
        "progress_message": job.progress_message,
        "kwargs": dict(job.kwargs),
        "case_dir": job.case_dir,
        "effective_timeout_s": job.effective_timeout_s,
    })
    return base
```

### Example 4: capa spec

```python
def _build_capa_argv(case_dir: Path, kw: dict) -> list[str]:
    """Build argv for capa. kwargs: {sample: sha256-or-path}.

    Resolves sample via tools.samples.resolve_sample (sha256 → uploads/<sha>/...).
    Adds --quiet to suppress the rich Console spinner (Pitfall 7).
    """
    from mcp_gateway.tools import samples  # local import to avoid cycle
    sample_path = samples.resolve_sample(kw["sample"])
    return ["capa", "--quiet", "--json", str(sample_path)]

_CAPA_SPEC = JobToolSpec(
    name="capa",
    slug="capa",
    build_argv=_build_capa_argv,
    default_timeout_s=900.0,  # 15 min — capa on a real PE routinely 1-5 min, defense 3x
    progress_parser=None,  # D-17 VERIFIED: capa uses rich spinner, no parseable progress
    kwargs_schema={"sample": {"type": "string", "max_length": 256}},
    description=(
        "Run Mandiant's capa to identify capabilities of a binary sample. "
        "JSON output. Long-running for real samples (1-5 min typical, up to 15 min cap). "
        "No progress signals — poll get_tool_job for status."
    ),
)
register_job_tool(_CAPA_SPEC)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Block agent on long-running tool with no progress (60s MCP request cap kills the connection mid-analysis) | Submit-and-poll job pattern | This phase (Phase 9, v1.1) | Agents can drive capa/unblob/Ghidra without losing their work to request timeouts |
| Hand-rolled subprocess.Popen in each tool wrapper | Centralized `ReToolRunner` chokepoint (Phase 6) | v1.0→v1.1 | One place to enforce argv-only, pgroup-kill, log capture, timeout |
| Per-session r2 with no analog for one-shot heavy tools | `SessionRegistry` (Phase 8) for r2 + `BackgroundJobRegistry` (Phase 9) for one-shot heavy tools | v1.0→v1.1 | Two complementary registries with parallel lifecycle ownership patterns |
| Server-push progress via SSE (deprecated) | MCP Streamable HTTP + `Context.report_progress` per-request scope | MCP spec 2025-03-26 | Progress notifications work in modern transport; Phase 9 implements the poll-side push variant for jobs |

**Deprecated/outdated:**
- `asyncio.subprocess.Process.communicate()` for long-running streams (blocks until exit, no streaming drain). Phase 6 already avoided this; Phase 9 inherits.

## Assumptions Log

> Claims tagged `[ASSUMED]` in this research. Most decisions are LOCKED by CONTEXT.md; this list is the small residue.

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | capa accepts `--quiet` AND `--json` flags simultaneously and writes JSON to stdout, no progress to stderr | Example 4 / Pitfall 7 | If `--quiet` suppresses `--json` output too, capa returns nothing useful. **Mitigation:** Wave 0 integration test runs `capa --quiet --json <small_sample>` and asserts stdout parses as JSON. If it fails, fall back to `--json` only and accept the spinner noise on stderr. [CITED: capa/main.py shows `disable_progress=args.quiet or args.debug`; usage.md mentions `-j` for JSON] |
| A2 | rich's Console spinner cannot be parsed by line-based progress_parser due to `\r`/cursor escapes | Pitfall 1 | If rich emits any newline events at milestone boundaries, we could parse those. **Mitigation:** Confirmed by running capa locally OR ship `progress_parser=None` and tolerate the gap; JOBS-07 phrasing allows "where the tool can produce progress signals." |
| A3 | `Context.report_progress` is safe to call when the originating MCP request has already returned to the client | D-16 Tier-2 | If FastMCP raises or silently swallows the call after request return, the poll-side push pattern fails. **Mitigation:** D-16 Tier-2 fires only INSIDE `get_tool_job`'s request scope — the request has NOT returned yet, so this is moot for the polled case. The risk only exists if Tier-2 is misused; D-16 specifies the in-handler pattern. |
| A4 | Stdout and stderr written to the same log file (Phase 6's pattern) can be tail-read for "last N KB of stdout only" by re-parsing — **see Open Q1** | D-19 snapshot, Pitfall 6 | If we can't separate roles in the unified log, `stdout_tail` and `stderr_tail` are wrong or duplicated. **Major design call deferred to planner.** |
| A5 | `asyncio.wait_for(asyncio.shield(...), timeout)` works as intended (timeout fires, inner is shielded from outer cancellation) | Cancel ladder D-07 | This is the standard Python pattern. Verified by Phase 6 D-04 usage at runner.py:249 and sessions.py:308. |
| A6 | `MAX_COMPLETED_JOBS = 200` FIFO eviction is sufficient for v1.1 single-team usage | D-10 | If an analyst does >200 jobs in one case session, oldest results fall out of registry. **Mitigation:** D-21 `.json` snapshots preserve full result on disk; `tool-logs/<...>.json` is exposed via Resources. Eviction only impacts the in-memory list. |
| A7 | Phase 9's drain pattern uses chunked read (Phase 6 precedent), NOT readline (CONTEXT.md D-09 example) | Alternatives / Pitfall 1 | **See Open Q2 — this is a CONFLICT between CONTEXT.md and existing code.** Recommendation: chunked read; planner should resolve. |

## Open Questions

### Q1: Per-role tail extraction from a unified stdout+stderr log

**What we know:** runner.py:228-233 opens ONE log file sink and writes both stdout and stderr to it. There are no per-line role tags (no `[stdout]` / `[stderr]` prefixes). The 12-key D-03 dict has `stdout_head` and `stderr_head` from in-memory drain buffers, but the on-disk log is interleaved.

**What's unclear:** How does Phase 9 produce `stdout_tail` and `stderr_tail` (D-19 fields) from the unified log? Three options:
- **(a)** Tail the unified log as one stream and present BOTH tails as identical content with a doc comment "interleaved roles" — agents are mildly misled but no role-parsing logic needed.
- **(b)** Keep per-role in-memory ring buffers in the `Job` for tail (mirror the head buffer approach). Costs ~64 KB of extra in-memory state per running job; eviction post-terminal frees it.
- **(c)** Change Phase 6's log format to tag each line with role (`[O]`/`[E]`) — breaking change for Phase 7 typed wrappers + Phase 8 sessions.

**Recommendation: (b)** — keep per-role ring buffers on `Job`. The cost (64 KB × 4 inflight jobs = 256 KB) is negligible, no Phase 6/7/8 changes required, and `_read_log_tail` is unneeded. Note this changes the snapshot construction in Example 3 above: `stdout_tail` is `str(job._tail_buf_stdout)` not a file read. **Planner should lock this.**

### Q2: Drain pattern — `readline()` (per CONTEXT.md D-09 pseudocode) vs `read(CHUNK)` (per Phase 6's actual code)

**What we know:**
- CONTEXT.md D-09 pseudocode shows `line = await stream.readline()` then byte-counter-based cap check per-line.
- runner.py:120 actual implementation uses `chunk = await stream.read(CHUNK)` with `CHUNK = 64 * 1024`, byte-counter per-chunk.
- The conflict matters because `readline()` blocks waiting for `\n` — tqdm/rich/spinner output (which uses `\r`) would deadlock the drain.

**What's unclear:** Which pattern wins?

**Recommendation:** Use **chunked read** (Phase 6's pattern). The cap-check happens per-chunk; head/tail buffers slice per-byte; progress_parser is called on **buffered line boundaries** rather than on raw chunks. Specifically:
```python
buf = bytearray()
while True:
    chunk = await stream.read(CHUNK)
    if not chunk: break
    total += len(chunk)
    if total > MAX_JOB_LOG_BYTES: ... # kill, set _log_cap_exceeded
    file_sink.write(chunk)
    # update head/tail ring buffers
    buf.extend(chunk)
    # extract complete lines for progress_parser
    while b"\n" in buf:
        line, _, buf = buf.partition(b"\n")
        if spec.progress_parser:
            result = spec.progress_parser(line)
            if result:
                job.progress, job.progress_total, job.progress_message = result
```

**Why not readline:** Phase 6's read-CHUNK pattern is the verified working code. CONTEXT.md's D-09 pseudocode appears to be illustrative — D-09's intent is "counter-based cap, not periodic stat," which is preserved either way. **Planner should accept the chunked read as the binding implementation.**

### Q3: Where does `JobToolSpec.kwargs_schema` validation happen — at registration or at `start_tool_job`?

**What we know:** D-02 / D-05 step 2 says validation happens in `start_tool_job` (per-call). D-13's "kwargs validation at registration time" hint in code_context section §"Established patterns" mentions "the import-time validation pattern carries over for `kwargs_schema` checks at registration time" — but that's about validating the SCHEMA structure (is the schema itself well-formed), not validating CALLER kwargs against the schema.

**What's unclear:** Two distinct checks:
- **(c1)** At `register_job_tool(spec)` import time: is `spec.kwargs_schema` itself well-formed (no unknown rule keys, no impossible min>max)? Optional.
- **(c2)** At `start_tool_job(tool, kwargs)` time: do the caller's `kwargs` match `spec.kwargs_schema`? Required per D-05.

**Recommendation:** Implement **only (c2)** for Phase 9 (per D-05 step 2). Skip (c1) until Phase 10/11 ship enough specs that schema-structure errors become a real risk. For Phase 9's two specs (`_sleep_probe`, `capa`), schemas are 1-2 fields each and developer-authored. **Planner should not enforce (c1).**

### Q4: ReToolRunner internal `proc` reference is not exposed — how does the registry SIGTERM the running proc?

**What we know:** runner.py:217 spawns `proc = await asyncio.create_subprocess_exec(...)` inside `ReToolRunner.run()`. The `proc` reference is a local variable in that method. `Job` cannot reach in and `killpg(job.proc.pid)` unless the runner exposes it.

**What's unclear:** Either:
- **(d1)** Refactor `ReToolRunner.run()` to publish `proc` on the runner instance (`self._proc = proc`) so the registry can access it. Small change to runner.py.
- **(d2)** Reimplement spawn-and-drain in `jobs.py` (don't use ReToolRunner for jobs). Duplicates the chokepoint logic — loses the JOBS-01 "same safety properties" assurance.
- **(d3)** Pass a `proc_callback: Callable[[Process], None]` kwarg to `ReToolRunner.run()` that the runner invokes immediately after spawn, so the registry captures the `proc` reference without ReToolRunner publishing it.

**Recommendation:** **(d3)** — add a `proc_callback` optional kwarg to `ReToolRunner.run()`. This is a 2-line addition to runner.py:
```python
async def run(self, argv: list[str], *, proc_callback: Optional[Callable] = None) -> dict:
    # ... existing spawn ...
    proc = await asyncio.create_subprocess_exec(...)
    if proc_callback is not None:
        proc_callback(proc)  # Job captures pgid here
    # ... rest unchanged ...
```
Then `_spawn_and_drive(job)` passes a lambda: `proc_callback=lambda p: (setattr(job, '_proc', p), setattr(job, 'pgid', os.getpgid(p.pid)))`. **Planner should lock this approach** — it's the smallest surgical change to Phase 6's chokepoint and preserves "all subprocess spawn goes through ReToolRunner" (JOBS-01).

### Q5: Does the `_sleep_probe` need to be filtered out of `list_tool_jobs(state='_specs')` for production agents?

**What we know:** D-03 names it `_sleep_probe` with underscore prefix. CONTEXT.md says "The underscore prefix marks it as internal."

**Recommendation:** `list_tool_jobs(state='_specs')` filters OUT names with leading underscore by default; passing an additional `include_internal: bool = False` parameter exposes them for diagnostics. Hides the probe from production agent agents while preserving test-fixture utility. **Planner: small UX call, low risk.**

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Phase 9 code | ✓ | 3.11+ (container) | — |
| asyncio | stdlib | ✓ | 3.11+ | — |
| `mcp` SDK | FastMCP `Context.report_progress` | ✓ | pinned `>=1.27,<1.28` in pyproject.toml | — |
| `sleep` binary | `_sleep_probe` test spec | ✓ | coreutils (Kali default) | — |
| `sh` / `bash` | `_log_burst_probe` test spec | ✓ | Kali default | — |
| `capa` binary | `_CAPA_SPEC` integration test | Likely ✓ | per Kali container | If absent: `pytest.skip("capa unavailable")` marker, gated by `shutil.which("capa") is None` (matches conftest.py:13 `_require_r2_or_skip` pattern) |
| `pytest`, `pytest-asyncio` | Tests | ✓ | dev extras in pyproject.toml | — |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `capa` on the dev/CI host — fall back to skip-on-missing using the conftest.py pattern. Inside the container image, capa is required to be installed (verify against Dockerfile in planning).

## Validation Architecture

Phase 9 has 6 success criteria + 7 requirements (JOBS-01..JOBS-07). Existing test infrastructure:

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8+ with pytest-asyncio 0.23+ (`asyncio_mode = "auto"`) |
| Config file | `mcp-gateway/pyproject.toml` (`[tool.pytest.ini_options]`) |
| Shared fixtures | `mcp-gateway/tests/conftest.py` (existing fixtures: `bearer_token`, `tmp_upload_dir`, `tmp_status_dir`, `_require_r2_or_skip`) |
| Quick run command | `cd mcp-gateway && pytest -m 'not slow' -x tests/test_jobs*.py tests/test_jobs_tools.py` |
| Full suite command | `cd mcp-gateway && pytest -x` |
| Slow integration | `cd mcp-gateway && pytest -m slow tests/test_jobs_capa.py` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | File | Automated Command | File Exists? |
|--------|----------|-----------|------|-------------------|-------------|
| JOBS-01 | `start_tool_job(tool, kwargs)` returns `job_id`; runs via ReToolRunner | unit | `tests/test_jobs_lifecycle.py::test_start_returns_job_id_and_running_status` | `pytest tests/test_jobs_lifecycle.py::test_start_returns_job_id_and_running_status -x` | ❌ Wave 0 |
| JOBS-01 | Underlying spawn uses argv-only (no `shell=True`) and `start_new_session=True` (pgroup) | regression | `tests/test_jobs_runner_integration.py::test_argv_only_no_shell_invocation` | `pytest tests/test_jobs_runner_integration.py -x` | ❌ Wave 0 |
| JOBS-02 | `get_tool_job(job_id)` returns D-19 25-key snapshot | unit | `tests/test_jobs_lifecycle.py::test_snapshot_shape_locked` | `pytest tests/test_jobs_lifecycle.py::test_snapshot_shape_locked -x` | ❌ Wave 0 |
| JOBS-02 | `get_tool_job` head and tail are populated correctly for completed job | integration | `tests/test_jobs_lifecycle.py::test_completed_job_head_and_tail_populated` | `pytest tests/test_jobs_lifecycle.py::test_completed_job_head_and_tail_populated -x` | ❌ Wave 0 |
| JOBS-03 | `cancel_tool_job` SIGTERMs then SIGKILLs after grace | integration | `tests/test_jobs_cancel.py::test_sigterm_then_sigkill_ladder` | `pytest tests/test_jobs_cancel.py::test_sigterm_then_sigkill_ladder -x` | ❌ Wave 0 |
| JOBS-03 | `cancel_tool_job` is idempotent on terminal jobs | unit | `tests/test_jobs_cancel.py::test_cancel_on_terminal_is_idempotent` | `pytest tests/test_jobs_cancel.py::test_cancel_on_terminal_is_idempotent -x` | ❌ Wave 0 |
| JOBS-04 | `list_tool_jobs(state)` filters by status | unit | `tests/test_jobs_list.py::test_list_filters_by_state` | `pytest tests/test_jobs_list.py -x` | ❌ Wave 0 |
| JOBS-04 | Gateway restart cancels in-flight jobs (registry `__aexit__` kills pgroups) | integration | `tests/test_jobs_lifespan.py::test_restart_cancels_inflight` | `pytest tests/test_jobs_lifespan.py -x` | ❌ Wave 0 |
| JOBS-05 | `MAX_JOB_LOG_MB` cap triggers `killed_log_cap` status | integration | `tests/test_jobs_log_cap.py::test_log_cap_kills_job_with_correct_status` | `pytest tests/test_jobs_log_cap.py -x` | ❌ Wave 0 |
| JOBS-05 | Completed-jobs FIFO eviction at `MAX_COMPLETED_JOBS` | unit | `tests/test_jobs_eviction.py::test_fifo_evicts_oldest_completed` | `pytest tests/test_jobs_eviction.py -x` | ❌ Wave 0 |
| JOBS-05 | Eviction preserves on-disk log file | unit | `tests/test_jobs_eviction.py::test_eviction_preserves_log_file` | `pytest tests/test_jobs_eviction.py::test_eviction_preserves_log_file -x` | ❌ Wave 0 |
| JOBS-06 | Drive-task cancellation → subprocess dead within 200 ms (SC-4 contract) | integration | `tests/test_jobs_cancel.py::test_disconnect_dead_within_200ms` | `pytest tests/test_jobs_cancel.py::test_disconnect_dead_within_200ms -x` | ❌ Wave 0 |
| JOBS-06 | `asyncio.shield` used ONLY in cancel-grace path (D-23) | regression | `tests/test_jobs_internals.py::test_shield_only_in_cancel_grace_path` | `pytest tests/test_jobs_internals.py::test_shield_only_in_cancel_grace_path -x` | ❌ Wave 0 |
| JOBS-07 | `Context.report_progress` called from `get_tool_job` when progress changed | unit (mock Context) | `tests/test_jobs_progress.py::test_report_progress_called_on_changed_state` | `pytest tests/test_jobs_progress.py::test_report_progress_called_on_changed_state -x` | ❌ Wave 0 |
| JOBS-07 | No duplicate `report_progress` for same session_id when state unchanged | unit (mock Context) | `tests/test_jobs_progress.py::test_no_duplicate_progress_per_session` | `pytest tests/test_jobs_progress.py::test_no_duplicate_progress_per_session -x` | ❌ Wave 0 |

### Success Criteria → Test Map (the six from ROADMAP)

| SC | Description | Test Type | File | File Exists? |
|----|-------------|-----------|------|--------------|
| SC-1 | `start_tool_job → job_id`, runs through ReToolRunner with same safety properties | integration | `tests/test_jobs_runner_integration.py` (argv-only + pgroup + cwd containment) | ❌ Wave 0 |
| SC-2 | `get_tool_job`/`cancel_tool_job`/`list_tool_jobs` all functional | integration | `tests/test_jobs_lifecycle.py`, `tests/test_jobs_cancel.py`, `tests/test_jobs_list.py` | ❌ Wave 0 |
| SC-3 | `MAX_JOB_LOG_MB` cap, `killed_log_cap` state, LRU/FIFO cleanup | integration | `tests/test_jobs_log_cap.py` (uses `_log_burst_probe` shell-loop), `tests/test_jobs_eviction.py` | ❌ Wave 0 |
| SC-4 | Client disconnect → subprocess dead within 200 ms (`asyncio.shield` + `killpg`) | integration | `tests/test_jobs_cancel.py::test_disconnect_dead_within_200ms` (uses `_sleep_probe`, drive-task cancellation, `time.monotonic()` delta < 0.2 s) | ❌ Wave 0 |
| SC-5 | `MCP Context.report_progress` for tools that emit progress signals | unit | `tests/test_jobs_progress.py` (mock spec with synthetic `progress_parser` that emits `(5, 10, "step")` on a known stderr fixture) | ❌ Wave 0 |
| SC-6 | Gateway restart cancels in-flight jobs (docstring-documented) | unit + integration | `tests/test_jobs_lifespan.py::test_restart_cancels_inflight`, `tests/test_jobs_docstrings.py::test_d26_disclaimer_present_in_all_tools` | ❌ Wave 0 |

### Additional Tests Called Out in CONTEXT.md

| Test | File | Asserts | Failure Mode Protected |
|------|------|---------|------------------------|
| D-26 disclaimer regression | `tests/test_jobs_docstrings.py::test_d26_disclaimer_present_in_all_tools` | All four tool docstrings contain "In-memory registry — gateway restart cancels" AND "shared across all bearer-token clients" verbatim | An accidental docstring rewrite (e.g., refactor that breaks the `__doc__.replace` splice) silently drops the cross-cutting limitation warning |
| D-15 error-shape closure | `tests/test_jobs_errors.py::test_all_error_paths_return_one_of_four_shapes` | Every error path tested produces exactly one of the four D-15 dict shapes; no `pytest.raises(...)` on the MCP-tool surface | A `raise ValueError(...)` accidentally leaking through the MCP tool boundary, which would fail FastMCP serialization |
| D-21 sibling .json snapshot | `tests/test_jobs_lifecycle.py::test_terminal_writes_json_snapshot_sibling` | After job reaches terminal state, file `tool-logs/<ts>-<slug>-<rand4>.json` exists alongside the `.txt` log, contains full snapshot | An eviction destroys the in-memory entry before the snapshot is persisted, losing audit trail |
| capa integration | `tests/test_jobs_capa.py::test_capa_succeeds_on_known_sample` (marked `@pytest.mark.slow` and gated by `shutil.which("capa")`) | `start_tool_job("capa", {"sample": "<sha>"})` reaches `status == "succeeded"`; log file exists and is non-empty; sibling `.json` parseable | Phase 9's surface works for a real Kali tool end-to-end (not just synthetic probes) |
| spec.kwargs_schema rejection | `tests/test_jobs_validation.py::test_invalid_kwargs_returns_d15_error_dict` | `start_tool_job("_sleep_probe", {"seconds": -1})` returns the D-15 #4 invalid-kwargs error dict | Hand-rolled validator misses negative-int rejection or other boundary cases |
| Lifespan nesting LIFO | `tests/test_jobs_lifespan.py::test_lifo_unwind_jobs_before_sessions_before_backend` | On lifespan exit, `BackgroundJobRegistry.__aexit__` completes before `SessionRegistry.__aexit__` (assert ordering via instrumented mock contexts) | A v1.2 refactor that swaps the nesting silently breaks "kill jobs before their r2 sessions go away" |
| Concurrency cap | `tests/test_jobs_cap.py::test_max_jobs_inflight_returns_d15_error` | Submit `MAX_JOBS_INFLIGHT + 1` jobs; the (n+1)th returns the D-15 #1 cap-reached error dict | Hidden queueing introduced inadvertently |

### Sampling Rate

- **Per task commit:** `pytest -m 'not slow' -x tests/test_jobs*.py` (target: < 30 s total)
- **Per wave merge:** `pytest -x` (full suite, < 90 s expected based on existing infra)
- **Phase gate:** `pytest -x && pytest -m slow tests/test_jobs_capa.py` (full suite green + capa integration)

### Wave 0 Gaps

All test files for Phase 9 are NEW. To be created in Wave 0:

- [ ] `tests/test_jobs_lifecycle.py` — covers JOBS-01, JOBS-02, SC-1, SC-2, D-21
- [ ] `tests/test_jobs_cancel.py` — covers JOBS-03, JOBS-06, SC-4
- [ ] `tests/test_jobs_list.py` — covers JOBS-04, list filtering, `_specs` magic state
- [ ] `tests/test_jobs_log_cap.py` — covers JOBS-05 log cap, SC-3 (uses `_log_burst_probe`)
- [ ] `tests/test_jobs_eviction.py` — covers JOBS-05 FIFO eviction, log preservation
- [ ] `tests/test_jobs_lifespan.py` — covers JOBS-04 restart-cancels, SC-6, LIFO unwind D-25
- [ ] `tests/test_jobs_progress.py` — covers JOBS-07, SC-5 (mock Context.report_progress; synthetic parser)
- [ ] `tests/test_jobs_internals.py` — D-23 shield-only-in-cancel-grace regression
- [ ] `tests/test_jobs_docstrings.py` — D-26 disclaimer regression
- [ ] `tests/test_jobs_errors.py` — D-15 four-shape closure
- [ ] `tests/test_jobs_validation.py` — kwargs_schema rejection paths
- [ ] `tests/test_jobs_cap.py` — D-11 concurrency cap
- [ ] `tests/test_jobs_runner_integration.py` — argv-only / pgroup / cwd integration with ReToolRunner
- [ ] `tests/test_jobs_capa.py` — `@pytest.mark.slow` + `shutil.which("capa")` gate; end-to-end with real binary
- [ ] `tests/conftest.py` extension — add `_require_capa_or_skip` helper (matches `_require_r2_or_skip` at line 13)

No new framework install needed — `pytest`, `pytest-asyncio`, and the `slow` marker are already configured in pyproject.toml.

## Sources

### Primary (HIGH confidence)

- **`mcp-gateway/src/mcp_gateway/runner.py`** lines 1-313 — `ReToolRunner`, `_drain`, `_env_int/_env_float`, `_truncate_to_utf8_boundary`, `_ANSI_ESCAPE`, the 12-key D-03 result dict, chunked-read drain pattern, `start_new_session=True`, `asyncio.shield(proc.wait())` cancel pattern
- **`mcp-gateway/src/mcp_gateway/sessions.py`** lines 1-459 — `SessionRegistry` async-context-manager template, `_env_float`/`_env_int` inlined (Phase 8 precedent), `SessionCapReached.to_dict()` error-shape pattern, parallel-kill on `__aexit__`, `strip_ansi`/`truncate_for_response` inlined
- **`mcp-gateway/src/mcp_gateway/app.py`** lines 91-163 — Lifespan nested-async-with pattern in both backend and no-backend branches; `session_state.SESSION_REGISTRY` set/clear in try/finally
- **`mcp-gateway/src/mcp_gateway/session_state.py`** lines 1-19 — Module-level state slot pattern; `PINNED_BACKEND` and `SESSION_REGISTRY` precedents
- **`mcp-gateway/src/mcp_gateway/artifacts_io.py`** lines 33-139 — `EXPANDED_CASE_SUBDIRS` already contains `tool-logs` (line 35), `tool_log_path(case_dir, slug)` signature returns Path with shape `case_dir/tool-logs/<UTC>Z-<slug>-<rand4>.txt`; ensure_subdir is required before tool_log_path use
- **`mcp-gateway/src/mcp_gateway/tools/r2_sessions.py`** lines 1-404 — `register(mcp)` pattern, docstring `.replace("{_FULL_DISCLAIMER}", _SESS_05_DISCLAIMER_FULL)` splice, `_require_registry` helper, module-attribute access (`sessions.MAX_SESSIONS` rather than `from sessions import MAX_SESSIONS`)
- **`mcp-gateway/src/mcp_gateway/tools/__init__.py`** lines 27-53 — `register_all_tools` adds one import + one `<module>.register(mcp)` call per phase
- **`mcp-gateway/src/mcp_gateway/tools/case_dirs.py`** lines 1-23 — `resolve_case_dir(case_dir) -> str`; STATUS_ROOT containment
- **`mcp-gateway/pyproject.toml`** — pinned deps; **NO jsonschema dep**; `mcp>=1.27,<1.28`; pytest-asyncio + pytest 8
- **`mcp-gateway/tests/test_runner.py`** lines 64-78 — Existing CancelledError → killpg-within-200ms test (`test_cancel_propagates_to_killpg`); Phase 9's SC-4 test mirrors this structure
- **`mcp-gateway/tests/conftest.py`** lines 1-40 — `_require_r2_or_skip` helper pattern; Phase 9 adds `_require_capa_or_skip` analogously
- **`.planning/phases/09-background-job-system/09-CONTEXT.md`** — All D-01..D-26 locked decisions, Claude's Discretion section, deferred items
- **`.planning/REQUIREMENTS.md`** lines 64-71 — JOBS-01..JOBS-07 verbatim, Out of Scope items

### Secondary (MEDIUM confidence)

- **mcp Python SDK 1.27.0 `Context.report_progress`** signature `async def report_progress(self, progress: float, total: float | None = None, message: str | None = None) -> None`. [CITED: https://github.com/modelcontextprotocol/python-sdk]
- **capa source — `capa/loader.py`** — uses `rich.console.Console(stderr=True).status("analyzing program...", spinner="dots")`. [CITED: https://github.com/mandiant/capa]
- **capa source — `capa/main.py`** — `disable_progress=args.quiet or args.debug`, confirming `--quiet` suppresses the spinner. [CITED: https://github.com/mandiant/capa]
- **capa usage.md** — `-j` is the JSON output flag; recommended for "Scripting, CI, one-off analysis." [CITED: https://github.com/mandiant/capa/blob/master/doc/usage.md]

### Tertiary (LOW confidence)

- capa's exit code semantics on parse error vs no-capabilities-found (assumed: exit 1 on real error, exit 0 on no-match). Worth confirming during Wave 0 integration test.
- rich Console's exact byte sequence emitted on stderr during a spinner cycle. Confirmed semantically (cursor moves + `\r`) but the exact bytes might vary across rich versions. Mitigation: D-17 ships `progress_parser=None` for capa, so the bytes are written to the log as raw and the parser is bypassed entirely.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — every library/component already in use in the codebase; verified via direct file reads
- Architecture: HIGH — three established precedents (Phase 6 runner, Phase 8 sessions, Phase 7 tools) provide template patterns for every Phase 9 module
- Pitfalls: HIGH-MEDIUM — Pitfall 1 (tqdm/rich) is verified by reading capa source; Pitfall 5 (duplicate progress) is a design pattern from D-16, not an experienced failure; Pitfall 6 (tail extraction) is an open design question (Q1)
- Open questions: MEDIUM — five concrete questions; recommendations provided for each; planner makes the final call

**Research date:** 2026-05-19
**Valid until:** 2026-06-18 (30 days for the stable mcp-gateway codebase patterns; revisit if mcp SDK bumps past 1.28 or if capa adopts a different progress library)

## RESEARCH COMPLETE

**Phase:** 9 - Background Job System
**Confidence:** HIGH

### Key Findings

1. **capa progress emission verified-and-refuted:** capa uses `rich.console.Console(stderr=True).status(spinner='dots')`, NOT tqdm or newline-emitting logs. D-17's capa `progress_parser` MUST be `None`. The capa spec ships `--quiet --json` argv; progress fields stay None throughout the capa run. JOBS-07 is still satisfied per its conditional phrasing.
2. **Phase 6 drain pattern is chunked-read, NOT readline:** CONTEXT.md D-09's `await stream.readline()` pseudocode conflicts with the verified `await stream.read(CHUNK)` in runner.py. Phase 9 should use chunked-read with per-line progress_parser dispatch on buffered `\n` boundaries (resolved in Open Q2).
3. **No jsonschema dep — hand-roll kwargs_schema validation:** pyproject.toml has no jsonschema; pydantic is transitive-only. Hand-rolled 30-line walker covers Phase 9's two specs and Phase 10/11's foreseeable specs. Recommendation locked.
4. **`ReToolRunner.proc` is internal — add `proc_callback` kwarg:** Job registry needs the `proc` reference for `killpg`; smallest surgical change is a 2-line `proc_callback` optional kwarg added to `ReToolRunner.run()` (Open Q4).
5. **Per-role tail buffers, not file re-parsing:** Unified stdout+stderr log file has no role tags. Recommend per-role ring buffers on `Job` (Open Q1) rather than role-tagging Phase 6's log format.
6. **All Phase 8 precedents are directly reusable:** Inline `_env_float`/`_env_int`, inline `strip_ansi`/`truncate_for_response`, docstring `.replace()` splice for D-26 disclaimer, `register_all_tools` += 1 import + 1 register call, `app.py::lifespan` += 1 nested async-with in both branches.

### File Created

`/home/cervon/Code/MARE-MCP-Toolbox/.planning/phases/09-background-job-system/09-RESEARCH.md`

### Confidence Assessment

| Area | Level | Reason |
|------|-------|--------|
| Standard Stack | HIGH | Every library already in pyproject.toml; verified |
| Architecture | HIGH | Three established Phase 6/7/8 precedents replicated verbatim |
| Pitfalls | HIGH | Verified via direct source reads (capa, runner.py, sessions.py) |
| Validation Architecture | HIGH | Test framework already configured; pattern (one test file per concern) matches existing test/test_*.py layout |

### Open Questions for Planner

5 design calls surfaced (Q1-Q5). Recommendations provided for each:
- Q1: Per-role tail via in-memory ring buffers (not log-file re-parsing)
- Q2: Chunked-read drain (Phase 6 pattern), NOT readline
- Q3: kwargs_schema validation at call-time only (skip registration-time schema validation for Phase 9)
- Q4: Add `proc_callback` kwarg to `ReToolRunner.run()` for registry's `killpg` access
- Q5: `_specs` filters underscore-prefixed names by default; `include_internal=True` exposes them

### Ready for Planning

Research complete. Planner can now create PLAN.md files. Key locked references for the planner:
- D-01..D-26 in CONTEXT.md (do not redesign)
- Open Q1-Q5 recommendations (planner makes the final call)
- 15 new test files in Wave 0 (listed in Validation Architecture section)
- One surgical 2-line addition to `runner.py` (`proc_callback` kwarg) is the only change outside Phase 9's own new modules
