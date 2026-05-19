"""Test start_tool_job D-05 signature + argument resolution order (SC-1)."""
from __future__ import annotations

import re

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.tools import jobs as tjobs


# Exact D-19 25-key set
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
    """Attach a registry to session_state.JOB_REGISTRY for the duration of a test."""
    async with registry_factory() as reg:
        prev = session_state.JOB_REGISTRY
        session_state.JOB_REGISTRY = reg
        try:
            yield reg
        finally:
            session_state.JOB_REGISTRY = prev


@pytest.mark.asyncio
async def test_sc1_submit_returns_25_key_snapshot(case_dir_fixture, attached_registry):
    """SC-1: start_tool_job returns the D-19 25-key snapshot with status in
    {pending, running, succeeded}."""
    result = await tjobs.start_tool_job(
        tool="_sleep_probe",
        kwargs={"seconds": 0},
        case_dir=str(case_dir_fixture),
    )
    assert "error" not in result, result
    assert set(result.keys()) == D19_KEYS
    assert result["status"] in {"pending", "running", "succeeded"}
    assert result["argv"] == ["sleep", "0"]
    assert result["slug"] == "sleep_probe"
    assert re.fullmatch(r"[0-9a-f]{16}", result["job_id"])


@pytest.mark.asyncio
async def test_caller_timeout_overrides_spec_default(case_dir_fixture, attached_registry):
    result = await tjobs.start_tool_job(
        tool="_sleep_probe",
        kwargs={"seconds": 0},
        case_dir=str(case_dir_fixture),
        timeout=5.0,
    )
    assert "error" not in result
    assert result["effective_timeout_s"] == 5.0


@pytest.mark.asyncio
async def test_timeout_zero_returns_invalid_kwargs(case_dir_fixture, attached_registry):
    result = await tjobs.start_tool_job(
        tool="_sleep_probe",
        kwargs={"seconds": 0},
        case_dir=str(case_dir_fixture),
        timeout=0,
    )
    assert result.get("error") == "invalid kwargs"
    assert result["field"] == "timeout"


@pytest.mark.asyncio
async def test_timeout_negative_returns_invalid_kwargs(case_dir_fixture, attached_registry):
    result = await tjobs.start_tool_job(
        tool="_sleep_probe",
        kwargs={"seconds": 0},
        case_dir=str(case_dir_fixture),
        timeout=-1,
    )
    assert result.get("error") == "invalid kwargs"
    assert result["field"] == "timeout"


@pytest.mark.asyncio
async def test_timeout_huge_capped_at_max(case_dir_fixture, attached_registry):
    """T-09-04 defense-in-depth: huge timeout capped at JOB_MAX_TIMEOUT_S."""
    huge = 10**20
    result = await tjobs.start_tool_job(
        tool="_sleep_probe",
        kwargs={"seconds": 0},
        case_dir=str(case_dir_fixture),
        timeout=huge,
    )
    assert "error" not in result
    assert result["effective_timeout_s"] == jobs.JOB_MAX_TIMEOUT_S


@pytest.mark.asyncio
async def test_unknown_tool_returns_d15_unknown(case_dir_fixture, attached_registry):
    result = await tjobs.start_tool_job(
        tool="totally_unknown_tool_xyz",
        kwargs={},
        case_dir=str(case_dir_fixture),
    )
    assert result.get("error") == "unknown job tool"
    assert result["tool"] == "totally_unknown_tool_xyz"
    assert isinstance(result["known"], list)


@pytest.mark.asyncio
async def test_invalid_case_dir_returns_invalid_kwargs(tmp_path, attached_registry, monkeypatch):
    """A case_dir NOT under STATUS_ROOT returns D-15 invalid-kwargs(field=case_dir)."""
    from mcp_gateway.tools import samples

    monkeypatch.setattr(samples, "STATUS_ROOT", str(tmp_path / "status"), raising=True)
    (tmp_path / "status").mkdir(parents=True)
    bogus = tmp_path / "elsewhere" / "not-a-case"
    bogus.mkdir(parents=True)

    result = await tjobs.start_tool_job(
        tool="_sleep_probe",
        kwargs={"seconds": 0},
        case_dir=str(bogus),
    )
    assert result.get("error") == "invalid kwargs"
    assert result["field"] == "case_dir"
