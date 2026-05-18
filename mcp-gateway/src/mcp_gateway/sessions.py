"""SessionRegistry: lifespan-owned r2-session machinery (Phase 8).

Public API (consumed by tools/r2_sessions.py and app.py::lifespan):
- `SessionRegistry` -- async-context-manager (D-16). __aenter__ starts the
  reaper task; __aexit__ cancels reaper + killpgs every open session.
- `R2Session` -- dataclass holding per-session state (D-15).
- `_DANGEROUS_R2_CMD_RE` -- module-level compiled regex (D-08).
- `check_dangerous_cmd(cmd)` -- raises ValueError with D-09 message on match.
- 5 module constants read once from env vars (D-14): SESSION_IDLE_S,
  MAX_SESSIONS, R2_CMD_TIMEOUT_S, REAPER_INTERVAL_S, SESSION_OPEN_TIMEOUT_S.

Design contract (locked):
- argv-only spawn via asyncio.create_subprocess_exec (D-02) -- never shell-invocation kwarg
- start_new_session=True for killpg cleanup (Phase 6 D-17)
- Per-session randomized sentinel via secrets.token_hex(4) (D-04)
- Lockdown init batch BEFORE user init_commands (D-03):
    e scr.interactive=false / e scr.color=0 / e scr.html=0 / e cfg.user=mare
- Dangerous-command check at the wrapper layer (D-08, D-09)
- Cap-reject (D-18): SessionCapReached carries the D-18 error dict shape
- Reaper loop (D-17): exception-isolated per iteration; CancelledError exits
- Shutdown: asyncio.gather(close(...)) over every open session, parallel kill

This module is the layer BELOW MCP. It does not import from mcp.server.fastmcp;
Plan 03 (tools/r2_sessions.py) is the MCP surface that imports from here.
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import os
import re
import secrets
import signal
import time
from pathlib import Path
from typing import Optional

from mcp_gateway.artifacts_io import confine_to, ensure_subdir

log = logging.getLogger("mcp_gateway.sessions")


# ----------------------------------------------------------------------------
# D-14: env-var module constants. Read once at import; raise RuntimeError on
# bad values (matches Phase 6 D-08 pattern). Pattern verified against runner.py.
# ----------------------------------------------------------------------------
def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, str(default))
    try:
        v = float(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be a float, got {raw!r}") from e
    if v < 0:
        raise RuntimeError(f"{name} must be >= 0, got {v}")
    return v


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        v = int(raw)
    except ValueError as e:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}") from e
    if v < 0:
        raise RuntimeError(f"{name} must be >= 0, got {v}")
    return v


SESSION_IDLE_S: float = _env_float("MCP_GATEWAY_SESSION_IDLE_S", 1800.0)
MAX_SESSIONS: int = _env_int("MCP_GATEWAY_MAX_SESSIONS", 8)
R2_CMD_TIMEOUT_S: float = _env_float("MCP_GATEWAY_R2_CMD_TIMEOUT_S", 30.0)
REAPER_INTERVAL_S: float = _env_float("MCP_GATEWAY_REAPER_INTERVAL_S", 60.0)
SESSION_OPEN_TIMEOUT_S: float = _env_float("MCP_GATEWAY_SESSION_OPEN_TIMEOUT_S", 15.0)


# ----------------------------------------------------------------------------
# D-08 / D-09: dangerous-command regex. Full-string scan, not literal-first-char.
# Anchored at start/`;`/`|`/newline; matches optional whitespace before the prefix.
# Per-command refusal raises ValueError with the D-09 message naming the prefix.
# ----------------------------------------------------------------------------
_DANGEROUS_R2_CMD_RE: re.Pattern[str] = re.compile(
    r"(?:^|;|\||\n)\s*(?:#!|R!|!)"
)


def check_dangerous_cmd(cmd: str) -> None:
    """Raise ValueError if `cmd` contains a refused shell-escape prefix (D-08, D-09).

    Refusal is per-command (one bad command does not invalidate the session).
    The error message names the rejected prefix specifically so operators see an
    actionable error.
    """
    if _DANGEROUS_R2_CMD_RE.search(cmd):
        raise ValueError(
            "dangerous r2 command refused: shell-escape prefix "
            "'!' / '#!' / 'R!' is blocked by the gateway wrapper"
        )


# ----------------------------------------------------------------------------
# ANSI-strip + UTF-8-safe truncation (reuse from runner.py if exported, else
# inline local copies -- Claude's Discretion). Phase 8 picks the inline-copy
# path to keep sessions.py importable without circular-import worry.
# ----------------------------------------------------------------------------
_ANSI_ESCAPE_TEXT = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def strip_ansi(text: str) -> str:
    """Strip CSI SGR escape sequences from `text`. Defense-in-depth over scr.color=0."""
    return _ANSI_ESCAPE_TEXT.sub("", text)


def truncate_for_response(text: str, head_kb: int) -> str:
    """UTF-8-safe head truncation. Drops trailing bytes if they would split a code point."""
    max_bytes = head_kb * 1024
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    cut = encoded[:max_bytes]
    # Walk back to a UTF-8 code-point boundary.
    while cut and (cut[-1] & 0xC0) == 0x80:
        cut = cut[:-1]
    return cut.decode("utf-8", errors="replace")


# ----------------------------------------------------------------------------
# D-15: R2Session dataclass.
# ----------------------------------------------------------------------------
@dataclasses.dataclass
class R2Session:
    session_id: str
    case_dir: Path
    sample_sha256: str
    sample_path: Path
    proc: asyncio.subprocess.Process
    pgid: int
    lock: asyncio.Lock
    sentinel: str
    transcript_path: Path
    opened_at: float
    opened_iso: str
    last_used_at: float
    command_count: int = 0
    closed: bool = False
    close_reason: Optional[str] = None

    async def exec_one(self, cmd: str, *, timeout: float) -> tuple[bytes, bool]:
        """Send one command + sentinel, read stdout until sentinel line.

        Returns (raw_bytes_before_sentinel, timed_out_bool).
        On timeout the caller must close() the session (D-20 step d).
        Does NOT acquire self.lock -- caller is responsible (Phase 8 D-20).
        """
        sentinel_line = (self.sentinel + "\n").encode()
        self.proc.stdin.write(cmd.encode("utf-8") + b"\n")
        self.proc.stdin.write(f"?e {self.sentinel}\n".encode())
        await self.proc.stdin.drain()
        buf = bytearray()
        try:
            while True:
                line = await asyncio.wait_for(
                    self.proc.stdout.readuntil(b"\n"),
                    timeout=timeout,
                )
                if line == sentinel_line:
                    return bytes(buf), False
                buf.extend(line)
        except asyncio.TimeoutError:
            return bytes(buf), True


# ----------------------------------------------------------------------------
# D-18: cap-reject signal.
# ----------------------------------------------------------------------------
class SessionCapReached(Exception):
    """Raised by SessionRegistry.open when the cap is hit. Carries error-dict payload."""

    def __init__(self, max_sessions: int, open_count: int, existing: list[dict]):
        self.max_sessions = max_sessions
        self.open_count = open_count
        self.existing = existing
        super().__init__(f"session cap reached: open={open_count} max={max_sessions}")

    def to_dict(self) -> dict:
        return {
            "error": "session cap reached",
            "max": self.max_sessions,
            "open_count": self.open_count,
            "existing": self.existing,
        }


# ----------------------------------------------------------------------------
# D-16, D-17: SessionRegistry async-context-manager + reaper loop.
# ----------------------------------------------------------------------------
class SessionRegistry:
    """Async-context-managed registry of R2Sessions; owns the reaper task.

    Lifespan contract (D-16):
    - __aenter__: start the reaper background task; return self.
    - __aexit__: cancel reaper; asyncio.gather(close(reason='shutdown')) over
      every open session; await reaper exit.
    """

    def __init__(self, *, max_sessions: int, idle_s: float, reaper_interval_s: float):
        self._max = max_sessions
        self._idle_s = idle_s
        self._reaper_interval_s = reaper_interval_s
        self._sessions: dict[str, R2Session] = {}
        self._lock = asyncio.Lock()
        self._reaper_task: Optional[asyncio.Task] = None

    async def __aenter__(self) -> "SessionRegistry":
        self._reaper_task = asyncio.create_task(
            self._reaper_loop(), name="r2-session-reaper"
        )
        log.info("[sessions] registry entered (max=%d idle_s=%s reaper_interval_s=%s)",
                 self._max, self._idle_s, self._reaper_interval_s)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        # Cancel the reaper first so it does not race the shutdown sweep.
        if self._reaper_task is not None:
            self._reaper_task.cancel()
            try:
                await self._reaper_task
            except (asyncio.CancelledError, Exception):
                pass
        # Parallel kill of every still-open session (Claude's Discretion
        # recommendation: bounded by slowest killpg, not their sum).
        open_ids = [sid for sid, s in self._sessions.items() if not s.closed]
        if open_ids:
            log.info("[sessions] shutting down: killing %d open session(s)", len(open_ids))
            await asyncio.gather(
                *[self.close(sid, reason="shutdown") for sid in open_ids],
                return_exceptions=True,
            )

    def count_open(self) -> int:
        return sum(1 for s in self._sessions.values() if not s.closed)

    def get(self, session_id: str) -> R2Session:
        sess = self._sessions.get(session_id)
        if sess is None or sess.closed:
            raise KeyError(f"unknown session_id: {session_id}")
        return sess

    async def open(
        self,
        *,
        case_dir: Path,
        sample_sha256: str,
        sample_path: Path,
        init_commands: Optional[list[str]],
        open_timeout_s: float,
    ) -> R2Session:
        """Spawn r2, run lockdown init (D-03), then user init_commands (D-19 step 4)."""
        # D-19 step 3: validate init_commands BEFORE spawn (Pitfall 4).
        for ic in (init_commands or []):
            check_dangerous_cmd(ic)

        # D-18: cap check under registry lock; insert under registry lock.
        async with self._lock:
            if self.count_open() >= self._max:
                raise SessionCapReached(self._max, self.count_open(), self.list())
            session_id = secrets.token_urlsafe(12)

        # D-13: lazy r2-sessions/ subdir + transcript path under confine_to.
        ensure_subdir(case_dir, "r2-sessions")
        transcript_path = confine_to(case_dir, f"r2-sessions/{session_id}-transcript.log")

        # D-04: per-session randomized sentinel.
        sentinel = f"__MARE_END_{secrets.token_hex(4)}__"

        # D-02: argv-only spawn with start_new_session=True for killpg cleanup.
        proc = await asyncio.create_subprocess_exec(
            "r2", "-2", "-q0", str(sample_path),
            cwd=str(case_dir),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        pgid = os.getpgid(proc.pid)

        # D-03: lockdown init batch + sentinel emitter. Send as a single batch.
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
            await asyncio.wait_for(
                proc.stdout.readuntil((sentinel + "\n").encode()),
                timeout=open_timeout_s,
            )
        except (asyncio.TimeoutError, Exception):
            try:
                os.killpg(pgid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            await asyncio.shield(proc.wait())
            raise RuntimeError(
                "r2 init failed: lockdown commands did not complete within timeout"
            )

        # D-13: transcript header.
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        with open(transcript_path, "ab") as f:
            f.write(
                f"=== MARE r2_session {session_id} opened {now_iso} "
                f"sample={sample_sha256[:8]} ===\n".encode()
            )

        now_mono = time.monotonic()
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
            opened_at=now_mono,
            opened_iso=now_iso,
            last_used_at=now_mono,
        )

        # D-19 step 4: run user init_commands inside the session lock (single-threaded r2).
        async with sess.lock:
            for ic in (init_commands or []):
                raw, timed_out = await sess.exec_one(ic, timeout=open_timeout_s)
                if timed_out:
                    try:
                        os.killpg(pgid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
                    await asyncio.shield(proc.wait())
                    raise RuntimeError(
                        f"r2 init_commands timed out on {ic!r} after {open_timeout_s}s"
                    )
                sess.command_count += 1
                sess.last_used_at = time.monotonic()

        # Register under lock.
        async with self._lock:
            self._sessions[session_id] = sess
        log.info("[sessions] opened %s (pid=%d sample=%s)", session_id, proc.pid, sample_sha256[:8])
        return sess

    async def close(self, session_id: str, *, reason: str = "user") -> dict:
        """Idempotent close: killpg + shielded wait + transcript footer (D-21)."""
        sess = self._sessions.get(session_id)
        if sess is None:
            return {
                "ok": True, "session_id": session_id, "already_closed": True,
                "transcript_path": "", "closed_at":
                    datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "command_count": 0, "duration_s": 0.0, "close_reason": reason,
            }
        if sess.closed:
            return {
                "ok": True, "session_id": session_id, "already_closed": True,
                "transcript_path": str(sess.transcript_path.relative_to(sess.case_dir)),
                "closed_at":
                    datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                "command_count": sess.command_count,
                "duration_s": time.monotonic() - sess.opened_at,
                "close_reason": sess.close_reason or reason,
            }
        # Mark closed under registry lock to block re-entry from get().
        async with self._lock:
            sess.closed = True
            sess.close_reason = reason

        try:
            os.killpg(sess.pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        try:
            await asyncio.shield(sess.proc.wait())
        except Exception:
            pass

        closed_iso = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        duration = time.monotonic() - sess.opened_at
        # D-13: transcript-close footer line.
        try:
            with open(sess.transcript_path, "ab") as f:
                f.write(
                    f"=== MARE r2_session {session_id} closed {closed_iso} "
                    f"reason={reason} ===\n".encode()
                )
        except OSError:
            log.exception("[sessions] failed to write transcript footer for %s", session_id)
        log.info("[sessions] closed %s (reason=%s duration=%.2fs)", session_id, reason, duration)
        return {
            "ok": True,
            "session_id": session_id,
            "already_closed": False,
            "transcript_path": str(sess.transcript_path.relative_to(sess.case_dir)),
            "closed_at": closed_iso,
            "command_count": sess.command_count,
            "duration_s": duration,
            "close_reason": reason,
        }

    def list(self) -> list[dict]:
        """Snapshot of open sessions for cap-reject error dict + list_sessions tool (D-22).

        Note: full list_sessions tool surface (with fd_count) lives in
        tools/r2_sessions.py (Plan 03). This helper is used internally
        (e.g., cap-reject `existing` field).
        """
        now = time.monotonic()
        out = []
        for sid, sess in self._sessions.items():
            if sess.closed:
                continue
            out.append({
                "session_id": sid,
                "case_dir": str(sess.case_dir),
                "sample_sha256": sess.sample_sha256,
                "opened_at": sess.opened_iso,
                "idle_s": now - sess.last_used_at,
                "command_count": sess.command_count,
                "pid": sess.proc.pid,
            })
        return out

    async def _reaper_loop(self) -> None:
        """D-17: poll every reaper_interval_s, close any session idle longer than idle_s."""
        while True:
            try:
                await asyncio.sleep(self._reaper_interval_s)
                now = time.monotonic()
                stale_ids = [
                    sid for sid, sess in list(self._sessions.items())
                    if not sess.closed and (now - sess.last_used_at) > self._idle_s
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
