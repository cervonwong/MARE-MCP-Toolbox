"""Test get_tool_job D-19 snapshot shape + JOBS-02 + D-15 #3."""
from __future__ import annotations

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.tools import jobs as tjobs


D19_KEYS = {
    "exit_code", "timed_out", "duration_s",
    "stdout_head", "stdout_truncated", "stdout_bytes_total",
    "stderr_head", "stderr_truncated", "stderr_bytes_total",
    "log_path", "argv", "slug",
    "job_id", "tool", "status", "started_at", "ended_at",
    "stdout_tail", "stderr_tail",
    "progress", "progress_total", "progress_message",
    "kwargs", "case_dir", "effective_timeout_s",
}


@pytest.fixture
async def attached_registry(registry_factory):
    async with registry_factory() as reg:
        prev = session_state.JOB_REGISTRY
        session_state.JOB_REGISTRY = reg
        try:
            yield reg
        finally:
            session_state.JOB_REGISTRY = prev


@pytest.mark.asyncio
async def test_get_succeeded_job_returns_25_key_snapshot(case_dir_fixture, attached_registry):
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    job = await attached_registry.submit(
        spec=spec, kwargs={"seconds": 0},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=5.0,
    )
    await job._drive_task

    snap = await tjobs.get_tool_job(job.job_id)
    assert set(snap.keys()) == D19_KEYS
    assert snap["status"] == "succeeded"
    assert snap["exit_code"] == 0
    assert snap["ended_at"] is not None


@pytest.mark.asyncio
async def test_snapshot_field_types(case_dir_fixture, attached_registry):
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    job = await attached_registry.submit(
        spec=spec, kwargs={"seconds": 0},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=5.0,
    )
    await job._drive_task
    snap = await tjobs.get_tool_job(job.job_id)
    assert isinstance(snap["stdout_head"], str)
    assert isinstance(snap["stderr_head"], str)
    assert isinstance(snap["stdout_truncated"], bool)
    assert isinstance(snap["stderr_truncated"], bool)
    assert isinstance(snap["stdout_tail"], str)
    assert isinstance(snap["stderr_tail"], str)


@pytest.mark.asyncio
async def test_get_unknown_returns_job_not_found(attached_registry):
    """D-15 #3: unknown 16-hex job_id returns job-not-found dict."""
    result = await tjobs.get_tool_job("deadbeefdeadbeef")
    assert "job not found" in result.get("error", "")
    assert result["job_id"] == "deadbeefdeadbeef"
    assert "hint" in result
