"""Test D-06 7-state vocabulary + terminal-immutable invariant."""
from __future__ import annotations

import typing

import pytest

from mcp_gateway import jobs


def test_d06_status_vocabulary_exact_order():
    """D-06: exact 7 literal strings in exact order."""
    args = typing.get_args(jobs.JobStatus)
    assert args == (
        "pending", "running", "succeeded", "failed",
        "cancelled", "killed_timeout", "killed_log_cap",
    )


def test_terminal_statuses_frozenset():
    """5 terminal states (everything except pending/running)."""
    assert jobs._TERMINAL_STATUSES == frozenset({
        "succeeded", "failed", "cancelled", "killed_timeout", "killed_log_cap",
    })


@pytest.mark.asyncio
async def test_drive_completion_yields_terminal_status(case_dir_fixture, registry_factory):
    async with registry_factory() as reg:
        spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
        job = await reg.submit(
            spec=spec, kwargs={"seconds": 0},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=5.0,
        )
        await job._drive_task
        assert job.status in jobs._TERMINAL_STATUSES


@pytest.mark.asyncio
async def test_cancel_is_noop_on_terminal_job(case_dir_fixture, registry_factory):
    async with registry_factory() as reg:
        spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
        job = await reg.submit(
            spec=spec, kwargs={"seconds": 0},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=5.0,
        )
        await job._drive_task
        terminal_status = job.status
        # Cancel a terminal job -- must be a no-op (idempotent).
        await reg.cancel(job)
        assert job.status == terminal_status
