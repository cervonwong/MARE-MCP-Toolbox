"""Kind-agnostic session primitives shared by r2 and gdb drivers (Phase 11 D-01..D-03).

This module is the LEAF of the sessions/ package (per D-DYN-IMPORT-01): it
imports only from stdlib + `mcp_gateway.artifacts_io`. Driver modules
(`sessions.r2`, future `sessions.gdb`) import FROM `_base`, never the other
way around.

Public surface (re-exported by `sessions/__init__.py`):
- `BaseSession` dataclass: kind-agnostic per-session state (D-02).
- `SessionRegistry`: kind-aware async-context-managed registry. `open()`
  dispatches to `r2._open_r2` or `gdb._open_gdb` based on the `kind` kwarg
  (default `"r2"` for backward compat with Phase 8 callers).
- `SessionCapReached`: cap-reject signal exception (Phase 8 D-18).
- Env-var module constants: `SESSION_IDLE_S`, `MAX_SESSIONS`, `R2_CMD_TIMEOUT_S`,
  `REAPER_INTERVAL_S`, `SESSION_OPEN_TIMEOUT_S` (Phase 8 D-14).
- ANSI / UTF-8 helpers: `strip_ansi`, `truncate_for_response`, `_ANSI_ESCAPE_TEXT`.
- Sentinel factory: `make_sentinel()` -- factored out of inline
  `secrets.token_hex(4)` so Plan 03's gdb driver reuses identical semantics.
- Env coercers: `_env_int`, `_env_float` (RuntimeError on bad values).

Design contract is verbatim Phase 8 (no behavior change) except for two
minimal additions: (a) `BaseSession` dataclass + `R2Session subclass` so
gdb sessions can store kind-agnostic state symmetrically; (b)
`SessionRegistry.open` gains a `kind: Literal["r2","gdb"]` kwarg with default
`"r2"` so Phase 8/9/10 callers continue working unchanged.
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
from typing import Literal, Optional

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
# ANSI-strip + UTF-8-safe truncation (verbatim copy from Phase 8 sessions.py:107-125).
# Inline local copies keep this module importable without circular-import worry
# from runner.py (Phase 8 Claude's-Discretion decision preserved).
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


def make_sentinel() -> str:
    """Per-session randomized sentinel factory.

    Factored from Phase 8 D-04 inline `secrets.token_hex(4)` so Plan 03's gdb
    driver reuses identical generator semantics. Returns `__MARE_END_<8hex>__`.
    """
    return f"__MARE_END_{secrets.token_hex(4)}__"


# ----------------------------------------------------------------------------
# D-02 (Phase 11): BaseSession dataclass -- kind-agnostic per-session fields ONLY.
# `R2Session` and the future `GdbSession` subclass this with their own
# kind-specific fields (sample_sha256, sample_path for r2; whatever gdb needs).
# ----------------------------------------------------------------------------
@dataclasses.dataclass
class BaseSession:
    session_id: str
    case_dir: Path
    pgid: int
    lock: asyncio.Lock
    sentinel: str
    transcript_path: Path
    opened_at: float
    opened_iso: str
    last_used_at: float
    proc: "asyncio.subprocess.Process"
    command_count: int = 0
    closed: bool = False
    close_reason: Optional[str] = None
    kind: Literal["r2", "gdb"] = "r2"


# ----------------------------------------------------------------------------
# D-18 (Phase 8): cap-reject signal -- preserved verbatim.
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
# D-16, D-17 (Phase 8): SessionRegistry async-context-manager + reaper loop.
# Phase 11 D-02 change: kind-aware. `open()` accepts a `kind: Literal["r2","gdb"]`
# kwarg with default `"r2"` and dispatches to the kind-specific driver function
# (r2._open_r2 / gdb._open_gdb). The cap (D-02 combined cap of 8) applies across
# r2 + gdb sessions uniformly because the registry sees only BaseSession objects.
# ----------------------------------------------------------------------------
class SessionRegistry:
    """Async-context-managed registry of sessions (r2 + gdb); owns the reaper task.

    Lifespan contract (Phase 8 D-16):
    - __aenter__: start the reaper background task; return self.
    - __aexit__: cancel reaper; asyncio.gather(close(reason='shutdown')) over
      every open session; await reaper exit.

    Phase 11 D-02 update: `open(kind="r2"|"gdb")` dispatches to the kind-specific
    driver. The combined cap of 8 (default) applies across both kinds.
    """

    def __init__(self, *, max_sessions: int, idle_s: float, reaper_interval_s: float):
        self._max = max_sessions
        self._idle_s = idle_s
        self._reaper_interval_s = reaper_interval_s
        # NOTE: storage is now BaseSession-typed so the registry can hold any
        # session-kind. R2Session / GdbSession are both BaseSession subclasses.
        self._sessions: dict[str, BaseSession] = {}
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

    def get(self, session_id: str) -> BaseSession:
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
        kind: Literal["r2", "gdb"] = "r2",
    ) -> BaseSession:
        """Spawn a session of the requested kind (D-02: r2 or gdb).

        Default `kind="r2"` keeps Phase 8/9/10 callers (which never pass `kind`)
        working unchanged. Plan 03's gdb path is reached only when `kind="gdb"`
        and Plan 03 has landed `sessions/gdb.py`.
        """
        if kind == "r2":
            from .r2 import _open_r2
            return await _open_r2(
                self,
                case_dir=case_dir,
                sample_sha256=sample_sha256,
                sample_path=sample_path,
                init_commands=init_commands,
                open_timeout_s=open_timeout_s,
            )
        elif kind == "gdb":
            from .gdb import _open_gdb  # provided by Plan 03; ImportError until then
            return await _open_gdb(
                self,
                case_dir=case_dir,
                sample_sha256=sample_sha256,
                sample_path=sample_path,
                init_commands=init_commands,
                open_timeout_s=open_timeout_s,
            )
        else:
            raise ValueError(f"unknown session kind: {kind!r}")

    async def close(self, session_id: str, *, reason: str = "user") -> dict:
        """Idempotent close: killpg + shielded wait + transcript footer (Phase 8 D-21)."""
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
        # Phase 8 D-13: transcript-close footer line.
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

        Phase 11 addition: each entry includes a `"kind"` field so callers can
        distinguish r2 vs gdb sessions. r2-only callers ignore the extra key.
        """
        now = time.monotonic()
        out = []
        for sid, sess in self._sessions.items():
            if sess.closed:
                continue
            entry = {
                "session_id": sid,
                "case_dir": str(sess.case_dir),
                # `sample_sha256` is r2-specific; access via getattr for kind-agnostic
                # iteration (gdb session may not have it under that exact attr name).
                "sample_sha256": getattr(sess, "sample_sha256", ""),
                "opened_at": sess.opened_iso,
                "idle_s": now - sess.last_used_at,
                "command_count": sess.command_count,
                "pid": sess.proc.pid,
                "kind": sess.kind,
            }
            out.append(entry)
        return out

    async def _reaper_loop(self) -> None:
        """Phase 8 D-17: poll every reaper_interval_s, close any session idle longer than idle_s."""
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
