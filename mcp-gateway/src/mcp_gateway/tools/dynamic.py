"""Phase 11 dynamic-mode MCP tool surface (D-DYN-TOOL-01).

Seven `@mcp.tool()` handlers registered iff MCP_GATEWAY_DYNAMIC_TOOLS=1 (env-gated;
tools/__init__.py conditionally imports this module).

Layering:
  tools/dynamic.py (THIS FILE)          -- MCP boundary (FastMCP-aware)
    -> mcp_gateway.dynamic               -- primitive layer (probes, argv builders, JobToolSpecs)
    -> mcp_gateway.sessions (gdb.py)     -- session driver for gdb-MI3
    -> mcp_gateway.tools.jobs            -- start_tool_job (Phase 9 dispatch surface)
    -> mcp_gateway.session_state         -- SESSION_REGISTRY slot

Tools NEVER raise (Phase 6 D-04 + Phase 8 D-18 + Phase 9 D-15). Every internal
exception is caught and converted to a structured `{error, ...}` dict.

The D-DYN-TOOL-02 disclaimer is spliced into each tool's __doc__ via post-definition
`.__doc__ = ...` rewrite (matches Phase 8 r2_sessions D-23 pattern -- Python's parser
only attaches pure string literals to __doc__, so docstring-concat idioms yield None).
"""
from __future__ import annotations

import asyncio
import dataclasses
import datetime
import logging
import time
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from mcp_gateway import dynamic
from mcp_gateway import session_state
from mcp_gateway.sessions.gdb import (
    GDB_OPEN_TIMEOUT_S,
    GDB_CMD_TIMEOUT_S,
    validate_mi_command,
)
from mcp_gateway.tools import case_dirs, samples
from mcp_gateway.tools import jobs as tools_jobs

log = logging.getLogger("mcp_gateway.tools.dynamic")


# ----------------------------------------------------------------------------
# D-DYN-TOOL-02 disclaimer (verbatim). Spliced into each tool's __doc__ via
# post-definition `.__doc__ +=` rewrite. Three keyword markers are
# regression-tested in test_disclaimer_in_all_docstrings:
#   - "Dynamic mode tool"
#   - "MCP_GATEWAY_DYNAMIC_TOOLS=1"
#   - "unshare --net --ipc --uts"
# ----------------------------------------------------------------------------
_DYNAMIC_TOOL_DISCLAIMER = (
    "\n\n"
    "**Dynamic mode tool (env-gated, no-net by default).**\n\n"
    "This tool is registered only when MCP_GATEWAY_DYNAMIC_TOOLS=1 at gateway "
    "startup. Subprocess runs under per-call `unshare --net --ipc --uts` -- no "
    "network, no host IPC, no shared UTS. The sample IS executed; only run on "
    "samples you intend to detonate. Output captured under "
    "`case_dir/{dynamic,qemu}/`.\n\n"
    "Capability prerequisites (see `get_dynamic_capabilities()`):\n"
    "  - strace/ltrace/gdb: `ptrace_scope` must allow parent-child tracing "
    "(yama.ptrace_scope=0 or =1).\n"
    "  - qemu_user: the requested arch must be in `qemu_architectures`.\n\n"
    "Sessions and jobs are shared across all MCP clients with the same bearer "
    "token. Per-`Mcp-Session-Id` keying is deferred to v1.2."
)


# ----------------------------------------------------------------------------
# D-DYN-CAP-PROBE-02 helpers: structured cap-missing error dicts.
# Tools call these BEFORE sample resolution / JOBS dispatch so we never even
# attempt subprocess work when prereqs are missing.
# ----------------------------------------------------------------------------
def _check_capabilities_for_strace_ltrace_gdb() -> Optional[dict]:
    """Return a structured error dict if ptrace OR netns is unavailable; else None."""
    caps = dynamic.CAPABILITIES
    if caps is None:
        return {
            "error": "capabilities not probed yet",
            "hint": "gateway lifespan has not populated dynamic.CAPABILITIES; retry after startup",
        }
    missing = []
    if not caps.ptrace_traceme_works:
        missing.append("ptrace")
    if not caps.netns_feasible:
        missing.append("netns")
    if missing:
        return {
            "error": "dynamic capability unavailable",
            "missing": missing,
            "ptrace_scope": caps.ptrace_scope,
            "netns_feasible": caps.netns_feasible,
            "hint": (
                "host operator: set /proc/sys/kernel/yama/ptrace_scope=0 "
                "or run docker with --cap-add=SYS_PTRACE --security-opt seccomp=unconfined"
            ),
            "capabilities_snapshot": dataclasses.asdict(caps),
        }
    return None


def _check_capabilities_for_qemu_user(arch: str) -> Optional[dict]:
    caps = dynamic.CAPABILITIES
    if caps is None:
        return {
            "error": "capabilities not probed yet",
            "hint": "gateway lifespan has not populated dynamic.CAPABILITIES; retry after startup",
        }
    if not caps.netns_feasible:
        return {
            "error": "dynamic capability unavailable",
            "missing": ["netns"],
            "hint": "container needs --security-opt seccomp=unconfined",
            "capabilities_snapshot": dataclasses.asdict(caps),
        }
    available = set(caps.qemu_architectures) | {
        a.replace("qemu-", "").replace("-static", "")
        for a in caps.qemu_static_binaries
    }
    if arch not in available:
        return {
            "error": "qemu arch unavailable",
            "arch": arch,
            "available": sorted(caps.qemu_architectures),
            "hint": "binfmt_misc may need registering with the F flag on the host",
        }
    return None


def _err_sample_not_found(sha256: str, exc: Exception) -> dict:
    return {
        "error": "sample_not_found",
        "sha256": sha256,
        "searched": ["uploads/", "existing case_dir/"],
        "detail": str(exc),
    }


def _err_internal(exc: Exception) -> dict:
    log.exception("[tools/dynamic] internal error")
    return {"error": "internal error", "exception": type(exc).__name__, "detail": str(exc)}


# ----------------------------------------------------------------------------
# D-DYN-TOOL-01: the 7 module-level coroutines.
# Pattern: validate inputs -> check caps -> resolve sample -> dispatch.
# Disclaimer spliced AFTER each definition because Python's parser only
# attaches docstrings when the function body's first expression is a pure
# string literal (Phase 8 r2_sessions D-23 precedent).
# ----------------------------------------------------------------------------


async def run_strace(
    case_dir: str,
    sample_sha256: str,
    profile: str,
    extra_args: Optional[list[str]] = None,
    run_argv: Optional[list[str]] = None,
    timeout: Optional[float] = None,
) -> dict:
    """Run Linux strace on a sample under per-call netns isolation; dispatched via JOBS."""
    try:
        case_dir_resolved = str(case_dirs.resolve_case_dir(case_dir))
    except Exception as e:
        return {"error": "invalid case_dir", "case_dir": case_dir, "detail": str(e)}

    cap_err = _check_capabilities_for_strace_ltrace_gdb()
    if cap_err is not None:
        return cap_err

    try:
        samples.resolve_sample(sample_sha256)
    except FileNotFoundError as e:
        return _err_sample_not_found(sample_sha256, e)
    except Exception as e:
        return _err_internal(e)

    kwargs = {
        "sample":     sample_sha256,
        "profile":    profile,
        "extra_args": list(extra_args or []),
        "run_argv":   list(run_argv or []),
    }
    try:
        return await tools_jobs.start_tool_job(
            tool="strace", kwargs=kwargs, case_dir=case_dir_resolved, timeout=timeout,
        )
    except Exception as e:
        return _err_internal(e)
run_strace.__doc__ = (run_strace.__doc__ or "") + _DYNAMIC_TOOL_DISCLAIMER


async def run_ltrace(
    case_dir: str,
    sample_sha256: str,
    profile: str,
    extra_args: Optional[list[str]] = None,
    run_argv: Optional[list[str]] = None,
    timeout: Optional[float] = None,
) -> dict:
    """Run Linux ltrace on a sample under per-call netns isolation; dispatched via JOBS.

    NOTE: ltrace 0.7.3 is unmaintained -- prefer run_strace for modern binaries.
    """
    try:
        case_dir_resolved = str(case_dirs.resolve_case_dir(case_dir))
    except Exception as e:
        return {"error": "invalid case_dir", "case_dir": case_dir, "detail": str(e)}

    cap_err = _check_capabilities_for_strace_ltrace_gdb()
    if cap_err is not None:
        return cap_err

    try:
        samples.resolve_sample(sample_sha256)
    except FileNotFoundError as e:
        return _err_sample_not_found(sample_sha256, e)
    except Exception as e:
        return _err_internal(e)

    kwargs = {
        "sample": sample_sha256, "profile": profile,
        "extra_args": list(extra_args or []),
        "run_argv": list(run_argv or []),
    }
    try:
        return await tools_jobs.start_tool_job(
            tool="ltrace", kwargs=kwargs, case_dir=case_dir_resolved, timeout=timeout,
        )
    except Exception as e:
        return _err_internal(e)
run_ltrace.__doc__ = (run_ltrace.__doc__ or "") + _DYNAMIC_TOOL_DISCLAIMER


async def run_qemu_user(
    case_dir: str,
    sample_sha256: str,
    arch: str,
    profile: str,
    extra_args: Optional[list[str]] = None,
    run_argv: Optional[list[str]] = None,
    timeout: Optional[float] = None,
) -> dict:
    """Run qemu-<arch>-static cross-arch user-mode emulation under per-call netns."""
    try:
        case_dir_resolved = str(case_dirs.resolve_case_dir(case_dir))
    except Exception as e:
        return {"error": "invalid case_dir", "case_dir": case_dir, "detail": str(e)}

    cap_err = _check_capabilities_for_qemu_user(arch)
    if cap_err is not None:
        return cap_err

    try:
        samples.resolve_sample(sample_sha256)
    except FileNotFoundError as e:
        return _err_sample_not_found(sample_sha256, e)
    except Exception as e:
        return _err_internal(e)

    kwargs = {
        "sample": sample_sha256, "arch": arch, "profile": profile,
        "extra_args": list(extra_args or []),
        "run_argv": list(run_argv or []),
    }
    try:
        return await tools_jobs.start_tool_job(
            tool="qemu_user", kwargs=kwargs, case_dir=case_dir_resolved, timeout=timeout,
        )
    except Exception as e:
        return _err_internal(e)
run_qemu_user.__doc__ = (run_qemu_user.__doc__ or "") + _DYNAMIC_TOOL_DISCLAIMER


async def open_gdb_session(
    case_dir: str,
    sample_sha256: str,
    init_commands: Optional[list[str]] = None,
    follow_fork_mode: str = "parent",
    open_timeout: Optional[float] = None,
) -> dict:
    """Open an interactive gdb-MI3 session restricted to an MI prefix allowlist."""
    try:
        case_dir_resolved = case_dirs.resolve_case_dir(case_dir)
    except Exception as e:
        return {"error": "invalid case_dir", "case_dir": case_dir, "detail": str(e)}

    cap_err = _check_capabilities_for_strace_ltrace_gdb()
    if cap_err is not None:
        return cap_err

    if follow_fork_mode not in ("parent", "child"):
        return {
            "error": "invalid follow_fork_mode",
            "value": follow_fork_mode,
            "allowed": ["parent", "child"],
        }

    try:
        sample_path_str = samples.resolve_sample(sample_sha256)
    except FileNotFoundError as e:
        return _err_sample_not_found(sample_sha256, e)
    except Exception as e:
        return _err_internal(e)

    registry = session_state.SESSION_REGISTRY
    if registry is None:
        return {"error": "session registry not initialized", "hint": "gateway lifespan not entered"}

    timeout_s = float(open_timeout) if open_timeout is not None else GDB_OPEN_TIMEOUT_S
    try:
        sess = await registry.open(
            kind="gdb",
            case_dir=Path(case_dir_resolved),
            sample_sha256=sample_sha256,
            sample_path=Path(sample_path_str),
            init_commands=init_commands,
            open_timeout_s=timeout_s,
        )
    except ValueError as e:
        return {"error": "gdb command refused", "reason": str(e)}
    except Exception as e:
        # SessionCapReached: surfaced as structured dict (Phase 8 D-18 pattern)
        try:
            from mcp_gateway.sessions import SessionCapReached
            if isinstance(e, SessionCapReached):
                return e.to_dict()
        except Exception:
            pass
        return _err_internal(e)

    # D-DYN-TOOL-03 return dict shape (13 keys).
    try:
        max_sessions = getattr(registry, "_max", -1)
        open_count = registry.count_open() if hasattr(registry, "count_open") else -1
        try:
            transcript_rel = str(sess.transcript_path.relative_to(sess.case_dir))
        except (ValueError, AttributeError):
            transcript_rel = str(getattr(sess, "transcript_path", ""))
        return {
            "session_id": sess.session_id,
            "kind": "gdb",
            "case_dir": str(sess.case_dir),
            "sample_sha256": sess.sample_sha256,
            "sample_path": str(sess.sample_path),
            "transcript_path": transcript_rel,
            "opened_at": getattr(sess, "opened_iso", ""),
            "gdb_version": getattr(sess, "gdb_version", ""),
            "follow_fork_mode": getattr(sess, "follow_fork_mode", follow_fork_mode),
            "max_sessions": max_sessions,
            "open_count": open_count,
            "init_command_count": getattr(sess, "command_count", 0),
            "warnings": [],
        }
    except Exception as e:
        return _err_internal(e)
open_gdb_session.__doc__ = (open_gdb_session.__doc__ or "") + _DYNAMIC_TOOL_DISCLAIMER


async def gdb_exec(
    session_id: str,
    cmd: str,
    timeout: Optional[float] = None,
) -> dict:
    """Execute one gdb-MI3 command in an open session; allowlisted prefixes only."""
    registry = session_state.SESSION_REGISTRY
    if registry is None:
        return {"error": "session registry not initialized"}

    try:
        sess = registry.get(session_id)
    except KeyError:
        return {"error": "unknown session_id", "session_id": session_id}
    except Exception as e:
        return _err_internal(e)

    # Pre-send allowlist + deny-regex check (D-07).
    try:
        validate_mi_command(cmd)
    except ValueError as e:
        return {
            "error": "gdb command refused",
            "reason": str(e),
            "session_id": session_id,
        }
    except Exception as e:
        return _err_internal(e)

    timeout_s = float(timeout) if timeout is not None else GDB_CMD_TIMEOUT_S
    slug = "gdb_cmd"
    t0 = time.monotonic()
    try:
        async with sess.lock:
            raw, timed_out = await sess.exec_one(cmd, timeout=timeout_s)
            try:
                sess.command_count = (getattr(sess, "command_count", 0) or 0) + 1
                sess.last_used_at = time.monotonic()
            except Exception:
                pass
    except Exception as e:
        return _err_internal(e)
    duration = time.monotonic() - t0

    # Best-effort MI parse: locate the result-class line.
    mi_result_class = "unknown"
    mi_records: list[dict] = []
    parse_error: Optional[str] = None
    try:
        for line in raw.split(b"\n"):
            s = line.decode("utf-8", errors="replace").strip()
            if s.startswith("^done"):
                mi_result_class = "done"
                break
            if s.startswith("^error"):
                mi_result_class = "error"
                break
            if s.startswith("^running"):
                mi_result_class = "running"
                break
            if s.startswith("^connected"):
                mi_result_class = "connected"
                break
            if s.startswith("^exit"):
                mi_result_class = "exit"
                break
    except Exception as e:
        parse_error = f"{type(e).__name__}: {e}"

    # If we timed out, invalidate the session per D-09
    session_invalidated = False
    if timed_out:
        session_invalidated = True
        try:
            await registry.close(session_id, reason="cmd_timeout")
        except Exception:
            log.exception("[tools/dynamic] failed to close invalidated session %s", session_id)

    # Append transcript line (best effort)
    try:
        with open(sess.transcript_path, "ab") as f:
            ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            f.write(f"\n--- gdb_cmd {ts} ---\n".encode())
            f.write(cmd.encode("utf-8") + b"\n")
            f.write(raw)
            f.write(b"\n")
    except OSError:
        log.exception("[tools/dynamic] transcript append failed")
    except Exception:
        log.exception("[tools/dynamic] transcript append failed (non-OSError)")

    stdout_text = raw.decode("utf-8", errors="replace") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        from mcp_gateway.sessions import truncate_for_response
        stdout_head = truncate_for_response(stdout_text, 32)
    except Exception:
        stdout_head = stdout_text[: 32 * 1024]

    try:
        case_dir = sess.case_dir
        transcript_path_rel = str(sess.transcript_path.relative_to(case_dir))
    except (ValueError, AttributeError):
        transcript_path_rel = str(getattr(sess, "transcript_path", ""))

    stdout_bytes = len(stdout_text.encode("utf-8"))
    return {
        "exit_code": 0 if not timed_out else -9,
        "timed_out": timed_out,
        "duration_s": duration,
        "stdout_head": stdout_head,
        "stdout_truncated": stdout_bytes > 32 * 1024,
        "stdout_bytes_total": stdout_bytes,
        "stderr_head": "",
        "stderr_truncated": False,
        "stderr_bytes_total": 0,
        "log_path": transcript_path_rel,
        "argv": ["gdb-session-cmd", session_id[:8], cmd[:80]],
        "slug": slug,
        "session_id": session_id,
        "session_invalidated": session_invalidated,
        "transcript_path": transcript_path_rel,
        "mi_result_class": mi_result_class,
        "mi_records": mi_records,
        "parse_error": parse_error,
    }
gdb_exec.__doc__ = (gdb_exec.__doc__ or "") + _DYNAMIC_TOOL_DISCLAIMER


async def close_gdb_session(session_id: str) -> dict:
    """Close an open gdb session (idempotent)."""
    registry = session_state.SESSION_REGISTRY
    if registry is None:
        return {"error": "session registry not initialized"}
    try:
        return await registry.close(session_id, reason="user")
    except Exception as e:
        return _err_internal(e)
close_gdb_session.__doc__ = (close_gdb_session.__doc__ or "") + _DYNAMIC_TOOL_DISCLAIMER


_refresh_lock = asyncio.Lock()


async def get_dynamic_capabilities(refresh: bool = False) -> dict:
    """Return the dataclass.asdict view of the startup capability probe.

    When refresh=True, re-runs `probe_all()` under a module-level lock and updates
    `dynamic.CAPABILITIES` before returning.
    """
    if refresh:
        try:
            async with _refresh_lock:
                new_caps = dynamic.probe_all()
                dynamic.CAPABILITIES = new_caps
        except Exception as e:
            return _err_internal(e)

    caps = dynamic.CAPABILITIES
    if caps is None:
        return {
            "error": "capabilities not probed yet",
            "hint": "gateway lifespan has not populated dynamic.CAPABILITIES; retry after startup",
        }
    try:
        return dataclasses.asdict(caps)
    except Exception as e:
        return _err_internal(e)
get_dynamic_capabilities.__doc__ = (get_dynamic_capabilities.__doc__ or "") + _DYNAMIC_TOOL_DISCLAIMER


# ----------------------------------------------------------------------------
# Register seam (Phase 10 D-20 pattern: mcp.tool()(fn) NOT @decorator at definition).
# ----------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register the 7 dynamic-mode MCP tools on the given FastMCP instance.

    Called by tools/__init__.py::register_all_tools ONLY when
    MCP_GATEWAY_DYNAMIC_TOOLS=1 (env-gate per D-DYN-IMPORT-01).
    """
    mcp.tool()(run_strace)
    mcp.tool()(run_ltrace)
    mcp.tool()(run_qemu_user)
    mcp.tool()(open_gdb_session)
    mcp.tool()(gdb_exec)
    mcp.tool()(close_gdb_session)
    mcp.tool()(get_dynamic_capabilities)
