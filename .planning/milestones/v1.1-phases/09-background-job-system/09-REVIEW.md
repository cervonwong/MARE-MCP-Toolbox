---
phase: 09-background-job-system
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 29
files_reviewed_list:
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/src/mcp_gateway/jobs.py
  - mcp-gateway/src/mcp_gateway/runner.py
  - mcp-gateway/src/mcp_gateway/session_state.py
  - mcp-gateway/src/mcp_gateway/tools/__init__.py
  - mcp-gateway/src/mcp_gateway/tools/jobs.py
  - mcp-gateway/tests/jobs/__init__.py
  - mcp-gateway/tests/jobs/conftest.py
  - mcp-gateway/tests/jobs/test_cancel_grace.py
  - mcp-gateway/tests/jobs/test_capa_integration.py
  - mcp-gateway/tests/jobs/test_disconnect_200ms.py
  - mcp-gateway/tests/jobs/test_docstring_disclaimer.py
  - mcp-gateway/tests/jobs/test_errors.py
  - mcp-gateway/tests/jobs/test_get_tool_job.py
  - mcp-gateway/tests/jobs/test_lifecycle_status.py
  - mcp-gateway/tests/jobs/test_lifespan_integration.py
  - mcp-gateway/tests/jobs/test_list_tool_jobs.py
  - mcp-gateway/tests/jobs/test_log_cap.py
  - mcp-gateway/tests/jobs/test_lru_retention.py
  - mcp-gateway/tests/jobs/test_progress.py
  - mcp-gateway/tests/jobs/test_registry_lifecycle.py
  - mcp-gateway/tests/jobs/test_spec_validation.py
  - mcp-gateway/tests/jobs/test_start_tool_job.py
  - mcp-gateway/tests/jobs/test_terminal_snapshot_json.py
  - mcp-gateway/tests/jobs/test_timeout.py
  - mcp-gateway/tests/test_runner.py
  - mcp-gateway/tests/test_tool_list.py
  - mcp-gateway/tests/test_tools_jobs_smoke.py
findings:
  critical: 0
  warning: 5
  info: 7
  total: 12
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-05-19T00:00:00Z
**Depth:** standard
**Files Reviewed:** 29
**Status:** issues_found

## Summary

Phase 9 implements the background-job subsystem on top of FastMCP, layering an
in-memory `BackgroundJobRegistry`, a subprocess drive loop with per-role drain
and ring buffers, and four MCP-surface tools (start/get/cancel/list_tool_jobs).
The architecture is well-disciplined: argv-only spawn, `start_new_session=True`
for killpg, asyncio.shield around the cancellation grace window, lock-free
subprocess I/O, hand-rolled kwargs validator avoiding a jsonschema dependency,
and module-attribute access for test-friendly reloads. Errors are dictified
through four locked shapes; the regression tests for the verification gap
(CR-01/CR-02: capa raising out of the MCP boundary) are present and assert the
boundary contract.

The findings below are non-blocking quality concerns -- no Critical issues
were found. The main warnings cluster around concurrency edges in `_drain`
during log-cap exceedance, snapshot reads without a lock, and a few minor
correctness asymmetries between `runner.py`'s ANSI handling and `jobs.py`'s.
Tests are thorough; a handful of style/clarity nits are noted as Info.

## Warnings

### WR-01: Both drains can race the log-cap branch and emit duplicate kill markers

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:417-430`
**Issue:** When the combined byte cap is exceeded, each drain task independently
takes the cap-exceeded branch: it writes its truncated remainder, writes the
`MARE_JOB_KILLED_LOG_CAP` marker, and SIGKILLs the pgroup. Because stdout and
stderr drains run concurrently via `asyncio.gather`, both can decide the cap is
hit on the same tick (or in quick succession before EOF arrives) and each will
write its own marker line. The on-disk log may then contain two trailing
markers, only one of which is the "real" one. `test_log_cap.py` masks this
because it asserts `endswith(MARKER)` -- a duplicate marker still satisfies the
suffix check.
**Fix:** Make the cap-exceeded handler idempotent within `_drain` by gating the
marker-write and the `killpg` call on `job._log_cap_exceeded` so the second
drain to arrive sees the flag already set and skips its branch:
```python
if job.log_bytes_written + n > MAX_JOB_LOG_BYTES:
    if not job._log_cap_exceeded:
        job._log_cap_exceeded = True
        allowed = max(0, MAX_JOB_LOG_BYTES - job.log_bytes_written)
        if allowed > 0:
            file_sink.write(chunk[:allowed])
            job.log_bytes_written += allowed
        file_sink.write(b"\n=== MARE_JOB_KILLED_LOG_CAP ===\n")
        if job.pgid is not None:
            try:
                os.killpg(job.pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
    return
```

### WR-02: `_build_snapshot` reads mutable Job state without acquiring the registry lock

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:707-755`
**Issue:** `_build_snapshot` is invoked from `get_tool_job`, `cancel_tool_job`,
and `list_tool_jobs` -- all of which can run concurrently with the drive task
mutating the same `Job` instance (head/tail buffers, byte counters,
progress fields, status, ended_at). The registry's `_lock` is documented as
guarding `_inflight`/`_completed`, but `_build_snapshot` reads through the Job
reference without holding it. With deques and bytearrays the GIL prevents
corruption per-operation, but composite reads can observe partial updates
(e.g., `stdout_bytes_total` newer than `stdout_head_buf`). The 25-key snapshot
contract does not currently document this skew, and `list_tool_jobs` builds
N snapshots in a loop without coordination.
**Fix:** Either (a) document explicitly that snapshots are best-effort point-
in-time approximations and add a single comment to that effect in
`_build_snapshot`, or (b) acquire `_lock` for the duration of the read and
copy out the primitive scalars + `bytes(...)` of the buffers before formatting.
Option (a) is the pragmatic choice given the existing test contract; in that
case add this docstring note:
```python
def _build_snapshot(self, job: Job) -> dict:
    """... Snapshot is a best-effort read of live state without holding the
    registry lock; concurrent drain updates can produce small skew between
    byte counters and ring-buffer contents (acceptable per Phase 9 D-19)."""
```

### WR-03: `_strip_ansi` runs after UTF-8 decode in `jobs.py` but on bytes in `runner.py` -- inconsistent escape handling

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:92-96, 722-725`
**Issue:** `runner.py` strips ANSI on the raw bytes BEFORE decode (line 158
`_ANSI_ESCAPE.sub(b"", head_bytes)`). `jobs.py` decodes first with
`errors="replace"` and THEN strips ANSI on text. When an ANSI escape contains
or is adjacent to non-UTF-8 bytes (unlikely for clean tools, possible for
tools that emit raw memory), the decode step inserts U+FFFD replacement
characters which may break the regex match, leaving ANSI fragments in the
snapshot. The two paths diverge in observable behavior for the same input.
**Fix:** Mirror the runner.py ordering -- ANSI-strip on bytes first, then
decode. Add a bytes regex to jobs.py and apply it in `_build_snapshot` before
decoding `bytes(job.stdout_head_buf)`:
```python
_ANSI_ESCAPE_BYTES = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")

def _strip_ansi_bytes(buf: bytes) -> bytes:
    return _ANSI_ESCAPE_BYTES.sub(b"", buf)

# in _build_snapshot:
stdout_head_text = _strip_ansi_bytes(bytes(job.stdout_head_buf)).decode("utf-8", errors="replace")
```

### WR-04: `cancel_tool_job` uses `await asyncio.sleep(0)` as a synchronisation primitive

**File:** `mcp-gateway/src/mcp_gateway/tools/jobs.py:255-258`
**Issue:** After calling `registry.cancel(...)`, the code does
`await asyncio.sleep(0)` "to let the drive task's finally-block settle status
to terminal." A single yield is not a reliable synchronisation point -- the
drive task's finally block may need multiple awaits (e.g., the json snapshot
write, the lock acquire in `_mark_terminal`) before it sets the terminal
status. The snapshot returned from `cancel_tool_job` may therefore still show
`status="running"` under load even though the kill has been issued, leading
to user-visible confusion. `test_cancel_grace.py::test_cancel_running_long_job`
relies on this implicitly when asserting `snap.get("status") == "cancelled"`.
**Fix:** Await the drive task directly once cancellation has been issued:
```python
if not was_terminal:
    await registry.cancel(job, reason="user")
    # Wait for the drive task to actually settle terminal status.
    if job._drive_task is not None:
        try:
            await asyncio.shield(job._drive_task)
        except (asyncio.CancelledError, Exception):
            pass  # drive task swallows its own errors via _spawn_and_drive
```

### WR-05: `submit()` checks the inflight cap and inserts the Job under two separate lock acquisitions, opening a small TOCTOU window

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:545-572`
**Issue:** The cap check at line 546 (`len(self._inflight) >= self._max_inflight`)
runs inside the lock, but the actual insertion at line 572
(`self._inflight[job_id] = job`) is in a *second* lock acquisition AFTER
`build_argv` has run. Between the two lock holds, additional `submit()` calls
can pass their cap checks while none of them has yet inserted. With three
concurrent submits against `max_inflight=2` (and two already in-flight),
all three can see "2 < 2 false" at separate moments and all three eventually
insert, producing 3 in-flight jobs (cap violated). The race is narrow but
real -- `build_argv` is fast for `_sleep_probe` (no I/O) but for `capa` it
calls `samples.resolve_sample` which does filesystem work and significantly
widens the window.
**Fix:** Insert a placeholder Job under the same lock that performs the cap
check, so the cap is honoured atomically. Then backfill argv / log paths
outside the lock, and remove the placeholder on `build_argv` failure:
```python
async with self._lock:
    if len(self._inflight) >= self._max_inflight:
        raise JobCapReached(inflight=len(self._inflight), cap=self._max_inflight)
    job_id = secrets.token_hex(8)
    while job_id in self._inflight or job_id in self._completed:
        job_id = secrets.token_hex(8)
    placeholder = Job(
        job_id=job_id, tool=spec.name, spec=spec, kwargs=dict(kwargs),
        case_dir=case_dir_resolved, argv=[],
        effective_timeout_s=effective_timeout_s,
        log_path_abs=Path("/"), log_path_rel="",
    )
    self._inflight[job_id] = placeholder

try:
    case_dir_path = Path(case_dir_resolved)
    ensure_subdir(case_dir_path, "tool-logs")
    argv = spec.build_argv(case_dir_path, kwargs)
    log_abs = tool_log_path(case_dir_path, spec.slug)
    placeholder.argv = list(argv)
    placeholder.log_path_abs = log_abs
    placeholder.log_path_rel = str(log_abs.relative_to(case_dir_path))
except Exception:
    async with self._lock:
        self._inflight.pop(job_id, None)
    raise
```

## Info

### IN-01: Duplicate env-helper functions across `jobs.py` and `runner.py`

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:49-68`, `mcp-gateway/src/mcp_gateway/runner.py:55-74`
**Issue:** `_env_int` and `_env_float` are duplicated verbatim across both
modules. The jobs.py file calls out "inlined per Q4 -- avoid runner.py /
sessions.py cross-import" but that rationale isn't load-bearing -- a small
`mcp_gateway/_env.py` leaf module would be importable by both without cycles.
**Fix:** Extract `_env_int` / `_env_float` to a leaf module
`mcp_gateway/_env.py` and import from there in both `jobs.py` and `runner.py`.
Phase 8 `sessions.py` can later adopt the same module.

### IN-02: `_validate_kwargs` does not support `enum` on integer fields

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:274-280`
**Issue:** The validator supports `enum` for `string` types but not for
`integer`. No current spec needs it, but the docstring on line 256-263 lists
the supported shapes; future spec authors may try `{"type": "integer",
"enum": [1, 2, 3]}` and find it silently ignored.
**Fix:** Add the same `enum` branch to the integer block, or document the
omission explicitly: "Note: enum is supported on string only".

### IN-03: `_build_capa_argv` ignores its `case_dir` parameter

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:356-366`
**Issue:** The function takes `case_dir: Path` but never uses it -- it calls
`samples.resolve_sample(sample_ref)` directly without any case-scoping. Sample
resolution happens against the global `samples.STATUS_ROOT` rather than
against the job's `case_dir`. This is documented behaviour elsewhere in the
codebase but is non-obvious from `_build_capa_argv` alone.
**Fix:** Add a one-line comment clarifying that `case_dir` is intentionally
unused because `resolve_sample` already enforces STATUS_ROOT confinement:
```python
def _build_capa_argv(case_dir: Path, kw: dict) -> list[str]:
    # case_dir is the cwd for the child process; sample lookup is STATUS_ROOT-
    # scoped via samples.resolve_sample (not case-scoped).
    ...
```

### IN-04: `cancel()` swallows `PermissionError` silently with no logging

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:602-616, 426-429`
**Issue:** Both `os.killpg` sites in `cancel()` silently `pass` on
`PermissionError`. If the gateway's UID ever loses permission to signal a
child it spawned (unusual but possible with namespacing), the job will hang
silently with no log breadcrumb. The same pattern in `_drain` (line 428) has
the same gap.
**Fix:** Log at debug level when these exceptions fire:
```python
except (ProcessLookupError, PermissionError) as e:
    log.debug("[jobs] killpg pgid=%s failed: %s", job.pgid, e)
```

### IN-05: `test_terminal_snapshot_json.py` does not validate timestamp parseability

**File:** `mcp-gateway/tests/jobs/test_terminal_snapshot_json.py:25-42`
**Issue:** Minor: the test asserts `loaded["ended_at"] is not None` but
doesn't verify the ISO string is parseable. A future regression that produces
malformed timestamps (e.g., None on `pending` path, or non-ISO strings) would
slip through.
**Fix:** Add `from datetime import datetime; datetime.fromisoformat(loaded["ended_at"])`
to assert the format is parseable.

### IN-06: `asyncio.get_event_loop()` is deprecated when no loop is running (Python 3.12+)

**File:** `mcp-gateway/tests/jobs/test_cancel_grace.py:27-28`
**Issue:** `asyncio.get_event_loop().time()` is called inside an `async def`
helper. Inside a running loop it works, but the recommended replacement is
`asyncio.get_running_loop().time()`. The deprecation warning is suppressed in
async context for now but the idiom is being phased out.
**Fix:** Replace with `asyncio.get_running_loop().time()` in both occurrences
(lines 27, 28).

### IN-07: Comment in `test_progress.py::test_ctx_different_session_does_report` could sharpen test intent

**File:** `mcp-gateway/tests/jobs/test_progress.py:84-99`
**Issue:** The test asserts `ctx_a.calls == [(5, 10, "halfway")]` and
`ctx_b.calls == [(5, 10, "halfway")]` -- which is correct per the dedup
contract, but the assertions are silent on what would happen if a third call
on `ctx_a` somehow leaked through (e.g., due to a regression that breaks
dedup keying). Coverage-wise this is fine; clarity-wise the intent could be
sharper.
**Fix:** Add a brief comment above the assertions: `# Each session must get
its own first-time push; subsequent same-state polls within one session are
dedup'd (covered by test_ctx_dedup_same_session_no_resend).`

---

_Reviewed: 2026-05-19T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
