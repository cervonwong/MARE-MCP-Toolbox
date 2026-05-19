---
phase: 09-background-job-system
reviewed: 2026-05-19T00:00:00Z
depth: standard
files_reviewed: 26
files_reviewed_list:
  - mcp-gateway/src/mcp_gateway/jobs.py
  - mcp-gateway/src/mcp_gateway/tools/jobs.py
  - mcp-gateway/src/mcp_gateway/runner.py
  - mcp-gateway/src/mcp_gateway/session_state.py
  - mcp-gateway/src/mcp_gateway/app.py
  - mcp-gateway/src/mcp_gateway/tools/__init__.py
  - mcp-gateway/tests/jobs/conftest.py
  - mcp-gateway/tests/jobs/test_spec_validation.py
  - mcp-gateway/tests/jobs/test_registry_lifecycle.py
  - mcp-gateway/tests/jobs/test_start_tool_job.py
  - mcp-gateway/tests/jobs/test_lifecycle_status.py
  - mcp-gateway/tests/jobs/test_get_tool_job.py
  - mcp-gateway/tests/jobs/test_list_tool_jobs.py
  - mcp-gateway/tests/jobs/test_cancel_grace.py
  - mcp-gateway/tests/jobs/test_timeout.py
  - mcp-gateway/tests/jobs/test_log_cap.py
  - mcp-gateway/tests/jobs/test_disconnect_200ms.py
  - mcp-gateway/tests/jobs/test_progress.py
  - mcp-gateway/tests/jobs/test_errors.py
  - mcp-gateway/tests/jobs/test_lru_retention.py
  - mcp-gateway/tests/jobs/test_docstring_disclaimer.py
  - mcp-gateway/tests/jobs/test_terminal_snapshot_json.py
  - mcp-gateway/tests/jobs/test_lifespan_integration.py
  - mcp-gateway/tests/jobs/test_capa_integration.py
  - mcp-gateway/tests/test_tool_list.py
  - mcp-gateway/tests/test_runner.py
findings:
  critical: 3
  warning: 6
  info: 5
  total: 14
status: issues_found
---

# Phase 9: Code Review Report

**Reviewed:** 2026-05-19
**Depth:** standard
**Files Reviewed:** 26
**Status:** issues_found

## Summary

Phase 9 implements the background-job system: a `BackgroundJobRegistry` async-context-manager primitive (`jobs.py`) plus a four-tool MCP surface (`tools/jobs.py`). The implementation is deliberate, well-documented against decision tags (D-01..D-26, Q1..Q5), and the test suite is dense. Subprocess lifecycle handling (start_new_session + killpg + shielded wait), LRU eviction with on-disk log preservation, and the LIFO unwind ordering in `app.py` are all sound.

The phase has **three Critical issues that violate the D-15 "tools never raise" contract** at the MCP boundary, all in the `start_tool_job` flow:

1. `spec.build_argv(...)` is called inside `BackgroundJobRegistry.submit` BEFORE any try/except in `tools/jobs.py::start_tool_job`, and `_build_capa_argv` calls `samples.resolve_sample` which raises `ValueError` / `FileNotFoundError` on bad input -- these propagate out of the MCP tool, contradicting the contract enforced by `test_no_tool_handler_raises`.
2. `_build_capa_argv` raises a bare `KeyError("sample")` when the required kwarg is missing -- the hand-rolled validator has no required-fields concept, so a perfectly-valid-looking call `start_tool_job(tool="capa", kwargs={}, case_dir=...)` crashes with an uncaught KeyError.
3. A submit-cap race in `BackgroundJobRegistry.submit` can briefly exceed `max_inflight`: the cap check, id reservation, and inflight-insertion happen in two separate critical sections with file/path work in between, so two concurrent submits at `inflight == cap - 1` can both pass the check and both insert.

Several Warning-level concerns center on cancel/status correctness: cancel-before-spawn marks a job that ran-to-completion as `cancelled` (misleading), `cancel_tool_job` returns the snapshot after only a single `await asyncio.sleep(0)` (snapshot may still show `running`), and `line_buf` in `_drain` is unbounded for stderr streams without newlines.

The test suite is thorough for the happy paths but does not exercise: missing-kwarg paths for tools with required fields, the submit-cap race, or `cancel_tool_job` racing the drive task to terminal status.

## Critical Issues

### CR-01: `capa` argv-builder raises uncaught exceptions from inside `start_tool_job`

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:353-363` (definition) and `mcp-gateway/src/mcp_gateway/jobs.py:550-552` (call site inside `submit`)

**Issue:** `_build_capa_argv` calls `samples.resolve_sample(sample_ref)`, which raises `ValueError` (bad type, traversal, not-under-allowed-prefix) or `FileNotFoundError` (unknown sha256 / empty dir). `BackgroundJobRegistry.submit` invokes `spec.build_argv(case_dir_path, kwargs)` at line 552, OUTSIDE any try/except. In `tools/jobs.py::start_tool_job` (line 158-166), only `JobCapReached` is caught. Result: a caller passing `kwargs={"sample": "../etc/passwd"}` or `kwargs={"sample": "deadbeef..."}` (non-existent sha256) gets the exception propagated out through the MCP boundary -- this directly violates D-15 ("tools never raise") which the test `test_no_tool_handler_raises` claims to enforce, though the test only exercises the happy-error paths (unknown tool, not-found, invalid-kwargs schema miss).

**Fix:** Wrap the `submit` call (or the inner `build_argv` call) and translate to a D-15 `InvalidKwargs` dict shape:

```python
# In tools/jobs.py::start_tool_job, replace the existing submit try/except:
try:
    job = await registry.submit(
        spec=spec,
        kwargs=kwargs or {},
        case_dir_resolved=case_dir_resolved,
        effective_timeout_s=effective_timeout,
    )
except JobCapReached as e:
    return e.to_dict()
except (ValueError, FileNotFoundError, KeyError, OSError) as e:
    # build_argv or path-resolution failure
    return InvalidKwargs(
        field="kwargs",
        expected="valid per-tool argv inputs",
        got=f"{type(e).__name__}: {e}",
    ).to_dict()
```

Alternatively, push the catch inside `submit` itself so the registry primitive guarantees no raise from a build_argv miss.

---

### CR-02: Missing required kwarg crashes with bare KeyError (capa)

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:361` and `mcp-gateway/src/mcp_gateway/jobs.py:254-287`

**Issue:** `_build_capa_argv` does `sample_ref = kw["sample"]` -- if a client calls `start_tool_job(tool="capa", kwargs={}, case_dir=...)`, this raises `KeyError("sample")`. The hand-rolled validator `_validate_kwargs` has no concept of "required" fields (line 267: `if field not in kwargs: continue`), so the validator passes the empty dict cleanly. The KeyError then propagates out of `submit` and out of the MCP tool (same propagation path as CR-01). No test in `tests/jobs/test_spec_validation.py` exercises a missing-required-field case.

**Fix:** Add a `"required": True` flag to the schema vocabulary and enforce in `_validate_kwargs`:

```python
# In _validate_kwargs, after the spec.kwargs_schema None-check:
for field, rule in spec.kwargs_schema.items():
    if field not in kwargs:
        if rule.get("required"):
            raise InvalidKwargs(field, "present (required)", "missing")
        continue
    # ... rest unchanged

# In _CAPA_SPEC.kwargs_schema:
kwargs_schema={"sample": {"type": "string", "max_length": 256, "required": True}},
```

Plus add a defensive `kw.get("sample", "")` in `_build_capa_argv` so the validator is the single source of truth, not a second crash site.

---

### CR-03: Submit-cap race -- `max_inflight` can be briefly exceeded under concurrent calls

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:533-576`

**Issue:** `submit` takes the lock at line 542 to check `len(self._inflight) >= self._max_inflight` and generate a `job_id`, then RELEASES the lock at line 549. Between line 549 and the second lock acquisition at line 568, `submit` does I/O (`ensure_subdir`, `spec.build_argv`, `tool_log_path`) and constructs the `Job` dataclass. During that window another concurrent `submit` task is free to enter the first critical section, see the same `len(self._inflight)`, and also pass the cap check. With `max_inflight=4` and three jobs in-flight, two simultaneous submits both pass, both build their argv, both insert -> final inflight count is 5.

Although the unique-id collision check holds (token_hex(8) is reserved while the lock is held, but only against `_inflight | _completed` at the moment of the first acquisition -- another submit could pick the same id during the lock-released window; however with 64 bits of entropy this is statistically negligible), the cap-exceedance is a real correctness violation against D-14 / JOBS-04.

**Fix:** Hold the lock across the entire reservation -> insertion sequence, OR insert a placeholder into `_inflight` under the first lock and complete the Job fields afterwards:

```python
async def submit(self, *, spec, kwargs, case_dir_resolved, effective_timeout_s) -> Job:
    case_dir_path = Path(case_dir_resolved)
    ensure_subdir(case_dir_path, "tool-logs")
    argv = spec.build_argv(case_dir_path, kwargs)
    log_abs = tool_log_path(case_dir_path, spec.slug)
    log_rel = str(log_abs.relative_to(case_dir_path))

    async with self._lock:
        if len(self._inflight) >= self._max_inflight:
            raise JobCapReached(inflight=len(self._inflight), cap=self._max_inflight)
        job_id = secrets.token_hex(8)
        while job_id in self._inflight or job_id in self._completed:
            job_id = secrets.token_hex(8)
        job = Job(
            job_id=job_id, tool=spec.name, spec=spec, kwargs=dict(kwargs),
            case_dir=case_dir_resolved, argv=list(argv),
            effective_timeout_s=effective_timeout_s,
            log_path_abs=log_abs, log_path_rel=log_rel,
        )
        self._inflight[job_id] = job

    job._drive_task = asyncio.create_task(self._spawn_and_drive(job), name=f"job-drive-{job_id}")
    return job
```

Note: this also moves CR-01's argv-build failure outside the lock, where it can propagate cleanly to the caller (and be wrapped per CR-01's fix).

## Warnings

### WR-01: `cancel-before-spawn` mislabels a successful job as cancelled

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:591-602` (`cancel`) and `mcp-gateway/src/mcp_gateway/jobs.py:663-671` (terminal-status decision)

**Issue:** If `cancel(job)` is called after `submit` returns but BEFORE `_spawn_and_drive` has set `job.proc`, the cancel sets `_cancel_requested=True` and returns (line 596-598 early-out). The drive task then proceeds to spawn, run, and complete the subprocess to a clean exit. At line 664-665, the terminal-status switch sees `_cancel_requested=True` first and sets `status="cancelled"` even though the process ran to a successful exit. The user is told "your job was cancelled" but in fact the work was performed in full -- and any side effects (file writes, network calls, etc.) happened.

**Fix:** In the drive task, check `_cancel_requested` before spawning AND after spawning the process kill it if requested:

```python
# At the top of _spawn_and_drive, before opening the file sink:
if job._cancel_requested:
    job.status = "cancelled"
    return  # finally-block will set ended_at + mark terminal

# Immediately after capturing pid/pgid (after `job.pgid = os.getpgid(...)`):
if job._cancel_requested:
    try:
        os.killpg(job.pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    await asyncio.shield(proc.wait())
    job.status = "cancelled"
    return
```

---

### WR-02: `cancel_tool_job` returns snapshot before drive task has settled

**File:** `mcp-gateway/src/mcp_gateway/tools/jobs.py:243-250`

**Issue:** After calling `await registry.cancel(job, reason="user")`, the code does `await asyncio.sleep(0)` and then immediately calls `registry._build_snapshot(job)`. A single zero-sleep yields only ONE turn of the event loop -- the drive task's finally-block does multiple awaits (status setting, ended_at, `_mark_terminal` which writes the JSON snapshot under the lock). The returned snapshot may therefore show `status="running"` even though the proc has already been reaped, and `ended_at` may still be None. The cancel-grace test passes because `cancel()` itself awaits `proc.wait()`, but the post-cancel `_drive_task` chain is still racing.

**Fix:** Await the drive task directly (with a short timeout as a safety net) instead of a single yield:

```python
was_terminal = job.status in jobs._TERMINAL_STATUSES
if not was_terminal:
    await registry.cancel(job, reason="user")
    # Wait for the drive task's finally-block to mark terminal status.
    if job._drive_task is not None and not job._drive_task.done():
        try:
            await asyncio.wait_for(asyncio.shield(job._drive_task), timeout=2.0)
        except (asyncio.TimeoutError, asyncio.CancelledError):
            pass  # snapshot may be transient; user can re-poll get_tool_job
snapshot = registry._build_snapshot(job)
snapshot["previously_terminal"] = was_terminal
return snapshot
```

---

### WR-03: `_drain` `line_buf` grows unbounded for newline-less stderr

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:457-472`

**Issue:** When a tool with a `progress_parser` is configured, `_drain` accumulates stderr chunks into `line_buf` until a `\n` arrives (`line_buf.extend(chunk); while b"\n" in line_buf: ...`). A misbehaving tool that writes large amounts of stderr without any newline (e.g., a binary dump, a progress carriage-return spinner using `\r` only, or a faulty tool that strips newlines) will balloon `line_buf` in memory up to the per-job log cap (default 256 MiB) before the cap-kill path fires. This is the entire 256 MiB held twice -- once in the bytearray, plus the on-disk log -- a real memory pressure issue.

**Fix:** Cap `line_buf` at a sane line size and drop overflow without parsing it:

```python
MAX_LINE_BUF = 64 * 1024  # 64 KiB max line for progress parsing
# ... inside the progress branch:
if role == "stderr" and spec.progress_parser is not None:
    line_buf.extend(chunk)
    if len(line_buf) > MAX_LINE_BUF:
        # Drop everything before the last newline (if any), or truncate to last
        # MAX_LINE_BUF bytes -- prevents unbounded growth on newline-less streams.
        idx = line_buf.rfind(b"\n")
        if idx >= 0:
            line_buf = bytearray(line_buf[idx:])
        else:
            line_buf = bytearray(line_buf[-MAX_LINE_BUF:])
    while b"\n" in line_buf:
        # ... unchanged
```

---

### WR-04: `_truncate_for_response` has no walk-back iteration cap

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:99-107`

**Issue:** `_truncate_for_response` walks the cut backwards while `(cut[-1] & 0xC0) == 0x80` (UTF-8 continuation byte). In valid UTF-8 a codepoint is at most 4 bytes so this terminates in <=3 steps, but on malformed input (e.g., bytes injected by a malicious tool stdout or corrupted output) the loop could in theory chew through the entire buffer. `runner.py::_truncate_to_utf8_boundary` correctly caps the walk-back at 4 iterations (line 95) -- the same defense should be applied here.

**Fix:** Mirror the runner.py pattern:

```python
def _truncate_for_response(text: str, head_kb: int) -> str:
    max_bytes = head_kb * 1024
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    cut = max_bytes
    for _ in range(4):
        if cut == 0:
            return ""
        if (encoded[cut] & 0xC0) != 0x80:
            break
        cut -= 1
    return encoded[:cut].decode("utf-8", errors="replace")
```

---

### WR-05: `os.getpgid(proc.pid)` after fast-exiting children may raise

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:637`

**Issue:** Immediately after `create_subprocess_exec` returns, the code does `job.pgid = os.getpgid(proc.pid)`. If the child has already exited (e.g., a fast-failing `sh -c "exit 1"`, or `sleep 0`), `getpgid` can raise `ProcessLookupError` (ESRCH). This is not caught -- it propagates to the outer `except Exception` at line 673, which marks status="failed" and logs. The job is marked failed even though the child may have actually executed correctly (exit 0). Compare runner.py line 259 which uses `os.getpgid(proc.pid)` only at signal time and catches ProcessLookupError.

**Fix:** Capture the pgid defensively and tolerate the lookup miss:

```python
job.proc = proc
try:
    job.pgid = os.getpgid(proc.pid)
except ProcessLookupError:
    # Child already exited; we can still proc.wait() on the existing handle
    # and there is nothing to killpg.
    job.pgid = None
```

Cancel paths already guard `if job.pgid is None or job.proc is None: return` so this stays safe.

---

### WR-06: `stdout_tail_buf.extend(chunk)` is O(n) per byte for high-throughput streams

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:167-172, 443, 454`

**Issue:** `stdout_tail_buf` / `stderr_tail_buf` are `collections.deque[int]` with `maxlen=32*1024` (32 KiB). `deque.extend(bytes)` iterates the bytes object one byte at a time, performing 32 KiB of single-int appends per ring saturation cycle. For a tool that writes 256 MiB to stdout, this is ~256e6 / 64KiB = 4000 chunks, each appending all 64 KiB byte-by-byte (deque-of-int has no bulk-copy fast-path). Then `bytes(job.stdout_tail_buf)` on the snapshot path rebuilds a `bytes` object from the deque -- another byte-by-byte iteration.

This is a perf concern (out of v1 scope per the review guidance), BUT it also has correctness implications under load: a slow `_drain` keeps the OS pipe buffer full longer, increasing the chance that a misbehaving subprocess blocks on a full pipe and never reaches the cap-kill path. Flagging as Warning rather than Info because it interacts with subprocess lifecycle.

**Fix:** Use a bounded bytearray ring or a deque of bytes-chunks (with byte-count tracking) instead of a deque-of-int. Example:

```python
# Replace deque[int] with a bytearray-based bounded tail buffer.
class _ByteRing:
    def __init__(self, maxlen: int):
        self.maxlen = maxlen
        self.buf = bytearray()
    def extend(self, data: bytes) -> None:
        self.buf.extend(data)
        if len(self.buf) > self.maxlen:
            del self.buf[: len(self.buf) - self.maxlen]
    def __bytes__(self) -> bytes:
        return bytes(self.buf)
```

## Info

### IN-01: `_validate_kwargs` silently ignores unknown schema-type values

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:266-287`

**Issue:** If a future spec adds `{"type": "number"}` (typo) or `{"type": "list"}` (unsupported), `_validate_kwargs` silently passes the value through (none of the `elif` branches match, no `else` clause). This is forward-compat-friendly but masks typos.

**Fix:** Add a final `else: raise RuntimeError(f"unsupported schema type {expected!r} in spec {spec.name}")` -- this is a developer error, not a user error, so a non-D-15 raise at spec-registration / first-call time is appropriate.

---

### IN-02: `MAX_JOBS_INFLIGHT=0` permanently disables job submission

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:78`

**Issue:** `_env_int` accepts `0` (lower bound is `>= 0`, not `> 0`). `MAX_JOBS_INFLIGHT=0` means every submit raises `JobCapReached(0, 0)`. This is technically valid (a way to disable the job system entirely) but is silently accepted. Same applies to `MAX_COMPLETED_JOBS=0` (eviction on every terminal job).

**Fix:** Either (a) explicitly document the zero-value semantics in the module docstring or in CLAUDE.md, or (b) tighten validation:

```python
MAX_JOBS_INFLIGHT: int = _env_int("MCP_GATEWAY_MAX_JOBS_INFLIGHT", 4)
if MAX_JOBS_INFLIGHT == 0:
    log.warning("[jobs] MCP_GATEWAY_MAX_JOBS_INFLIGHT=0 -- all submits will fail with JobCapReached")
```

---

### IN-03: `_log_burst_probe` argv uses `sh -c` despite the argv-only invariant

**File:** `mcp-gateway/src/mcp_gateway/jobs.py:337`

**Issue:** `_build_log_burst_argv` returns `["sh", "-c", "while true; do head -c 1048576 /dev/urandom | base64; done"]`. This is technically argv-spawned (not `shell=True`), but the contents are a shell pipeline. The module docstring claims "argv-only spawn ... same safety properties as ReToolRunner" (line 12). The `_log_burst_probe` is an internal/hidden test fixture so this is fine in practice, but if a future tool author copies the pattern thinking sh -c is sanctioned by precedent, the chokepoint property weakens.

**Fix:** Add a comment to `_build_log_burst_argv` reinforcing that `sh -c` is permissible ONLY for internal underscore-prefixed test probes, and that user-visible specs (like capa) must use direct argv only.

---

### IN-04: `get_tool_job` swallows `ctx.report_progress` exceptions silently

**File:** `mcp-gateway/src/mcp_gateway/tools/jobs.py:207-215`

**Issue:** The `try/except Exception` block around `ctx.report_progress` catches everything and only logs. This is correct per D-15 (tools never raise) but the bare `except Exception` is broad enough to mask real bugs (e.g., a malformed progress payload, an SDK API mismatch). At minimum the log should include the job_id and progress payload so post-mortem analysis is possible.

**Fix:**

```python
try:
    await ctx.report_progress(
        job.progress,
        job.progress_total if job.progress_total is not None else None,
        job.progress_message,
    )
    job._last_reported_to[sid] = cur
except Exception:
    log.exception(
        "[tools.jobs] ctx.report_progress failed for job=%s progress=%s/%s -- ignoring",
        job.job_id, job.progress, job.progress_total,
    )
```

---

### IN-05: `list_tool_jobs` `limit` coercion silently accepts non-numeric

**File:** `mcp-gateway/src/mcp_gateway/tools/jobs.py:303-308`

**Issue:** When `limit` is not a positive int <= 500, the code tries `min(max(1, int(limit)), max_limit)` and falls back to `limit = 50` on `(TypeError, ValueError)`. This silently rewrites a bogus client argument. A client passing `limit="bogus"` or `limit=None` gets `50` with no indication that their argument was ignored. Borderline -- the tools-never-raise contract argues against signalling an error, but a one-line log at INFO level would aid debuggability:

```python
if not isinstance(limit, int) or limit <= 0 or limit > max_limit:
    try:
        coerced = min(max(1, int(limit)), max_limit)
        log.info("[tools.jobs] list_tool_jobs limit %r coerced to %d", limit, coerced)
        limit = coerced
    except (TypeError, ValueError):
        log.info("[tools.jobs] list_tool_jobs limit %r invalid, defaulting to 50", limit)
        limit = 50
```

---

_Reviewed: 2026-05-19_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
