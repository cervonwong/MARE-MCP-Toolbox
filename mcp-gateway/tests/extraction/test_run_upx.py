"""Phase 10 GREEN tests for tools.extract.run_upx_test / list / unpack."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from mcp_gateway.tools import extract


def _patch_resolve(monkeypatch) -> None:
    def _fake_case(case_dir: str) -> str:
        return str(Path(case_dir).resolve())
    monkeypatch.setattr("mcp_gateway.tools.extract.resolve_case_dir", _fake_case)

    def _fake_sample(sample: str) -> str:
        return "/agent/uploads/deadbeef/" + Path(sample).name
    monkeypatch.setattr("mcp_gateway.tools.extract.resolve_sample", _fake_sample)


def test_test_not_packed(tmp_path, monkeypatch):
    """upx -t on a not-packed binary returns is_upx_packed=False, test_result='not_packed'."""
    case = tmp_path / "700-case"
    case.mkdir()
    _patch_resolve(monkeypatch)

    fake_run_tool_dict = {
        "exit_code": 1,
        "stdout_head": "",
        "stderr_head": "upx: x.bin: NotPackedException: Not packed by UPX",
        "argv": ["upx", "-t", "--", "/agent/uploads/deadbeef/x.bin"],
        "log_path": "tool-logs/upx-test.txt",
        "started_at": "2026-05-19T14:32:11Z",
        "completed_at": "2026-05-19T14:32:11Z",
        "duration_s": 0.1,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "case_dir": str(case),
        "slug": "upx_test",
    }

    async def _fake_run_tool(*args, **kwargs):
        return fake_run_tool_dict
    monkeypatch.setattr("mcp_gateway.tools.extract.run_tool", _fake_run_tool)

    res = asyncio.run(extract.run_upx_test(str(case), "x.bin"))

    assert "error" not in res, res
    assert res["engine"] == "upx"
    assert res["mode"] == "test"
    assert res["is_upx_packed"] is False
    assert res["test_result"] == "not_packed"


def test_list_parses_columns(tmp_path, monkeypatch):
    """upx -l stderr table parses into rows with file/compressed/uncompressed/ratio/format columns."""
    case = tmp_path / "701-case"
    case.mkdir()
    _patch_resolve(monkeypatch)

    fake_stderr = (
        "       File size         Ratio      Format      Name\n"
        "   --------------------   ------   -----------   -----------\n"
        "       12345    25000     50.00%   linux/elf64   x.bin\n"
        "       67890   100000     30.50%   linux/elf64   y.bin\n"
    )
    fake_run_tool_dict = {
        "exit_code": 0,
        "stdout_head": "",
        "stderr_head": fake_stderr,
        "argv": ["upx", "-l", "--", "/agent/uploads/deadbeef/x.bin"],
        "log_path": "tool-logs/upx-list.txt",
        "started_at": "2026-05-19T14:32:11Z",
        "completed_at": "2026-05-19T14:32:11Z",
        "duration_s": 0.1,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "case_dir": str(case),
        "slug": "upx_list",
    }

    async def _fake_run_tool(*args, **kwargs):
        return fake_run_tool_dict
    monkeypatch.setattr("mcp_gateway.tools.extract.run_tool", _fake_run_tool)

    res = asyncio.run(extract.run_upx_list(str(case), "x.bin"))

    assert "error" not in res, res
    assert res["engine"] == "upx"
    assert res["mode"] == "list"
    assert isinstance(res["rows"], list)
    # At least the 2 parseable rows should be present
    parsed = [r for r in res["rows"] if r.get("compressed_size") is not None]
    assert len(parsed) >= 2
    # Inspect first parsed row column types
    sample_row = parsed[0]
    assert isinstance(sample_row["compressed_size"], int)
    assert isinstance(sample_row["uncompressed_size"], int)
    assert isinstance(sample_row["ratio"], str)
    assert isinstance(sample_row["format"], str)


@pytest.mark.slow
def test_unpack_writes_output(_require_upx_or_skip, tmp_path, monkeypatch):
    """Slow-integration: real upx -d on a fixture. We don't have a real packed
    binary fixture in the repo, so this stubs run_tool and verifies the
    contract — the slow gate ensures the test only runs when upx is on PATH.
    """
    case = tmp_path / "702-case"
    case.mkdir()
    _patch_resolve(monkeypatch)

    fake_run_tool_dict = {
        "exit_code": 0,
        "stdout_head": "",
        "stderr_head": "Unpacked 1 file.\n",
        "argv": ["upx", "-d", "-o", "/tmp/x.bin.unpacked", "--", "/agent/uploads/deadbeef/x.bin"],
        "log_path": "tool-logs/upx-unpack.txt",
        "started_at": "2026-05-19T14:32:11Z",
        "completed_at": "2026-05-19T14:32:11Z",
        "duration_s": 0.5,
        "stdout_truncated": False,
        "stderr_truncated": False,
        "case_dir": str(case),
        "slug": "upx_unpack",
    }

    async def _fake_run_tool(*args, **kwargs):
        # Simulate that upx actually wrote the unpacked file
        argv = args[1] if len(args) >= 2 else kwargs.get("argv") or []
        if "-o" in argv:
            target = argv[argv.index("-o") + 1]
            Path(target).write_bytes(b"\x7fELF unpacked content")
        return fake_run_tool_dict
    monkeypatch.setattr("mcp_gateway.tools.extract.run_tool", _fake_run_tool)

    res = asyncio.run(extract.run_upx_unpack(str(case), "x.bin"))

    assert "error" not in res, res
    assert res["engine"] == "upx"
    assert res["mode"] == "unpack"
    # extraction_dir should be case-rel
    assert res["extraction_dir"].startswith("extracted/upx-")
    # unpacked_path should be present (case-rel) when the file exists
    assert res["unpacked_path"] is not None
    assert res["unpacked_path"].startswith("extracted/upx-")
    assert res["unpacked_size"] > 0
