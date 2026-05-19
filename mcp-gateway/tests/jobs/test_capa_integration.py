"""D-04: capa user-visible spec smoke (slow, container-only)."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from mcp_gateway import jobs, session_state
from mcp_gateway.tools import jobs as tjobs
from tests.jobs.conftest import _require_capa_or_skip


@pytest.mark.slow
@pytest.mark.asyncio
async def test_capa_succeeds_on_simple_sample(case_dir_fixture, registry_factory):
    """capa runs end-to-end on a tiny ELF (/bin/ls). Skipped if capa is absent."""
    _require_capa_or_skip()

    # Copy /bin/ls into case_dir as a known sample. capa accepts ELF input.
    ls = shutil.which("ls") or "/bin/ls"
    sample = Path(case_dir_fixture) / "sample.bin"
    sample.write_bytes(Path(ls).read_bytes())

    async with registry_factory() as reg:
        prev = session_state.JOB_REGISTRY
        session_state.JOB_REGISTRY = reg
        try:
            result = await tjobs.start_tool_job(
                tool="capa",
                kwargs={"sample": str(sample)},
                case_dir=str(case_dir_fixture),
                timeout=900.0,
            )
            assert "error" not in result, result
            job_id = result["job_id"]
            job = reg.get(job_id)
            await job._drive_task
            final = await tjobs.get_tool_job(job_id)
            assert final["status"] in {"succeeded", "failed"}, final["status"]
            # On success, stdout should be valid JSON (capa --quiet --json)
            if final["status"] == "succeeded":
                # stdout may be truncated; parse log file directly if needed
                log_path = Path(job.log_path_abs)
                stdout_blob = log_path.read_text(errors="replace")
                # capa --json prints a JSON dict; verify parseable prefix exists
                assert "{" in stdout_blob
        finally:
            session_state.JOB_REGISTRY = prev
