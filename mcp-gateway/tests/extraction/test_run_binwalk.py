"""Phase 10 GREEN tests for tools.extract.run_binwalk (D-02).

Signatures + entropy parse sync; extract mode dispatches a Phase 9 job.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcp_gateway import extraction
from mcp_gateway.tools import extract


def _patch_resolve(monkeypatch, case_path: Path) -> None:
    def _fake_case(case_dir: str) -> str:
        return str(Path(case_dir).resolve())
    monkeypatch.setattr("mcp_gateway.tools.extract.resolve_case_dir", _fake_case)

    def _fake_sample(sample: str) -> str:
        # Pretend any input resolves to a fake absolute path.
        return "/agent/uploads/deadbeef/" + Path(sample).name
    monkeypatch.setattr("mcp_gateway.tools.extract.resolve_sample", _fake_sample)


def test_signatures_mode_parses_rows(tmp_path, monkeypatch):
    case = tmp_path / "500-case"
    case.mkdir()
    _patch_resolve(monkeypatch, case)

    # Fake binwalk stdout with 2 signature rows in the documented text format.
    fake_stdout = (
        "        0  0x0       PE32 executable\n"
        "      256  0x100     ELF executable, 64-bit, statically linked\n"
    )
    fake_run_tool_dict = {
        "exit_code": 0,
        "stdout_head": fake_stdout,
        "stderr_head": "",
        "argv": ["binwalk", "-l", "report.json", "-q", "--", "/agent/uploads/deadbeef/x.bin"],
        "log_path": "tool-logs/binwalk-1.txt",
        "started_at": "2026-05-19T14:32:11Z",
        "completed_at": "2026-05-19T14:32:12Z",
        "duration_s": 1.0,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "case_dir": str(case),
        "slug": "binwalk_signatures",
    }

    async def _fake_run_tool(*args, **kwargs):
        return fake_run_tool_dict
    monkeypatch.setattr("mcp_gateway.tools.extract.run_tool", _fake_run_tool)

    res = asyncio.run(extract.run_binwalk(str(case), "x.bin", mode="signatures"))

    assert "error" not in res, res
    assert res["mode"] == "signatures"
    assert res["engine"] == "binwalk"
    # extraction_dir is case-rel (no leading slash, starts with "extracted/")
    assert res["extraction_dir"].startswith("extracted/binwalk-")
    assert isinstance(res["signatures"], list)
    assert len(res["signatures"]) >= 2
    assert res["entropy"] is None
    assert res["job_id"] is None


def test_entropy_mode_parses_rows(tmp_path, monkeypatch):
    case = tmp_path / "501-case"
    case.mkdir()
    _patch_resolve(monkeypatch, case)

    fake_stdout = (
        "0x00000000  0.123456 rising\n"
        "0x00001000  0.987654 falling\n"
    )
    fake_run_tool_dict = {
        "exit_code": 0,
        "stdout_head": fake_stdout,
        "stderr_head": "",
        "argv": ["binwalk", "-E", "--", "/agent/uploads/deadbeef/x.bin"],
        "log_path": "tool-logs/binwalk-2.txt",
        "started_at": "2026-05-19T14:32:11Z",
        "completed_at": "2026-05-19T14:32:13Z",
        "duration_s": 2.0,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "case_dir": str(case),
        "slug": "binwalk_entropy",
    }

    async def _fake_run_tool(*args, **kwargs):
        return fake_run_tool_dict
    monkeypatch.setattr("mcp_gateway.tools.extract.run_tool", _fake_run_tool)

    res = asyncio.run(extract.run_binwalk(str(case), "x.bin", mode="entropy"))

    assert "error" not in res, res
    assert res["mode"] == "entropy"
    assert res["engine"] == "binwalk"
    assert res["signatures"] is None
    assert isinstance(res["entropy"], list)
    assert len(res["entropy"]) >= 2


@pytest.mark.slow
def test_extract_mode_dispatches_job(_require_binwalk_or_skip, tmp_path, monkeypatch):
    """mode=extract returns a Phase 9 D-19 snapshot dict layered with Phase 10
    extension keys. Stubs start_tool_job + _spawn_monitor to avoid real job
    submission.
    """
    case = tmp_path / "502-case"
    case.mkdir()
    _patch_resolve(monkeypatch, case)

    fake_snapshot = {
        "job_id": "job-abc-1234",
        "status": "pending",
        "tool": "binwalk_extract",
        "argv": [],
        "log_path": "tool-logs/binwalk-extract.txt",
    }

    async def _fake_start_tool_job(**kwargs):
        return fake_snapshot
    monkeypatch.setattr(
        "mcp_gateway.tools.extract.tools_jobs.start_tool_job",
        _fake_start_tool_job,
    )

    def _fake_spawn(job_id, ext_dir):
        return None
    monkeypatch.setattr("mcp_gateway.extraction._spawn_monitor", _fake_spawn)

    res = asyncio.run(extract.run_binwalk(str(case), "x.bin", mode="extract"))

    assert "error" not in res, res
    assert res["mode"] == "extract"
    assert res["engine"] == "binwalk"
    assert res["job_id"] == "job-abc-1234"
    assert res["extraction_dir"].startswith("extracted/binwalk-")


def test_errors_structured(tmp_path, monkeypatch):
    """Invalid case_dir -> D-22 shape 1 error dict (not raised)."""
    # Force resolve_case_dir to raise so we hit the invalid-case-dir envelope.
    def _bad_case(case_dir: str) -> str:
        raise ValueError("not under STATUS_ROOT")
    monkeypatch.setattr("mcp_gateway.tools.extract.resolve_case_dir", _bad_case)

    res = asyncio.run(extract.run_binwalk("/nonexistent/case", "x.bin"))

    assert isinstance(res, dict)
    assert res.get("error") == "invalid case_dir"
    assert "hint" in res
