"""Tests for composite workflow tools (run_triage ordering, run_deep_analysis phase arg)."""
from __future__ import annotations
from pathlib import Path

import pytest
from mcp.server.fastmcp import FastMCP

from mcp_gateway.tools import workflows as workflows_mod
from mcp_gateway.tools import samples as samples_mod


EXPECTED_ORDER = [
    "init_status_tree.sh",
    "collect_strings.sh",
    "collect_imports.sh",
    "scan_yara.sh",
    "scan_capa.sh",
    "rank_signals.py",
    "build_hypothesis.py",
    "update_state.py",
]


@pytest.fixture
def mocked_run_triage(monkeypatch, tmp_path):
    invocations: list[list[str]] = []

    async def fake_run_script(argv, *, cwd="/agent", timeout=600.0, env=None):
        invocations.append(list(argv))
        # init_status_tree.sh prints the case_dir as the last stdout line
        if argv[1].endswith("init_status_tree.sh"):
            return {"exit_code": 0, "stdout": "/agent/status/001-demo.bin", "stderr": ""}
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(workflows_mod, "run_script", fake_run_script)

    uploads = tmp_path / "uploads"
    uploads.mkdir()
    sha = "d" * 64
    (uploads / sha).mkdir()
    (uploads / sha / "demo.bin").write_bytes(b"\x00")
    monkeypatch.setattr(samples_mod, "UPLOADS_ROOT", uploads)
    monkeypatch.setattr(samples_mod, "ALLOWED_PREFIXES", (uploads,))
    return invocations, sha


def _get_tool(mcp: FastMCP, name: str):
    # FastMCP internal — if upgraded past 1.27, rewrite using create_connected_server_and_client_session.call_tool(name, args)
    # This is acceptable for unit-level tests that need direct function access for argv assertion;
    # name listing and integration tests should use the public API (see test_tool_list.py).
    return mcp._tool_manager._tools[name].fn


@pytest.fixture
def mcp_instance():
    m = FastMCP("test", stateless_http=True)
    workflows_mod.register(m)
    return m


@pytest.mark.asyncio
async def test_run_triage_order(mocked_run_triage, mcp_instance):
    invocations, sha = mocked_run_triage
    run_triage = _get_tool(mcp_instance, "run_triage")
    result = await run_triage(sample=sha)
    scripts_called = [argv[1].split("/")[-1] for argv in invocations]
    assert scripts_called == EXPECTED_ORDER, f"got {scripts_called}"
    # All steps reported
    assert [s["step"] for s in result["steps"]] == [
        "init_case", "collect_strings", "collect_imports", "scan_yara", "scan_capa",
        "rank_signals", "build_hypothesis", "update_state",
    ]


@pytest.mark.asyncio
async def test_run_deep_analysis_sets_phase(mocked_run_triage, mcp_instance):
    invocations, _sha = mocked_run_triage
    run_deep = _get_tool(mcp_instance, "run_deep_analysis")
    await run_deep(case_dir="/agent/status/001-demo.bin")
    argv = invocations[0]
    assert argv[0] == "python3"
    assert argv[1].endswith("update_state.py")
    assert "--phase" in argv and argv[argv.index("--phase") + 1] == "planning_complete"


def test_generate_report_missing(mcp_instance, tmp_path):
    gen = _get_tool(mcp_instance, "generate_report")
    r = gen(case_dir=str(tmp_path))
    assert "error" in r


def test_generate_report_returns_content(mcp_instance, tmp_path):
    (tmp_path / "10_reporting_draft.md").write_text("# Report\nhello")
    gen = _get_tool(mcp_instance, "generate_report")
    r = gen(case_dir=str(tmp_path))
    assert r["content"].startswith("# Report")
