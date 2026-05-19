"""ReToolRunner: chokepoint subprocess primitive for v1.1 RE tools (Phase 6).

Public API:
- `ReToolRunner.run(argv, *, proc_callback=None)` -- class form (D-01). Hold
  across multiple ops in Phase 8 sessions / Phase 9 jobs. The optional
  `proc_callback` kwarg (Phase 9 Q4) fires once with the live Process
  immediately after spawn so registry owners can capture pid+pgid for cancellation.
- `run_tool` -- module-level convenience (D-02). One-shot use in Phase 7 typed wrappers.
- Module constants `STDOUT_HEAD_KB`, `STDERR_HEAD_KB`, `DEFAULT_TIMEOUT_S`, `MAX_LOG_MB` --
  read once at module import from `MCP_GATEWAY_RUNNER_*` env vars (D-08).

Design contract (locked for Phase 7+ consumers):
- argv-only spawn via `asyncio.create_subprocess_exec` -- never the shell-invocation kwarg (D-04 / T-6-02)
- cwd pinned to `Path(case_dir).resolve(strict=True)` -- fails fast if case_dir is invalid
- `start_new_session=True` so the runner can `killpg` the whole pgroup (Pitfall 4)
- Concurrent stdout/stderr drain via `asyncio.gather` -- never the blocking `communicate`
  shortcut (Pitfall 1)
- Head buffer + raw file sink -- `stdout_head` <= STDOUT_HEAD_KB; full bytes go to
  `tool-logs/<...>.txt` (Pitfall 12 + FOUND-03)
- ANSI strip + UTF-8 boundary truncation on the head slice only (Pattern 2 + Pattern 3)
- On timeout: return `{timed_out=True, exit_code=-9, ...}` -- never raises (D-04)
- On CancelledError: killpg + `asyncio.shield(proc.wait())` then re-raise (D-17 / Pitfall 18)
- Returns dict with 12 locked keys in D-03 order
- On timeout (`timed_out=True`), `stdout_bytes_total`, `stderr_bytes_total`, `*_head`,
  and `*_truncated` are reset to placeholder values (0 / empty / False) because the
  drain tasks are cancelled by `asyncio.wait_for`. Full bytes remain captured on disk
  at `log_path`; consumers needing accurate byte counts on timeout must read the
  log file.

Out of scope this phase (explicit references):
- SIGTERM grace period -- Phase 9 Jobs adds it for user-cancel (D-17 commentary)
- Follow-fork straggler scan via /proc -- Phase 11 Dynamic Mode (D-18)
- Env-var scrub (MCP_GATEWAY_TOKEN etc.) -- Phase 7's `run_shell` (this runner inherits
  `os.environ.copy()` unless caller overrides `env`)
"""
from __future__ import annotations

import asyncio
import os
import re
import signal
import time
from pathlib import Path
from typing import Callable, Optional

from mcp_gateway import artifacts_io
from mcp_gateway.artifacts_io import ensure_subdir, tool_log_path

# Module-level CSI ANSI escape regex (operates on bytes -- applied on head slice only).
# Pattern 7: covers CSI SGR (objdump --color, grep --color, etc.). OSC sequences not
# stripped here; Phase 7 may widen for run_shell if real escapes surface.
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


# D-08: read once at module import, raise RuntimeError on bad values.
# uploads._max_bytes is the verified-in-codebase template.
STDOUT_HEAD_KB: int = _env_int("MCP_GATEWAY_RUNNER_STDOUT_HEAD_KB", 256)
STDERR_HEAD_KB: int = _env_int("MCP_GATEWAY_RUNNER_STDERR_HEAD_KB", 64)
DEFAULT_TIMEOUT_S: float = _env_float("MCP_GATEWAY_RUNNER_DEFAULT_TIMEOUT_S", 55.0)
MAX_LOG_MB: int = _env_int("MCP_GATEWAY_RUNNER_MAX_LOG_MB", 256)


def _truncate_to_utf8_boundary(buf: bytes, n: int) -> bytes:
    """Return the largest prefix of buf with length <= n ending on a UTF-8 codepoint boundary.

    UTF-8 leading bytes: 0xxxxxxx (1-byte) or 11xxxxxx (multi-byte start).
    Continuation bytes: 10xxxxxx (b & 0xC0 == 0x80). UTF-8 codepoints are at most 4 bytes,
    so we walk back at most 4 steps.
    """
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


async def _drain(
    stream: asyncio.StreamReader,
    head_cap_bytes: int,
    file_sink,  # open BinaryIO in "ab" mode, buffering=0
    log_cap_bytes: int,
) -> tuple[bytes, int, bool, bool]:
    """Drain one pipe; accumulate head buffer + write raw bytes to file sink.

    Returns (head_bytes, total_bytes, head_truncated, log_truncated).
    Never stops reading the pipe (would deadlock the child); it drains-and-drops
    past either cap.
    """
    head = bytearray()
    total = 0
    head_truncated = False
    log_truncated = False
    log_written = 0
    CHUNK = 64 * 1024
    while True:
        chunk = await stream.read(CHUNK)
        if not chunk:
            break
        total += len(chunk)

        # File sink: raw bytes, capped at log_cap_bytes.
        if log_written < log_cap_bytes:
            remaining = log_cap_bytes - log_written
            to_write = chunk[:remaining]
            file_sink.write(to_write)
            log_written += len(to_write)
            if len(chunk) > remaining:
                log_truncated = True
        else:
            log_truncated = True

        # Head buffer: accumulate up to head_cap_bytes, then stop appending (but keep draining).
        if not head_truncated:
            remaining_head = head_cap_bytes - len(head)
            if remaining_head > 0:
                head.extend(chunk[:remaining_head])
                if len(chunk) > remaining_head:
                    head_truncated = True
            else:
                head_truncated = True

    return bytes(head), total, head_truncated, log_truncated


def _finalize_head(head_bytes: bytes, cap_bytes: int) -> str:
    """ANSI-strip on bytes, truncate to UTF-8 boundary, decode with errors='replace'.

    Pattern 2 ordering: ANSI strip first (regex operates on bytes), then boundary truncate,
    then decode. The decode is safe because we already cut at a UTF-8 codepoint boundary.
    """
    stripped = _ANSI_ESCAPE.sub(b"", head_bytes)
    truncated = _truncate_to_utf8_boundary(stripped, cap_bytes)
    return truncated.decode("utf-8", errors="replace")


class ReToolRunner:
    """Chokepoint subprocess primitive (D-01).

    Construct with per-call invariants; `await runner.run(argv)` returns the D-03 dict.
    Phase 8 sessions / Phase 9 jobs hold a runner across operations; Phase 7 one-shots
    use `run_tool` instead.
    """

    def __init__(
        self,
        *,
        case_dir,
        slug: str,
        timeout: Optional[float] = None,
        env: Optional[dict[str, str]] = None,
        stdout_head_kb: Optional[int] = None,
        stderr_head_kb: Optional[int] = None,
    ) -> None:
        # Fail fast on bad case_dir (RESEARCH Open Q1 recommendation): resolve(strict=True).
        # NOTE: This does NOT enforce STATUS_ROOT -- that's resolve_case_dir's job (D-14).
        try:
            self._case_dir = Path(case_dir).resolve(strict=True)
        except (FileNotFoundError, OSError) as exc:
            raise ValueError(f"case_dir does not exist: {case_dir!r}") from exc
        if not self._case_dir.is_dir():
            raise ValueError(f"case_dir is not a directory: {case_dir!r}")

        # Slug validation reuses the artifacts_io slug regex transparently --
        # tool_log_path() will raise ValueError if bad. We validate eagerly so
        # the failure surfaces in __init__, not on .run().
        # tool_log_path also returns the canonical lowercased slug indirectly;
        # we re-lowercase here for storage.
        _ = artifacts_io.tool_log_path(self._case_dir, slug)
        self._slug = slug.lower()

        self._timeout = timeout if timeout is not None else DEFAULT_TIMEOUT_S
        self._env = env  # If None, we pass os.environ.copy() at spawn time.
        self._stdout_head_bytes = (
            stdout_head_kb if stdout_head_kb is not None else STDOUT_HEAD_KB
        ) * 1024
        self._stderr_head_bytes = (
            stderr_head_kb if stderr_head_kb is not None else STDERR_HEAD_KB
        ) * 1024
        self._log_cap_bytes = MAX_LOG_MB * 1024 * 1024

    async def run(
        self,
        argv: list[str],
        *,
        proc_callback: Optional[Callable[["asyncio.subprocess.Process"], None]] = None,
    ) -> dict:
        if not argv:
            raise ValueError("argv must not be empty")

        # Ensure tool-logs/ subdir exists before opening the log file (D-09 caller contract).
        ensure_subdir(self._case_dir, "tool-logs")
        log_abs = tool_log_path(self._case_dir, self._slug)
        log_rel = log_abs.relative_to(self._case_dir)

        env = self._env if self._env is not None else os.environ.copy()

        t0 = time.monotonic()
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(self._case_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
            start_new_session=True,
        )

        # Q4 (Phase 9): notify caller of live Process so registry-owned
        # cancellation paths (Phase 9 D-07/D-23) can capture pid+pgid for
        # killpg. Fires exactly once, before drain starts. Exceptions propagate.
        if proc_callback is not None:
            proc_callback(proc)

        timed_out = False

        # Open the log sink synchronously, unbuffered (Pattern 6).
        with open(log_abs, "ab", buffering=0) as sink:
            try:
                drains = asyncio.gather(
                    _drain(proc.stdout, self._stdout_head_bytes, sink, self._log_cap_bytes),
                    _drain(proc.stderr, self._stderr_head_bytes, sink, self._log_cap_bytes),
                )
                # wait_for(gather(proc.wait, drains)) -- see Pattern 4 / Code Example sec.4.
                wait_results = await asyncio.wait_for(
                    asyncio.gather(proc.wait(), drains),
                    timeout=self._timeout,
                )
                # wait_results[0] = proc.returncode; wait_results[1] = (out_tuple, err_tuple)
                drain_out, drain_err = wait_results[1]
            except asyncio.TimeoutError:
                timed_out = True
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                # Pitfall 18: shielded wait ensures cleanup completes.
                await asyncio.shield(proc.wait())
                # We don't have drain results -- drains may have been cancelled mid-flight.
                # Construct empty/zero placeholders; the on-disk log captured what it could.
                drain_out = (b"", 0, False, False)
                drain_err = (b"", 0, False, False)
            except asyncio.CancelledError:
                try:
                    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                # Pitfall 18: shielded wait so the cancel cascade can't drop proc.wait().
                await asyncio.shield(proc.wait())
                raise

        duration_s = time.monotonic() - t0

        head_out, total_out, head_out_trunc, _log_out_trunc = drain_out
        head_err, total_err, head_err_trunc, _log_err_trunc = drain_err

        # D-04 + D-08: on timeout, exit_code is -9 (SIGKILL). Otherwise proc.returncode.
        exit_code = proc.returncode if proc.returncode is not None else -1
        if timed_out and exit_code != -9:
            # SIGKILL via killpg shows up as -9 in returncode after wait(); be defensive.
            exit_code = -9

        return {
            "exit_code": exit_code,
            "timed_out": timed_out,
            "duration_s": duration_s,
            "stdout_head": _finalize_head(head_out, self._stdout_head_bytes),
            "stdout_truncated": head_out_trunc,
            "stdout_bytes_total": total_out,
            "stderr_head": _finalize_head(head_err, self._stderr_head_bytes),
            "stderr_truncated": head_err_trunc,
            "stderr_bytes_total": total_err,
            "log_path": str(log_rel),  # D-10: relative to case_dir
            "argv": list(argv),
            "slug": self._slug,
        }


async def run_tool(
    case_dir,
    argv: list[str],
    *,
    slug: str,
    timeout: Optional[float] = None,
    env: Optional[dict[str, str]] = None,
    stdout_head_kb: Optional[int] = None,
    stderr_head_kb: Optional[int] = None,
) -> dict:
    """Module-level convenience for one-shot static-wrapper use (D-02).

    Constructs a fresh ReToolRunner and awaits run(argv). Phase 7 typed wrappers use
    this; Phases 8 sessions / 9 jobs hold a ReToolRunner instance directly.
    """
    runner = ReToolRunner(
        case_dir=case_dir,
        slug=slug,
        timeout=timeout,
        env=env,
        stdout_head_kb=stdout_head_kb,
        stderr_head_kb=stderr_head_kb,
    )
    return await runner.run(argv)
