"""Test D-16 two-tier progress (Tier-1 stderr parse + Tier-2 ctx.report_progress)."""
from __future__ import annotations

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.tools import jobs as tjobs
from tests.jobs.conftest import FakeContext


def _progress_parser(line: bytes):
    if b"PROGRESS" in line:
        return (5, 10, "halfway")
    return None


SYNTHETIC_SPEC = jobs.JobToolSpec(
    name="_progress_test_probe",
    slug="progress_test_probe",
    build_argv=lambda case_dir, kw: [
        "sh", "-c", "printf 'PROGRESS\\n' >&2; sleep 0"
    ],
    default_timeout_s=10.0,
    progress_parser=_progress_parser,
    kwargs_schema=None,
    description="Synthetic progress test probe.",
)


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
async def test_progress_fields_set_on_drive(case_dir_fixture, attached_registry):
    """Tier-1: stderr 'PROGRESS' line is parsed; progress/total/message set."""
    job = await attached_registry.submit(
        spec=SYNTHETIC_SPEC, kwargs={},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=10.0,
    )
    await job._drive_task
    assert job.progress == 5
    assert job.progress_total == 10
    assert job.progress_message == "halfway"


@pytest.mark.asyncio
async def test_ctx_report_progress_called_on_poll(case_dir_fixture, attached_registry, fake_ctx):
    """Tier-2: get_tool_job(ctx=...) calls ctx.report_progress when progress changed."""
    job = await attached_registry.submit(
        spec=SYNTHETIC_SPEC, kwargs={},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=10.0,
    )
    await job._drive_task

    await tjobs.get_tool_job(job.job_id, ctx=fake_ctx)
    assert fake_ctx.calls == [(5, 10, "halfway")]


@pytest.mark.asyncio
async def test_ctx_dedup_same_session_no_resend(case_dir_fixture, attached_registry, fake_ctx):
    """D-16 dedup: same session_id, unchanged state -> no second report."""
    job = await attached_registry.submit(
        spec=SYNTHETIC_SPEC, kwargs={},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=10.0,
    )
    await job._drive_task

    await tjobs.get_tool_job(job.job_id, ctx=fake_ctx)
    await tjobs.get_tool_job(job.job_id, ctx=fake_ctx)
    assert len(fake_ctx.calls) == 1, "dedup should suppress the second report"


@pytest.mark.asyncio
async def test_ctx_different_session_does_report(case_dir_fixture, attached_registry):
    """D-16 dedup: a different ctx.session_id gets its own first-time report."""
    job = await attached_registry.submit(
        spec=SYNTHETIC_SPEC, kwargs={},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=10.0,
    )
    await job._drive_task

    ctx_a = FakeContext(session_id="session-A")
    ctx_b = FakeContext(session_id="session-B")
    await tjobs.get_tool_job(job.job_id, ctx=ctx_a)
    await tjobs.get_tool_job(job.job_id, ctx=ctx_b)
    assert ctx_a.calls == [(5, 10, "halfway")]
    assert ctx_b.calls == [(5, 10, "halfway")]


@pytest.mark.asyncio
async def test_ctx_no_call_when_progress_none(case_dir_fixture, attached_registry, fake_ctx):
    """When job.progress is None, ctx.report_progress is NEVER called."""
    # _sleep_probe has no progress_parser -> progress stays None
    spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
    job = await attached_registry.submit(
        spec=spec, kwargs={"seconds": 0},
        case_dir_resolved=str(case_dir_fixture),
        effective_timeout_s=5.0,
    )
    await job._drive_task
    assert job.progress is None

    await tjobs.get_tool_job(job.job_id, ctx=fake_ctx)
    assert fake_ctx.calls == []
