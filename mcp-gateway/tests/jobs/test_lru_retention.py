"""Test D-10 FIFO eviction + log preservation invariant."""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.tools import jobs as tjobs


@pytest.fixture
async def attached_registry(registry_factory):
    async with registry_factory(max_completed=3) as reg:
        prev = session_state.JOB_REGISTRY
        session_state.JOB_REGISTRY = reg
        try:
            yield reg
        finally:
            session_state.JOB_REGISTRY = prev


@pytest.mark.asyncio
async def test_fifo_eviction_after_cap(case_dir_fixture, attached_registry):
    """Submit 4 quick jobs into max_completed=3; oldest evicted."""
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    submitted = []
    for _ in range(4):
        job = await attached_registry.submit(
            spec=spec, kwargs={"seconds": 0},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=5.0,
        )
        await job._drive_task
        submitted.append(job)

    completed_ids = {j.job_id for j in attached_registry.list_completed()}
    assert len(completed_ids) == 3
    # The first submitted is the evicted one.
    evicted = submitted[0]
    assert evicted.job_id not in completed_ids

    # Log preservation invariant: .txt and .json still on disk.
    txt_path = Path(evicted.log_path_abs)
    json_path = txt_path.with_suffix(".json")
    assert txt_path.exists(), "evicted job's .txt log was deleted"
    assert json_path.exists(), "evicted job's .json sibling was deleted"

    # get_tool_job on the evicted id returns D-15 #3
    result = await tjobs.get_tool_job(evicted.job_id)
    assert "job not found" in result.get("error", "")
    assert "tool-logs" in result.get("hint", "").lower() or "tool-logs" in result.get("hint", "")
