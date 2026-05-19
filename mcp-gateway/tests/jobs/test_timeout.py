"""Test D-08 job-level hard timeout -> killed_timeout."""
from __future__ import annotations

import pytest

from mcp_gateway import jobs


@pytest.mark.asyncio
async def test_timeout_killed_timeout(case_dir_fixture, registry_factory):
    async with registry_factory(cancel_grace_s=0.2) as reg:
        spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
        job = await reg.submit(
            spec=spec, kwargs={"seconds": 10},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=0.5,
        )
        try:
            await job._drive_task
        except Exception:
            pass

        assert job.status == "killed_timeout", f"unexpected status: {job.status}"
        snap = reg._build_snapshot(job)
        assert snap["timed_out"] is True
        # exit_code is non-zero (or -1 placeholder when proc was reaped)
        assert snap["exit_code"] != 0
