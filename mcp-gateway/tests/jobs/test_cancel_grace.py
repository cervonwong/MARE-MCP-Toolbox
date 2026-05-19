"""Test D-07 SIGTERM-grace-SIGKILL ladder + JOBS-03 idempotent cancel."""
from __future__ import annotations

import asyncio
import os

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.tools import jobs as tjobs


@pytest.fixture
async def attached_registry(registry_factory):
    """Short cancel grace for fast tests."""
    async with registry_factory(cancel_grace_s=0.5) as reg:
        prev = session_state.JOB_REGISTRY
        session_state.JOB_REGISTRY = reg
        try:
            yield reg
        finally:
            session_state.JOB_REGISTRY = prev


async def _wait_until_running(job, timeout: float = 2.0) -> int:
    """Wait until the subprocess has spawned and is running; return captured pid."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if job.proc is not None and job.pgid is not None and job.status == "running":
            return job.proc.pid
        await asyncio.sleep(0.01)
    raise AssertionError(f"job did not reach running within {timeout}s; status={job.status}")


@pytest.mark.asyncio
async def test_cancel_running_long_job(case_dir_fixture, attached_registry):
    """SIGTERM-grace-SIGKILL ladder reaps a long-running sleep."""
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    job = await attached_registry.submit(
        spec=spec, kwargs={"seconds": 30},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=60.0,
    )
    captured_pid = await _wait_until_running(job)

    snap = await tjobs.cancel_tool_job(job.job_id)
    assert snap.get("status") == "cancelled"
    assert snap.get("previously_terminal") is False

    # PID is reaped (kernel returned ProcessLookupError to os.kill).
    with pytest.raises(ProcessLookupError):
        os.kill(captured_pid, 0)


@pytest.mark.asyncio
async def test_cancel_is_idempotent(case_dir_fixture, attached_registry):
    """JOBS-03 idempotent: second cancel returns previously_terminal=True."""
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    job = await attached_registry.submit(
        spec=spec, kwargs={"seconds": 30},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=60.0,
    )
    await _wait_until_running(job)

    snap1 = await tjobs.cancel_tool_job(job.job_id)
    assert snap1.get("previously_terminal") is False
    status_after_first = snap1["status"]

    snap2 = await tjobs.cancel_tool_job(job.job_id)
    assert snap2.get("previously_terminal") is True
    # Status unchanged across the second call.
    assert snap2["status"] == status_after_first
