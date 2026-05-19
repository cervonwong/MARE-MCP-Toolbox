"""Test D-09 counter-based log cap (SC-3): MARE_JOB_KILLED_LOG_CAP marker on disk."""
from __future__ import annotations

from pathlib import Path

import pytest

from mcp_gateway import jobs


MARKER = b"\n=== MARE_JOB_KILLED_LOG_CAP ===\n"


@pytest.mark.asyncio
async def test_sc3_log_burst_killed_with_marker(case_dir_fixture, registry_factory):
    """Override MAX_JOB_LOG_MB=1 so the cap reaches in <~30s."""
    async with registry_factory(
        cancel_grace_s=0.2,
        env={"MCP_GATEWAY_MAX_JOB_LOG_MB": "1"},
    ) as reg:
        spec = jobs.JOB_TOOL_REGISTRY["_log_burst_probe"]
        job = await reg.submit(
            spec=spec, kwargs={},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=60.0,
        )
        try:
            await job._drive_task
        except Exception:
            pass

        assert job.status == "killed_log_cap", f"unexpected status: {job.status}"

        log_path = Path(job.log_path_abs)
        assert log_path.exists()
        data = log_path.read_bytes()

        # Cap is 1 MiB; on-disk file size <= ~1 MiB + the marker overshoot tolerance.
        # _drain writes the marker once when cap is exceeded.
        assert len(data) <= (1 * 1024 * 1024) + 128, f"unexpected log size: {len(data)}"
        assert data.endswith(MARKER), (
            "log file did not end with MARE_JOB_KILLED_LOG_CAP marker"
        )
