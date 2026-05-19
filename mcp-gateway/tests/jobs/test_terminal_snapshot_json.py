"""Test D-21 sibling .json snapshot written alongside the .txt log on terminal."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_gateway import jobs


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


@pytest.mark.asyncio
async def test_sibling_json_written_on_terminal(case_dir_fixture, registry_factory):
    async with registry_factory() as reg:
        spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
        job = await reg.submit(
            spec=spec, kwargs={"seconds": 0},
            case_dir_resolved=str(case_dir_fixture),
            effective_timeout_s=5.0,
        )
        await job._drive_task

        json_path = Path(job.log_path_abs).with_suffix(".json")
        assert json_path.exists(), "sibling .json was not written"

        loaded = json.loads(json_path.read_text())
        assert isinstance(loaded, dict)
        assert set(loaded.keys()) == D19_KEYS
        assert loaded["status"] in jobs._TERMINAL_STATUSES
        assert loaded["ended_at"] is not None
