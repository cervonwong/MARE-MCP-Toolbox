"""Phase 9 MCP surface: four background-job tools (start / get / cancel / list).

Layered on top of the `mcp_gateway.jobs` primitive (Plan 01). This module is the
MCP surface; the primitive is `mcp_gateway.jobs.BackgroundJobRegistry`.

D-26 limitation (verbatim in every tool docstring): the registry is in-memory
only -- gateway restart cancels in-flight jobs and forgets terminal jobs. On-disk
logs and JSON result snapshots under tool-logs/ are preserved across restart.
Jobs are shared across all bearer-token clients (no per-Mcp-Session-Id keying;
deferred to v1.2 GW-V2-03).

Result-dict shape (D-19): every snapshot is the 25-key dict layered on Phase 6's
12-key base with 13 Phase 9 extensions. Errors return one of the four D-15 dict
shapes; tools NEVER raise out of the MCP boundary.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Union

from mcp.server.fastmcp import FastMCP

# Module-attribute access (NOT `from X import Y`) so importlib.reload(jobs) propagates
# through tests -- same convention as tools/r2_sessions.py.
from mcp_gateway import jobs
from mcp_gateway import session_state
from mcp_gateway.jobs import (
    BackgroundJobRegistry,
    InvalidKwargs,
    JobCapReached,
    JobNotFound,
    UnknownJobTool,
)
from mcp_gateway.tools.case_dirs import resolve_case_dir

log = logging.getLogger("mcp_gateway.tools.jobs")


# ----------------------------------------------------------------------------
# D-26 disclaimer text. Spliced into every tool __doc__ via .replace() because
# Python's parser only attaches docstrings when the function body's first
# expression is a pure string literal (see tools/r2_sessions.py for the same
# pattern with SESS-05).
# ----------------------------------------------------------------------------
_JOBS_DISCLAIMER = """
    In-memory registry -- gateway restart cancels in-flight jobs and forgets
    terminal jobs. On-disk logs and JSON result snapshots under tool-logs/ are
    preserved across restart.

    Jobs are shared across all bearer-token clients (no per-Mcp-Session-Id
    keying). Any client with the bearer token can see and cancel any job.
    (Per-session keying deferred to v1.2.)
"""


# ----------------------------------------------------------------------------
# Registry require helper (mirrors tools/r2_sessions.py::_require_registry).
# ----------------------------------------------------------------------------
def _require_registry() -> BackgroundJobRegistry:
    reg = session_state.JOB_REGISTRY
    if reg is None:
        raise RuntimeError(
            "job registry not initialized -- gateway lifespan not running"
        )
    return reg


# ----------------------------------------------------------------------------
# D-12 effective-timeout resolver.
# ----------------------------------------------------------------------------
def _resolve_effective_timeout(
    spec: "jobs.JobToolSpec", caller_timeout: Optional[float]
) -> float:
    """D-12: min(caller_or_spec_or_default, JOB_MAX_TIMEOUT_S). Negative/zero raises ValueError.

    Module-attribute access (jobs.JOB_TIMEOUT_S, jobs.JOB_MAX_TIMEOUT_S) so
    importlib.reload(jobs) in tests propagates correctly.
    """
    chosen: float
    if caller_timeout is not None:
        if not isinstance(caller_timeout, (int, float)) or isinstance(caller_timeout, bool):
            raise ValueError("timeout must be a number")
        if caller_timeout <= 0:
            raise ValueError("timeout must be > 0")
        chosen = float(caller_timeout)
    else:
        chosen = spec.default_timeout_s if spec.default_timeout_s else jobs.JOB_TIMEOUT_S
    # Defense-in-depth ceiling (T-09-04)
    return min(chosen, jobs.JOB_MAX_TIMEOUT_S)


# ----------------------------------------------------------------------------
# D-05: start_tool_job
# ----------------------------------------------------------------------------
async def start_tool_job(
    tool: str,
    kwargs: dict,
    *,
    case_dir: str,
    timeout: Optional[float] = None,
    ctx: Optional[Any] = None,  # FastMCP Context injected when ctx kwarg declared
) -> dict:
    """Submit a long-running tool as a background job and return immediately.

    Arguments:
        tool: registered job-tool name (see list_tool_jobs(state='_specs')).
        kwargs: per-tool kwargs (validated against JobToolSpec.kwargs_schema).
        case_dir: case directory (validated via resolve_case_dir).
        timeout: per-call wallclock cap (seconds). Defaults to spec.default_timeout_s
            or MCP_GATEWAY_JOB_TIMEOUT_S (3600 s). Capped at MCP_GATEWAY_JOB_MAX_TIMEOUT_S
            (86400 s, T-09-04 ceiling).

    Returns: the D-19 25-key snapshot dict (status=='pending' or 'running').
    On error returns one of the four D-15 error dict shapes; the tool NEVER raises.

    Job survives the request that launched it -- client disconnect does NOT cancel.

    {_JOBS_DISCLAIMER}
    """
    registry = _require_registry()

    # Step 1: resolve tool name (D-15 #2 on miss)
    spec = jobs.JOB_TOOL_REGISTRY.get(tool)
    if spec is None:
        return UnknownJobTool(
            tool=tool,
            known=list(jobs.JOB_TOOL_REGISTRY.keys()),
        ).to_dict()

    # Step 2: validate kwargs against schema (D-15 #4 on miss; Q3 hand-rolled walker)
    try:
        jobs._validate_kwargs(spec, kwargs or {})
    except InvalidKwargs as e:
        return e.to_dict()

    # Step 3: resolve case_dir via STATUS_ROOT (D-15 invalid-kwargs shape on failure)
    try:
        case_dir_resolved = resolve_case_dir(case_dir)
    except (ValueError, TypeError) as e:
        return InvalidKwargs(
            field="case_dir",
            expected="valid case directory under STATUS_ROOT",
            got=str(e),
        ).to_dict()

    # Step 4: D-12 effective-timeout resolution
    try:
        effective_timeout = _resolve_effective_timeout(spec, timeout)
    except ValueError:
        return InvalidKwargs(
            field="timeout",
            expected="positive number",
            got=str(timeout),
        ).to_dict()

    # Steps 5/6/7: submit via registry (D-15 #1 on cap, D-15 #4 on build_argv failure)
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
        # D-15 #4: spec.build_argv() raised on caller-supplied kwargs (e.g., path
        # traversal in capa's sample, or non-existent sha256). Convert to the
        # invalid-kwargs error shape so tools NEVER raise out of the MCP boundary
        # (verification gap: 09-VERIFICATION.md truth #7 / CR-01 + CR-02).
        return InvalidKwargs(
            field="kwargs",
            expected="valid per-tool argv inputs",
            got=f"{type(e).__name__}: {e}",
        ).to_dict()

    return registry._build_snapshot(job)


start_tool_job.__doc__ = (start_tool_job.__doc__ or "").replace(
    "{_JOBS_DISCLAIMER}", _JOBS_DISCLAIMER
)


# ----------------------------------------------------------------------------
# JOBS-02: get_tool_job (with D-16 Tier-2 ctx.report_progress + session-id dedup)
# ----------------------------------------------------------------------------
async def get_tool_job(
    job_id: str,
    *,
    ctx: Optional[Any] = None,
) -> dict:
    """Return the current D-19 25-key snapshot of a job.

    When ctx is non-None and job.progress has changed since this session_id's
    last poll, calls ctx.report_progress(progress, total, message) BEFORE
    returning the snapshot (D-16 Tier-2 poll-side push). Dedup is keyed by
    ctx.session_id via job._last_reported_to.

    On unknown job_id: returns the D-15 #3 job-not-found error dict.

    {_JOBS_DISCLAIMER}
    """
    registry = _require_registry()
    try:
        job = registry.get(job_id)
    except JobNotFound as e:
        return e.to_dict()

    # D-16 Tier-2: report_progress when changed (dedup by ctx.session_id)
    if ctx is not None and job.progress is not None:
        sid = getattr(ctx, "session_id", None) or "_anon_"
        last = job._last_reported_to.get(sid)
        cur = (job.progress, job.progress_total)
        if last != cur:
            try:
                await ctx.report_progress(
                    job.progress,
                    job.progress_total if job.progress_total is not None else None,
                    job.progress_message,
                )
                job._last_reported_to[sid] = cur
            except Exception:
                log.exception("[tools.jobs] ctx.report_progress failed -- ignoring")

    return registry._build_snapshot(job)


get_tool_job.__doc__ = (get_tool_job.__doc__ or "").replace(
    "{_JOBS_DISCLAIMER}", _JOBS_DISCLAIMER
)


# ----------------------------------------------------------------------------
# JOBS-03: cancel_tool_job (D-07 idempotent SIGTERM-grace-SIGKILL ladder)
# ----------------------------------------------------------------------------
async def cancel_tool_job(job_id: str) -> dict:
    """Cancel an inflight job via SIGTERM-then-SIGKILL ladder.

    Idempotent on terminal jobs -- returns previously_terminal=True without re-signalling.
    Returns the D-19 25-key snapshot dict with `previously_terminal` added. On unknown
    job_id returns the D-15 #3 job-not-found error dict.

    {_JOBS_DISCLAIMER}
    """
    registry = _require_registry()
    try:
        job = registry.get(job_id)
    except JobNotFound as e:
        return e.to_dict()

    was_terminal = job.status in jobs._TERMINAL_STATUSES
    if not was_terminal:
        await registry.cancel(job, reason="user")
        # Yield to let the drive task's finally-block settle status to terminal.
        await asyncio.sleep(0)
    snapshot = registry._build_snapshot(job)
    snapshot["previously_terminal"] = was_terminal
    return snapshot


cancel_tool_job.__doc__ = (cancel_tool_job.__doc__ or "").replace(
    "{_JOBS_DISCLAIMER}", _JOBS_DISCLAIMER
)


# ----------------------------------------------------------------------------
# D-20: list_tool_jobs (with `_specs` magic-state + Q5 include_internal filter)
# ----------------------------------------------------------------------------
async def list_tool_jobs(
    state: Optional[Union[str, list[str]]] = None,
    *,
    limit: int = 50,
    include_internal: bool = False,
) -> dict:
    """Enumerate jobs, optionally filtered by status.

    Special value: state='_specs' returns the registered job-tool spec catalog
    (NOT a real status). Underscore-prefixed spec names (e.g., '_sleep_probe',
    '_log_burst_probe') are HIDDEN unless include_internal=True (Q5 default).

    Filter: state may be a single status string, a list of strings, or None
    (returns inflight + completed). Limit caps the returned jobs list (default 50,
    max 500); jobs are returned most-recent-first by started_at.

    {_JOBS_DISCLAIMER}
    """
    registry = _require_registry()

    # `_specs` magic-state per D-20 + Q5
    if state == "_specs":
        specs_list = []
        for name in sorted(jobs.JOB_TOOL_REGISTRY.keys()):
            if not include_internal and name.startswith("_"):
                continue
            spec = jobs.JOB_TOOL_REGISTRY[name]
            specs_list.append({
                "name": spec.name,
                "slug": spec.slug,
                "description": spec.description,
                "default_timeout_s": spec.default_timeout_s,
                "kwargs_schema": dict(spec.kwargs_schema) if spec.kwargs_schema else None,
                "has_progress_parser": spec.progress_parser is not None,
            })
        return {
            "specs": specs_list,
            "count": len(specs_list),
            "include_internal": include_internal,
        }

    # Normal listing: collect all, filter, sort, limit
    max_limit = 500
    if not isinstance(limit, int) or limit <= 0 or limit > max_limit:
        try:
            limit = min(max(1, int(limit)), max_limit)
        except (TypeError, ValueError):
            limit = 50

    wanted: Optional[set[str]] = None
    if state is not None:
        wanted = {state} if isinstance(state, str) else set(state)

    all_jobs = list(registry.list_inflight()) + list(registry.list_completed())
    if wanted is not None:
        all_jobs = [j for j in all_jobs if j.status in wanted]

    # Sort started_at DESC; None started_at (pending without started_at_iso) sort last
    all_jobs.sort(
        key=lambda j: (j.started_at_iso or "0000-00-00T00:00:00+00:00"),
        reverse=True,
    )

    truncated = len(all_jobs) > limit
    all_jobs = all_jobs[:limit]

    snapshots = [registry._build_snapshot(j) for j in all_jobs]

    return {
        "jobs": snapshots,
        "inflight_count": len(registry.list_inflight()),
        "completed_count": len(registry.list_completed()),
        "completed_cap": jobs.MAX_COMPLETED_JOBS,
        "truncated": truncated,
    }


list_tool_jobs.__doc__ = (list_tool_jobs.__doc__ or "").replace(
    "{_JOBS_DISCLAIMER}", _JOBS_DISCLAIMER
)


# ----------------------------------------------------------------------------
# Phase 7/8 register-wrapper pattern.
# ----------------------------------------------------------------------------
def register(mcp: FastMCP) -> None:
    """Register the four job-system tools on the FastMCP instance."""
    mcp.tool()(start_tool_job)
    mcp.tool()(get_tool_job)
    mcp.tool()(cancel_tool_job)
    mcp.tool()(list_tool_jobs)
