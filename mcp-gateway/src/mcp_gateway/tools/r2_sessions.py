"""Session-scoped r2 MCP tools (Phase 8): open / r2_cmd / close / list.

Layered on top of the `mcp_gateway.sessions` primitive (Plan 02). This module
is the MCP surface; the primitive is `mcp_gateway.sessions.SessionRegistry`.

SESS-05 limitation (D-23): Sessions are shared across all MCP clients
connected with the same bearer token. Per-`Mcp-Session-Id` keying is
deferred to v1.2 (GW-V2-03). Rotate the bearer token to invalidate.

Result-dict shape (D-11): every r2_cmd return layers exactly on top of the
Phase 6 12-key base; 6 extension keys add session_id, session_invalidated,
format, parsed_json, parse_error, transcript_path.
"""
from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Literal, Optional

from mcp.server.fastmcp import FastMCP

# Import the sessions module itself (NOT names from it). Module-attribute
# access (`sessions.MAX_SESSIONS`) is required so `importlib.reload(sessions)`
# in Plan 05 tests propagates through. The `from X import Y` form binds Y
# to this module's namespace at import time -- reload(X) does NOT update Y.
# Phase 14 D-01: same applies to `sessions.SessionCapReached` -- the bare
# `from ... import SessionCapReached` binding survives load but escapes
# `except` after `importlib.reload(mcp_gateway.sessions._base)` swaps the
# class object. Catch via `sessions.SessionCapReached` to resolve at
# exception-catch time.
from mcp_gateway import session_state
from mcp_gateway import sessions
from mcp_gateway.artifacts_io import ensure_subdir, tool_log_path
from mcp_gateway.runner import STDOUT_HEAD_KB
from mcp_gateway.sessions import (
    check_dangerous_cmd,
    strip_ansi,
    truncate_for_response,
)
from mcp_gateway.tools.case_dirs import resolve_case_dir
from mcp_gateway.tools.samples import resolve_sample

log = logging.getLogger("mcp_gateway.tools.r2_sessions")


# ----------------------------------------------------------------------------
# SESS-05 disclaimer text (D-23). The FULL form is embedded in open_r2_session
# and r2_cmd docstrings; list_sessions and close_r2_session get the short form.
# Test test_sess05_disclaimer_in_docstrings asserts these phrases verbatim.
# ----------------------------------------------------------------------------
_SESS_05_DISCLAIMER_FULL = """
    Limitation (v1.1): Sessions are shared across all MCP clients connected
    with the same bearer token. A session_id returned by one client is
    accessible to every other client with the same token. Per-Mcp-Session-Id
    keying is deferred to v1.2 (GW-V2-03). Rotate the bearer token if a new
    client must not see existing sessions.
"""
_SESS_05_DISCLAIMER_SHORT = (
    "See `open_r2_session` for the cross-client-sharing limitation "
    "(sessions shared across same bearer-token clients; deferred to v1.2)."
)


def _ends_in_j(cmd: str) -> bool:
    """D-10: 'j' suffix detection. Accounts for trailing whitespace."""
    return cmd.rstrip().endswith("j")


def _require_registry() -> "sessions.SessionRegistry":
    reg = session_state.SESSION_REGISTRY
    if reg is None:
        raise RuntimeError(
            "session registry not initialized -- gateway lifespan not running"
        )
    return reg


def _fd_count(pid: int) -> int:
    """D-22 + Pitfall 5: read /proc/<pid>/fd; return -1 on failure (never throw)."""
    try:
        return len(os.listdir(f"/proc/{pid}/fd"))
    except OSError:
        return -1


async def _persist_artifacts(
    *,
    sess: "sessions.R2Session",
    cmd: str,
    stdout_full: str,
    fmt: str,
    invalidated: bool,
    duration_s: float,
) -> Path:
    """D-12 per-command log + D-13 transcript line write. Returns case-rel log path.

    Called under `asyncio.shield(...)` from r2_cmd so artifacts persist even
    on cancellation (Phase 6 D-04 / D-17 posture).
    """
    # D-12: per-command tool-log filename via the canonical Phase 6 D-09 shape.
    ensure_subdir(sess.case_dir, "tool-logs")
    log_path = tool_log_path(sess.case_dir, "r2_cmd")
    with open(log_path, "ab") as f:
        f.write(stdout_full.encode("utf-8", errors="replace"))

    # D-13: transcript line.
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    invalidated_marker = " [INVALIDATED]" if invalidated else ""
    stdout_bytes = len(stdout_full.encode("utf-8"))
    truncated = stdout_bytes > STDOUT_HEAD_KB * 1024
    block = (
        f">>> CMD {ts} {duration_s:.3f}s format={fmt}{invalidated_marker}\n"
        f"{cmd}\n"
        f"<<< OUTPUT bytes={stdout_bytes} truncated={str(truncated).lower()}\n"
        f"{stdout_full}\n"
        f"--- END ---\n"
    )
    try:
        with open(sess.transcript_path, "ab") as f:
            f.write(block.encode("utf-8", errors="replace"))
    except OSError:
        log.exception("[r2_sessions] failed to append transcript for %s", sess.session_id)
    return log_path.relative_to(sess.case_dir)


# ----------------------------------------------------------------------------
# D-19: open_r2_session
# ----------------------------------------------------------------------------
async def open_r2_session(
    case_dir: str,
    sample: str,
    *,
    init_commands: Optional[list[str]] = None,
    open_timeout: Optional[float] = None,
) -> dict:
    """Open a persistent r2 analysis session against `sample` in `case_dir`.

    Arguments:
        case_dir: case directory (validated via resolve_case_dir).
        sample: sample reference -- sha256 or case-dir-relative path.
        init_commands: optional list of r2 commands run AFTER the mandatory
            lockdown init (e scr.interactive=false; e scr.color=0;
            e scr.html=0; e cfg.user=mare). Validated for shell-escape BEFORE
            spawning r2 (Pitfall 4).
        open_timeout: combined timeout (seconds) for spawn + lockdown +
            init_commands. Defaults to MCP_GATEWAY_SESSION_OPEN_TIMEOUT_S (15s).
            Large samples with init_commands=['aaa'] typically need 60+.

    Returns: dict with session_id, transcript_path, opened_at, max_sessions,
    open_count, init_command_count, warnings. On cap-exceeded: returns the
    D-18 error dict instead: {error: 'session cap reached', max, open_count,
    existing: [...]}.

    {_FULL_DISCLAIMER}
    """
    registry = _require_registry()

    # Phase 7 resolvers return `str` (verified: case_dirs.py:10, samples.py:34).
    # Phase 8 must compute the sha256 explicitly from the resolved sample bytes.
    resolved_case = Path(resolve_case_dir(case_dir))
    sample_path = Path(resolve_sample(sample))
    sample_sha = hashlib.sha256(sample_path.read_bytes()).hexdigest()

    # D-19 step 3: validate init_commands BEFORE registry.open (Pitfall 4).
    # The registry also validates inside open(), but failing fast here gives a
    # cleaner error path (no half-acquired session-cap slot).
    for ic in (init_commands or []):
        check_dangerous_cmd(ic)

    # Module-attribute access so importlib.reload(sessions) propagates.
    # Phase 14 D-01: refetch the package module from sys.modules so that, after
    # `sys.modules.pop('mcp_gateway.sessions') + reimport` (which the gdb-env
    # validation test performs), the local `sessions` binding is updated to
    # the LIVE module rather than the stale, popped-but-still-referenced one.
    sessions = sys.modules["mcp_gateway.sessions"]
    timeout = open_timeout if open_timeout is not None else sessions.SESSION_OPEN_TIMEOUT_S

    try:
        sess = await registry.open(
            case_dir=resolved_case,
            sample_sha256=sample_sha,
            sample_path=sample_path,
            init_commands=init_commands,
            open_timeout_s=timeout,
        )
    except sessions.SessionCapReached as e:
        return e.to_dict()

    return {
        "session_id": sess.session_id,
        "case_dir": str(sess.case_dir),
        "sample_sha256": sess.sample_sha256,
        "sample_path": str(sess.sample_path),
        "transcript_path": str(sess.transcript_path.relative_to(sess.case_dir)),
        "opened_at": sess.opened_iso,
        "max_sessions": sessions.MAX_SESSIONS,
        "open_count": len(registry.list()),
        "init_command_count": len(init_commands or []),
        "warnings": [],
    }


# Splice the FULL disclaimer into open_r2_session.__doc__ post-definition.
# Python attaches the docstring only when the function body's first expression
# is a pure string literal; the trailing `""" + _SESS_05_DISCLAIMER_FULL` form
# is a string-concat expression (not a literal), which strips __doc__ to None.
# Post-definition splice via __doc__ assignment sidesteps the parser rule.
open_r2_session.__doc__ = (open_r2_session.__doc__ or "").replace(
    "{_FULL_DISCLAIMER}", _SESS_05_DISCLAIMER_FULL
)


# ----------------------------------------------------------------------------
# D-20: r2_cmd
# ----------------------------------------------------------------------------
async def r2_cmd(
    session_id: str,
    cmd: str,
    *,
    format: Literal["text", "json"] = "text",
    timeout: Optional[float] = None,
) -> dict:
    """Execute one r2 command in an open session and return the result.

    Arguments:
        session_id: opaque ID from open_r2_session.
        cmd: r2 command string. Dangerous shell-escape prefixes ('!', '#!',
            'R!', including in compound `;`/`|`/newline forms) are refused.
        format: 'text' (default; raw r2 output) or 'json' (appends 'j'
            suffix to cmd if not already present; parses output with
            json.loads, best-effort -- parsed_json=None + parse_error on fail).
        timeout: per-call wallclock cap (seconds). On timeout the SESSION IS
            KILLED (whole-session-kill -- Pitfall 6) and the result has
            session_invalidated=True, exit_code=-9, timed_out=True. Defaults
            to MCP_GATEWAY_R2_CMD_TIMEOUT_S (30s).

    Returns: 18-key result dict layered on the Phase 6 12-key shape (D-11):
        exit_code, timed_out, duration_s,
        stdout_head, stdout_truncated, stdout_bytes_total,
        stderr_head ('' -- sentinel framing reads stdout only),
        stderr_truncated (False), stderr_bytes_total (0),
        log_path, argv, slug,
        session_id, session_invalidated, format, parsed_json,
        parse_error, transcript_path.

    {_FULL_DISCLAIMER}
    """
    registry = _require_registry()
    try:
        sess = registry.get(session_id)
    except KeyError:
        raise ValueError(f"unknown session_id: {session_id}")

    check_dangerous_cmd(cmd)

    # Module-attribute access so importlib.reload(sessions) propagates.
    resolved_timeout = timeout if timeout is not None else sessions.R2_CMD_TIMEOUT_S
    started = time.monotonic()
    invalidated = False
    parse_error: Optional[str] = None
    parsed_json: object = None

    # D-10: append 'j' if format='json' and cmd doesn't already end in 'j'.
    sent_cmd = cmd + "j" if (format == "json" and not _ends_in_j(cmd)) else cmd

    async with sess.lock:
        raw_bytes, timed_out = await sess.exec_one(sent_cmd, timeout=resolved_timeout)

    if timed_out:
        await registry.close(session_id, reason="timeout")
        invalidated = True
        stdout_full_text = ""
        exit_code = -9
    else:
        stdout_full_text = strip_ansi(raw_bytes.decode("utf-8", errors="replace"))
        exit_code = 0
        sess.last_used_at = time.monotonic()
        sess.command_count += 1
        if format == "json":
            try:
                parsed_json = json.loads(stdout_full_text)
            except (json.JSONDecodeError, ValueError) as e:
                parse_error = str(e)

    # D-20 step c/d: persistence under asyncio.shield so cancellation does NOT
    # lose the per-command log + transcript line.
    log_path_rel = await asyncio.shield(_persist_artifacts(
        sess=sess,
        cmd=sent_cmd,
        stdout_full=stdout_full_text,
        fmt=format,
        invalidated=invalidated,
        duration_s=time.monotonic() - started,
    ))

    stdout_bytes_total = len(stdout_full_text.encode("utf-8"))
    stdout_head = truncate_for_response(stdout_full_text, STDOUT_HEAD_KB)
    cmd_argv_preview = sent_cmd[:120]
    duration_s = time.monotonic() - started

    return {
        # Phase 6 D-03 12-key base:
        "exit_code": exit_code,
        "timed_out": timed_out,
        "duration_s": duration_s,
        "stdout_head": stdout_head,
        "stdout_truncated": stdout_bytes_total > STDOUT_HEAD_KB * 1024,
        "stdout_bytes_total": stdout_bytes_total,
        "stderr_head": "",            # D-11: always empty (sentinel reads stdout only)
        "stderr_truncated": False,
        "stderr_bytes_total": 0,
        "log_path": str(log_path_rel),
        "argv": ["r2-session-cmd", session_id[:8], cmd_argv_preview],
        "slug": "r2_cmd",
        # D-11 6 extensions:
        "session_id": session_id,
        "session_invalidated": invalidated,
        "format": format,
        "parsed_json": parsed_json,
        "parse_error": parse_error,
        "transcript_path": str(sess.transcript_path.relative_to(sess.case_dir)),
    }


# Splice the FULL disclaimer into r2_cmd.__doc__ post-definition (same parser
# rule as open_r2_session above).
r2_cmd.__doc__ = (r2_cmd.__doc__ or "").replace(
    "{_FULL_DISCLAIMER}", _SESS_05_DISCLAIMER_FULL
)


# ----------------------------------------------------------------------------
# D-21: close_r2_session
# ----------------------------------------------------------------------------
async def close_r2_session(session_id: str) -> dict:
    """Close an open r2 session. Idempotent -- returns already_closed=True on second call.

    {_SHORT_DISCLAIMER}
    """
    registry = _require_registry()
    return await registry.close(session_id, reason="user")


# Splice the short disclaimer into close_r2_session.__doc__ post-definition
# (avoid f-string complications inside docstring).
close_r2_session.__doc__ = (close_r2_session.__doc__ or "").replace(
    "{_SHORT_DISCLAIMER}", _SESS_05_DISCLAIMER_SHORT
)


# ----------------------------------------------------------------------------
# D-22: list_sessions
# ----------------------------------------------------------------------------
async def list_sessions() -> dict:
    """Enumerate currently-open r2 sessions with fd_count + idle_s + command_count.

    {_SHORT_DISCLAIMER}
    """
    registry = _require_registry()
    now = time.monotonic()
    out_sessions = []
    for entry in registry.list():
        # registry.list() returns the base shape; this tool adds fd_count +
        # last_used_at (ISO8601) + transcript_path. Look up the live R2Session
        # for the fields the base list() doesn't carry.
        try:
            sess = registry.get(entry["session_id"])
        except KeyError:
            continue  # raced with close -- skip
        last_used_iso = datetime.datetime.fromtimestamp(
            time.time() - (now - sess.last_used_at),
            tz=datetime.timezone.utc,
        ).isoformat(timespec="seconds")
        out_sessions.append({
            "session_id": sess.session_id,
            "case_dir": str(sess.case_dir),
            "sample_sha256": sess.sample_sha256,
            "opened_at": sess.opened_iso,
            "last_used_at": last_used_iso,
            "idle_s": now - sess.last_used_at,
            "command_count": sess.command_count,
            "fd_count": _fd_count(sess.proc.pid),
            "pid": sess.proc.pid,
            "transcript_path": str(sess.transcript_path.relative_to(sess.case_dir)),
        })
    return {
        "max_sessions": sessions.MAX_SESSIONS,
        "open_count": len(out_sessions),
        "sessions": out_sessions,
    }


list_sessions.__doc__ = (list_sessions.__doc__ or "").replace(
    "{_SHORT_DISCLAIMER}", _SESS_05_DISCLAIMER_SHORT
)


# ----------------------------------------------------------------------------
# Phase 13 D-10/D-11/D-12: env-gated unsafe-r2 tool.
# Registered iff MCP_GATEWAY_R2_UNSAFE_ALLOWED=1 at gateway startup.
# Spawns r2 WITHOUT cfg.sandbox=true (Plan 03 sandbox=False driver kwarg).
# WARN-level log on every open (D-11) for audit-trail visibility.
# ----------------------------------------------------------------------------
async def open_r2_session_unsafe(
    case_dir: str,
    sample: str,
    *,
    init_commands: Optional[list[str]] = None,
    open_timeout: Optional[float] = None,
) -> dict:
    """Open an UNSANDBOXED r2 analysis session (use only when writes/plugins are required).

    UNSAFE: r2's cfg.sandbox is DISABLED for this session. r2 commands can
    run !shell escapes, open arbitrary files (including outside case_dir),
    exec external processes, and write project files. Use the sandboxed
    `open_r2_session` for triage and analysis; only reach for this tool
    when you genuinely need r2 to write project files, load plugins, or
    run external scripts.

    Registered iff `MCP_GATEWAY_R2_UNSAFE_ALLOWED=1` at gateway startup.
    Every open is logged at WARNING level.

    Arguments mirror `open_r2_session`:
        case_dir: case directory (validated via resolve_case_dir).
        sample: sample reference -- sha256 or case-dir-relative path.
        init_commands: optional list of r2 commands run AFTER the lockdown
            init batch. The gateway's `_DANGEROUS_R2_CMD_RE` UX-layer regex
            still applies (rejects '!' / 'R!' / '#!' prefixes) but the r2
            sandbox is OFF inside the session, so other escape paths are
            NOT blocked.
        open_timeout: combined timeout (seconds) for spawn + lockdown +
            init_commands. Defaults to MCP_GATEWAY_SESSION_OPEN_TIMEOUT_S.

    Returns: dict with session_id, transcript_path, opened_at, max_sessions,
    open_count, init_command_count, sample_sha256, sample_path, case_dir,
    warnings=['r2 sandbox is DISABLED for this session']. On cap-exceeded:
    returns the SessionCapReached error dict (shared cap with safe sessions).

    Cap sharing (Q6): unsafe sessions share the SAME combined SessionRegistry
    cap (MCP_GATEWAY_MAX_SESSIONS=8 by default) as safe r2 sessions + gdb
    sessions. Closing any session frees one cap slot.

    {_FULL_DISCLAIMER}
    """
    registry = _require_registry()
    resolved_case = Path(resolve_case_dir(case_dir))
    sample_path = Path(resolve_sample(sample))
    sample_sha = hashlib.sha256(sample_path.read_bytes()).hexdigest()

    # D-09 frozen regex still runs as the UX layer (defense in depth on the
    # UNSAFE path -- the regex blocks the obvious '!' shell-escape commands
    # even though cfg.sandbox is off inside the session).
    for ic in (init_commands or []):
        check_dangerous_cmd(ic)

    # Phase 14 D-01: same refetch trick as open_r2_session above.
    sessions = sys.modules["mcp_gateway.sessions"]
    timeout = open_timeout if open_timeout is not None else sessions.SESSION_OPEN_TIMEOUT_S

    try:
        sess = await registry.open(
            case_dir=resolved_case,
            sample_sha256=sample_sha,
            sample_path=sample_path,
            init_commands=init_commands,
            open_timeout_s=timeout,
            sandbox=False,
        )
    except sessions.SessionCapReached as e:
        return e.to_dict()

    # D-11: WARN-level audit log line. Fields: session_id, sample_sha256[:8],
    # case_dir. Uses logger.warning (Pitfall 9: log.warn is deprecated).
    log.warning(
        "[r2_sessions] unsafe session opened: session_id=%s sample_sha256=%s case_dir=%s",
        sess.session_id, sess.sample_sha256[:8], str(sess.case_dir),
    )

    return {
        "session_id": sess.session_id,
        "case_dir": str(sess.case_dir),
        "sample_sha256": sess.sample_sha256,
        "sample_path": str(sess.sample_path),
        "transcript_path": str(sess.transcript_path.relative_to(sess.case_dir)),
        "opened_at": sess.opened_iso,
        "max_sessions": sessions.MAX_SESSIONS,
        "open_count": len(registry.list()),
        "init_command_count": len(init_commands or []),
        "warnings": ["r2 sandbox is DISABLED for this session"],
    }


# Splice the FULL disclaimer into open_r2_session_unsafe.__doc__ post-definition
# (matches the open_r2_session pattern at line 205-207).
open_r2_session_unsafe.__doc__ = (open_r2_session_unsafe.__doc__ or "").replace(
    "{_FULL_DISCLAIMER}", _SESS_05_DISCLAIMER_FULL
)


def register_unsafe(mcp: FastMCP) -> None:
    """Register the env-gated unsafe-r2 tool. Called iff MCP_GATEWAY_R2_UNSAFE_ALLOWED=1."""
    mcp.tool()(open_r2_session_unsafe)


# ----------------------------------------------------------------------------
# Phase 7 register-wrapper pattern (verified in tools/shell.py).
# ----------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register the four r2-session tools on the FastMCP instance."""
    mcp.tool()(open_r2_session)
    mcp.tool()(r2_cmd)
    mcp.tool()(close_r2_session)
    mcp.tool()(list_sessions)
