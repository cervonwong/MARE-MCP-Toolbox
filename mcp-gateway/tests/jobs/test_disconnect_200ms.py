"""SC-4: subprocess reaped within 200 ms after drive-task cancellation (JOBS-06)."""
from __future__ import annotations

import asyncio
import os
import time

import pytest

from mcp_gateway import jobs, session_state


@pytest.mark.asyncio
async def test_disconnect_dead_within_200ms(case_dir_fixture, registry_factory):
    """SC-4 ledger assertion. The drive task is externally cancelled (simulating
    a client disconnect / registry shutdown signal); the subprocess MUST be
    reaped within 200 ms via os.kill(pid, 0) -> ProcessLookupError."""
    async with registry_factory(cancel_grace_s=0.05) as reg:
        prev = session_state.JOB_REGISTRY
        session_state.JOB_REGISTRY = reg
        try:
            spec = jobs.JOB_TOOL_REGISTRY["_sleep_probe"]
            job = await reg.submit(
                spec=spec, kwargs={"seconds": 30},
                case_dir_resolved=str(case_dir_fixture),
                effective_timeout_s=60.0,
            )

            # Wait until spawn populates proc/pgid.
            for _ in range(200):
                if job.proc is not None and job.pgid is not None:
                    break
                await asyncio.sleep(0.005)
            assert job.proc is not None and job.pgid is not None, "spawn never completed"
            captured_pid = job.proc.pid

            t0 = time.monotonic()
            # SC-4: drive task externally cancelled.
            job._drive_task.cancel()
            try:
                await job._drive_task
            except asyncio.CancelledError:
                pass

            # Assert subprocess reaped within 200 ms.
            elapsed_ms = None
            for _ in range(40):  # 40 * 5ms = 200 ms
                try:
                    os.kill(captured_pid, 0)
                except ProcessLookupError:
                    elapsed_ms = (time.monotonic() - t0) * 1000.0
                    break
                await asyncio.sleep(0.005)

            assert elapsed_ms is not None, (
                "subprocess survived 200 ms after drive-task cancellation"
            )
            assert elapsed_ms < 200, f"reaped at {elapsed_ms:.1f} ms (> 200 ms)"
        finally:
            session_state.JOB_REGISTRY = prev
