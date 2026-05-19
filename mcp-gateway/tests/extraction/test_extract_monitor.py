"""Phase 10 GREEN tests for extraction.start_extract_monitor (D-17 / Plan 03).

Cap-exceeded path; clean-exit on terminal; monitor poll count updates meta.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcp_gateway import extraction


def _make_ext_with_meta(tmp_path: Path) -> Path:
    case = tmp_path / "800-case"
    case.mkdir()
    d = extraction.extraction_dir(case, "binwalk")
    extraction.write_meta(d, {
        "engine": "binwalk", "mode": "extract", "status": "running",
        "monitor_polls": 0, "cap_exceeded": False,
    })
    return d


class _FakeJobsModule:
    """Minimal stand-in for `mcp_gateway.tools.jobs` used by the monitor's
    LOCAL import.  Provides async get_tool_job + cancel_tool_job whose
    behaviour is driven by a script of return-values supplied per test.
    """

    def __init__(self, script: list[dict]):
        self._script = list(script)
        self._calls: list[str] = []
        self.cancel_calls: list[str] = []

    async def get_tool_job(self, job_id, *, ctx=None):
        self._calls.append("get")
        if self._script:
            return self._script.pop(0)
        # Fallback once exhausted
        return {"status": "succeeded", "exit_code": 0}

    async def cancel_tool_job(self, job_id):
        self.cancel_calls.append(job_id)
        return {"status": "cancelled", "job_id": job_id}


def _install_fake_jobs(monkeypatch, fake: _FakeJobsModule) -> None:
    """The monitor does `from mcp_gateway.tools import jobs as tools_jobs`
    inside the coroutine — replace the attribute on the parent module."""
    import mcp_gateway.tools as tools_pkg
    monkeypatch.setattr(tools_pkg, "jobs", fake, raising=False)


def test_cap_exceeded_cancels_job(tmp_path, monkeypatch):
    """When _du_sb returns size > cap, monitor writes the marker, flips meta
    to status='cap_exceeded', and calls cancel_tool_job."""
    d = _make_ext_with_meta(tmp_path)
    # Drop some files so _du_sb returns > 0
    (d / "big1.bin").write_bytes(b"x" * 1024)
    (d / "big2.bin").write_bytes(b"y" * 1024)

    # First poll returns "running" so the loop enters the cap check.
    fake = _FakeJobsModule(script=[
        {"status": "running", "exit_code": None},
        {"status": "cancelled", "exit_code": -15},  # post-terminal hook reads this
    ])
    _install_fake_jobs(monkeypatch, fake)

    # interval_s=0.01 to keep the test fast; max_bytes=0 => any non-empty tree triggers.
    asyncio.run(
        extraction.start_extract_monitor(
            "job-xyz",
            d,
            interval_s=0.01,
            max_bytes=0,
        )
    )

    # Marker file exists
    assert (d / ".MARE_EXTRACT_CAP_EXCEEDED").is_file()
    # Meta reflects cap_exceeded
    meta = json.loads((d / "_mare_meta.json").read_text(encoding="utf-8"))
    assert meta["cap_exceeded"] is True
    assert meta["status"] == "cap_exceeded"
    # cancel_tool_job was called once
    assert fake.cancel_calls == ["job-xyz"]


def test_clean_exit_on_terminal(tmp_path, monkeypatch):
    """Monitor exits cleanly when get_tool_job returns a terminal status."""
    d = _make_ext_with_meta(tmp_path)
    fake = _FakeJobsModule(script=[
        {"status": "succeeded", "exit_code": 0},  # first poll already terminal
        {"status": "succeeded", "exit_code": 0},  # post-terminal hook read
    ])
    _install_fake_jobs(monkeypatch, fake)

    # Plant a symlink so the post-terminal quarantine has work to do.
    target = tmp_path / "outside-tgt"
    target.write_text("x")
    import os
    os.symlink(str(target), str(d / "ln"))

    # Use a large cap so cap-exceeded never fires.
    asyncio.run(
        extraction.start_extract_monitor(
            "job-clean",
            d,
            interval_s=0.01,
            max_bytes=10**12,
        )
    )

    meta = json.loads((d / "_mare_meta.json").read_text(encoding="utf-8"))
    # Status should be succeeded (final job status)
    assert meta["status"] == "succeeded"
    # Symlink quarantine ran in the post-terminal hook
    assert meta["symlinks_quarantined"] >= 1
    # No cancel
    assert fake.cancel_calls == []


def test_monitor_poll_count_updates_meta(tmp_path, monkeypatch):
    """When get_tool_job returns non-terminal N times then terminal, meta's
    monitor_polls counter should reflect N polls."""
    d = _make_ext_with_meta(tmp_path)
    # 3 non-terminal polls then terminal
    fake = _FakeJobsModule(script=[
        {"status": "running", "exit_code": None},
        {"status": "running", "exit_code": None},
        {"status": "running", "exit_code": None},
        {"status": "succeeded", "exit_code": 0},
        {"status": "succeeded", "exit_code": 0},  # post-terminal read
    ])
    _install_fake_jobs(monkeypatch, fake)

    asyncio.run(
        extraction.start_extract_monitor(
            "job-polls",
            d,
            interval_s=0.005,
            max_bytes=10**12,
        )
    )

    meta = json.loads((d / "_mare_meta.json").read_text(encoding="utf-8"))
    # Each non-terminal poll increments monitor_polls before the next sleep.
    assert meta["monitor_polls"] == 3
    assert meta["status"] == "succeeded"
