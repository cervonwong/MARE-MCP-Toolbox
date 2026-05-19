"""Test list_tool_jobs D-20 result + Q5 `_specs` magic with include_internal."""
from __future__ import annotations

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.tools import jobs as tjobs


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
async def test_specs_default_hides_underscore(attached_registry):
    """Q5: state='_specs' default hides underscore-prefixed names."""
    result = await tjobs.list_tool_jobs(state="_specs")
    assert "specs" in result
    assert "count" in result
    assert "include_internal" in result
    assert result["include_internal"] is False
    names = [s["name"] for s in result["specs"]]
    assert names == ["capa"]


@pytest.mark.asyncio
async def test_specs_with_include_internal_shows_all(attached_registry):
    """Q5: include_internal=True surfaces underscore-prefixed names."""
    result = await tjobs.list_tool_jobs(state="_specs", include_internal=True)
    names = sorted(s["name"] for s in result["specs"])
    assert names == ["_log_burst_probe", "_sleep_probe", "capa"]


@pytest.mark.asyncio
async def test_spec_dict_keys(attached_registry):
    """Each spec dict has required descriptive keys."""
    result = await tjobs.list_tool_jobs(state="_specs", include_internal=True)
    required = {"name", "slug", "description", "default_timeout_s",
                "kwargs_schema", "has_progress_parser"}
    for spec in result["specs"]:
        assert required.issubset(spec.keys())


@pytest.mark.asyncio
async def test_normal_listing_shape(attached_registry):
    """D-20: state=None returns the 5-key listing dict."""
    result = await tjobs.list_tool_jobs(state=None)
    assert set(result.keys()) == {
        "jobs", "inflight_count", "completed_count", "completed_cap", "truncated",
    }


@pytest.mark.asyncio
async def test_filter_by_state_string(case_dir_fixture, attached_registry):
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    job = await attached_registry.submit(
        spec=spec, kwargs={"seconds": 0},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=5.0,
    )
    await job._drive_task

    # All jobs are now terminal; "running" filter yields empty list
    result = await tjobs.list_tool_jobs(state="running")
    assert result["jobs"] == []

    # "succeeded" returns the one we just ran
    result = await tjobs.list_tool_jobs(state="succeeded")
    assert any(j["job_id"] == job.job_id for j in result["jobs"])


@pytest.mark.asyncio
async def test_filter_by_state_list(case_dir_fixture, attached_registry):
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    job = await attached_registry.submit(
        spec=spec, kwargs={"seconds": 0},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=5.0,
    )
    await job._drive_task
    result = await tjobs.list_tool_jobs(state=["running", "succeeded"])
    assert any(j["job_id"] == job.job_id for j in result["jobs"])
