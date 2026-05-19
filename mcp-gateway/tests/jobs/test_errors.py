"""Test D-15 four locked error dict shapes (cap, unknown, not-found, invalid-kwargs)."""
from __future__ import annotations

import asyncio

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.tools import jobs as tjobs


@pytest.fixture
async def attached_registry(registry_factory):
    async with registry_factory(max_inflight=2) as reg:
        prev = session_state.JOB_REGISTRY
        session_state.JOB_REGISTRY = reg
        try:
            yield reg
        finally:
            session_state.JOB_REGISTRY = prev


def _no_exception(coro_factory):
    """Wrap a coroutine factory; fail the test if any exception escapes."""
    async def _wrapped():
        try:
            return await coro_factory()
        except Exception as e:
            pytest.fail(f"MCP tool raised {type(e).__name__}: {e}")
    return _wrapped()


@pytest.mark.asyncio
async def test_cap_reached_shape(case_dir_fixture, attached_registry):
    """D-15 #1: when inflight >= cap, start_tool_job returns cap-reached dict."""
    # Cap is 2 long jobs
    j1 = await tjobs.start_tool_job(
        tool="_sleep_probe", kwargs={"seconds": 30},
        case_dir=str(case_dir_fixture),
    )
    assert "error" not in j1
    j2 = await tjobs.start_tool_job(
        tool="_sleep_probe", kwargs={"seconds": 30},
        case_dir=str(case_dir_fixture),
    )
    assert "error" not in j2

    # Third must fail with cap-reached
    j3 = await tjobs.start_tool_job(
        tool="_sleep_probe", kwargs={"seconds": 30},
        case_dir=str(case_dir_fixture),
    )
    assert j3.get("error") == "job cap reached"
    assert j3["inflight"] == 2
    assert j3["cap"] == 2
    assert isinstance(j3.get("hint"), str) and j3["hint"]

    # Drain: cancel the two inflight
    for jid in (j1["job_id"], j2["job_id"]):
        await tjobs.cancel_tool_job(jid)


@pytest.mark.asyncio
async def test_unknown_tool_shape(case_dir_fixture, attached_registry):
    result = await tjobs.start_tool_job(
        tool="unknown_tool",
        kwargs={},
        case_dir=str(case_dir_fixture),
    )
    assert result["error"] == "unknown job tool"
    assert result["tool"] == "unknown_tool"
    assert sorted(result["known"]) == ["_log_burst_probe", "_sleep_probe", "capa"]
    assert isinstance(result["hint"], str) and result["hint"]


@pytest.mark.asyncio
async def test_job_not_found_shape(attached_registry):
    result = await tjobs.get_tool_job("0000000000000000")
    assert "job not found" in result["error"]
    assert result["job_id"] == "0000000000000000"
    assert "hint" in result
    assert isinstance(result["hint"], str) and result["hint"]


@pytest.mark.asyncio
async def test_invalid_kwargs_shape(case_dir_fixture, attached_registry):
    result = await tjobs.start_tool_job(
        tool="_sleep_probe",
        kwargs={"seconds": -1},
        case_dir=str(case_dir_fixture),
    )
    assert result["error"] == "invalid kwargs"
    assert result["field"] == "seconds"
    assert result["expected"] == ">= 0"
    assert result["got"] == "-1"


@pytest.mark.asyncio
async def test_capa_missing_sample_returns_invalid_kwargs(case_dir_fixture, attached_registry):
    """D-15 #4 (Task 1 of 09-05-PLAN): capa with kwargs={} must NOT raise.

    Regression for 09-VERIFICATION.md truth #7 / CR-02: previously KeyError('sample')
    from _build_capa_argv escaped the MCP boundary. After this fix, the schema's
    'required': True on capa.sample triggers _validate_kwargs to raise InvalidKwargs
    BEFORE build_argv is reached.
    """
    async def _call():
        return await tjobs.start_tool_job(
            tool="capa",
            kwargs={},
            case_dir=str(case_dir_fixture),
        )
    result = await _no_exception(_call)
    assert result["error"] == "invalid kwargs"
    assert result["field"] == "sample"
    assert result["expected"] == "required field"
    assert result["got"] == "missing"


@pytest.mark.asyncio
async def test_capa_path_traversal_returns_invalid_kwargs(case_dir_fixture, attached_registry):
    """D-15 #4 (Task 2 of 09-05-PLAN): capa with traversal sample must NOT raise.

    Regression for 09-VERIFICATION.md truth #7 / CR-01: previously
    ValueError('path traversal rejected') from samples.resolve_sample escaped the
    MCP boundary. After this fix, start_tool_job's broadened except wraps
    (ValueError, FileNotFoundError, KeyError, OSError) into a D-15 #4 InvalidKwargs
    with field='kwargs'.
    """
    async def _call():
        return await tjobs.start_tool_job(
            tool="capa",
            kwargs={"sample": "../etc/passwd"},
            case_dir=str(case_dir_fixture),
        )
    result = await _no_exception(_call)
    assert result["error"] == "invalid kwargs"
    assert result["field"] == "kwargs"
    assert result["expected"] == "valid per-tool argv inputs"
    # got is f"{type(e).__name__}: {e}" -- exception class varies (ValueError on
    # traversal-rejection, FileNotFoundError if traversal isn't pre-checked).
    # Both are caught by the broadened except clause.
    assert result["got"].startswith(("ValueError:", "FileNotFoundError:", "OSError:", "KeyError:"))


@pytest.mark.asyncio
async def test_every_error_has_error_key(attached_registry, case_dir_fixture):
    results = [
        await tjobs.start_tool_job(tool="unknown", kwargs={}, case_dir=str(case_dir_fixture)),
        await tjobs.get_tool_job("0000000000000000"),
        await tjobs.cancel_tool_job("0000000000000000"),
        await tjobs.start_tool_job(
            tool="_sleep_probe", kwargs={"seconds": -1}, case_dir=str(case_dir_fixture),
        ),
    ]
    for r in results:
        assert isinstance(r.get("error"), str)
        assert r["error"]


@pytest.mark.asyncio
async def test_no_tool_handler_raises(attached_registry, case_dir_fixture):
    """D-15 contract: tools NEVER raise out of the MCP boundary."""
    async def _calls():
        await tjobs.start_tool_job(tool="unknown", kwargs={}, case_dir=str(case_dir_fixture))
        await tjobs.get_tool_job("0000000000000000")
        await tjobs.cancel_tool_job("0000000000000000")
        await tjobs.list_tool_jobs(state="_specs")
        # 09-05-PLAN gap-closure: capa with missing/invalid sample previously raised
        await tjobs.start_tool_job(tool="capa", kwargs={}, case_dir=str(case_dir_fixture))
        await tjobs.start_tool_job(
            tool="capa", kwargs={"sample": "../etc/passwd"},
            case_dir=str(case_dir_fixture),
        )
    await _no_exception(lambda: _calls())
