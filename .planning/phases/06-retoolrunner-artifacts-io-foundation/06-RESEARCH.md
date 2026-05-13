# Phase 6: ReToolRunner + artifacts_io Foundation - Research

**Researched:** 2026-05-13
**Domain:** asyncio subprocess primitives, stream-drain patterns, cancellation propagation, path-traversal containment
**Confidence:** HIGH (all primitives are stdlib + already-pinned `anyio`; all behaviors verifiable in existing v1.0 source)

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions (D-01..D-21 — contract for Phase 7+ consumers)

- **D-01:** `ReToolRunner` is exposed as a **class** in `runner.py`. Caller constructs with per-call invariants (`case_dir`, default timeout, head-buffer sizes, slug) and `await runner.run(argv)` returns the structured result dict.
- **D-02:** A module-level convenience `run_tool(case_dir, argv, *, slug, timeout=None, env=None, stdout_head_kb=None, stderr_head_kb=None) -> dict` is also exported. It constructs a fresh `ReToolRunner` and awaits `run(argv)`. One-shot static wrappers use this; Phases 8/9 use the class.
- **D-03:** The structured return dict has these keys, in this exact order, locked for Phase 7+ to depend on:
  ```python
  {
      "exit_code": int,            # process returncode; -1 if not exited
      "timed_out": bool,
      "duration_s": float,
      "stdout_head": str,          # head-buffered, ANSI-stripped, UTF-8-safe
      "stdout_truncated": bool,
      "stdout_bytes_total": int,
      "stderr_head": str,
      "stderr_truncated": bool,
      "stderr_bytes_total": int,
      "log_path": str,             # case_dir-relative
      "argv": list[str],
      "slug": str,
  }
  ```
- **D-04:** `run()` **never raises** on subprocess exit state. It raises only on programmer errors before spawn (`FileNotFoundError`, `ValueError`, `PermissionError`). `asyncio.CancelledError` from the awaiter is re-raised AFTER `proc.wait()` returns, shielded.
- **D-05:** Flat module layout — `mcp-gateway/src/mcp_gateway/runner.py` and `mcp-gateway/src/mcp_gateway/artifacts_io.py` at the top of the package. No new `re_runtime/` sub-package.
- **D-06:** `confine_to` is NOT merged into `tools/case_dirs.py`. `case_dirs.resolve_case_dir` remains the `STATUS_ROOT`-aware guard; `confine_to` is a lower-level pure path helper. Phase 7+ composes the two.
- **D-07:** `runner.py` MAY import from `artifacts_io`; `artifacts_io` has zero gateway-internal dependencies.
- **D-08:** Four `MCP_GATEWAY_RUNNER_*` env vars, read **once at module import** with `_max_bytes()`-style sanity check raising `RuntimeError` on bad values. Per-call kwargs override the env-derived defaults.

  | Env var                                  | Default | Purpose |
  |------------------------------------------|---------|---------|
  | `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB`      | `256`   | stdout head bytes returned in dict |
  | `MCP_GATEWAY_RUNNER_STDERR_HEAD_KB`      | `64`    | stderr head bytes returned in dict |
  | `MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S`   | `55.0`  | default hard timeout (5 s margin under MCP 60 s cap) |
  | `MCP_GATEWAY_RUNNER_MAX_LOG_MB`          | `256`   | per-invocation log file cap; over-cap kills child, sets `exit_code=-9`, `timed_out=False`, `truncated_log=true` marker |

- **D-09:** Tool log files at `case_dir/tool-logs/<%Y%m%dT%H%M%SZ>-<slug>-<rand4>.txt`. `<rand4>` = `secrets.token_hex(2)`. Filename function `tool_log_path(case_dir, slug) -> Path` lives in `artifacts_io.py`.
- **D-10:** `log_path` returned in the dict is the path **relative to `case_dir`**, as a string.
- **D-11:** `confine_to(case_dir, path) -> Path` resolves `case_dir` with `strict=True` (must exist, must be dir), joins relative paths, resolves target with `strict=False`, enforces `target.is_relative_to(case_dir)`. Returns canonical resolved `Path`.
- **D-12:** Symlinks inside `case_dir` whose target also lies inside `case_dir` are allowed (resolved containment check handles this).
- **D-13:** `confine_to` raises `ValueError` on every rejection path; never `FileNotFoundError` for the target.
- **D-14:** `confine_to` does NOT enforce `STATUS_ROOT` containment; that is `resolve_case_dir`'s job.
- **D-15:** `ensure_subdir(case_dir, name) -> Path` with regex `^[a-z0-9][a-z0-9_-]{0,39}$` and `mkdir(parents=False, exist_ok=True)`. Idempotent and concurrency-safe.
- **D-16:** Module constant `artifacts_io.EXPANDED_CASE_SUBDIRS` lists the nine canonical names (`tool-logs`, `extracted`, `hex`, `rop`, `dynamic`, `qemu`, `disassembly`, `decompilation`, `xrefs`). Iterable, lazy-create catalog (NOT create-all-at-init).
- **D-17:** On timeout or `CancelledError`, runner runs:
  ```python
  try:
      os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
  except (ProcessLookupError, PermissionError):
      pass
  await asyncio.shield(proc.wait())
  ```
  SIGTERM-then-SIGKILL is NOT used; SIGKILL only.
- **D-18:** Follow-fork stragglers (`/proc/<pid>/task/*/children`) are NOT scanned in Phase 6 — deferred to Phase 11.
- **D-19:** Tests at `mcp-gateway/tests/test_runner.py` + `mcp-gateway/tests/test_artifacts_io.py`.
- **D-20:** One test per Success Criterion — SC-1 chokepoint/cwd/timeout/cancel; SC-2 return shape; SC-3 capture; SC-4 100 MB urandom OOM-safety + RSS delta < 32 MB via `RUSAGE_CHILDREN.ru_maxrss`; SC-5 confine_to matrix; D-09 log naming.
- **D-21:** Hermetic via `tmp_path`; 100 MB urandom test marked `slow`.

### Claude's Discretion

- Exact concurrent-drain pattern (`anyio.create_task_group` vs `asyncio.gather` of two coroutines) — both acceptable.
- Whether `ensure_subdir` validates `case_dir ⊂ STATUS_ROOT` — recommended NO (callers compose with `resolve_case_dir`).
- ANSI-strip regex (stdlib preferred): `re.compile(r"\x1b\[[0-9;]*[A-Za-z]")` recommended; tiny dep allowed iff regex misses a known RE-tool sequence (unlikely for `objdump`/`strings`/`xxd`).
- Log file open mode: `open(log_path, "ab", buffering=0)` is the recommended default; alternative `Path.write_bytes` loop is OK as long as partial writes are flushed before return.

### Deferred Ideas (OUT OF SCOPE)

- Convergence of `subprocess_runner.run_script` and `ReToolRunner` (v1.2+).
- Follow-fork straggler scan (Phase 11).
- SIGTERM-then-SIGKILL grace period (Phase 9 layers on top for user-cancel).
- Per-`Mcp-Session-Id` keying (v1.2).
- Mount-namespace isolation for the runner subprocess (Phase 7 / v1.2).
- Per-call `tool-logs/` rotation (v1.2+).
- Refactoring `tools/artifacts.py::get_artifact` to call `confine_to` (permitted but not required).
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| FOUND-02 | Every new v1.1 subprocess invocation goes through a single `ReToolRunner` enforcing argv-only execution, cwd-confinement, hard timeout, process-group SIGKILL on timeout/cancel, structured JSON result with `exit_code`/`stdout_head`/`stderr_head`/`log_path`/`timed_out`/byte+truncation counts | §Standard Stack (asyncio.create_subprocess_exec, start_new_session, killpg, asyncio.shield), §Architecture Patterns (concurrent drain, head buffer + file sink), §Code Examples §1-5 |
| FOUND-03 | Runner-driven tools auto-capture full stdout/stderr to `case_dir/tool-logs/<timestamp>-<slug>.txt` while returning only a head-truncated preview | §Architecture Patterns (head buffer + file sink interaction, ANSI strip ordering, UTF-8 codepoint boundary truncation), §Code Examples §6-8 |
| FOUND-04 | Canonical `confine_to(case_dir, path)` helper exists and is used by every path-accepting tool in v1.1 to reject path traversal | §Architecture Patterns (resolve(strict=False) semantics + is_relative_to containment + NUL byte rejection), §Code Examples §9-10 |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Licensing**: IDA Pro / Binary Ninja licenses never baked into images — irrelevant to Phase 6 (no disassembler launch in tests).
- **Security**: Container runs with elevated capabilities (`SYS_PTRACE`, `seccomp=unconfined`); not directly exercised by Phase 6 but the runner must NOT loosen any of these.
- **Transport**: Phase 6 has no MCP-visible surface; runner is in-process Python.
- **Backward compatibility**: "Agent inside container" mode must continue unchanged → Phase 6 **does NOT modify** `subprocess_runner.py`; the two runners coexist by design.
- **GSD Workflow Enforcement**: Edits must flow through GSD commands. Research output here feeds gsd-planner.

## Summary

Phase 6 lands the chokepoint subprocess primitive (`ReToolRunner`) and two pure path helpers (`confine_to`, `ensure_subdir`) that every Phase 7-11 RE tool will sit atop. The implementation is **entirely stdlib + already-pinned `anyio`** — no new pip dependencies. The reference for the spawn/cleanup shape is the existing v1.0 `mcp_gateway/subprocess_runner.py:52-67`, which the new runner mirrors and extends with: (1) concurrent stdout/stderr drain instead of `proc.communicate()` (Pitfall 1 mitigation), (2) head buffer + file sink with ANSI strip before UTF-8 boundary truncation (Pitfall 3 + Pitfall 12 mitigation), (3) `asyncio.shield(proc.wait())` cleanup that runs on `CancelledError` (Pitfall 18 mitigation), (4) structured return dict with 12 locked keys (D-03).

The dominant technical risks are: (a) the `proc.communicate()` cargo-cult that would re-introduce the PIPE deadlock for 100 MB+ outputs — mitigated by the concurrent-drain pattern below; (b) cancellation that drops the subprocess but not the OS process — mitigated by shielded wait + killpg; (c) silent UTF-8 mojibake from mid-codepoint truncation — mitigated by the explicit boundary-finding algorithm below.

**Primary recommendation:** Use `asyncio.gather` of two coroutines (one per pipe) inside a `try/except (TimeoutError, CancelledError)` block, with `asyncio.wait_for(proc.wait(), timeout)` as the timeout driver. Apply ANSI strip + UTF-8 boundary truncation **only on the head slice** (decoded once at the end), and write **raw bytes** to the file sink for forensic fidelity.

## Standard Stack

### Core
| Library / Primitive | Version | Purpose | Why Standard |
|---------------------|---------|---------|--------------|
| `asyncio` (stdlib) | Python 3.11+ | `create_subprocess_exec`, `wait_for`, `shield`, `gather`, `Task` | Argv-only async exec is the v1.0 convention; `shield` is the documented `CancelledError`-safe cleanup primitive. [VERIFIED: `mcp-gateway/src/mcp_gateway/subprocess_runner.py:52`] |
| `os` (stdlib) | Python 3.11+ | `killpg`, `getpgid`, `setsid` (via `start_new_session=True`) | Same primitives the v1.0 runner uses. POSIX-only — fine, target is a Linux container. [VERIFIED: existing code] |
| `signal` (stdlib) | Python 3.11+ | `SIGKILL` constant | SIGTERM-then-SIGKILL is explicitly out of scope (D-17). [CITED: CONTEXT.md D-17] |
| `re` (stdlib) | Python 3.11+ | ANSI-strip regex compiled once at module load | Stdlib regex preferred over a tiny dep (D-08 discretion). [CITED: CONTEXT.md] |
| `pathlib.Path` (stdlib) | Python 3.11+ | `resolve(strict=True/False)`, `is_relative_to`, joinpath | `is_relative_to` is the correct containment primitive (added Python 3.9; container is 3.11+). [VERIFIED: `mcp-gateway/pyproject.toml` `requires-python = ">=3.11"`] |
| `secrets` (stdlib) | Python 3.11+ | `token_hex(2)` for the 4-char rand suffix | Same primitive `_resolve_session_id` patterns use across the codebase. [CITED: CONTEXT.md D-09] |
| `resource` (stdlib) | Python 3.11+ | `getrusage(RUSAGE_CHILDREN).ru_maxrss` for the 100 MB OOM-safety test | Container is Linux-only; `ru_maxrss` is in kilobytes on Linux. [VERIFIED: Python docs, Linux man getrusage(2)] |
| `anyio` | ≥4.5 (already pinned) | Optional alternative for `create_task_group` drain pattern; recommended NOT used in this phase | `asyncio.gather` of two coroutines is simpler and equivalent. Use `anyio` only in Phase 8 sessions where its task-group cancellation semantics buy something. [VERIFIED: `mcp-gateway/pyproject.toml`] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | ≥8 (dev) | Test runner | Already the project standard. [VERIFIED: `mcp-gateway/pyproject.toml`] |
| `pytest-asyncio` | ≥0.23 (dev) | `asyncio_mode = "auto"` is set, no `@pytest.mark.asyncio` decorator needed | `async def test_*` works directly. [VERIFIED: `mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]`] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `asyncio.gather` two-coroutine drain | `anyio.create_task_group()` | Equivalent correctness; `anyio` task-group has stronger cancellation semantics but adds an indirection layer that doesn't pay off for two fixed pipes. Stick with `asyncio.gather`. |
| Per-call `re.compile(ANSI)` | Module-level compile | Module-level is the obvious win — compile once at import. Apply only on the head slice (small bytes), not on the full stream. |
| `aiofiles` for log writes | Plain blocking `open(..., "ab", buffering=0)` | At 100 MB/s writes the synchronous write blocks the event loop for ~1 µs per chunk — invisible. `aiofiles` adds a dep and a thread pool round-trip per chunk that actively hurts. Recommend plain `open` + `os.write` or `f.write` with `buffering=0`. |
| `asyncio.timeout(...)` (context manager) | `asyncio.wait_for(...)` | Both work in 3.11+. `wait_for` composes more cleanly with the gather pattern (one `wait_for` wraps `proc.wait()`, drains run in parallel). Recommend `wait_for`. |
| `psutil.Process.memory_info()` | `resource.getrusage(RUSAGE_CHILDREN)` | `resource` is stdlib, zero dep cost. `ru_maxrss` covers all reaped children — exactly what we want for the runner test. Recommend `resource`. |
| `tracemalloc` | `resource.getrusage` | `tracemalloc` measures the **gateway's** Python heap, not the **child subprocess** RSS. Wrong tool for this assertion. |

**Installation:** No new pip dependencies. Phase 6 is entirely stdlib + already-pinned `anyio`.

## Architecture Patterns

### Recommended Project Structure
```
mcp-gateway/src/mcp_gateway/
├── subprocess_runner.py       # v1.0 — UNCHANGED
├── runner.py                  # NEW — ReToolRunner + run_tool
├── artifacts_io.py            # NEW — confine_to, ensure_subdir, tool_log_path, EXPANDED_CASE_SUBDIRS
├── uploads.py                 # reference for _max_bytes-style env validation
└── tools/
    ├── case_dirs.py           # composed-with, not replaced
    └── artifacts.py           # inline ancestor of confine_to lives at lines 115-139
mcp-gateway/tests/
├── test_runner.py             # NEW — SC-1..SC-4 + cancel + D-09 + grep-shell-True
├── test_artifacts_io.py       # NEW — SC-5 matrix + ensure_subdir + EXPANDED_CASE_SUBDIRS + D-09 naming
└── conftest.py                # tmp_path is sufficient; no new shared fixtures needed
```

### Pattern 1: Concurrent stream drain (Pitfall 1)
**What:** Drain stdout and stderr in parallel as two awaited coroutines. Each accumulates a head buffer up to its cap, then continues draining into the file sink only (not the in-memory buffer), so the child cannot deadlock when its pipe fills.

**When to use:** Every spawn that pipes either stdout or stderr — i.e., every `ReToolRunner.run()`.

**Failure mode if violated:** `await proc.communicate()` reads **all** of both pipes into memory before returning. For the 100 MB urandom test, this is 100 MB Python `bytes` allocation; for `objdump -d` on a 50 MB binary, gateway RSS climbs to multi-GB; for `yes | head -c 50G` it OOMs the container. `communicate()` is correctness-safe for *deadlocks* (it does drain both pipes concurrently internally) but is **not** memory-safe.

**Algorithm:**
1. Spawn with `stdout=PIPE`, `stderr=PIPE`, `start_new_session=True`.
2. Start two drain coroutines, one per pipe, in parallel via `asyncio.gather`.
3. Each drain coroutine loops `await stream.read(CHUNK)` (CHUNK = 64 KB):
   - Always write raw chunk to the file sink (forensic fidelity).
   - Increment `bytes_total` counter.
   - If head buffer is not yet full: append to head buffer, capped at `head_kb * 1024`. After the cap is reached, set `truncated = True` and stop appending — but keep draining.
   - On `b""` (EOF) or log-cap exceeded, return.
4. Wrap `proc.wait()` in `asyncio.wait_for(..., timeout)` running concurrently with the drains via `asyncio.gather`.
5. On TimeoutError / CancelledError → cleanup block (Pattern 4 below).

### Pattern 2: Head buffer + file sink — exact ordering (Pitfall 3, Pitfall 12)
**What:** The file sink receives **raw bytes** (no ANSI strip, no UTF-8 decode). ANSI strip + UTF-8 boundary truncation runs **once, at the end, on the head slice only**.

**Why this order:**
- Stripping ANSI from the file sink would change byte counts (`stdout_bytes_total` no longer matches the file size on disk) and lose forensic data.
- Stripping ANSI per-chunk requires reasoning about ANSI sequences split across chunk boundaries (escape byte `0x1b` arriving in chunk N, `[31m` arriving in chunk N+1) — complex and error-prone.
- Truncating to a UTF-8 boundary per-chunk requires the same cross-chunk reasoning for multi-byte UTF-8 codepoints.

**Algorithm at end of drain:**
1. `head_bytes` is whatever was accumulated (≤ head_kb_cap, raw bytes including any ANSI sequences and partial UTF-8 codepoints).
2. ANSI-strip via the module-level compiled regex (operates on bytes).
3. Truncate to last valid UTF-8 leading byte ≤ N (algorithm below).
4. Decode with `errors="replace"` — this only catches truly malformed bytes (replacement chars at the *boundary* are now impossible because we truncated to a codepoint boundary).

### Pattern 3: UTF-8 codepoint boundary truncation
**What:** Given a `bytes` buffer that may end mid-codepoint, find the largest prefix ≤ N bytes that ends on a valid UTF-8 codepoint boundary.

**Algorithm:** A UTF-8 leading byte is either `0xxxxxxx` (1-byte codepoint) or `11xxxxxx` (start of multi-byte). Continuation bytes are `10xxxxxx`. To find the last valid boundary in `buf[:N]`, walk backward from position `N` while the byte at that position is a continuation byte (`(b & 0xC0) == 0x80`), then truncate there. At most 3 backward steps are needed (UTF-8 codepoints are ≤ 4 bytes).

**Code (paste into task action):**
```python
def truncate_to_utf8_boundary(buf: bytes, n: int) -> bytes:
    """Return the largest prefix of buf with length <= n that ends on a UTF-8 codepoint boundary.

    A continuation byte has the high bits 10xxxxxx (i.e. b & 0xC0 == 0x80).
    Walk back at most 3 bytes; UTF-8 codepoints are <= 4 bytes.
    """
    if n >= len(buf):
        return buf
    cut = n
    # cut is the *length*, so cut == 0 returns b"" which is always a valid boundary.
    # Walk back while the byte AT position `cut` (the first dropped byte) is a continuation.
    # If buf[cut] starts a new codepoint (leading byte), cut is already a valid boundary.
    for _ in range(4):
        if cut == 0:
            return b""
        if (buf[cut] & 0xC0) != 0x80:
            return buf[:cut]
        cut -= 1
    # buf is malformed (>4 continuation bytes in a row); fall through and slice anyway.
    return buf[:cut]
```

### Pattern 4: Cancellation contract (Pitfall 18) + process-group cleanup (Pitfall 4)
**What:** `CancelledError` from the awaiter must result in the subprocess being dead before the runner returns. Cleanup runs in a shielded block so that even a cascading cancel doesn't drop `proc.wait()` mid-flight.

**Code (paste into task action):**
```python
import asyncio
import os
import signal

# Inside ReToolRunner.run():
proc = await asyncio.create_subprocess_exec(
    *argv,
    cwd=str(resolved_case_dir),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env=env,
    start_new_session=True,
)
try:
    # gather: two drains run in parallel, wait_for drives the timeout
    drains = asyncio.gather(
        _drain(proc.stdout, stdout_head_cap, file_sink),
        _drain(proc.stderr, stderr_head_cap, file_sink),
    )
    exit_code = await asyncio.wait_for(
        asyncio.gather(proc.wait(), drains),
        timeout=timeout,
    )
    # ... build return dict on happy path ...
except (asyncio.TimeoutError, asyncio.CancelledError) as exc:
    timed_out = isinstance(exc, asyncio.TimeoutError)
    # Pitfall 4: swallow both ProcessLookupError and PermissionError.
    # - ProcessLookupError: child already exited between the timeout check and killpg.
    # - PermissionError: rare; can happen if uid changed mid-flight via a setuid binary
    #   that escalated then dropped privs in the pgroup.
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    # Pitfall 18: shielded wait ensures cleanup completes even under cancel cascade.
    await asyncio.shield(proc.wait())
    if isinstance(exc, asyncio.CancelledError):
        raise
    # On timeout: fall through to return the dict with timed_out=True
```

**Key points:**
- `os.getpgid(proc.pid)` rather than `proc.pid` directly because the kernel allocates the pgroup; `start_new_session=True` makes them equal in practice, but getpgid is the documented portable form (matches v1.0 line 64 which uses `proc.pid` — note Phase 6 hardens this).
- `asyncio.shield(proc.wait())` is the load-bearing call. Without it, a cancel cascading from the caller can interrupt our cleanup, leaving a zombie.
- The `raise` only fires on `CancelledError`. On timeout we **return the dict normally** (D-04 — `timed_out=True`, `exit_code=-9`) per the "never raise on subprocess state" contract.

### Pattern 5: Timeout primitive choice
**Recommendation:** `asyncio.wait_for(..., timeout=t)` wrapping the gather.

**Rationale:**
- Composes cleanly with the cancellation contract (Pattern 4): `wait_for` raises `TimeoutError`, the same except block catches both `TimeoutError` and `CancelledError`.
- `asyncio.timeout(t)` (3.11+ context manager) is also fine, but its cancellation-mechanism via task cancellation interacts subtly with the surrounding gather. `wait_for` is the simpler, well-trodden primitive — and it's what the v1.0 `subprocess_runner.run_script` already uses.
- Manual loop with `proc.wait` + `asyncio.sleep` is anti-pattern — it busy-polls.

### Pattern 6: Log file open mode
**Recommendation:** `open(log_path, "ab", buffering=0)` — synchronous, append, unbuffered.

**Rationale:**
- For 100 MB written over ~1-2 seconds in 64 KB chunks, each `f.write()` is a fast syscall (~µs). The event loop is blocked for nanoseconds per chunk — invisible.
- `buffering=0` ensures bytes hit the kernel immediately; if the process is killed mid-stream, the on-disk log is as complete as possible (forensic fidelity).
- `"ab"` (append-binary) lets the runner write raw bytes without any encoding decisions.
- `aiofiles` adds a thread-pool round-trip per write (~10-50 µs) — slower than the blocking write it's "replacing". The async appeal is irrelevant for fast syscalls.
- **Test that proves it:** the 100 MB urandom test (SC-4) measures wall-clock duration; if synchronous writes were blocking the event loop meaningfully, the gather of two drains would serialize and the total would be 2x the single-pipe time. The test asserts duration < 60 s on stock hardware — synchronous writes pass this with margin.

### Pattern 7: ANSI escape regex
**Recommended regex (module-level compile):**
```python
import re
_ANSI_ESCAPE = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")
```
(Applied to **bytes**, before UTF-8 decode.)

**Coverage analysis (sequences emitted by Phase 7-11 tools):**

| Tool | Sequences emitted | Covered by regex? |
|------|-------------------|-------------------|
| `objdump -d` | None by default (no color flag) | n/a |
| `objdump --disassembler-color=on` | CSI SGR — e.g., `\x1b[01;32m`, `\x1b[m` | YES (CSI Final Byte ∈ `[A-Za-z]`, e.g. `m`) |
| `strings` | None (binary tool, no color) | n/a |
| `xxd` | None by default | n/a |
| `xxd -R always` | CSI SGR colors | YES |
| `capstone CLI` (cstool) | None by default | n/a |
| `readelf --color` | CSI SGR | YES |
| `nm --color` | CSI SGR | YES |
| `ls --color=always` (run_shell-pulled) | CSI SGR | YES |
| `grep --color=always` | CSI SGR (`\x1b[01;31m`) | YES |
| `bat`, `delta`, etc. (analyst ad-hoc) | CSI SGR + occasionally OSC | Most YES; OSC sequences `\x1b]...\x07` NOT covered |

**Gaps and trade-off:**
- The proposed regex covers the **CSI** family (`ESC [ ... letter`), which is 99% of what RE tools emit.
- **NOT covered:** OSC sequences (`\x1b]0;title\x07`), DCS sequences (`\x1bP...\x1b\\`), and bare SS3/single-char ESC sequences. Pitfall 3 mentions OSC as a vector for malicious filenames in `run_shell`.
- **Recommendation:** Phase 6 ships the CSI regex as documented in CONTEXT.md Claude's-Discretion. Phase 7 (run_shell) MAY widen the regex to also strip OSC if `run_shell` ad-hoc testing surfaces a real escape; doing so does not require a Phase 6 API change. A note in the runner docstring documents the CSI-only coverage.
- **Optional widening (not required for Phase 6 to pass):**
  ```python
  _ANSI_ESCAPE = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]|\x1b\][^\x07]*\x07")
  ```
  Matches PITFALLS.md Pitfall 3 §"How to avoid" suggestion.

### Pattern 8: `confine_to` semantics (D-11..D-14, FOUND-04)
**Code (paste into task action):**
```python
from __future__ import annotations
import os
from pathlib import Path

def confine_to(case_dir: str | os.PathLike, path: str | os.PathLike) -> Path:
    """Reject path-traversal escapes from a case directory.

    Returns the canonical resolved Path of `path` joined under `case_dir`.
    Raises ValueError on every rejection path (D-13). Never raises FileNotFoundError
    for the target — non-existing leaf is the legitimate write case.
    """
    # NUL byte rejection (D-13): must precede any Path operation. Path.resolve silently
    # truncates at NUL on some platforms; check the raw string form first.
    case_str = os.fspath(case_dir)
    path_str = os.fspath(path)
    if "\x00" in case_str or "\x00" in path_str:
        raise ValueError("path contains NUL byte")

    # D-11 step 1: case_dir must exist and be a directory.
    try:
        resolved_case = Path(case_str).resolve(strict=True)
    except (FileNotFoundError, OSError) as exc:
        raise ValueError(f"case_dir does not exist: {case_str!r}") from exc
    if not resolved_case.is_dir():
        raise ValueError(f"case_dir is not a directory: {case_str!r}")

    # D-11 step 2: join relative onto case_dir; absolute as-is.
    candidate = Path(path_str)
    if not candidate.is_absolute():
        candidate = resolved_case / candidate

    # D-11 step 3: resolve target with strict=False (non-existing leaf is OK; intermediate
    # symlinks are followed).
    resolved_target = candidate.resolve(strict=False)

    # D-11 step 4: containment via is_relative_to (Python 3.9+, container is 3.11+).
    # Includes case_dir itself (target == case_dir is allowed).
    if not (resolved_target == resolved_case or resolved_target.is_relative_to(resolved_case)):
        raise ValueError(f"path escapes case_dir: {path_str!r}")

    return resolved_target
```

**Key verifications:**
- `Path.resolve(strict=False)` on a non-existing leaf returns the canonical absolute path with all existing parents resolved through symlinks; the leaf is left as-is. This is exactly what we need for write-side use cases (`write_artifact`, log file creation). [VERIFIED: Python docs `Path.resolve`]
- `Path.is_relative_to(other)` returns True if `self` is rooted at `other`; **strict prefix** containment. Available since 3.9. [VERIFIED: Python docs]
- `Path.resolve()` follows intermediate symlinks and any leaf symlink that exists, so D-12 ("symlinks whose target leaves case_dir are rejected") falls out naturally — no separate `lstat` walk required.
- **NUL byte handling:** `pathlib.Path("a\x00b")` raises `ValueError` on Python 3.11+ when materialized to OS form, but `Path("a").resolve()` against a *string* `"a\x00b"` has had historical surprises. The explicit `"\x00" in path_str` check is belt-and-suspenders; it also gives a uniform `ValueError` message regardless of where the NUL appeared.

### Anti-Patterns to Avoid
- **`proc.communicate()` for unbounded output** — buffers everything; OOM on 100 MB. Pitfall 1.
- **`stderr=asyncio.subprocess.STDOUT`** — merges streams; loses `stderr_head` vs `stdout_head` distinction; breaks D-03 return shape.
- **ANSI-stripping the file sink** — destroys forensic fidelity; misaligns `stdout_bytes_total` with on-disk size; complicates partial-chunk handling.
- **Decoding bytes to `str` before the boundary truncation** — `bytes.decode("utf-8", errors="replace")` on a mid-codepoint slice produces `�` characters that are hard to distinguish from genuinely-malformed input.
- **Trying SIGTERM before SIGKILL** — D-17 explicitly forbids; the grace period belongs to Phase 9 Jobs.
- **`os.killpg(proc.pid, ...)` instead of `os.killpg(os.getpgid(proc.pid), ...)`** — works in practice because `start_new_session=True` makes them equal, but `getpgid` is the portable documented form. (Note v1.0's `subprocess_runner.py:64` uses the shorter form; Phase 6 prefers the explicit form.)
- **Auto-deriving slug from `argv[0]`** — D-09 forbids; argv[0] might be `env`, `bash`, or an absolute path.
- **Returning absolute `log_path`** — D-10 forbids; leaks host paths through MCP.
- **Catching `BaseException` in the cleanup** — only `(asyncio.TimeoutError, asyncio.CancelledError)`. Catching wider would mask programmer errors (FileNotFoundError on argv[0], PermissionError on log).

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Path containment | Custom `startswith(real_case + os.sep)` (the v1.0 pattern at `tools/artifacts.py:128-131`) | `Path.is_relative_to` after `resolve(strict=False)` | `startswith` has subtle bugs with trailing slashes and case-equality; `is_relative_to` is the explicit stdlib primitive added for exactly this case. |
| UTF-8 boundary truncation | Naive `buf[:N].decode("utf-8", errors="ignore")` | The 4-byte-walk-back algorithm in Pattern 3 | `errors="ignore"` silently drops partial codepoints, producing inconsistent byte/char counts in the return dict. Pattern 3 finds the largest valid prefix; decode-with-replace is then guaranteed safe at the boundary. |
| Process-group SIGKILL | `os.kill(proc.pid, SIGKILL)` (kills only the leader) | `os.killpg(os.getpgid(proc.pid), SIGKILL)` | Pipeline children (`strings huge.bin \| grep …`) are in the pgroup but not children of `proc.pid` directly; killing only the leader leaves zombie pipeline tails. |
| Concurrent pipe drain | Manual `while True: stdout = await read; stderr = await read` round-robin loop | `asyncio.gather(_drain_stdout(), _drain_stderr())` | Sequential reads deadlock when one pipe fills while the other is being read. Gather runs both as parallel tasks. |
| Cancellation-safe cleanup | Plain `finally: await proc.wait()` | `await asyncio.shield(proc.wait())` | Without `shield`, a cancel cascade from the caller can interrupt the wait, leaving a zombie. Pitfall 18. |
| Unique log filename suffix | `time.time_ns()` microsecond suffix | `secrets.token_hex(2)` per D-09 | Microsecond suffixes can still collide under concurrent calls and look ugly; 4 hex chars give 65k buckets, race is astronomically improbable at the contemplated rates. |
| Subprocess RSS measurement | `psutil.Process(pid).memory_info()` (requires psutil dep) | `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss` | Stdlib; covers all reaped children; KB on Linux. Container is Linux-only. |
| ANSI strip | Hand-written byte-by-byte state machine | Module-level `re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")` | Covers >99% of RE-tool sequences (CSI SGR + cursor); easy to widen later for OSC if Phase 7 testing surfaces a gap. |
| Env-var validation | Per-call parsing inside `ReToolRunner.run()` | Module-import-time validation mirroring `uploads._max_bytes()` | Fail-fast at gateway startup, not on the first tool call. Matches D-08 and the existing project convention. |

**Key insight:** Every problem above has a stdlib answer in Python 3.11. The temptation to wrap `subprocess.Popen`, hand-roll regex, or reach for `psutil` exists only because the asyncio subprocess docs are scattered. Phase 6 is the foundation that paves the cowpath — the seven Patterns above are the durable contract.

## Runtime State Inventory

> Phase 6 is a greenfield phase (no existing `runner.py` to rename; no migration). This section is included for completeness only — all categories are explicitly "nothing."

| Category | Items Found | Action Required |
|----------|-------------|-----------------|
| Stored data | None — Phase 6 introduces new modules; no rename of any existing key, collection, or ID | None |
| Live service config | None — no MCP tool registration in Phase 6; no n8n/Datadog/Tailscale equivalents in this project | None |
| OS-registered state | None — no Task Scheduler, pm2, launchd, systemd registrations touched | None |
| Secrets/env vars | NEW env vars introduced (D-08): `MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB`, `MCP_GATEWAY_RUNNER_STDERR_HEAD_KB`, `MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S`, `MCP_GATEWAY_RUNNER_MAX_LOG_MB`. All have built-in defaults; no migration of an existing key. | Document in CLAUDE.md / phase docs at the end of Phase 6. No code that reads "old names" exists. |
| Build artifacts | None — `pip install -e mcp-gateway/[dev]` re-resolves; no stale egg-info from a rename because no rename occurred. | None |

**Canonical question check:** *After every file in the repo is updated, what runtime systems still have the old string cached, stored, or registered?* — Nothing, because no string is being renamed. Phase 6 is purely additive.

## Common Pitfalls

### Pitfall 1: PIPE deadlock on large subprocess output (PITFALLS.md §1)
**What goes wrong:** `proc.communicate()` reads all of stdout+stderr into memory; 100 MB urandom OOMs or hangs.
**Why it happens:** Devs cargo-cult the v1.0 `run_script` pattern which uses `communicate()` (safe for small JSON outputs but not for RE tools).
**How to avoid:** Pattern 1 + Pattern 2 above — concurrent drain with head cap + file sink that keeps draining past the cap.
**Warning signs:** Test against 100 MB `/dev/urandom` exceeds 60 s; gateway RSS climbs to multi-GB on `objdump -d`.

### Pitfall 3: ANSI escapes saved to artifacts, slow-loris hang (PITFALLS.md §3)
**What goes wrong:** Raw ANSI in `tool-logs/*.txt`; agent reads garbled output; sleep-until-timeout commands burn the wallclock.
**Why it happens:** ANSI strip and timeout are easy to add and easy to forget interact (timeout must include drain time).
**How to avoid:** Module-level ANSI regex (Pattern 7). `asyncio.wait_for` includes drain time (Pattern 5). `TERM=dumb`/`NO_COLOR=1` env (defense in depth — applied by Phase 7's `run_shell`, not by `ReToolRunner` directly).
**Warning signs:** `cat tool-logs/<file>.txt | grep $'\\x1b'` returns matches; tests with `sleep 700; echo hi` don't return in `timeout + 1s`.

### Pitfall 4: Process-group cleanup leaks grandchildren (PITFALLS.md §4)
**What goes wrong:** `setsid()`'d grandchildren escape the pgroup; `asyncio` cancels the Python task but not the OS process.
**Why it happens:** Linux pgroups are per-process; kernel doesn't track grandchildren after `setsid`.
**How to avoid:** `start_new_session=True` + `os.killpg(os.getpgid(proc.pid), SIGKILL)` swallowing `(ProcessLookupError, PermissionError)` (Pattern 4).
**Note:** Phase 6 explicitly defers the `/proc/<pid>/task/*/children` follow-fork scan to Phase 11 (D-18) — `strace -f` doesn't ship until then.
**Warning signs:** `ps -ef` shows `<defunct>` orphans after a cancelled call; `pgrep -g <pgid>` after cleanup returns rows.

### Pitfall 12: MCP 25k-token result cap silent client-side truncation (PITFALLS.md §12)
**What goes wrong:** Gateway returns 200 KB; client truncates silently; agent reads partial data.
**Why it happens:** Client cap is opaque to the server.
**How to avoid:** Return head (≤ 256 KB stdout / 64 KB stderr per D-08) + `log_path` + `stdout_truncated`/`stdout_bytes_total`. The dict shape (D-03) is the contract.
**Warning signs:** A `run_*` tool returns a `stdout_head` larger than its head_kb cap; an MCP client sees `...truncated` markers from FastMCP.

### Pitfall 18: FastMCP request cancellation does not cancel the subprocess (PITFALLS.md §18)
**What goes wrong:** Client disconnects; `asyncio.CancelledError` raised in the tool handler; subprocess keeps running for the full nominal timeout.
**Why it happens:** asyncio cancels Python tasks, not OS processes.
**How to avoid:** Pattern 4 — `asyncio.shield(proc.wait())` after `killpg`, then re-raise the `CancelledError`.
**Warning signs:** Test: spawn `sleep 60`, cancel after 1 s, assert process dead within 200 ms (the contract assertion).

## Code Examples

### §1 — Module skeleton for `runner.py`
```python
# Source: synthesized from subprocess_runner.py + CONTEXT.md D-01..D-21
"""ReToolRunner: chokepoint subprocess primitive for v1.1 RE tools."""
from __future__ import annotations

import asyncio
import os
import re
import signal
import time
from pathlib import Path
from typing import Optional

from . import artifacts_io

_ANSI_ESCAPE = re.compile(rb"\x1b\[[0-9;]*[A-Za-z]")


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        v = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from e
    if v < 0:
        raise RuntimeError(f"{name} must be >= 0, got {v}")
    return v


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        v = float(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be a float, got {raw!r}") from e
    if v < 0:
        raise RuntimeError(f"{name} must be >= 0, got {v}")
    return v


# Module-level defaults — read once at import (D-08 + uploads._max_bytes pattern).
STDOUT_HEAD_KB = _env_int("MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB", 256)
STDERR_HEAD_KB = _env_int("MCP_GATEWAY_RUNNER_STDERR_HEAD_KB", 64)
DEFAULT_TIMEOUT_S = _env_float("MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S", 55.0)
MAX_LOG_MB = _env_int("MCP_GATEWAY_RUNNER_MAX_LOG_MB", 256)
```

### §2 — UTF-8 boundary truncation (paste-ready)
```python
# Source: Pattern 3 above (no published library; this is the standard algorithm).
def _truncate_to_utf8_boundary(buf: bytes, n: int) -> bytes:
    if n >= len(buf):
        return buf
    cut = n
    for _ in range(4):
        if cut == 0:
            return b""
        if (buf[cut] & 0xC0) != 0x80:
            return buf[:cut]
        cut -= 1
    return buf[:cut]
```

### §3 — Concurrent drain coroutine
```python
# Source: Pattern 1 + Pattern 2.
async def _drain(
    stream: asyncio.StreamReader,
    head_cap_bytes: int,
    file_sink,                       # an open BinaryIO in "ab" mode, buffering=0
    log_cap_bytes: int,
) -> tuple[bytes, int, bool, bool]:
    """Return (head_bytes, total_bytes, head_truncated, log_truncated)."""
    head = bytearray()
    total = 0
    head_truncated = False
    log_truncated = False
    log_written = 0
    while True:
        chunk = await stream.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if log_written + len(chunk) > log_cap_bytes:
            # Write the partial that fits, then refuse further writes.
            remaining = log_cap_bytes - log_written
            if remaining > 0:
                file_sink.write(chunk[:remaining])
                log_written = log_cap_bytes
            log_truncated = True
            # Still consume the rest of the pipe to avoid child block.
            # But we don't store it anywhere — drain & drop.
        else:
            file_sink.write(chunk)
            log_written += len(chunk)
        if not head_truncated:
            remaining_head = head_cap_bytes - len(head)
            if remaining_head > 0:
                head.extend(chunk[:remaining_head])
            if len(head) >= head_cap_bytes and len(chunk) > remaining_head:
                head_truncated = True
            elif len(chunk) > remaining_head and remaining_head == 0:
                head_truncated = True
    return bytes(head), total, head_truncated, log_truncated
```

### §4 — Cancellation contract (Pattern 4 expanded)
```python
# Source: PITFALLS.md §18 + CONTEXT.md D-17.
proc = await asyncio.create_subprocess_exec(
    *argv,
    cwd=str(resolved_case_dir),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    env=env,
    start_new_session=True,
)
t0 = time.monotonic()
try:
    drain_task = asyncio.gather(
        _drain(proc.stdout, stdout_cap, sink_stdout, log_cap),
        _drain(proc.stderr, stderr_cap, sink_stderr, log_cap),
    )
    await asyncio.wait_for(
        asyncio.gather(proc.wait(), drain_task),
        timeout=timeout,
    )
    timed_out = False
except asyncio.TimeoutError:
    timed_out = True
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    await asyncio.shield(proc.wait())
except asyncio.CancelledError:
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass
    await asyncio.shield(proc.wait())
    raise
duration_s = time.monotonic() - t0
```

### §5 — Module-level config validation (uploads._max_bytes template)
```python
# Source: mcp-gateway/src/mcp_gateway/uploads.py:31-66 (verified pattern).
# Same shape as _env_int / _env_float in §1: read once at import, raise RuntimeError on bad.
```

### §6 — Log path naming (D-09)
```python
# Source: CONTEXT.md D-09.
import datetime
import secrets
from pathlib import Path

def tool_log_path(case_dir: str | Path, slug: str) -> Path:
    """Return case_dir/tool-logs/<%Y%m%dT%H%M%SZ>-<slug>-<rand4>.txt.

    Caller is responsible for ensure_subdir(case_dir, "tool-logs") before writing.
    """
    if not _SLUG_RE.fullmatch(slug.lower()):
        raise ValueError(f"slug fails validation: {slug!r}")
    slug = slug.lower()
    ts = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rand4 = secrets.token_hex(2)  # 4 hex chars
    return Path(case_dir) / "tool-logs" / f"{ts}-{slug}-{rand4}.txt"

_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")
```

### §7 — Slug regex validation (D-09 + D-15)
```python
# Source: CONTEXT.md D-09 "auto-lowercased before validation".
import re
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

def _validate_slug(slug: str) -> str:
    """Lowercase, then validate. Returns the canonical lowercased form."""
    lowered = slug.lower()
    if not _SLUG_RE.fullmatch(lowered):
        raise ValueError(
            f"slug must match {_SLUG_RE.pattern!r} (after lowercase), got {slug!r}"
        )
    return lowered
```

### §8 — `ensure_subdir` (D-15 + D-16)
```python
# Source: CONTEXT.md D-15, D-16.
from pathlib import Path

EXPANDED_CASE_SUBDIRS: tuple[str, ...] = (
    "tool-logs",
    "extracted",
    "hex",
    "rop",
    "dynamic",
    "qemu",
    "disassembly",
    "decompilation",
    "xrefs",
)


def ensure_subdir(case_dir: str | Path, name: str) -> Path:
    """Lazily create case_dir/<name>, return resolved path. Idempotent."""
    lowered = _validate_slug(name)            # reuses §7
    target = Path(case_dir) / lowered
    target.mkdir(parents=False, exist_ok=True)
    return target.resolve(strict=True)
```

### §9 — `confine_to` (full implementation, see Pattern 8 above)
See Pattern 8 — the complete D-11..D-14 implementation including NUL byte rejection, strict=True case_dir resolve, strict=False target resolve, is_relative_to containment.

### §10 — RSS measurement for SC-4
```python
# Source: Linux man getrusage(2) + Python `resource` stdlib docs.
import resource
import asyncio

async def test_oom_safety_100mb_urandom(tmp_path):
    """SC-4: 100 MB stdout completes with bounded RSS (delta < 32 MB)."""
    rss_before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    runner = ReToolRunner(case_dir=case_dir, slug="urandom", timeout=60.0)
    result = await runner.run(["bash", "-c", "head -c 104857600 /dev/urandom"])
    rss_after = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    # ru_maxrss is kilobytes on Linux.
    assert result["exit_code"] == 0
    assert result["stdout_bytes_total"] == 104857600
    assert result["stdout_truncated"] is True
    # Generous bound: head buffer + file write buffers + bash + head overhead
    # should be well under 32 MB (32 * 1024 KB).
    assert (rss_after - rss_before) < 32 * 1024, \
        f"RSS grew by {(rss_after - rss_before) // 1024} MB — possible OOM regression"
```

## State of the Art

| Old Approach (v1.0 `subprocess_runner.run_script`) | New Approach (v1.1 `ReToolRunner`) | When Changed | Impact |
|---------------------------------------------------|------------------------------------|--------------|--------|
| `proc.communicate()` + raise on timeout | concurrent drain via `asyncio.gather` + head buffer + file sink + return dict (never raise on subprocess state) | This phase | Unblocks 100 MB+ outputs; lets MCP tools convert one runner result into one MCP response shape uniformly |
| `raise asyncio.TimeoutError` on timeout | return `{timed_out: True, exit_code: -9, ...}` (D-04) | This phase | Tool handlers no longer wrap in `try/except TimeoutError`; uniform branching on `timed_out` |
| `os.killpg(proc.pid, SIGKILL)` (works but implicit) | `os.killpg(os.getpgid(proc.pid), SIGKILL)` swallowing `(ProcessLookupError, PermissionError)` | This phase | Portable form; Pitfall 4 `PermissionError` swallow added |
| Plain `await proc.wait()` after killpg | `await asyncio.shield(proc.wait())` | This phase | Pitfall 18 — cleanup survives cancel cascade |
| No log capture (callers post-process `stdout` themselves) | Auto-capture to `case_dir/tool-logs/<…>.txt`, return relative path | This phase | Pitfall 12 — head + log_path is the new uniform contract |
| Inline path-traversal guard (`tools/artifacts.py:115-139`) | Extracted to `artifacts_io.confine_to` with `is_relative_to` | This phase | Pitfall 7 — every path-accepting tool calls the same helper; matches v1.0's `startswith` semantics |

**Deprecated/outdated:**
- The `startswith(real_case + os.sep)` containment idiom (still live in `tools/artifacts.py:130`) is correct but verbose. Phase 6 deliberately does NOT rewrite it (deferred per CONTEXT.md "Deferred Ideas"). A Phase 7 task may swap it for `confine_to` if quick.
- `asyncio.wait_for` is not deprecated despite the addition of `asyncio.timeout` in 3.11 — both are supported. We prefer `wait_for` here.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | The CSI regex `\x1b\[[0-9;]*[A-Za-z]` covers all sequences emitted by Phase 7-11 RE tools (`objdump`, `strings`, `xxd`, `capstone`, `readelf`, `nm`) when those tools are invoked **without** explicit color flags | Pattern 7 | LOW — tools default to no-color when stdout is a pipe. If a Phase 7 wrapper passes `--color=always`, gaps will surface in that phase's testing; widening the regex to also strip OSC is a one-line change with no API impact. [CITED: PITFALLS.md §3, CONTEXT.md Claude's Discretion] |
| A2 | Synchronous `open(log_path, "ab", buffering=0)` writes do not meaningfully block the event loop at 100 MB / 1-2 s throughput | Pattern 6 | LOW — verifiable by SC-4 wall-clock assertion. If wrong, switch to `aiofiles` (one import + one open-context change). |
| A3 | `resource.getrusage(RUSAGE_CHILDREN).ru_maxrss` returns kilobytes on Linux | Pattern in Code Example §10 | [VERIFIED: Linux man getrusage(2)] — on Linux specifically, `ru_maxrss` is in KB. (On macOS it's bytes — but the container is Linux.) |
| A4 | The 100 MB urandom test completes in < 60 s on stock developer hardware | SC-4 | LOW — `bash + head + /dev/urandom` is millisecond-deterministic. Marked `slow` per D-21 to allow CI gating. |
| A5 | Phase 6's `runner.py` does NOT need MCP `Context.report_progress` integration | n/a | LOW — Phase 9 Jobs is the layer that wires progress notifications; Phase 6 is internal-only with no MCP surface. [CITED: CONTEXT.md domain block] |

**Conclusion:** All assumptions are LOW risk. The two unverified ones (A1, A2) are testable inside Phase 6's own SC verification.

## Open Questions

1. **Should `runner.py` import `confine_to` and apply it to `case_dir` before spawning, or trust the caller to pass an already-validated `case_dir`?**
   - What we know: D-07 permits `runner.py` to import from `artifacts_io`. CONTEXT.md D-14 says `confine_to` does NOT enforce `STATUS_ROOT`; that is `resolve_case_dir`'s job. Phase 7+ wrappers compose `resolve_case_dir(case_dir)` then pass to the runner.
   - What's unclear: Does `ReToolRunner.__init__` call `Path(case_dir).resolve(strict=True)` defensively, or does it trust the caller? If it does call resolve, it's a belt-and-suspenders guard against a future wrapper forgetting; if it doesn't, the runner stays leaf.
   - Recommendation: `ReToolRunner.__init__` SHOULD call `Path(case_dir).resolve(strict=True)` and store the resolved form (raising `ValueError` if it fails to exist or isn't a dir). This is cheap, fails fast, and aligns with the spawn-side `cwd=resolved_case_dir`. It does NOT enforce `STATUS_ROOT` — that's still `resolve_case_dir`'s job upstream.

2. **Does the `slow` pytest marker need to be registered in `pyproject.toml`?**
   - What we know: D-21 mandates the 100 MB urandom test be marked `slow`. The existing `pyproject.toml` has `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and `testpaths` set, but no `markers =` block.
   - What's unclear: Without registration, `@pytest.mark.slow` emits a `PytestUnknownMarkWarning`. The test still runs; the warning is cosmetic.
   - Recommendation: Add `markers = ["slow: marks tests as slow (deselect with '-m \"not slow\"')"]` to `[tool.pytest.ini_options]`. One-line addition; surfaces during the plan-phase implementation work.

3. **Should `confine_to` reject NUL bytes in the `case_dir` argument too, or only in `path`?**
   - What we know: D-13 says "raises ValueError on every rejection path (non-existing case_dir, traversal escape, NUL byte, etc.)".
   - Recommendation: Reject NUL in **both** `case_dir` and `path`. The code in Pattern 8 does this. Cheap; eliminates a class of weird-platform-truncation bugs.

## Environment Availability

Phase 6 deliverables run inside the existing Kali container. The runner's tests exercise the runner against `bash`, `head`, `/dev/urandom`, `sleep`, and `printf` — all guaranteed-present in the container and on any analyst dev machine.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `bash` | SC-3 capture test, SC-4 urandom test | ✓ (container + dev hosts) | 5.x | — |
| `/dev/urandom` | SC-4 urandom test | ✓ (Linux) | — | — |
| `head` (coreutils) | SC-4 urandom test | ✓ | 9.x | — |
| `sleep` | SC-1 timeout test | ✓ | 9.x | — |
| Python ≥ 3.11 | runtime + `is_relative_to` + `asyncio.timeout` | ✓ | 3.11+ pin in `mcp-gateway/pyproject.toml` | — |
| `pytest` ≥ 8 | test runner | ✓ (`[dev]` extras) | 8.x | — |
| `pytest-asyncio` ≥ 0.23 | async tests | ✓ (`[dev]` extras + `asyncio_mode = "auto"`) | 0.23+ | — |
| `resource` stdlib (Linux `RUSAGE_CHILDREN`) | SC-4 RSS measurement | ✓ (Linux) | — | If running tests on macOS, ru_maxrss returns bytes (not KB) — divide by 1024 only on Linux. **Recommendation:** test asserts `sys.platform.startswith("linux")` before measuring, skip on other platforms with `pytest.skip("Linux-only RSS measurement")`. |
| `slow` pytest marker | D-21 | ✗ (not yet registered) | — | Register in `pyproject.toml` `[tool.pytest.ini_options].markers` (see Open Question 2). |

**Missing dependencies with no fallback:** None.

**Missing dependencies with fallback:** `slow` marker registration is a one-line addition during implementation.

## Validation Architecture

> Phase 6 has nyquist_validation enabled (config.json `workflow.nyquist_validation = true`). This section is required to unlock the VALIDATION.md template; without it, plans fail Dimension 8.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.23+ (`asyncio_mode = "auto"`) |
| Config file | `mcp-gateway/pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `cd mcp-gateway && pytest tests/test_runner.py tests/test_artifacts_io.py -x -m 'not slow' -ra` |
| Full suite command | `cd mcp-gateway && pytest -x -ra` |
| Slow-included command | `cd mcp-gateway && pytest tests/test_runner.py -x -ra` (the `slow` SC-4 test runs by default unless deselected) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| FOUND-02 / SC-1a chokepoint | `runner.py` does not contain `shell=True` | unit (source grep) | `pytest tests/test_runner.py::test_runner_never_uses_shell_true -x` | ❌ Wave 0 |
| FOUND-02 / SC-1b cwd-confine | Subprocess CWD equals resolved `case_dir` | unit (async) | `pytest tests/test_runner.py::test_cwd_is_resolved_case_dir -x` | ❌ Wave 0 |
| FOUND-02 / SC-1c timeout SIGKILL | `sleep 60` w/ `timeout=0.5` → `timed_out=True`, process dead within 200 ms | unit (async + monkeypatch or real spawn) | `pytest tests/test_runner.py::test_timeout_kills_process_group -x` | ❌ Wave 0 |
| FOUND-02 / SC-1d cancel propagation | Wrap spawn in task, cancel, assert subprocess dead within 200 ms | unit (async) | `pytest tests/test_runner.py::test_cancel_propagates_to_killpg -x` | ❌ Wave 0 |
| FOUND-02 / SC-2 return shape | All 12 D-03 keys present, correct types, `argv` and `slug` echoed | unit (async) | `pytest tests/test_runner.py::test_return_shape_locked -x` | ❌ Wave 0 |
| FOUND-03 / SC-3 auto-capture | stdout/stderr written to `tool-logs/`; `log_path` returned relative; head preview matches first N bytes (ANSI-stripped) | unit (async + tmp_path) | `pytest tests/test_runner.py::test_log_capture_and_head_alignment -x` | ❌ Wave 0 |
| FOUND-02 / SC-4 OOM safety | 100 MB urandom → `exit_code=0`, `stdout_bytes_total=104857600`, `stdout_truncated=True`, RSS delta < 32 MB | unit (async, marked `slow`) | `pytest tests/test_runner.py::test_100mb_urandom_bounded_rss -x` | ❌ Wave 0 |
| FOUND-04 / SC-5a confine_to relative-allowed | `case_dir/foo.txt` → returns resolved path under case_dir | unit | `pytest tests/test_artifacts_io.py::test_confine_to_allows_relative_inside -x` | ❌ Wave 0 |
| FOUND-04 / SC-5b confine_to non-existing leaf allowed | `case_dir/sub/bar.txt` not-yet-existing → returns resolved path | unit | `pytest tests/test_artifacts_io.py::test_confine_to_allows_nonexisting_leaf -x` | ❌ Wave 0 |
| FOUND-04 / SC-5c traversal rejected | `case_dir/../../etc/passwd` → `ValueError` | unit | `pytest tests/test_artifacts_io.py::test_confine_to_rejects_traversal -x` | ❌ Wave 0 |
| FOUND-04 / SC-5d absolute-outside rejected | absolute `/etc/passwd` → `ValueError` | unit | `pytest tests/test_artifacts_io.py::test_confine_to_rejects_absolute_outside -x` | ❌ Wave 0 |
| FOUND-04 / SC-5e symlink-inside allowed | symlink in case_dir → target in case_dir → allowed | unit | `pytest tests/test_artifacts_io.py::test_confine_to_allows_inside_symlink -x` | ❌ Wave 0 |
| FOUND-04 / SC-5f symlink-outside rejected | symlink in case_dir → /etc/passwd → `ValueError` | unit | `pytest tests/test_artifacts_io.py::test_confine_to_rejects_escaping_symlink -x` | ❌ Wave 0 |
| FOUND-04 / SC-5g NUL byte rejected | path with `\x00` → `ValueError` | unit | `pytest tests/test_artifacts_io.py::test_confine_to_rejects_nul_byte -x` | ❌ Wave 0 |
| D-09 log naming | filename matches `^<ts>-<slug>-[0-9a-f]{4}\.txt$`; same-second concurrent calls collide-free via `rand4` | unit | `pytest tests/test_artifacts_io.py::test_tool_log_path_format -x` and `::test_tool_log_path_no_collision -x` | ❌ Wave 0 |
| D-15 ensure_subdir idempotent | Two concurrent calls for same subdir do not raise; resolves to existing dir | unit (async) | `pytest tests/test_artifacts_io.py::test_ensure_subdir_idempotent -x` | ❌ Wave 0 |
| D-15 ensure_subdir slug regex | `BADNAME!!` rejected with `ValueError` | unit | `pytest tests/test_artifacts_io.py::test_ensure_subdir_validates_slug -x` | ❌ Wave 0 |
| D-16 EXPANDED_CASE_SUBDIRS catalog | Tuple contains exactly the 9 names from REQUIREMENTS.md ARTIF-01; freshly-created case_dir has no subdirs (lazy) | unit | `pytest tests/test_artifacts_io.py::test_expanded_case_subdirs_catalog -x` and `::test_no_empty_subdirs_at_case_init -x` | ❌ Wave 0 |
| D-08 env validation | Bad `MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S=abc` at import → `RuntimeError` | unit (subprocess import) | `pytest tests/test_runner.py::test_env_validation_rejects_bad_values -x` | ❌ Wave 0 |
| Manifest regression | Module imports do not introduce new top-level pip deps | regression grep | `pytest tests/test_runner.py::test_no_new_pip_deps -x` (greps `runner.py` + `artifacts_io.py` for forbidden imports) | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd mcp-gateway && pytest tests/test_runner.py tests/test_artifacts_io.py -x -m 'not slow' -ra` (≤ 5 s expected — pure stdlib, hermetic tmp_path).
- **Per wave merge:** `cd mcp-gateway && pytest tests/test_runner.py tests/test_artifacts_io.py -x -ra` (includes the `slow` SC-4 test; ≤ 30 s expected).
- **Phase gate:** `cd mcp-gateway && pytest -x -ra` — full suite green (existing 18 v1.0 files + Phase 5's `test_image_hash.py` + the two new Phase 6 files) before `/gsd-verify-work`.

### Wave 0 Gaps
- [ ] `mcp-gateway/tests/test_runner.py` — covers FOUND-02, FOUND-03, D-08, D-09 (a subset), Pitfall 18.
- [ ] `mcp-gateway/tests/test_artifacts_io.py` — covers FOUND-04, D-09 (full), D-15, D-16, Pitfall 7.
- [ ] `mcp-gateway/pyproject.toml` — register `markers = ["slow: marks tests as slow"]` under `[tool.pytest.ini_options]`.

**Note:** No new framework install — pytest + pytest-asyncio are already `[dev]` deps; `tmp_path` is built-in.

## Security Domain

> `security_enforcement` is not explicitly disabled in `.planning/config.json` — treated as enabled per default.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase 6 has no MCP surface; no auth boundary touched |
| V3 Session Management | no | No session state in Phase 6 (Phase 8) |
| V4 Access Control | yes | `confine_to` enforces case-dir confinement; `resolve_case_dir` composed upstream enforces `STATUS_ROOT` containment |
| V5 Input Validation | yes | Slug regex, NUL byte rejection, argv-only spawn (no shell metacharacter exposure), env var sanity-check at import |
| V6 Cryptography | no | No new crypto in Phase 6 (`secrets.token_hex(2)` is for collision suffix, not security — and stdlib `secrets` is the correct primitive) |
| V7 Error Handling | yes | `ValueError` on every rejection path (D-13); `RuntimeError` on bad env at import (D-08); never silently swallow programmer errors |
| V12 File / Resources | yes | Log file write-cap (`MAX_LOG_MB`), path-traversal containment, NUL byte rejection, log paths returned relative (no host-path leak through MCP) |

### Known Threat Patterns for Python asyncio subprocess

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Path traversal via `..` or symlink | Tampering / Info-disclosure | `Path.resolve(strict=False)` + `is_relative_to` (`confine_to`) |
| Symlink-escape via in-case-dir symlink pointing outside | Tampering / Info-disclosure | Same `confine_to` check — `resolve()` follows the link to its target before the containment check |
| NUL byte truncation of path arg | Tampering | Explicit `"\x00" in str` rejection before any `Path` op |
| Shell injection via argv element interpretation | Tampering / Elevation | Argv-only `asyncio.create_subprocess_exec` (no `shell=True`); enforced by `test_runner_never_uses_shell_true` source grep |
| Process-group zombie / DoS | Denial of Service | `start_new_session=True` + `killpg(SIGKILL)` + `(ProcessLookupError, PermissionError)` swallow + `asyncio.shield(proc.wait())` |
| PIPE-buffer OOM / resource exhaustion | Denial of Service | Concurrent drain + head buffer + file sink (Pitfall 1 mitigation); log-cap kills child on overrun |
| Slow-loris (output below cap, infinite duration) | Denial of Service | Wallclock timeout via `asyncio.wait_for` — drain time included in budget |
| ANSI escape injection via filenames or sample content | Tampering (terminal hijack) | Module-level CSI regex strip on head slice before decode |
| Mid-UTF-8-codepoint truncation producing inconsistent encoding | Info-disclosure (subtle) | Pattern 3 boundary truncation before decode |
| Env-var leak into subprocess (e.g., `MCP_GATEWAY_TOKEN`) | Info-disclosure | NOT a Phase 6 concern — Phase 7's `run_shell` does env scrub. Phase 6 `ReToolRunner` accepts caller-supplied `env`; default behavior matches `subprocess_runner` (inherits `os.environ.copy()`). Wrappers in Phase 7+ are responsible for whitelist scrub. **Document this in the runner docstring.** |
| Log file write outside case_dir | Tampering | `log_path` is constructed via `tool_log_path(case_dir, slug)` then implicitly under `case_dir/tool-logs/` (D-09); no caller-supplied component bypasses this. |

**Phase 6 explicitly defers:**
- `mare-shell` UID drop, mount namespace, env scrub — all Phase 7 (where `run_shell` ships).
- ptrace/strace permission gates — Phase 11.
- Sample sha256 verification — Phase 10 (`promote_extracted_sample`).

## Sources

### Primary (HIGH confidence)
- `mcp-gateway/src/mcp_gateway/subprocess_runner.py:52-67` — v1.0 spawn/cleanup pattern (verified)
- `mcp-gateway/src/mcp_gateway/tools/artifacts.py:115-139` — inline path-traversal guard (verified)
- `mcp-gateway/src/mcp_gateway/uploads.py:31-66` — `_max_bytes()` env-validation template (verified)
- `mcp-gateway/src/mcp_gateway/tools/case_dirs.py:10-23` — `resolve_case_dir` to compose with `confine_to` (verified)
- `mcp-gateway/tests/test_image_hash.py` — Phase 5 hermetic-pytest pattern (verified)
- `mcp-gateway/tests/test_sample_resolution.py:97-151` — `test_run_script_*` patterns including `shell=True` grep and `killpg`-via-monkeypatch (verified — `test_run_script_never_uses_shell_true` exists at line 148)
- `mcp-gateway/tests/conftest.py` — shared fixture style (verified; `tmp_path` is sufficient for Phase 6)
- `mcp-gateway/pyproject.toml` — confirms Python ≥3.11, anyio ≥4.5 pinned, `asyncio_mode = "auto"`, no `slow` marker yet (verified)
- `.planning/research/PITFALLS.md` §§1, 3, 4, 12, 18 — top-five pitfalls the runner addresses (verified)
- `.planning/research/SUMMARY.md` "Recommended Stack" + "Critical Pitfalls" (verified)
- `.planning/REQUIREMENTS.md` FOUND-02, FOUND-03, FOUND-04 (verified)
- `.planning/ROADMAP.md` Phase 6 — 5 success criteria (verified)
- `.planning/phases/06-retoolrunner-artifacts-io-foundation/06-CONTEXT.md` — D-01..D-21 contract (verified)
- Python stdlib docs: `asyncio.create_subprocess_exec`, `asyncio.wait_for`, `asyncio.shield`, `Path.resolve`, `Path.is_relative_to`, `resource.getrusage` (verified against Python 3.11 docs)
- Linux man `getrusage(2)` — `ru_maxrss` is kilobytes on Linux (verified)

### Secondary (MEDIUM confidence)
- ANSI escape coverage table (Pattern 7) — based on knowledge of objdump/binutils/coreutils color flag conventions, not exhaustively tested in this session. Verifiable during Phase 7 runner integration testing.

### Tertiary (LOW confidence)
- None. All design-load-bearing claims are either verified in this session or cited from CONTEXT.md / research docs.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all primitives are stdlib + already-pinned `anyio`; verified Python ≥3.11 in pyproject.toml
- Architecture patterns: HIGH — every pattern has a stdlib primitive backing it; reference implementation in `subprocess_runner.py` already validates the spawn shape
- Pitfalls: HIGH — five load-bearing pitfalls are pre-cataloged in `.planning/research/PITFALLS.md` with verified mitigations; CONTEXT.md D-17/D-18 lock the cleanup contract
- Code examples: HIGH — direct paste-ready snippets, each tagged with source provenance
- Validation architecture: HIGH — test framework already in place; new test files are the only Wave 0 gap

**Research date:** 2026-05-13
**Valid until:** 2026-06-13 (30 days; stack is mature stdlib, low churn risk)
