"""Tests for atomic artifact tools — verify they assemble the correct argv for run_script.

We patch subprocess_runner.run_script to capture argv rather than actually execute scripts.
"""
from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_gateway.tools import artifacts as artifacts_mod
from mcp_gateway.tools import samples as samples_mod


@pytest.fixture
def captured_argv(monkeypatch, tmp_path):
    captured: list[tuple[list[str], dict]] = []

    async def fake_run_script(argv, *, cwd="/agent", timeout=600.0, env=None):
        captured.append((list(argv), {"cwd": cwd, "timeout": timeout}))
        return {"exit_code": 0, "stdout": str(tmp_path / "001-demo.bin"), "stderr": ""}

    monkeypatch.setattr(artifacts_mod, "run_script", fake_run_script)
    # Also allow resolve_sample to accept a sample under a tmp uploads dir.
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    sha = "c" * 64
    sd = uploads / sha
    sd.mkdir()
    f = sd / "demo.bin"
    f.write_bytes(b"\x00")
    monkeypatch.setattr(samples_mod, "UPLOADS_ROOT", uploads)
    monkeypatch.setattr(samples_mod, "ALLOWED_PREFIXES", (uploads,))
    return captured, sha, f


async def _invoke(fn, *args, **kwargs):
    return await fn(*args, **kwargs)


def _get_tool(mcp: FastMCP, name: str):
    """Extract the underlying handler callable from a registered FastMCP tool."""
    # FastMCP internal — if upgraded past 1.27, rewrite using create_connected_server_and_client_session.call_tool(name, args)
    # Private-attr access is acceptable here because unit tests need direct access to the
    # bound function for argv-shape assertions (the public API would hide argv inside a
    # subprocess call). Name listing / tools/list tests use the public API (see test_tool_list.py).
    mgr = getattr(mcp, "_tool_manager", None)
    if mgr is None:
        raise AssertionError("FastMCP version missing _tool_manager")
    tool = mgr._tools[name]
    return tool.fn


@pytest.fixture
def registered_mcp():
    mcp = FastMCP("test", stateless_http=True)
    artifacts_mod.register(mcp)
    return mcp


@pytest.mark.asyncio
async def test_init_case_argv(captured_argv, registered_mcp):
    captured, sha, f = captured_argv
    init_case = _get_tool(registered_mcp, "init_case")
    await init_case(sample=sha)
    assert captured[0][0][0] == "bash"
    assert captured[0][0][1].endswith("init_status_tree.sh")
    assert captured[0][0][2] == str(f.resolve())
    assert captured[0][1]["cwd"] == "/agent"


@pytest.mark.asyncio
async def test_collect_strings_with_case_dir(captured_argv, registered_mcp):
    captured, sha, f = captured_argv
    collect_strings = _get_tool(registered_mcp, "collect_strings")
    await collect_strings(sample=sha, case_dir="/agent/status/001-demo.bin")
    argv = captured[0][0]
    assert argv[1].endswith("collect_strings.sh")
    assert argv[2] == str(f.resolve())
    assert argv[3] == "/agent/status/001-demo.bin"


@pytest.mark.asyncio
async def test_rank_signals_uses_python3(captured_argv, registered_mcp):
    captured, _sha, _f = captured_argv
    rank_signals = _get_tool(registered_mcp, "rank_signals")
    await rank_signals(case_dir="/agent/status/001-demo.bin")
    argv = captured[0][0]
    assert argv[0] == "python3"
    assert argv[1].endswith("rank_signals.py")
    assert argv[2:4] == ["--status-dir", "/agent/status/001-demo.bin"]


@pytest.mark.asyncio
async def test_update_state_phase_flag(captured_argv, registered_mcp):
    captured, _sha, _f = captured_argv
    update_state = _get_tool(registered_mcp, "update_state")
    await update_state(case_dir="/x", phase="triage_complete")
    argv = captured[0][0]
    assert argv == ["python3", argv[1], "--status-dir", "/x", "--phase", "triage_complete"]


def test_get_artifact_rejects_traversal(tmp_path, registered_mcp):
    get_artifact = _get_tool(registered_mcp, "get_artifact")
    (tmp_path / "00_sample_profile.md").write_text("hi")
    with pytest.raises(ValueError):
        get_artifact(case_dir=str(tmp_path), artifact_name="../etc/passwd")
    with pytest.raises(ValueError):
        get_artifact(case_dir=str(tmp_path), artifact_name="foo/bar")


def test_get_artifact_reads_content(tmp_path, registered_mcp):
    get_artifact = _get_tool(registered_mcp, "get_artifact")
    (tmp_path / "00_sample_profile.md").write_text("sample-content")
    r = get_artifact(case_dir=str(tmp_path), artifact_name="00_sample_profile.md")
    assert r["content"] == "sample-content"
    assert r["size"] == len("sample-content")
